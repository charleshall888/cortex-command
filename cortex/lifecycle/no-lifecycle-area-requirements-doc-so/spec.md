# Specification: no-lifecycle-area-requirements-doc-so

## Problem Statement

The lifecycle state machine is the largest subsystem in this repo and the one `/cortex-core:refine` and `/cortex-core:build` exist to drive, yet it has no area requirements doc. Two distinct costs follow. First, seven lifecycle ADRs are recorded in `cortex/adr/` and cited in the requirements corpus **nowhere**, verified by grep returning 0 hits each in `project.md`. Four are `status: accepted` (`0010`, `0012`, `0017`, `0030`) and are a genuine coverage gap in ratified doctrine. Three are still `status: proposed` (`0018`, `0020`, `0022`) — landed 2026-06-29/06-30 and never promoted — and are a *visibility* gap in decisions still under review, not ratified doctrine; per `cortex/adr/README.md:62` a consumer "MUST NOT automatic-ally treat a `proposed` or `deprecated` ADR as binding." Second, the `## Conditional Loading` row #454 landed can never resolve: the loader treats all text right of the `→` as the path and existence-checks it verbatim, so the row's `(NOT YET WRITTEN — …)` parenthetical is part of the path. Verified executably — with a real `lifecycle.md` on disk the loader still printed `(skipped: file absent)`. That same row also silenced the `no area docs matched` warning (stderr is now 0 bytes for a lifecycle-tagged feature), so the gap is currently invisible rather than merely unclosed. The beneficiary is every lifecycle ticket's Specify and Review phase, which today assess against `project.md` alone.

## Phases

- **Phase 1: Reachable doc** — author `cortex/requirements/lifecycle.md` and make the routing row resolve to it.
- **Phase 2: Relocation and guard** — move the uncontested lifecycle-only material out of `project.md` behind pointer stubs, and add the regression guard that would have caught #454's unresolvable row.

Phase 1 is independently shippable and closes the reachability defect on its own; every Phase 2 requirement depends on Phase 1 (R6 needs R1's file to point at, R8 needs R6, R9 needs R2's corrected row or it starts red). The split is a dependency ordering, not a stop-gap.

## Requirements

1. **`cortex/requirements/lifecycle.md` exists and conforms to the area template.** Acceptance: `python3 -m cortex_command.lifecycle.validate_requirements_doc_cli --scope area --path cortex/requirements/lifecycle.md` emits `{"state": "pass", ...}` with `"missing": []`. The file opens with `# Requirements: lifecycle`, a `> Last gathered: 2026-08-07` line, and the verbatim backlink `**Parent doc**: [requirements/project.md](project.md)`. **Phase**: Reachable doc

2. **The routing row is a bare path and the loader resolves it.** Acceptance: the `## Conditional Loading` line in `cortex/requirements/project.md` ends with `→ cortex/requirements/lifecycle.md` and nothing after it; `cortex-load-requirements --feature no-lifecycle-area-requirements-doc-so` prints `cortex/requirements/lifecycle.md` on stdout **without** the ` (skipped: file absent)` suffix. Grounding: `cortex_command/lifecycle/load_requirements_cli.py:_parse_conditional_loading`, `resolve`. **Phase**: Reachable doc

3. **The doc cites the seven previously-uncited lifecycle ADRs, each with its status honoured.** Acceptance: `grep -c` for each of `0010`, `0012`, `0017`, `0018`, `0020`, `0022`, `0030` in `cortex/requirements/lifecycle.md` returns ≥1. **Status discipline is binding, not stylistic**: the four accepted ADRs (`0010`, `0012`, `0017`, `0030`) may be described with "ratifies"; the three proposed ones (`0018`, `0020`, `0022`) MUST NOT be — they are described as *proposed and not binding*, because `cortex/adr/README.md:62` states a consumer "MUST NOT automatic-ally treat a `proposed` or `deprecated` ADR as binding." Additional acceptance: for each of `0018`, `0020`, `0022`, the line citing it in `lifecycle.md` contains the substring `proposed`, and `grep -n '0018\|0020\|0022' cortex/requirements/lifecycle.md | grep -c 'ratif'` returns 0. Re-check each ADR's `status:` frontmatter at build time rather than trusting this list — any of the three may have been promoted since 2026-08-07. Grounding: `cortex/adr/`, `cortex/adr/README.md:47,62`. **Phase**: Reachable doc

4. **The doc states its boundary against the docs that already own adjacent surfaces.** Acceptance, both runnable and expected to pass once R1 lands: `grep -c 'cortex/requirements/observability.md' cortex/requirements/lifecycle.md` returns ≥1, and `grep -c 'cortex/requirements/pipeline.md' cortex/requirements/lifecycle.md` returns ≥1 — each occurrence must sit in a sentence attributing statusline/dashboard narration of lifecycle phase to the former and the session-level state machine (`planning → executing → complete`) plus feature-status vocabulary (`pending → running → merged`) to the latter (a bare citation without the attribution does not discharge this). Grounding: `cortex/requirements/observability.md:13-39`, `cortex/requirements/pipeline.md:13-29`. **Phase**: Reachable doc

