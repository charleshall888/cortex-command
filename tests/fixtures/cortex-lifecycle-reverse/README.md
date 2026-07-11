# cortex-lifecycle-reverse — reverse-direction golden fixtures

Reverse-direction (**new writer, old reader**) golden for the 374 Phase-4
phase-authority cutover (spec R16, arm h; ADR-0025). The cutover forfeits the
cheap prose-side git-revert rollback, so the STANDING safety net is that the
**old reducer/resolver consumers keep working when they encounter
machine-written logs**. This fixture set pins that guarantee: machine-written
**mixed** logs are fed to each enumerated legacy reader and each reader's
projection is asserted to stay correct.

Driven by `tests/test_lifecycle_reverse_golden.py` (CI-run under `uv run pytest`).

## What "mixed log" means

Each `<case>.events.log` is a log an in-repo `advance` (dual-emission) would
write: the **legacy transition vocabulary** — `lifecycle_start`,
`phase_transition`, `review_verdict`, `spec_approved`/`plan_approved`,
`feature_complete`, `feature_paused`, `complexity_override`/`criticality_override`
— **interleaved with the additive machine content**:

- `advance_started` / `advance_committed` rows (the claim/commit pair), and
- the additive `invocation_id` field carried on the dual-emitted legacy rows.

The reverse golden proves the additive content is **inert** to every old reader:
the legacy projection over the mixed log equals the projection over the same log
with the additive content stripped (`test_additive_rows_are_inert`).

## Enumerated reader set (pinned by grep at build time)

Spec R16 requires the reader set be enumerated by grep so the list stays honest.
`enumerate_reader_sites()` in the test greps each reader for a sentinel symbol
proving it still consumes the shared reducer/resolver; `test_reader_sentinels_present`
and `test_readme_pins_enumerated_readers` fail CI if a reader drops its call or
this table drifts. Sentinel first-hit `path:line` captured 2026-07-11:

| Reader | Path (sentinel first-hit) | Actual projection call site | Derivation |
|--------|---------------------------|-----------------------------|------------|
| `cortex-lifecycle-state` | `cortex_command/lifecycle/state_cli.py:15` | `state_cli.py:152` (`reduce_lifecycle_state`) | tolerant reducer → `{criticality, tier[, pause_kind]}` |
| `cortex-lifecycle-counters` | `cortex_command/lifecycle/counters.py:53` | `counters.py:124` (`count_rework_cycles`) | plan.md + events.log → `{tasks_total, tasks_checked, rework_cycles}` |
| statusline derivation | `claude/statusline.sh:376` | `claude/statusline.sh` phase ladder (~L376–L431) | **artifact-only** bash mirror of `detect_lifecycle_phase` (permanent exception) |
| `dashboard/data.py` | `cortex_command/dashboard/data.py:39` | `dashboard/data.py:314` (`resolve_lifecycle_phase`) | events-first shared resolver → `current_phase` |
| `scan_lifecycle` | `cortex_command/hooks/scan_lifecycle.py:174` | `scan_lifecycle.py:852,947` (`resolve_lifecycle_phase`) | events-first shared resolver → encoded phase / additionalContext label |
| `generate_index.py` | `cortex_command/backlog/generate_index.py:27` | `generate_index.py:177` (`resolve_lifecycle_phase`) | events-first shared resolver → `lifecycle_phase` (base, `-paused` stripped) |

Task 17 migrated `dashboard`, `scan_lifecycle`, and `generate_index` to the
events-first shared resolver `common.resolve_lifecycle_phase` (events
authoritative where machine rows exist; artifact derivation is the legacy
fallback — ADR-0025). `cortex-lifecycle-state`/`counters` are reducer consumers
(criticality/tier and counters, not phase). The statusline keeps its own
artifact-only bash derivation — a **permanent, parity-pinned exception** (it is
NOT migrated), so a mixed log can legitimately project **differently** between
the events-first Python readers and the statusline; see `rev-rework-events-only`.

### Prose-embedded readers are NOT claimed covered

This golden covers only the enumerated **machine/tool** readers above.
**Prose-embedded readers** (lifecycle SKILL.md / phase-reference prose that reads
events.log conventions by eye) are **explicitly out of scope**: their
compatibility surface is the served envelope's **legacy display-phase projection
field** (coherence req 1), not this fixture set. That field is exercised by the
`next`-envelope tests, not here.

## Flat sibling-file layout (per case, per reader projection)

Modeled on `tests/fixtures/cortex-lifecycle-state/` (flat sibling files, one
README, synthetic slugs staged into a scratch `cortex/lifecycle/<slug>/`).
**Deviation, flagged:** the model has one reader with per-stream files
(`.stdout`/`.stderr`/`.exitcode`); this golden has six heterogeneous readers, so
the per-stream files become **per-reader-projection** files. Each case
(`<case>` = the synthetic slug, discovered by globbing `*.events.log`):

