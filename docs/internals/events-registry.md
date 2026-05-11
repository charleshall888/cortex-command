[← Back to Agentic Layer](../agentic-layer.md)

# events.log Emission Registry

**Internal reference — not a user-facing skill.**

`bin/.events-registry.md` is the canonical allowlist of every `event` name written to any `events.log` in this repo. It pairs each emission with at least one documented consumer so that "what does this event get read for?" is answerable without a repo-wide grep. The static gate at `bin/cortex-check-events-registry` enforces the producer side at commit time for skill-prompt sources; Python emission sites are governed by review and recorded manually for human reference.

The registry exists because the audit that produced epic #172 found the cost of emitting a dead event (a one-line skill-prompt edit) was far lower than the cost of proving an event was dead (a repo-wide grep across Python, shell, skill prompts, and tests). The registry inverts the asymmetry: emitting a new event now requires a registry row, so the consumer is named at the same time the producer is added.

---

## Schema

`bin/.events-registry.md` contains a single markdown table with the columns below. One row per `event_name`.

| Column | Required | Description |
|---|---|---|
| `event_name` | yes | The event-name string literal as it appears in emissions (matches the `"event"` field in the JSONL row). |
| `target` | yes | `per-feature-events-log` for `lifecycle/{feature}/events.log` rows, `overnight-events-log` for `lifecycle/overnight-events.log` rows. |
| `scan_coverage` | yes | `gate-enforced` — the static gate scans for new emissions of this name in the skill-prompt scan surface. `manual` — Python or shell emission; the gate does NOT auto-detect drift; the row exists for human reference. |
| `producers` | yes | `;`-separated list of `path:line` pointers to the emission sites. Python collective references (e.g. `cortex_command/overnight/events.py:EVENT_TYPES`) are permitted. |
| `consumers` | yes | `;`-separated list of `path:line` pointers to read sites. Skill prompts, Python, shell, and tests all count; tests-only consumers carry a `tests-only` annotation. Audit-affordance rows may use the literal value `human-skim` with a rationale. |
| `category` | yes | `live` (current production emission with a documented reader), `audit-affordance` (emitted for operator skim, no programmatic reader), or `deprecated-pending-removal` (scheduled for deletion). |
| `added_date` | yes | YYYY-MM-DD the row was added. |
| `deprecation_date` | conditional | YYYY-MM-DD; required when `category=deprecated-pending-removal`. The `--audit` mode fires on rows whose date is in the past. |
| `rationale` | conditional | ≥30 chars; required when `category != live`. Explains why an `audit-affordance` row has no programmatic reader, or why a `deprecated-pending-removal` row's removal is staged. |
| `owner` | conditional | Required when `category=deprecated-pending-removal`. Identifies who has authority to bump `deprecation_date` and is named in `--audit` output as the cleanup-PR runner. |

---

## Scope split: `gate-enforced` vs `manual`

The `scan_coverage` column splits the registry into two scopes with different enforcement guarantees:

- **`gate-enforced`** — for events emitted from skill-prompt sources (`skills/**/*.md`, `cortex_command/overnight/prompts/*.md`). The gate scans these files at commit time; a staged emission whose `event_name` is not registered fails the pre-commit check. This is the dominant asymmetric path the audit identified, and where the gate inverts the cost.
- **`manual`** — for events emitted from Python (`cortex_command/**/*.py`, `bin/cortex-*`) or shell. The gate does NOT scan these files; new emissions are caught at PR review or by the write-time `EVENT_TYPES` enforcement in `cortex_command/overnight/events.py` for the overnight session scope. The registry row exists so the consumer is documented even though the gate is not the discipline mechanism.

The split is a deliberate scope choice. Extending the static gate to Python would require AST-walking with constant-resolution to handle the call-shape variety (positional bare-constant, dict-built-incrementally, kwargs-style) and would not improve coverage of the asymmetric pattern beyond the existing Python review process.

---

## Two modes: `--staged` and `--audit`

`bin/cortex-check-events-registry` runs in two modes:

### `--staged` (pre-commit critical path)

