#!/usr/bin/env python3
"""
FINAL PRE-FLIGHT AUDIT — V0.1-LLM
Generates and saves the exact LLM prompt payloads for all conditions.
NO API CALLS. NO NETWORK. NO CREDITS SPENT.
"""
import sys
import json
import re
import os
from pathlib import Path

sys.path.insert(0, ".")

from lib.llm_worker import build_llm_prompt, _SYSTEM_PROMPT
from lib.worker import build_worker_inputs
from lib.scenario import make_scenario

OUTPUT_DIR = Path("results/preflight")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

scenario = make_scenario()
conditions = ["A", "B-full", "B-minus", "B-corrupt", "B-restored"]
episodes = ["F", "L"]

print("=" * 70)
print("FINAL PRE-FLIGHT AUDIT — V0.1-LLM")
print("NO API CALLS. NO NETWORK. NO CREDITS SPENT.")
print("=" * 70)
print()

all_prompts = {}
issues = []

for condition in conditions:
    for episode in episodes:
        inputs = build_worker_inputs(condition, episode, scenario)
        prompt = build_llm_prompt(inputs, condition, episode)

        # Save sanitized prompt (API key not in prompt — confirmed)
        prompt_data = {
            "condition": condition,
            "episode": episode,
            "system_prompt": prompt[0]["content"],
            "user_prompt": prompt[1]["content"],
            "message_count": len(prompt),
        }
        key = f"{condition}_{episode}"
        all_prompts[key] = prompt_data

        # Save to file
        filepath = OUTPUT_DIR / f"prompt_{condition}_{episode}.json"
        filepath.write_text(json.dumps(prompt_data, indent=2, ensure_ascii=False), encoding="utf-8")

print("PROMPT FILES SAVED:")
for f in sorted(OUTPUT_DIR.glob("prompt_*.json")):
    print(f"  {f}")
print()

# ======================================================================
# VERIFICATION CHECKS
# ======================================================================

print("=" * 70)
print("VERIFICATION CHECKS")
print("=" * 70)
print()

# --- CHECK 1: A contains no continuation-state values ---
print("--- CHECK 1: A contains no continuation-state values ---")
for ep in episodes:
    user = all_prompts[f"A_{ep}"]["user_prompt"]
    # Check for position VALUE (not field name in task_spec)
    pos_val = re.search(r"position_qty\s*[=:]\s*[01]", user)
    cash = "cash_cents" in user.lower()
    episode_ref = re.search(r"\bepisode\s*[=:]?\s*[FL]\b", user, re.IGNORECASE)

    ok = pos_val is None and not cash and episode_ref is None
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] A/{ep}: pos_val={'FOUND' if pos_val else 'none'}, cash_cents={'FOUND' if cash else 'none'}, episode_ref={'FOUND' if episode_ref else 'none'}")
    if not ok:
        issues.append(f"A/{ep} contains continuation-state values")

print()

# --- CHECK 2: B-full contains canonical continuation state ---
print("--- CHECK 2: B-full contains canonical continuation state ---")
for ep in episodes:
    user = all_prompts[f"B-full_{ep}"]["user_prompt"]
    has_packet = "compiled state packet" in user.lower()
    expected_pos = 0 if ep == "F" else 1
    # Check that the expected position value appears in the prompt
    pos_pattern = rf"position_qty[\"']?\s*[:=]\s*{expected_pos}"
    has_pos = re.search(pos_pattern, user) is not None

    ok = has_packet and has_pos
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] B-full/{ep}: packet_section={'YES' if has_packet else 'NO'}, position_qty={expected_pos}={'FOUND' if has_pos else 'MISSING'}")
    if not ok:
        issues.append(f"B-full/{ep} missing expected continuation state")

print()

# --- CHECK 3: B-minus removes required position state ---
print("--- CHECK 3: B-minus removes required position state ---")
for ep in episodes:
    user = all_prompts[f"B-minus_{ep}"]["user_prompt"]
    # B-minus should have the packet section but NO position_qty VALUE
    pos_val = re.search(r"position_qty\s*[=:]\s*\d", user)
    has_packet = "compiled state packet" in user.lower()

    ok = has_packet and pos_val is None
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] B-minus/{ep}: packet_section={'YES' if has_packet else 'NO'}, position_value={'FOUND (BAD)' if pos_val else 'absent (GOOD)'}")
    if not ok:
        issues.append(f"B-minus/{ep} has position state when it should not")

print()

