---
schema_version: "1"
uuid: 350677ba-faa6-4aef-98ce-c6f6faab0edd
title: "Gate worktree option on console-script reachability, not bare-Python importability"
status: complete
priority: medium
type: feature
created: 2026-05-26
updated: 2026-05-27
complexity: complex
criticality: high
spec: cortex/lifecycle/gate-worktree-option-on-console-script/spec.md
areas: ['lifecycle']
---
## Why

The "Implement on feature branch with worktree" option silently disappears from the lifecycle implement menu in consumer repos installed via the documented `uv tool install` path. Users in their own project repos see only "Implement on current branch" and "Create feature branch", with no diagnostic explaining why the worktree option is missing or how to restore it. Even users whose runner CLI is correctly installed and whose `cortex-*` console scripts work fine from anywhere experience the disappearance — the option is reachable only when the lifecycle runs from the cortex-command source tree itself, which is not the documented consumer install topology.

## Role

A presence check that decides whether to offer the worktree-based interactive lifecycle option by gating on whether the runner CLI's worktree-creation functionality is actually reachable from the calling shell. The check replaces a proxy signal (bare-Python module importability) that diverges from actual reachability under the documented install topology, so the gate's verdict matches the downstream path's true availability instead of an unrelated environmental coincidence.

## Integration

The check feeds the implement-phase branch-mode picker that populates the lifecycle skill's branch-mode menu. Its outbound consumer is the menu's options array and the interactive interactive-worktree-creation sub-flow that runs once the worktree option is chosen. Its inbound dependency is the runner CLI's `[project.scripts]` console-script surface — the only invocation mechanism that holds across both source-tree development and uv-tool isolated-venv install. The interactive worktree-creation sub-flow itself must align with the same surface, since gate and gated path must agree on what "available" means.

## Edges

- Must gate on a signal that holds across both source-tree development and the documented uv-tool install topology — not on bare-Python module importability, which holds in the source tree only by virtue of the cwd-in-sys.path accident.
- Must preserve the architectural intent from the archived "graceful degradation when runner absent" spec — when the runner CLI is genuinely absent, the worktree option must still be hidden.
- The worktree-creation sub-flow that the gate guards must invoke runner functionality through the same console-script surface the gate detects, so that a passing gate implies a working downstream path.
- Non-goal: relaxing the gate to always-on. The "no runner installed" case is a real install class the option must still degrade for.
- Non-goal: changing the project's install topology away from uv-tool isolation to restore bare-Python importability. That would invert prior architectural decisions on non-editable wheel support and plugin isolation.
- A class-level lint guard against bare-Python `cortex_command` imports in skill files belongs in scope. Narrow literal-substring grep guards in the precedent lifecycle failed to catch this regression class once already and will fail again without a class-level rule.

## Touch points

- `skills/lifecycle/references/implement.md:55-66` — §1 runtime probe using `importlib.util.find_spec('cortex_command')` via bare `python3 -c`.
- `skills/lifecycle/references/implement.md:123-128` — interactive step iii `from cortex_command.pipeline.worktree import create_worktree` fenced as a `python` block, invoked via bare python3.
- `pyproject.toml` `[project.scripts]` table — no entry currently exposes `cortex_command.pipeline.worktree.create_worktree` as a console script; the corresponding gate signal therefore does not yet exist on PATH.
- `cortex/lifecycle/archive/lifecycle-skill-gracefully-degrades-autonomous-worktree-option-when-runner-absent/spec.md` — authoritative intent document for the gate's purpose ("hide the option when the runner CLI isn't installed").
- `cortex/backlog/248-convert-bin-cortex-and-skill-embedded-python3-callsites-to-cli-subcommands.md` and `cortex/lifecycle/convert-bin-cortex-and-skill-embedded/spec.md:51,53` — precedent lifecycle that converted four specific snippets; the verification grep `'python3 -c "import cortex_command'` is a literal-substring pattern that does not catch multi-line probes (e.g., `python3 -c "\nimport sys\n..."`) or heredoc-fed Python blocks.
- `cortex_command/lint/contract.py`, `cortex_command/lint/prescriptive_prose.py` — existing lint surfaces; no rule against bare-Python `cortex_command` imports in `skills/**/*.md`.