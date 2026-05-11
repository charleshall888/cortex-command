# Complexity Escalation Gates

During `/cortex-core:refine` delegation, two complexity-escalation gates run at phase transitions. They invoke `cortex-complexity-escalator` and route based on exit code and stdout.

## Research → Specify gate

At the Research → Specify transition, run `cortex-complexity-escalator <feature> --gate research_open_questions`.

- On exit 0 with non-empty stdout: announce the escalation message to the user and proceed to Specify at Complex tier.
- On exit 0 with empty stdout: the gate did not fire (already-complex, missing section, or below threshold). Proceed to Specify at current tier.
- On non-zero exit: surface the stderr message to the user and halt the phase transition. Resume only after the underlying failure is resolved (e.g., re-run with a corrected slug, restore sandbox write permission, address a malformed input file).

## Specify → Plan gate

After spec approval, before the Specify → Plan transition, run `cortex-complexity-escalator <feature> --gate specify_open_decisions`. Same hook, different gate.

- Exit-code branching is identical to the Research → Specify gate above.
