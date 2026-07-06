# Complexity Escalation Gates

Two complexity-escalation gates run during `/cortex-core:refine` delegation.

## Research → Specify gate

At the Research → Specify transition, run `cortex-complexity-escalator <feature> --gate research_open_questions`.

- Exit 0, non-empty stdout: announce the escalation message and proceed to Specify at Complex tier.
- Exit 0, empty stdout: the gate did not fire — proceed to Specify at current tier.
- Non-zero exit: surface the stderr message and halt the phase transition until the failure is resolved.

## Specify → Plan gate

After spec approval, before the Specify → Plan transition, run `cortex-complexity-escalator <feature> --gate specify_open_decisions`. Same hook, different gate; exit-code branching is identical to the gate above.
