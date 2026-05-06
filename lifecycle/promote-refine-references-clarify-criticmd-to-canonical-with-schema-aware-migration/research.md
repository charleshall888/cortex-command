# Research: Promote skills/refine/references/clarify-critic.md to canonical with schema-aware migration

Topic source: backlog #175. Clarified intent: promote refine's 215-line schema-evolved superset to canonical, delete lifecycle's 167-line legacy copy, rewire `skills/lifecycle/references/clarify.md` §3a, add `schema_version` to the markdown event schema (NOT to `cortex_command/overnight/events.py` since `clarify_critic` is not in `EVENT_TYPES`), and add a real-archived-event replay test as the migration safety mechanism.

> **Critical findings from Adversarial review (verified directly).** Two assumptions that the source ticket and the parallel research agents made are **false** in the current codebase. They reshape the implementation:
>
> 1. **Python legacy-tolerance fallback does not exist.** The markdown spec at `skills/refine/references/clarify-critic.md:157` documents `bare-string findings → {text, origin: "primary"}` and `parent_epic_loaded → false on absence`, but neither is implemented in any Python consumer. `tests/test_clarify_critic_alignment_integration.py:192-204` `check_invariant()` calls `f.get("origin")` directly and crashes with `AttributeError: 'str' object has no attribute 'get'` on every real archived v1 event (verified by running it against `lifecycle/archive/define-output-floors-.../events.log:2`).
> 2. **Recent production clarify_critic events are YAML-block, not JSONL** — invisible to `cortex_command/pipeline/metrics.py:75-101` `parse_events()`, which is `json.loads(line)` strictly. 11 of the 14 active lifecycle/ directories with clarify_critic events use YAML-block format. Even this lifecycle's own events.log (the clarify_critic written earlier in this session) is YAML-block. The `schema_version: 2` field added to YAML-block emission is observable to nothing in cortex's parser today.

## Codebase Analysis

### Files that will change

| File | Action | Notes |
|------|--------|-------|
| `skills/lifecycle/references/clarify-critic.md` (167 lines) | **Delete** | Auto-pruned from `plugins/cortex-core/` mirror by `just build-plugin` rsync `--delete` |
| `skills/lifecycle/references/clarify.md:55` | **Edit** | Change `Read \`references/clarify-critic.md\`` → `Read \`../refine/references/clarify-critic.md\``. Cross-skill relative path. |
| `skills/refine/references/clarify-critic.md` `## Event Logging` (lines ~128-161) | **Edit** | Add `schema_version: <int>` field to required-fields prose and example YAML; document v2 marker semantics; document v1 read-fallback (already present at line 157, may need integer-version variant alongside the existing field-presence variant) |
| `tests/test_clarify_critic_alignment_integration.py` | **Edit + add test** | Implement Python legacy-tolerance fallback (was prose-only); add `test_clarify_critic_v1_replay_invariant` reading a pinned fixture |
| `tests/fixtures/clarify_critic_v1.json` (NEW) | **Create** | Pin v1 fixture to test-owned location, decoupled from live archive churn. Source: `lifecycle/archive/define-output-floors-for-interactive-approval-and-overnight-compaction/events.log:2` (1074 bytes, JSONL, bare-string findings, no `parent_epic_loaded`, no `dismissals`). |
| `plugins/cortex-core/skills/lifecycle/references/clarify-critic.md` | **Auto-prune** | rsync `--delete` removes when source is deleted; pre-commit drift hook enforces same-commit rebuild. |

### Producer chain & current emission format

The orchestrator (Claude itself running clarify §3a) writes the `clarify_critic` event YAML directly to `lifecycle/{feature}/events.log`. Confirmed: `clarify_critic` is **NOT** in `EVENT_TYPES` (`cortex_command/overnight/events.py:90-148`); `record_event()` would `ValueError` if invoked with it (line 216-218). The orchestrator bypasses `record_event()` entirely.

**Format split across the corpus** (verified directly):

| Location | JSONL files | YAML-block files | Notes |
|----------|-------------|------------------|-------|
| `lifecycle/archive/*/events.log` | 110 | 32 | Older archives (pre-2026-04) are JSONL; ~30 mid-2026 ones switched to YAML-block. |
| `lifecycle/*/events.log` (active) | 3 | 11 | Recent active lifecycles use YAML-block almost exclusively. The clarify_critic this very session wrote is YAML-block. |
| **Total** | **113** | **43** | — |

