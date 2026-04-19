# Session Retro: 2026-04-17 17:16

## Problems

**Problem**: First spec draft overclaimed §4 approval as a safety net for malformed fix-agent rewrites — Non-Requirements asserted "will surface at user approval time (§4)" when §4 is a Produced/Value/Trade-offs paraphrase, not a file read. **Consequence**: Critical-review caught a factually wrong rationale; required rewriting the Non-Requirements F5 bullet and adjacent Edge Case entries.

**Problem**: First spec draft claimed S1–S6 checklist would "flag missing or broken structure" on a malformed on-disk artifact. S1–S6 are content-coverage criteria (Binary-checkable acceptance criteria, Edge cases, MoSCoW, Non-Requirements, Technical constraints, Changes to behavior) — none check file existence, emptiness, or parse validity. **Consequence**: Critical-review caught another false claim; had to document the failure mode as accepted-hidden-failure instead.

**Problem**: First spec draft cited Google ADK `disallow_transfer_to_parent=True` and OpenAI Agents SDK JSON-schema envelopes as evidence for "subagent boundary is the high-reliability lever." Those frameworks enforce at runtime; this design enforces via instruction in a prompt template. **Consequence**: Critical-review caught the overclaim; had to rewrite Technical Constraints to describe the envelope honestly as an LLM-mediated instruction-level convention.

**Problem**: Original R2/R3 acceptance criteria used `grep -c ≥ 2` without awk-bounded extraction to verify per-block presence. Two occurrences clustered in the cycle-1 block would satisfy the greps while cycle≥2 had zero. **Consequence**: Critical-review flagged the grep gap; had to swap to awk-bounded extraction (the same technique R6/R7 already used).

**Problem**: Original R2/R3 bind-by-reference phrasing "flagged signals from the list above" was a positional referent, not a structural anchor — breaks if §2a is reordered or content is inserted between the signal list and failure-path blocks. **Consequence**: Critical-review flagged it; had to swap to "signals flagged in §2a's Research Confidence Check" (structural anchor tied to the section heading).

**Problem**: Original spec R4 had a conjunctive acceptance criterion ("positive directive AND no instruction asks to summarize/announce/confirm"), but only the positive directive had a grep. The second clause was framed as instruction-to-the-implementer, not a verification assertion. **Consequence**: Silent coverage gap — a fix-agent could add "Announce passing checks" and R4 would still pass. Plan critical-review caught this and required adding R4.2 awk-bounded grep to plan T3 and T6.

**Problem**: First AskUserQuestion call in spec phase returned only 3 of 4 answers — Q1 (§2a pass event) was missing from the response. **Consequence**: Had to re-ask Q1 separately; extra round-trip with the user.

**Problem**: First plan draft labeled Context-field text as "Recommended phrasing" when the acceptance greps bind specific substrings and the phrasing was effectively mandatory. **Consequence**: Plan critical-review flagged the linguistic mismatch; had to relabel as "Example phrasing (illustrative only); the grep defines the binding invariant."

**Problem**: First plan draft's T4 Context contained a full fenced YAML template with surrounding prose directive and numbered-list prefix — pre-written edit material rather than structural context. **Consequence**: Plan critical-review flagged code-budget crossing; had to rewrite T4 Context as field-by-field invariant specification.

**Problem**: First plan draft's Overview claimed "Tasks are serialized per file to avoid edit-merge conflicts." The `Edit` tool matches on `old_string`, not line numbers, so disjoint-region edits are mechanically safe — the real risk is pipeline-level concurrent dispatch. **Consequence**: Plan critical-review caught the false rationale; had to rewrite Overview to document defensive serialization against pipeline dispatch semantics, not edit-merge conflicts.

**Problem**: First plan draft's T6 Files was "none (read-only verification)" under P6 which reads "every file implied by Verification is listed in Files." T6's verification reads two files; the Files value didn't list them. **Consequence**: Plan critical-review flagged P6 ambiguity; had to list both files with `(read-only)` qualifier.

**Problem**: First plan draft's T6 Verification said "every R1–R7 acceptance command" without enumerating the assertions — implicit reference to spec.md. **Consequence**: Plan critical-review flagged this as drift-prone; had to enumerate all 14 acceptance assertions inline (count grew from 13 to 14 after R4.2 was added).

**Problem**: Two critical-review rounds in the same session each surfaced multiple honesty/accuracy gaps in first-draft artifacts — spec critical-review caught 9 objections; plan critical-review caught another ~10. **Consequence**: Significant rework in critical-review Step 4 twice in the session; the pattern suggests first-draft artifacts consistently overclaim or leave acceptance gaps that only adversarial review surfaces.

**Problem**: Initial spec draft labeled all 7 requirements as a flat list without MoSCoW justification, despite all 7 being genuine must-haves. **Consequence**: Orchestrator-review cycle 1 flagged S3; required a fix-agent dispatch to add the MoSCoW paragraph.

**Problem**: Initial spec acceptance criteria for R3, R6, R7 used form (b) observable-state while R1, R2, R4, R5 used form (a) runnable-command — inconsistent rigor within the same artifact. **Consequence**: Orchestrator-review cycle 1 flagged the inconsistency; fix-agent tightened R3 to awk+grep counts, R6/R7 to awk-bounded Step 5 extraction.
