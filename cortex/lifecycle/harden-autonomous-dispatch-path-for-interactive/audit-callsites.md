# Audit: `python3 -m cortex_command.*` Callsites

**Audit date**: 2026-05-12
**Grep command**:
```
grep -rn 'python3 -m cortex_command\.' \
  skills/ hooks/ claude/ bin/ docs/ justfile tests/
```
(Justfile.local not present; skipped.)

## Naming convention rationale

Every promoted console-script name uses kebab-case prefixed with `cortex-`. This convention
mirrors the existing bin-wrapper naming already established in `bin/cortex-backlog-ready`,
`bin/cortex-morning-review-complete-session`, and all other utilities shipped via the
`cortex-core` plugin. Kebab-case is the pip/PEP 517 idiomatic form for `[project.scripts]`
entries and is shell-tab-completion-friendly. The `cortex-` prefix namespaces the scripts
against system PATH collisions (verified via `command -v` at audit time) and makes provenance
visible at a glance in shell history and `ps` output. Where a module path contains sub-package
dots (e.g., `cortex_command.overnight.daytime_pipeline`), only the terminal component is used
for the script name (e.g., `cortex-daytime-pipeline`), except when disambiguation is required
(e.g., `cortex_command.dashboard.seed` → `cortex-dashboard-seed` to distinguish it from any
future `cortex-seed` utility).

## Collision check

All proposed names verified via `command -v <name>` against a clean PATH on 2026-05-12.
`cortex-backlog-ready` was found at the cortex-core plugin mirror path
(`~/.claude/plugins/cache/cortex-command/cortex-core/.../bin/cortex-backlog-ready`); this is
the cortex-command package's own wrapper script and is not an external collision — the
`[project.scripts]` console-script will supersede it on a `uv tool install --reinstall`. All
other names were CLEAR.

---

## Callsite table

Format: `{file}:{line} → cortex_command.{module} → {proposed-console-script-name}`

### skills/

| Callsite | Module | Proposed console-script |
|---|---|---|
| `skills/critical-review/SKILL.md:45` | `cortex_command.critical_review` | `cortex-critical-review` |
| `skills/critical-review/SKILL.md:69` | `cortex_command.critical_review` | `cortex-critical-review` |
| `skills/critical-review/SKILL.md:85` | `cortex_command.critical_review` | `cortex-critical-review` |
| `skills/critical-review/references/verification-gates.md:14` | `cortex_command.critical_review` | `cortex-critical-review` |
| `skills/critical-review/references/verification-gates.md:47` | `cortex_command.critical_review` | `cortex-critical-review` |
| `skills/critical-review/references/verification-gates.md:76` | `cortex_command.critical_review` | `cortex-critical-review` |
| `skills/discovery/SKILL.md:60` | `cortex_command.discovery` | `cortex-discovery` |
| `skills/discovery/SKILL.md:84` | `cortex_command.discovery` | `cortex-discovery` |
| `skills/lifecycle/SKILL.md:80` | `cortex_command.common` | `cortex-common` |
| `skills/lifecycle/references/implement.md:19` | `cortex_command.overnight.daytime_pipeline` | `cortex-daytime-pipeline` |
| `skills/lifecycle/references/implement.md:83` | `cortex_command.overnight.daytime_dispatch_writer` | `cortex-daytime-dispatch-writer` |
| `skills/lifecycle/references/implement.md:91` | `cortex_command.overnight.daytime_pipeline` | `cortex-daytime-pipeline` |
| `skills/lifecycle/references/implement.md:99` | `cortex_command.overnight.daytime_dispatch_writer` | `cortex-daytime-dispatch-writer` |
| `skills/lifecycle/references/implement.md:119` | `cortex_command.overnight.daytime_result_reader` | `cortex-daytime-result-reader` |
| `skills/morning-review/SKILL.md:73` | `cortex_command.overnight.report` | `cortex-report` |
| `skills/morning-review/SKILL.md:141` | `cortex_command.overnight.report` | `cortex-report` |
| `skills/morning-review/references/walkthrough.md:28` | `cortex_command.overnight.report` | `cortex-report` |
| `skills/morning-review/references/walkthrough.md:559` | `cortex_command.overnight.report` | `cortex-report` |

### hooks/

| Callsite | Module | Proposed console-script |
|---|---|---|
| `hooks/cortex-scan-lifecycle.sh:425` | `cortex_command.pipeline.metrics` | `cortex-pipeline-metrics` |

### claude/

No `python3 -m cortex_command.*` callsites found.

### bin/