`cortex_command/pipeline/metrics.py:parse_events()` is `json.loads(line)` strictly. **Every YAML-block clarify_critic event is silently warn-skipped by every parse_events caller in the codebase.** The "real-archived-event replay test" can only target the 110 archived JSONL events — the 32 archived YAML-block events and all 11 active YAML-block events are unparseable through the cortex parser.

### Consumer audit (Phase 1 precondition — answered definitively)

**Sole programmatic consumer**: `tests/test_clarify_critic_alignment_integration.py`. Specifically the `check_invariant()` function at lines 192-204, exercised by `test_cross_field_invariant_violation_detector` at lines ~379-433 with synthetic dicts only.

**Other event-log readers that are NOT clarify_critic consumers** (verified by Adversarial agent across `cortex_command/`):

| File | Path | Behavior |
|------|------|----------|
| Dashboard event timeline | `cortex_command/dashboard/data.py:281-355 parse_feature_events()` | Filters explicitly by `event in {"phase_transition"}`. Never touches clarify_critic. |
| Dashboard overnight feed | `cortex_command/dashboard/data.py:626` | Allowlist `{"feature_start", "feature_complete", "feature_paused", "feature_failed"}`. |
| Morning report | `cortex_command/overnight/report.py:337,838,951,958,967,1692` | Allowlists per call site (`feature_merged`, `phase_transition`, `circuit_breaker`, etc.). Findings/drift/residue rendering reads JSON residue files, not events.log. |
| Generic JSONL parser | `cortex_command/pipeline/metrics.py:parse_events()` | Type-agnostic, but clarify_critic is structurally invisible whenever YAML-block (see "Format split" above). |

**Verdict**: Even though `parse_events()` is type-agnostic, no production-code path uses it to read clarify_critic. The consumer set really is enumerable. **But the legacy-tolerance test in the consumer that DOES read clarify_critic (`check_invariant`) crashes on every real archived v1 JSONL event.** The "consumers handle bare-string findings gracefully" precondition assumed by Phase 1 of the source ticket is **false**.

### Cross-skill reference machinery

`bin/cortex-check-parity` token regex (`cortex-[a-z][a-z0-9-]*`) only matches `cortex-*` CLI script tokens. It does NOT scan or enforce cross-skill markdown file references. The new `skills/lifecycle/references/clarify.md` §3a → `../refine/references/clarify-critic.md` reference is manually maintained with no lint gate.

**Existing precedent**: `skills/refine/SKILL.md:39, 66, 87, 157, 164` already use cross-skill `..` references to lifecycle files. The new reference is symmetric (lifecycle now references refine via `..`), making the coupling bidirectional but well-precedented. **However**: there is no markdown link-validator in `.githooks/pre-commit` or anywhere else in the build. If `skills/refine/` is ever renamed, all 5 existing references AND the new one silently break at runtime — the orchestrator agent gets a "file not found" at skill-invocation time. This is latent risk but out of scope for this ticket; recommend a follow-up to add a link-validator pre-commit hook.

### Plugin mirror

`just build-plugin` recipe rsyncs each canonical skills directory into `plugins/cortex-core/skills/` with `--delete`. Both 167-line lifecycle copy and 215-line refine copy currently exist as live mirrors. After this ticket: `plugins/cortex-core/skills/lifecycle/references/clarify-critic.md` auto-prunes; `plugins/cortex-core/skills/refine/references/clarify-critic.md` updates with the schema_version edit. The `.githooks/pre-commit` drift hook fails the commit if the mirror diverges, forcing a same-commit rebuild.

### schema_version placement (concrete change)

In `skills/refine/references/clarify-critic.md` `## Event Logging` section:
- Add `schema_version: <int>  # 2 for current schema; absent → treat as v1` to the field list (after `feature:`, before `parent_epic_loaded:`).
- Add `schema_version: 2` to the example YAML (line 169 area).
- Update prose at line 138 to include `schema_version` in the required-field list.
- Document the read-rule explicitly: "absent → v1 (bare-string findings, no `parent_epic_loaded`); present and `2` → v2 (object findings, `parent_epic_loaded` required)."

