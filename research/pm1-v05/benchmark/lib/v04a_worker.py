"""
Workers for PM1 Trading Benchmark v0.4a sequential handoffs.

Two worker implementations:

1. ``DeterministicHandoffWorker`` — offline simulation worker used by the
   test suite. Implements the trading policy INLINE (its own copy of the
   rule). It MUST NOT import ``lib.oracle`` — the oracle stays independent.

2. ``LLMHandoffWorker`` — the real experiment worker. Builds a fresh prompt
   from ONLY the PM-1/direct state representation + the task specification,
   calls the LLM once, and parses the action + next position. Every hop
   constructs a brand-new messages array: no conversation history, no
   previous reasoning, no chain ID, no hop number, no expected action.

The LLM contract for V0.4a: the worker must emit the action AND the next
state it produces:
    {"action": "BUY"|"SELL"|"HOLD", "quantity": 0|1,
     "next_position_qty": <int>, "reasoning": "..."}

Token accounting: ``call_llm_api_with_usage`` returns raw content plus the
``usage`` block from the API so the harness can record input/output tokens.
"""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from lib.v04a_state import State, encode_direct_state, encode_pm1_state

__all__ = [
    "HandoffOutput",
    "DeterministicHandoffWorker",
    "ScriptedHandoffWorker",
    "LLMHandoffWorker",
    "build_handoff_prompt",
    "parse_handoff_output",
    "call_llm_api_with_usage",
]

_TASK_SPEC = (
    "Policy: set position_qty equal to target_signal. Use BUY 1 when "
    "position_qty is below target_signal, SELL 1 when position_qty is "
    "above target_signal, and HOLD when they are equal."
)

_SYSTEM_PROMPT = (
    "You are a trading algorithm operating a single decision step in a long chain. "
    "You receive the current state and the immutable task specification. "
    "Decide the single action the policy requires and the resulting position.\n\n"
    "Output ONLY valid JSON with exactly these keys:\n"
    '  {"action": "BUY" | "SELL" | "HOLD", "quantity": <int>, '
    '"next_position_qty": <int>, "reasoning": "<brief explanation>"}\n\n'
    "Rules:\n"
    "- BUY and SELL always have quantity 1.\n"
    "- HOLD always has quantity 0.\n"
    "- next_position_qty is the position AFTER applying this action "
    "(BUY: +1, SELL: -1, HOLD: unchanged).\n"
    "- Do NOT include any text outside the JSON object."
)


@dataclass(frozen=True)
class HandoffOutput:
    """Structured output from one handoff worker step."""

    action_kind: str
    quantity: int
    next_position_qty: int | None
    reasoning: str = ""
    raw_text: str = ""
    parse_error: bool = False


class DeterministicHandoffWorker:
    """Offline worker that implements the policy inline (no oracle import)."""

    def __init__(self) -> None:
        self.calls = 0

    def _policy(self, position: int, target: int) -> tuple[str, int]:
        """Inline copy of the policy rule — independent of lib.oracle."""
        if position < target:
            return "BUY", 1
        if position > target:
            return "SELL", 1
        return "HOLD", 0

    def run(self, state: State, state_kind: str = "pm1") -> HandoffOutput:
        del state_kind  # representation does not affect the policy result
        self.calls += 1
        action, qty = self._policy(state.position_qty, state.target_signal)
        delta = 1 if action == "BUY" else (-1 if action == "SELL" else 0)
        return HandoffOutput(
            action_kind=action,
            quantity=qty,
            next_position_qty=state.position_qty + delta,
            reasoning=f"inline policy: pos={state.position_qty} target={state.target_signal}",
        )


class ScriptedHandoffWorker:
    """Worker that fails at scripted hops (used to exercise the taxonomy).

    At fail-hops the worker returns the scripted wrong output; elsewhere it
    behaves like the deterministic worker. ``fail_hops`` keys are 1-based
    call numbers (call N corresponds to hop N within a single chain run).
    """

    def __init__(self, fail_hops: dict[int, HandoffOutput] | None = None) -> None:
        self.fail_hops = fail_hops or {}
        self.calls = 0
        self._inner = DeterministicHandoffWorker()

    def run(self, state: State, state_kind: str = "pm1") -> HandoffOutput:
        self.calls += 1
        if self.calls in self.fail_hops:
            return self.fail_hops[self.calls]
        return self._inner.run(state, state_kind=state_kind)


