# Research: Eliminate the duplicate _read_tier in cortex_command/overnight/report.py by switching callers to cortex_command/common.py:read_tier, and decide the disposition of bin/cortex-audit-tier-divergence once a single canonical reader remains

## Codebase Analysis

### The two implementations

- `cortex_command/common.py:read_tier` (line 444) — public, lru_cache-wrapped via `_read_tier_inner` (line 406) keyed on `(path, exists, mtime_ns, size)` via `_stat_key`. Signature: `read_tier(feature, lifecycle_base=Path("lifecycle"))`. Parses events.log line-by-line via `json.loads`, silently skips malformed lines, and inspects `record.get("event")` without case normalization. Public API contract published via `read_tier.__wrapped__` at line 469 for introspection.
- `cortex_command/overnight/report.py:_read_tier` (line 746) — private, no cache. Signature: `_read_tier(feature)`. Parses via `read_events()` (`overnight/events.py:248`), which (a) emits `warnings.warn` on malformed JSON, (b) **lowercases the `event` field** for backward compat with archived logs, (c) requires the `"event"` key.

### Semantic divergence (subtle, low-risk)

The two implementations are *behaviorally* equivalent on the current in-tree corpus but differ on a fringe edge: `read_events()` lowercases event names, so an events.log line with `"event": "LIFECYCLE_START"` is correctly classified by `report._read_tier` but not by `common.read_tier`. No in-tree log uses uppercase event names (the `test_read_tier_parity.py` case-iv corpus sweep passes). Captured as an Open Question.

### Callers and call sites

- `cortex_command/overnight/report.py:535` — sole production callsite of `_read_tier`, inside `_render_feature_block`. Called once per feature in the morning-report render loop.
- `cortex_command/overnight/outcome_router.py:830` — sole production callsite of `common.read_tier`. Already on the canonical reader; unchanged by this work.
- `cortex_command/overnight/tests/test_report.py` — ~13 in-test references to `_read_tier` (precise count to be verified during implementation; lines ≈ 339, 344, 498, 508, 515, 525, 532, 539, 591, 602, 635, 651, 663, 677, 688, 699, 720, 730, 740, 743, 752, 756, 759, 773). All tests already `monkeypatch.chdir(tmp_path)`, so the no-arg `read_tier(feature)` form continues to work after import-swap.
- `tests/test_outcome_router.py:85,306,352` and `cortex_command/overnight/tests/test_lead_unit.py:1666,1696,1731,1766,1805` — patch `cortex_command.overnight.outcome_router.read_tier` (the *binding name* in outcome_router). These remain valid post-consolidation; the binding name does not change.

### Audit gate ecosystem (files affected if retired)

- `bin/cortex-audit-tier-divergence` (189 lines) — Python script; pre-commit Phase 1.9 wired in `.githooks/pre-commit:172-197`; justfile recipe at `justfile:360-361`.
- `plugins/cortex-core/bin/cortex-audit-tier-divergence` — dual-source mirror managed by `.githooks/pre-commit` Phase 4 (lines 235-258) and `just build-plugin` (justfile lines 507-539, rsync with `--delete`). Mirror cleanup is automatic on next `just build-plugin` after source deletion.
- `tests/test_audit_tier_divergence.py` (93 lines) + fixture tree at `tests/fixtures/audit_tier/`.
- `tests/test_read_tier_parity.py` (162 lines) — guards parity between the two readers; becomes vacuous after consolidation. Canonical-rule cases (i, ii, iii) still pin semantics for the remaining reader. Disposition is an Open Question.

### Cache invalidation contract

`_stat_key` returns `(exists, mtime_ns, size)`. The cache invalidates when any of those change. The morning report loop (`for name in groups[repo_path]`) reads each feature once per render, so the cache provides no in-report speedup — but each callsite of `common.read_tier` shares the same `_read_tier_inner` cache (lru_cache maxsize=128) across the process. Migrating the report.py callsite is a strict perf-neutral-or-positive change.