```
<case>.events.log        the machine-written MIXED log staged as events.log
<case>.research.md        optional artifact staged into the scratch feature dir
<case>.spec.md            optional (drives the artifact-ladder readers)
<case>.plan.md            optional (drives counters + implement progress)
<case>.review.md          optional (none of the current cases use it)
<case>.state.stdout       pinned cortex-lifecycle-state stdout
<case>.state.stderr       pinned cortex-lifecycle-state stderr (empty = clean)
<case>.counters.stdout    pinned cortex-lifecycle-counters stdout
<case>.resolver.phase     pinned events-first phase (dashboard/scan/generate_index)
<case>.statusline.phase   pinned statusline bash-ladder wire string
<case>.scan.contains      substrings required in scan additionalContext
                          (empty file = feature suppressed, no output)
```

`generate_index`'s expected is `resolver.phase` with `-paused` stripped (it
stores the BASE phase); `dashboard` uses the full `resolver.phase` (incl.
`-paused`). Both are derived from the single `.resolver.phase` file in the test.

## Cases

| Case | Scenario | resolver phase | statusline | state | counters |
|------|----------|----------------|-----------|-------|----------|
| `rev-implement-progress` | dual-emitted advance to implement; plan 1/3 | `implement` | `implement:1/3` (agrees) | `{high, complex}` | `3/1, rework 0` |
| `rev-review-complete` | advance to review→complete + `feature_complete`; plan 2/2 | `complete` | `complete` (agrees) | `{medium, simple}` | `2/2, rework 0` |
| `rev-rework-events-only` | events reach `implement-rework`, **no review.md**; plan 2/3 | `implement-rework` | `implement:2/3` (**DIVERGES**) | `{high, complex}` | `3/2, rework 1` |
| `rev-plan-paused` | overrides + `feature_paused` + orphaned `advance_started`; no plan.md | `plan-paused` | `plan-paused` (agrees) | `{high, complex, pause_kind: relayed-consent}` | `0/0, rework 0` |
| `rev-torn-additive` | torn additive line mid-log; recovered to `plan` | `plan` | `plan` (agrees) | `{high, complex}` | `0/0, rework 0` |

### The divergence case (`rev-rework-events-only`)

The events reach `implement-rework` (a `phase_transition … to:"implement-rework"`),
but there is **no review.md**, so the artifact ladder cannot see the
`CHANGES_REQUESTED` verdict. The events-first readers correctly project
`implement-rework`; the artifact-only statusline projects `implement:2/3`. Both
are "correct" for their derivation — this is exactly the post-cutover reality the
golden must pin, not paper over. `scan_lifecycle` renders the events-first
result (`Implement — rework (review cycle 1)`).

### Terminal suppression (`rev-review-complete`)

`scan_lifecycle` filters a `complete`, no-PR feature out of the incomplete
enumeration; as the sole feature it emits nothing. Its `scan.contains` file is
empty and the test asserts `additionalContext == ""`.

## Tolerances

Projections are asserted **byte-exact** (stdout/stderr) or **string-exact**
(phase wire strings), except `scan_lifecycle`, asserted as **substring
containment** of the rendered `additionalContext` (the hook emits a larger
context block; the pinned substrings are the feature slug + phase label). Line
numbers in the reader table above are informational (first-hit at capture time);
the honesty gate keys on the **sentinel symbol**, not the line number, so it does
not churn as the readers shift.

## Anti-self-seal: hand-authored oracles + inertness differential

The `*.resolver.phase` / `*.statusline.phase` / `*.state.*` / `*.counters.stdout`
/ `*.scan.contains` files are **hand-authored oracles**, reasoned from the
documented legacy ladder — NOT regenerated by running the readers. Do NOT
"recapture" them by piping reader output into the files; that would make the
absolute-value assertions self-sealing.

Independently, `test_additive_rows_are_inert` proves the additive machine content
is inert by a **differential**: each reader's projection over the mixed log must
equal its projection over the same log with `advance_started`/`advance_committed`
rows dropped and the `invocation_id` field stripped (`_strip_additive`). This
holds even if someone regenerated the pinned files from a reader, so the
inertness guarantee never rests on the pinned values.

## Determinism / recapture harness

- **Synthetic slugs**: every case slug is a `rev-*` name that does not exist in
  the real `cortex/lifecycle/` tree. The test stages each fixture into a scratch
  `tmp_path/repo/cortex/lifecycle/<slug>/` — the real tree is never mutated.
- **statusline (bash reader)**: exercised deterministically by sourcing its
  phase-detection ladder fragment (shared with
  `tests/test_lifecycle_phase_parity.py` via `_invoke_statusline_ladder`) against
  the staged feature dir — not covered only by proxy.
- **Reader-list recapture**: run
  `uv run python -c "import sys; sys.path.insert(0,'tests'); from test_lifecycle_reverse_golden import enumerate_reader_sites; [print(s) for s in enumerate_reader_sites()]"`
  to re-derive the `path:line` values for the table above. It fails loudly if a
  reader dropped its sentinel.
- **Adding a case**: drop a `<case>.events.log` (+ optional artifacts) and the
  matching pinned-projection files; the test discovers it by glob. Author the
  expected files by hand from the ladder, never from reader output.
