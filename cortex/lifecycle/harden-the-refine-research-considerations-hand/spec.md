# Specification: harden-the-refine-research-considerations-hand (#337)

## Problem Statement

`/cortex-core:refine` hands Apply'd clarify-critic alignment findings to `/cortex-core:research` through a `research-considerations="<multi-line bullets>"` argument that research parses from its model-read `$ARGUMENTS` string. Because the *value* is multi-line free text inside a quoted arg, it cannot safely contain `=` or `"`, forcing both skills to carry character-stripping prose (refine's "Strip or paraphrase away any embedded `=` or `"`"; research's "Embedded `=` and `"` characters are not supported"). This feature moves the considerations *text* onto a file channel that handles arbitrary multi-line content without escaping, passing only a benign file *path* in the argument. The escaping caveats are deleted; in their place the channel relies on a small set of **tested** producer disciplines (write-and-arg coupled in one step, overwrite-never-append, write-before-dispatch) — so this is an honest *trade* of an escaping caveat for structurally-enforced, test-guarded write semantics, not a free reduction. The beneficiary is every refine→research run: a clean, escaping-immune hand-off whose correctness is verified rather than assumed.

## Phases

- **Phase 1: Migrate the hand-off channel** — both SKILL.md endpoints swap value-arg → file+coupled-path-arg, drop the escaping caveats, couple the write to the arg emission and sequence it before the dispatch, gitignore the transient file, regenerate the mirror; ships with the discriminating prose-contract tests AND the inject-content-not-path guard (the guard for a Phase-1 behavior must ship in Phase 1).
- **Phase 2: Structural test hardening + decision record** — register the hand-off field in the schema fixture, add the gitignore-template test case, and record ADR-0022.

## Priority (MoSCoW)

- **Must-have (Phase 1, R1–R11)**: the channel migration, its discriminating prose-contract tests, AND the inject-content-not-path guard (R6) are the feature. R6 guards R4 (a Phase-1 behavior — research reading-then-injecting), so it ships in Phase 1, not later. Shipping the behavioral change without the escaping-caveat removal, the coupled file+arg channel, write-before-dispatch ordering, the content-not-path guard, the gitignore rule, the regenerated mirror, or the behavioral tests would be incomplete or unguarded.
- **Should-have (Phase 2, R12–R14)**: structural test hardening that locks the contract against future drift — handoff-schema registration (R12), the gitignore-template test case (R13) — and ADR-0022 (R14). High value (they stop the channel being re-litigated a fourth time) but the migration is correct and guarded without them, so they are a distinct, lower-urgency phase.
- **Won't-do**: see Non-Requirements.

## Requirements

1. **Refine writes the considerations file and emits the path arg as one coupled step.** In `skills/refine/SKILL.md` the Alignment-Considerations Propagation block, **fired only when ≥1 Apply'd alignment finding exists**, performs a single coupled action: it writes the Apply'd considerations (unchanged newline-delimited bullet format) to `cortex/lifecycle/{lifecycle-slug}/research-considerations.md` **overwriting (never appending)**, and the same `/cortex-core:research` dispatch carries `research-considerations-file=cortex/lifecycle/{lifecycle-slug}/research-considerations.md`. The arg is **never emitted without a same-step fresh write** (this is what makes a stale prior-run read structurally impossible — see Edge Cases). When no Apply'd findings exist, the block performs neither the write nor the arg emission. Acceptance: `grep -c "research-considerations-file" skills/refine/SKILL.md` ≥ 1 AND `grep -c 'research-considerations="' skills/refine/SKILL.md` = 0 AND a prose-contract test asserts the propagation block contains an explicit file-**write** instruction targeting `research-considerations.md` with overwrite (not append) wording. **Phase**: Migrate the hand-off channel

2. **Refine's escaping caveat is removed.** The "Strip or paraphrase away any embedded `=` or `"`" prose is gone. Acceptance: `grep -c "Strip or paraphrase away" skills/refine/SKILL.md` = 0 AND the `### Alignment-Considerations Propagation` heading still exists (`grep -c "### Alignment-Considerations Propagation" skills/refine/SKILL.md` = 1, non-vacuity anchor). **Phase**: Migrate the hand-off channel

