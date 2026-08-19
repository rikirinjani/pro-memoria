#set document(
  title: "Pro Memoria: Skip-Based State Transmission for Long-Horizon Agent Handoffs",
  author: "Riki Rinjani, PharmD",
  date: none,
)
#set page(paper: "a4", margin: (x: 2.2cm, y: 2.2cm), numbering: "1 / 1")
#set text(size: 10.5pt, lang: "en")
#set par(justify: true, leading: 0.62em)
#show heading: set block(above: 1.1em, below: 0.5em)

#align(center)[
  #text(size: 16pt, weight: "bold")[Pro Memoria: Skip-Based State Transmission for Long-Horizon Agent Handoffs]
]

#align(center)[
  #text(size: 10.5pt)[Riki Rinjani, PharmD]
  #linebreak()
  #text(size: 9.5pt)[Hisfarma IAI (Himpunan Seminat Farmasi Komunitas Ikatan Apoteker Indonesia)]
  #linebreak()
  #text(size: 9.5pt)[sekretariat\@hisfarma.com]
  #linebreak()
  #text(size: 9pt)[ORCID: 0009-0002-9364-2637]
]

#v(0.8em)

#block(
  width: 100%,
  inset: (x: 0.8em, y: 0.6em),
  radius: 4pt,
  stroke: (left: 3pt + blue, top: 0.5pt + luma(200), right: 0.5pt + luma(200), bottom: 0.5pt + luma(200)),
)[
  *Abstract.* Sequential agent workflows that hand work between fresh workers face a growing
  transmission problem: if every worker receives the accumulated conversational
  history of its predecessors, transmitted context grows with each handoff, and
  cumulative token consumption grows faster than the task itself. This paper
  presents Pro Memoria (PM-1), a handoff architecture organized around a single
  principle: #emph[skip, don't compress]. Rather than retransmitting accumulated
  history in a smaller representation, PM-1 does not retransmit it at all; each
  worker receives a bounded continuation-state packet containing the state
  required to continue. The architecture is designed to be encoding-agnostic:
  the original implementation used Morse, and the benchmark reported here uses a
  PM-1-shaped JSON packet.

  We evaluate the architecture across 30,100 completed API-backed handoffs in two
  sequential experiments. A 100-hop state-survival experiment (4,000 calls,
  10 chains, 4 conditions) measured 100% state integrity, 100% digest continuity,
  and zero protocol-induced state drift. A token/context scaling experiment
  (26,100 calls) compared a bounded PM-1 state packet against an accumulating
  conversational transcript over horizons 10–250. The packet condition maintained
  bounded per-hop context of approximately 78–79 tokens and exhibited
  approximately linear cumulative token growth (linear fit R² = 0.999998), while
  the conversational condition exhibited strongly super-linear cumulative growth
  (quadratic fit R² = 0.999999) — a 90.43% cumulative-token reduction relative to
  the accumulating conversational condition at horizon 250. In the packet
  condition, 99.98% of hops produced successfully formatted worker responses and
  100% preserved state integrity and digest continuity; the three formatting
  failures produced no state divergence.

  These results support claims about sequential state survival and the
  transmission economics of skip-based handoff within this benchmark. They do not
  address semantic knowledge transmission, institutional memory, or cross-model
  generalization, which are out of scope and are the subject of future work.

  #v(0.3em)
  #text(size: 9pt)[*Keywords:* agent handoff; context management; state transmission; token economics; long-horizon agents]
]

#v(0.6em)

= 1. Introduction

Long-running agentic systems decompose tasks into steps, each executed by a
fresh worker, with results flowing to the next worker. A common implementation
passes the accumulated conversation — every prior state, action, and reasoning
trace — to each new worker. As the horizon grows, this accumulated context
occupies more of the model's context window, cumulative consumption grows
faster than the task, and the transmitted context eventually approaches the
window limit. Empirical evidence shows that language models do not robustly use
arbitrarily long contexts even when they fit [Liu et al., 2024], so an
accumulating transcript is not merely expensive — it may also degrade the
reliability of the information a worker actually needs. PM-1 addresses one
architectural mechanism that may contribute to long-horizon context pollution:
the unnecessary retransmission of conversational history across handoffs.