**No Python code change in `cortex_command/overnight/events.py` is needed or appropriate.** Adding `clarify_critic` to `EVENT_TYPES` would not be load-bearing — no producer calls `record_event()` with it, and the YAML-block emission format wouldn't go through `record_event()` anyway.

### Replay test design

Per Adversarial agent's mitigation #3: pin the fixture to `tests/fixtures/clarify_critic_v1.json` (test-owned), not the live archive. Source: `lifecycle/archive/define-output-floors-for-interactive-approval-and-overnight-compaction/events.log:2` — a single-line JSONL v1 event (~1074 bytes, bare-string findings of length 4, no `parent_epic_loaded`, no `dismissals`). Add a comment at the top of the fixture pointing back to the source archive line.

The replay test must:
1. Load the fixture and parse it as JSON.
2. Apply the legacy-tolerance fallback (which this ticket implements in Python — see below).
3. Assert the cross-field invariant holds (no alignment finding → invariant trivially holds for v1).
4. Assert post-fallback shape: every finding has `text` and `origin` keys; `origin == "primary"` for all v1 findings; `parent_epic_loaded == false`.

Test name: `test_clarify_critic_v1_replay_invariant` (versioned in the name per Adversarial mitigation #4).

### Legacy-tolerance fallback (must be implemented in Python, not just prose)

Per Adversarial Critical Finding A: the markdown's prose-only legacy-tolerance is not Python-executable. This ticket must add a `_normalize_clarify_critic_event(evt: dict) -> dict` helper in `tests/test_clarify_critic_alignment_integration.py` (or a sibling module if there's appetite for a shared location). The helper:

