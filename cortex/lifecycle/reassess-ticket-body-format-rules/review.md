# Review: reassess-ticket-body-format-rules

**Tier**: complex · **Criticality**: high → Stage 1 + Stage 2 run.

## Requirements loaded

- `cortex/requirements/project.md` — read in full; Deletion bias paragraph (line 23) is the load-bearing section for R3/R4.
- `cortex/requirements/glossary.md` — read; no defined term is touched by this change, no drift.
- `cortex/requirements/backlog.md` — read manually per the task brief's instruction (the auto-load matched no area docs — this is a Context B lifecycle with structurally empty `index.md` tags, not a repairable index defect). `backlog.md` documents the local `cortex-backlog` store's mechanics; it does not govern `skills/backlog-author/SKILL.md`'s ticket-body template content or the citation-ban prose. No conflict with this diff.

## Stage 1 — Spec compliance

**R1 — Delete the citation ban from the shipped skill: PASS.**
`skills/backlog-author/SKILL.md` (commit `4c6a70c7`) removed exactly the "Prose only: ..." second sentence on the old `:13` and the trailing "If an `## Edges` bullet needs a path:line ..." sentence plus its preceding blank line. The five heading names and all five section bullets are untouched, verified byte-for-byte against the pre-change version via `git show 4c6a70c7`.
Acceptance checks re-run directly:
- `grep -ciE 'path:line|§N|fenced code' skills/backlog-author/SKILL.md` → `0` ✓
- `grep -c '^- \*\*`## ' skills/backlog-author/SKILL.md` → `5` ✓
- `uv run pytest tests/test_backlog_author.py` → `3 passed` ✓

**R2 — Correct the stale test docstring: PASS.**
`tests/test_backlog_author.py` (commit `8ac0f33a`) drops the two phantom entries (`test_interview_mode_routes_through_askuserquestion`, `test_lex1_rejects_code_block_in_why_section`) and the finished-build scaffolding sentence. Verified:
- `diff <(docstring names) <(def names)` → empty, exit `0` ✓
- `uv run pytest tests/test_backlog_author.py --collect-only -q` → `3 tests collected` ✓

**R3 — Record the build-failure discharge rule: PASS, polarity correct.**
This is the finding that matters most, so I read the live paragraph directly rather than trusting any grep. The added text (commit `f63bfc68`, appended in-line to the existing Deletion bias paragraph at `project.md:23`):

> "A surface with no consumer that fails on its removal carries the presumption of removal; discharge requires either a consumer that turns a build or gate red when the surface is removed — not a report-only or manually-invoked script — or a filed bug recording observed failure, not a hypothetical. Discharge holds only while its consumer holds, since a discharging consumer is itself subject to deletion bias in turn; where discharged, the surface is weighed on the merits rather than presumed deletable."

Checked against the correct polarity stated in my brief — *absence of a consumer that fails on removal is what MAKES a surface presumed-deletable; a build-reddening consumer or a filed observed-failure bug is what RESCUES it, and that rescue expires with its consumer* — this is an exact, unambiguous match on all three parts: (1) no-failing-consumer → presumption of removal (not the inverse), (2) the two named discharge routes (build/gate-red consumer, or filed-bug-with-observed-failure — explicitly excluding report-only/manual scripts and hypotheticals), (3) discharge expires when its consumer does. There is no ambiguity to call PARTIAL on; this is a clean PASS on the one axis that could not be caught by any token check.

Caps: sentence-count check — `grep -m1 '^\*\*Deletion bias\*\*' ... | grep -oE '\. |\.$' | wc -l` → `7` against baseline `4` → **3 sentences added** for R3+R4 combined, well inside the ≤6 cap. Reads in-line as part of the existing paragraph (confirmed via `git show f63bfc68` — a single-line diff, no new heading or bullet). Does not restate "the burden of proof sits on keeping, not deleting" verbatim or in substance-duplicating form.

