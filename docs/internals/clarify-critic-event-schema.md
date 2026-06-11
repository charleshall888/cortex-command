[← Back to Agentic Layer](../agentic-layer.md)

# clarify_critic Event Schema — Legacy Shapes and Read Mappings

**Internal reference — not a user-facing skill.**

The current (v3) write shape and the producer-side contract live in `skills/refine/references/clarify-critic.md` (`## Event Logging`). This doc carries the read-side material that serves programmatic readers and audit tooling rather than the orchestrator's runtime path: the per-shape legacy read-mapping semantics, the legacy cross-field invariant, and the rationale for the v3 counts-only decision. Backlog #186 plans a validator built against this contract.

## Why v3 carries only counts

The per-finding prose (`findings[].text`), the dismissal rationales (`dismissals[].rationale`), and the applied-fix descriptions (`applied_fixes[]`) are intentionally not preserved in the row. Audit verified there are zero non-test consumers of those prose fields; preserving them without a reader would re-create the dead-emission pattern that the count-only schema work eliminated. Disposition counts and `applied_fixes_count` / `dismissals_count` remain on the row to keep the audit-affordance signal (`detections >= 1` plus disposition-shape sanity) intact.

## Legacy-shape read mappings

Readers MUST tolerate every prior event shape forever. Each shape below is described by behavioral effect; archived `cortex/lifecycle/*/events.log` files remain readable without rewrite.

1. **minimal v1** — events without `schema_version`, without `parent_epic_loaded`, and with bare-string `findings[]` entries. Read `schema_version` as v1, `parent_epic_loaded` as `false`, and each bare-string finding as `{text: <string>, origin: "primary"}`. The `dismissals` array may be absent; read as `[]`. Read-tolerated indefinitely.
2. **v1+dismissals** — events without `schema_version` but with the `dismissals` array present (and the `len(dismissals) == dispositions.dismiss` invariant intended). Apply the same v1 defaults for missing fields; honor the present `dismissals` array as written. Read-tolerated indefinitely.
3. **v2** — events with `schema_version: 2`, structured `findings[]` array of `{text, origin}` objects, `dismissals[]` array of `{finding_index, rationale}` objects, and `applied_fixes[]` array of prose strings. Read-tolerated indefinitely; readers that need only count-shape data can compute counts from the arrays at read time (`findings_count = len(findings)`, etc.).
4. **YAML-block** — events written as a multi-line YAML block on disk rather than single-line JSONL. Tolerate on read; do not rewrite. Producers SHOULD emit single-line JSONL going forward. Read-tolerated indefinitely.
5. **v3** — current write shape (count-only, defined in `skills/refine/references/clarify-critic.md`). This is the only shape new producers emit.

## Cross-field invariant (legacy events with arrays present)

Any post-feature legacy event whose `findings[]` contains at least one item with `origin: "alignment"` has `parent_epic_loaded: true`. Violation indicates a write-side bug in the legacy v2 emitter. This invariant sits in parallel to the `len(dismissals) == dispositions.dismiss` invariant; neither is programmatically validated. Under v3 the invariant has no row-level expression because per-finding `origin` is no longer logged.

## Count arithmetic under self-resolution

Disposition counts reflect post-self-resolution values. If self-resolution reclassifies an Ask item as Apply, the logged `apply` count increases and `ask` count decreases accordingly, and `applied_fixes_count` increments. If self-resolution reclassifies an Ask item as Dismiss, `ask` decreases and `dismiss` increases and `dismissals_count` increments in lockstep.
