# Research: Consolidate tier supersession into a shared pure-events reducer

**Clarified intent:** Establish a single source of truth for tier supersession by extracting the event-fold of `reduce_lifecycle_state` (`cortex_command/common.py`) into a pure reducer over parsed records, delegating the Path-based reader to it, and replacing the inline tier fold in `extract_feature_metrics` (`cortex_command/pipeline/metrics.py`) with a call to the shared core — so the in-memory metrics path and the file-based readers agree *by construction* rather than by parity test.

**Headline (read this first):** The metrics fold is **not** an accidental drift — it shipped deliberately in commit `3deac51b` ("Attribute feature metrics to the final effective tier"), hand-written to mirror the canonical rule. The empirical audit found **zero** out-of-vocab values across 279 real logs / 340 vocab-bearing rows, so the two folds already agree on **100% of real historical data**. This reframes the work from "fix a divergence" to "de-duplicate an intentional re-implementation + close a real test-coverage gap." The research recommends a **smaller, lower-boundary design than the ticket's framing** (see Tradeoffs + Adversarial), and surfaces two genuinely new findings the ticket did not anticipate (parity-harness gap; a latent non-UTF-8 crash in the metrics intake).

---

## Codebase Analysis

**Files in scope:**
- `cortex_command/common.py` — `reduce_lifecycle_state` (660–738), `LifecycleStateReduction` NamedTuple (623–657), `TIER_VOCABULARY`/`CRITICALITY_VOCABULARY` (619–620), the cached readers `_read_tier_inner` (564–610)/`_read_criticality_inner` (507–556), `lifecycle_state_corrupted` (741–761). Imports already cover the need (`json`, `lru_cache`, `Path`, `NamedTuple`).
- `cortex_command/pipeline/metrics.py` — `extract_feature_metrics` (198–300), the inline `initial_tier`/`tier` fold (237–245). **No `cortex_command.common` import exists today** — one must be added.
- `tests/test_reduce_lifecycle_state.py` — thin coverage for the new pure entry point (ticket touch-point).

**Call graph of `reduce_lifecycle_state` (5 production callers, all in `cortex_command/`; none in skills/hooks/bin):**
- `_read_criticality_inner` (common.py:524), `_read_tier_inner` (common.py:580) — lru_cached, read `.state` only.
- `lifecycle_state_corrupted` (common.py:761) — reads `.corrupted`. **No production callers** (corruption reaches prod via `reduction.corrupted` directly at `outcome_router.py:1004`, `state_cli.py:175`); tested only.
- `refine._reduce_current_state` (refine.py:126) — `.state` only, already a thin delegate.
- `state_cli` (state_cli.py:86, 152) — reads `.state`, `.skipped_lines`, `.corrupted`.
- `outcome_router._review_required` (outcome_router.py:1001) — reads both axes + `.corrupted`.

`read_tier`/`read_criticality` are consumed widely in `overnight/` (outcome_router, report, runner, feature_executor). All access `LifecycleStateReduction` by **named attribute** — no positional unpacking, no `_asdict()`, no `result[0]` indexing anywhere (verified).

**How `extract_feature_metrics` receives events:** via `parse_events` (metrics.py:75–101), called by `extract_all_feature_metrics` (856–882). `parse_events` reads `read_text(encoding="utf-8")` **strict (no `errors="replace"`)**, drops lines that fail JSON parse OR lack `event`/`ts` keys (via `warnings.warn`), and **discards line numbers**. So `events` is a pre-parsed, pre-filtered `list[dict]` in file order with no line positions — every element is guaranteed a dict with `event` and `ts`.

**Behavioral divergences, metrics fold (240–245) vs canonical fold (690–737):**
1. **Vocab gating** — canonical rejects values outside `TIER_VOCABULARY`/`CRITICALITY_VOCABULARY`; metrics accepts any non-None string verbatim.
2. **`initial_tier`** — metrics tracks first-seed `initial_tier`; the reducer has no first-seed concept (last-writer-wins only).
3. **Criticality** — metrics ignores it; reducer folds it too (harmless to metrics).
4. **`skipped_lines`/`corrupted`** — reducer tracks; metrics has nothing to track.
5. **Intake decode** — reducer `errors="replace"` (tolerant); `parse_events` strict utf-8 (can raise — see Adversarial).

**Cache contract:** unaffected. lru_cache keys on `(exists, mtime_ns, size)` computed before the cached body; splitting the fold out of the file-read is invisible to it, provided `reduce_lifecycle_state(Path) -> LifecycleStateReduction` keeps its signature. Preserve the `__wrapped__` introspection hooks (610/556).

