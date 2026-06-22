# Research: post-discovery-brief-over-cap

Implementation-level research for: when the discovery research→decompose gate
produces a brief that is anchor-valid but over the word cap, **post that brief**
(keeping the cap as a soft telemetry/warning signal) instead of discarding it and
dumping the raw `## Architecture` section.

## Decision context (from Clarify)

- **Post over-cap-but-anchored briefs.** Keep the word cap as a soft, non-blocking
  warning/telemetry signal — do **not** delete the cap concept.
- **Post at any length** — the cap is purely advisory; no runaway ceiling.
- **Unchanged fallback triggers:** empty brief, SDK/dispatch failure, and
  missing-decision-anchor briefs still fall back to the `## Architecture` section.
- Tier: **complex**; criticality: **high** (shared-skill gate, spec-adjacent contract).

## Codebase findings

### `validate_brief` — the shared predicate (`cortex_command/discovery.py:549-621`)

- Checks run **in order**: empty (587) → decision anchor (591) → alternatives (598)
  → tradeoff (606) → **word-cap (612-621, LAST)**. Because word-cap is the final
  check, a brief whose failure reason is `"word count N exceeds cap K"` **provably
  passed all three anchor checks** — an over-cap-reason brief is anchor-complete by
  construction.
- Signature `(ok: bool, reason: str)` — `reason` is `""` on success. ~18 call sites:
  2 production (`830`, `859` in `_cmd_generate_brief`), ~16 in tests. **No caller
  branches on over-cap-vs-anchor**; the bool drives all control flow, and `reason`
  is consumed only for retry feedback (`837`) and stderr/error text.

### Gate-render predicate (`skills/discovery/SKILL.md:88`; test mirror `tests/test_discovery_gate_brief.py:270-307`)

- Prose: fall back to `## Architecture` if **(generator exit non-zero) OR (brief.md
  missing) OR (brief.md fails decision-content validation)**.
- Test mirror `_render_gate`: renders `brief.md` iff
  `brief_path.is_file() and brief_text and validate_brief(brief_text)[0]` — reason
  discarded (`ok, _`, line 287).
- **Consequence:** the gate-render guard rejects *any* `validate_brief`-False brief,
  including over-cap. So displaying an over-cap brief requires either `validate_brief`
  to pass it, or the gate predicate to stop using the word-cap dimension.

### `_cmd_generate_brief` control flow (`cortex_command/discovery.py:727-890`)

- Over-cap currently flows through the unified `if not valid` retry (`836`), then the
  final `validation_failed` / `return 1` block (`861-867`) → **does not persist
  brief.md** → gate falls back. Persist + `return 0` happen only when valid (`876-890`).
- Retry-on-overflow (`836`) fires on **any** validation failure and interpolates the
  reason into the retry feedback (`837`).

### Frozen-contract surface (thinner than the clarify-critic feared)

- **No test asserts `over-cap → validate_brief returns False`.** The canonical-floor
  parity test (`test:841-880`) freezes only the *anchor* token sets. The one word-cap
  test (`test:149-153`) asserts `word_count <= cap` on **fixtures directly**
  (independent of `validate_brief`) — it survives an advisory-cap change. Test 4
  (`test:431-435`) deliberately keeps its brief **under** the cap so the rejection is
  anchor-missing, explicitly avoiding the over-cap path.
- `fix-validate-brief-substring-anchors-that/spec.md:70` notes "Brief over word cap …
  Unchanged" — but that was scoped to *that* fix (an f-string/anchor bug), not a
  permanent freeze. This lifecycle supersedes it.
- Retry template (`discovery.py:370-400`) references `"hard ceiling {cap+25}"` — wording
  to reconcile with the soft-cap semantics.
- Cap purpose (docstring `273-289` + `discovery-output-density-investigate-author-centric/word-cap-derivation.md`):
  a quality boundary that "distinguish[es] a tight gate brief from a full section dump"
  — this is precisely the **signal to preserve** as soft telemetry.

### Event consumers (`gate_brief_generated`)

- **No production code switches on `status`.** The emitter adds `brief_excerpt` only on
  `status == "validation_failed"` (`799-800`); `brief_word_count` has no consumers.
