# Seed → reconcile → gate ordering

`/cortex-core:refine` (and `/cortex-core:lifecycle`, which wraps it) must preserve a fixed order: **seed `lifecycle_start` → `reconcile-clarify` → §3b tier read**.

On a non-local backend (or Context B), the `lifecycle_start` seed is written without `--backlog-slug`, so it carries the canonical `simple`/`medium` defaults, and the critical-review gate skips silently at `tier = simple`. The gate stays alive only via the **tier ratchet**: `reconcile-clarify`, running at Spec-phase entry before `specify.md` §3b, ratchets the lifecycle state up using **Clarify's computed** tier/criticality (explicit `--complexity`/`--criticality` flags, never literals or seed defaults). Reversing the order would let §3b observe the seed `simple` and skip review.

The local `cortex-backlog` arm is immune regardless: its `reconcile-clarify --backlog-slug` re-sources tier/criticality from backlog frontmatter, so the seed defaults never survive to the gate.
