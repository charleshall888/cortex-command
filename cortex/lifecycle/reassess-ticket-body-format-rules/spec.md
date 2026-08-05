# Specification: reassess-ticket-body-format-rules

## Problem Statement

Two ticket-body governance defects were confirmed by research, and one presumed defect was disproved. The confirmed defect: `skills/backlog-author/SKILL.md:13` and `:21` carry a citation ban (no `path:line` / `§N` / code fences outside `## Touch points`) whose enforcing lint — the LEX-1 prescriptive-prose scanner — was retired in `e3aef4e5`, leaving zero enforcement since; `tests/test_backlog_author.py`'s module docstring still advertises a `test_lex1_rejects_code_block_in_why_section` that does not exist, which is *why* the dead rule went unnoticed. Corpus measurement of the ban's effect was inconclusive — underpowered and confounded, with contradictory signs across two repos (cells of 17–29) — so the case for removal rests on zero enforcement, not on a demonstrated null. The disproved defect: the five-section template does not degrade ticket quality, and removing `## Why`/`## Role` would silently re-open closed bug #375. Settling that surfaced a governance gap — **deletion bias**, read literally, presumes removal for any surface that cannot show a completion-rate advantage, which no prose surface can under any available proxy. This spec retires the dead rule and scopes the principle so that presumption attaches where it belongs.

**Scope of the fix, stated precisely.** R3 governs *when the presumption of removal attaches*. It does not, and cannot, protect prose content that no consumer reads — critical review confirmed that `cortex/requirements/` prose (including the Deletion bias paragraph itself) and ADR decision bodies have no content-level consumer, only heading-name, path-bullet, and citation-token checks. Those surfaces remain outside the discharge mechanism; R3 makes no claim to rescue them. What it does is stop a *machine-consumed* surface from being presumed deletable merely because its value is unmeasurable.

## Phases

- **Phase 1: Retire the dead citation ban** — delete the unenforced rule and the stale docstring that concealed it.
- **Phase 2: Scope deletion bias** — record the build-failure discharge rule and its worked example in the canonical statement.

## Requirements

1. **Delete the citation ban from the shipped skill**: remove the prose in `skills/backlog-author/SKILL.md:13` forbidding `path:line`/`§N` citations and code fences outside `## Touch points`, and the dependent sentence at `:21` routing such citations into `## Touch points`. The five heading names on `:13` and all five section bullets (`:15-19`) are retained verbatim. Acceptance: `grep -ciE 'path:line|§N|fenced code' skills/backlog-author/SKILL.md` returns `0`; `grep -c '^- \*\*`## ' skills/backlog-author/SKILL.md` returns `5`; `uv run pytest tests/test_backlog_author.py` passes. **Phase**: Retire the dead citation ban

2. **Correct the stale test docstring**: `tests/test_backlog_author.py`'s module docstring names `test_lex1_rejects_code_block_in_why_section` and `test_interview_mode_routes_through_askuserquestion`; neither function exists. The docstring must describe only functions present in the file. Acceptance: the set of test names in the module docstring equals the set returned by `uv run pytest tests/test_backlog_author.py --collect-only -q` (currently 3). **Phase**: Retire the dead citation ban

3. **Record the build-failure discharge rule** in `cortex/requirements/project.md`'s **Deletion bias** paragraph. The rule to record, in substance:
   - Deletion bias presumes removal for a surface with **no consumer that fails on its removal**.
   - The presumption is discharged two ways: (i) a consumer that **turns a build or gate red** when the surface is removed — not a report-only or manually-invoked script; or (ii) a **filed bug recording observed failure, not a hypothetical** (the qualifier already in force at `CLAUDE.md:34` and `project.md:23`).
   - Discharge holds **only while its consumer holds**; a discharging consumer is itself subject to deletion bias, per `project.md:25` ("a defense retained without named evidence is complexity too"). It is not a permanent exemption.
   - Where discharged, the surface is weighed on the merits rather than presumed deletable.

   Acceptance: (a) `grep -c '#375' cortex/requirements/project.md` returns ≥1 and the Deletion bias paragraph is the match's section; (b) the addition is ≤4 sentences, verifiable by reading the paragraph; (c) `Interactive/session-dependent: whether the recorded prose states the rule faithfully — including which branch carries the presumption — is a judgment no string match can make, as critical review demonstrated by constructing an inverted restatement that passed every token check.` **Phase**: Scope deletion bias

