# Review: config-driven-backlog-backend-resolver-local

## Stage 1: Spec Compliance

### Requirement 1: Backend resolver (config-authoritative, fail-toward-default)
- **Expected**: `resolve_backlog_backend(repo_root) -> str` in `cortex_command/lifecycle_config.py`, reusing `_extract_frontmatter_text`, mirroring `read_branch_mode`, descending the nested `backlog:` mapping with an explicit `isinstance(backlog_block, dict)` guard, returning `"cortex-backlog"` for every degenerate case and the raw string for an explicit value; must not introspect plugins.
- **Actual**: `lifecycle_config.py:97-154` implements exactly this. It reuses `_extract_frontmatter_text`, mirrors the `read_branch_mode` file-read/YAML-parse/top-level `isinstance(parsed, dict)` guard, adds the net-new `isinstance(backlog_block, dict)` guard at `:143` before `.get("backend")`, and returns the `_BACKLOG_BACKEND_DEFAULT = "cortex-backlog"` module constant for missing-file, no-frontmatter, non-dict top-level, absent block, scalar block, and null/empty backend. No plugin introspection. `tests/test_lifecycle_config_backlog_backend.py` covers all degenerate cases plus a valid value (passing).
- **Verdict**: PASS
- **Notes**: Signature, docstring contract, and constants all match the spec/plan. Function never returns None.

### Requirement 2: Resolver CLI module + graceful binstub
- **Expected**: New `backlog_backend_cli.py` mirroring `branch_mode_cli.py` (argparse, `_telemetry.log_invocation`, stdout = value + newline, return 0); `pyproject.toml` entry; `chmod +x` binstub + cortex-core mirror. Failure contract is graceful (print `cortex-backlog`, exit 0), NOT the exit-2 shape.
- **Actual**: `cortex_command/lifecycle/backlog_backend_cli.py:55-62` calls `_telemetry.log_invocation("cortex-read-backlog-backend")`, resolves repo_root from positional/`CORTEX_COMMAND_ROOT`, writes `backend + "\n"`, returns 0. The entry point `cortex-read-backlog-backend = "cortex_command.lifecycle.backlog_backend_cli:main"` is present at `pyproject.toml:59`. The binstub `bin/cortex-read-backlog-backend` is executable, carries the log-invocation shim, and branch (d) prints `cortex-backlog` + `exit 0` (graceful, line 31-33), not the exit-2 remediation. The cortex-core mirror is byte-identical (verified). `tests/test_backlog_backend_cli.py` passes (stdout=resolved + newline for a fixture; `cortex-backlog`+exit 0 for unconfigured).
- **Verdict**: PASS
- **Notes**: Graceful console-script shape correctly chosen; the interactive fail-safe lives in the reader.

### Requirement 3: Config scaffold `backlog:` block
- **Expected**: Nested `backlog:` block in `lifecycle.config.md` template — `backend: cortex-backlog` default + commented `github-issues|jira|none` alternatives + optional `instructions:` with a documented `github-issues` example + a best-effort/#318 comment. A pytest reads the scaffold through `resolve_backlog_backend` and asserts `cortex-backlog`.
- **Actual**: Template `:21-28` adds the nested block with `backend: cortex-backlog`, commented `# backend: github-issues|jira|none` alternatives, a commented `instructions:` example using `gh` + cortex label + epics-as-milestones, and the "best-effort now and harden in #318" comment. `tests/test_init_backlog_scaffold.py` reads the scaffold through `resolve_backlog_backend` (passing), proving the block is nested at the descended path. `tests/test_init_artifacts_hash_inputs.py` passes.
- **Verdict**: PASS
- **Notes**: The documented external example (`backlog.md:35` mandate) is present.

