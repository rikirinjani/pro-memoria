# PM-1 Related Work Bibliography (verified)

Status: all entries verified against primary sources retrieved 2026-08-18.
No entry is fabricated. Works that could not be verified are listed at the end
as excluded. Practitioner material is marked as such and is not treated as
authoritative academic prior art.

---

## Verified references

### R1. MemGPT — hierarchical agent memory

- **Citation:** C. Packer, S. Wooders, K. Lin, V. Fang, S. G. Patil, I. Stoica, J. E. Gonzalez. *MemGPT: Towards LLMs as Operating Systems.* arXiv:2310.08560, 2023. https://arxiv.org/abs/2310.08560
- **Area:** agent memory; long-context management
- **What it does:** OS-inspired virtual context management: the model pages data between a finite context window ("main memory") and external storage ("disk") via self-directed function calls, giving the illusion of larger context.
- **Relationship to PM-1:** adjacent architecture — both address the finite-context problem for long-running agents. MemGPT is a *retrieval/eviction* design (page out, retrieve on demand).
- **Key difference:** MemGPT keeps the accumulated conversation and manages *where it lives* (in-context vs external, retrieved by the model). PM-1 does not retrieve history at all; it transmits a bounded continuation-state packet and the accumulated transcript does not cross the handoff boundary.
- **Threatens PM-1 novelty?** No. It is the closest architectural neighbor but operates on a different axis (memory placement vs transmission boundary).
- **Citation location:** Related Work — Agent memory; Discussion (contrast); MemGPT paging vs PM-1 skip.

### R2. Generative Agents — memory stream + retrieval

- **Citation:** J. S. Park, J. C. O'Brien, C. J. Cai, M. R. Morris, P. Liang, M. S. Bernstein. *Generative Agents: Interactive Simulacra of Human Behavior.* UIST 2023 / arXiv:2304.03442. https://arxiv.org/abs/2304.03442 ; https://dl.acm.org/doi/10.1145/3586183.3606763
- **Area:** agent memory; long-horizon agent behavior
- **What it does:** agents keep a comprehensive natural-language memory stream; a retrieval function surfaces relevant memories by recency/importance; reflections synthesize higher-level abstractions.
- **Relationship to PM-1:** adjacent architecture — persistent memory with retrieval, applied to open-world simulation.
- **Key difference:** stores and retrieves the full experience record in natural language; the memory is the agent's own persistent store within a continuing agent. PM-1 targets *handoff between fresh workers*, where history is deliberately not carried.
- **Threatens PM-1 novelty?** No.
- **Citation location:** Related Work — Agent memory; persistent agent memory.

### R3. Lost in the Middle — long-context use limitations

- **Citation:** N. F. Liu, K. Lin, J. Hewitt, A. Paranjape, M. Bevilacqua, F. Petroni, P. Liang. *Lost in the Middle: How Language Models Use Long Contexts.* TACL 12:157–173, 2024 (arXiv:2307.03172, 2023). https://aclanthology.org/2024.tacl-1.9/ ; https://arxiv.org/abs/2307.03172
- **Area:** context-window limitations; long-context management
- **What it does:** empirically shows LLM performance is U-shaped vs position of relevant information and degrades as context grows — long-context models do not robustly use all in-context information.
- **Relationship to PM-1:** motivating evidence for the context problem PM-1 addresses; supports the premise that retransmitting an ever-growing transcript is not free even when it fits.
- **Key difference:** it studies model behavior under long context; PM-1 proposes an architectural alternative that avoids accumulating long context at all.
- **Threatens PM-1 novelty?** No.
- **Citation location:** Introduction (motivation); Related Work — context-window limitations; Discussion.

### R4. RAG — retrieval-augmented generation

- **Citation:** P. Lewis, E. Perez, A. Piktus, F. Petroni, V. Karpukhin, N. Goyal, H. Küttler, M. Lewis, W. Yih, T. Rocktäschel, S. Riedel, D. Kiela. *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.* NeurIPS 2020 / arXiv:2005.11401. https://arxiv.org/abs/2005.11401
- **Area:** retrieval-based memory
- **What it does:** combines a parametric generator with a non-parametric dense vector index; retrieves relevant passages at generation time; hot-swappable knowledge.
- **Relationship to PM-1:** the canonical *retrieval* family that PM-1 explicitly does NOT compare against in V0.5; a possible future-work baseline.
- **Key difference:** retrieval injects *relevant external/historical content on demand*; PM-1 transmits a *canonical continuation state* and never retrieves prior conversation.
- **Threatens PM-1 novelty?** No.
- **Citation location:** Related Work — retrieval-based memory; Limitations (explicitly: no retrieval baseline); Future Work.

### R5. Blackboard architecture — shared structured state

- **Citation:** B. Hayes-Roth. *The Blackboard Architecture: A General Framework for Problem Solving?* HPP-83-20, Stanford, 1983; also *A Blackboard Architecture for Control.* Artificial Intelligence 26(3):251–321, 1985; and H. P. Nii, *Blackboard Systems.* Stanford CS-TR-86-1123, 1986. https://aitopics.org/download/aiclassics:344F987A ; https://stacks.stanford.edu/file/druid:bh000bv2768/bh000bv2768.pdf
- **Area:** shared-state / structured state transfer; blackboard architectures
- **What it does:** independent knowledge sources communicate solely through a shared structured blackboard holding problem-solving state; control selects which knowledge source acts next.
- **Relationship to PM-1:** conceptual precedent for shared structured state between independent components — the closest classical ancestor of "transmit the state, not the conversation."
- **Key difference:** blackboard systems share one global state space among concurrently active knowledge sources; PM-1 defines a *handoff boundary* for sequential fresh workers where history is intentionally not carried and state is transmitted as a bounded packet. PM-1 does not claim to invent shared structured state; it formalizes the selective transmission boundary for LLM handoffs.
- **Threatens PM-1 novelty?** Partially, at the level of "structured state sharing is old." The novelty claim must be the handoff-boundary formalization + measured token consequence, not the existence of structured state.
- **Citation location:** Related Work — shared state / blackboard; Discussion (explicit contrast, "PM-1 does not claim structured state is new").