3. **The file write is sequenced before the dispatch.** The propagation block's write+arg step appears, in `skills/refine/SKILL.md`, before the `/cortex-core:research` invocation it feeds, so the path is valid when research reads it (no read-before-write). Acceptance: a prose-contract test asserts that the first line matching the unambiguous write anchor `research-considerations.md` appears at a smaller line index than the **fenced dispatch invocation** line `/cortex-core:research topic=` (the exact dispatch-line anchor, not the prose "Delegate to" mention or the other `/cortex-core:research` occurrences). Both anchor strings are pinned literals so the test is deterministic. **Phase**: Migrate the hand-off channel

4. **Research reads the file in its body and injects the content.** In `skills/research/SKILL.md` Step 1, `research-considerations-file` is a supported key replacing `research-considerations`; when present, **research's orchestrator body** reads that file and injects the file's **literal content** into the three mandatory core-angle prompts via the existing `{research_considerations_bullets}` placeholders (Codebase, Web, Requirements & Constraints). The injection points, per-angle applicability, and the `## Considerations Addressed` output section are behavior-unchanged. Acceptance: `grep -c "research-considerations-file" skills/research/SKILL.md` ≥ 1 AND the three `{research_considerations_bullets}` placeholders remain (`grep -c "research_considerations_bullets" skills/research/SKILL.md` = 3) AND a prose-contract test asserts Step 1 contains an explicit instruction that research **reads the file and substitutes its content** into the placeholder (not merely that the key was renamed). **Phase**: Migrate the hand-off channel

5. **Research's escaping caveat is removed.** The "Embedded `=` and `"` characters are not supported in the value" prose is gone. Acceptance: `grep -c "are not supported in the value" skills/research/SKILL.md` = 0 AND the Step 1 "Parse Arguments" heading still exists (non-vacuity anchor). **Phase**: Migrate the hand-off channel