This paper examines an alternative design. Pro Memoria (PM-1) is a handoff
architecture whose organizing principle is *skip, don't compress*: the next
worker does not receive the accumulated history of how prior workers arrived at
the current situation; it receives a bounded packet containing the state
required to continue. The distinction from compression is fundamental.
Compression transmits the same accumulated information in a smaller
representation; PM-1 changes what crosses the handoff boundary, so that known
or unnecessary history is not transmitted at all.

The research question is:

#quote(block: true)[
For a sequential task executed by fresh workers, how does the cumulative cost of
transmitted context grow with horizon under skip-based bounded state
transmission compared with accumulating conversational retransmission?
]

We evaluate this with two sequential experiments. V0.4a asks whether PM-1 state
can survive repeated sequential handoffs. V0.5 asks what transmission and
context cost is incurred by repeatedly handing off state while avoiding
accumulated conversational history. Together they provide 30,100 completed
API-backed handoffs.

*Contributions.*

1. *An architectural principle.* Skip-based state transmission decouples
   per-handoff transmission cost from accumulated history length.
2. *A protocol definition.* PM-1 specifies a bounded continuation-state packet
   (`sections → records → payload`), a fresh-worker handoff boundary, and
   digest-continuity integrity semantics.
3. *An empirical evaluation.* Two sequential experiments measure state survival
   over 100 handoffs and the cumulative token/context consequences of
   skip-based handoff over horizons 10–250.

We do not claim that PM-1 invented state handoff, structured state, or agent
memory — structured state sharing has long precedent in blackboard
architectures [Hayes-Roth, 1985; Nii, 1986]. The claim is narrower: PM-1
formalizes the handoff boundary as a selective transmission boundary and
empirically evaluates bounded continuation-state transmission against
accumulating conversational history across repeated fresh-worker handoffs.

= 2. Problem Definition

Consider a sequential task of horizon *N* executed by fresh workers: at each
step *i*, a worker receives transmitted context, produces an action, and is
destroyed; the next worker receives new context for step *i+1*. The task's
*continuation state* is the minimal set of variables the worker needs to
determine the correct next action.

Two transmission strategies are compared:

- *Condition P (bounded state packet).* Each worker receives a bounded
  continuation-state packet — the semantic state plus minimal identifying
  fields — and an immutable task specification. Packet size is independent of
  *N*.
- *Condition C (accumulating conversation).* Each worker receives the
  chronological transcript of all prior (state → action) entries plus a
  current-state line, and the same immutable task specification. The transcript
  grows with every hop.

The measured quantities are per-hop transmitted context and cumulative
transmitted tokens as functions of *N*.

The problem is deliberately scoped to *state transmission*, not knowledge
transmission. The continuation state in this benchmark is a small deterministic
portfolio state; the task is a vehicle for measuring handoff economics, and the
paper makes no claim about trading.

*Design goals.* Three goals govern the design: (1) *boundedness* — per-handoff
transmission must not grow with horizon; (2) *continuation* — a fresh worker
receiving only the packet and the task specification must determine the correct
next action; (3) *integrity* — the continuation state must survive handoff
intact, with a verifiable digest. These goals are orthogonal to compression: a
compressed transcript still grows with history; a skip-based packet does not.

= 3. Pro Memoria Architecture

The architecture separates four concerns:

1. *Canonical state.* The continuation state the next worker needs, materialized
   as records in a `sections → records → payload` packet shape.
2. *Handoff boundary.* Each worker runs in a fresh session with no access to
   prior sessions, the state directory, hidden truth, or the oracle.
3. *Transmission.* The bounded packet plus the immutable task specification is
   the only task-relevant context the worker receives.
4. *Validation.* An independent oracle validates actions against hidden truth; a
   deterministic ledger applies transitions; digests verify state continuity.

== 3.1 Skip semantics

The core operation is *skipping*, not *shrinking*:

- Known or unnecessary history is not retransmitted.
- The receiving worker receives the state required to continue.
- The accumulated transcript is dropped at each handoff boundary, not compressed
  and forwarded.

Two clarifications position this correctly. First, *skip* is not merely
*choosing a smaller state representation*: selecting a compact state is
necessary but not sufficient. The mechanism claim is that accumulated
conversational history does not cross the handoff boundary at all, which the
P-vs-C comparison isolates — both conditions solve the same task, and only the
transmission of prior history differs. Second, structured state itself is not
novel (blackboard architectures transmit state rather than interaction history
[Hayes-Roth, 1985; Nii, 1986]); the contribution is the formalized selective
handoff boundary for fresh LLM workers and the measured transmission
consequences.

