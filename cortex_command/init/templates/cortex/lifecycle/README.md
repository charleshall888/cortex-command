# Lifecycle

This directory tracks structured feature development. Each feature gets its
own subdirectory named after the feature slug, containing the artifacts
produced by the lifecycle phases.

## Phases

1. **research** - gather context; produce `research.md`
2. **specify** - pin down requirements and decisions; produce `spec.md`
3. **plan** - decompose into ordered tasks; produce `plan.md`
4. **implement** - execute tasks, committing each; append to `events.log`
5. **review** - critical review of the shipped change
6. **complete** - close out and update the backlog item

## Artifact layout per feature

```
cortex/lifecycle/<feature-slug>/
  index.md        # phase + status + links to artifacts
  research.md     # phase 1 output
  spec.md         # phase 2 output
  plan.md         # phase 3 output
  events.log      # phase 4 per-task events
```

## Configuration

`cortex/lifecycle.config.md` at the repo root sets project-specific overrides such
as the test command, whether to skip the specify or review phases, and any
demo commands surfaced in review artifacts.

## Session state

`cortex/lifecycle/sessions/` stores overnight-runner session state. It is per-machine
and should generally not be committed.