**R4 — Record why `## Why`/`## Role` are retained: PASS.**
Same commit, final added sentence: "`cortex_command/backlog/load_parent_epic.py`'s `INTENT_SECTIONS` tier is a live consumer of the ticket body's `## Why`/`## Role` sections, and closed bug #375 records the observed harm when they return empty, so their discharge runs through #375's observed failure rather than through `tests/test_load_parent_epic.py`, which pins `CORTEX_BACKLOG_DIR=tmp_path` and so can never fail on real-corpus drift." This names `load_parent_epic.py` and `#375`, states the discharge runs through the closed bug and explicitly not through the tmp_path-fixtured test (matching the spec's specific instruction), and is 1 sentence (≤2 cap). Lands only in `cortex/requirements/project.md`; confirmed via `git diff 36593790..HEAD --stat` that no other R3/R4-related edit touched `skills/` or `plugins/`.
- `grep -c '#375' project.md` → `1` ✓; `grep -c 'load_parent_epic.py' project.md` → `1` ✓.

**R5 — Mirror parity holds: PASS.**
`diff skills/backlog-author/SKILL.md plugins/cortex-core/skills/backlog-author/SKILL.md` → empty, exit `0`. The pre-commit hook regenerated the mirror from the staged blob in `4c6a70c7`; both files are identical post-commit.

**Non-Requirements — spot-checked, no violations found:**
- Five-section template: unchanged. All five headings and bullets byte-identical apart from the two deleted sentences named in R1.
- No repo-governance prose leaked into `skills/` or `plugins/` (`CLAUDE.md:33-34`): `git diff 36593790..HEAD -- skills/ plugins/` greps clean for `CLAUDE.md`/`project.md`/`Deletion bias`/`governance` — no match.
- CLAUDE.md front-door bar not reopened: `CLAUDE.md` does not appear in the changed-files list at all.
- Full changeset matches exactly the 7 files named in the plan/spec (`git diff --stat`): `project.md`, both `SKILL.md` copies, `tests/test_backlog_author.py`, and the lifecycle's own `plan.md`/`index.md`/`events.log`. No stray edits.

**No FAIL on any requirement → proceeding to Stage 2.**

## Stage 2 — Code quality

- **Naming/pattern consistency**: The R3/R4 addition reuses the paragraph's existing vocabulary and register ("burden of proof," "named evidence" elsewhere in the same doc) rather than introducing a new jargon layer — reasonably consistent with the surrounding `project.md` prose style.
- **Verification genuinely executed, not self-certified**: I independently re-ran every acceptance/verification command named in the spec and plan rather than trusting the builders' checkpoints — all reproduced the claimed results (grep counts, pytest runs, docstring/def diff, mirror diff, and the combined suite `tests/test_backlog_author.py tests/test_skill_size_budget.py tests/test_l1_surface_ratchet.py` → `25 passed`).
- **Minor — compound-sentence risk flagged by the plan, partially realized (PARTIAL, non-blocking)**: The plan's Risks section explicitly warned that the ≤6-sentence cap "bounds count, not bytes" and that "compound run-on construction is the specific failure mode." The landed prose stays within the sentence-count cap (3 added) but two of the three added sentences use semicolon-joined compound clauses, and the R4 sentence chains three clauses via "and / so / which." This is defensible — polarity and substance are unambiguous and each clause carries distinct content, not padding — but it is denser than "plain phrasing" ideally calls for. Not a spec violation (all caps are met), just a style note for anyone editing this paragraph next.
- **Minor — orphaned stale-reference comment, out of R2's literal scope (PARTIAL, non-blocking)**: `tests/test_backlog_author.py:64` still carries the section-header comment `# Test functions (bodies added in Task 9)`, the same "finished build step" staleness R2 was written to fix in the module docstring. R2's acceptance criteria are scoped to the *docstring* specifically and are fully met; this sibling comment was simply out of scope, not missed by the letter of the task. Cheap to clean up in a follow-up touch, not worth reopening this lifecycle for.
- **Error handling**: N/A — no new code paths, only prose/doc edits.

No blocking Stage 2 issues.

## Requirements Drift

**State**: none

**Findings**: None — the implementation is exactly what R3/R4 asked `project.md` to record; no new behavior was introduced beyond what the loaded requirements already describe post-edit.

**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["Minor: R3/R4 addition uses semicolon-joined compound sentences in 2 of 3 added sentences, which the plan's own Risks section flagged as the specific failure mode to avoid even though the sentence-count cap is met (non-blocking, style-only)", "Minor: tests/test_backlog_author.py:64's section-header comment still references 'Task 9' — same staleness pattern R2 fixed in the docstring, but out of R2's literal scope so not a spec violation (non-blocking cleanup candidate)"], "requirements_drift": "none"}
```
