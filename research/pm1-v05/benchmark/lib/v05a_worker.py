"""
V0.5 workers for the Context Scaling & Token Economics benchmark.

Two handoff strategies on the SAME deterministic task:

Condition P (PM-1 state handoff)
    worker -> PM-1 state (bounded) -> next worker

Condition C (conversational context handoff)
    worker -> accumulated conversation/history -> next worker

Both workers operate from a fresh context per hop. The LLM is never told
which condition it is in, nor the horizon, trial, scenario, seed, expected
action, oracle output, or any token measurement.

DeterministicV05Worker is the offline/simulation worker used by the test
suite: it decodes the received representation and applies the trading policy
inline. It MUST NOT import lib.oracle (oracle stays independent).

LLMV05Worker is the real experiment worker: one fresh API call per hop with
provider token-usage capture.
"""

from __future__ import annotations

import json
import re
from typing import Any

from lib.v04a_state import State, decode_direct_state, decode_pm1_state, encode_pm1_state
from lib.v04a_worker import (
    HandoffOutput,
    call_llm_api_with_usage,
    parse_handoff_output,
)

__all__ = [
    "TASK_SPEC",
    "SYSTEM_PROMPT",
    "build_state_block",
    "build_v05a_prompt",
    "DeterministicV05Worker",
    "LLMV05Worker",
]

# Identical task specification for BOTH conditions (fairness requirement).
TASK_SPEC = (
    "Policy: set position_qty equal to target_signal. Use BUY 1 when "
    "position_qty is below target_signal, SELL 1 when position_qty is "
    "above target_signal, and HOLD when they are equal."
)

# Neutral system prompt: identical for P and C. Does not name the condition.
SYSTEM_PROMPT = (
    "You are a trading algorithm performing one decision step. You receive "
    "the current task state and the immutable task specification. Decide the "
    "single action the policy requires and the resulting position.\n\n"
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

_CURRENT_LINE = "Current state:"


def pm1_packet_text(state: State) -> str:
    """Render the bounded PM-1 packet as prompt text (Condition P)."""
    return json.dumps(encode_pm1_state(state), sort_keys=True)


def transcript_entry(step: int, state: State, action: str, quantity: int, reasoning: str) -> str:
    """One chronological conversation entry (Condition C)."""
    return (
        f"step {step}: state(position_qty={state.position_qty}, "
        f"target_signal={state.target_signal}) -> action {action} "
        f"(quantity {quantity}) | {reasoning}"
    )


def current_state_line(state: State) -> str:
    """The continuation line a C worker reads to determine the next action."""
    return f"{_CURRENT_LINE} position_qty={state.position_qty}, target_signal={state.target_signal}"


def parse_current_state_line(text: str) -> State:
    """Extract the current State from a C-transcript current-state line."""
    if not isinstance(text, str):
        raise ValueError("current-state line must be text")
    m = re.search(rf"{re.escape(_CURRENT_LINE)}\s*position_qty=(-?\d+),\s*target_signal=(-?\d+)", text)
    if not m:
        raise ValueError("cannot parse current-state line")
    return State(position_qty=int(m.group(1)), target_signal=int(m.group(2)))


def build_state_block(condition: str, state: State, transcript: list[str] | None = None) -> str:
    """Build the worker-visible state block.

    Condition P -> bounded PM-1 packet.
    Condition C -> neutral chronological transcript + current-state line.
    The block never names the condition, horizon, trial, scenario, or seed.
    """
    if condition == "P":
        return pm1_packet_text(state)
    if condition == "C":
        if transcript is None:
            raise ValueError("transcript required for condition C")
        lines = list(transcript)
        lines.append(current_state_line(state))
        return "\n".join(lines)
    raise ValueError(f"unknown v0.5 condition: {condition!r}")


def build_v05a_prompt(state_block: str, task_spec: str = TASK_SPEC) -> list[dict[str, str]]:
    """Fresh chat messages for one hop. Identical framing for P and C."""
    user_content = f"{task_spec}\n\nCurrent task state:\n{state_block}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _inline_policy(position: int, target: int) -> tuple[str, int]:
    """Inline copy of the trading policy — independent of lib.oracle."""
    if position < target:
        return "BUY", 1
    if position > target:
        return "SELL", 1
    return "HOLD", 0


class DeterministicV05Worker:
    """Offline worker: decodes the received representation, applies the
    policy inline (no oracle import), emits action + next position."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_usage: dict[str, int] = {}

    def run(self, state_block: str, condition: str, task_spec: str = TASK_SPEC) -> HandoffOutput:
        """Decode the current state from the representation and act."""
        del task_spec
        self.calls += 1
        if condition == "P":
            state = decode_pm1_state(json.loads(state_block))
        elif condition == "C":
            state = parse_current_state_line(state_block)
        else:
            raise ValueError(f"unknown condition: {condition!r}")
        action, qty = _inline_policy(state.position_qty, state.target_signal)
        delta = 1 if action == "BUY" else (-1 if action == "SELL" else 0)
        self.last_usage = {}
        return HandoffOutput(
            action_kind=action,
            quantity=qty,
            next_position_qty=state.position_qty + delta,
            reasoning=f"inline policy: pos={state.position_qty} target={state.target_signal}",
        )


class LLMV05Worker:
    """Real experiment worker: one fresh LLM call per hop, usage captured."""

    def __init__(self, model_config: dict[str, Any]) -> None:
        self.model_config = model_config
        self.calls = 0
        self.last_usage: dict[str, int] = {}
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def run(self, state_block: str, condition: str, task_spec: str = TASK_SPEC) -> HandoffOutput:
        del condition  # never exposed to the prompt
        self.calls += 1
        messages = build_v05a_prompt(state_block, task_spec)
        content, usage = call_llm_api_with_usage(messages, self.model_config)
        self.last_usage = usage or {}
        self.total_input_tokens += usage.get("prompt_tokens", 0)
        self.total_output_tokens += usage.get("completion_tokens", 0)
        return parse_handoff_output(content)
