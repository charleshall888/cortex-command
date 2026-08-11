---
schema_version: "1"
uuid: e8f07288-13a7-4d96-a5dd-0e427892cc7b
title: Tier clause vocabulary is still the criticality set, so §5.2's tier language has no tag to land on
status: backlog
priority: medium
type: feature
created: 2026-08-10
updated: 2026-08-10
tags: ['lifecycle', 'tiering']
areas: ['lifecycle']
---
## Why

#471 wired `--tier-reason` into Step 4 while deliberately declining to define a tier-specific clause vocabulary, and
#471 is `status: complete` — so the fork it left open is tracked by nothing.
`cortex/lifecycle/tier-overrides-record-no-reason-and/spec.md:32` holds the deferral, the classification finding behind
it, and its re-measure trigger, verbatim:

> if fill on `complexity_override` at `gate=clarify_reconcile` remains under 5% after 60 days or 50 lifecycles, the
> prose wiring is not doing the work and the mechanism — not the vocabulary — is the thing to revisit

and, on the same line, the reading rule that must travel with the data — on `complexity_override` rows,

> a resulting distribution dominated by `other` is evidence *for* a tier-specific vocabulary, not against it

The clock started at `f0cf4ec1` (2026-08-07), the commit that put `--tier-reason` on both Step 4 arms. Both halves of
the trigger — the fill rate and the tag distribution — are read by one query over the corpus:

```
find cortex/lifecycle -name events.log -exec grep -h '^{.*"complexity_override"' {} + \
  | jq -s '[.[] | select(.gate=="clarify_reconcile")]
      | {rows: length,
         filled: [.[] | select((.reason // "") != "")] | length,
         tags: ([.[].reason // "" | select(. != "") | split(":")[0]]
                | group_by(.) | map({(.[0]): length}) | add)}'
```

Reading on 2026-08-10, 3 days into the 60: `{"rows": 57, "filled": 1, "tags": {"other": 1}}` — 1.8% fill, and the one
filled row is tagged `other`. Neither arm can fire yet, which is why this is a ticket and not a decision.

The `^{` guard is required by `project.md:65`: it skips 4 legacy YAML-block `complexity_override` rows, which carry no
`gate` field and predate the flag. Do not replace it with `2>/dev/null` — that failure mode is what ADR-0036 records.

Re-run at 60 days (2026-10-06) or once 50 further rows have accumulated, whichever comes first:

- `filled/rows` ≥ 5% **and** `tags` dominated by `other` → build the §5.2 vocabulary. That is the positive result.
- `filled/rows` < 5% → the mechanism, not the vocabulary, is what to revisit; close this and file against the mechanism.

## Role

Define the tier axis's own clause vocabulary from `skills/refine/references/clarify.md:33` (§5.2) and apply it on the
tier axis only.

## Integration

The validation half #471 deferred is closed by #474: both `complexity_override` writers — `reconcile-clarify`'s
`--tier-reason` and `lifecycle-event complexity-override --reason` — validate against one shared clause set in
`cortex_command/override_reason.py`. This ticket does not reopen that. It changes *which* set the tier axis validates
against.

That set is `{reversibility, exposure, consequence, other}`, derived from §5.3's **criticality** OR-bundle. §5.2 bundles
different things: *"competing designs, a blast radius you can't enumerate, or a precedent others follow"*, plus
*"whether the next tier down was considered"*. #471 classified the 24 existing free-prose tier reasons against the
criticality set: roughly half land on `other`, and the ~9 landing on `exposure` do so by coincidental vocabulary
overlap — they describe design-uncertainty scope, not downstream-breakage risk.

## Edges

- **The measurement is the gate, not the design.** Do not open by drafting tags. Re-run the query above first; a
  sub-5% fill routes this at the mechanism and this ticket closes unbuilt.
- **A second vocabulary is not a second free-text field.** #471 ruled that shape out; the ask is a §5.2-derived closed
  set applied to the tier axis.
- **`other:` stays.** It keeps an unclassifiable reason recordable, and its share is the signal the trigger reads —
  removing it destroys the instrument.
- **Forking the set forks the module.** `ALLOWED_REASON_CLAUSES` is one frozenset both writers import; a tier-only set
  means a per-axis lookup, and `project.md:64`'s closed-set co-edit constraint fires, because a tag is added.
- **Do not rename `--complexity` to `--tier`.** #471 rated it a breaking CLI change across many callers for cosmetics.
  Still out.
- **The seeded-tier blind spot is unmeasured.** A ticket whose frontmatter already names its final tier never ratchets,
  so no row exists to carry a reason. #471 flagged this as measured for criticality (10.5%/16.7%) and unmeasured for
  tier; it bounds the denominator above and should be stated, not assumed away.

## Touch points

- `cortex_command/override_reason.py` — `ALLOWED_REASON_CLAUSES`, the shared set both writers import
- `cortex_command/refine.py` — `reconcile-clarify`'s `--tier-reason` parser
- `cortex_command/lifecycle_event.py` — `complexity-override --reason`
- `skills/refine/references/clarify.md:33` (§5.2) — source of the tier vocabulary; read, not edited
- `cortex/requirements/project.md:64` → `cortex/requirements/lifecycle.md` — the closed-set constraint and its co-edit sites
- `cortex/adr/0036-ceremony-relief-is-not-taken-on-the-criticality-axis.md` — the clause-distribution recipe and its re-open trigger
- `cortex/lifecycle/tier-overrides-record-no-reason-and/spec.md:32` — the deferral, the classification finding, and the trigger quoted above
