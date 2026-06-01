# Specification: investigate-critical-review-telemetry-creating-phantom

> **Spike deliverable.** This spec is the decision artifact for #274: it records the confirmed root
> cause and the **recommended** fix shape (A+C, high confidence — see below), and carries an
> implementable plan so that if the operator chooses to land it, the Plan phase has a concrete target.
> Producing an implementable spec and taking the land-vs-defer call at the approval gate is the shape
> the operator selected ("decide at the spec gate"). tier=complex, criticality=high.

## Problem Statement

`/cortex-core:critical-review`'s telemetry writers (`check-synth-stable` → `synthesizer_drift`,
`check-artifact-stable`/`record-exclusion` → `sentinel_absence`) compute their events.log path as
`Path(lifecycle_root)/{feature}/events.log` and funnel through `append_event`, whose first line is an
unconditional `mkdir(parents=True, exist_ok=True)` (`cortex_command/critical_review/__init__.py:469`).
When critical-review runs on a **research-scoped** artifact (the discovery flow on
`cortex/research/{topic}/research.md`) and the orchestrator supplies a `--feature {topic}` — which the
design **documents should not happen** (`verification-gates.md:18,49,79` says the `<path>`-arg form
omits `--feature` and *skips* telemetry; the `_default_artifact_roots` docstring at `:529-538` states
this contract explicitly) — the write lands under `cortex/lifecycle/{topic}/`, creating a **phantom
lifecycle directory**: a dir holding only a telemetry event and no real artifacts. The SessionStart
scanner then surfaces it as a stale "research"-phase lifecycle on every session for 30 days. Observed
three times (`cortex-init-scope-reduction`, `doc-audit-2026-05-18`,
`swap-daytime-autonomous-for-worktree-interactive`), all archived. The contract that prevents this is
**prose-only**; this spec makes it **structural** at the write site, and adds a scanner-side backstop
so a telemetry-only artifact-less dir cannot nag the operator.

## Chosen approach (and the alternative considered)

**Recommended (high confidence): A (write-guard) + C (detection discriminator).** A structurally
enforces the already-documented "skip telemetry for non-feature reviews" contract at the write site;
C prevents a telemetry-only, artifact-less dir from surfacing as a lifecycle and is the executable
check that satisfies #255's "a change claiming structural value must ship a check" bar.

**Considered and rejected: B' (route research-scoped telemetry to `cortex/research/{topic}/events.log`).**
B' is structurally elegant (~15-20 lines, since `validate_artifact_path` already computes the matched
root and discovery already owns a research-topic events.log) but it *changes* the documented contract
to start persisting telemetry the design says to skip, for a consumer that is explicitly future
("future per-tier compliance audit", `bin/.events-registry.md:113-114`; zero current readers). The
project's recent trajectory (`critical-review-sentinel-gate-relax-first`) *relaxes* this telemetry's
enforcement, not the reverse.

**The single condition that flips A+C → B'** is the Open Decision below: make discovery-flow integrity
telemetry a *first-class consumed* signal. This is a genuine operator-override hook, surfaced
explicitly — **not** a sign the recommendation is unsettled. A+C is the committed recommendation;
implementation is gated on the operator's land-vs-defer + approach confirmation at the approval gate.

## Phases

- **Phase 1: Structural write-guard** — make the three telemetry writers suppress the dir-creating
  side effect when their target lifecycle dir does not already exist, mirroring the shipped
  `complexity_escalator.py` R11 guard; tighten the complementary prose so the `<path>`-arg/skip
  contract is unambiguous.
- **Phase 2: Detection-side discriminator + housekeeping** — suppress telemetry-only / artifact-less
  dirs from SessionStart enumeration via a content-based predicate built on the existing tolerant
  events.log reader; record the sibling-gate audit result; fix the stale events-registry code pointers.

## Requirements

> **Priority tiers.** **Must** (the load-bearing fix + green suite): Reqs 1, 2, 3, 5, 6, 7, 12.
> **Should** (complementary / housekeeping / mechanical, each genuinely required by repo
> parity/registry discipline but not load-bearing for the phantom fix): Reqs 4, 8, 9, 10, 11.

1. **[Must] Shared guard helper.** Add a single helper to `cortex_command/critical_review/__init__.py`
   (e.g. `_lifecycle_dir_exists(lifecycle_root, feature) -> bool`) returning whether
   `Path(lifecycle_root)/feature` is an existing directory. Carry a `# gate-class: hygiene` annotation
   at the guard site(s). Acceptance: `grep -c 'gate-class: hygiene' cortex_command/critical_review/__init__.py`
   ≥ 1 increase over baseline; `python3 -m pytest tests/test_critical_review_phantom_guard.py -q` exits 0.
   **Phase**: Phase 1.
