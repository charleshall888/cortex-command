# Research: Critical-review telemetry creating phantom lifecycle dirs (+ related verification-gate issues)

> Spike #274. Goal: map the full failure surface, confirm/refute the prior session's candidate
> root cause, broadly audit sibling prose-only gates, and recommend a structural fix shape. The
> land-vs-defer decision is taken at the spec-approval gate. tier=complex, criticality=high.

## Codebase Analysis

### The causal chain — CONFIRMED at the code level, root cause refined

1. **Unconditional mkdir.** `append_event` (`cortex_command/critical_review/__init__.py:469`) opens with
   `events_log_path.parent.mkdir(parents=True, exist_ok=True)` — before any existence check on the
   feature dir. It writes wherever the caller's path points.
2. **Three single-root writers funnel through it.** `_cmd_check_synth_stable` (`synthesizer_drift`,
   path `:659`, append `:689`), `_cmd_check_artifact_stable` (`sentinel_absence`, `:743`/`:746`), and
   `_cmd_record_exclusion` (`sentinel_absence`, `:762`/`:774`) each compute
   `Path(lifecycle_root)/{feature}/events.log` with `lifecycle_root = args.lifecycle_root or
   _default_lifecycle_root()`. `_default_lifecycle_root` (`:524`) is hardcoded to `cortex/lifecycle`.
   `--feature` is `required=True` on all three. Each can independently birth a phantom.
3. **The structural seam (refined root cause).** `prepare-dispatch` is multi-root —
   `_default_artifact_roots()` (`:529`) returns `(cortex/lifecycle, cortex/research)` and `--allow-adhoc`
   snapshots into `cortex/_adhoc/`. But `prepare_dispatch` returns only `{resolved_path, sha256}`
   (`:326-332`) — **the matched root is dropped and never threaded to the telemetry writers.** So a
   critical-review on a `cortex/research/{topic}/research.md` artifact validates fine, but if a
   `--feature` reaches a telemetry subcommand the write can *only* land under `cortex/lifecycle/{topic}/`,
   mirroring the research topic under the wrong root. The single-root/multi-root mismatch is not an
   incidental detail — it is the mechanism.
4. **The trigger.** Discovery (`skills/discovery/references/research.md:130`) invokes
   `/cortex-core:critical-review` on `cortex/research/{topic}/research.md` with **no `--feature`**.
   `verification-gates.md` (`:18,:49,:79`) says the `<path>`-arg form omits `--feature` and *skips* the
   synth/sentinel telemetry ("telemetry requires a lifecycle feature directory"). This is **prose-only**
   enforcement. The phantom is born when the orchestrator supplies a `--feature {topic}` anyway — and the
   prose condition "no feature in scope" is **ambiguous** for discovery-on-research.md, because the topic
   slug *looks* like a feature. So it is a prose-design gap, not merely an LLM error.

### All four writer sites (per `tests/test_variant_a_writer_sites_baseline.py`)

- **Site A** — `refine.py:117` (`lifecycle_start`): the legitimate first-write of a fresh lifecycle dir.
  Goes through a *different* path than `append_event`'s telemetry writers.
- **Site B** — the 3 critical-review telemetry writers (above): the phantom source.
- **Site C** — `cortex_command/lifecycle/complexity_escalator.py:191`: also does the unconditional
  `mkdir(parents=True, exist_ok=True)`, **but cannot create a phantom** — it short-circuits with an
  artifact-existence guard ("R11: graceful no-op when artifact missing", `:300-301`) *before* emitting.
  **This is the exact guard the fix proposes — already shipped in the codebase. The fix mirrors an
  existing idiom, it does not invent one.**
- **Site D** — `discovery.py` writes its own discovery events to `cortex/research/{topic}/events.log`.

### Detection side — why a phantom nags at SessionStart