The economic consequence: because the packet size does not depend on history
length, cumulative transmission grows with the number of hops rather than with
the product of hops and accumulated history. This is the mechanism behind the
measured scaling separation in Section 6.

== 3.2 PM-1 packet model

A PM-1-shaped state packet is a JSON document of the form
`sections → records → payload`. In this benchmark the packet contains a single
`project_state` section whose payload carries the continuation state:
`position_qty`, `target_signal`, `cash_cents`, `instrument`, `price_cents`,
`logical_tick`, and tags. The state digest is computed over the semantic state
fields (`position_qty`, `target_signal`) so that digest continuity measures
continuation state rather than experiment identity.

== 3.3 Encoding

PM-1 is defined by what is transmitted and what is skipped, not by any
particular encoding. Morse is the original encoding implementation and part of
the architecture's provenance. V0.5 uses a PM-1-shaped JSON packet. The
successful substitution of JSON for the original Morse encoding demonstrates
that Morse is not required by the architecture; broader encoding agnosticism
remains to be evaluated.

== 3.4 Scope of the benchmark implementation

V0.5 exercises a PM-1-shaped payload subset rather than every feature of the
original implementation:

1. The packet is a payload-shaped subset; full envelope semantics were not
   exercised.
2. Selection was intentionally trivial: one `project_state` record per hop.
3. The benchmark transmitted a bounded full-state snapshot; field-level delta
   selection was not tested.
4. The packet used JSON rather than Morse.

These are scope boundaries, not defects; the paper does not claim V0.5 tested
intelligent memory selection.

= 4. Experimental Design

== 4.1 Task

The benchmark uses a deterministic synthetic portfolio/state task. It is not a
trading claim. It exists because it provides deterministic state, a
deterministic oracle, controlled transitions, measurable state divergence, and
repeatable long-horizon handoffs. The scientific object is the handoff
architecture.

== 4.2 Model and configuration

Single model (deepseek-v4-flash), temperature 0.0, maximum output tokens 2048,
identical between P and C. Workers run in fresh contexts; the condition,
horizon, scenario, and trial are hidden from the worker; there is no oracle
leakage, no expected-action leakage, and no token-count leakage. No
heterogeneous-model or cross-provider validation is claimed.

== 4.3 Token and context measurement

Provider-reported `usage` (prompt/completion tokens) is captured per hop. When
the provider omits usage, a deterministic `chars/4` estimate is used and
reported explicitly. Cumulative input/output/total tokens are tracked per hop
and per chain; token-completeness was verified at 26,100 / 26,100 records.
Transmitted context size per hop is recorded in characters (exact) and
estimated tokens (`chars/4`): PM-1 packet size per P hop, conversation history
size per C hop.

== 4.4 Horizons and scaling analysis

Horizons 10, 25, 50, 100, and 250. H500 and H1000 were registered but not
executed; they did not fail, and no results are extrapolated for them. All
executed horizons evaluate a prefix of the same master chain specification.
Linear and quadratic least-squares fits (pure-python normal equations) are fit
to cumulative tokens versus horizon. Growth is reported as measured
approximately-linear versus strongly super-linear over the observed horizons
H10–H250; the quadratic fit is a characterization of the measured data, not an
asymptotic proof.

== 4.5 Reliability metrics and acceptance criteria

Reliability metrics: action correctness, received-state correctness,
oracle-state correctness, state integrity (divergence == 0), digest continuity,
semantic drift, handoff survival, chain survival, parse errors, and
failure-taxonomy counts, per condition and horizon.

Acceptance criteria (registered before API calls): reliability equivalence
between P and C within ±5 pp at each horizon; P cumulative-context scaling
linear R² ≥ 0.95; C cumulative-context scaling super-linear (quadratic R² >
linear R²); PM-1 boundedness (P maximum transmitted tokens ≤ 2× from H10 to
H1000); C context growth (> 5× from H10 to H1000); zero metadata leakage; zero
oracle leakage; deterministic reproducibility; token completeness.

= 5. Results

== 5.1 V0.4a — state survival across 100 sequential handoffs

