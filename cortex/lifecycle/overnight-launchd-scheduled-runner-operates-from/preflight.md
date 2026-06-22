# Task 7 — Installed-wheel / launchd verification (R9)

**Status:** operator-attested verification performed (audit evidence below). This is NOT a structural lifecycle gate — see the Risks note in `plan.md` (the lifecycle completes on `[x]`-task tally + `feature_complete` + green `just test`, none of which observe wheel/launchd state).

## Which check ran

A **faithful installed-wheel-equivalent invocation under the real launchd filesystem/environment condition**, rather than a live launchd fire. Rationale for the substitution:

- The true global reinstall (`uv tool install --force`) replaces the `cortex` console-script for **all** sessions sharing the host install; doing it mid-lifecycle would disrupt the concurrent lifecycle sessions active in this working tree, and is premature — these commits have not yet passed the high-criticality **Review** gate.
- The wheel ships the same `cortex_command/overnight/cli_handler.py` that the repo's editable `.venv` already exposes, so running the editable interpreter (`<repo>/.venv/bin/python`) from `cwd=/` with `CORTEX_REPO_ROOT` stripped exercises the **exact code the wheel will contain**, in the **exact launchd condition** (`cwd=/`, bare env, `git rev-parse` fails because `/` is not a repo).

## Command

```
cd /
env -u CORTEX_REPO_ROOT <repo>/.venv/bin/python  # import cortex_command.overnight.cli_handler
  _resolve_repo_path(state_project_root=<marker-bearing tmp repo>)   # fixed path
  _resolve_repo_path()                                               # old / launchd path
```

## Observed result (PASS)

| Condition | Resolved `repo_path` | Expectation |
|---|---|---|
| `cwd=/`, no `CORTEX_REPO_ROOT` | (env confirms both: cwd `/`, `CORTEX_REPO_ROOT` absent) | launchd condition reproduced |
| **Fixed** — `state_project_root=<repo>` | `/private/tmp/claude-503/t7_fakerepo` (real root, `.resolve()`d) — **not `/`** | recovers real root via state precedence |
| **Unfixed contrapositive** — `state_project_root=None` | `/` | reproduces the #311 bug (proves the fix is causal) |
| Marker guard | rejects `/` and `None`; accepts the marker-bearing repo | guard sound |

The fixed resolver recovers the real project root under the launchd condition; the unfixed code path reproduces the exact `/` mis-resolution #311 reports. Full `handle_start` integration (the `--launchd` child via `runner.run` and the `--scheduled` parent via `_spawn_runner_async`) is covered by the un-patched regression test `cortex_command/overnight/tests/test_launchd_repo_root.py` (Task 4, commit 8e64d9d7).

## Remaining operator action (deploy-time, post-merge)

To make the fix reach production scheduled runs, reinstall the global wheel after merge:

```
uv tool install --force git+https://github.com/charleshall888/cortex-command.git@<new-tag>
```

Then (optional, highest-fidelity confirmation) schedule a fire 1–2 min out (`cortex overnight schedule …`), let launchd fire, and confirm `cortex/lifecycle/sessions/<id>/active-session.json` `repo_path` is the real project root (not `/`) and `overnight-events.log` has no `morning_report_commit_failed` with `details.project_root: "/"`.

This document is the audit record (R9); the externally-observed root above — not this file — is the pass condition.