# ---------------------------------------------------------------------------
# Prompt construction (fresh context per hop)
# ---------------------------------------------------------------------------


def build_handoff_prompt(
    state_repr: str,
    task_spec: str = _TASK_SPEC,
    state_kind: str = "pm1",
) -> list[dict[str, str]]:
    """Build a fresh chat messages array for one handoff step.

    The only content is the state representation (PM-1 packet text or plain
    text) plus the immutable task specification. No chain ID, hop number,
    seed, expected action, oracle output, or condition name appears.
    """
    if state_kind == "direct":
        block = "Current state (plain text):\n" + state_repr
    else:
        block = "Current PM-1 state packet:\n" + state_repr
    user_content = f"{task_spec}\n\n{block}"
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def parse_handoff_output(raw_text: str) -> HandoffOutput:
    """Parse the raw LLM response into a HandoffOutput.

    Accepts plain JSON, fenced JSON, or JSON embedded in prose.
    A parse failure yields ``parse_error=True`` with action PARSE_ERROR —
    it never silently becomes HOLD.
    """
    raw = raw_text if isinstance(raw_text, str) else str(raw_text)
    parsed = _try_json(raw)
    if parsed is None:
        return HandoffOutput("PARSE_ERROR", 0, None, raw_text=raw, parse_error=True)

    action_raw = parsed.get("action") or ""
    action = action_raw.strip().upper()
    quantity = parsed.get("quantity", 0)
    next_pos = parsed.get("next_position_qty")
    reasoning = parsed.get("reasoning", "")

    if action not in {"BUY", "SELL", "HOLD"}:
        return HandoffOutput("PARSE_ERROR", 0, None,
                             reasoning=f"unknown action {action!r}", raw_text=raw, parse_error=True)
    expected_qty = 0 if action == "HOLD" else 1
    if quantity != expected_qty:
        return HandoffOutput("PARSE_ERROR", 0, None,
                             reasoning=f"{action} must have quantity {expected_qty}", raw_text=raw, parse_error=True)
    if next_pos is None:
        return HandoffOutput("PARSE_ERROR", 0, None,
                             reasoning="next_position_qty missing", raw_text=raw, parse_error=True)
    try:
        next_pos = int(next_pos)
    except (TypeError, ValueError):
        return HandoffOutput("PARSE_ERROR", 0, None,
                             reasoning=f"invalid next_position_qty {next_pos!r}", raw_text=raw, parse_error=True)
    return HandoffOutput(action, quantity, next_pos, reasoning=reasoning, raw_text=raw)


def _try_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        value = json.loads(text[start:end])
        return value if isinstance(value, dict) else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# LLM API call with usage accounting (stdlib only)
# ---------------------------------------------------------------------------


def call_llm_api_with_usage(
    messages: list[dict[str, str]],
    model_config: dict[str, Any],
) -> tuple[str, dict[str, int]]:
    """Call an OpenAI-compatible /chat/completions endpoint, returning
    (content, usage). ``usage`` contains prompt_tokens / completion_tokens
    when the provider reports them, else empty dict.
    """
    base_url = model_config["base_url"].rstrip("/")
    api_key = model_config["api_key"]
    model = model_config.get("model", "deepseek-v4-flash")
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
            usage = data.get("usage", {})
            usage = {k: int(v) for k, v in usage.items() if isinstance(v, (int, float))}
            if content:
                return content, usage
            last_error = RuntimeError("LLM returned empty content")
            time.sleep(2 ** attempt)
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


class LLMHandoffWorker:
    """Real experiment worker: one fresh LLM call per handoff."""

    def __init__(self, model_config: dict[str, Any]) -> None:
        self.model_config = model_config
        self.calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def run(self, state: State, state_kind: str = "pm1") -> HandoffOutput:
        self.calls += 1
        if state_kind == "direct":
            repr_text = encode_direct_state(state)
        else:
            repr_text = json.dumps(encode_pm1_state(state), sort_keys=True)
        messages = build_handoff_prompt(repr_text, state_kind=state_kind)
        content, usage = call_llm_api_with_usage(messages, self.model_config)
        # F2 fix: store the actual usage dict so run_chain() can record real
        # token numbers. Empty dict when the provider omits usage — the caller
        # records usage_available=False in that case.
        self.last_usage = usage or {}
        self.total_input_tokens += usage.get("prompt_tokens", 0)
        self.total_output_tokens += usage.get("completion_tokens", 0)
        return parse_handoff_output(content)