### Requirement 4: ADR-0016
- **Expected**: `0016-configurable-backlog-backend-and-llm-as-adapter.md`, `status: proposed`, with context/decision/rejected-alternatives (per-tool adapters; plugin-introspection)/consequences clearing the three-criteria gate; back-pointer from `backlog.md`.
- **Actual**: The ADR exists with `status: proposed`, all four sections, both rejected alternatives (per-tool O(N) adapters; plugin-install introspection), and an explicit three-criteria-gate statement (hard-to-reverse / surprising / real-trade-off). The back-pointer is at `backlog.md:106` linking ADR-0016 by number without rationale duplication.
- **Verdict**: PASS
- **Notes**: 0016 confirmed as the next free number; content substantively matches the spec's Proposed ADR.

### Requirement 5: Overnight refusal guard (structural, in-process, fail-closed)
- **Expected**: Shared helper at the top of `handle_prepare`/`handle_launch`, before `select_overnight_batch` and `bootstrap_session`, resolving in-process via `resolve_backlog_backend(repo_path)` into `backlog_backend`, refusing unless exactly `cortex-backlog` with a versioned JSON error envelope (`backend_not_supported`) + non-zero exit. Guard stays at the handler layer.
- **Actual**: `_refuse_unsupported_backlog_backend` (`cli_handler.py:1949-1989`) resolves in-process via `resolve_backlog_backend(repo_path)` into a variable named `backlog_backend` (`:1977`, avoiding the scheduler `backend`), returns `None` when `== "cortex-backlog"`, else emits `{"error": "backend_not_supported", "message": ...}` (message names the configured backend) via `_emit_json` and returns 1. It is invoked after `repo_path` and before selection in `handle_prepare` (`:2051`, selection at `:2062`) and `handle_launch` (`:2131`, selection at `:2143`, bootstrap at `:2203`). `_emit_json` auto-stamps `schema_version` (`:130-133`) — no misleading hand-added `version` key. `tests/test_overnight_backlog_backend_guard.py` configures genuine non-local blocks and asserts the refusal on both handlers (passing).
- **Verdict**: PASS
- **Notes**: Resolution is genuinely in-process (`from cortex_command.lifecycle_config import resolve_backlog_backend`), NOT via the fail-open binstub — the exact R11 hazard the spec calls out is avoided.

### Requirement 6: Guard short-circuits before any selection or write (positive assertion)
- **Expected**: pytest positively asserts that on a non-local backend `select_overnight_batch` and `bootstrap_session` (both patched to raise) are never reached.
- **Actual**: `tests/test_overnight_backlog_backend_guard.py` patches BOTH `select_overnight_batch` and `bootstrap_session` to raise `AssertionError` if reached, then asserts the `backend_not_supported` refusal on both handlers across `github-issues`/`jira`/`none`. The absent-block proceed path is proven by a distinct `selection_failed` marker (the guard returned None and selection was reached). Tests pass.
- **Verdict**: PASS
- **Notes**: This is the load-bearing fail-closed regression catch; a future fail-open DRY-merge flips it red.

### Requirement 7: Interactive consumer backend routing (inline, local-default)
- **Expected**: Each backlog-touching consumer (lifecycle write-back, discovery decompose + SKILL, refine, dev, morning-review) carries a short inline guard — resolve once via `cortex-read-backlog-backend`; `cortex-backlog` default first arm proceeds as today; `none` skips with an advisory; any other value is external best-effort. No fail-safe/fallback prose; no new MUST.
- **Actual**: Verbatim extraction confirms each consumer carries the inline guard with `cortex-backlog` as the **default first arm**, a `none` arm, and an external best-effort arm keyed on `backlog.instructions`: backlog-writeback.md (`:7-15`, three write-backs), refine SKILL.md (`:63-90`), discovery decompose.md (`:138-142`), discovery SKILL.md promote-sub-topic (`:93`), dev SKILL.md (`:135-142`), morning-review walkthrough.md (`:535-545`). Each consumer references the reader (`grep` ≥ 1). No MUST/REQUIRED/CRITICAL in any new guard prose (prescriptive-prose lint rc=0). `tests/test_l1_surface_ratchet.py` passes (frontmatter unaffected).
- **Verdict**: PASS
- **Notes**: The local default arm requires no additional reference load — off-hot-path cost preserved.

