# Complexity Escalation Gates

Two complexity-escalation gates run during `/cortex-core:refine` delegation.

## Research → Specify gate

At the Research → Specify transition, run `cortex-complexity-escalator <feature> --gate research_open_questions`.

- On exit 0 with non-empty stdout: announce the escalation message to the user and proceed to Specify at Complex tier.
- On exit 0 with empty stdout: the gate did not fire. Proceed to Specify at current tier.
- On non-zero exit: surface the stderr message to the user and halt the phase transition. Resume only after the underlying failure is resolved.

## Specify → Plan gate

After spec approval, before the Specify → Plan transition, run `cortex-complexity-escalator <feature> --gate specify_open_decisions`. Same hook, different gate.

- Exit-code branching is identical to the Research → Specify gate above.