5. **The doc points at `glossary.md` for shared vocabulary rather than restating it.** Acceptance — presence: `grep -Fc 'cortex/requirements/glossary.md' cortex/requirements/lifecycle.md` returns ≥1. Acceptance — absence (genuine negative, kept vacuous until R1 creates the file): each of `grep -Fc '(simple / moderate / complex)' cortex/requirements/lifecycle.md`, `grep -Fc '(low / medium / high / critical)' cortex/requirements/lifecycle.md`, and `grep -Fc 'criticality ∈ {high, critical} OR tier == complex' cortex/requirements/lifecycle.md` returns 0. Rationale: `glossary.md` is in `## Global Context` and already loads unconditionally, so a second copy in a conditionally-loaded doc is strictly worse. Grounding: `cortex/requirements/glossary.md:7-9`, `project.md` `## Global Context`. **Phase**: Reachable doc

6. **Exactly seven `project.md` items relocate, each leaving a one-line pointer.** Acceptance, mechanical, per identifying phrase in {`Multi-step lifecycle phases`, `Kept user pauses are a marked taxonomy`, `Phase boundaries are session boundaries`, `Served lifecycle verb class`, `` Consumer `EnterWorktree` authorization surface ``, `The reviewer brief is a protocol-governed served surface`, `Override-reason clause vocabulary`}: `grep -F "<phrase>" cortex/requirements/project.md` returns exactly one line; that line contains the substring `cortex/requirements/lifecycle.md`; and `grep -F "<phrase>" cortex/requirements/project.md | wc -c` reports ≤200. The removed detail appears in `lifecycle.md`. **Phase**: Relocation and guard

7. **Five contested items stay in `project.md` in full.** Acceptance: `project.md` still contains the complete text of the bullets currently at lines 38 (`Critical-review gates at spec only`), 40 (`The short road`), 59 (`Lifecycle identity is the canonical slug`), 61 (`Lifecycle phase vocabulary`), and 65 (`The lifecycle events corpus is mixed-format`). Rationale: 40 duplicates `glossary.md`, which loads unconditionally; 59, 61, and 65 carry normative clauses with real cross-area readers and would go dark for any feature whose tags miss the trigger. Line 38 is genuinely split between the two areas — "the adversarial review gate runs on the spec" is lifecycle, "Reviewer width is 1–2, weighted toward 2" is dispatch policy — and `multi-agent.md` does **not** cover it today (`grep -i 'critical-review\|reviewer width\|spec only' cortex/requirements/multi-agent.md` returns zero hits, verified). Splitting a 282-byte bullet across two docs buys nothing, so it stays in `project.md`, where both audiences load it unconditionally. Relocating it to `multi-agent.md` is a defensible separate change; it is not proposed here. **Phase**: Relocation and guard

8. **`project.md` shrinks measurably and the figure is recorded.** Acceptance: `wc -c cortex/requirements/project.md` reports a value at least 3,000 bytes below the pre-change 29,918, and the commit body or `lifecycle.md` records the measured before/after. Expected: ~29,918 → ~26,450, a ~11.6% net shrink (4,370 bytes relocated, ~909 returned as stubs — measured from seven drafted stubs of 124–138 bytes each, not estimated). **Phase**: Relocation and guard

> **Who pays and who benefits.** The front-door evidence bar requires the net effect on the shrunk surface, and it is not uniform. Today every feature loads `project.md` (29,918 B) + `glossary.md` (1,176 B) = 31,094 B. After this change, the ~82% of features that are not lifecycle-tagged load 27,424 B — **3,670 B less**. Lifecycle-tagged features load roughly 33,400–36,400 B — **2,330 to 5,330 B more**, in exchange for the area content they need and the seven ADRs recorded nowhere today. The shrink's beneficiary is therefore the non-lifecycle majority, not this ticket's nominal audience. That is the honest trade and it is accepted deliberately.

9. **A regression test pins that every `## Conditional Loading` path resolves.** The test MUST read the repo's real `cortex/requirements/project.md` — a `tmp_path` fixture cannot catch this defect. `tests/test_refine_session_ownership.py:240-251` already writes a synthetic `project.md` under `tmp_path` and is therefore **not** a discharge of this requirement. Acceptance, by mutation rather than by grep: with the test in place, append ` (annotation)` to the lifecycle row in the real `project.md` and confirm the test goes **red**; revert and confirm it goes green. Named failure it prevents (per `project.md:41`'s rule that a new gate enters only with its named failure stated): #454 shipped a routing row whose path could never resolve, and no test could see it. **Phase**: Relocation and guard

> **Criteria that do not fail at HEAD, by design.** R7 is a *preservation* criterion — it passes on the unmodified repo (verified: 5/5 bullets present) and exists to catch the build over-relocating. R5 is a negative assertion that is vacuous until R1 creates the file. Every other criterion was run against HEAD and fails there as expected.

## Non-Requirements