4. **Record why `## Why`/`## Role` are retained**: `cortex_command/backlog/load_parent_epic.py`'s `INTENT_SECTIONS` tier is a live consumer, and closed bug #375 documents observed harm when it returns empty. Note explicitly that the discharge runs through **#375's observed failure**, not through `tests/test_load_parent_epic.py` — that suite sets `CORTEX_BACKLOG_DIR=tmp_path` and therefore cannot fail on real-corpus drift. Acceptance: (a) `cortex/requirements/project.md` contains `load_parent_epic.py` and `#375` (true); (b) the note is ≤2 sentences; (c) it lands in `cortex/requirements/project.md`, never in `skills/` (`CLAUDE.md:33-34`). **Phase**: Scope deletion bias

5. **Mirror parity holds**: `plugins/cortex-core/skills/backlog-author/SKILL.md` matches the canonical source after commit. Acceptance: `diff skills/backlog-author/SKILL.md plugins/cortex-core/skills/backlog-author/SKILL.md` is empty; mirrors are produced by `.githooks/pre-commit` Phase 3 from staged blobs, never staged by hand. **Phase**: Retire the dead citation ban

## Non-Requirements

- **No change to the five sections.** `## Why`/`## Role` are discharged by #375's observed failure. The supporting measurement, stated with its scope: of epics *served by the Why/Role tier*, 9/9 in cortex-command and 7/7 in wild-light degrade to `(no body content)` on removal — 16 of 59 total epics (27%), not 16 of 16. Separately, 11 of 24 wild-light epics (46%) already return the placeholder today for unrelated reasons.
- **`## Integration` and `## Edges` are not touched here.** No consumer fails on their removal and no filed bug records harm, so under R3 their presumption of removal stands — they remain legitimately deletable. Applying that is separate work.
- **No heading-agnostic extraction tier for `load_parent_epic`, and no de-fixturing of `tests/test_load_parent_epic.py`.** R3 makes the need sharper — the test cannot discharge anything while it is `tmp_path`-isolated — but building it is the gating precondition for a *future* structural change (research Q6), and nothing here changes a section.
- **The CLAUDE.md front-door evidence bar is not reopened.** #409 settled its carrier (`a86bd4c3`).
- **No new lint replaces the retired LEX-1 scanner.** `project.md:41` requires a gate to name its evidenced failure; none exists here.
- **R3 does not extend protection to content no consumer reads.** ADR decision bodies and `cortex/requirements/` prose have only heading/path/token-level consumers; they stay outside the discharge mechanism. Whether they need one is a separate question this spec does not answer.
- **The `Context from discovery` / `Scope` / `Research Context` second-template overlap is not reconciled.** Real (95/75/44 tickets) but a discovery-skill concern.
- **`decompose.md`'s merged-body lockstep dependency is not exercised.** `skills/discovery/references/decompose.md:23` (ADR-0007-backed) names the five sections as merge targets and needs a lockstep prose edit under any section change; moot here because this spec changes no section.
- **`## Promoted from`'s sole-linkage fragility is not addressed.** `skills/discovery/SKILL.md:51` makes this body section the only linkage, with nothing parsing or testing it — a discovery-skill defect warranting its own ticket.
- **`SECTION_PRIORITY` staleness is not touched.** `load_parent_epic.py:63-67` names three headings no current skill emits, though 95 tickets carry `## Context from discovery` in the exact casing required — legacy-served, not dead.

## Edge Cases

