# Spec: Batch 1 — Verified Lifecycle-Cluster Trim Sweep (#353)

> Epic background: `cortex/research/skill-value-scorecard/report.html` (audit #347). Per-candidate authoritative instructions (trim + keep-list + mirror precondition) live in `cortex/research/skill-value-scorecard/master_candidates.json` → `verdict_summaries[].revised_claim`. See `research.md` for the batch inventory and rationale.

## Objective

Apply the 50 already-verified trim verdicts in the lifecycle cluster (+ the one verified critical-review `reviewer-prompt` candidate) that no sibling ticket owns, realizing ~8.6k weighted-token savings on hot-path skill prose, **without weakening any pinned or consumed surface**.

## In scope

The 50 `verified_survives` candidates across 19 files enumerated in `research.md`. Each is applied per its `revised_claim`, honoring the named keep-list verbatim.

## Out of scope

- The provisional tail (162 candidates), the transitive-file slice, and all cluster SKILL.md provisional bodies — deferred to later #353 batches / follow-up tickets.
- Sibling-owned files (implement.md #348, commit SKILL #349, research SKILL #350, project.md #351, lifecycle.config.md #352).
- `dup_groups.json` groups that span `implement.md` — deferred to the #348 seam. Non-implement dup groups may be single-sourced only opportunistically when both files are open in a batch commit.

## Requirements

- **R1 — Apply each verdict faithfully.** For every Batch-1 candidate, perform the `revised_claim`'s action (COMPRESS / LAZY_REF / DELETE / MERGE_DEDUP) and keep verbatim exactly what its keep-list names (verb+flag invocations, exit/stdout routing, gate names, canonical-rule anchors).
- **R2 — Locate by heading + pins.** Never trust the stored line numbers (stale). Find each section by its heading and pinned tokens.
- **R3 — Dual-source integrity.** Every edited file's `plugins/cortex-core/` mirror is regenerated and committed in the **same commit** as its canonical edit. The drift pre-commit hook must pass (no split, no stale mirror).
- **R4 — reviewer-prompt s9 keep/relocate.** The straddle-rationale population instruction (sole repo-wide) is kept or relocated, not dropped. The JSON-envelope compression preserves the `<!--findings-json-->` delimiter contract and every field the critical-review synthesizer parses.
- **R5 — Kept-pauses / parity safety.** Edits to `SKILL.md` s16 and `kept-pauses.md` s1 must not change the parity-tested pause **inventory** (`tests/test_lifecycle_kept_pauses_parity.py`) — compress preamble/restatement prose only.
- **R6 — Reference-resolution safety.** Edits to reference files must not break `tests/test_lifecycle_references_resolve.py` (file existence + reference-map entries in SKILL.md:155 and its mirror). LAZY_REF candidates (orchestrator s7, criticality-matrix s5) must leave a resolvable pointer.
- **R7 — Commit hygiene on trunk.** Commit each file with an explicit pathspec (`git commit -- <canonical> <mirror>`) so the concurrent session's staged files don't leak. Use the `/cortex-core:commit` skill.

## Acceptance criteria

- **AC1** — All pinned tests green after each file, and a full `just test` passes before Review (7/7 suites, per the audit's baseline).
- **AC2** — Every keep-list token named in an applied candidate's `revised_claim` still greps present in its file (keep-list survival check).
- **AC3** — `git status` shows canonical + mirror in lockstep for every edited skill file; the drift hook passes on each commit.
- **AC4** — Realized weighted savings ≈ 8.6k (best-effort measurement against the candidate `weighted_cost` sum; exact token count not gated, direction is).
- **AC5** — No behavioral regression in the lifecycle/critical-review flow: the reference-resolve, kept-pauses parity, and complexity-escalator parity suites all pass.

## Risks & mitigations

- **Over-trimming a load-bearing line** → mitigated by R1 keep-lists + AC2 survival greps + per-file test gate.
- **Mirror drift** → R3 + AC3, canonical+mirror in one commit.
- **reviewer-prompt synthesizer breakage** → R4, verify against synthesizer parsing before committing that file; it's the single highest-risk candidate (verify first or isolate its commit).
- **Concurrent-session commit contamination** → R7 explicit pathspecs.