2. **[Must] Write-guard is write-only and verdict-preserving.** The guard suppresses **only** the
   directory-creating side effect (the `mkdir` + events.log append) when `cortex/lifecycle/{feature}/`
   does not already exist. It MUST NOT alter the subcommand's integrity verdict or fabricate one: the
   exit code continues to reflect the genuine check result (a `synthesizer_drift`/`sentinel_absence`
   verdict is real and still surfaces; a clean check writes nothing regardless). Two correctness
   invariants the implementation must satisfy and a test must assert: (a) **no skipped write is
   observably indistinguishable from a real invalidation** — the orchestrator (which routes on exit
   code + stdout, per `verification-gates.md:54,84`) must be able to tell "skipped: no lifecycle dir"
   from "invalidated: drift/absence detected"; (b) **a skipped `record-exclusion` MUST NOT signal that
   an exclusion was persisted** when it was not. The precise exit-code/stdout mechanism that satisfies
   (a) and (b) is an implementation contract to be settled in the Plan phase against the actual routing
   code in `__init__.py` and `verification-gates.md` (this is a HOW, deferred per spec discipline) — see
   Open Decisions. Acceptance: a test invoking each subcommand with a `--feature` whose
   `cortex/lifecycle/{feature}/` dir does not exist asserts (i) no directory is created, (ii) no
   `events.log` is written, and (iii) the caller can distinguish the skip from a genuine invalidation
   and from a successful record; `python3 -m pytest tests/test_critical_review_phantom_guard.py -q`
   exits 0. The guard lives in the callers, NOT in `append_event` (which must keep creating the dir for
   the legitimate first-write of a fresh lifecycle at Site A, `refine.py`). **Phase**: Phase 1.
3. **[Must] Auto-trigger invariant preserved.** A test asserts that when `cortex/lifecycle/{feature}/`
   already exists (the in-lifecycle auto-trigger case), all three writers still append normally and a
   genuine drift/absence still returns its real verdict. Acceptance: the same test module includes a
   positive case; `python3 -m pytest tests/test_critical_review_phantom_guard.py -q` exits 0. **Phase**: Phase 1.
4. **[Should] Prose tightening (complementary, not load-bearing).**
   `skills/critical-review/references/verification-gates.md` and `skills/discovery/references/research.md:130`
   are updated so the `<path>`-arg / no-`--feature` / skip-telemetry contract is stated unambiguously,
   with a one-line note that the guard now enforces it structurally. Add no new MUST imperative (the
   structural guard is the enforcement). Acceptance:
   `grep -ci 'guard\|structurally enforced\|skipped' skills/critical-review/references/verification-gates.md`
   ≥ 1; the canonical preamble MUST/MUST-NOT lines at `verification-gates.md:1-7` are unchanged. **Phase**: Phase 1.
5. **[Must] Phantom predicate built on the existing tolerant events.log reader.** Classify a lifecycle
   dir as a phantom / non-lifecycle when it has no `research.md`/`spec.md`/`plan.md` AND **either** (i)
   its events.log event-set is a non-empty subset of `{synthesizer_drift, sentinel_absence}`, **or**
   (ii) its events.log is empty / absent / unparseable (the residue an interrupted `mkdir`-then-write
   leaves). The event-type extraction MUST reuse the project's existing tolerant events.log reading path
   — the one already used by `_detect_lifecycle_phase_inner` / `scan_lifecycle`, which per the
   clarify-critic events schema's documented legacy-tolerance already handles **hybrid files** that
   interleave multi-line YAML-block records and single-line JSONL records. It MUST NOT introduce a naive
   whole-file `yaml.safe_load` (which raises on the hybrid) or a JSONL-only reader (which mis-reads YAML
   blocks as empty). For case (ii), reconcile with the existing `_is_stale` handling
   (`scan_lifecycle.py:398`), which already treats a missing/unparseable events.log as stale — cite
   whether the predicate subsumes or defers to it rather than duplicating. Acceptance:
   `python3 -m pytest tests/test_phantom_dir_discriminator.py -q` exits 0, with fixtures including a
   hybrid YAML+JSONL events.log and an empty/absent events.log. **Phase**: Phase 2.