`detect_lifecycle_phase` / `_detect_lifecycle_phase_inner` (`cortex_command/common.py:223-368`) is a
pure artifact-presence state machine; an artifact-less, non-terminal dir falls through to
**Step 6 → `"research"`** (`:367-368`). `scan_lifecycle.py` then enumerates it as an incomplete
research-phase lifecycle. The only existing suppressors are: `archive/`+`sessions/` structural exclusion
(`:898` — so archived phantoms are not scanned), and `_is_stale`'s 30-day threshold (`:398`) — which
leaves a 30-day window where a *fresh* phantom nags every session. That window is the user complaint.

### Existing phantom corpus (the repro evidence — three, not two)

All telemetry-only, all correspond to real `cortex/research/{topic}/` topics, all currently **archived**:

1. `archive/cortex-init-scope-reduction/` — `synthesizer_drift` (`observed_sha_or_null: null`) + a later
   manual `feature_wontfix`. Archived via `d21d395e`.
2. `archive/doc-audit-2026-05-18/` — single `synthesizer_drift` (`observed_sha_or_null: null`).
3. `archive/swap-daytime-autonomous-for-worktree-interactive/` — **3× `sentinel_absence`** + later
   manual `feature_wontfix` (the third phantom, found this session; the `sentinel_absence` variant).
   Its sentinel rows (`2026-05-18T17:17`) predate that topic's own discovery events (`17:52`, `18:12`)
   in `cortex/research/swap-daytime.../events.log` — confirming critical-review ran on the research.md
   early in discovery.

No telemetry-only phantom currently sits live under `cortex/lifecycle/` (this lifecycle's own dir is a
*legitimate* one — it has `lifecycle_start`, `clarify_critic`, `phase_transition`, `.session`, `index.md`).

### `.lock` debris — not critical-review's doing

`cortex/lifecycle/*/.lock` is written by `feature_lock()` in `cortex_command/hooks/_session_state.py:122`
(SessionStart session-claim flock), **not** by critical-review. It appears in a phantom only because the
scanner *surfaced and claimed* the phantom. Kill the phantom at the source and the `.lock` never lands.
It is gitignored (`cortex/lifecycle/*/.lock`).

### Auto-trigger invariant — CONFIRMED safe for a write-guard

In-lifecycle auto-triggers (`specify.md:172`, `plan.md:274`) fire only after `cortex/lifecycle/{feature}/`
exists (research.md/spec.md are already written). Empirically, in every real lifecycle dir containing
telemetry, the telemetry event is **never** at index 0 — the first event is always `lifecycle_start` or
`clarify_critic`. So a guard "write telemetry only if the feature dir already exists" breaks no
legitimate flow. (The guard must live in the **three callers**, not in `append_event` — Site A's
legitimate first-write of a fresh dir goes through `append_event` and would be wrongly blocked.)

## Web Research

Durable engineering principles, strongly converging on the write-guard framing:

- **Telemetry must be a pure observer.** A logging/telemetry call that mutates filesystem topology
  (creates a new entity dir) violates the observer contract; telemetry should write only into locations
  that already exist (LoongCollector log-collection anti-patterns; the kaggle-mcp "create-before-validate"
  vuln as the analogue).
- **Idempotent ≠ guarded.** `mkdir(exist_ok=True)` is idempotent but *unguarded* — it still creates
  structure that shouldn't exist. The fix is a *precondition guard* ("only if the entity dir already
  exists"), à la Chef's resource `guard` property. (arslan.io / serverio.co.uk idempotency guidance.)
- **Parse, don't validate / make illegal states unrepresentable** (Alexis King; Minsky's slogan
  "making the wrong thing hard to express is better than checking for it at runtime"). The structural
  move is to enforce the invariant at the construction boundary (the writer refuses to construct a dir
  for a non-existent entity), not via a downstream check.
- **Hyrum's Law** is the argument *against* a prose-only fix: a written rule ("don't pass `--feature`
  for research reviews") does not bind behavior; it will eventually be violated. Encode it in code.