### Import boundary and conventions

- `cortex_command/overnight/report.py:25` already does `from cortex_command.common import _resolve_user_project_root, atomic_write, slugify`. Add `read_tier` to that import.
- Absolute imports throughout overnight/. No relative-import pattern in use.
- `/cortex-core:commit` skill required for commits; never `git commit` manually.
- Dual-source enforcement (`just build-plugin`) runs automatically via pre-commit Phase 4; manual `just build-plugin` not required, but pre-commit will block if the mirror drifts mid-commit.
- Retired surfaces documented in `CHANGELOG.md` per `requirements/project.md:23`.

## Web Research

### lru_cache with stat-keyed invalidation

The `(path, exists, mtime_ns, size)` key tuple matches the canonical recipe for stat-keyed lru_cache invalidation. Known gotchas, none of which block this work:

- **mtime resolution is filesystem/OS-dependent.** apenwarr's "mtime comparison considered harmful" documents that ext4 supports nanosecond mtime; HFS+ and many NFS exports do 1-second; FAT/exFAT do 2-second. Pairing mtime with size (already done) catches "same-time, different-size" edits.
- **Sub-granule races** remain possible (same-time, same-size edits within one tick). Lifecycle events.log files do not churn at sub-ms rates; acceptable residual risk.
- **macOS mmap quirk:** mtime bumps only on `msync()`. Not relevant — events.log is written via plain file writes / `os.rename`.
- **Free-threading contention** (CPython issue #131757): `functools.lru_cache` serializes concurrent calls to the same key under free-threading. Not a correctness bug; cortex-command does not use free-threaded CPython.
- **Forked processes** inherit the cache dict as a snapshot, then independent. Fine for read-only state.

### Audit-gate disposition pattern

The **strangler-fig** lineage applies directly: once the façade has fully replaced the duplicate, the scaffolding (parity gate) should be removed, not preserved as "defense in depth." Falco PR #1976 ("deprecate PSP regression tests") is a concrete precedent — parity tests went away with the deprecated code path rather than being repurposed.

Synthesized principle: a divergence-audit check is a *structural* invariant ("two implementations agree"). When the structural condition disappears, the invariant is vacuously true and the gate produces no signal — retire, don't preserve. Repurposing is only justified if a **different**, still-live invariant can be expressed through the same harness; that would be a new tool, not a renamed legacy gate.

### Single-source-of-truth refactor sequence (consensus)

1. Pin behavior on the canonical with a regression test (already done in `test_read_tier_parity.py`).
2. Import-graph sweep for every caller of the duplicate (manual call-site enumeration is the most common miss).
3. Migrate callers in one mechanical pass — no interleaving with behavior changes.
4. Delete the duplicate in the same commit.
5. Delete the parity test along with the duplicate — keeping it pinned against a single implementation is tautological.

### Caller-migration safety (Python)

- **"Patch where it's used, not where it lives."** Tests that monkeypatch `cortex_command.overnight.report._read_tier` silently become no-ops after the caller imports `read_tier` from `common`. Audit for this pattern; none observed in the current test suite.
- **Dynamic dispatch / `getattr` / string-based imports** are the second-biggest miss vector. A static grep for `_read_tier` plus `read_tier` (string form) covers it.
- **Shadowed names / re-exports.** No `_read_tier` re-export observed.

### Key URLs

- [apenwarr: mtime comparison considered harmful](https://apenwarr.ca/log/20181113)
- [CPython issue 131757: lru_cache serializes under free-threading](https://github.com/python/cpython/issues/131757)
- [Azure Architecture Center: Strangler Fig Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/strangler-fig)
- [Falco PR #1976: deprecate PSP regression tests](https://github.com/falcosecurity/falco/pull/1976)
- [pytest monkeypatch docs](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)

## Requirements & Constraints

### Project.md

- **Workflow trimming (line 23)**: "Hard-deletion is preferred over deprecation notices, tombstone skills, or env-var soft-deletes when the surface has zero downstream consumers (verified per-PR). Retired surfaces are documented in `CHANGELOG.md` with replacement entry points." → If the audit gate is retired, hard-delete + CHANGELOG entry is the prescribed shape.
- **Complexity earns its place (line 19)**: Favors the simpler resolution.
- **Maintainability through simplicity (line 38)**: Direct rationale for the consolidation.
- **SKILL.md-to-bin parity enforcement (line 29)**: If `bin/cortex-audit-tier-divergence` is deleted, the justfile recipe, pre-commit Phase 1.9, test file, and fixtures must be deleted atomically — `bin/cortex-check-parity` will block a half-deletion.
- **Two-mode gate pattern (line 32)**: The audit currently runs only as `--staged` mode wired off pre-commit Phase 1.9. Repurposing it as an `--audit`-only on-demand check is the precedent's shape *if* there is residual value — but per the strangler-fig finding above, the structural invariant disappears with the duplicate.

### Pipeline.md / observability.md

- No constraint pins `_read_tier`'s shape or location.
- The morning report path is invoked via `python3 -m cortex_command.overnight.report` (observability.md:144); pipeline.md imposes no internal-helper constraints.
- `outcome_router.py:830` review-gating must continue to route correctly (covered by existing gating-matrix tests).

### Scope explicitly carried forward from #190

Per `lifecycle/promote-lifecycle-state-out-of-eventslog-full-reads/spec.md:29`, the #190 spec excluded "Python writer code" changes; `report.py` is a *reader*, not a writer, so the non-requirement does not block this work. Backlog #199 explicitly invites the audit-gate disposition decision (line 42) without commitment to either retirement or repurposing.

### Audit gate's stated purpose (`bin/cortex-audit-tier-divergence:17-21`)

> "Any divergence between these two reads means a stray non-override `tier` field appears in the events log after a `complexity_override` — a regression risk that would silently shift routing if the canonical reader were rolled back."

The audit compares `read_tier_last_wins` (legacy semantic) vs `read_tier_canonical` (current semantic) against the corpus. Once the duplicate reader is removed, the "two reads" framing is undefined; the audit's purpose dissolves.

## Tradeoffs & Alternatives

### Consolidation approach

**A. Direct swap (mechanical) — RECOMMENDED.** Replace the single call site at `report.py:535` with `common.read_tier(name)`. Delete `_read_tier` (`report.py:746-778`). Update the ~13 test imports in `cortex_command/overnight/tests/test_report.py`. Add `read_tier` to the existing `from cortex_command.common import …` at `report.py:25`.
- **Pros:** Minimal change (~30 net lines deleted + import edits). Inherits stat-keyed cache. Aligns with project's workflow-trimming and "single canonical reader" principles. Behavior preserved by existing `test_read_tier_parity.py` case-(iv) corpus sweep.
- **Cons:** Subtle lowercase-event-name semantic difference between `read_events()` and `common._read_tier_inner` becomes a (silent) behavior change. No in-tree corpus uses uppercase events; risk is theoretical. Captured as Open Question.

**B. Direct swap + cache hot-path tuning.** Same as A, plus audit lru_cache size for the new caller pattern.
- **Pros:** Theoretically more rigorous.
- **Cons:** Overshoots. Morning report iterates each feature once; cache benefit is for the `outcome_router` round loop, not report.py. No evidence the default 128 is wrong. Gold-plating; rejected.

**C. Promote a richer canonical reader.** Widen `read_tier` to return `(tier, source_event, lifecycle_path)`.
- **Pros:** Future-proofs against hypothetical consumers.
- **Cons:** Speculative — no current caller needs the extras. Breaks the `outcome_router.py:830` signature. Violates "prescribe what and why, not how." Hard-reject.

### Audit-gate disposition

**X. Retire entirely — RECOMMENDED.** Delete `bin/cortex-audit-tier-divergence` (189 lines), `tests/test_audit_tier_divergence.py` (93 lines), `tests/fixtures/audit_tier/`, justfile recipe at `justfile:360-361`, pre-commit Phase 1.9 block at `.githooks/pre-commit:172-197`, and the plugin mirror at `plugins/cortex-core/bin/cortex-audit-tier-divergence` (auto-deleted by next `just build-plugin` / pre-commit Phase 4 sync).
- **Pros:** The audit's stated purpose ("any divergence between these two reads") is structurally impossible after consolidation. Removes ~310 lines + pre-commit latency. Aligns with project's workflow-trimming preference. Strangler-fig precedent: scaffolding goes away with the duplicate.
- **Cons:** A future contributor *could* reintroduce a divergent reader; normal code review + preserved canonical-rule tests catch this.

**Y. Repurpose as corpus-data audit.** Strip dual-reader comparison; keep an events.log shape check. Move out of pre-commit; expose only as `just audit-tier-divergence` (on-demand).
- **Pros:** Preserves diagnostic surface; aligns with two-mode gate pattern in theory.
- **Cons:** The "corpus shape" the script checks is *defined as* divergence-between-readers; there is no independent shape invariant once one reader exists. Rewriting it for a new invariant is a *new* tool dressed as repurposing. On-demand-only with no current invariant means "kept in case someone wants it" — the deprecation anti-pattern project.md explicitly rejects. Reject.

**Z. Keep as-is.**
- **Pros:** Zero work.
- **Cons:** Pre-commit gate runs a check whose premise no longer holds; latency on every `common.py` / `report.py` edit for zero signal. Accumulates the exact technical debt the trimming principle exists to prevent. Reject.

### Recommendation

- **Consolidation: A (direct swap).**
- **Audit-gate: X (retire entirely).**
- **Test corpus cleanup**: delete `tests/test_audit_tier_divergence.py` and `tests/fixtures/audit_tier/`; preserve canonical-rule cases (i–iii) from `tests/test_read_tier_parity.py` by either keeping the file (re-cast as a "canonical rule" test) or migrating its cases into `tests/test_common_utils.py`. Disposition handled in Open Questions.
- **CHANGELOG.md entry** for the retired audit surface per `requirements/project.md:23`.

## Open Questions

1. **Lowercase-event-name semantic divergence.** `report._read_tier` (via `read_events()`) lowercases event names for backward compat with archived logs; `common.read_tier` does not. The in-tree corpus has no uppercase events today, so the consolidation is a silent behavior change only for hypothetical archived logs. **Proposed resolution**: accept the canonical reader's stricter behavior. The lowercase normalization is documented in `events.py:282-284` as "backward compat with archived logs"; if archive readability becomes a requirement later, normalize in `_read_tier_inner` then. Defer.

2. **Disposition of `tests/test_read_tier_parity.py` (162 lines).** Two options:
   - **(a)** Delete entirely. The parity premise (two readers agree) is gone.
   - **(b)** Preserve canonical-rule cases (i, ii, iii) — `lifecycle_start`-only, `lifecycle_start + complexity_override`, multiple-override-last-wins — by migrating them into `tests/test_common_utils.py` or renaming the file to `test_read_tier_canonical_rule.py`. The case-(iv) corpus sweep can be dropped (it was the parity-vs-fixture safety net).
   - **Proposed resolution**: option (b) — migrate the rule cases. They pin the semantic that `outcome_router.py:830` depends on; a future regression in `read_tier` should still fire a test. Resolve in spec.

3. **CHANGELOG entry shape.** `requirements/project.md:23` requires retired surfaces be documented in `CHANGELOG.md` with replacement entry points. The replacement for the audit gate is "code review + canonical-rule tests in `test_common_utils.py`." Spec should pin the CHANGELOG entry's content.