- **The citation ban shares line 13 with the five heading names.** A careless deletion takes the headings with it, and `tests/test_backlog_author.py:76` asserts all five are present. Expected: the test fails loudly and the edit is corrected — the one guardrail that does fire.
- **`## Touch points` loses its stated rationale.** Expected: `:21` is removed entirely, not edited to point elsewhere; the `:19` bullet stands on its own.
- **Someone armors a surface with a report-only script to manufacture discharge.** Expected: fails. R3 (ii) requires a consumer that turns a build or gate red; `cortex_command/adr_citation_audit.py` ("Report-only: exits 0 on every path", invoked only by a manual `justfile:471-472` recipe) is the worked counter-example of a consumer that does *not* discharge.
- **Someone files a bug at trim-proposal time to manufacture discharge.** Expected: fails. R3 requires *observed* failure, not a hypothetical — the same qualifier `CLAUDE.md:34` already applies at the front door.
- **A discharging consumer is itself unearned.** Expected: it faces deletion bias on its own terms; discharge is not a permanent exemption, and removing the consumer restores the presumption on what it discharged.
- **A future contributor re-adds a citation rule** unaware it was retired. Expected: R3/R4's project.md note records the rationale so the next trim pass finds it.
- **`just ratchet-refs` is not needed.** `skills/backlog-author/references/` holds only `size-pin.txt`, pinned at `0`.
- **The L1 surface ratchet only lowers.** `SKILL.md:3`'s `description` is unchanged, so the 288-byte baseline at `tests/test_l1_surface_ratchet.py:55` is unaffected.

## Changes to Existing Behavior

- **REMOVED** — `skills/backlog-author/SKILL.md`: the citation ban (`:13` second sentence) and the citation-routing sentence (`:21`). Effect: authors may cite `path:line` in `## Why`, which ~46% of recent cortex-command tickets already do.
- **MODIFIED** — `tests/test_backlog_author.py`: module docstring corrected to describe only extant tests.
- **MODIFIED** — `cortex/requirements/project.md`: Deletion bias paragraph gains the discharge rule (≤4 sentences) and the `## Why`/`## Role` retention note (≤2 sentences).
- **MODIFIED (generated)** — `plugins/cortex-core/skills/backlog-author/SKILL.md`, rebuilt by the pre-commit hook.

## Technical Constraints

- Edit canonical sources only; `.githooks/pre-commit` Phase 3 rebuilds `plugins/cortex-core/` from staged blobs and folds mirrors into the commit. Expect commit contents you did not name.
- `skills/` edits are lifecycle-gated (`CLAUDE.md`); this lifecycle is that gate.
- Repo-governance prose must not enter `skills/` or `plugins/` (`CLAUDE.md:33-34`, `project.md:23`). R3 and R4 land in `cortex/requirements/project.md` only.
- `project.md` loads on every Clarify, so R3+R4 are capped at **≤6 sentences combined**. This is a sentence cap, not a byte cap — it bounds count, not length, so the implementer must also avoid compound run-on construction. Prefer plain phrasing over mandated vocabulary.
- R3+R4 must read as part of the existing Deletion bias paragraph, not as an appended block. That paragraph already states "the burden of proof sits on keeping, not deleting"; the addition must not restate it.
- `SKILL.md` is 21 lines against a 500-line cap; all size gates pass in the shrinking direction.

## Open Decisions

None. Research Q2 (the rising-adoption confound in the completion comparison) is unresolved and now explicitly non-load-bearing: the Problem Statement no longer asserts a null result, and R1 rests on zero enforcement alone.

## Proposed ADR

None considered — but the reasoning is narrower than an earlier draft claimed. `cortex/adr/README.md`'s gate requires all three criteria. Criterion 3 (a real trade-off, credible alternative rejected for stated reasons) **is** met: research Q3 framed presumption-vs-weighing as an open fork. Criterion 1 is not: reversal means editing one paragraph, and no call site, data format, or external contract depends on it — trim decisions made under the rule are individually revisitable, not a coordinated migration. Note that `a86bd4c3` is **not** precedent for this: that commit corrected #409's *carrier* (moving prose out of the shipped template), not a scope redefinition, and an earlier draft of this spec misread it.
