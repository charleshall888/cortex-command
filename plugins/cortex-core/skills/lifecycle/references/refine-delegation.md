# Refine Delegation Steps

Follow when `cortex/lifecycle/{feature}/research.md` and/or `spec.md` is missing and lifecycle delegates to `/cortex-core:refine`.

1. **Read refine SKILL.md verbatim** (`<REFINE_SKILL_MD>`) so lifecycle stays in sync as `/cortex-core:refine` evolves.
2. **Epic context + starting point** — apply the Epic-Context Rules below: the Starting-Point rule always, Epic Research Detection when `phase = research`, and Epic Context Injection when `epic_research_path` was recorded.
3. **Phase progression** — lifecycle owns `cortex/lifecycle/{feature}/events.log`, but the refine sub-phase boundaries (clarify→research, research→specify) are no longer emitted from this prose. They are derived from artifact presence and served by `cortex-lifecycle-next`; the phase detector reads only the boundary-carrying `specify→plan`/`plan→…` rows, not these sub-phase breadcrumbs, so the served loop needs no in-prose `phase_transition` emission here. The `specify→plan` boundary stays verb-owned — the spec-approve verb (`cortex-lifecycle-advance`, invoked by specify.md §4 under lifecycle-wrapped refine) records it when its transition flag is set.
4. **Complexity escalation** — run the Research → Specify and Specify → Plan complexity-escalator gates below.
5. **Post-refine commit** — after the `phase_transition specify→plan` (or `lifecycle_cancelled`) row is logged and before auto-advancing to Plan, follow the Post-Refine Commit rules below. On commit failure, halt rather than advance.

## Epic-Context Rules

### Epic Research Detection

When `phase = research` (no lifecycle directory yet), check whether discovery already produced epic-level artifacts — consume Step 1's parsed frontmatter, don't re-scan. Take `discovery_source` as the epic research path (falling back to `research`), recording it only if the file exists (warn and treat as unset otherwise); record `spec` as `epic_spec_path` only alongside a recorded, existing research path. No match or missing field means no epic context.

**Do not copy epic content into lifecycle files** — epic research spans all tickets, so copying bleeds cross-ticket context into this ticket. Record the paths as reference only; `/cortex-core:refine` produces ticket-specific research.md and spec.md that link the epic artifacts without reproducing them. If found, announce `epic_research_path` as background reference for the research and spec phases.

### Epic Context Injection (during /cortex-core:refine delegation)

When `epic_research_path` was recorded, read it (and `{epic_spec_path}` if present) as background before Clarify, and instruct `/cortex-core:refine` to add a `## Epic Reference` section to `research.md` and a preamble note to `spec.md` linking the epic path — scoped to this ticket, without reproducing epic content.

### Refine Starting-Point Rules

`/cortex-core:refine`'s Step 2 (Check State) checks for `cortex/lifecycle/{lifecycle-slug}/research.md` and `spec.md` at those exact paths. Both exist → proceeds normally. A `discovery_source`/`research` field pointing to epic research elsewhere is background only — refine still runs its full Research phase to produce `cortex/lifecycle/{slug}/research.md`.

## Complexity Escalation Gates

Two complexity-escalation gates run during `/cortex-core:refine` delegation.

**Research → Specify gate** — at the Research → Specify transition, run `cortex-complexity-escalator <feature> --gate research_open_questions`.

- Exit 0, non-empty stdout: announce the escalation message and proceed to Specify at Complex tier.
- Exit 0, empty stdout: the gate did not fire — proceed to Specify at current tier.
- Non-zero exit: surface the stderr message and halt the phase transition until the failure is resolved.

**Specify → Plan gate** — after spec approval, before the Specify → Plan transition, run `cortex-complexity-escalator <feature> --gate specify_open_decisions`. Same hook, different gate; exit-code branching is identical to the gate above.

## Post-Refine Commit

Follow this when refine returns control at the Specify → Plan boundary.

**Flag check** — run `cortex-read-commit-artifacts` (the `commit-artifacts` flag from `cortex/lifecycle.config.md`). `false` → skip the commit silently, return to lifecycle Step 3. `true` → proceed to Staging.

**Staging** — stage the refine artifact set, then act on the verb's `signal`:

```
cortex-lifecycle-stage-artifacts --phase refine --feature {feature}
```

It prints `{"signal": "staged"|"nothing_staged", "staged_paths": [...]}`: `nothing_staged` → exit silently, return to Step 3 (auto-advances to Plan on resume); `staged` → proceed to Commit. A non-zero verb exit is a staging failure: halt before Plan rather than commit a partial set.

**Commit subject** — from the staged set (approval stages `spec.md`, cancel omits it): `spec.md` staged → `Refine {feature}: research and spec`; absent → `Refine {feature}: cancelled at spec approval`. Invoke `/cortex-core:commit` with that subject and a one-line body (e.g. `- Research and spec produced by /cortex-core:refine for {feature}`).

**Halt-before-Plan gate** — if `/cortex-core:commit` exits non-zero (index lock, pre-commit hook rejection, working-tree conflict), surface the error and HALT — do not auto-advance to Plan. The uncommitted `phase_transition` / `lifecycle_cancelled` row (emitted by the spec-approve verb, `cortex-lifecycle-advance`, in specify.md §4) waits until the operator resolves the failure and re-invokes `/cortex-core:lifecycle`; resume continues from the current phase. Hand-edits made before re-invocation are staged and committed under the Refine subject as-is — do not split, re-title, or pause.