### R6. LLMLingua — prompt compression

- **Citation:** H. Jiang, Q. Wu, C.-Y. Lin, Y. Yang, L. Qiu. *LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models.* EMNLP 2023 / arXiv:2310.05736. https://aclanthology.org/2023.emnlp-main.825/ ; https://arxiv.org/abs/2310.05736
- **Area:** context compaction / compression
- **What it does:** coarse-to-fine prompt compression (budget controller, token-level iterative compression, distribution alignment) achieving up to 20x compression with little loss.
- **Relationship to PM-1:** the clearest example of the *compression* family that PM-1 explicitly contrasts with "skip." Compression keeps the same information, represented more compactly; PM-1 does not transmit known/unnecessary information at all.
- **Key difference:** LLMLingua compresses a given prompt (same information, smaller representation, still grows with history); PM-1 changes what crosses the handoff boundary.
- **Threatens PM-1 novelty?** No — it sharpens the skip-vs-compress distinction.
- **Citation location:** Related Work — context compaction; Discussion (the compression comparator); Limitations (no compaction baseline tested).

### R7. AutoGen — multi-agent conversation framework

- **Citation:** Q. Wu, G. Bansal, J. Zhang, Y. Wu, B. Li, E. Zhu, L. Jiang, X. Zhang, S. Zhang, J. Liu, A. Awadallah, R. W. White, D. Burger, C. Wang. *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation Framework.* arXiv:2308.08155, 2023. https://arxiv.org/abs/2308.08155v2
- **Area:** multi-agent handoff / orchestration
- **What it does:** conversable agents with unified message interfaces and "conversation programming"; agents coordinate by passing conversation messages.
- **Relationship to PM-1:** adjacent — multi-agent communication where agents pass *messages/conversations* between each other.
- **Key difference:** AutoGen's inter-agent communication is conversational message passing (conversation-centric); PM-1's handoff transmits a bounded state packet, and the prior conversation is not forwarded. PM-1 is not an orchestration framework; it is a handoff-transmission layer.
- **Threatens PM-1 novelty?** No.
- **Citation location:** Related Work — multi-agent handoff; Future Work (heterogeneous-agent swarms).

### R8. StreamingDialogue — long-context compression for dialogue

- **Citation:** J. Li, Q. Tu, C. Mao, Z. Yu, J.-R. Wen, R. Yan. *StreamingDialogue: Prolonged Dialogue Learning via Long Context Compression with Minimal Losses.* NeurIPS 2024 / arXiv:2403.08312. https://proceedings.neurips.cc/paper_files/paper/2024/file/9c43057f39d49b8b5c989cc1aac70ab7-Paper-Conference.pdf
- **Area:** context compaction for conversation; long-context efficiency
- **What it does:** compresses long dialogue history into "conversational attention sinks" (EoU tokens) to reduce compute/memory while preserving dialogue consistency.
- **Relationship to PM-1:** compression-family work for conversational history — again the comparator class PM-1 contrasts with skip.
- **Key difference:** operates inside the attention mechanism (KV caching of sinks) and keeps history in compressed form; PM-1 operates at the handoff boundary and does not carry history.
- **Threatens PM-1 novelty?** No.
- **Citation location:** Related Work — context compaction; Discussion (compression comparator).

---

## Practitioner / adjacent (not academic prior art)

- **P. (HackerNoon, 2026).** *Debugging Multi-Agent Memory Loss in Long-Running Pipelines* [title per project notes; exact URL and author to be recorded if the article is cited]. Treated as practitioner evidence of the memory-loss/context-growth problem, NOT authoritative prior art. Do not cite it in the paper as academic work; may be referenced as an industry motivation only if a stable URL is captured and the note is marked non-academic.

## Excluded (not verifiable at retrieval time)

- ReMEMBER (arXiv:2608.09043, dated 2026) and CALMem (arXiv:2605.20724, dated 2026) appeared in search results but could not be verified against authoritative sources with confidence; excluded from the bibliography. If needed later, re-verify via arXiv abs pages before citation.

---

## Placement summary in the paper

| Work | Where it appears |
|---|---|
| Lost in the Middle | Introduction (motivation); Related Work §"Context-window limitations"; Discussion |
| MemGPT | Related Work §"Agent memory"; Discussion (paging vs skip) |
| Generative Agents | Related Work §"Agent memory"; Related Work §"Persistent agent memory" |
| RAG | Related Work §"Retrieval-based memory"; Limitations (no retrieval baseline); Future Work |
| Blackboard (Hayes-Roth) | Related Work §"Shared structured state"; Discussion (novelty boundary) |
| LLMLingua | Related Work §"Context compaction"; Discussion (skip vs compress); Limitations |
| AutoGen | Related Work §"Multi-agent handoff"; Future Work |
| StreamingDialogue | Related Work §"Context compaction" |

Remaining [CITATION NEEDED] slots (no verified source yet): formal agent-handoff taxonomies, stateful-agent-architecture surveys beyond the above, and any direct "transmitting state rather than conversation" empirical study — none found that closely pre-empts the PM-1 formulation.