6. **[Must] Discriminator wired into SessionStart enumeration; fixtures use the birth signature.**
   `scan_lifecycle.py` does not surface a dir the predicate classifies as a phantom as an
   incomplete/"research" lifecycle. The predicate targets a **live phantom at birth** — telemetry-only,
   **before** any `feature_wontfix` archival cap — so the test fixtures encode the birth signature
   (e.g. a lone `synthesizer_drift`, or 3× `sentinel_absence`), NOT the now-`feature_wontfix`-capped
   content of the archived examples (which are excluded from scanning anyway). Acceptance: a fixture set
   containing (a) the birth signatures of the known phantoms, (b) a freshly-started legitimate lifecycle
   whose events.log holds `lifecycle_start`/`clarify_critic` but no artifacts yet, and (c) an
   empty-events.log dir, asserts the phantoms+empty dir are suppressed and the legitimate fresh
   lifecycle is **still surfaced**; `python3 -m pytest tests/test_phantom_dir_discriminator.py -q`
   exits 0. **Phase**: Phase 2.
7. **[Must] No false-positive on real lifecycles.** The discriminator test includes a corpus check
   asserting zero real lifecycle dirs (those containing any non-telemetry event, or any artifact) are
   classified as phantoms — in particular a real dir that lacks a `lifecycle_start` event must NOT be
   flagged (the "has lifecycle_start" discriminator was empirically refuted; ~16% of real dirs lack it).
   Acceptance: covered by `tests/test_phantom_dir_discriminator.py`; exits 0. **Phase**: Phase 2.
8. **[Should] Events-registry pointer fix.** Correct the stale producer code pointers for
   `sentinel_absence` and `synthesizer_drift` in `bin/.events-registry.md` (they reference
   `cortex_command/critical_review.py`; the module is now the package
   `cortex_command/critical_review/__init__.py`). Acceptance: the two rows reflect the package path;
   the events-registry audit recipe (if present) exits 0. **Phase**: Phase 2.
9. **[Should] Sibling-gate audit recorded.** A short note (events-registry rationale or a code comment
   at the guard site) records that the broad sibling-gate audit was performed and that `residue-write`
   (resolver-exit-gated via `cortex-critical-review-resolve-feature`), `complexity_escalator`
   (R11-guarded), and `lifecycle_critical_review_skipped` (fires only where the dir exists) were found
   already structurally protected and need no change — the #255-compliant "siblings audited, no
   conversion needed" record. Acceptance:
   `grep -rci 'residue-write\|already guarded\|R11\|sibling' <the chosen note location>` ≥ 1. **Phase**: Phase 2.
10. **[Should] Plugin-mirror parity.** After canonical edits, `plugins/cortex-core/skills/critical-review/`
    and any mirrored sources are regenerated. Acceptance: `python3 -m pytest tests/test_plugin_mirror_parity.py -q`
    exits 0. **Phase**: Phase 2.
11. **[Should] Full suite green.** Acceptance: `just test` exits 0. **Phase**: Phase 2.
12. **[Must] Full suite green is also a Must gate** — restated as a Must because the fix touches shared
    infrastructure. Acceptance: `just test` exits 0. **Phase**: Phase 2. *(Reqs 11 and 12 are the same
    check; 12 marks it Must-tier so a green suite is not treated as optional.)*

## Non-Requirements

- **No routing of telemetry to `cortex/research/` (Option B').** Rejected above; revisit only if
  discovery-flow integrity telemetry becomes a consumed signal (Open Decisions).
- **No broad conversion of sibling prose-only gates.** The broad audit was *performed* (Req 9); its
  result is that no sibling needs conversion. Converting already-guarded gates would be speculative
  rails the repo's "anchor on current knowledge" principle rejects.
- **No one-shot cleanup script.** All three known phantoms are already archived; zero live phantoms
  today; a blind "events ⊆ telemetry ⇒ delete" sweep is unsafe (archived events.log-only dirs carry
  `clarify_critic` YAML / legitimate `feature_wontfix` caps). The manual `git mv`→`feature_wontfix`
  path (`wontfix.md`) remains the remedy for any rare future survivor.
- **No defense against telemetry mis-attribution to a *wrong-but-existing* feature dir.** A guard
  catches the non-existent-dir case; a plausible-but-wrong `--feature` colliding with a real lifecycle
  would mis-file telemetry (not create a phantom). No current-knowledge evidence; out of scope, noted as
  a known residual that only B' would close.
- **No `.lock` change.** `cortex/lifecycle/*/.lock` is written by `_session_state.feature_lock` (scanner
  claim), not critical-review; killing the phantom at the source means the scanner never claims it.
- **The backstop is not universal.** Despite covering an artifact-less dir from any source, the
  content predicate keys on the telemetry allow-set + the empty/unparseable case; a future writer that
  emits a *different* non-telemetry event as a dir's sole content is out of scope (allow-set is a noted
  maintenance coupling, not a universal "any writer" guarantee).

