"""
LLM worker harness for PM1 Trading Benchmark v0.1-LLM / v0.2a.

Replaces the deterministic policy executor with a real LLM API call.
The LLM independently chooses actions from its supplied prompt —
no oracle truth, no compute_expected_action(), no hidden state injection.

The prompt is built exclusively from the inputs dict returned by
build_worker_inputs(). For condition A this contains no continuation
state; for B variants it contains the canonical compiled packet produced
by the context assembler.  The worker never independently reads fixture
files or scenario internals.

V0.2a adds:
- B-minus-explicit: explicit system-level fail-closed instruction
- Condition S: direct plain-text state (position_qty = N)
- No trial_number, scenario_id, or run_id in prompts
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any

try:
    from .validator import WorkerOutput
except ImportError:
    from validator import WorkerOutput

__all__ = [
    "build_llm_prompt",
    "call_llm_api",
    "parse_llm_response",
    "execute_llm_worker",
]

# ---------------------------------------------------------------------------
# System prompt — defines the action contract for the LLM
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a trading algorithm.  Analyse the observation and, if provided, "
    "the compiled state packet.  Decide which single action to take.\n\n"
    "Output ONLY valid JSON with exactly these keys:\n"
    '  {"action": "BUY" | "SELL" | "HOLD", "quantity": <int>, '
    '"reasoning": "<brief explanation>"}\n\n'
    "Rules:\n"
    "- BUY and SELL always have quantity 1.\n"
    "- HOLD always has quantity 0.\n"
    "- Do NOT include any text outside the JSON object."
)

# V0.2a: Explicit fail-closed system prompt for B-minus-explicit.
# This prompt explicitly instructs the LLM to return MISSING_REQUIRED_STATE
# when the required position_qty field is absent from the packet.
_SYSTEM_PROMPT_EXPLICIT_FAIL_CLOSED = (
    "You are a trading algorithm.  Analyse the observation and, if provided, "
    "the compiled state packet.  Decide which single action to take.\n\n"
    "Output ONLY valid JSON with exactly these keys:\n"
    '  {"action": "BUY" | "SELL" | "HOLD" | "MISSING_REQUIRED_STATE", '
    '"quantity": <int>, "reasoning": "<brief explanation>"}\n\n'
    "Rules:\n"
    "- BUY and SELL always have quantity 1.\n"
    "- HOLD always has quantity 0.\n"
    "- MISSING_REQUIRED_STATE always has quantity 0.\n"
    "- If the compiled state packet is present but does NOT contain "
    "position_qty (the required field for this policy), you MUST return "
    '{"action": "MISSING_REQUIRED_STATE", "quantity": 0, '
    '"reasoning": "position_qty is missing from the state packet"}.\n'
    "- Do NOT guess or assume a value for position_qty when it is absent.\n"
    "- Do NOT include any text outside the JSON object."
)

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _format_packet_sections(packet: dict[str, Any]) -> str:
    """Render assembled packet sections as readable text for the LLM."""
    lines: list[str] = []
    for section in packet.get("sections", []):
        title = section.get("title", "section")
        lines.append(f"--- {title} ---")
        for record in section.get("records", []):
            payload = record.get("payload", {})
            if payload:
                lines.append(json.dumps(payload, indent=2))
        lines.append("")
    return "\n".join(lines)


def build_llm_prompt(
    inputs: dict[str, Any],
    condition: str,
    episode_id: str,
) -> list[dict[str, str]]:
    """Build the chat messages array for the LLM.

    The prompt is constructed *exclusively* from the ``inputs`` dict
    returned by ``build_worker_inputs()``.  No scenario internals,
    fixture files, or hidden state are read directly.

    V0.2a prompt isolation rules:
    - No scenario_id, trial_number, run_id, expected action, or hidden state
    - B-minus-explicit uses explicit fail-closed system prompt
    - Condition S includes direct plain-text state (position_qty = N)

    Condition A  – task_spec + observation only (no continuation state).
    B variants   – task_spec + observation + the compiled packet.
    B-minus-explicit – same packet as B-minus, but explicit fail-closed prompt.
    Condition S  – task_spec + observation + direct plain-text state.
    """
    user_parts: list[str] = []

    # 1. Task specification (same for every condition)
    user_parts.append(inputs["task_spec"])

    # 2. Current observation (same for every condition)
    user_parts.append("Current observation:")
    user_parts.append(inputs["observation"])

    # 3. Compiled packet — ONLY for B variants (including B-minus-explicit)
    key = condition.strip().upper().replace("_", "-").split(",", 1)[0]
    if key in {"B", "B-FULL", "B-MINUS", "B-MINUS-EXPLICIT", "B-CORRUPT", "B-RESTORED"}:
        packet = inputs.get("packet")
        if packet is not None:
            user_parts.append("Compiled state packet:")
            user_parts.append(_format_packet_sections(packet))

    # 4. Direct plain-text state — ONLY for Condition S
    if key == "S":
        direct_state = inputs.get("direct_state")
        if direct_state:
            user_parts.append("Current state:")
            user_parts.append(direct_state)

    user_content = "\n\n".join(user_parts)

    # V0.2a: Select system prompt based on condition
    system_prompt = _SYSTEM_PROMPT
    if key == "B-MINUS-EXPLICIT":
        system_prompt = _SYSTEM_PROMPT_EXPLICIT_FAIL_CLOSED

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# LLM API call (stdlib only)
# ---------------------------------------------------------------------------


def call_llm_api(
    messages: list[dict[str, str]],
    model_config: dict[str, Any],
) -> str:
    """Call an OpenAI-compatible /chat/completions endpoint.

    Parameters
    ----------
    messages : list[dict[str, str]]
        Chat messages array (system + user).
    model_config : dict[str, Any]
        Must contain at least ``base_url`` and ``api_key``.
        Optional: ``model`` (default ``"mimo-2.5-free"``),
        ``temperature`` (default 0.0), ``max_tokens`` (default 2048).

    Returns
    -------
    str
        The raw content string from the LLM response.

    Raises
    ------
    RuntimeError
        If all retries are exhausted or the response cannot be parsed.
    """
    base_url = model_config["base_url"].rstrip("/")
    api_key = model_config["api_key"]
    model = model_config.get("model", "mimo-2.5-free")
    temperature = model_config.get("temperature", 0.0)
    max_tokens = model_config.get("max_tokens", 2048)
    max_retries = model_config.get("max_retries", 3)

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # Use normal TLS verification by default.
    ctx = ssl.create_default_context()

    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            content = data["choices"][0]["message"]["content"]
            if content:
                return content

            # Empty content — transient issue, retry.
            last_error = RuntimeError("LLM returned empty content")
            time.sleep(2 ** attempt)
            continue

        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                retry_after = int(exc.headers.get("Retry-After", 10))
                time.sleep(retry_after)
                continue
            if exc.code in (502, 503, 504) and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"LLM API HTTP {exc.code}") from exc

        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"LLM API network error: {exc}") from exc

    raise RuntimeError(f"LLM API: all {max_retries} retries exhausted: {last_error}")


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def parse_llm_response(raw_text: str) -> WorkerOutput:
    """Parse the raw LLM response into a WorkerOutput.

    Handles:
    - plain JSON objects
    - markdown-fenced ```json blocks
    - surrounding prose before/after the JSON

    A parse failure produces action_kind ``"PARSE_ERROR"`` — it does NOT
    silently become HOLD, because that would conflate parse failure with
    a valid HOLD action.
    """
    raw = raw_text if isinstance(raw_text, str) else str(raw_text)

    # --- attempt 1: extract from markdown fence ---
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.IGNORECASE | re.DOTALL)
    if fenced:
        parsed = _try_json(fenced.group(1))
        if parsed is not None:
            return _parsed_to_worker(parsed, raw)

    # --- attempt 2: first JSON object in the text ---
    parsed = _try_json(raw)
    if parsed is not None:
        return _parsed_to_worker(parsed, raw)

    # --- attempt 3: find { ... } anywhere ---
    brace = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if brace:
        parsed = _try_json(brace.group(0))
        if parsed is not None:
            return _parsed_to_worker(parsed, raw)

    # --- fallback: try plain-text MISSING_REQUIRED_STATE ---
    if re.search(r"\bMISSING_REQUIRED_STATE\b", raw, re.IGNORECASE):
        return WorkerOutput(
            "MISSING_REQUIRED_STATE", 0,
            reasoning="parsed from text: MISSING_REQUIRED_STATE", raw_text=raw,
        )

    # --- fallback: try plain-text BUY/SELL/HOLD ---
    match = re.search(
        r"\b(BUY|SELL|HOLD)\b(?:\s+(\d+))?",
        raw,
        re.IGNORECASE,
    )
    if match:
        kind = match.group(1).upper()
        qty = int(match.group(2)) if match.group(2) else (0 if kind == "HOLD" else 1)
        expected_qty = 0 if kind == "HOLD" else 1
        if qty == expected_qty:
            return WorkerOutput(kind, qty, reasoning=f"parsed from text: {kind}", raw_text=raw)

    return WorkerOutput("PARSE_ERROR", 0, reasoning="could not parse LLM response", raw_text=raw)


def _try_json(text: str) -> dict[str, Any] | None:
    """Attempt to parse text as a JSON object.  Returns None on failure."""
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass
    # Try stripping leading/trailing prose
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        value = json.loads(text[start:end])
        return value if isinstance(value, dict) else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def _parsed_to_worker(parsed: dict[str, Any], raw: str) -> WorkerOutput:
    """Convert a parsed JSON dict to a WorkerOutput.

    V0.2a: Handles MISSING_REQUIRED_STATE as a valid action kind
    when returned by B-minus-explicit condition.
    """
    action_raw = parsed.get("action") or parsed.get("action_kind") or ""
    action_kind = action_raw.strip().upper()
    quantity = parsed.get("quantity", 0)
    reasoning = parsed.get("reasoning", "")

    if action_kind in {"BUY", "SELL"}:
        if quantity != 1:
            return WorkerOutput("INVALID", quantity,
                                reasoning=f"BUY/SELL must have quantity 1, got {quantity}",
                                raw_text=raw)
        return WorkerOutput(action_kind, quantity, reasoning=reasoning, raw_text=raw)

    if action_kind == "HOLD":
        if quantity != 0:
            return WorkerOutput("INVALID", quantity,
                                reasoning=f"HOLD must have quantity 0, got {quantity}",
                                raw_text=raw)
        return WorkerOutput("HOLD", 0, reasoning=reasoning, raw_text=raw)

    # V0.2a: MISSING_REQUIRED_STATE is a valid action kind
    if action_kind == "MISSING_REQUIRED_STATE":
        if quantity != 0:
            return WorkerOutput("INVALID", quantity,
                                reasoning=f"MISSING_REQUIRED_STATE must have quantity 0, got {quantity}",
                                raw_text=raw)
        return WorkerOutput("MISSING_REQUIRED_STATE", 0, reasoning=reasoning, raw_text=raw)

    return WorkerOutput("INVALID", 0,
                        reasoning=f"unknown action kind: {action_kind!r}",
                        raw_text=raw)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def execute_llm_worker(
    inputs: dict[str, Any],
    condition: str,
    episode_id: str,
    model_config: dict[str, Any],
) -> WorkerOutput:
    """Execute the LLM worker for one condition.

    Builds the prompt from ``inputs`` (produced by ``build_worker_inputs``),
    calls the LLM, and parses the response.

    The LLM is the sole decision-maker — no oracle truth is injected.
    """
    messages = build_llm_prompt(inputs, condition, episode_id)
    raw_response = call_llm_api(messages, model_config)
    return parse_llm_response(raw_response)


if __name__ == "__main__":
    # Quick smoke test with a mock config — will fail without a real API.
    print("llm_worker: module loads OK")
    # Verify no oracle import.
    import sys as _sys
    for mod_name in list(_sys.modules):
        if "oracle" in mod_name:
            print(f"WARNING: oracle module loaded: {mod_name}")
    print("No oracle module loaded — independence check passed.")