*Question: can PM-1 state survive repeated sequential handoffs?*

Design: 4,000 API calls; 100-hop sequential handoffs; 10 chains × 100 hops × 4
conditions (H-full, H-direct, H-corrupt, H-recover).

#figure(
  table(
    columns: 2,
    [*Metric*], [*Result*],
    [100-hop completion], [100% in every condition],
    [State integrity (divergence == 0)], [100% in every condition],
    [Digest continuity], [100% (H-full, H-direct)],
    [Protocol-induced state drift], [0],
    [H-full handoff success], [999 / 1,000],
    [H-full failure], [1 model PARSE_ERROR (chain-05, hop 24), no state consequence],
  ),
  caption: [V0.4a results summary (4,000 calls, 10 chains, 100 hops, 4 conditions).],
)

The single H-full failure was a worker output-format failure, not a protocol
failure; it moved chain survival to 9/10 (−10 pp) but produced no state
divergence. H-corrupt also recorded one model PARSE_ERROR (chain-08, hop 40) at
a non-corruption hop with no state consequence; H-direct and H-recover
completed 1,000/1,000.

== 5.2 V0.5 — token/context scaling over horizons 10–250

*Question: what is the transmission/context cost of repeatedly handing off
state while avoiding accumulated conversational history?*

Design: 26,100 completed API calls; horizons 10, 25, 50, 100, 250; 10
scenarios × 3 trials × 2 conditions (P, C). Same deterministic task, same
model, same configuration; the only independent variable is how state/history
is transmitted.

Dataset reconciliation: expected and actual persisted hop records 26,100 /
26,100; checkpoint match true; duplicate call IDs 0; missing call IDs 0; token
usage records 26,100 / 26,100; recomputed actual-digest mismatches 0;
expected-vs-actual digest mismatches 2 (both in C at H100 — see Section 5.5).

== 5.3 Cumulative token totals

#figure(
  table(
    columns: 5,
    [*Horizon*], [*P total (tok)*], [*C total (tok)*], [*C/P*], [*Reduction 1−P/C*],
    [10], [149,590], [168,676], [1.128], [11.32%],
    [25], [370,703], [633,117], [1.708], [41.45%],
    [50], [737,870], [1,957,375], [2.653], [62.30%],
    [100], [1,474,888], [6,819,750], [4.624], [78.37%],
    [250], [3,672,305], [38,366,105], [10.447], [90.43%],
  ),
  caption: [Cumulative token totals by horizon and condition.],
)

At H250, the PM-1 packet condition consumed 3,672,305 cumulative tokens versus
38,366,105 for the conversational condition: a *90.43% cumulative-token
reduction relative to the accumulating conversational condition at H250*. This
is a difference between two handoff strategies within this benchmark; it is not
a compression ratio applied to history, and it is not memory compression.

#figure(
  image("figures/fig1_cumulative_tokens.png", width: 78%),
  caption: [Cumulative token consumption over horizons H10–H250, with fitted curves.],
)

== 5.4 Per-hop transmitted context

#figure(
  table(
    columns: 8,
    [*Horizon*], [*Cond*], [*Min tok*], [*Max tok*], [*Mean tok*], [*Min chars*], [*Max chars*], [*Mean chars*],
    [10], [P], [78], [79], [78.67], [314], [319], [317.04],
    [10], [C], [11], [356], [161.81], [46], [1,427], [648.78],
    [25], [P], [78], [79], [78.63], [314], [319], [316.84],
    [25], [C], [11], [881], [396.61], [46], [3,526], [1,588.05],
    [50], [P], [78], [79], [78.61], [314], [319], [316.77],
    [50], [C], [11], [1,833], [788.28], [46], [7,332], [3,154.72],
    [100], [P], [78], [79], [78.61], [314], [319], [316.73],
    [100], [C], [11], [3,618], [1,609.30], [46], [14,474], [6,438.74],
    [250], [P], [78], [79], [78.60], [314], [319], [316.71],
    [250], [C], [11], [8,864], [3,977.78], [46], [35,457], [15,912.62],
  ),
  caption: [Per-hop transmitted context by horizon and condition.],
)