### Requirement 8: Criticality-feed decoupling (Design A, local byte-identical)
- **Expected**: Local path byte-identical (refine seed/reconcile unchanged under `cortex-backlog`); only the non-local branch omits `--backlog-slug` and passes Clarify's explicit `--complexity/--criticality`; the `cortex-update-item --complexity/--criticality` write-backs gated on `backend == cortex-backlog`. No Python change to `refine.py`/`common.py`/`state_cli.py`.
- **Actual**: refine SKILL.md routes the seed (`emit-lifecycle-start`) and reconcile on the resolved backend; the non-local arm invokes `reconcile-clarify --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value}` (omits `--backlog-slug`, uses computed `{value}` placeholders), while the local Context-A arm keeps `--backlog-slug {backlog-filename-slug}` unchanged. The clarify §7 (`clarify.md:100-114`) and refine write-backs are backend-gated (skip on `none`, external best-effort otherwise). `tests/test_refine_reconcile_clarify.py` includes the R8 functional regression (non-local explicit flags ratchet events.log to `complex` via `cortex-lifecycle-state --field tier`) and a value-aware structural test (asserts the non-local branch omits `--backlog-slug` and uses `{value}` placeholders, NOT `simple`/`medium` literals). No diff to `refine.py`/`common.py`/`state_cli.py` in the #317 commit range. Tests pass.
- **Verdict**: PASS
- **Notes**: The seed→reconcile→gate invariant is documented explicitly in refine SKILL.md; the resume-to-spec gap it leaves is closed by R11/Task 11.

### Requirement 9: Structural-consumer degrade (ordering-assertable)
- **Expected**: Under non-local, dev's epic-map/triage skips with an advisory routing to lifecycle/discovery; the backend read gates the call so the structural local-index read is not reached (the R5 ordering shape).
- **Actual**: dev SKILL.md (`:135-142`) places the backend read in a "Backend gate (resolve before any index read)" section BEFORE `cortex-generate-backlog-index` (`:146`), the `index.{md,json}` reads (`:150`,`:156`), and `cortex-build-epic-map` (`:164`). The non-local arm explicitly says "Do not run `cortex-generate-backlog-index`, read `cortex/backlog/index.{md,json}`, or call `cortex-build-epic-map`," with an advisory routing to `/cortex-core:lifecycle`/`/cortex-core:discovery`. The gate precedes the structural read (ordering verified, not string-presence alone).
- **Verdict**: PASS
- **Notes**: refine's parent-epic alignment guard is the same shape; dev is the CLI-seam case the spec names.

### Requirement 10: `none`-backend discovery surfaces composed bodies
- **Expected**: Under `backend: none`, discovery surfaces composed ticket bodies inline (in `decomposed.md`/its research artifact) rather than failing.
- **Actual**: decompose.md (`:141`) `none` arm: "do not call the create CLI. Instead, surface the composed epic and child ticket bodies inline … write each full title + body into `cortex/research/{topic}/decomposed.md` … No writes land in `cortex/backlog/`." discovery SKILL.md promote-sub-topic (`:93`) mirrors this (surface composed title+body inline on `none`). Reachable `none` branch confirmed by grep.
- **Verdict**: PASS
- **Notes**: Unique inline-surface pattern correctly distinguishes discovery from the skip-and-advisory consumers.