6. **Inject content, never the bare path — guarded at the injection-prose level.** Because the file-read is new and the skill-path lint cannot catch a `cortex/lifecycle/...` path (D2 regex targets `references/`//`../`//`skills/`; D1 is dormant in `research/SKILL.md`), the content-not-path discipline must be enforced where it lives: the **injection instruction prose**, not the placeholder-only prompt code blocks (a grep of those blocks is vacuous — they contain only `{research_considerations_bullets}`). Acceptance: a prose-contract test, scoped to research's Step 1 + Considerations-injection section, asserts (positive) that the read-and-substitute instruction names **content/literal text** as what is injected, AND (negative control) that the injection prose does **not** instruct a subagent to read the file itself nor forward the `research-considerations-file` path/`.md` filename into the agent prompt. The negative control is red against a draft that tells subagents to read the path. **Phase**: Migrate the hand-off channel

7. **Absence = no injection, structurally — via coupling, no clear-discipline.** A stale prior-run file is never read because the arg is emitted only coupled to a same-step fresh write (R1); the no-findings path emits neither. Research injects only when the arg is present AND the file is non-empty, so even a propagation misfire injects empty (not stale) content — matching the old value-arg's failure mode. No "clear/truncate each run" discipline is introduced. Acceptance: a prose-contract test asserts refine's block retains conditional-fire + coupling language (the arg is emitted only alongside a same-step write, only when findings exist) AND contains no "clear … each run"/"truncate … each run" instruction. (This is a **preservation + negative-control** test, not red-before-green — see R11.) **Phase**: Migrate the hand-off channel

8. **Standalone research reads nothing.** Standalone mode (no `lifecycle-slug`, hence no `research-considerations-file` arg) injects no considerations. Acceptance: a prose-contract test asserts research's standalone-mode path does not read a considerations file (the read is conditioned on the arg/lifecycle mode). (This is a **negative-control** test — vacuously green today because research reads no file at all; it guards against a future unconditional read — see R11.) **Phase**: Migrate the hand-off channel

9. **Gitignore the transient considerations file.** Add `lifecycle/**/research-considerations.md` to `cortex_command/init/templates/cortex/.gitignore` and to this repo's `cortex/.gitignore`, joining the existing lifecycle transient-file family (the `**` covers active and archive depth). Acceptance: `grep -c "lifecycle/\*\*/research-considerations.md" cortex_command/init/templates/cortex/.gitignore` = 1 AND `git check-ignore cortex/lifecycle/_probe/research-considerations.md` exits 0 against an untracked probe path. **Phase**: Migrate the hand-off channel

10. **Mirror regenerated and byte-identical.** `plugins/cortex-core/skills/{refine,research}/SKILL.md` regenerated via `just build-plugin`. Acceptance: `.venv/bin/pytest tests/test_dual_source_reference_parity.py` exits 0. **Phase**: Migrate the hand-off channel

11. **Behavioral prose-contract tests added (Phase 1).** New `tests/test_*` (modeled on `tests/test_refine_skill.py`'s anchored-slice + negative-regression pattern). Classify honestly:
    - **Red-before-green** (the strings change with the migration): R2 (refine caveat removed), R5 (research caveat removed), R1 (write-instruction + overwrite wording present; old `research-considerations="` absent), R4 (read-and-substitute-content instruction present), R3 (write anchor precedes the dispatch anchor), R6 (negative control: no path-forward/subagent-read directive).
    - **Preservation / negative-control** (green today, guard against regression): R7 (conditional-fire + coupling retained; no clear-discipline), R8 (standalone reads nothing).
    Acceptance: `just test` exits 0 with the new tests collected; the red-before-green tests fail against the unmodified files. **Phase**: Migrate the hand-off channel

12. **Hand-off field registered in the schema fixture.** Add `{name: research-considerations-file, producer: refine, consumers: [research]}` to `tests/fixtures/skill_handoff_schema.yaml` so `tests/test_skill_handoff.py` enforces the token in both skills' prose (its existing `pytest.raises` fixture is the built-in negative control). Acceptance: `.venv/bin/pytest tests/test_skill_handoff.py` exits 0. **Phase**: Structural test hardening + decision record

13. **Gitignore-template test case added.** Add a `_IGNORED` case for `research-considerations.md` (active and archive depth) to `cortex_command/init/tests/test_cortex_gitignore_template.py`. Acceptance: `.venv/bin/pytest cortex_command/init/tests/test_cortex_gitignore_template.py` exits 0. **Phase**: Structural test hardening + decision record

14. **ADR-0022 recorded.** Write `cortex/adr/0022-*.md` recording the explicit-path-arg decision, the rejected alternatives (implicit slug-derived file; full argument removal), and the coupling/absence-semantics rationale; back-point both SKILL.md edits to it rather than restating the body. Acceptance: a file matching `cortex/adr/0022-*.md` exists AND `just test` passes ADR-related gates (`tests/test_lifecycle_references_resolve.py` and the ADR-citation audit). **Phase**: Structural test hardening + decision record

## Non-Requirements

- Does NOT change the considerations value **format** (newline-delimited bullets) or the per-angle **injection points** (Codebase / Web / Requirements & Constraints core angles only) — behavior-identical.
- Does NOT change the `## Considerations Addressed` output trigger (still emitted when considerations were non-empty AND lifecycle mode).
- Does NOT introduce a new CLI verb. The producer disciplines (couple write+arg, overwrite-never-append, write-before-dispatch) are expressed in SKILL.md prose and guarded by tests, not by a new `cortex-refine` verb — coupling makes the absence-semantics structural without one.
- Does NOT commit the considerations file to git, nor register it in `index.md` — it is a transient *input* to a single research dispatch, not a phase deliverable.
- Does NOT alter clarify-critic alignment-finding production. This change is purely the transport channel; the producer side is untouched.
- Does NOT add an unconditional clear/truncate-each-run discipline (Approach A's central cost). Coupling, not clearing, is what keeps absence structural.

## Edge Cases

- **No Apply'd findings (or all Dismissed)**: the propagation block does not fire; refine writes nothing and emits no arg; research injects nothing; any stale on-disk file from a prior run is never read (reading requires the arg, which is never emitted here).
- **Propagation misfire (arg emitted with empty/zero considerations)**: because the arg is coupled to a same-step write, refine writes this-run's (empty) considerations; research reads empty → no injection. A misfire injects empty, not stale content — the same failure mode as the old value-arg.
- **§2a loop-back**: considerations derive from Clarify-stage dispositions, not the interview that changed, so they are invariant; the propagation block re-fires on re-entry, re-writing identical content and re-emitting the coupled arg — never stale.
- **`resume=research` branch (Clarify skipped)**: no clarify-critic → no findings → propagation block does not fire → no write, no arg → research does not read; a stale on-disk file from a prior full run is never referenced. (This is the path Approach A would have read stale; Approach B's coupling makes it safe.)
- **Within-run read-before-write**: eliminated structurally — the write is part of the propagation step that precedes the dispatch in refine's sequential control flow (R3), and the inline, single-threaded execution means the Write completes before the dispatch turn begins.
- **Present-but-empty / whitespace-only file**: research treats it as no-injection, so a degenerate write cannot inject a blank `### Considerations` section.
- **Slug collision** (lifecycle slug is a lossy truncated prefix of the backlog filename): two items sharing a slug share the file — a pre-existing lifecycle-dir hazard (`research.md`/`spec.md` already collide) that the new file inherits and does not worsen; coupling still guarantees a same-run overwrite before any read.
- **Existing repos without the new gitignore rule**: the file would be untracked there and could trip the dirty-tree gates until the repo re-syncs `cortex/.gitignore` — the documented `.gitignore`-template propagation limitation (see Technical Constraints).

## Changes to Existing Behavior

- **MODIFIED**: refine passes `research-considerations="<bullets>"` → writes `cortex/lifecycle/{slug}/research-considerations.md` and emits `research-considerations-file=<path>` coupled in one step.
- **MODIFIED**: research parses the `research-considerations` value key → the `research-considerations-file` path key and its body reads the file.
- **REMOVED**: the `=`/`"` escaping caveats in both skills.
- **ADDED**: `lifecycle/**/research-considerations.md` gitignore rule; ADR-0022; a registered `research-considerations-file` hand-off field in the test schema.

## Technical Constraints

- **SP001/SP002 + ADR-0009**: research must inject file **content**, never the bare path, into composed subagent prompts. The skill-path lint does not match a `cortex/lifecycle/...` path shape (D2 regex targets `references/`//`../`//`skills/`; D1 is dormant in `research/SKILL.md` — no subagent-prompt fences). The grep target for this guard is therefore the **injection-instruction prose** (R6), not the placeholder-only prompt code blocks, which a static grep cannot use to witness runtime substitution.
- **Mirror canonical-edit rule**: edit `skills/` only, run `just build-plugin`, commit canonical + mirror together; `tests/test_dual_source_reference_parity.py` and the pre-commit drift gate enforce parity.
- **Net prose-obligation trade (honest accounting)**: this change deletes two escaping caveats and adds three tested producer disciplines (couple write+arg, overwrite-never-append, write-before-dispatch) plus a defensive empty-file reader contract. The win is not "fewer caveats" — it is that the channel can no longer misparse arbitrary text and the remaining disciplines are test-guarded rather than relied on by prose alone.
- **Body-only prose change**: the L1 surface ratchet (refine 624B / research 379B, both cluster skills) and the SKILL.md size cap (refine 200 / research 244 lines vs. 500) are unaffected; parity, contract, and events-registry gates run on the edits but pass (no new `cortex-*` script, no new event).
- **`.gitignore`-template propagation**: the rule reaches new repos via the template; existing repos must re-sync `cortex/.gitignore` to pick it up (documented limitation in the template header).

## Open Decisions

- **ADR number 0022 is provisional.** The next free number is 0022 at spec time, but a concurrent lifecycle session could claim it before this lands; verify it is still free at implement/build time and bump to the next free number if taken. *Reason: ADR-number availability is a build-time fact that cannot be locked at spec time given concurrent sessions.*

## Proposed ADR

### Proposed ADR: 0022-explicit-path-arg-for-refine-research-considerations-handoff

**Context**: The refine→research alignment-considerations hand-off has been designed three times (original implementation, deferred in #322, decided here in #337). The fragility is that research parses an argument from its model-read `$ARGUMENTS` string, so a multi-line free-text *value* cannot carry `=`/`"`.

**Decision**: Carry the considerations *text* over a file (`cortex/lifecycle/{slug}/research-considerations.md`, gitignored) and emit only the file *path* in a `research-considerations-file` argument, **coupled** to a same-step fresh write and fired only when Apply'd findings exist. Research's body reads the file and injects its content into the core-angle prompts.

**Rejected alternatives**: (a) *Implicit slug-derived file* — research always reads in lifecycle mode, forcing a mandatory clear-each-run discipline (the very prose this ticket removes, merely relocated) and exposing the `resume=research` stale-file path; rejected. (b) *Full argument removal* — would require a CLI verb to make the write structural, adding ceremony for no benefit over a coupled explicit path arg.

**Trade-off and ADR-gate posture**: A benign path argument is retained (rather than a zero-argument interface), in exchange for an escaping-immune channel whose absence-semantics is kept structural by coupling the write to the arg. The change is mechanically easy to reverse, so the ADR's warrant rests primarily on the *surprising* leg (why keep an arg at all, and why coupling matters) and the *real-trade-off* leg (path-arg vs. zero-arg vs. implicit-file), reinforced by the decision having been re-litigated three times — recording it stops a fourth round. This is recorded as a borderline ADR on the hard-to-reverse criterion; the recording value is the dominant justification.
