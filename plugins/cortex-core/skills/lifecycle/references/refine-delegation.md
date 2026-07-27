# Refine Delegation

Follow when `research.md` and/or `spec.md` is missing and lifecycle delegates to `/cortex-core:refine`.

1. **Read refine's SKILL.md verbatim** (`<REFINE_SKILL_MD>`) so lifecycle stays in sync as refine evolves.
2. Apply the Epic-Context rules below.
3. Run the two complexity-escalation gates below.
4. After the spec-exit row is logged and before auto-advancing to Plan, follow Post-Refine Commit below. On commit failure, halt rather than advance.

Lifecycle owns `cortex/lifecycle/{feature}/events.log`, but the refine sub-phase boundaries (clarify→research, research→specify) are **not** emitted from this prose — they're derived from artifact presence and served by `cortex-lifecycle-next`. The `specify→plan` boundary stays verb-owned: the spec-approve verb records it when its transition flag is set.

## Epic context

**Detection** (when `phase = research`, no lifecycle directory yet): consume Step 1's parsed frontmatter, don't re-scan. Take `discovery_source` as the epic research path (falling back to `research`), recording it only if the file exists — warn and treat as unset otherwise. Record `spec` as `epic_spec_path` only alongside a recorded, existing research path.

**Do not copy epic content into lifecycle files.** Epic research spans all tickets, so copying bleeds cross-ticket context into this one. Record the paths as reference only and announce `epic_research_path` as background for research and spec.

**Injection**: when a path was recorded, read it (and `{epic_spec_path}` if present) as background before Clarify, and instruct refine to add a `## Epic Reference` section to `research.md` and a preamble note to `spec.md` linking the epic path — scoped to this ticket, without reproducing epic content.

**Starting point**: refine's Step 2 checks `cortex/lifecycle/{lifecycle-slug}/research.md` and `spec.md` at those exact paths. A `discovery_source`/`research` field pointing at epic research elsewhere is background only — refine still runs its full Research phase to produce this ticket's own `research.md`.

## Complexity escalation gates

At the Research → Specify transition, and again after spec approval before the Specify → Plan transition:

```bash
cortex-complexity-escalator <feature> --gate research_open_questions
cortex-complexity-escalator <feature> --gate specify_open_decisions
```

Exit 0 with non-empty stdout → announce the escalation and proceed at Complex tier. Exit 0 with empty stdout → the gate didn't fire; proceed at the current tier. Non-zero → surface the stderr message and halt the transition until it's resolved.

## Post-refine commit

At the Specify → Plan boundary, run `cortex-read-commit-artifacts`: `false` → skip silently and return to lifecycle Step 3; `true` → stage:

```
cortex-lifecycle-stage-artifacts --phase refine --feature {feature}
```

`nothing_staged` → exit silently, return to Step 3 (auto-advances to Plan on resume). `staged` → commit. A non-zero exit is a staging failure: halt before Plan rather than commit a partial set.

Subject from the staged set — approval stages `spec.md`, cancel omits it: `Refine {feature}: research and spec`, or `Refine {feature}: cancelled at spec approval`. Invoke `/cortex-core:commit` with a one-line body.

**Halt before Plan** if `/cortex-core:commit` exits non-zero (index lock, hook rejection, tree conflict): surface the error and stop — do not auto-advance. The uncommitted transition row waits until the operator resolves it and re-invokes `/cortex-core:lifecycle`; resume continues from the current phase. Hand-edits made before re-invocation are staged and committed under the same subject as-is — do not split, re-title, or pause.
