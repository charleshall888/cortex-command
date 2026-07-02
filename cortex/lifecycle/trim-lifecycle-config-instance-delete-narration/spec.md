# Specification: trim-lifecycle-config-instance-delete-narration

> Epic context: child of #347 (skill-value-scorecard follow-through). Epic research: `cortex/research/skill-value-scorecard/report.html`; verdict source: `cortex/research/skill-value-scorecard/master_candidates.json` (candidates s4–s8 under `file: cortex/lifecycle.config.md`). See `research.md` for the full code-verified findings.

## Problem Statement

This repo's own `cortex/lifecycle.config.md` is read wholesale by the lifecycle skill at start, so its body prose is model-read context on every lifecycle invocation. Five `verified_survives` scorecard verdicts (s4–s8, ~3,280 weighted tokens) identify a `## Branch Mode` section whose content is either code-enforced parser narration (s7/s8) or a third copy of documentation already owned by the picker-decision path and code (s4/s5/s6). Removing it shrinks the always-read surface with no behavioral effect, and consolidates the branch-mode operator documentation into its existing doc home — closing a pre-existing gap where the four valid values are listed nowhere operator-facing.

## Phases

- **Phase 1: Trim + consolidate** — delete the Branch Mode section from the config, relocate the value enumeration to the operator doc, add a frontmatter pointer, and correct the ADR-0017 status.

## Requirements

