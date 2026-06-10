---
schema_version: "1"
uuid: f9bc97d9-f171-46aa-9d56-50898edc891d
title: "cortex-lifecycle-state collapses to null on any malformed events.log line, silently skipping the spec-phase gates (diverges from common.py tolerant skip)"
status: complete
priority: medium
type: bug
created: 2026-06-02
updated: 2026-06-10
complexity: complex
criticality: high
spec: cortex/lifecycle/cortex-lifecycle-state-collapses-to-null/spec.md
areas: ['lifecycle']
lifecycle_phase: plan
---
**Why:** `cortex_command/lifecycle/state_cli.py`'s `_reduce_events` returns `None` (jq-1.8.1 reduce-to-null semantics) if ANY single line in `events.log` fails JSON parse; `main()` then writes the filtered result and `sys.exit(0)` (state_cli.py:195-201), so `cortex-lifecycle-state --field tier` emits a non-`complex` result and exits cleanly. Downstream the value reads as absent and defaults to `simple`. By contrast `cortex_command/common.py`'s `_read_tier_inner`/`_read_criticality_inner` tolerantly SKIP malformed lines (`continue`) and return the last valid value. This divergence is a split-brain: a single torn line (crash mid-write, external edit, partial append) silently disables the spec-phase adversarial gates that read via `cortex-lifecycle-state` — §3a Orchestrator Review applicability and the §3b Critical Review run-rule both default to `simple` and skip — while overnight model/effort sizing (which reads via `common.py`) still sees the correct value. The skip is silent (exit 0, no diagnostic). Surfaced during the §3b critical-review of #285 (standalone-refine-seeds-lifecycle-tier-criticality) and deliberately scoped out of that fix because it is a read-path defect affecting all `cortex-lifecycle-state` consumers, not just refine.

**Role:** The gate read path should treat a single malformed historical line the way `common.py` does — skip-and-continue to the last valid value — OR fail loudly so a poisoned reduce is observable rather than silently degrading the gate to `simple`. The two readers (`state_cli` and `common.py`) should agree on torn-line handling; their current disagreement is the bug.

**Integration:** The canonical reader pair is `cortex_command/lifecycle/state_cli.py` (`_reduce_events`, reduce-to-null) and `cortex_command/common.py` (`_read_tier_inner`/`_read_criticality_inner`, tolerant skip). `cortex-lifecycle-state` (backed by `state_cli`) is consumed by `skills/lifecycle/references/specify.md` §3a/§3b, `skills/lifecycle/references/orchestrator-review.md` applicability, `skills/refine/SKILL.md` §3b tier detection, and `skills/lifecycle/SKILL.md` resume reporting. Aligning `state_cli` to `common.py`'s tolerant skip is the natural fix; a parity test should pin that both readers return the same value on a torn log.

**Edges:**
- A torn line ANYWHERE in `events.log` poisons the whole reduce, not just lines after it.
- `main()` exits 0 on the poisoned reduce — no error signal; the skip is fully silent.
- `_filter_field` collapses both torn-line `None` and a genuinely-empty `{}` to the same output, so callers cannot distinguish "no state yet" from "corrupted log."
- Changing `state_cli` to skip-and-continue alters the contract for every `cortex-lifecycle-state` consumer — verify none rely on reduce-to-null as a corruption signal (none currently do).

**Touch-points:**
- `cortex_command/lifecycle/state_cli.py` (`_reduce_events`, `_filter_field`, `main`).
- `cortex_command/common.py` (`_read_tier_inner`, `_read_criticality_inner` — the tolerant reference implementation).
- `tests/test_cortex_lifecycle_state_parity.py` (add a torn-line parity case asserting both readers agree).

Discovered during the §3b critical-review of #285.