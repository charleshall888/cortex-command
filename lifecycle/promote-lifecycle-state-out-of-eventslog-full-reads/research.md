# Research: promote-lifecycle-state-out-of-eventslog-full-reads

Topic: Promote lifecycle state (`criticality`, `tier`, `tasks_total`, `tasks_checked`, `rework_cycles`) out of full-file reads of `events.log` / `plan.md` / `review.md` into a structured, concurrency-safe read store with incremental-migration fallback. Evaluate state.json, index.md frontmatter, central index, and reader-wrapper mechanisms; design reader surface and write-coordination across `runner.py`, `outcome_router.py`, `feature_executor.py`, and skill-prompt emitters under the project's no-lock concurrent-writer constraint.

## Codebase Analysis

### Readers to eliminate / unify

- `cortex_command/common.py:143-272` — `detect_lifecycle_phase()` runs a 6-step state machine that does `events_log.read_text(errors="replace")` then `'"feature_complete"' in content` (`:197`), full-reads `plan.md` for `\*\*Status\*\*: ... [x]` checkbox regex (`:173-179`), and full-reads `review.md` for `"verdict"\s*:\s*"([A-Z_]+)"` verdict regex (`:182-192`). Called by 5 prod sites: `cortex_command/common.py:574` (CLI), `backlog/generate_index.py:149`, `dashboard/data.py:312` and `:933`, `dashboard/seed.py:535`, `hooks/cortex-scan-lifecycle.sh:247-250`, plus heavy test fixtures at `tests/test_lifecycle_state.py:28` and `tests/test_lifecycle_phase_parity.py:320,438`.
- `cortex_command/common.py:279-313` — `read_criticality()` full-reads `events.log`, JSON-parses every line, returns most-recent `criticality` field; default `"medium"`. Callers: `cortex_command/overnight/runner.py:40,2442`, `outcome_router.py:23,831`, `feature_executor.py:27,618`.
- `cortex_command/common.py:320-354` — `read_tier()` identical structure, default `"simple"`. Caller: `outcome_router.py:24,830`.
- `cortex_command/overnight/report.py:746-778` — `_read_tier()` parallel implementation using `read_events()` with **lifecycle_start → complexity_override `to` supersession**. **This is the canonically-correct rule; `common.py:read_tier()` uses a simpler "last `tier` field wins" rule and silently disagrees with `report.py` when a non-override event carries a stray `tier` field (e.g., `batch_dispatch` per `skills/lifecycle/references/implement.md:163`).** Today `outcome_router.py:830` consumes the non-canonical `common.py` rule; unifying readers requires explicit semantic-alignment first or risks silent behavioral change in review-gating.
- `skills/lifecycle/references/complete.md:25-26` — checkbox-count regex over `plan.md` for `tasks_total`; verdict-count over `review.md` for `rework_cycles`. The audit's "weakest consumer-value ratio" case (two integers from two full-file reads).
- 10+ duplicate skill-prompt scan-events.log stanzas: `skills/lifecycle/SKILL.md:79,81`; `references/plan.md:21,269`; `references/specify.md:147`; `references/orchestrator-review.md:7`; `references/implement.md:246`; `skills/refine/SKILL.md:159`; `skills/dev/SKILL.md:126`; `skills/morning-review/references/walkthrough.md:237`.

### Writers (state-bearing emit sites)

**Python (autonomous pipeline)**:

- `cortex_command/pipeline/review_dispatch.py:190,281,529` — `phase_transition` (implement→review, review→complete)
- `:287,535` — `feature_complete` (carries `tasks_total`, `rework_cycles`)
- `:205,232,274,301,318,336,522,548,571` — `review_verdict` (carries `cycle`)
- `bin/cortex-complexity-escalator:192-205` — `complexity_override` with read-after-write verification (`:208-235`)

**Skill prompts (Claude-driven)**:

- `skills/lifecycle/SKILL.md:240` — `lifecycle_start` (baseline `tier` + `criticality`)
- `skills/lifecycle/SKILL.md:284` — `criticality_override`
- `skills/lifecycle/references/{plan,specify,implement,review,complete}.md` — `phase_transition`, `feature_complete`, `review_verdict` emit sites
- `skills/morning-review/references/walkthrough.md:259-262,279-280` — **third writer class**: emits phase_transition + review_verdict + feature_complete when reconciling stale lifecycles. Walkthrough lines 274-284 explicitly contemplate crash-recovery sequences where morning-review writes for features the runner was active on minutes earlier. This is a **documented overlap with autonomous-pipeline writers**, not a theoretical race.

### Canonical patterns

- **Atomic write** at `cortex_command/common.py:482-522` `atomic_write(path, content, encoding)` — `tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")` → `os.write` → `durable_fsync(fd)` (F_FULLFSYNC on macOS) → `os.replace`. Used by `cortex_command/overnight/state.py:421-464,467,517+` (`save_state`, `save_batch_result`, `save_daytime_result`) and `cortex_command/overnight/sandbox_settings.py:222-253` (per-spawn 0o600 settings).
- **JSON state precedent**: `lifecycle/overnight-state.json`, `lifecycle/sessions/{id}/runner.pid` (0o600), `~/.cache/cortex-command/scheduled-launches.json`, `lifecycle/sessions/{id}/sandbox-settings/cortex-sandbox-*.json` (0o600). Pattern: integer `schema_version`, strict-equality drift guard with `RuntimeError` (`orchestrator_context.py:128`, `_EXPECTED_SCHEMA_VERSION = 2`), tolerant-reader for forward-compat (`load_state` treats `schema_version=0` as legacy at `state.py:248-250`).
- **No read locks**: `requirements/pipeline.md:127,134` — permanent architectural constraint; writers use atomic `os.replace`; readers may observe pre-replace content; forward-only transitions make this safe.

### Post-#189 baseline

`bin/.events-registry.md` is the post-#189 governance gate. Registry-`live` and still emitted from skill prompts: `lifecycle_start`, `criticality_override` (gate-enforced), `complexity_override` (manual but registered), `phase_transition`, `feature_complete`, `batch_dispatch`, `review_verdict`, `dispatch_complete`, `clarify_critic` (v3), `plan_comparison`. Deprecated-pending-removal (grandfather window through 2026-06-10): `confidence_check`, `discovery_reference`, `implementation_dispatch`, `orchestrator_review`, `orchestrator_dispatch_fix`, `orchestrator_escalate`, `requirements_updated`, `task_complete`, decompose_*. **All state-bearing events this ticket depends on are still live**, but the registry's deprecation mechanism (`grandfather window until 2026-06-10` per `events-registry.md:96-106`) is a precedent that *could* prune fallback sources later — making "events.log fallback persists indefinitely" a load-bearing assumption that needs an explicit registry-pin if the design relies on it.

### Index.md current shape

Index.md is genuinely passive today. Frontmatter carries `slug, title, backlog_filename, artifacts: [], created, updated`; only known programmatic reader is `skills/lifecycle/references/review.md:14` extracting `tags` for review-targeting. Writers: lifecycle SKILL initial creation (`:123-157`) and per-phase artifact-append rewrites at `references/plan.md:257-261` and `references/review.md:149-153`. Promoting state fields here mutates a previously-passive file.

### Alternative-exploration prior recommendations (verbatim treatment)

`research/lifecycle-discovery-token-audit/research.md:49,55` framed the *minimal* audit-side fix as hoisting reads to a `cortex-read-criticality` bin invocation (with optional `grep -F` / `deque(f, maxlen=200)` tail-read), and Item #13 (`:114`) for `complete.md`'s JSON helper for two integers. DR-1 in that audit is about dispatch-payload paths-not-content (unrelated). **The audit did not recommend a structured read-store**; the four candidates in `backlog/190` Research hooks are an upgrade of the audit's recommendation, not a direct adoption. Treat the read-store framing as evaluated input, not pre-validated.

## Web Research

### Concurrent file-based state without locks (prior art)