P per-hop transmitted context remained bounded at approximately 78–79 tokens /
314–319 characters across all horizons. C grew continuously, reaching a maximum
observed per-hop transmitted context of approximately 8,864 tokens / 35,457
characters at H250. The provider genuinely consumed the growing C context:
cumulative C totals are computed from provider-reported prompt tokens, not from
the `chars/4` heuristic.

#figure(
  image("figures/fig2_per_hop_context.png", width: 78%),
  caption: [Per-hop transmitted context: P bounded, C growing.],
)

== 5.5 Scaling behavior

*P (packet condition).* Approximately linear cumulative growth over the
measured horizons:

- Linear fit: `y = 14676.770143x + 4192.197598`, R² = 0.999998
- Power-law exponent: 0.9946

*C (conversational condition).* Strongly super-linear cumulative growth:

- Quadratic fit: `y = 568.922736x² + 11268.721360x − 7709.001538`, R² = 0.999999
- Linear fit R²: 0.960105 (quadratic dominates)
- Power-law exponent: 1.6905

These are characterizations of measured growth over horizons 10–250. They are
not formal proofs of asymptotic O(N) versus O(N²).

#figure(
  image("figures/fig3_reduction.png", width: 78%),
  caption: [Cumulative-token reduction relative to the accumulating conversational condition by horizon.],
)

== 5.6 Reliability and state integrity

Two distinct properties are reported separately and must not be conflated:

- *Worker formatting success* — the fraction of worker outputs that parsed into
  the required structured JSON.
- *State integrity* — the fraction of hops in which the state after the hop
  equals the state the protocol requires (divergence == 0 and digest match).

A malformed worker response is a worker-output failure; state divergence is an
integrity failure. An output can fail to parse while state remains intact (a
failed parse is recorded as a non-action with no ledger transition, hence zero
divergence), and an output can parse correctly while state diverges (as
observed in C at H100).

*Aggregate across 26,100 calls:*

#figure(
  table(
    columns: 8,
    [*Cond*], [*Total*], [*PASS*], [*Parse err*], [*Action err*], [*State corr*], [*Divergence rate*], [*Digest continuity*], [*State integrity*],
    [P], [13,050], [99.98%], [0.02%], [0.00%], [0.00%], [0.00%], [100.00%], [100.00%],
    [C], [13,050], [99.98%], [0.01%], [0.01%], [0.01%], [0.02%], [99.98%], [99.98%],
  ),
  caption: [Aggregate reliability across all 26,100 calls.],
)

*H250 only:*

#figure(
  table(
    columns: 8,
    [*Cond*], [*Total*], [*PASS*], [*Parse err*], [*Action err*], [*State corr*], [*Divergence rate*], [*Digest continuity*], [*State integrity*],
    [P], [7,500], [99.97%], [0.03%], [0.00%], [0.00%], [0.00%], [100.00%], [100.00%],
    [C], [7,500], [99.99%], [0.01%], [0.00%], [0.00%], [0.00%], [100.00%], [100.00%],
  ),
  caption: [Reliability at H250 only (7,500 P + 7,500 C calls).],
)

*Precise statement for the packet condition.* PM-1 maintained 100% state
integrity and digest continuity across all 13,050 P hops, while 99.98% produced
successfully formatted worker responses; the three PARSE_ERROR events produced
no state divergence.

== 5.7 Failure taxonomy

Five non-PASS records across the full 26,100-call dataset:

#figure(
  table(
    columns: 7,
    [*Horizon*], [*Scenario*], [*Trial*], [*Cond*], [*Hop*], [*Type*], [*Divergence*],
    [100], [8], [2], [C], [2], [ACTION_ERROR (worker action failure)], [−1],
    [100], [8], [2], [C], [3], [STATE_CORRUPTION (persistent state corruption)], [−1],
    [250], [3], [1], [C], [79], [PARSE_ERROR (worker output-format failure)], [0],
    [250], [3], [2], [P], [102], [PARSE_ERROR (worker output-format failure)], [0],
    [250], [9], [1], [P], [188], [PARSE_ERROR (worker output-format failure)], [0],
  ),
  caption: [All five non-PASS records across the 26,100-call dataset.],
)