- **Sentinel/marker-file pattern** for the scanner: a dir should count as a real entity only if it
  carries an explicit marker created by the entity-creation path — not because *some* file (a telemetry
  event) happens to live there.
- **Defense-in-depth** justifies doing *both* a write-guard and a scanner-side discriminator — independent
  layers. **SSOT caveat:** routing to "a different valid root" (option B) is only safe if "valid roots"
  is a single shared definition both validator and writer consume; otherwise it re-introduces the
  multi-root/single-root drift rather than fixing it.

## Requirements & Constraints

- **Solution horizon (`project.md:21`, CLAUDE.md).** Durable fix is justified only by *current knowledge*
  (named follow-up / same patch in multiple *named* places / a *namable* sidestepped constraint) — "test:
  current knowledge, not prediction." A speculative structural rail for a predicted-only failure does not
  clear this bar. The three archived phantoms are exactly the current-knowledge evidence for the 3 writers.
- **Structural over prose-only enforcement (CLAUDE.md)** — but carved out: prose-only is acceptable
  "where the cost of occasional deviation is low," and **before declaring a gate ceremonial, name the
  user-facing affordance it protects.** The critical-review verification gates protect the affordance
  "don't surface synthesizer prose that wasn't really produced by a dispatched reviewer" — that must
  survive. The *write-to-lifecycle-root* behavior is **not** an affordance; it's an unintended side
  effect, so guarding it removes no protective boundary.
- **#255 (gate-policy-taxonomy-and-critical-review) is directly-prior work** and sets the bar:
  - Every gate carries `# gate-class: <security|hygiene|advisory>`, enforced by
    `tests/test_critical_review_gate_class_parity.py`. Any new write-guard must carry one (a phantom
    guard is `hygiene`). *(Note: that parity test governs `validate_artifact_path`, not the telemetry
    writers — so a guard on the writers does not collide with it, but the annotation convention applies.)*
  - **Honesty-vs-structural distinction**: a change defended on "structural separation" grounds **must**
    ship an executable check; a mere honesty/naming change must **not** claim structural value. → the fix
    must ship a test asserting the invariant, or it cannot claim "structural."
  - Established `_default_artifact_roots()` and the `_adhoc/` peer-root.
- **Events registry (`bin/.events-registry.md:113-114`).** `sentinel_absence` and `synthesizer_drift` are
  registered `target: per-feature-events-log`, `scan_coverage: manual`, consumer
  `(future per-tier compliance audit)` — i.e. unbuilt. Routing to `cortex/research/` (option B) would
  require widening `target` to the dual form (precedent: `approval_checkpoint_responded`). The registry's
  producer code pointers are **stale** (`cortex_command/critical_review.py` — now a package
  `__init__.py`); any touching fix should correct them. No pre-commit gate blocks (manual coverage), so
  the registry update is review-enforced.
- **MUST-escalation policy (CLAUDE.md).** Prefer structural enforcement over new MUST prose. If the fix
  adds any MUST imperative, it needs an evidence artifact + an effort=high(/xhigh) dispatch attempt
  showing soft phrasing failed. The structural write-guard sidesteps this cleanly.
- **No new ADR** unless the three-criteria gate (hard-to-reverse + surprising + real-trade-off) is met.
  A localized write-guard does not; a routing redesign threading a new root through many call sites might.
- **Adjacent enforcement to respect, not duplicate:** `_is_stale` content-based staleness; `cortex clean
  --adhoc` (only manages `_adhoc/` SHA dirs, not phantom lifecycle dirs); SKILL.md-to-bin parity
  (`bin/cortex-check-parity`); plugin-mirror parity (edit canonical `skills/` only); destructive-ops
  preserve uncommitted state (`project.md:53` — any cleanup script must SKIP on uncommitted state).

## Tradeoffs & Alternatives