### Requirement 11: Two readers, opposite fail directions — kept distinct (anti-DRY)
- **Expected**: The interactive fail-safe (graceful binstub/resolver default) and the overnight fail-closed (in-process strict check) remain two distinct code points; a comment/Technical-Constraint documents the asymmetry; R5/R6 tests assert the overnight refuse-direction.
- **Actual**: The graceful reader (`backlog_backend_cli.py` + binstub branch (d)) and the strict guard (`_refuse_unsupported_backlog_backend`) are physically distinct. The guard docstring (`cli_handler.py:1961-1973`) documents the fail-direction asymmetry explicitly ("this overnight guard fails closed … the OPPOSITE of the interactive reader … must NOT be DRY-merged"). The guard reads config in-process and never shells the binstub. The §3b non-local fail-safe (Task 11) is wired at the specify §3b inline decision BEFORE the skip handoff — `tests/test_critical_review_gate_nonlocal_failsafe.py` asserts both the documented rule (gate ref) and the wiring order (backend read precedes the gate-protocol skip handoff via index comparison). Tests pass.
- **Verdict**: PASS
- **Notes**: The structural regression catch is the test, not the comment — matching CLAUDE.md's structural-over-prose preference.

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. The resolver mirrors `read_branch_mode`/`read_commit_artifacts`; module constants (`_BACKLOG_BLOCK_FIELD`, `_BACKLOG_BACKEND_FIELD`, `_BACKLOG_BACKEND_DEFAULT`) follow the existing underscore-prefixed convention. The CLI module mirrors `branch_mode_cli.py`. The guard variable is named `backlog_backend` as mandated (avoids the scheduler `backend` collision). Terminology stays `cortex-backlog` (not `local`) throughout config, prose, and tests.
- **Error handling**: Appropriate and deliberately bidirectional. The resolver/reader fail open (return the default) on every degenerate input; the overnight guard fails closed (refuse + non-zero exit). The refusal uses the `selection_failed`-shaped JSON envelope with `_emit_json`'s auto-stamped `schema_version` — correctly avoiding a misleading hand-added `version` key. The malformed-YAML branch warns to stderr and returns the default, matching the sibling readers.
- **Test coverage**: Strong. Six new test files cover the resolver (8 degenerate + valid cases), the CLI graceful shape, the scaffold-through-resolver round-trip, the overnight guard (refusal on both handlers × 3 backends + R6 positive short-circuit + absent-block proceed), the R8 functional+structural decoupling, and the §3b fail-safe (documented rule + wiring order). All 53 feature-related tests pass. Prose routing in pure-prose consumers is verified structurally (the documented verification-strength caveat — runtime model substitution is interactive — is honestly stated in the plan).
- **Pattern consistency**: Follows existing conventions throughout — the lifecycle_config reader family, the branch_mode CLI/binstub pattern, the `_emit_json` envelope pattern, the dual-source mirror discipline (all 10 canonical/mirror pairs verified byte-identical; morning-review correctly mirrors to `plugins/cortex-overnight/`, the rest to `plugins/cortex-core/`), and soft positive-routing prose (no new MUST/REQUIRED). One pre-existing, non-#317 observation (below) on the binstub family.

### Non-blocking observations (not defects in #317)
- The `bin/cortex-read-backlog-backend` binstub trips the whole-repo `cortex-check-parity --audit` gate for four bare `python3 -m cortex_command.*` callsites not in `bin/.audit-bare-python-m-allowlist.md`. This is a **pre-existing family condition**: the sibling `bin/cortex-read-commit-artifacts` (the pattern the spec explicitly names as the model) trips the identical audit at the same line numbers and is likewise not allowlisted. The pre-commit `--staged` gate (which blocks commits) passed at commit time per the plan; `--audit` is a separate `just`-recipe time/repo-wide gate. The new binstub faithfully mirrors the established sibling; this is latent shared audit-debt across the read-binstub family, not a #317-introduced regression. Optional future cleanup: add the read-binstub family to the allowlist with a `wrapper-script-r14-pending` rationale, or close the underlying R14 cleanup.

## Requirements Drift
**State**: none
**Findings**:
- None. The implementation matches `cortex/requirements/backlog.md` and `cortex/requirements/project.md` faithfully. backlog.md was updated in-feature (it is the authoritative area spec this ticket implements): the `cortex-backlog`-terminology constraint, config-authoritative resolution, skill-layer routing, overnight-requires-`cortex-backlog`, `none`-backend behavior, and the ADR-0016 back-pointer all land exactly as the area doc prescribes. The ADR-0016 reference at `backlog.md:106` resolves to the created file. No behavior is introduced that the requirements docs do not already reflect.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