The ACTION_ERROR and STATE_CORRUPTION occurred under C at H100 (scenario 8,
trial 2, hops 2–3) with divergence −1, corresponding to the two expected-vs-
actual digest mismatches in the dataset reconciliation. All three H250 parse
errors had zero state divergence; none propagated to later hops. The two
state-related failures occurred in C; none occurred in P. The distribution is
consistent with formatting failures being condition-independent (they occurred
in both P and C), while the only state failures occurred in the conversational
condition. No causal claim about failure prevention is made; the harness's role
is capture and classification.

= 6. Discussion

The results establish two things. First, PM-1 state survives long sequential
handoffs (V0.4a), and the packet condition maintains bounded per-hop context
with 100% state integrity and digest continuity (V0.5). Second, the
transmission economics of skip-based handoff separate sharply from those of
accumulating conversation within this benchmark: approximately linear versus
strongly super-linear cumulative growth over the observed horizons, with a
90.43% cumulative-token reduction relative to the accumulating conversational
condition at H250.

The result is not simply "JSON is shorter than conversation." The architectural
interpretation is that PM-1 changes what information crosses the worker
boundary. Token savings and bounded context are consequences of that design,
not of a better encoding: the P packet is a compact JSON document, but the
boundedness comes from dropping history at the handoff boundary rather than
compressing and forwarding it. Compression inherits the input's growth; skip
semantics do not.

For long-running agent systems, the implication is that larger context windows
provide capacity, while PM-1 reduces unnecessary occupation of that capacity.
The benchmark does not measure needle-in-a-haystack accuracy, retrieval
quality, or long-context comprehension; those are future experiments. Within
this benchmark, the results support the hypothesis that skip-based bounded
transmission changes the long-horizon cost structure of handoffs.

The reliability distinction is central. Worker formatting success (99.98% in P)
and state integrity (100% in P) are different properties; a formatting failure
left state intact, while the only state failures in the dataset occurred in the
conversational condition. The results are consistent with protocol integrity
being independent of individual worker output quality, but they do not support
a claim that PM-1 prevents model failures.

= 7. Related Work

== 7.1 Agent memory and persistent state

Memory-augmented LLM agents manage the gap between finite context windows and
long-running interaction. MemGPT treats the context window as "main memory"
and external storage as "disk," with the model paging data between them via
self-directed function calls [Packer et al., 2023]. Generative agents maintain
a persistent natural-language memory stream, retrieving relevant memories and
synthesizing reflections over long-horizon simulation [Park et al., 2023].
These systems answer a common question: *where should old information live?*
PM-1 asks a different question: *what information actually needs to cross the
handoff boundary?*

== 7.2 Retrieval-based memory

Retrieval-augmented generation combines parametric generation with a
non-parametric index, retrieving relevant content at generation time
[Lewis et al., 2020]. Retrieval injects relevant historical or external content
on demand. PM-1 does not retrieve prior conversation; it transmits canonical
continuation state. Retrieval-based memory is a potential future-work baseline
but was not tested in this benchmark.

== 7.3 Context compaction and compression

Prompt compression reduces a given prompt to a smaller representation while
preserving semantics [Jiang et al., 2023]. Long-context dialogue compression
achieves similar ends inside the attention mechanism, caching compacted
utterance state rather than full history [Li et al., 2024]. These methods
represent the *compression* family that PM-1 explicitly contrasts with *skip*:
compression keeps the same accumulated information in a smaller form, which
still grows with history; PM-1 does not transmit known or unnecessary history
at all. No compaction baseline was tested in this benchmark, and none is
claimed.

== 7.4 Multi-agent handoff and shared state

Multi-agent frameworks coordinate agents through conversational message
passing [Wu et al., 2023]. Blackboard architectures provide a shared structured
state space through which independent knowledge sources communicate
[Hayes-Roth, 1985; Nii, 1986] — the classical precedent for transmitting state
rather than interaction history. PM-1 builds on this precedent at the LLM
handoff layer: it does not claim that structured state is new; it formalizes a
selective transmission boundary for sequential fresh workers and measures the
token/context consequences.

== 7.5 Context-window limitations

Models do not use long contexts robustly: performance is U-shaped with respect
to the position of relevant information and degrades as context grows
[Liu et al., 2024]. This motivates the architectural alternative of not
accumulating long context at all.

[CITATION NEEDED] formal taxonomies of agent handoff and stateful-agent
architecture surveys beyond the works above; no verified source was available
at the time of writing, and none is fabricated.

= 8. Limitations