- Tests assert failure `status ∈ {validation_failed, empty, sdk_unavailable}` (`test:238`)
  and filter `validation_failed` (`test:490`) — both use anchor-missing input, so they
  are **unaffected** by reclassifying over-cap.
- `bin/.events-registry.md:119` documents `status` as `ok / fallback`; it must be updated
  for the new over-cap-posted status (events-registry pre-commit gate + the
  `grep -c` Done-When resolution rule).

## Mechanism — recommended

**Make the word cap advisory *inside* `validate_brief` (single source of truth).**

- `validate_brief` enforces empty + the three decision-content anchors only;
  over-cap-with-anchors returns `(True, "")`. Its `(bool, str)` signature is unchanged
  (no ripple across the ~18 call sites).
- Surface the overage separately via a small helper (e.g. `brief_word_overage(brief) -> int`,
  0 within cap else words-over), consumed by (a) `_cmd_generate_brief` for the
  soft-warning stderr line and the event status, and (b) the gate prose for a one-line
  soft note.
- Both callers then accept over-cap **automatically**: the generator persists +
  exits 0, and the gate-render guard (which calls `validate_brief()[0]`) renders the
  brief. The prose's "fails decision-content validation" wording becomes *more* accurate
  (it now means anchors-missing/empty only); we add the soft-note display alongside it.

### Alternative considered — rejected

Keep `validate_brief` strict on word-cap and add a separate `is_displayable_brief()`
(hard-gates only) for both the gate-render guard and the generator's persist decision.
Rejected: it splits the predicate into two near-identical functions and leaves
`validate_brief`'s over-cap-False semantics live, inviting drift between the two
callers. The advisory-in-`validate_brief` approach keeps a single predicate that both
callers already share.

## Files to change (inventory for Plan)

- `cortex_command/discovery.py` — soften `validate_brief`'s word-cap branch; add the
  overage helper; rework `_cmd_generate_brief`'s final block (persist + `ok_over_cap`
  + exit 0 when over-cap is the only failure); reconcile retry-template wording;
  update `GATE_BRIEF_WORD_CAP` docstring.
- `skills/discovery/SKILL.md:88` — reword the fallback-trigger list and add the over-cap
  soft-note display. (Canonical only; `plugins/cortex-core/skills/discovery/SKILL.md`
  mirror auto-regenerates via the pre-commit drift hook — do not hand-edit the mirror.)
- `bin/.events-registry.md:119` — register the `ok_over_cap` status.
- `tests/test_discovery_gate_brief.py` — add an over-cap-posts test (exit 0, brief.md
  persisted, gate renders brief not Architecture, `ok_over_cap` event); align the
  `_render_gate` helper / any retry-template assertion with the new behavior.

## Open Questions

1. **Retry-on-overflow:** keep one compression retry on over-cap before accepting, or
   accept immediately? *Deferred to Spec.* Recommendation: retain a single compression
   retry (it fires only when over-cap, preserves the deliberate resilience documented in
   the `GATE_BRIEF_WORD_CAP` docstring, and "post at any length" governs the *final
   accept*, not whether we attempt to tighten once). Confirm in the Spec interview /
   critical-review.

2. **Event-status shape:** a distinct `ok_over_cap` status vs `ok` + an `over_cap: true`
   field? *Deferred to Spec.* Recommendation: distinct `ok_over_cap` — an explicit,
   greppable telemetry signal that directly serves "keep the cap as a soft signal," and
   safe because no consumer switches on `status`.

3. **Soft-warning copy:** exact wording of the gate's one-line soft note and the stderr
   warning. *Deferred to Spec* (cosmetic; settled at authoring time).

All open questions are explicitly deferred with rationale → Research Exit Gate passes.

## Risks

- `validate_brief` is shared; softening it also affects the gate-render guard — but that
  is the **intended** effect (both callers should accept over-cap). Verified no other
  caller relies on the over-cap-False return.
- Plugin mirror regenerates via pre-commit; edit the canonical `skills/discovery/SKILL.md`
  only and let `build-plugin` regenerate the mirror in the same commit.
- The events-registry pre-commit gate and the backlog `grep -c` Done-When resolution
  require `ok_over_cap` to be registered before any acceptance check greps for it.
