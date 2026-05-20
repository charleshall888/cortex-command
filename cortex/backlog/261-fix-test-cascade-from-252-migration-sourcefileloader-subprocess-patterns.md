---
schema_version: "1"
uuid: fa775672-f8c2-47ef-9bf3-933a1ba75ec3
title: "Fix test cascade from #252 migration (SourceFileLoader + subprocess patterns)"
status: backlog
priority: medium
type: chore
created: 2026-05-20
updated: 2026-05-20
parent: "252"
---
## Why

#252 migrated 13 bin/cortex-* scripts from canonical-Python to dual-channel bash wrappers. Per-task parity tests verified the promoted modules' byte-identical behavior, but pre-existing test files in tests/ that loaded those scripts via `importlib.SourceFileLoader` or invoked them via `subprocess.run('bin/cortex-X')` were not updated. The result: full `just test` run shows 58 failures + 28 errors across 10 test files. Tasks 11, 12, 15 agents proactively fixed their own downstream test cascade; the other promotion tasks did not.

Production behavior (wheel-tier entry points, dual-channel wrappers, remediation hints, PATH self-test, parity audit gate) is intact and on main. The damage is to dev-environment test infrastructure.

## Role / Integration

- Touch only test files in tests/ and cortex_command/dashboard/tests/.
- Two repair patterns:
  1. SourceFileLoader-on-bin → import from the promoted module (e.g. `from cortex_command.backlog.resolve_item import slugify` instead of loading bin/cortex-resolve-backlog-item as a module). Tasks 11, 12, 15 fixes are the model.
  2. `subprocess.run(['bin/cortex-X', ...])` patterns: either land binstubs via `uv tool install --reinstall --refresh`, OR rewrite the subprocess to use `sys.executable, '-m', 'cortex_command.X'`.
- Also patch `tests/test_cortex_log_invocation_parity.py` for the `id(tmp_path)` aliasing hazard Task 14's agent flagged (Task 6 didn't backport).

## Edges

- Affected test files (10): tests/test_resolve_backlog_item.py, tests/test_load_parent_epic.py, tests/test_check_prescriptive_prose.py, tests/test_commit_preflight.py, tests/test_superseded_frontmatter_tolerance.py, tests/test_variant_a_writer_sites_baseline.py, tests/test_clarify_critic_alignment_integration.py, tests/test_cortex_log_invocation_parity.py, cortex_command/dashboard/tests/test_feature_cards_pr_url.py, cortex_command/dashboard/tests/test_templates.py.
- tests/test_log_invocation_perf.py was pre-existing failure (unrelated).

## Touch points

- The Task 15 fix at tests/test_complexity_escalator.py (commit 5f0d16eb) is the canonical model for SourceFileLoader → module-import rewrites.
- Tasks 11 and 12 also updated _run_script helpers in their related tests.
- Closeout signal: `just test` exits 0 (or down to the pre-existing test_log_invocation_perf failure).