- **Fixing the tag-matching miss rate.** Backlog #472 owns the selection mechanism (measured 72% of lifecycles loading `project.md` only). This spec does not change `_read_tags`, the `areas:`/`tags:` field mismatch, or substring matching.
- **Widening the trigger text.** `review`, `plan`, and `build` carry substring false-positive risk with no word-boundary protection; `state-machine` is safe but low-value alone. Deferred to #472, which may replace the matcher outright.
- **Extending the reference-size ratchet to `cortex/requirements/`.** The area doc has no size brake (no token budget, not ratcheted, validator not CI-wired) and §3a auto-appends to it on detected drift. Real, but no observed runaway growth yet — adding the brake now would fail the same evidence bar this ticket is held to. Recorded as a known exposure, not built.
- **Routing the doc through `## Global Context` instead of `## Conditional Loading`.** Considered and rejected. Listing it in Global Context would load it unconditionally, which would fix both the miss rate and the go-dark risk outright and make R7 unnecessary. Rejected as disproportionate: it taxes every dashboard, remote-access, and backlog ticket forever, contradicting the loader's stated purpose of "avoiding both under-loading … and over-loading" (`load_requirements_cli.py:8-10`) and `project.md`'s token-economy clause. `glossary.md` earns that slot by being ~9 lines of universal vocabulary; a 10 KB governance doc does not.
- **Writing area docs for the other undocumented areas.** `skills` (133 tickets), `hooks`, `docs`, `tests`, `install`, and `requirements` have none. No stated principle exists for when an area earns a doc; establishing one is out of scope.
- **Making `review.md`'s warning fire on a `(skipped: file absent)` entry.** Related and arguably the deeper fix, but it is a change to the review skill's warning contract, not to the requirements corpus.

## Edge Cases

- **A future ticket edits `resolve.py` tagged only `slug-resolution`**: it will not match the lifecycle trigger, so it must still see the `MUST be retained` clause — which is why R7 keeps line 59 in `project.md`. Expected behavior: the clause loads unconditionally, as today.
- **An `observability`-tagged ticket touches `phase_labels.py` or an events.log parser**: it matches `observability.md`, so `review.md`'s boolean no-match warning stays silent while lifecycle content never loads. Expected behavior: R7 keeps 61 and 65 in `project.md` so the content still arrives; the residual gap is recorded in Open Decisions.
- **The validator is run against the new doc before it has real content in a section**: `## Non-Functional Requirements`, `## Dependencies`, and `## Edge Cases` may be genuinely thin. Expected behavior: a short honest line ("None beyond the project-level bar") — the validator checks H2 presence only, so this passes without invented content.
- **A reviewer auto-appends drift into `lifecycle.md`**: §3a appends `Content` at the end of a named section. Expected behavior: succeeds; the doc grows with no brake. Accepted per Non-Requirements.
- **A stub in `project.md` points at a section later renamed in `lifecycle.md`**: nothing validates cross-doc pointer targets. Expected behavior: stubs name the constraint, not a section anchor, so a rename cannot break them.
- **`cortex init` scaffolds a consumer repo**: `cortex_command/init/scaffold.py` copies requirements templates. Expected behavior: unchanged — this adds a repo-local area doc, not a template.

## Changes to Existing Behavior

- **ADDED**: `cortex/requirements/lifecycle.md`.
- **ADDED**: a `tests/` regression test asserting every `## Conditional Loading` path resolves.
- **MODIFIED**: `cortex/requirements/project.md` — the lifecycle routing row becomes a bare path; seven bullets shrink to pointer stubs.
- **MODIFIED**: what a lifecycle-tagged feature loads. Today it gets `project.md` + `glossary.md`; after this it also gets `lifecycle.md`. Net context per lifecycle load rises by roughly the doc's size minus the 4,370 relocated bytes.
- **REMOVED**: nothing.

## Technical Constraints

- The loader splits `## Conditional Loading` bullets on the **first** U+2192 and existence-checks all text to its right verbatim — so the row must carry a bare path with no trailing annotation (`load_requirements_cli.py:_parse_conditional_loading`).
- Tag matching is ASCII-casefold substring, tag-in-trigger; a longer trigger matches strictly more tags.
- Area docs require seven H2s verbatim; the validator checks H2 presence only and is **not** wired into any hook or CI (`skills/requirements/SKILL.md:55-67`).
- `## Architectural Constraints` is specified as "strategic constraints only; operational detail lives in `CLAUDE.md`" — relocated items must not smuggle runbook detail.
- `project.md` is emitted unconditionally on line 1 of every load; an area doc only on a trigger match. This asymmetry is the reason R7 exists.
- Editing `cortex/requirements/` is not lifecycle-gated by `CLAUDE.md`, but the new `tests/` file is ordinary repo code and must pass `just test`.

## Open Decisions

- **Whether `review.md`'s no-match warning should also fire on a `(skipped: file absent)` entry.** Deferred: the fix belongs to the review skill's warning contract and needs implementation-level knowledge of how the reviewer prompt consumes the path list, which is not obtainable without writing that change.

## Proposed ADR

None considered. The two decisions with real trade-offs — keeping five contested bullets in `project.md` (R7) and declining to widen the trigger — are both recorded in this spec with rationale, and neither is hard to reverse: each is a text edit to a single file with no consumer contract attached.