- **Git refs / `.git/HEAD`** — `O_CREAT|O_EXCL` lockfile pattern: write `path.lock`, atomic-rename onto `path`. Readers never block. Stale `.lock` is a known operational hazard ([Git lockfile API](https://git-scm.com/docs/api-lockfile), [git-update-ref](https://git-scm.com/docs/git-update-ref)). **Lock-with-retry**, not lock-free.
- **Jujutsu (jj) operation log** — the canonical lock-free design: append-only DAG of operations with view objects (snapshots). On load, multiple heads trigger 3-way view merge with conflict markers. Works on filesystems with no flock ([jj concurrency](https://jj-vcs.github.io/jj/latest/technical/concurrency/)). Most aligned prior art with cortex's no-lock constraint — but keeps the **event log as authority** and reconstructs state.
- **Terraform** abandoned the lockless model — 1.10+ uses S3 conditional writes (`If-None-Match`) + `.tflock` sidecar ([Terraform S3 native locking](https://www.bschaatsbergen.com/s3-native-state-locking)). **Takeaway: for mutable shared state, even hyperscale tooling concludes coordination is required**; lock-free patterns are restricted to append-only logs.
- **Restic** — separates append-only data files (write-once-never-modified) from a *coordinated* index ([Restic Design](https://restic.readthedocs.io/en/v0.4.0/Design/)). Directly analogous: append-log as authority, derived index as cache.
- **npm/write-file-atomic** — serializes concurrent same-file writes via in-process Promise queue. Cross-process: pure last-writer-wins after atomic rename ([write-file-atomic](https://github.com/npm/write-file-atomic), [#64](https://github.com/npm/write-file-atomic/issues/64)).

### Event-log → snapshot promotion

Convergent guidance ([Kurrent live projections](https://www.kurrent.io/blog/live-projections-for-read-models-with-event-sourcing-and-cqrs), [Snapshotting (domaincentric)](https://domaincentric.net/blog/event-sourcing-snapshotting), [Martin Fowler EventSourcing](https://martinfowler.com/eaaDev/EventSourcing.html)): **snapshots are an optimization, not a correctness primitive**. Implement only when measurements confirm read latency correlates with event count. CQRS read-stores are materialized views, typically projected asynchronously. Application state is always derivable; cache anywhere; the log is authority.

### JSON schema versioning

Integer `schema_version` preferred over semver ([Schema versioning for JSON config](https://offlinetools.org/a/json-formatter/schema-versioning-for-json-configuration-files), [Creek evolving JSON schemas](https://www.creekservice.org/articles/2024/01/08/json-schema-evolution-part-1.html)). Loader pipeline: parse → detect version → validate → migrate one step at a time → hand normalized to app. Lazy migration with fallback-read preferred over eager bulk for backwards-compatible additions ([NoSQL schema evolution paper](https://www.verwertungsverbund-mv.de/storages/uni-rostock/Alle_IEF/Informatik/Homepages/Meike_Klettke/scdm-2016-proceedings.pdf)).

### YAML frontmatter mutation hazards

Confirmed anti-pattern. Obsidian's `app.fileManager.processFrontmatter()` is known-hazardous under concurrent edits ([Obsidian forum](https://forum.obsidian.md/t/updating-frontmater-programatically/53594), [Templater #1387](https://github.com/SilentVoid13/Templater/issues/1387)). ruamel.yaml round-trip preservation is fragile under restructuring ([ruamel.yaml PyPI](https://pypi.org/project/ruamel.yaml/), [Reorx PyYAML tips](https://medium.com/@reorx/tips-that-may-save-you-from-the-hell-of-pyyaml-572cde7e1d6f)).

### Atomicity ≠ durability ≠ no-lost-update

- `os.replace()` is POSIX-atomic for same-volume rename ([Python atomic file updates](https://thelinuxcode.com/python-osreplace-for-safe-atomic-file-updates-in-real-systems/), [LWN atomic writes](https://lwn.net/Articles/789600/)).
- Atomicity ≠ durability: ext4 delayed allocation can lose new file contents on crash without `fsync(tmp)` + `fsync(dir)` ([ext4 and data loss LWN](https://lwn.net/Articles/323067/), [evanjones.ca durability](https://www.evanjones.ca/durability-filesystem.html), [leveldb #195](https://github.com/google/leveldb/issues/195)).
- **Atomic rename does NOT prevent lost-update under concurrent RMW** ([npm/write-file-atomic #64](https://github.com/npm/write-file-atomic/issues/64)). Defenses: (a) single-writer-per-key, (b) CAS-with-retry on version field ([Wikipedia OCC](https://en.wikipedia.org/wiki/Optimistic_concurrency_control), [CAS](https://en.wikipedia.org/wiki/Compare-and-swap)), (c) treat file as rebuildable cache and rebuild from log on conflict (jj-style).

### Recommendation hierarchy from web research

1. **First-choice**: parser-cache via reader-wrapper (no snapshot, no new file). Bounded read surface (single helper / `functools.lru_cache` over file mtime, or `cortex-read-state` bin). Justified by Kurrent/domaincentric "only when measurements demand" rule.
2. **Second-choice (if (1) insufficient)**: per-feature `state.json` as **rebuildable cache**, not authority. Readers fall back to `events.log` scan when `state.json` is missing/stale. Writers use last-writer-wins atomic-replace. Lost-update tolerated because the cache is rebuildable.
3. **Reject**: CAS-version-locking (machinery cost for a derived cache); frontmatter mutation (race + ruamel fragility); central state-index (single hot point of contention).

## Requirements & Constraints

### The "without locking" convention

`requirements/pipeline.md:127`: "**Concurrency safety**: State file reads are not protected by locks; the forward-only phase transition model ensures re-reading a new state is safe (idempotent transitions)"

`requirements/pipeline.md:134`: "**State file locking**: State file reads are not protected by locks by design. Writers use atomic `os.replace()`; readers may observe a state mid-mutation, but forward-only transitions make this safe. This is a permanent architectural constraint."

`cortex_command/overnight/orchestrator_context.py:7-10` (in-tree affirmation): "read-only with respect to all state files, lock-free per requirements/pipeline.md:127,134, and performs no in-process caching (each round-spawn gets a fresh read)."

Write-coordination convention: per-file, used only where a true concurrency window exists. Existing flock precedents: `~/.cache/cortex-command/scheduled-launches.lock` (LaunchAgent serialization, `pipeline.md:157`) and `init/settings_merge.py` (per-repo sandbox registration, `project.md:28`). Single-writer state files (`overnight-state.json`, runner.pid, sandbox-settings) rely on atomic-write alone with neither read nor write locks.

### Atomic-write precedent

`pipeline.md:21,126` enforces tempfile + `os.replace` for all session state writes. Canonical implementation at `overnight/state.py:421-464`. Precedent files: `overnight-state.json`, `runner.pid` (0o600), `scheduled-launches.json`, `sandbox-settings/*.json` (0o600), `active-session.json`. `0o600` standard for files carrying process-identity contracts.

### Schema-version convention

Documented repo-wide convention. Integer field (occasionally string for YAML); strict-equality `_EXPECTED_SCHEMA_VERSION` constant + `RuntimeError` drift guard; `dict.get(..., 0)` semantics for legacy fallback (`state.py:248-250`). Backlog YAML frontmatter uses `schema_version: "1"` as a required field (`docs/backlog.md:16,44`).

### Audit-trail vs structured-state separation

`pipeline.md:129`: "**Audit trail**: `lifecycle/pipeline-events.log` provides an append-only JSONL record of all dispatch and merge events." `bin/.events-registry.md` distinguishes `live` events (with programmatic reader) from `audit-affordance` events (human-skim only, `events-registry.md:24`). Tolerant-reader semantics (`events-registry.md:72`): "readers silently skip unknown event names, so archive data is never broken by registry pruning." Requirements **do not** state that events.log is the canonical source for structured lifecycle state — that's an emergent reading by `common.py:read_criticality/read_tier`.

### Scope boundaries

- Per-feature artifacts (`lifecycle/{feature}/...`) — owned by lifecycle skill. A new state file plausibly belongs here.
- Per-session artifacts (`lifecycle/sessions/{id}/...`) — owned by overnight runner.
- Repo-wide lifecycle artifacts — `master-plan.md`, `pipeline-events.log`, `metrics.json`, `morning-report.md`, `deferred/`.
- `project.md:27`: "File-based state... No database or server... simplicity is preferred." Not exiting file-based state.
- `project.md:64` (Deferred): "Migration from file-based state if/when complexity demands it" — explicitly classified deferred, not banned.
- Out-of-scope subsystems confirmed: `observability.md:93` ("All three subsystems are read-only with respect to session state files"); `multi-agent.md` and `remote-access.md` no relevant constraints.

## Tradeoffs & Alternatives

### A — Per-feature `lifecycle/<feature>/state.json`

Small JSON file with `schema_version: 1` and the promoted fields. Written via the canonical `atomic_write` helper. New Python helper `cortex_command/common.py:load_lifecycle_state(slug) -> dict | None`. Fallback: when state.json absent, callers fall back to existing `read_criticality`/`read_tier`/plan-scan path.

- Implementation complexity: **LOW-MEDIUM** (~1 helper, ~2-3 writer-side edits, ~5-7 skill-prompt stanzas + fallback path).
- Maintainability: **HIGH** (follows the canonical JSON-state precedent: `overnight-state.json`, `preconditions.json`, `critical-review-residue.json`).
- Performance: **HIGH** for criticality/tier and counter reads (O(small parse) replaces O(events.log scan)).
- Alignment: **HIGH** with `project.md:27` "JSON for structured state" and `pipeline.md:126` atomic-write precedent.
- Cons: introduces a new file type per lifecycle dir; **RMW lost-update hazard for counter fields** (`tasks_checked`, `rework_cycles`) under concurrent writers — see Adversarial.

### B — `lifecycle/<feature>/index.md` YAML frontmatter

Add fields to existing index.md frontmatter.

- Implementation complexity: **MEDIUM-HIGH** (frontmatter round-trip preserving body + RMW-conflict handling).
- Maintainability: **MEDIUM** (single-file co-location; writer-discipline overhead is real).
- Performance: **MEDIUM** (read-whole-file-to-write-frontmatter scales with body size).
- Alignment: **LOW-MEDIUM** (conflicts with implicit JSON-for-structured-state convention; semantic break — passive→mutable).
- **Web research confirms anti-pattern**: Obsidian/Templater race + ruamel.yaml fragility. **Reject**.

### C — Centralized state index (`lifecycle/state-index.json`)

Single JSON keyed by feature slug.

- Bulk-read win is real but small (1-2 callsites: `runner.py:2442` scanning all features).
- **Global contention point**: every per-feature mutation rewrites the global file; converts per-feature races into all-features-vs-all races.
- No precedent for authoritative central state (closest analog `backlog/index.json` is a regenerated cache, not authority).
- Implementation complexity: **HIGH**. Maintainability: **LOW**. Alignment: **LOW**. **Reject**.

### D — Reader-wrapper / cache layer

Keep state authoritative in events.log; add `functools.lru_cache` on `(feature, events.log mtime)` or `cortex-lifecycle-state` bin returning JSON.

- Zero migration, minimal blast radius, no writer coordination.
- **Does not solve `complete.md` plan+review reads** — those live in plan.md/review.md, not events.log.
- Cross-process cache invalidation via mtime works but skill-prompt callers spawn fresh processes → in-process cache is per-spawn.
- The adversarial review's framing: this is **Web research's first-choice**, and the audit's actual measurements may not justify going beyond it.

### Field-set recommendation

In: `criticality`, `tier`, `tasks_total`, `tasks_checked`, `rework_cycles`. Add `schema_version` (mandatory) and `updated` (ISO 8601, mirrors index.md convention).

Out — `phase`: keep derived. Write-frequency objection (10×-50× write amplification for no read-cost win) — but see Adversarial #12 challenging this.

Out — `complexity_override`/`criticality_override` historical reasons: state.json carries effective-current-value only; the historical trail stays in events.log.

### Write-coordination recommendations

- **W1 (`fcntl.LOCK_EX`)** — violates `pipeline.md:134` no-lock constraint. **Reject**.
- **W2 (field-partitioning)** — runner/lifecycle-skill own classification fields; pipeline/feature_executor own counter fields. Compatible with the no-lock constraint; depends on whether two processes can simultaneously write the *same* field.
- **W3 (CAS-version-locking)** — `version: N` field on RMW; reader captures version, writer checks before rename, retries on mismatch. Web research and Adversarial both surface as the *correct* defense if W4 doesn't hold.
- **W4 (single-writer-per-lifecycle)** — claimed via existing orchestrator-singleton constraint. **Adversarial documents three concrete races that falsify this** — see below.

Tradeoffs agent's recommendation was W2+W4 hybrid + Alternative A; the adversarial review reshapes this.

## Adversarial Review

### Falsified assumptions (ranked)

1. **W4 single-writer-per-lifecycle is empirically false.** Three concrete races identified:
   - **(1a) Pipeline-Python vs user-interactive Claude**: `cortex_command/pipeline/review_dispatch.py:189` writes phase_transition during overnight; user may simultaneously invoke `/cortex-core:lifecycle` for paused-run triage. No `runner.pid`-style lockfile cross-checked in lifecycle SKILL prevents this; the only `kill -0` guard at `references/implement.md:67` only blocks new batch-dispatch, not arbitrary state writes (e.g., `criticality_override` at SKILL.md:281-284 has no PID guard).
   - **(1b) Morning-review is a third writer class by design**: `skills/morning-review/references/walkthrough.md:254-263` writes `phase_transition implement→review`, `review_verdict APPROVED cycle:0`, `phase_transition review→complete`, `feature_complete`. Walkthrough lines 274-284 explicitly contemplate "crash recovery" sequences where morning-review completes writes the pipeline started minutes earlier. W4 is **violated by design**.
   - **(1c) `bin/cortex-complexity-escalator` runs as subprocess from a `/cortex-core:lifecycle` session** and emits `complexity_override` while the parent session emits `phase_transition` — tight interleave can produce RMW lost-update; both `os.replace` succeed atomically, second wins.

2. **Authority contract is incoherent between Web (cache) and Tradeoffs (authoritative).** Concrete failure: pipeline writes `state.json {tier: "complex"}`, then a Claude session forgets state.json but writes `complexity_override → simple` to events.log. Next reader sees state.json present → reads "complex"; events.log says "simple." `outcome_router.py:830 requires_review()` mis-routes silently. No explicit conflict-resolution rule was proposed by Tradeoffs.

3. **events.log fallback is not safe indefinitely.** `bin/.events-registry.md:96-106` documents `grandfather window until 2026-06-10` for deprecated event types. A future epic-187 child could mark `criticality_override` as `audit-affordance` or `deprecated-pending-removal` once state.json is canonical; the moment skill prompts stop emitting it, in-flight pre-migration lifecycles silently lose fallback recovery.

4. **Claude-driven write reliability has no enforcement layer.** Tests in `tests/test_lifecycle_phase_parity.py` test *reader* paths against pre-written fixtures; nothing asserts a running Claude session emits the event after a transition. Failure mode: Claude writes events.log line, forgets state.json. Combined with (2), silent state drift.

5. **`common.py:read_tier` and `report.py:_read_tier` already silently disagree.** `outcome_router.py:830` currently consumes the non-canonical "last tier wins" rule. Unifying readers to `report.py`'s canonical `lifecycle_start→complexity_override.to` rule silently changes review-gating behavior for any feature whose events.log carries a stray `tier` field (e.g., from `batch_dispatch`).

6. **`cycle` regex over review.md prose at `common.py:188-190` is format-fragile.** A future reviewer-prompt rewrite (code-fenced JSON, YAML, alternate verdict format) breaks silently. State.json subsumes this only if writers reliably update it.

7. **Incremental fallback produces inconsistent partial-migration reads.** If state.json covers `criticality, tier, counters` but the phase machine still scans plan.md/review.md, a half-migrated lifecycle can return `tasks_checked = 2` (state.json stale) and `tasks_total = 5` (plan.md fresh) — contradictory snapshot. Needs all-or-nothing per lifecycle ("if state.json complete, use it for all promoted fields; never mix").

8. **F_FULLFSYNC policy unresolved.** ~10-100ms per write on macOS. Cache contract → drop fsync (rebuild is the durability guarantee). Authoritative contract → fsync required, plus crash-between-counter-writes loses second update.

9. **Audit's measurements do not justify the structural shift.** The audit's quantified per-call cost for `read_criticality` is **Tier-3** ("notable, smaller per-occurrence"); the Tier-1 token-waste lines (critical-review artifact duplication ~3-15k tok, SKILL.md description ~2,300 tok) are unrelated to state storage. A parser-cache (`functools.lru_cache` keyed on mtime) plausibly captures 90% of the read-cost win at <5% of the structural-shift complexity.

10. **No value-enum validation on read.** Schema-version drift guard catches version mismatches but not `criticality: "Hi"` typos. State.json becomes a poison-pill vector for `requires_review()`.

11. **Concurrent-writer test infrastructure does not exist.** `tests/test_lifecycle_state.py` uses static fixtures; no `multiprocessing.Process` scaffolding. The backlog acceptance signal "concurrent writers don't corrupt the state under stress" requires new test surface.

12. **Design may optimize the wrong reader.** `detect_lifecycle_phase` (called from the dashboard FastAPI poller at `dashboard/data.py:933` every 2s per feature, plus the per-session scan-lifecycle hook, plus `generate_index`) reads `plan.md` + `review.md`, **not events.log**, for its main work. Promoting criticality/tier alone does not reduce its cost. If state.json is to win the dashboard polling cost, it must carry `phase, checked, total, cycle` — which Tradeoffs explicitly excluded. The write-amplification objection collapses if `phase_transition` events are actually ≤10/lifecycle in practice and the read amplification is `2s × N features × hours`.

### Bottom-line reshaping

The adversarial review recommends downgrading scope:

- Ship the **parser-cache** (Web's first-choice) + **read_tier semantic alignment** (mitigation for #5) as a stand-alone first commit. *Measure*. Only revisit state.json if post-cache measurements still show events.log full-reads as a top-N cost center.
- If state.json must ship now: adopt **rebuildable-cache framing** + **CAS-version-locking** + **skill-prompts-don't-write-state** (rebuild on read). This collapses the W4/authority/Claude-write failure modes simultaneously.

## Open Questions

These are resolution-required for Spec. Mark each Resolved or Deferred-to-Spec before Spec entry.

- **Q1 (mechanism)**: state.json (Tradeoffs' recommendation) vs. parser-cache (Web/Adversarial's recommendation) vs. hybrid (parser-cache first, state.json gated on measurement). Resolution drives the rest of the design.
  - *Deferred: will be resolved in Spec by asking the user. The user must pick whether the ticket lands as the structural shift, the measurement-first parser-cache, or the hybrid sequence.*

- **Q2 (authority contract)**: If state.json ships, is it the authoritative state or a rebuildable cache from events.log? Determines fsync policy, conflict resolution, and skill-prompt write discipline.
  - *Deferred: tightly coupled to Q1. If state.json ships, Spec must pick one contract and propagate it through all design decisions; "rebuildable cache" (Adversarial's recommendation) collapses several failure modes but requires a rebuilder bin.*

- **Q3 (write coordination)**: If state.json ships, W2 (field-partitioning) + W4 (single-writer) is empirically falsified by the morning-review writer class. CAS-version-locking (W3) is the remaining viable defense. Adopt it, or restructure writers to genuinely single-writer (e.g., all writes routed through a rebuilder triggered by events.log mtime)?
  - *Deferred: Spec phase work; depends on Q1+Q2 resolution.*

- **Q4 (read_tier semantic divergence)**: `common.py:read_tier` and `report.py:_read_tier` disagree today. Aligning to the canonical rule is a prerequisite to any unified reader — it can land as a separate first commit, or be folded into this ticket's first PR. Tests-required either way.
  - *Resolved: must land before or as part of this ticket's first PR. Spec must include test fixture covering the divergent case (stray `tier` field on `batch_dispatch` event) and assert the canonical `lifecycle_start → complexity_override.to` rule across both call sites.*

- **Q5 (field-set scope)**: Tradeoffs says criticality+tier+counters; Adversarial argues `phase, checked, total, cycle` may be required for the dashboard hot path. Resolution requires a measurement.
  - *Deferred: Spec must either (a) commit to the minimum field set with a documented measurement-trigger to revisit, or (b) extend to the broader phase-machine fields. Recommend Spec asks the user to choose between scope-minimum and scope-extended, citing the dashboard `data.py:933` 2s poll loop as the load-bearing signal for the broader set.*

- **Q6 (events.log fallback durability)**: `lifecycle_start`, `criticality_override`, `complexity_override`, `feature_complete` are currently registry-`live`. If the fallback path depends on them, should the events-registry gate pin them as `state-source-of-truth` to block future pruning? This is a small policy edit to `bin/.events-registry.md` and `bin/cortex-check-events-registry`.
  - *Resolved: yes — add an explicit registry column or comment noting fallback-source status. Cheap and prevents the silent-rot failure mode.*

- **Q7 (test infrastructure)**: Concurrent-writer test scaffolding (`multiprocessing.Process`) does not exist in `tests/`. Adding it is in-scope for this ticket if state.json ships; out-of-scope if only the parser-cache ships.
  - *Resolved: in-scope conditional on state.json shipping. The backlog acceptance signal explicitly requires "concurrent writers don't corrupt the state under stress (test required)" — Spec must scope the new test module.*

- **Q8 (`detect_lifecycle_phase` regex over review.md prose)**: Format-fragile under future reviewer-prompt rewrites. Out of strict scope today, but Spec should at minimum add a golden-fixture test that breaks first if the reviewer prompt evolves.
  - *Resolved: add the golden-fixture test as a Spec deliverable regardless of Q1's resolution.*

## Considerations Addressed

- **Locate the alternative-exploration's specific state-storage recommendations in `research/lifecycle-discovery-token-audit/research.md` and treat them as evaluated-inputs in the research phase, neither reflexively adopted nor reflexively dismissed.** Addressed: the audit's actual recommendations (`:49,55,111,114`) are a `cortex-read-criticality` bin invocation and a `complete.md` JSON helper for two integers — i.e., the parser-cache pattern, *not* the structured read-store. DR-1 in the audit is about dispatch-payload paths-not-content (unrelated). The four candidates in `backlog/190` Research hooks are an upgrade of the audit's recommendation, not a direct adoption. The adversarial review elevates the audit's actual recommendation as the first-choice option, in tension with the ticket's structural framing — surfaced as Q1.

- **Verify the post-#189 events.log emission shape by reading the actually-landed code (post-commit-6ab3760), not the pre-#189 spec, so this design targets the stable emission baseline rather than a stale assumption.** Addressed: read `bin/.events-registry.md` (the post-#189 governance gate) and confirmed `lifecycle_start`, `criticality_override` (gate-enforced), `complexity_override`, `phase_transition`, `feature_complete`, `review_verdict` are still emitted from registry-live skill-prompt sites. State-recovery fallback can rely on them today. **Caveat surfaced**: the registry's `grandfather window until 2026-06-10` deprecation mechanism means a future epic-187 child could prune fallback sources; surfaced as Q6 with a concrete mitigation (pin them as `state-source-of-truth` in the registry).