| Callsite | Module | Proposed console-script |
|---|---|---|
| `bin/cortex-backlog-ready:7` | `cortex_command.backlog.ready` | `cortex-backlog-ready` |
| `bin/cortex-morning-review-complete-session:7` | `cortex_command.overnight.complete_morning_review_session` | `cortex-morning-review-complete-session` |
| `bin/cortex-morning-review-complete-session:14` | `cortex_command.overnight.complete_morning_review_session` | `cortex-morning-review-complete-session` |

Note: `bin/cortex-backlog-ready:7` and `bin/cortex-morning-review-complete-session:7,14` are
existing shell wrappers that themselves invoke `python3 -m cortex_command.*`. Once the
console-script entries are promoted to `[project.scripts]`, these wrappers' branch (a) calls
will become redundant and the wrappers can delegate directly to the console script; that
cleanup is tracked under R14.

### docs/

| Callsite | Module | Proposed console-script |
|---|---|---|
| `docs/overnight-operations.md:68` | `cortex_command.overnight.integration_recovery` | `cortex-integration-recovery` |
| `docs/overnight-operations.md:194` | `cortex_command.overnight.integration_recovery` | `cortex-integration-recovery` |
| `docs/overnight-operations.md:200` | `cortex_command.overnight.interrupt` | `cortex-interrupt` |
| `docs/overnight-operations.md:312` | `cortex_command.overnight.integration_recovery` | `cortex-integration-recovery` |
| `docs/overnight-operations.md:673` | `cortex_command.overnight.auth` | `cortex-auth` |

### justfile

| Callsite | Module | Proposed console-script |
|---|---|---|
| `justfile:79` | `cortex_command.overnight.smoke_test` | `cortex-smoke-test` |
| `justfile:117` | `cortex_command.dashboard.seed` | `cortex-dashboard-seed` |
| `justfile:121` | `cortex_command.dashboard.seed` | `cortex-dashboard-seed` |

### tests/

| Callsite | Module | Proposed console-script |
|---|---|---|
| `tests/test_critical_review_path_validation.py:12` | `cortex_command.critical_review` | `cortex-critical-review` |
| `tests/test_critical_review_path_validation.py:171` | `cortex_command.critical_review` | `cortex-critical-review` |
| `tests/test_daytime_preflight.py:319` | `cortex_command.overnight.daytime_pipeline` | `cortex-daytime-pipeline` |
| `tests/test_daytime_preflight.py:332` | `cortex_command.overnight.daytime_dispatch_writer` | `cortex-daytime-dispatch-writer` |
| `tests/test_daytime_preflight.py:356` | `cortex_command.overnight.daytime_pipeline` | `cortex-daytime-pipeline` |
| `tests/test_daytime_preflight.py:403` | `cortex_command.overnight.daytime_result_reader` | `cortex-daytime-result-reader` |
| `tests/test_daytime_preflight.py:419` | `cortex_command.overnight.daytime_dispatch_writer` | `cortex-daytime-dispatch-writer` |

---

## Candidate module → console-script name index

The following 15 distinct modules appear across the callsite audit. All 13 candidates named in
research.md (lines 32-46) are present; 2 additional modules were discovered during the grep
sweep (`cortex_command.overnight.smoke_test`, `cortex_command.dashboard.seed`).

| Module | Proposed console-script | Callable | Collision check |
|---|---|---|---|
| `cortex_command.overnight.daytime_pipeline` | `cortex-daytime-pipeline` | `_run` | CLEAR |
| `cortex_command.overnight.daytime_dispatch_writer` | `cortex-daytime-dispatch-writer` | `main` | CLEAR |
| `cortex_command.overnight.daytime_result_reader` | `cortex-daytime-result-reader` | `main` | CLEAR |
| `cortex_command.overnight.report` | `cortex-report` | `main` | CLEAR |
| `cortex_command.overnight.integration_recovery` | `cortex-integration-recovery` | `main` | CLEAR |
| `cortex_command.overnight.interrupt` | `cortex-interrupt` | `main` | CLEAR |
| `cortex_command.overnight.complete_morning_review_session` | `cortex-morning-review-complete-session` | `main` | CLEAR |
| `cortex_command.critical_review` | `cortex-critical-review` | `main` | CLEAR |
| `cortex_command.discovery` | `cortex-discovery` | `main` | CLEAR |
| `cortex_command.common` | `cortex-common` | `main` | CLEAR |
| `cortex_command.backlog.ready` | `cortex-backlog-ready` | `main` | cortex-core plugin mirror (same package; not external) |
| `cortex_command.pipeline.metrics` | `cortex-pipeline-metrics` | `main` | CLEAR |
| `cortex_command.overnight.auth` | `cortex-auth` | `_main` | CLEAR |
| `cortex_command.overnight.smoke_test` | `cortex-smoke-test` | `main` | CLEAR |
| `cortex_command.dashboard.seed` | `cortex-dashboard-seed` | `main` | CLEAR |