```python
def _normalize_clarify_critic_event(evt: dict) -> dict:
    """Apply v1→v2 read-fallback per skills/refine/references/clarify-critic.md
    `## Event Logging`: bare-string findings become {text, origin:"primary"};
    missing parent_epic_loaded becomes false; missing schema_version implies v1."""
    out = dict(evt)
    out.setdefault("schema_version", 1)
    out.setdefault("parent_epic_loaded", False)
    out["findings"] = [
        f if isinstance(f, dict) else {"text": f, "origin": "primary"}
        for f in evt.get("findings", [])
    ]
    return out
```

`check_invariant` should then either (a) call `_normalize_clarify_critic_event` before iterating findings, or (b) be rewritten to handle bare-string findings inline. Option (a) is preferred since the normalizer is reusable for the replay test.

**Scope question**: should this normalizer also live in production code (e.g., `cortex_command/overnight/events_clarify_critic.py`)? The current consumer set is test-only, so a test-side helper suffices. Surface as Open Question §1.

### Format reconciliation (YAML-block vs JSONL)

Per Adversarial Critical Finding B: the `parse_events()` JSONL-only parser silently warn-skips every YAML-block clarify_critic event. Adding `schema_version` to YAML-block emission is invisible to cortex's parser today.

This ticket has three options:
1. **Defer entirely** — acknowledge the format mismatch as known, ship `schema_version` to the markdown spec as guidance for future JSONL-emitted events, file a separate ticket for format reconciliation. *Pro:* keeps this ticket bounded. *Con:* the schema_version field accomplishes nothing observable until the format is reconciled, undermining the ticket's "safety mechanism" framing.
2. **Spec-amend the markdown to require JSONL emission** — write into `## Event Logging` that emissions MUST be single-line JSONL going forward, not multi-line YAML. *Pro:* aligns with the rest of cortex's events.log convention; restores parser visibility. *Con:* the user-facing example YAML in the markdown is currently multi-line, which is more readable for human authors of the spec — converting to JSONL hurts readability of the documentation.
3. **Extend `parse_events()` to recognize YAML-block events** — add a fallback path that reads multi-line YAML blocks into dicts. *Pro:* preserves current emission format. *Con:* meaningful new code, scope inflation, and risks affecting other event-log readers.

Surface as Open Question §2 — this is consequential and the right answer is not obvious.

### v1.5 intermediate shape

29 archived JSONL events have `dismissals` field but no `parent_epic_loaded`/`origin`. This is an intermediate shape (post-`dismissals` ticket, pre-`parent_epic_loaded` ticket) that neither the source ticket nor the markdown's existing legacy-tolerance prose explicitly enumerates. The proposed `_normalize_clarify_critic_event` handles it correctly (it normalizes per-field, not per-shape), but the markdown spec should call out the intermediate shape so future maintainers don't assume a binary v1↔v2 split.

### Conventions for similar past dual-source migrations

- **Commit `8268d084` (Lifecycle adopts cortex-resolve-backlog-item; drop refine clarify, #176)**: same pattern — delete one skill's copy, retarget references, auto-prune mirror. Direct precedent for Phase 1+2.
- **`plan_comparison` v2 events** (per `cortex_command/overnight/prompts/orchestrator-round.md:340`): markdown-spec'd, agent-emits-JSONL-line, `schema_version: 2` precedent. **However**, plan_comparison is JSONL — the cleaner precedent. clarify_critic's current YAML-block emission diverges from plan_comparison.
- **No prior cortex-command commit merges schema_version + replay test atomically.** Closest analogue: `cortex_command/pipeline/tests/test_metrics.py:1424-1471` ships schema-version-aware metrics tests, but there's no pre-existing pattern for replaying real archived events. This ticket establishes the pattern.

## Web Research

### Schema-versioning patterns (agent 2)

Three approaches in literature: (1) explicit version field (CloudEvents `specversion`, MongoDB Schema Versioning Pattern, AsyncAPI) — what cortex proposes; (2) registry-based (Confluent — N/A, no registry); (3) weak schema + upcaster (Greg Young, Marten — no version, readers tolerate missing/extra fields). Cortex's design effectively combines (1) and (3): explicit `schema_version` is the marker; the legacy-tolerance fallbacks are textbook upcasters. **"Frozen v1 events live forever" is universally endorsed** across event-sourcing literature.

YAGNI risk for `schema_version` (Fowler's `version='v1'` antipattern) is mitigated when introduced at the moment v2 ships, not speculatively — which matches Phase 3's framing. Naming convention `schema_version` (snake_case integer) dominates in YAML/Python ecosystem; matches MongoDB Schema Versioning Pattern; cleaner than `apiVersion`/`specversion`/`eventVersion` for this use case.

### Replay-test patterns

Documented advantages: catches long-tail shapes synthetic fixtures miss; cannot drift toward new schema; "deterministic replay" / "golden file testing" are the canonical names (Sakura Sky, AWS EventBridge archive/replay, pytest-golden, goldie). **Pitfalls** (cited verbatim into design):
- Pin to specific archive path; don't glob (Exactpro). → Implemented as Adversarial mitigation #3 (copy to `tests/fixtures/`).
- Replay only the consumer/parser layer, not the producer. → This ticket targets `check_invariant` / `_normalize_clarify_critic_event`, not the orchestrator dispatch.
- Test ages out — tag with the schema version it covers. → Implemented as Adversarial mitigation #4 (`test_clarify_critic_v1_replay_invariant`).

### Cross-module documentation references

Spotify Engineering, Backstage TechDocs, monorepo.tools convergent guidance: documentation-near-code is the default; cross-module references via relative path are not, in themselves, an antipattern. They become a smell only when the link target is load-bearing logic duplicated in both places (the SSOT-violation cortex was suffering from before this ticket). The fix here — promote one to canonical, delete the other — is textbook. The cross-skill `..` reference cortex now creates is well-precedented (5 existing instances in `skills/refine/SKILL.md`).

### Hard-delete vs deprecation

Literature is more nuanced than cortex's policy implies. Hard-delete fits this artifact (single repo, finite enumerable consumers, single commit) but wouldn't generalize to e.g. dropping a field from events.log itself — where archived events are passive "consumers" of v1 shape. **This is exactly why Phase 3's legacy-tolerance fallbacks exist**: the schema_version field makes the v1↔v2 boundary explicit; the fallbacks make v1 archives readable forever; together they implement Greg Young's "weak schema + upcaster" pattern within cortex's policy.

Sources: `event-driven.io` (Dudycz), Confluent docs, Martin Fowler (Event Sourcing, YAGNI), Greg Young's *Versioning in an Event Sourced System*, Marten event-store docs, CloudEvents spec, Yan Cui (theburningmonk), AWS EventBridge archive/replay, Tideways "Refactoring with Deprecations," PingCAP backward-compatibility patterns, Spotify Engineering TechDocs, Wikipedia SSOT.

## Requirements & Constraints

### Workflow trimming (project.md:23)

> Workflows that have not earned their place are removed wholesale rather than deprecated in stages. Hard-deletion is preferred over deprecation notices, tombstone skills, or env-var soft-deletes when the surface has zero downstream consumers (verified per-PR). Retired surfaces are documented in `CHANGELOG.md` with replacement entry points and any user-side cleanup paths the scaffolder cannot auto-prune.

The ticket's "aligned-with-caveats" framing is correct: project.md's text covers consumer-set verification cleanly but presupposes "kill the unused workflow." This ticket consolidates an actively-used duplicate where the destination survives. Direction-of-fit (hard-delete) is consistent; literal text-match is partial.

### Maintainability through simplicity (project.md:35)

> Complexity is managed by iteratively trimming skills and workflows. The system should remain navigable by Claude even as it grows.

`schema_version` + replay test are load-bearing defensive measures, not ceremony — `schema_version` is already an established pattern (`plan_comparison` v2; `runner.pid`). Both fit cleanly under "Maintainability through simplicity."

### File-based state (project.md:27)

> Lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files (markdown, JSON, YAML frontmatter). No database or server.

Reinforces the design: the legacy-tolerance fallback + schema_version field are the file-based-state equivalent of a database migration script. The architectural constraint supports the design.

### MUST-escalation policy (CLAUDE.md OQ3)

Existing `parent_epic_loaded: <bool>  # required` line at `skills/refine/references/clarify-critic.md:138` was added pre-Opus 4.7 (commit 5111710) and is grandfathered per #85. **NEW MUST language for `schema_version` would need OQ3 evidence** (an `events.log` F-row + an `effort=high` dispatch attempt). No such evidence exists.

**Implication for the spec**: phrase the `schema_version` field as SHOULD, not REQUIRED, until OQ3 evidence is gathered. The verbatim spec phrasing should be:

> `schema_version: <int>  # 2 for current schema; readers MUST tolerate absence as v1.`

Note the asymmetry: producers SHOULD include the field (positive routing); readers MUST tolerate its absence (legacy-readability is non-negotiable). The reader MUST is itself a NEW must, but it's a *defensive* must — readers crashing on absent fields is the failure mode this ticket explicitly prevents. Surface as Open Question §3 — should the reader-side rule actually be a MUST (and require OQ3 evidence) or be expressible as the test assertion alone?

### "Prescribe what and why, not how" (memory feedback_design_principle_what_why_not_how.md)

Applies to skill-rail content (the disposition framework in `clarify-critic.md` itself). Does NOT apply to delivery specs (the schema_version field is a runtime contract, not agent-facing prose). The spec should codify the *what* (field present, format, semantics) and *why* (replay safety) but not prescribe procedural how.

### CLAUDE.md 100-line cap

CLAUDE.md is currently 67 lines. This ticket adds zero policy text. The cap is not threatened.

### events.log conventions

`requirements/observability.md` and `requirements/pipeline.md` document events.log-reading conventions but don't mandate per-event schema versioning. The pattern exists (`plan_comparison` v2, `runner.pid`); this ticket extends it to clarify_critic. No requirement conflict.

### Conditional Loading

None of the directives map to skill-rail or clarify-critic work. Minor gap, out of scope.

## Tradeoffs & Alternatives

Six alternatives evaluated. **Recommended: Alternative 1 (ticket's prescription, slightly de-prescribed) — augmented with the Adversarial review's mitigations.**

| Alt | Description | Verdict |
|-----|-------------|---------|
| **1** | In-place promotion + cross-skill `..` reference + markdown-layer `schema_version` + replay test (with fixture pinning, Python normalizer, format reconciliation as separate decision) | **Recommended.** Best fit across all four dimensions. |
| 2 | Move to `skills/_shared/clarify-critic.md` neutral location | Rejected. Introduces brand-new top-level skills affordance, fights existing self-contained-skill convention, would need plugin-build infra updates. |
| 3 | Inline-merge then collapse | Rejected. Identical-outcome to Alt 1 plus pointless ceremony — refine is already a clean superset (215 vs 167 lines, all deltas additive). |
| 4 | Defer schema_version (Phase 1+2 only) | Rejected. Leaves the test-coverage gap that motivated the ticket. |
| 5 | Defer replay test (schema_version field only) | Rejected. Schema_version field has no executable consumer without a replay test asserting on it; "shipping an unread version field" is YAGNI in disguise. |
| 6 | Migrate producer to `record_event()` first, then add schema_version to events.py | Rejected. Scope inflation; counter-aligned with the markdown-spec'd-agent-emits-event pattern; plan_comparison v2 (the direct precedent) does not go through `record_event()` either. |

**Cross-skill `..` reference question**: Alt 4 evaluator's research found this is well-precedented (5 instances in `skills/refine/SKILL.md`). The "awkwardness" is illusory. The new reference makes the coupling bidirectional but symmetric, which is fine.

## Adversarial Review

### Failure modes verified

1. ⚠️ **CRITICAL: `check_invariant` crashes on every real archived v1 event** (`AttributeError: 'str' object has no attribute 'get'`). Verified directly. The markdown's prose-only legacy-tolerance is not Python-executable.
2. ⚠️ **CRITICAL: `parse_events()` is JSONL-only; 43 of 156 archived clarify_critic events are YAML-block** and silently warn-skipped. The schema_version field added to YAML-block emission is observable to nothing in cortex's parser.
3. **Consumer set is genuinely enumerable**: dashboard, morning report, all `parse_events()` callers filter by an explicit event-type allowlist that excludes clarify_critic. No generic event timeline rendering exists. Consumer audit collapses to one test file as expected.
4. **Plugin mirror auto-prune works as expected** — pre-commit drift hook will block partial-state commits.
5. **Replay test fixture fragility** — pinning to live archive path is fragile; copy to `tests/fixtures/` (mitigation implemented).
6. **Cross-skill `..` reference durability** — no existing tooling validates these references; 5 existing instances in `skills/refine/SKILL.md` are at the same risk class. Out of scope for this ticket; flag for follow-up.
7. **schema_version=2 vs absent indistinguishability** — a v2 producer that drops the field is indistinguishable from a v1 event. Mitigation: positive-routing producer guidance ("SHOULD include `schema_version: 2`") plus a producer-side test that asserts emitted events contain it.
8. **MUST-escalation chicken-and-egg** — adding `schema_version: REQUIRED` violates OQ3 without F-row evidence. Mitigation: use SHOULD phrasing initially.
9. **Cross-field invariant programmatic enforcement** — markdown prose only; backlog #186 plans the validator. Adding `schema_version` to the same prose layer has the same enforcement gap. Acceptable as long as we don't escalate to MUST.
10. **Working-tree mid-edit race** — brief and human-bounded; deletion + §3a edit must be the same commit (which the pre-commit drift hook enforces).
11. **No real v2 corpus exists yet** — replay test can only target v1. Acceptable; tag the test name with the schema version it covers.
12. **v1.5 intermediate shape** (29 JSONL events with `dismissals` but no `parent_epic_loaded`/`origin`) — the proposed normalizer handles this correctly per-field, but the spec should call out the intermediate shape.

### Anti-patterns surfaced (from Adversarial review)

- **Closed-allowlist warning template** (clarify-critic.md line 26) is markdown-spec'd but lacks runtime enforcement. Backlog #186 plans it. Out of scope for this ticket.
- **Markdown spec drift vs. emitted data**: producers writing YAML, parsers reading JSONL is a pre-existing data-integrity issue. Adding more fields to the YAML spec without fixing the format mismatch increases blast radius.
- **`research/archive/claude-code-sdk-usage/research.md:42` cites line numbers in the to-be-deleted file** — minor doc-rot vector. Trim during this ticket as housekeeping.

## Open Questions

All resolved before transitioning to Spec.

1. **Where should the Python `_normalize_clarify_critic_event` helper live?** **Resolved**: test-side helper in `tests/test_clarify_critic_alignment_integration.py`. Current consumer set is test-only; production-side affordance is YAGNI. If a production consumer ever needs it (per #186 or successors), it can be promoted later via a one-import refactor.

2. **How to handle the YAML-block vs JSONL emission mismatch?** **Resolved**: spec-amend `skills/refine/references/clarify-critic.md` `## Event Logging` to require JSONL emission going forward. Rationale: aligns clarify_critic with the rest of cortex's events.log convention (every other event type is JSONL via `record_event()`); matches the `plan_comparison` v2 precedent; restores `parse_events()` visibility for new events; purely additive producer change with no impact to archived YAML-block events (which are already invisible to the parser — status quo, not regression). The example YAML in the spec stays multi-line for human readability; the wire format is single-line JSONL. Existing 43 archived YAML-block events remain readable as text but stay invisible to `parse_events()` — this is acknowledged status quo, not new regression. Filing a separate cleanup ticket to backfill or convert the 43 YAML-block archives is out of scope for this ticket.

3. **Should the reader-side legacy-tolerance be a MUST?** **Resolved**: yes. Producer-side `schema_version` is SHOULD (per OQ3 grandfathering for new MUST language). Reader-side rule "readers MUST tolerate absence as v1" is a defensive MUST — the failure mode being prevented (reader crash on missing field) is concrete, the test assertion enforces it, and treating reader fragility as optional invites future regressions. The asymmetric SHOULD/MUST is the OQ3-spirit-compliant compromise.

4. **Does the spec need to enumerate the v1.5 intermediate shape** (29 archived JSONL events with `dismissals` but no `parent_epic_loaded`/`origin`)? **Resolved**: yes — call out the intermediate shape briefly in the markdown's "Pre-feature legacy events…" prose. The per-field normalizer handles all combinations correctly; the documentation is for future maintainers so they don't assume a binary v1↔v2 split. One additional sentence in the spec's `## Event Logging` section.

5. **Replay test fixture provenance documentation**: **Resolved**: inline a single-line comment at the top of `tests/fixtures/clarify_critic_v1.json` pointing back to the source archive line. Format: `// Source: lifecycle/archive/define-output-floors-for-interactive-approval-and-overnight-compaction/events.log:2 — pre-feature v1 clarify_critic event with bare-string findings, no parent_epic_loaded, no dismissals.` (Note: JSON doesn't support comments natively; if strict JSON is required, store as a sibling `.provenance` file; if YAML-style or jsonc, inline `//` comment is fine. Decide concretely during Spec implementation; default to a sibling `clarify_critic_v1.json.provenance` markdown file to avoid jsonc/json-strict ambiguity.)

## Considerations Addressed

- **Phase 3 (schema_version + replay test) is the safety mechanism for the Phase 2 migration, not orthogonal duplication-collapse work — verify this framing holds in design and confirm the epic-172-audit C5 source justifies inclusion in epic 172 rather than a standalone ticket.**

  Verified. The framing holds and is well-grounded in the schema-evolution literature: Greg Young's "weak schema + upcaster" pattern is explicitly framed as the safety mechanism that lets event shapes evolve without rewriting history. The legacy-tolerance fallbacks (`bare-string findings → {text, origin: "primary"}`, `parent_epic_loaded → false on absence`) are textbook upcasters; the `schema_version` field is the explicit-version-field marker that complements them; the replay test is the executable assertion of BACKWARD compatibility (Confluent's terminology) for the Phase 2 schema change. Inclusion in epic 172 is structurally justified — schema-evolution work and replay-validation work are bundled together because the validation only makes sense relative to the specific evolution it protects, and decoupling them creates a window where the migration has landed but the safety net hasn't. **However**, the Adversarial review surfaced two findings that materially expand Phase 3's scope: (i) the Python legacy-tolerance fallback must be implemented (it's prose-only today, crashing on real archives), and (ii) the YAML-block vs JSONL format mismatch must be resolved or explicitly deferred. These are not orthogonal scope — they are direct consequences of treating Phase 3 as the safety mechanism. The framing therefore strengthens, not weakens, when the Adversarial findings are taken seriously.