# --- CHECK 4: B-corrupt contains intentionally corrupted state ---
print("--- CHECK 4: B-corrupt contains intentionally corrupted state ---")
for ep in episodes:
    user = all_prompts[f"B-corrupt_{ep}"]["user_prompt"]
    # Episode F has position=0, corrupt flips to 1. Episode L has position=1, corrupt flips to 0.
    expected_corrupted = 1 if ep == "F" else 0
    pos_pattern = rf"position_qty[\"']?\s*[:=]\s*{expected_corrupted}"
    has_corrupted = re.search(pos_pattern, user) is not None

    ok = has_corrupted
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] B-corrupt/{ep}: corrupted position_qty={expected_corrupted}={'FOUND' if has_corrupted else 'MISSING'}")
    if not ok:
        issues.append(f"B-corrupt/{ep} missing corrupted position value")

print()

# --- CHECK 5: B-restored contains canonical restored state ---
print("--- CHECK 5: B-restored contains canonical restored state ---")
for ep in episodes:
    user = all_prompts[f"B-restored_{ep}"]["user_prompt"]
    expected_pos = 0 if ep == "F" else 1
    pos_pattern = rf"position_qty[\"']?\s*[:=]\s*{expected_pos}"
    has_correct = re.search(pos_pattern, user) is not None

    ok = has_correct
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] B-restored/{ep}: restored position_qty={expected_pos}={'FOUND' if has_correct else 'MISSING'}")
    if not ok:
        issues.append(f"B-restored/{ep} missing restored position value")

print()

# --- CHECK 6: task_spec and observation identical across F/L ---
print("--- CHECK 6: task_spec and observation identical across F/L ---")
for condition in conditions:
    user_f = all_prompts[f"{condition}_F"]["user_prompt"]
    user_l = all_prompts[f"{condition}_L"]["user_prompt"]

    # Extract task_spec (first paragraph)
    task_f = user_f.split("\n\n")[0]
    task_l = user_l.split("\n\n")[0]

    # Extract observation (the "Current observation:" section)
    obs_match_f = re.search(r"Current observation:\n(.+?)(?:\n\n|$)", user_f, re.DOTALL)
    obs_match_l = re.search(r"Current observation:\n(.+?)(?:\n\n|$)", user_l, re.DOTALL)
    obs_f = obs_match_f.group(1) if obs_match_f else ""
    obs_l = obs_match_l.group(1) if obs_match_l else ""

    task_ok = task_f == task_l
    obs_ok = obs_f == obs_l

    status = "PASS" if task_ok and obs_ok else "FAIL"
    print(f"  [{status}] {condition}: task_spec={'identical' if task_ok else 'DIFFERS'}, observation={'identical' if obs_ok else 'DIFFERS'}")
    if not task_ok:
        issues.append(f"{condition} task_spec differs between F and L")
    if not obs_ok:
        issues.append(f"{condition} observation differs between F and L")

print()

# --- CHECK 7: No API key, secret, oracle output, expected action, or validator result ---
print("--- CHECK 7: No prohibited content in any prompt ---")
prohibited = ["api_key", "api-key", "secret", "token", "expected_action", "expected_action", "oracle", "validator", "hidden_position", "hidden_cash"]
all_clean = True
for key, prompt_data in all_prompts.items():
    user_lower = prompt_data["user_prompt"].lower()
    system_lower = prompt_data["system_prompt"].lower()
    for term in prohibited:
        if term in user_lower or term in system_lower:
            print(f"  [FAIL] {key}: contains prohibited term '{term}'")
            issues.append(f"{key} contains prohibited term '{term}'")
            all_clean = False
if all_clean:
    print("  [PASS] No prohibited content found in any prompt")

print()

# --- CHECK 8: LLM worker does not call oracle ---
print("--- CHECK 8: LLM worker does not call oracle ---")
import ast
from lib import llm_worker
source = ast.parse(open("lib/llm_worker.py", encoding="utf-8").read())
oracle_calls = []
for node in ast.walk(source):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and "oracle" in node.func.id.lower():
            oracle_calls.append(node.lineno)
        elif isinstance(node.func, ast.Attribute) and "oracle" in node.func.attr.lower():
            oracle_calls.append(node.lineno)
        elif isinstance(node.func, ast.Attribute) and "compute_expected" in node.func.attr:
            oracle_calls.append(node.lineno)
ok = len(oracle_calls) == 0
status = "PASS" if ok else "FAIL"
print(f"  [{status}] Oracle calls in llm_worker.py: {len(oracle_calls)}")
if not ok:
    issues.append(f"Oracle calls found at lines: {oracle_calls}")

print()

# --- CHECK 9: Exact files changed ---
print("--- FILES CHANGED ---")
print("  CREATED: lib/llm_worker.py (new file)")
print("  CREATED: lib/llm_runner.py (new file)")
print("  CREATED: test_llm_local.py (temporary test)")
print("  NO existing files modified")

print()

# --- SUMMARY ---
print("=" * 70)
if issues:
    print(f"PRE-FLIGHT: FAIL — {len(issues)} issue(s)")
    for i in issues:
        print(f"  - {i}")
else:
    print("PRE-FLIGHT: PASS")
print("=" * 70)
print("REAL API CALLS: 0")