- *Synthetic, deterministic task.* The portfolio task is a vehicle for
  controlled measurement, not a trading claim.
- *Simple state representation.* Continuation state is a small integer vector;
  no heterogeneous state was tested.
- *One model, one provider.* deepseek-v4-flash via one endpoint; no cross-model
  or cross-provider validation.
- *Temperature 0.* Greedy decoding; stochastic-sampling behavior untested.
- *Accumulating conversational baseline.* C is a naive baseline; no compaction,
  summarization, or retrieval baseline was tested. The measured 90.43%
  reduction is specifically relative to the accumulating conversational
  condition.
- *No evolving institutional knowledge.* No decisions, taxonomy, or knowledge
  in the packet; knowledge transmission and institutional memory are untested.
- *No heterogeneous models or agents.* Cross-model interoperability and
  heterogeneous-agent swarms are untested.
- *Finite measured horizon.* H10–H250; H500 and H1000 were registered but not
  executed; no extrapolation.
- *Payload-shaped subset.* Full envelope semantics, field-level delta
  selection, and intelligent selection were not exercised.
- *Encoding.* Substitution was tested with exactly one alternative (JSON);
  broader encoding agnosticism is not experimentally demonstrated.
- *Attention behavior.* The benchmark measures transmission/context economics,
  not model attention or long-context comprehension.

The strongest remaining reviewer objection is: *"C is a strawman; practical
systems may use compaction, summarization, retrieval, or external memory."*
This is valid and disclosed. The paper demonstrates the advantage of skip-based
bounded transmission over the accumulating-transcript condition tested; it does
not demonstrate superiority over all practical context-management techniques.
A stronger full-venue submission should add those baselines and ideally a
second model.

= 9. Future Work

== 9.1 The next experiment: evolving institutional truth

The next experimental phase addresses the "integer relay race" criticism
directly. Its question:

#quote(block: true)[
Can a bounded handoff packet preserve the CURRENT institutional truth when
knowledge changes over time?
]

The phase must add, relative to V0.5: stable decision IDs; decision
supersession; effective ticks; active knowledge selection (the packet carries
the currently-active set, not merely the most recent records); taxonomy
evolution; detector and validation logic evolution; and fresh workers applying
the current institutional truth. Heterogeneous models should be introduced in a
later phase, not retroactively claimed. This is a new experiment; it must not
be presented as a reinterpretation of V0.5, and the V0.5 paper does not claim
to have answered it.

== 9.2 Research program: the skip taxonomy

A broader research direction organizes skip behavior into categories. These are
architectural hypotheses for future work; V0.5 did not validate them.

- *Invariant skip.* Fixed content (e.g., a national anthem) that the receiving
  worker already possesses does not need retransmission. Known + invariant →
  skip.
- *Semantic / bounded skip.* Content is variable but the task has an allocated
  envelope (e.g., a 30-minute keynote); variable content does not imply
  unlimited budget. This maps naturally to token budgets: instruction budget,
  evidence budget, reasoning budget, handoff budget, total budget.
- *Process / temporal skip.* A long-running task does not require the agent to
  carry its entire execution history as active context: work, work, work,
  meaningful state change, checkpoint, continue. The agent preserves what the
  work resulted in, not every transient step.

The broader architectural principle under investigation is: *SKIP what is
invariant, BOUND what is variable, PERSIST what is durable, RETRIEVE what is
needed.* None of this is claimed as a V0.5 result.

== 9.3 PM-Adapter as future architecture

PM-Adapter is documented separately as a software artifact and technical note.
Its potential future architectural role is to adapt heterogeneous domain state
into what PM-1 needs: heterogeneous domain state → PM-Adapter (selection /
projection / prioritization / budget) → PM-1 → handoff → fresh worker. The
corresponding state hierarchy is *S_total* (everything the system knows),
*S_active* (currently relevant state), and *S_handoff* (what this particular
worker needs), with the hypothesis that *S_handoff* ≪ *S_active* ≪ *S_total*
when the domain permits it. This is future architecture, not a V0.5 result.
PM-Adapter was not the experimental variable in V0.5 and is not the basis of
the V0.5 scientific claim.

= 10.5 Code and Data Availability

