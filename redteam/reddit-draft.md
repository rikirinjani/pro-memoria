# Reddit Draft: Pro Memoria — 85–90% Agent State Token Savings, Zero Setup

## Post for r/LocalLLaMA

---

**Title:** Pro Memoria: cut your agent's state-tracking tokens 85–90% with zero setup — no tokenizer extensions, no config, no deps

**Body:**

If you're running multi-step agent loops (ReAct, function-calling, orchestrate-act-observe), you're burning thousands of tokens just re-serializing your agent's internal state every tick. Phase, confidence, tool calls, error count, flags — it adds up fast.

I wrote **Pro Memoria (PM-1)** — a protocol that encodes 8-bit agent state as plain ASCII `.` and `-` with differential emission (only transmit what changed).

**The numbers:**

- 146 real agent traces from production: **89.4% savings** (18,688 PM-1 chars vs 175,539 JSON bytes)
- AB-1 Crucible benchmark (7% change rate): **84.8% savings** vs steelman delta-JSON
- ~750 lines of pure Python, zero dependencies

**Why it works:**

`.` and `-` are single tokens in every major tokenizer (`cl100k_base`, `o200k_base`, `p50k_base`, `r50k_base` — verified). That means PM-1 works instantly with GPT-4, Claude, Gemini, any model — no tokenizer extension, no Unicode registration, no configuration. Just `pip install pro-memoria` and go.

AB-1 (Agent Braille, the inspiration) needs a tokenizer extension to make Unicode cells atomic. PM-1 trades some density (8 chars/byte vs 1 cell) for universal portability. The differential protocol makes that trade worthwhile: at low change rates (the common case for agent state), the per-byte cost is amortized across long stable runs.

**What you get:**

```
pip install pro-memoria
```

```python
from pro_memoria import DiffState

ds = DiffState()
ds.diff(b'\x00\x41\x00\x00\x00\x00\x00\x02')  # emit 8 chars
ds.diff(b'\x00\x42\x00\x00\x00\x00\x00\x02')  # emit 8 chars (1 byte changed)
```

Plus a CLI (`pm1-trace`) for recording agent traces and an audit dashboard:

```
pm1-trace audit --html report.html   # self-contained HTML with charts
python demo/react_integration.py --compare   # see JSON vs PM-1 side-by-side
```

**Why you might not want it:**

- High change rate (>50%) — PM-1's 8x overhead per byte hurts if almost everything changes each tick. Use Base64 or codebook.
- Multi-agent event logs (discrete unrelated events) — design target is single-agent evolving state.
- Ultra-dense encoding — AB-1 with a tokenizer extension beats PM-1 2:1. But it needs setup.

**GitHub:** https://github.com/rikirinjani/pro-memoria  
**License:** Apache-2.0

Happy to answer questions. Would love to see what other people's agent trace savings look like — the `pm1-trace audit` dashboard makes it easy to check.

---

## Alternative shorter title options:

1. "Pro Memoria — zero-setup agent state compression, 89% savings on real traces"
2. "I wrote a protocol that cuts agent state token overhead 85-90% with plain ASCII — no tokenizer extensions needed"
3. "PM-1: single-agent state telemetry in ~750 lines of Python, zero deps, 89% token savings"

## Cross-post options

- r/MachineLearning — shorter, more formal, focus on benchmark methodology
- r/LLMDevs — focus on implementation, code snippets, API
- r/Python — focus on the zero-dependency pure Python design