## Edge Cases

- **In-lifecycle auto-trigger** (`specify.md:172`, `plan.md:274`): dir already exists → guard is a
  pass-through, telemetry writes normally, genuine verdict surfaces (Req 3).
- **Guard fires but a real drift was detected**: the events.log write is skipped (no phantom) yet the
  exit code still reports the genuine invalidation verdict, distinguishable from a benign skip (Req 2a).
- **`record-exclusion` on absent dir**: the persistence is skipped without signalling that an exclusion
  was recorded (Req 2b).
- **Freshly-started legitimate lifecycle** (artifact-less, events.log has `lifecycle_start`/`clarify_critic`
  but no research.md yet — like this very lifecycle earlier): the discriminator must NOT suppress it
  (it has a non-telemetry event) (Req 6/7).
- **Empty / absent / unparseable events.log with no artifacts** (interrupted `mkdir`-then-write residue):
  classified as non-lifecycle / suppressed, reconciled with existing `_is_stale` handling (Req 5(ii)).
- **Hybrid events.log** (multi-line YAML-block record followed by JSONL lines in one file): the
  predicate's reader handles it via the existing tolerant reader, not a whole-file `yaml.safe_load` (Req 5).
- **Phantom already claimed by the scanner** (carries a `.lock`): the predicate keys on events.log
  content + artifact absence, so a stray `.lock` does not defeat classification.
- **Standalone critical-review writing into a pre-existing operator dir before `lifecycle_start`**
  (B-class concern from review): such a dir would have a telemetry-only event-set and be suppressed.
  Accepted residual for the recommended scope — flagged in the review residue for the morning report;
  the guard does not create this dir (it pre-exists), and the operator can re-surface by adding a real
  artifact. If this proves to bite, the mitigation is "classify as non-lifecycle but still report"
  rather than silent suppression — deferred, not silently dismissed.

## Changes to Existing Behavior

- **MODIFIED**: the three critical-review telemetry subcommands no longer create a lifecycle dir as a
  side effect; they suppress the `mkdir`+append when the target dir is absent, while preserving the
  genuine integrity verdict in the exit code.
- **MODIFIED**: SessionStart lifecycle enumeration no longer surfaces telemetry-only / empty,
  artifact-less dirs as "research"-phase lifecycles.
- **ADDED**: a phantom-dir predicate available to detection code, built on the existing tolerant
  events.log reader.

## Technical Constraints

- Guard in the callers, not `append_event` (preserves Site A fresh-dir first-write).
- The guard is write-only and verdict-preserving; the skip must be observably distinct from a real
  invalidation and from a successful record (Req 2).
- The predicate reuses the existing tolerant events.log reader (hybrid YAML+JSONL tolerant); no new
  parser, no whole-file `yaml.safe_load`.
- New/changed gate sites carry `# gate-class:` annotations (#255 parity).
- Field-additive / Tolerant-Reader events discipline; no new event names.
- Canonical sources only; plugin mirrors regenerate via pre-commit (Req 10).
- `just test` is the project test command (`lifecycle.config.md`).
- Any structural claim ships an executable check (#255 honesty bar) — satisfied by Reqs 1-3, 5-7 (the
  Must-tier load-bearing requirements); the Should-tier riders carry verification but are not the
  structural-value claim.

## Open Decisions

- **[product/roadmap — RESOLVED at approval gate] Make discovery-flow integrity telemetry a
  first-class consumed signal?** Resolved **No**: at the spec-approval gate the operator chose A+C +
  implement-here, declining the B' override. B' (route to `cortex/research/{topic}/events.log`) remains
  the documented fallback if discovery-flow telemetry later becomes a consumed signal, but is not the
  chosen shape. Recorded here for provenance.
- **[implementation, Plan phase] The exact exit-code/stdout contract for the dir-absent skip.** Req 2
  fixes the *requirement* (skip observably distinct from invalidation; no false "recorded" signal); the
  precise mechanism (a distinct non-3 exit, a stdout marker, or routing-side handling) requires the
  actual routing code in front of you and is the Plan phase's to settle. Deferred because it is an
  implementation-level contract detail, not a spec-time choice.

## Proposed ADR

None considered. A+C is localized (write-site guard + scanner predicate) and does not meet the
three-criteria ADR gate (hard-to-reverse + surprising + real trade-off). B', were it chosen, plausibly
would — it threads a resolved-root contract through multiple call sites — but it is not the chosen shape.