The benchmark implementation, experiment configuration, analysis tooling, and
released experimental artifacts are publicly available at
#link("https://github.com/rikirinjani/pro-memoria") (release v0.5.0). The raw
experimental records and archival release are available through Zenodo:
#link("https://doi.org/10.5281/zenodo.22005884").

The released artifact contains: the benchmark harness and offline test suite;
the V0.5 experiment configuration and status documents (26,100 executed calls
across horizons H10, H25, H50, H100, H250; H500 and H1000 registered but NOT
executed); raw hop records and checkpoint with a checksum manifest; and the
consolidation report. The archive supports offline reproduction and analysis
of the reported results. API-backed experimental reproduction requires
provider credentials and paid calls; it does not require executing H500 or
H1000. The complete 116,100-call registered matrix was not executed.

= 10. Conclusion

Pro Memoria is a handoff architecture, not a compression codec. Its principle
is *skip, don't compress*: known or unnecessary history is not retransmitted,
and the receiving worker receives the state required to continue. Across
30,100 completed API-backed handoffs, the architecture maintained 100% state
integrity and digest continuity in the packet condition, kept per-hop context
bounded at approximately 78–79 tokens, and exhibited approximately linear
cumulative token growth while the accumulating-conversation condition grew
strongly super-linearly — a 90.43% cumulative-token reduction relative to that
condition at H250.

PM-1 demonstrated that repeated fresh-worker handoffs can preserve state
integrity while transmitting a bounded continuation packet, and that, in the
tested benchmark, this produced increasingly large token savings relative to
accumulating conversational history. The architecture is designed to be
encoding-agnostic; Morse is the original encoding implementation, and this
benchmark operated with a PM-1-shaped JSON packet without changing the
architecture or its results.

The results do not show that PM-1 solves agent memory or eliminates context
limits; they motivate the next investigation into selective, budgeted,
heterogeneous state handoff, and specifically into whether a bounded packet can
preserve current institutional truth as knowledge changes over time.

= 11. References

#set text(size: 9pt)

1. N. F. Liu, K. Lin, J. Hewitt, A. Paranjape, M. Bevilacqua, F. Petroni,
   P. Liang. *Lost in the Middle: How Language Models Use Long Contexts.*
   Transactions of the Association for Computational Linguistics 12:157–173,
   2024. arXiv:2307.03172.
2. C. Packer, S. Wooders, K. Lin, V. Fang, S. G. Patil, I. Stoica,
   J. E. Gonzalez. *MemGPT: Towards LLMs as Operating Systems.*
   arXiv:2310.08560, 2023.
3. J. S. Park, J. C. O'Brien, C. J. Cai, M. R. Morris, P. Liang,
   M. S. Bernstein. *Generative Agents: Interactive Simulacra of Human
   Behavior.* UIST 2023. arXiv:2304.03442.
4. P. Lewis, E. Perez, A. Piktus, F. Petroni, V. Karpukhin, N. Goyal,
   H. Küttler, M. Lewis, W. Yih, T. Rocktäschel, S. Riedel, D. Kiela.
   *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.*
   NeurIPS 2020. arXiv:2005.11401.
5. B. Hayes-Roth. *A Blackboard Architecture for Control.* Artificial
   Intelligence 26(3):251–321, 1985.
6. H. P. Nii. *Blackboard Systems.* Stanford CS-TR-86-1123, 1986.
7. H. Jiang, Q. Wu, C.-Y. Lin, Y. Yang, L. Qiu. *LLMLingua: Compressing Prompts
   for Accelerated Inference of Large Language Models.* EMNLP 2023.
   arXiv:2310.05736.
8. Q. Wu, G. Bansal, J. Zhang, Y. Wu, B. Li, E. Zhu, L. Jiang, X. Zhang,
   S. Zhang, J. Liu, A. Awadallah, R. W. White, D. Burger, C. Wang. *AutoGen:
   Enabling Next-Gen LLM Applications via Multi-Agent Conversation Framework.*
   arXiv:2308.08155, 2023.
9. J. Li, Q. Tu, C. Mao, Z. Yu, J.-R. Wen, R. Yan. *StreamingDialogue:
   Prolonged Dialogue Learning via Long Context Compression with Minimal
   Losses.* NeurIPS 2024. arXiv:2403.08312.

[CITATION NEEDED] for formal agent-handoff taxonomies and stateful-agent
architecture surveys — not fabricated; to be added from verified sources.
