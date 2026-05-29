---
feature: rescope-cortex-init-ensure-to-never
parent_backlog_uuid: a66a9fe8-67c4-4243-8f31-f80e289a6528
parent_backlog_id: 273
artifacts: ["research", "spec", "plan", "review"]
tags: [cortex-init, distribution, sandbox, in-session]
created: 2026-05-29
updated: 2026-05-29
---
# [[273-rescope-cortex-init-ensure-to-never-write-claude|Rescope cortex init --ensure to never write ~/.claude/]]

Feature lifecycle for [[273-rescope-cortex-init-ensure-to-never-write-claude]].

- Research: [[rescope-cortex-init-ensure-to-never/research|research.md]]
- Spec: [[rescope-cortex-init-ensure-to-never/spec|spec.md]]
- Plan: [[rescope-cortex-init-ensure-to-never/plan|plan.md]]

## Notes

- 2026-05-29 (Plan resume): Runtime tier/criticality reconciled from refine-recorded
  simple/medium up to backlog #273's complex/high (complexity_override + criticality_override
  in events.log), per operator. Adds the forced /critical-review gate before plan approval.
- 2026-05-29 (Plan resume): `cortex-lifecycle-init-ensure` gate failed with the exact
  `~/.claude/.settings.local.json.lock` sandbox PermissionError that this feature exists to
  fix (present in installed v2.15.3 and identical at repo HEAD; not an install-staleness issue).
  Marker present, no real cortex/ drift. Gate overridden — Plan writes nothing to ~/.claude/ —
  rather than bypass the sandbox (the anti-pattern under repair).