Wired into `.githooks/pre-commit` Phase 1.8. Triggers only when the commit touches staged paths in the gate's scan surface (`skills/*`, `cortex_command/overnight/prompts/*`, the gate script itself, or the registry file). Crucially, the trigger does **not** include `cortex_command/**/*.py` — unrelated backend commits never invoke this phase.

The `--staged` mode enforces only unregistered-emission detection: a staged file containing `"event":"<name>"` where `<name>` is not present in the registry fails the commit. Time-based checks (stale `deprecation_date`) are deliberately off this path to avoid the day-15 tripwire pattern, where an unrelated commit gets blocked by an aged registry row that the committer is not responsible for.

If `bin/.events-registry.md` is missing or malformed, the gate fails closed with a `MISSING_REGISTRY` error message in positive-routing form. This overrides the `cortex-check-parity` precedent of failing open on missing allowlist — the registry is the discipline mechanism and a silent lapse would erase the gate's value.

### `--audit` (off critical path)

Invoked via `just check-events-registry-audit` or directly. Intended for manual or scheduled invocation (morning-review surface, weekly cron, on-demand). Scans the entire registry and fires the `deprecation_date` check: any `deprecated-pending-removal` row whose date is in the past, or that is missing the required `owner` field, is reported as a violation.

The audit mode does not modify the registry; it only reports. Output names the `owner` for each stale row so the cleanup-PR responsibility is unambiguous.

---

## Deprecation lifecycle

When an event is scheduled for deletion (the producer is being removed, but in-flight features may still emit the name), the registry row flips from `live` to `deprecated-pending-removal` with the following:

1. `category` set to `deprecated-pending-removal`.
2. `deprecation_date` set to today + 30 days (aligned to the repo's observed 25-day batch cadence; not 14 days, which is too tight to absorb a missed cycle).
3. `owner` set to the engineer responsible for the cleanup follow-up PR.
4. `rationale` updated to explain why the deletion is staged (typically: "Emission deleted in PR #N; deprecation row exists so in-flight features that already emit this name don't trip the gate; row removable once no events.log in `lifecycle/` contains the name").

Once the deprecation date passes and the cleanup-PR runner has confirmed no live emissions remain, the row is removed entirely from the registry. Tolerant-Reader semantics in all consumers (Python, shell, skill prompts) ensure that already-archived events.log rows with the deleted name remain parseable — readers silently skip unknown event names, so archive data is never broken by registry pruning.

---

## Stale-row recovery path

When the `--audit` recipe surfaces a stale row (`deprecation_date` in the past, event still emitted), the recovery path is:

1. **The audit output names the `owner`.** That engineer owns the cleanup PR.
2. **The owner has two options for the row.** Either (a) run the cleanup PR that removes the residual emissions and deletes the row, or (b) if the cleanup is genuinely blocked (e.g., the in-flight feature depending on the event hasn't merged yet), bump the `deprecation_date` for another cycle and update the `rationale` to explain the delay.
3. **Bumped rows surface a stronger warning on the next audit.** A row that has been bumped twice fires a heightened-attention signal in `--audit` output. This is the structural pressure that prevents indefinite drift without forcing a pre-commit tripwire on unrelated work.
4. **Unrelated commits are never blocked.** Even an aged stale row does not trip the pre-commit gate; cleanup is scheduled as separate work.

This split — pre-commit gate enforces only producer registration, audit recipe enforces deprecation-date hygiene — keeps the critical path fast and predictable while still giving operators a surface to track stale-row cleanup.

---

## Related

- `bin/.events-registry.md` — the registry itself.
- `bin/cortex-check-events-registry` — the gate script (skill-prompt scope, `--staged` and `--audit` modes).
- `.githooks/pre-commit` Phase 1.8 — pre-commit invocation.
- `justfile` recipes `check-events-registry` and `check-events-registry-audit`.
- `tests/test_check_events_registry.py` — gate self-tests.
- `docs/internals/pipeline.md` and `docs/overnight-operations.md` — where `events.log` shapes and consumers are documented at the module level.