- **A — Write-guard in the three callers (RECOMMENDED).** A shared helper (e.g.
  `guard_feature_dir_exists(lifecycle_root, feature)`) that the 3 writers call; if
  `Path(lifecycle_root)/{feature}/` doesn't exist, skip the append and exit cleanly (the
  invalidation decision is still surfaced via stdout/exit-3; only the events.log row is dropped).
  Mirror complexity-escalator's R11 guard so the codebase has one idiom. **Pros:** structural, at the
  exact safe site; smallest blast radius; nothing reads the dropped events so silent-drop costs ~nothing.
  **Cons:** drops research-scoped drift telemetry in the one case it fires (near-zero value today).
  Must NOT live in `append_event` (would block Site A's legitimate fresh-dir first-write).
- **B — Route research-scoped telemetry to `cortex/research/{topic}/` (REJECTED).** Thread
  prepare-dispatch's matched root to the writers. **Cons:** co-mingles critical-review's event schema
  with discovery's own `cortex/research/{topic}/events.log` (`discovery.py:43-45,:175-201`); needs a new
  arg + orchestrator plumbing; preserves a write nobody reads; requires the events-registry `target`
  widening. Over-built for a write-only diagnostic — unless the product intent is that discovery-time
  exclusions *should* be observable (see the genuine fork in Open Questions).
- **C — Detection-side discriminator (defense-in-depth, recommended as the executable test).** Classify a
  dir as a phantom and suppress it from SessionStart enumeration. The robust discriminator (resolved
  below): **no spec/plan/research.md AND events ⊆ `{synthesizer_drift, sentinel_absence}` (non-empty).**
  Piggybacks on the events.log read already in `_detect_lifecycle_phase_inner`. **Pro:** neutralizes
  phantoms regardless of writer (covers future/out-of-band writers); is the executable check that lets A
  honestly claim "structural" under #255. **Con:** symptom-side alone (the dir still materializes on
  disk/git) — so it complements A, it doesn't replace it.
- **D — A + C (RECOMMENDED combination).** Guard kills the known cause at the only sanctioned write path;
  discriminator + its test backstops any phantom that slips through and satisfies #255's executable-check
  bar. Both pieces are individually small. This is the defense-in-depth shape the principles endorse.
- **Cleanup:** **no script.** All three phantoms are already archived; there is zero live phantom today.
  A blind "events ⊆ telemetry ⇒ delete" sweep is unsafe (some archived events.log-only dirs carry
  `clarify_critic` YAML blocks or legitimate `feature_wontfix` caps). The manual `git mv` →
  `feature_wontfix` path (`wontfix.md`) is the correct remedy for the rare future survivor.

## Adversarial Review

- **Root-cause alternatives — none found.** The only callers of the 3 telemetry writers are the
  LLM-read skill prose (`SKILL.md:70,86`; `verification-gates.md:40,73`) + the regenerated plugin mirror.
  Zero programmatic callers in `cortex_command/`, `bin/`, `tests/`. The only birth path is an LLM
  orchestrator supplying `--feature` on a research-scoped review.
- **Timeline re-verification — HOLDS (refutes transient).** The skip clause was present in
  `verification-gates.md`'s creation commit `16fbcd7e` (2026-05-11); all three phantoms postdate it
  (2026-05-18, 2026-05-29). Structural-not-transient confirmed. Sharper: the prose condition is
  *ambiguous* for discovery-on-research.md, strengthening the case for structural enforcement.
- **Discriminator resolution — Tradeoffs agent RIGHT, Codebase agent REFUTED.** Tested across 89 live +
  158 archive dirs with a **YAML-aware** parser (real lifecycle events.log are sometimes multi-line YAML
  blocks, not JSONL — a naive JSONL reader mis-reads them as empty, which would itself break a
  discriminator). "has `lifecycle_start`" mis-flags **16%** of real dirs (14/89 lack it entirely —
  completed, legitimate). "events ⊆ {synthesizer_drift, sentinel_absence}" had **zero** false positives
  among live dirs and exactly one archive hit (`doc-audit`, a true phantom). Robust discriminator:
  **no spec/plan/research.md AND events.log event-set is a non-empty subset of
  {synthesizer_drift, sentinel_absence}.** Catches all three at birth (the `feature_wontfix` rows were
  added later during archival).
