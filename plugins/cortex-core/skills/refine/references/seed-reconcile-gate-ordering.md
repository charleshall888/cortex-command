# Seed → reconcile → gate ordering

`/cortex-core:refine` (and `/cortex-core:lifecycle`, which wraps it) must preserve a fixed order: **seed `lifecycle_start` → `reconcile-clarify` → §3b tier read**. This protects the critical-review gate's silent-skip behavior on non-`cortex-backlog` backends.

On a non-local backend (or Context B), the `lifecycle_start` seed is written without `--backlog-slug`, so it carries the canonical `simple`/`medium` defaults rather than any backlog-sourced values. The critical-review gate skips silently at `tier = simple`. So on those backends the gate stays alive *only* because `reconcile-clarify` — running at Spec-phase entry, before `specify.md` §3b — ratchets the lifecycle state up using **Clarify's computed** tier/criticality, passed as explicit `--complexity`/`--criticality` flags (never literals, never the seed defaults). If the §3b read ran before the reconcile, it would observe the seed `simple` and skip review.

Keep the three steps in order so the §3b read observes the ratcheted values. The local `cortex-backlog` arm is immune regardless: its `reconcile-clarify --backlog-slug` re-sources tier/criticality from backlog frontmatter, so the seed defaults never survive to the gate.
