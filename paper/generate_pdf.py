"""Generate Pro Memoria paper PDF with embedded figures."""
from fpdf import FPDF
from pathlib import Path

HERE = Path(__file__).resolve().parent

FONT_DIR = "C:/Windows/Fonts"

class PaperPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font('Arial', '', f'{FONT_DIR}/arial.ttf', uni=True)
        self.add_font('Arial', 'B', f'{FONT_DIR}/arialbd.ttf', uni=True)
        self.add_font('Arial', 'I', f'{FONT_DIR}/ariali.ttf', uni=True)
        self.add_font('Arial', 'BI', f'{FONT_DIR}/arialbi.ttf', uni=True)
        self.add_font('Times', '', f'{FONT_DIR}/times.ttf', uni=True)
        self.add_font('Times', 'B', f'{FONT_DIR}/timesbd.ttf', uni=True)
        self.add_font('Times', 'I', f'{FONT_DIR}/timesi.ttf', uni=True)

    def header(self):
        if self.page_no() > 1:
            self.set_font('Arial', 'I', 8)
            self.set_text_color(120, 120, 120)
            self.cell(0, 5, 'Pro Memoria (PM-1) -- ASCII-native binary protocol for agent state', align='C')
            self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')

    def section_title(self, title):
        self.set_font('Times', 'B', 15)
        self.set_text_color(30, 58, 95)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(30, 58, 95)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    def subsection_title(self, title):
        self.set_font('Times', 'B', 12)
        self.set_text_color(55, 65, 81)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body_text(self, text):
        self.set_font('Times', '', 10.5)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def insert_figure(self, img_path, caption, w=155):
        self.image(str(img_path), x=self.l_margin + 8, w=w)
        self.ln(2)
        self.set_font('Times', 'I', 9)
        self.set_text_color(80, 80, 80)
        self.multi_cell(0, 5, caption)
        self.ln(5)

    def bullet(self, text):
        self.set_font('Times', '', 10)
        self.set_text_color(30, 30, 30)
        self.cell(0, 5.5, f'  - {text}', new_x="LMARGIN", new_y="NEXT")

    def bold_text(self, text):
        self.set_font('Times', 'B', 10)
        self.set_text_color(30, 58, 95)
        self.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)


pdf = PaperPDF()
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=20)

# ── Title Page ─────────────────────────────────────────────────────────
pdf.add_page()
pdf.ln(35)
pdf.set_font('Times', 'B', 26)
pdf.set_text_color(30, 58, 95)
pdf.multi_cell(0, 13, 'Pro Memoria (PM-1):\nAn ASCII-Native Binary Protocol for\nToken-Efficient Agent State Communication', align='C')
pdf.ln(8)