---

## Web Research

- **Functional core, imperative shell (FCIS):** the target shape. Pure core (`reduce_lifecycle_events`) is unaware of its callers; the Path reader and the in-memory caller are two *shells* over it. The core must not own I/O or line-number tracking. Multiple shells over one core is the explicit point of the pattern.
- **Parse, don't validate:** JSONL parsing, torn-line detection, and 1-based line numbers belong at the shell boundary; the core receives records it can assume are JSON-shaped.
- **Surface skipped/error records out-of-band, keyed by record position (index), not line number** — let each shell map position→lineno or ignore it. The event-sourcing `apply` core carries no error channel; errors surface at the command/parse layer.
- **Agreement by construction > agreement by parity test** (Dijkstra: tests show presence, not absence, of bugs). This is past the Rule of Three (two copies + a test) and is *semantic*, not syntactic, duplication — so it clears the over-engineering bar. Caution honored: extract only the rule, not the divergent I/O.
- **Permissive→strict migration is the canonical hazard** — prefer reject-and-**flag** over reject-and-drop, and verify against *historical* data before cutover. (Our audit did exactly this — see below.)

Fetched: functional-architecture.org, kennethlange.com, zalas.pl/functional-event-sourcing, rednegra.net (parse-don't-validate), industriallogic.com (SPOT), agentclientprotocol.com enum-RFD. `deviq.com` parse-don't-validate returned HTTP 403 (covered via rednegra.net).

---

## Requirements & Constraints

- **`common.py` is lifecycle-protected** (CLAUDE.md / `skills/lifecycle/SKILL.md`) — this work requires the lifecycle it is running under. `metrics.py` is **not** protected.
- **No dual-source mirror co-commit:** `plugins/cortex-core/` mirrors only `bin/`, `hooks/`, `skills/`. `cortex_command/` ships via the wheel and is **not** mirrored (verified). Neither touch-point requires a canonical+mirror co-commit.
- **Sequential dispatch, not worktree:** editing the `cortex_command` package must use sequential dispatch on a feature branch — `just test` runs the editable install, so a worktree verifies stale code (MEMORY `project_lifecycle_implement_dispatch_mode`). Commit with explicit `git commit -- <pathspec>` if a concurrent session shares the checkout (MEMORY `trunk_shared_index_concurrent_session`).
- **Solution horizon:** ticket #301 IS the already-planned durable follow-up (Option C, deliberately deferred by the metricsFix recommendation), so it is justified under the durable-fix carve-out — but the same evidence rates **standalone value as LOW** ("near-zero historical churn and the parity test catches divergence").
- **#287** established the canonical reducer and `LifecycleStateReduction` (state insertion order criticality-then-tier; `skipped_lines` 1-based; non-dict JSON skipped silently and NOT a corruption signal; per-value rejection; never raises, never None; `.to`-only supersession with no `.tier`/`.criticality` fallback). The new pure core + delegating wrapper must preserve all of this.
- **evidence.json → metricsFix (Option C):** records the mechanism, the LOW standalone value, the vocab risk ("would become None and drop from aggregates"), and that `initial_tier` is NOT part of the canonical rule (keep local or extend deliberately).
- **`bin/.events-registry.md`:** no new event is minted, so no registry row is required. Minor staleness note: `complexity_override`'s consumer list does not include `metrics.py` (and the registry does not index it as a metrics consumer); a doc update is optional, not a gate.
- **No L1 ratchet / no dual-source test** applies to these files.

---

## Tradeoffs & Alternatives

Grounding facts: (1) vocab-validation asymmetry is the only non-theoretical defect, and the audit shows it never fires on real data; (2) input-medium mismatch (Path has raw text + linenos; metrics has pre-parsed dicts, no linenos); (3) `initial_tier` is metrics-only and consumed by exactly one reader.

- **Approach A — full extraction (ticket's framing):** pure core returns the full `LifecycleStateReduction`; Path delegates; metrics calls it. **Pros:** single rule incl. vocab guard; trivially unit-testable. **Cons:** heaviest touch on protected `common.py`; forces awkward answers for `skipped_lines` (line semantics for a line-less caller) and `initial_tier` placement; if `initial_tier` ends up re-derived in metrics, the "one source of truth" claim is partially hollow. Risk/reward skewed for a caller of low standalone value.
- **Approach B — minimal validating supersession core (RECOMMENDED):** extract a pure core that returns the bare `state` accumulator (and which records it rejected, by position) — **not** the NamedTuple. The Path shell wraps the result into `LifecycleStateReduction` (keeping `skipped_lines`/`corrupted` a *shell* concern); metrics calls the bare core for `tier` only and **keeps `initial_tier` local**. **Pros:** lightest touch on protected `common.py`; closes the high-value half (shared, validating supersession rule); avoids both the NamedTuple-growth tax and the synthetic-lineno footgun. **Cons:** does not unify criticality or the corruption layer — but metrics needs neither, so this is a non-loss.
- **Approach C — do-nothing / strengthen the parity guard:** keep both folds; add the missing out-of-vocab and re-seed cases to a parity check. **Pros:** zero touch on protected `common.py`; matches the ticket's "standalone value is low." **Cons:** detection-after-the-fact, not prevention; the duplicate-rule cognitive tax persists. **Note:** adding the out-of-vocab parity case would *fail today* (metrics doesn't validate), forcing a fix or an explicit documented acceptance.

**Recommendation: B**, with A-Option-2 (grow the NamedTuple) explicitly rejected (see Adversarial arbitration). C is the defensible floor given the empty audit; B is the durable version the user opted into. Reserve A only if a near-term, *named* second pre-parsed consumer of the full reduction were planned — none exists.

---

## Empirical Vocabulary-Gating Audit

- **Scanned:** 279 real-data logs under `cortex/lifecycle/**` (worktree copies excluded); 10,036 non-empty rows (5,432 JSON, 4,604 legacy YAML that neither reader parses). Plus committed and in-process test fixtures.
- **Distinct real-data values:** `tier` ∈ {simple, complex}; `complexity_override.to` ∈ {simple, complex}; `criticality` ∈ {low, medium, high, critical}; `criticality_override.to` ∈ {high}. **All in-vocab.**
- **Out-of-vocab in real data: NONE** — 340 vocab-bearing JSON rows, 0 out-of-vocab.
- **Out-of-vocab only in deliberate test-fixture mojibake injections** (e.g. `test_reduce_lifecycle_state.py:50,90,159`, `test_bin_lifecycle_state_parity.py:212`) — expected, exercising the rejection path.
- **Field-shape:** every `complexity_override` carries the value in `.to` (76/76); no `.tier`/`.value` carrier. Two `criticality_override` rows carry the value in a non-standard `criticality` field (`refine-commits-lifecycle-artifacts/events.log:4` has no `to` at all) — **irrelevant to the tier fold** (both readers read `.to` only on the tier axis), but a pre-existing latent drop on the criticality axis.
- **Verdict:** the vocab-gating switch is a **safe no-op over all real data** on the final-tier axis — aggregates byte-identical. The ticket's "no such data exists today" is empirically confirmed. (The `initial_tier` axis under re-seed/out-of-vocab was not separately audited — see Open Questions; moot if `initial_tier` stays local.)

---

## Contract & Semantics Design

*(The contract agent recommended a higher-boundary design — full `LifecycleStateReduction` core + growing it with `initial_tier`. The Adversarial pass refuted both; the synthesized recommendation below is the refuted-and-corrected version.)*

**Recommended core shape (Approach B, lower boundary):**

```python
def reduce_lifecycle_events(records: Iterable[dict]) -> tuple[dict[str, str], list[int]]:
    """Pure fold over already-parsed event dicts. No I/O, no json.loads.
    Returns (state, rejected_positions): `state` has at most {"criticality","tier"}
    in criticality-then-tier insertion order; `rejected_positions` are 0-based indices
    of records carrying an out-of-vocab value. Non-dict records and unknown events
    are no-ops. Caller owns line numbers and the LifecycleStateReduction wrapper."""
```

- **Path shell** (`reduce_lifecycle_state(Path) -> LifecycleStateReduction`, unchanged signature): keeps the file read (`errors="replace"`), the `splitlines()` loop, `json.loads` in try/except tracking parse-failure 1-based linenos; passes surviving records (paired with their linenos) to the core; maps `rejected_positions` back to linenos; merges `parse_failures ∪ vocab_rejections` (sorted) into `skipped_lines`; constructs `LifecycleStateReduction(state, skipped_lines)`. **`corrupted` and `skipped_lines` stay shell concerns** — the core never returns them.
- **Metrics shell:** `state, _ = reduce_lifecycle_events(events)`; reads `state.get("tier")`; **ignores rejected positions**; computes `initial_tier` with its own one-line first-seed capture (kept local). Metrics never holds a `LifecycleStateReduction`, so there is no misleading `.corrupted` to misread.
- Rejected alternative (contract agent's original): core takes `Iterable[tuple[int,dict]]` and returns the full `LifecycleStateReduction` with `initial_tier` added — rejected because it grows a 3-consumer NamedTuple for one consumer and creates the synthetic-lineno footgun (Adversarial §2).

**`initial_tier` fork — RESOLVED: keep local to metrics.** It has exactly one consumer (`metrics.json` via `format_feature_record`), needs a `seen_first` latch the gate readers don't want, and deliberately tolerates out-of-vocab tiers for forensic fidelity (escalation queryability) — a semantic the gate readers must NOT adopt. Keeping it local preserves that intended divergence instead of erasing it.

**Edge cases the spec must pin:** empty input → `({}, [])`; re-seed `lifecycle_start` overwrites `state["tier"]` while metrics' local `initial_tier` keeps the first seed; mixed valid+invalid on one line → valid value accumulates, line flagged once; non-dict JSON → silent no-op, NOT a skip; criticality axis → `corrupted` stays the symmetric tier-OR-criticality form; `lifecycle_start` with no tier (criticality-only seed) → no `initial_tier`, a later `complexity_override` does not set `initial_tier`.

---

## Test & Regression Coverage

- **`tests/test_reduce_lifecycle_state.py`** (the Path-reader safety net): covers non-UTF-8 no-raise (:31), out-of-vocab override ignored (:44), torn-line lineno (:57), clean-log no-skips + insertion order (:70), mixed-line per-value rejection (:84), missing-file empty (:97), reader delegation (:103), the corruption suite (:133–199), CLI-only stderr (:202). **Gaps:** no `lifecycle_start` re-seed test; non-dict-JSON handling untested; criticality-axis override re-seed untested. The `:100` equality assertion `result == LifecycleStateReduction(state={}, skipped_lines=())` is the one to watch under any NamedTuple change.
- **The metrics parity assertion** (`test_metrics.py:1749`, inside `test_extract_feature_metrics_complexity_override_supersedes_tier`): `assert m["tier"] == read_tier(...)` on a single in-vocab simple→complex fixture. After delegation it is **not** fully tautological (the two parse front-ends still differ), but it degrades to confirming the front-ends agree on clean input. It should be **strengthened**, not removed: add an out-of-vocab divergence case and a re-seed case.
- **Delegation guards** (behavior-preservation for the Path wrapper): `read_tier`/`read_criticality` (test_reduce_lifecycle_state.py:103,202; test_refine_module.py:105–266), `lifecycle_state_corrupted` (the five `test_corrupt_*`), `state_cli` (CLI assertions). These exercise `reduce_lifecycle_state(Path)` and protect the wrapper→core delegation as long as the wrapper keeps reading bytes and only hands records to the core.
- **`initial_tier` coverage:** `test_metrics.py:1744`,`:1783` pin first-seed-survives. Sufficient if `initial_tier` stays local (recommended).
- **NEW test matrix:** (a) pure-core tests (empty; seed+override+criticality; out-of-vocab dropped+position flagged; non-dict no-op; re-seed). (b) `skipped_lines` byte-for-byte regression — assert the torn-line lineno (`(2,)` at :66) is unchanged after delegation. (c) **The load-bearing new test — vocab-gating edge for metrics:** feed `lifecycle_start(tier="trivial")` and pin the post-switch behavior (dropped vs kept). `extract_feature_metrics` is a *new* consumer of the shared rule, so its vocab behavior is unconstrained by "behavior-preserving for existing consumers" and MUST be locked explicitly. (d) re-seed `initial_tier` if it ever moves.
- **Baselines at risk:** none. `test_l1_surface_ratchet.py` measures skill frontmatter, not Python. `TestPairDispatchEvents` (`tier="trivial"` at test_metrics.py:153) reads `dispatch_start.complexity`, a *different* aggregator — not this fold; don't be misled by the grep hit.

---

## Adversarial Review

- **Reframe (load-bearing):** the metrics fold shipped intentionally in `3deac51b`. The evidence.json vocab-risk quote describes *pre-3deac51b* code that no longer exists. This is de-duplicating a deliberate re-implementation, not repairing drift.
- **A-vs-B / `initial_tier` arbitration → B wins.** NamedTuple growth is *mechanically* safe (all consumers use named access) but the `:100` equality assertion makes a defaulted field a `TypeError` footgun the moment someone omits the default; `initial_tier` has one consumer and is a *different* fold (needs first-seed state the accumulator lacks); forensic-vs-gate vocab semantics genuinely differ. **Reject A-Option-2 (grow the NamedTuple).**
- **Synthetic-lineno footgun:** having metrics hold a `LifecycleStateReduction` with populated-but-meaningless `skipped_lines`/`corrupted` is a latent trap — a future `.corrupted` read would be *misleadingly plausible* (under-reported, since `parse_events` already dropped torn lines). Mitigation: core returns bare `(state, rejected_positions)`; the NamedTuple/`corrupted` is a Path-shell-only concern.
- **Partial-unification illusion (concrete):** `parse_events` reads strict UTF-8; on a non-UTF-8 log it raises `UnicodeDecodeError`, **uncaught**, crashing the whole metrics pipeline — while `read_tier` (`errors="replace"`) returns `simple`. Sharing the *fold* does not fix the *intake*. After the refactor the two can still disagree (graceful vs crash) on byte-corrupt input. The title oversells "by construction."
- **The parity harness does NOT cover metrics:** `test_bin_lifecycle_state_parity.py::test_all_readers_agree_on_effective_state` covers `state_cli`/`read_tier`/`read_criticality`/`refine` — **not** `extract_feature_metrics`. The only metrics cross-check is the single inline assertion above. So "the parity test already guards drift" is weaker than the do-nothing camp claims — strengthening the by-construction argument *and* identifying the cheapest standalone fix.
- **Commit hygiene:** runs on `main` with possible concurrent sessions → explicit `git commit -- <pathspec>`, sequential (not worktree) dispatch.
- **Bottom line:** "borderline gold-plating dressed as consolidation." The genuine value is real but small: there is currently *no systematic drift guard* on the metrics fold, and it agrees with the canonical rule on 100% of real data. Smallest defensible deliverable = close the parity-harness gap; durable version = Approach B with `initial_tier` local.

---

## Open Questions

1. **[RESOLVED] Vocabulary gating safe over real data?** — Yes. Empirical audit: 0 out-of-vocab values across 340 vocab-bearing real rows; the gating switch is byte-identical on the final-tier axis. The *new* metrics-side behavior for a hypothetical future out-of-vocab tier (drop vs keep) must still be **decided and locked by a test** (Test matrix item c) — the recommendation is to make metrics reject-and-flag consistent with the gate readers, since no real data depends on the permissive behavior.
2. **[RESOLVED] `initial_tier` fork (local vs extend reducer)?** — Keep **local** to metrics. One consumer, a distinct fold (first-seed latch), and deliberately-different vocab tolerance (forensic fidelity) that the gate readers must not adopt. A-Option-2 (grow `LifecycleStateReduction`) is rejected.
3. **[RESOLVED] Pure-reducer input contract / `skipped_lines` impedance?** — Core returns bare `(state, rejected_positions)` over `Iterable[dict]`; the Path shell owns parsing, line numbers, the merge into `skipped_lines`, and the `LifecycleStateReduction`/`corrupted` wrapper. Metrics ignores `rejected_positions`. This dissolves the synthetic-lineno footgun and keeps the NamedTuple a shell concern.
4. **[RESOLVED] Consumer behavior-preservation?** — All 5 consumers of `reduce_lifecycle_state` use named attribute access; the Path wrapper keeps its signature and tolerant-read contract, so consumers are unaffected. The existing `test_reduce_lifecycle_state.py` suite (esp. per-value :84, torn-lineno :57, `test_corrupt_*`) is the regression net; watch the `:100` equality assertion.
5. **[DEFERRED to Spec — scope decision] Latent non-UTF-8 crash in `parse_events`.** `parse_events` (strict utf-8) crashes the metrics pipeline on a byte-corrupt log while `read_tier` survives. This is independent of the fold consolidation and the title's "agree by construction" does not cover it. **Spec must decide:** (a) in-scope — harden `parse_events` to `errors="replace"` to match the reducer's tolerant intake; (b) out-of-scope — file a separate bug ticket and state the consolidation only unifies the fold, not the intake. *Deferred: this is a genuine product/scope decision for the spec interview, not resolvable by reading code.*
6. **[DEFERRED to Spec — scope decision] Parity-harness coverage gap.** The metrics tier fold is absent from the systematic parity harness. **Spec must decide** whether the deliverable includes adding `extract_feature_metrics` to `test_bin_lifecycle_state_parity.py`'s matrix (with out-of-vocab + re-seed cases) — this has genuine standalone value regardless of whether the fold is consolidated, and under Approach B it becomes the regression guard. *Deferred: depends on the chosen approach (B vs C), which is a §4 spec decision.*
7. **[DEFERRED — moot/monitoring] `initial_tier` byte-identity under `lifecycle_start` re-seed.** The audit verified the final-tier axis, not `initial_tier` under a second `lifecycle_start`. Moot under the recommended design (`initial_tier` stays local and unchanged), so no real-data risk. *Deferred: only relevant if Spec overrides OQ2 and moves `initial_tier` into the core.*
