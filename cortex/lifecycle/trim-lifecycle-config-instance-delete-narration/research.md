# Research: Trim `cortex/lifecycle.config.md` — delete narration, resolve Branch Mode cold home

## Epic Reference

Parent epic: [[347-*]] "Skill value scorecard follow-through: verified trims and offloads". Epic research: `cortex/research/skill-value-scorecard/report.html`; verdict source: `cortex/research/skill-value-scorecard/master_candidates.json`. This ticket applies the five `file: cortex/lifecycle.config.md` verdicts (candidate ids **s4–s8**); sibling tickets own the same-id candidates under *other* files. Research here is scoped to this one config instance only.

> Research method: this is a simple-tier, single-file prose trim. All claims below were verified directly against the code, the tests, and the audit data by the orchestrator rather than via a research fan-out. Each finding cites the file:line it was checked against.

## Goal

Reduce the always-read body surface of this repo's own `cortex/lifecycle.config.md` (read wholesale by the lifecycle skill at start) by ~3,280 weighted tokens (820 raw), by applying five `verified_survives` scorecard verdicts:

| id | Section (current lines) | Category | weighted |
|----|-------------------------|----------|----------|
| s4 | `## Branch Mode` intro (27–31) | LAZY_REF | 708 |
| s5 | `### Values (closed set)` (33–38) | LAZY_REF | 584 |
| s6 | `### Carve-outs` (40–45) | LAZY_REF | 784 |
| s7 | `### Normalization rules` (47–53) | DELETE | 920 |
| s8 | `### Edge cases` (55–57) | DELETE | 284 |

`## Review Criteria` (s3, lines 20–25) is **`verified_refuted`** in the audit — keep it untouched. Frontmatter (lines 1–14), `# Lifecycle Configuration` heading + intro (16–18) stay.

## Codebase findings

### The always-read consumer is the model, not code

`skills/lifecycle/SKILL.md` "Project Configuration" instructs: *"If `cortex/lifecycle.config.md` exists at the project root, read it first."* So the body prose has exactly one runtime consumer — the model reading the whole file at lifecycle start. **No code branch reads the body**: the parser (`cortex_command/lifecycle_config.py`) only ever extracts and `yaml.safe_load`s the *frontmatter* region (`_extract_frontmatter_text`, `read_branch_mode` at :55–94, `resolve_backlog_backend` at :97–154). Removing body prose reduces model-read context and cannot affect any code path. Edge #1 ("confirm nothing routes on the deleted prose") — **cleared**: a repo-wide grep for the deleted section headings finds no consumer outside the file itself and the audit artifacts.

### The closed set + carve-outs are already owned by the picker-decision path (governs the s4/s5/s6 cold home)

- **Code owns the closed set and the fire conditions.** `cortex_command/lifecycle_implement.py:should_fire_picker` (:106–141) enumerates `_VALID_BRANCH_MODES = {worktree-interactive, trunk, feature-branch, prompt}` and both carve-out conditions (`dirty_tree`, `live_interactive_worktree_session`). The value semantics are recorded in ADR-0004 / ADR-0008.
- **The point-of-use skill reference already documents value routing and carve-outs.** `skills/lifecycle/references/implement.md` §2 ("Branch-mode dispatch preflight", :28–44) spells out per-value routing (`trunk`/`worktree-interactive`/`feature-branch`/`prompt`) and the fall-through-to-picker reasons. This is the reference the picker path actually reads on demand.
- **The operator doc already hosts a branch-mode note.** `docs/overnight-operations.md:717` ("Consumed-but-unscaffolded exception") explains `branch-mode` exists and must be "set by hand" — but does **not** enumerate the four values.

Net: the config body's s5/s6 content is a **third copy** of code + implement.md §2. Per the ticket's own criterion ("deletion if the closed set is fully owned by the picker-decision verb"), s5/s6 qualify for deletion. The one genuine operator-facing gap is that `docs/overnight-operations.md` names `branch-mode` without listing its values.

### Correction to the audit's stated fail-safe (confirmed in code)

