# A→B Downgrade Rubric and Worked Examples

The synthesizer in Step 2d applies this rubric when evaluating each
A-class finding's `"fix_invalidation_argument"` field. A-class status
requires a concrete causal link from the cited evidence to a failure of
the proposed change. Downgrade A→B when any trigger fires; ratify as A
when the argument names a concrete failure mechanism.

## Trigger Definitions

- **Trigger 1 (absent)**: the `"fix_invalidation_argument"` field is absent or empty.
- **Trigger 2 (restates)**: the argument restates the finding text without adding a causal link from evidence to fix-failure.
- **Trigger 3 (adjacent)**: the argument identifies an adjacent issue (B-class material) rather than fix-invalidation. **Straddle exemption**: when the finding's `straddle_rationale` field is present, Straddle Protocol bias-up takes precedence and trigger 3 does NOT fire — ratify as A.
- **Trigger 4 (vague)**: the argument is vague or speculative ("might cause", "could break") without a concrete failure path.

Ratify as A when the `"fix_invalidation_argument"` names a concrete mechanism by which the proposed change, as written, would fail to produce its stated outcome.

Reclassification note format: `Synthesizer re-classified finding N from A→B: <rationale>`.

## Worked Examples

### Worked example 1 (absent): ratify

- Candidate `"fix_invalidation_argument"`: "the patch sets `retries=0` but leaves `retry_on_timeout=True`, so the loop in `client.py:142` still re-enters on timeout — the documented fix never takes effect."
- Trigger applies: none — argument is present and names a concrete mechanism.
- Disposition: ratify as A. The argument carries a concrete causal link from evidence (`retry_on_timeout=True`) to a fix-failure (loop still re-enters).

### Worked example 2 (absent): downgrade

- Candidate `"fix_invalidation_argument"`: (field omitted from envelope).
- Trigger applies: 1 (absent). The reviewer tagged the finding A but supplied no fix-invalidation argument.
- Disposition: downgrade A→B. Note: `Synthesizer re-classified finding N from A→B: fix_invalidation_argument absent; A-class requires a concrete failure path.`

### Worked example 3 (restates): ratify

- Candidate `"fix_invalidation_argument"`: "the proposed null-check guards `user.email` but the crash trace at `auth.py:88` shows the NPE originates from `user.profile.email`, two attribute hops up — the guard is on the wrong object."
- Trigger applies: none — argument adds a causal link (wrong object guarded → NPE persists), not a restatement.
- Disposition: ratify as A.

### Worked example 4 (restates): downgrade

- Candidate `"fix_invalidation_argument"`: "the fix does not work because the bug is not actually fixed by this change."
- Trigger applies: 2 (restates). The argument restates the finding ("does not work") without a causal mechanism linking evidence to fix-failure.
- Disposition: downgrade A→B. Note: `Synthesizer re-classified finding N from A→B: fix_invalidation_argument restates the finding without a causal link.`

### Worked example 5 (adjacent): ratify

- Candidate `"fix_invalidation_argument"`: "the patch updates the validator but the cache layer at `cache.py:55` still serves the pre-fix payload for 1h — within the documented 'effective immediately' window the fix is invisible to callers."
- `straddle_rationale`: "splits between fix-invalidation (cache window swallows the fix) and adjacent cache-invalidation gap; biasing up because the cache window collapses the documented outcome."
- Trigger applies: 3 would fire on adjacency grounds, BUT `straddle_rationale` is populated — Straddle exemption activates and trigger 3 does NOT fire.
- Disposition: ratify as A.

### Worked example 6 (adjacent): downgrade

- Candidate `"fix_invalidation_argument"`: "the analytics event one layer up still fires on the old code path, so downstream dashboards will be wrong."
- `straddle_rationale`: (absent).
- Trigger applies: 3 (adjacent). The argument describes a B-class adjacent gap (analytics misalignment) rather than fix-invalidation of the proposed change itself; no Straddle exemption because `straddle_rationale` is not set.
- Disposition: downgrade A→B. Note: `Synthesizer re-classified finding N from A→B: fix_invalidation_argument describes an adjacent gap, not fix-invalidation; no straddle_rationale present.`

### Worked example 7 (vague): ratify

- Candidate `"fix_invalidation_argument"`: "the migration drops the index before backfilling the new column, so the backfill query at `migrate.py:212` will table-scan a 40M-row table and time out under the 30s statement timeout — the migration aborts mid-fix."
- Trigger applies: none — argument names a concrete failure path (index drop → table scan → statement timeout → abort).
- Disposition: ratify as A.

### Worked example 8 (vague): downgrade

- Candidate `"fix_invalidation_argument"`: "this might cause performance issues and could break things under load."
- Trigger applies: 4 (vague). Hedged language ("might cause", "could break") with no concrete failure path.
- Disposition: downgrade A→B. Note: `Synthesizer re-classified finding N from A→B: fix_invalidation_argument is speculative ("might cause", "could break") with no concrete failure path.`