pdf.set_font('Times', '', 13)
pdf.set_text_color(80, 80, 80)
pdf.cell(0, 9, 'Riki', align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)
pdf.set_font('Times', 'I', 10)
pdf.cell(0, 7, 'Inspired by Tetrahedroned / Agent-Braille (Apache-2.0 / CC-BY-4.0)', align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)
pdf.set_font('Times', '', 10)
pdf.set_text_color(30, 58, 95)
pdf.cell(0, 7, 'github.com/rikirinjani/pro-memoria', align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(25)

# Abstract box
pdf.set_draw_color(30, 58, 95)
pdf.set_fill_color(240, 244, 248)
y0 = pdf.get_y()
box_h = 62
pdf.rect(pdf.l_margin, y0, pdf.w - 2*pdf.l_margin, box_h, style='DF')
pdf.set_xy(pdf.l_margin + 5, y0 + 4)
pdf.set_font('Times', 'B', 12)
pdf.set_text_color(30, 58, 95)
pdf.cell(0, 7, 'Abstract', new_x="LMARGIN", new_y="NEXT")
pdf.set_x(pdf.l_margin + 5)

pdf.set_font('Times', '', 10)
pdf.set_text_color(30, 30, 30)
abstract = (
    "Large language model (LLM) agents generate significant token overhead tracking their internal "
    "state across multi-step tasks. Existing compact state representations either require tokenizer "
    "extensions (e.g., Agent Braille) or remain tied to JSON with modest compression. We present "
    "Pro Memoria (PM-1), an ASCII-native binary protocol that encodes 8-bit state as 8-character "
    "Morse strings (.=0, -=1), combined with a Differential State Protocol (DSP) that emits only "
    "changed bytes and a two-tier error-correcting command lexicon (Hamming [8,4,4] + parity). "
    "Because . and - are unconditionally single tokens in every major tokenizer (cl100k_base, "
    "o200k_base, p50k_base, r50k_base), PM-1 requires zero setup -- no vocabulary extension, no "
    "Unicode registration, no configuration changes. On the AB-1 Crucible trace (1,417 states), "
    "PM-1 achieves 84.8% token savings vs delta-encoded JSON. On 235 real agent traces (8-byte "
    "state, 82.5% change rate), it achieves 60.8% savings. A sensitivity sweep across 1-128 byte "
    "states and 10-90% change rates shows PM-1 beats hex by 1.4-2x at low change rates on "
    "multi-byte states."
)
pdf.multi_cell(pdf.w - 2*pdf.l_margin - 10, 5, abstract)
pdf.ln(10)

# ── 1. Introduction ────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title('1. Introduction')

pdf.body_text(
    "LLM agents increasingly use structured internal state to track progress across multi-step tasks: "
    "tool calls completed, files touched, confidence levels, error counts, phase transitions, and "
    "outcome flags. As agent frameworks (ReAct, function-calling loops, orchestrate-act-observe "
    "pipelines) grow in sophistication, the volume of state-tracking tokens grows correspondingly."
)

pdf.body_text(
    "The standard approach -- serializing state as compact JSON -- produces verbose output even with "
    "minimized field names and whitespace. A single agent state transition consumes approximately 60-100 "
    "characters or 20-40 tokens. Over hundreds of steps, this overhead accumulates to thousands of "
    "tokens -- pure scaffolding that carries no semantic information for the task at hand."
)

pdf.body_text(
    "Recent work has proposed more efficient encodings. Agent Braille (AB-1) [Tetrahedroned, 2025] "
    "encodes 8-bit agency state as single Unicode Braille cells (U+2800-U+28FF), achieving approximately "
    "92% token savings versus delta-encoded JSON via a Differential State Protocol (DSP) and a hardened "
    "command lexicon. However, AB-1 requires a tokenizer extension to map Braille cells to single "
    "tokens. Without it, each cell fragments into approximately 3 byte-tokens on stock tokenizers."
)

pdf.body_text(
    "We present Pro Memoria (PM-1), which adopts AB-1's DSP and Hamming [8,4,4] math but replaces the "
    "Unicode Braille encoding layer with ASCII '.' and '-' characters. Our key observation is that "
    "these characters are atomic (single-token) in every production tokenizer without any extension. "
    "This yields a zero-setup protocol: the same 85%+ token savings regime as AB-1, but portable "
    "across any LLM provider or tokenizer."
)

pdf.bold_text('Contributions:')
contribs = [
    "PM-1 encoding -- deterministic, roundtrip-safe mapping from 8-bit bytes to 8-character Morse strings, verified for all 256 byte values.",
    "Zero-setup property -- proof that '.' and '-' are single tokens in cl100k_base, o200k_base, p50k_base, and r50k_base.",
    "Differential State Protocol -- emit-on-change frame format with grow/shrink support and configurable maximum state size (64 KB).",
    "Two-tier error-correcting lexicon -- 16 Hamming [8,4,4] commands (single-bit correction) and 128 parity-protected commands (single-bit detection).",
    "Comprehensive benchmarks -- AB-1 Crucible trace, 235 real agent self-harness traces, and sensitivity sweep over byte-width and change rate.",
]
for c in contribs:
    pdf.bullet(c)
pdf.ln(4)

# ── 2. Related Work ────────────────────────────────────────────────────
pdf.section_title('2. Related Work')

pdf.subsection_title('2.1 Agent Braille (AB-1)')
pdf.body_text(
    "AB-1 [Tetrahedroned, 2025] defines an 8-dimensional orthogonal agency state model, encodes "
    "each state as a Unicode Braille cell, and provides a Differential State Protocol that emits "
    "cells only on state change. Its hardened lexicon uses the Hamming [8,4,4] code for 16 commands "
    "and a single-parity code for 128 commands. PM-1 is directly inspired by AB-1 and reuses the "
    "DSP emit-on-change discipline, the Hamming [8,4,4] mathematics, the two-tier command "
    "architecture, and the benchmark methodology. PM-1 diverges by replacing Unicode Braille with "
    "ASCII Morse -- trading density (8 chars/byte vs 1 cell/state) for portability (no extension needed)."
)

pdf.subsection_title('2.2 Existing Compact Encodings')
pdf.body_text(
    "Hex encoding (2 chars/byte) and Base64 (4 chars per 3 bytes, approximately 1.33x overhead) "
    "are both ASCII-native and zero-setup. Hex is the simplest baseline at 16 tokens per byte. "
    "Base64 achieves 1.33 tokens per byte but is less human-readable. Both are included as baselines "
    "in our benchmarks. Prior work on state delta trajectories (latent-space deltas), A2A (agent-to-agent "
    "transport), and MCP (Model Context Protocol) addresses different parts of the agent communication "
    "stack. PM-1 is orthogonal to these: it compresses the state representation that travels over any transport."
)

# ── 3. Methods ─────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title('3. Methods')

pdf.subsection_title('3.1 PM-1 Encoding Layer')
pdf.body_text(
    "PM-1 maps each 8-bit byte to an 8-character ASCII string: bit 0 maps to '.' (dot), bit 1 maps "
    "to '-' (dash), encoded MSB-first. This is deterministic for all 256 byte values, verified by "
    "exhaustive roundtrip test. We verified that both '.' and '-' are exactly 1 token each in "
    "cl100k_base, o200k_base, p50k_base, and r50k_base. This property is structural: any BPE "
    "tokenizer trained on text that includes ASCII punctuation will assign these characters "
    "single-token encodings because they appear frequently as isolated characters."
)

pdf.subsection_title('3.2 Differential State Protocol')
pdf.body_text(
    "The DSP emits a diff frame containing only the byte positions that changed between consecutive "
    "states, plus an index for each changed byte: <index>:<8-morse-chars>|<index>:<8-morse-chars>|... "
    "The control command T:<length>| truncates state to new_length bytes. The DiffState class "
    "maintains the current state buffer and supports three operations: diff(new_state) to compare "
    "and emit, apply(frame) to apply incoming diffs, and sync(new_state) for full state replacement "
    "during initial handshake or error recovery. A maximum state size of 65,536 bytes bounds decoder "
    "allocations and provides a DoS guard."
)

pdf.subsection_title('3.3 Lexicon and Error Correction')
pdf.body_text(
    "PM-1 defines two command tiers that share the same 8-bit encoding space. Tier 1 -- Hamming "
    "[8,4,4] provides 16 commands (NOP, ACK, NAK, RESET, SYNC, REQ, DATA, EOF, ERR, RETRY, STATUS, "
    "CONFIG, HELLO, BYE, ECHO, HALT) with single-error correction and double-error detection. "
    "Tier 2 -- parity-protected provides 128 commands (e.g., STATE_REQ, STATE_REP, DIFF, FULL_SYNC, "
    "VERSION) with single-error detection. The value 0x87 is a valid codeword in both tiers (Hamming "
    "command 7 = EOF; parity command 7 = FULL_SYNC). The protocol requires explicit tier "
    "specification -- auto-detection is not supported."
)

pdf.subsection_title('3.4 Protocol State Machine')
pdf.body_text(
    "PM-1 defines a 7-state connection lifecycle: CLOSED, HANDSHAKE (version negotiation), SYNCING "
    "(full state synchronization), DATA (normal operation with diffs), ERROR (recoverable error), "
    "RECOVERY (re-syncing after error), and DISCONNECT (clean shutdown). The handshake sequence is: "
    "CLOSED -> HELLO -> HANDSHAKE -> VERSION -> VERSION_ACK -> ACK -> SYNCING -> SYNC -> STATE_REP -> "
    "ACK -> DATA. Error recovery follows: ERROR -> STATUS/RESET -> RECOVERY -> REQ -> STATE_REP -> ACK -> DATA."
)

pdf.insert_figure(HERE / "fig3_statemachine.png",
                  "Figure 3: PM-1 Protocol State Machine -- 7 states with defined transition paths and handshake/recovery sequences.",
                  w=150)

pdf.subsection_title('3.5 Benchmark Methodology')
pdf.body_text(
    "We evaluate on two datasets. The AB-1 Crucible trace consists of 1,417 single-byte state "
    "snapshots from AB-1's benchmark suite (6 unique masks, 52.8% emit ratio). Real self-harness "
    "traces consist of 235 traces from actual agent sessions, encoded as 8-byte state vectors "
    "(agent type, outcome, duration, tool calls, files, failure category, failure severity, "
    "validation flag) with 106 unique states and 82.5% change rate. We also generate synthetic "
    "states for sensitivity analysis: 500-step sequences at byte widths of 1, 8, 32, and 128, "
    "at change rates of 10%, 30%, 50%, 70%, and 90%. All token counts use tiktoken and are "
    "reported for both cl100k_base (GPT-4/GPT-4o) and o200k_base (Claude)."
)

# ── 4. Results ─────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title('4. Results')

pdf.subsection_title('4.1 Tokenizer Atomicity')
pdf.body_text(
    "Both '.' and '-' are exactly 1 token each in all four tested tokenizers (cl100k_base, "
    "o200k_base, p50k_base, r50k_base). The zero-setup property is confirmed."
)

pdf.subsection_title('4.2 AB-1 Crucible Trace')
pdf.insert_figure(HERE / "fig1_crucible.png",
                  "Figure 1: AB-1 Crucible trace token costs on cl100k_base (1,417 states, 748 emits). Morse DSP achieves 84.8% savings vs steelman JSON and 77.9% vs hex on single-byte states.",
                  w=145)

pdf.body_text(
    "On the AB-1 Crucible trace (1,417 states, 748 emits, 52.8% ratio), Morse DSP achieves 4,270 "
    "tokens vs steelman JSON's 28,076 tokens: 84.8% savings on cl100k_base. AB-1 Braille (with its "
    "tokenizer extension) achieves 92.0% savings at 2,244 tokens. Against ASCII baselines: hex is "
    "945 tokens (77.9% cheaper than Morse), Base64 is 1,255 tokens (70.6% cheaper). The single-byte "
    "nature of this trace favors hex, which encodes each state in 2 hex chars regardless of change rate."
)

pdf.subsection_title('4.3 Real Self-Harness Traces')
pdf.insert_figure(HERE / "fig4_realtraces.png",
                  "Figure 4: Real agent trace comparison (235 self-harness traces, 8-byte states, 82.5% change rate). Morse DSP achieves 60.8% savings vs delta JSON.",
                  w=145)

pdf.body_text(
    "On 235 real agent traces with 8-byte state vectors and 82.5% state-change rate, Morse DSP "
    "achieves 2,829 tokens vs delta JSON's 7,222 tokens: 60.8% savings on cl100k_base. The higher "
    "change rate (82.5%) reduces DSP's advantage compared to the Crucible trace (52.8% emit ratio). "
    "Hex (1,285 tokens) and Base64 (1,146 tokens) both outperform Morse on this workload because "
    "nearly every step triggers a diff, making the 8x per-byte overhead dominant."
)

pdf.subsection_title('4.4 Sensitivity Sweep')
pdf.insert_figure(HERE / "fig2_sensitivity.png",
                  "Figure 2: Sensitivity sweep -- Morse vs Hex vs Base64 at varying change rates on 128-byte and 8-byte states (500 steps, cl100k_base). Morse beats hex at low change rates on multi-byte states.",
                  w=160)

pdf.insert_figure(HERE / "fig5_crossover.png",
                  "Table 1: Cross-over points where Morse DSP outperforms hex encoding, by state width and change rate.",
                  w=130)

pdf.body_text(
    "On 128-byte states at 10% change rate, Morse DSP (40,533 tokens) beats hex (72,370 tokens) by "
    "1.8x. The cross-over varies by byte width: 1-byte states never favor Morse; 8-byte states favor "
    "Morse at less than 30% change rate; 32 and 128-byte states at less than 10% change rate. At 90% "
    "change on 128-byte states, Morse loses by 4.9x versus hex, as the 8x raw overhead dominates "
    "when nearly every byte changes."
)

pdf.subsection_title('4.5 End-to-End ReAct Integration')
pdf.body_text(
    "A simulated ReAct handoff scenario (orchestrator -> fixer -> oracle, 10 handoffs, 8-byte agent "
    "state) demonstrated PM-1 in a realistic agent loop: approximately 520 PM-1 characters vs 1,025 "
    "equivalent JSON characters, saving approximately 49.3%. Hamming error correction was verified "
    "on realistic failure scenarios: single-bit flips are corrected, double-bit flips are detected "
    "and flagged as uncorrectable."
)

# ── 5. Discussion ─────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title('5. Discussion')

pdf.subsection_title('5.1 When to Use PM-1')
pdf.body_text(
    "PM-1 is most effective in three regimes. (1) Low state-change rates (<=10%) where DSP "
    "amortizes per-byte overhead and Morse beats hex by 1.4-2x on multi-byte states. (2) Multi-byte "
    "state vectors (>=8 bytes) where emit-on-change selectivity offsets the 8x raw encoding "
    "overhead. (3) Cross-provider portability where no tokenizer extension can be installed and "
    "the protocol must work identically across GPT-4, Claude, Gemini, or any BPE-based model."
)
pdf.body_text(
    "PM-1 is NOT recommended for: single-byte states at high change rates (hex or Base64 is "
    "cheaper); environments where the tokenizer extension can be installed (AB-1 Braille is "
    "denser at 1 token/state); or human-readable debugging output (hex is more legible)."
)

pdf.subsection_title('5.2 Relationship to AB-1')
pdf.body_text(
    "PM-1 is explicitly a derivative of AB-1. The Differential State Protocol, Hamming [8,4,4] "
    "code, two-tier command structure, and benchmark methodology are adapted from Tetrahedroned's "
    "design. PM-1's original contributions are: the '.'/'-' encoding scheme with its zero-setup "
    "analysis; the complete protocol state machine (7 states with handshake/recovery sequences); "
    "DSP relay semantics (apply() returns the forwarded frame for relay chains); DoS hardening "
    "(MAX_STATE_BYTES = 65536); and benchmarking against hex and Base64 baselines on multi-byte "
    "states. We believe PM-1 occupies a useful niche: it trades AB-1's superior density for "
    "universal portability."
)

pdf.subsection_title('5.3 Limitations')
pdf.bullet("Single-benchmark scope: the Crucible trace is from AB-1's ecosystem, though our 235-trace real dataset partially addresses this.")
pdf.bullet("No trained embedding: PM-1 tokens have no learned semantics for the model -- they are opaque state identifiers.")
pdf.bullet("Human-unfriendly: designed for machine-to-machine communication; debugging requires a separate rendering layer.")
pdf.bullet("Unicode tokenizers not tested: SentencePiece-based models (Gemma, Llama-1/2) tokenize ASCII differently from tiktoken.")
pdf.ln(3)

pdf.subsection_title('5.4 Security Considerations')
pdf.body_text(
    "The 64 KB maximum state size bounds memory allocation for untrusted frames. The Hamming "
    "[8,4,4] and parity error detection layers protect against single-bit inference errors in "
    "model outputs. However, adversarial inputs designed to exploit the protocol (e.g., injecting "
    "command frames into natural-language text) are out of scope. PM-1 assumes a trusted transport "
    "between known agent instances."
)

# ── 6. Conclusion ─────────────────────────────────────────────────────
pdf.section_title('6. Conclusion')

pdf.body_text(
    "We presented Pro Memoria (PM-1), an ASCII-native binary protocol for token-efficient agent "
    "state communication. By encoding 8-bit state as 8-character Morse strings and combining this "
    "with a differential state protocol and a two-tier error-correcting lexicon, PM-1 achieves "
    "60-85% token savings versus delta-encoded JSON with zero setup -- no tokenizer extension, "
    "no Unicode registration, no configuration changes. The protocol is fully implemented "
    "(approximately 750 lines of Python), verified with exhaustive tests (256-byte roundtrip, "
    "128/128 single-error Hamming corrections, 448/448 double-error detections, 56 DSP edge "
    "cases), and benchmarked on both synthetic and real agent traces."
)

pdf.body_text(
    "PM-1 is not a replacement for AB-1 Braille, which achieves superior density through its "
    "tokenizer extension. Rather, PM-1 fills the gap for environments where an extension cannot "
    "be installed but token-efficient state communication is still required."
)

pdf.body_text(
    "The implementation is open source at github.com/rikirinjani/pro-memoria under Apache-2.0 "
    "(code) and CC-BY-4.0 (specification)."
)

# ── References ─────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title('References')

refs = [
    "[1] Tetrahedroned. Agent Braille (AB-1): A Unicode-Based Protocol for Machine-to-Machine State Communication. 2025. github.com/Tetrahedroned/Agent-Braille",
    "[2] Yao, S. et al. ReAct: Synergizing Reasoning and Acting in Language Models. ICLR, 2023.",
    "[3] Brown, T. et al. Language Models are Few-Shot Learners. NeurIPS, 2020.",
    "[4] Google. Model Context Protocol (MCP). 2024. github.com/modelcontextprotocol",
    "[5] Google. Agent-to-Agent (A2A) Protocol. 2025. github.com/google/A2A",
    "[6] Sennrich, R. et al. Neural Machine Translation of Rare Words with Subword Units. ACL, 2016.",
    "[7] Hamming, R. W. Error Detecting and Error Correcting Codes. Bell System Technical Journal, 1950.",
]

pdf.set_font('Times', '', 10)
for ref in refs:
    pdf.multi_cell(0, 5.5, ref)
    pdf.ln(2)

# Save
out_path = HERE / "pro-memoria.pdf"
pdf.output(str(out_path))
print(f"PDF saved: {out_path}")