s5's evidence ("invalid value → named stderr warning + picker") and s7's claim ("typos degrading fail-safe to the picker plus a stderr warning") are **factually wrong**. `should_fire_picker` returns `(True, "branch_mode_unset_or_invalid")` for any out-of-set value (:129–130) with **no stderr emission**; `read_branch_mode` prints a stderr warning **only** on malformed YAML (:80–85), never on an out-of-set value. So the picker fires **silently** on a typo. The deleted config prose at line 53 ("a stderr warning names the rejected value and the picker fires") is itself inaccurate. This *strengthens* the s7 DELETE verdict — the narration is not merely redundant, it is wrong — and it makes the operator-facing value enumeration slightly more valuable (a typo gives no named hint), which argues for completing the docs note rather than pure deletion.

### Test-safety (no test pins the deleted body)

- `tests/test_lifecycle_config_parity.py` compares **only the asset↔template frontmatter regions** (`skills/lifecycle/assets/…` vs `cortex_command/init/templates/…`); it never reads this repo instance. Body deletions here cannot break it. (Confirms the ticket's Integration claim + Edge on the #335 gate staying green.)
- `tests/test_skill_section_citations.py` pins headings in `plan.md` / `complete.md` cited by `lifecycle_config.py:8-9,95-96` — **not** any heading in this file.
- `tests/test_lifecycle_config.py` is a pure parser unit test with no body-prose assertions.
- The asset (`skills/lifecycle/assets/lifecycle.config.md`) and init template (`cortex_command/init/templates/cortex/lifecycle.config.md`) contain **neither** the Branch Mode nor Normalization blocks, so there is no asset/template edit and no mirror regeneration. (Confirms ticket Role.)

### ADR-0017 status (Edge #2)

`cortex/adr/0017-reconcile-and-gate-lifecycle-config-sources.md` reads `status: proposed`, but its parity gate (`test_lifecycle_config_parity.py`) is implemented and green. The ticket invites correcting this "in passing if touched." It is a one-line frontmatter change (`proposed` → `accepted`), independent of the config trim.

## Decision: cold home for the LAZY_REF trio

**Delete the whole `## Branch Mode` section (s4–s8, lines 27–57) from the repo config instance**, and:

1. **Complete the existing operator note** in `docs/overnight-operations.md` (at the `branch-mode` "Consumed-but-unscaffolded exception", ~:717) with the four-value enumeration (from s5) and a one-line carve-out summary (from s6). This consolidates into the *existing* operator home rather than creating a new copy, and closes the pre-existing "values not listed anywhere operator-facing" gap.
2. **Leave a one-line frontmatter pointer comment** above `branch-mode: prompt` in the config, pointing operators to the docs section (preserves discoverability of the field itself; frontmatter is cheap and is what the parser reads).

Rationale over the audit's literal "relocate all three to docs": s5 (routing) and s6 (carve-outs) are already fully documented at the point of use (implement.md §2) and in code — relocating them verbatim would recreate the triplication the audit flagged. Only the compact 4-value list fills a real doc gap. This honors the trim intent, the "picker-decision path owns it" criterion, and the solution-horizon principle (fix the doc gap durably, not just move bytes).

Scope consequence (per critic obj 1/2): the diff spans up to **three files** — `cortex/lifecycle.config.md` (delete + frontmatter comment), `docs/overnight-operations.md` (value list), and optionally `cortex/adr/0017-*.md` (status line). The ticket's "only file that changes" reflected the pure-delete branch; the LAZY_REF cold-home decision the ticket explicitly delegated to research expands it to the docs note. This remains a simple-tier change — three files of mechanical prose edits, no code, no new patterns, no behavioral effect on callers.

### Deletion span (resolved)

Remove lines 27–57 (`## Branch Mode` through the end of `### Edge cases`). Preserve the frontmatter (1–14), the `# Lifecycle Configuration` intro (16–18), and `## Review Criteria` (s3, 20–25).

### Spec-phase scope decision (not a research gap)

Whether to include the ADR-0017 `proposed` → `accepted` status fix is a scope-inclusion preference, not a research question. Recommendation for Spec: include it (one-line, factually correct, ticket-invited via Edge #2), scoped as a **distinct, optional requirement** so it can be dropped without affecting the trim.

## Open Questions

None. Research resolved the cold-home decision (delete + docs-note completion + frontmatter pointer) and the deletion span. The only remaining choice — ADR-0017 inclusion — is a spec-phase scope preference, recorded above, not an open research question.