1. **Delete the `## Branch Mode` section and all its subsections from `cortex/lifecycle.config.md`** (candidates s4–s8: intro, `### Values (closed set)`, `### Carve-outs`, `### Normalization rules`, `### Edge cases`). Acceptance: `grep -c '^## Branch Mode' cortex/lifecycle.config.md` = 0 AND `grep -cE '### (Values \(closed set\)|Carve-outs|Normalization rules|Edge cases)' cortex/lifecycle.config.md` = 0. **Phase**: Trim + consolidate
2. **Preserve everything above the deleted section**: frontmatter (fields unchanged), the `# Lifecycle Configuration` heading + intro, and `## Review Criteria` (s3, `verified_refuted` — keep). Acceptance: `grep -c '^## Review Criteria' cortex/lifecycle.config.md` = 1 AND the frontmatter still parses (`.venv/bin/python -c "import cortex_command.lifecycle_config as m,pathlib; print(m.read_branch_mode(pathlib.Path('.')))"` prints `prompt`, pass if output = `prompt`). **Phase**: Trim + consolidate
3. **Add a single frontmatter comment line pointing operators to the doc**, placed on its own line immediately above the `branch-mode: prompt` field (a YAML comment, so the parser is unaffected). Acceptance: the line immediately preceding `branch-mode: prompt` begins with `#` and contains `docs/overnight-operations.md`; `read_branch_mode` still returns `prompt` (per R2's parser check). **Phase**: Trim + consolidate
4. **Complete the existing branch-mode note in `docs/overnight-operations.md`** (at the "Consumed-but-unscaffolded exception", ~:717) with the four-value enumeration (`worktree-interactive`, `trunk`, `feature-branch`, `prompt`) and a one-line carve-out summary (picker fires regardless on a dirty tree or a live interactive worktree). Do not restate the full routing prose — the point-of-use owner is `implement.md` §2. Acceptance: `grep -c 'worktree-interactive' docs/overnight-operations.md` ≥ 1 AND all four value tokens appear in the branch-mode section. **Phase**: Trim + consolidate
5. **Correct `cortex/adr/0017-reconcile-and-gate-lifecycle-config-sources.md` frontmatter `status: proposed` → `status: accepted`** (its parity gate `tests/test_lifecycle_config_parity.py` is implemented and green). Acceptance: `grep -c '^status: accepted' cortex/adr/0017-reconcile-and-gate-lifecycle-config-sources.md` = 1. **Phase**: Trim + consolidate
6. **No regression in the config/citation/parity tests.** Acceptance: `.venv/bin/python -m pytest tests/test_lifecycle_config.py tests/test_lifecycle_config_parity.py tests/test_skill_section_citations.py tests/test_lifecycle_implement_branch_mode.py -q` exits 0. **Phase**: Trim + consolidate

## Priority (MoSCoW)

- **Must-have**: R1–R4 (the trim + docs consolidation + frontmatter pointer) and R6 (no test regression) — the core value and its safety net.
- **Should-have**: R5 (ADR-0017 status fix) — correct and operator-elected, but separable; it can be dropped without affecting the trim (this was the scope choice made at spec time).
- **Won't-do**: everything in Non-Requirements below (notably: no code, asset, template, or mirror change; no branch-mode scaffolding).

## Non-Requirements

- **No code change.** The parser (`lifecycle_config.py`) and picker (`lifecycle_implement.py:should_fire_picker`) are untouched — they read frontmatter and the closed set from code, never the deleted body prose.
- **No asset/template/mirror change.** Neither `skills/lifecycle/assets/lifecycle.config.md` nor `cortex_command/init/templates/cortex/lifecycle.config.md` contains the Branch Mode blocks; the #335 parity gate stays green untouched. No plugin mirror regeneration.
- **Not scaffolding `branch-mode` into the asset/template.** That is the separate follow-up already flagged at `docs/overnight-operations.md:717` (would require the ADR-0017-bound asset+template edit).
- **No change to `## Review Criteria` (s3)** — the audit refuted its dedup verdict.
- **Not correcting the audit's stderr-warning claim in `master_candidates.json`** — the verdict source is a research record; the correction lives in this lifecycle's `research.md`.

## Changes to Existing Behavior

- **REMOVED**: the `## Branch Mode` documentation section from the always-read repo config instance (model-read surface only; no code path reads it).
- **ADDED**: the four branch-mode values + a carve-out line to the operator doc `docs/overnight-operations.md` (consolidated into the existing note, not a new copy).
- **MODIFIED**: ADR-0017 status `proposed` → `accepted` (reflects its already-shipped parity gate).
- No change to any runtime behavior: `read_branch_mode`, `should_fire_picker`, and the picker UX are byte-for-byte unaffected.

## Edge Cases

- **Frontmatter comment breaks the parser**: if the R3 pointer is written as an inline value (`branch-mode: prompt # …`) or misplaced below the closing `---`, it could alter what `read_branch_mode` returns. Expected: write it as a standalone `#` comment line *above* `branch-mode:` inside the frontmatter; `read_branch_mode` must still return `prompt` (R2/R3 parser check).
- **Deletion boundary over/under-cut**: deleting the `## Branch Mode` section must stop exactly at it — `## Review Criteria` (immediately above) must survive (R2), and the file must end cleanly after Review Criteria with a single trailing newline (Branch Mode was the last section, so EOF follows the cut).
- **Docs value list lands in the wrong place**: the four values must be added to the branch-mode note in `docs/overnight-operations.md` (~:717), not elsewhere in the ~1k-line doc. Expected: the four tokens appear within the branch-mode section (R4).
- **ADR frontmatter has other fields**: ADR-0017's frontmatter currently holds only `status:`. Expected: change only that line to `accepted`; do not add or reorder fields (R5).

## Technical Constraints

- The frontmatter-region parser (`_extract_frontmatter_text`) bounds on the first two `---` delimiters; body edits below the closing `---` cannot affect it. The R3 comment must live *inside* the frontmatter (above `branch-mode:`) as a YAML `#` comment.
- Correction of record (research §"Correction to the audit's stated fail-safe"): an out-of-set `branch-mode` value fires the picker **silently** (`should_fire_picker` → `(True, "branch_mode_unset_or_invalid")`, no stderr). The deleted s7 prose claiming "a stderr warning names the rejected value" is inaccurate — a further reason the DELETE is safe.

## Open Decisions

None. Scope shape (config + docs + ADR, 3 files) confirmed with the operator at spec time.

## Proposed ADR

None considered. (R5 corrects the status of an existing ADR; it is not a new architectural decision.)