- **Consumer check — silent-drop breaks nothing.** Zero code reads/dispatches on either event repo-wide;
  the only event-dispatching reader (`overnight/report.py:912`) handles a different event
  (`drift_protocol_breach`). The registry consumer is hypothetical. Even a future per-tier audit would
  want phantom-case telemetry dropped (the guard fires only when the dir doesn't exist = the non-feature
  case). The drop is information-preserving for any real consumer.
- **Broad-sweep verdict — audit done; only the 3 writers qualify.** Sibling prose-only gates of the same
  "skip-write-when-no-feature" shape:
  - **residue-write** (`SKILL.md:92`, `write_residue_cli.py:72-73`) — same `mkdir`, but its `{feature}`
    is resolved by `cortex-critical-review-resolve-feature`, which **exits non-zero on zero/multiple
    match** (`resolve_feature_cli.py:58-61`) — a *structural* exit-code gate. Has **never** created a
    phantom. Already guarded; converting it would be speculative.
  - **complexity-escalator** — already R11-guarded (`:300-301`).
  - **`lifecycle_critical_review_skipped`** (`specify.md:174`, `plan.md:276`) — fires only where the dir
    exists. No failure evidence.
  → Per "anchor on current knowledge, not prediction" + #255's bar, a broad conversion would produce
  speculative rails the repo's own principles reject. The #255-compliant outcome of the broad audit is to
  **document that the siblings were audited and found already-guarded**, not to convert them.
- **Assumptions that may not hold:** the discriminator's allow-set is a maintenance coupling (a future
  telemetry-only event type written to a fresh dir would need adding); a phantom that the scanner already
  claimed carries a `.lock` a detection/cleanup path must tolerate; and the "silent-drop is correct"
  conclusion rests on "nobody reads it" — true today, but it is a product decision (see the fork below).

## Open Questions

1. **Fix shape: silent-drop (A+C) vs route-to-research-root (B)?** *Deferred: this is the central
   fix-shape decision the spec's approval gate resolves with the user.* Research recommends **A
   (write-guard in the 3 callers) + C (detection discriminator with its executable test)** and rejects B,
   because nothing reads `synthesizer_drift`/`sentinel_absence` today, B co-mingles schemas with
   discovery's own events.log, and A mirrors the already-shipped complexity-escalator R11 guard. B becomes
   correct **only if** the product intent is that discovery-time critical-review exclusions *should* be
   observable — the one genuine fork to put to the user in Spec.
2. **Scope: write-guard alone, or write-guard + detection discriminator?** *Deferred to Spec.* Research
   recommends both (defense-in-depth; the discriminator's test is also what lets the guard honestly claim
   "structural" under #255). The user may choose guard-only to minimize blast radius.
3. **One-shot cleanup?** *Resolved: No.* All three phantoms are already archived; zero live phantom today;
   a blind sweep is unsafe. Manual `feature_wontfix` archival for any future survivor.
4. **Broad sibling-gate sweep outcome?** *Resolved: audit complete.* Only the three telemetry writers
   have demonstrated failure; residue-write (resolver-exit-gated) and complexity-escalator (R11-guarded)
   are already structurally protected; `lifecycle_critical_review_skipped` fires only where the dir
   exists. The spec should *record* this audit result (a #255-compliant "siblings checked, no change
   needed"), not propose conversions.
5. **Stale events-registry producer pointers** (`critical_review.py` → package `__init__.py`) — *Resolved:
   a touching fix should correct them*; low-effort housekeeping bundled with whichever option lands.
