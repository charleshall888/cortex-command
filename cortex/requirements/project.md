# Requirements: cortex-command

> Last gathered: 2026-04-01 (updated 2026-05-12)

## Overview

Agentic workflow toolkit for AI-assisted software development on Claude Code: skills, lifecycle state machine, pipeline orchestrator, overnight execution. North star: autonomous multi-hour development — Claude works from a plan, spins up teams, reports afterward. Ships CLI-first as a non-editable wheel plus Claude Code plugins (→ ADR-0002).

## Philosophy of Work

**Day/night split**: Daytime is iterative collaboration; overnight is handoff; morning is strategic review, not debugging.

**Handoff readiness**: A feature isn't overnight-ready until the spec has no open questions, criteria are agent-verifiable from zero context, artifacts self-contained.

**Failure handling**: Surface failures in the morning report; keep working unless blocked.

**Daytime work**: Research before asking; don't fill unknowns with assumptions.

**Complexity**: Must earn its place by solving a real problem now. When in doubt, simpler wins.

**Solution horizon**: Long-term project — fixes reflect that. Before suggesting a fix, ask: do I already know this needs redoing (follow-up planned, patch applies in multiple known places, sidesteps a known constraint)? If yes, propose the durable version or surface both with tradeoff. If no, **Complexity** applies. A scoped phase of a multi-phase lifecycle is not a stop-gap (stop-gap means unplanned-redo). Test: current knowledge, not prediction.

**Quality bar**: Tests pass; the feature works as specced. ROI matters — ship faster, not be a project.

**Multi-step lifecycle phases**: A lifecycle phase may be multi-step with a user-driven re-invocation point. The Complete phase is the canonical example — it creates a PR, exits with a handoff message, and finalizes only on re-invocation after the PR is merged on GitHub. Merge (not PR-open) is the terminal event for "Done"; this aligns with GitHub/Linear/Jira/GitLab conventions and is recorded in the `feature_complete` event with `merge_anchor: "merge"`. Re-invocation routing is state-aware and idempotent; the finalization tail (Steps 9–11a) commits lifecycle artifacts and the backlog write-back via a flag-gated, stage-first step on all completion paths (trunk, worktree-interactive post-merge, feature-branch post-merge); consult `cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` for the design rationale.

**Kept user pauses come in two kinds**: (a) `AskUserQuestion`-site pauses where a phase blocks for an interactive answer; (b) phase-exit pauses where a phase exits cleanly and waits for the user to re-invoke after performing an out-of-band action (e.g., merging a PR on GitHub). The `skills/lifecycle/SKILL.md` kept-pauses inventory and `tests/test_lifecycle_kept_pauses_parity.py` enforce both kinds.

## Architectural Constraints

- **File-based state**: → ADR-0001: File-based state, no database
- **Per-repo sandbox registration**: → ADR-0003: Per-repo sandbox registration
- **SKILL.md-to-bin parity enforcement**: `bin/cortex-*` scripts wire through an in-scope SKILL.md/requirements/docs/hooks/justfile/tests reference. `bin/cortex-check-parity` blocks drift; exceptions at `bin/.parity-exceptions.md`.
- **SKILL.md size cap**: 500 lines (`tests/test_skill_size_budget.py`). Exceptions via in-file `<!-- size-budget-exception: ... -->`. Default fix: extract to `skills/<name>/references/`.
- **Skill-helper modules**: when a SKILL.md dispatch ceremony invites paraphrase, collapse it into atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry. Promoted modules expose a `[project.scripts]` console-script entry (e.g. `cortex-<skill>`) as the recommended invocation idiom; `python3 -m cortex_command.<skill> <subcommand>` is retained as a readable fallback for ad-hoc invocation. New events register in `bin/.events-registry.md`.
- **Backlog status vocabulary**: Canonical terminal statuses are maintained in `cortex_command/common.py:TERMINAL_STATUSES` (frozenset) and mirrored in `cortex_command/overnight/plan.py:_TERMINAL`. Extensions to terminal status vocabulary (e.g. adding `superseded`) must update both locations and add a corresponding `normalize_status` map entry. The frozenset in `cortex_command/overnight/backlog.py` is a known divergence tracked for a separate follow-up.
- **Historical compatibility shim pattern**: When a pipeline module is deleted, read-side filters that detect that module's schema in archived event logs (e.g. `_DAYTIME_DISPATCH_FIELDS` in `pipeline/metrics.py`) are retained as historical compat shims rather than deleted. Shim docstrings are retitled to "Historical compatibility — skip pre-#NNN <schema-name> rows in archived event logs." This preserves correct behavior for operators replaying or aggregating historical `pipeline-events.log` data after the module is gone.
- **Wheel-binstub vs working-tree invocation**: `cortex-<skill>` binstubs execute against the installed wheel's `site-packages/`; `python3 -m cortex_command.<skill>` runs against the working tree. When a Phase N commit edits `common.py` and a subsequent Phase N+1 step must invoke a binstub that reads `common.py` at runtime, Phase N's working-tree changes must be complete before invoking the binstub — the binstub reads the installed wheel, not the working tree. Use `python3 -m` invocation to run against the working tree when wheel reinstall between phases is not feasible. Setting `CORTEX_COMMAND_FORCE_SOURCE=1` in the environment makes the dual-channel wrappers in `bin/cortex-*` skip the wheel-import branch and execute the working-tree module directly via `python3 -m cortex_command.<module>`, regardless of whether a wheel is installed. Dogfooders iterating on working-tree code without `--reinstall` between edits should export this variable.
- **CLI/plugin version contract**: → ADR-0002: CLI wheel + plugin distribution
- **Architectural Decision Records**: `cortex/adr/` holds load-bearing decisions per `cortex/adr/README.md` (three-criteria gate, prose-only enforcement, MUST/MUST NOT/SHOULD consumer rules). Skills back-point to ADRs rather than restating rationale.
- **Consumer `EnterWorktree` authorization surface**: `cortex init` writes **no** clause to consumer `CLAUDE.md`. The lifecycle implement phase authorizes `EnterWorktree` via the user's live selection of the `worktree`-labeled picker option; the suppressed-picker (`branch-mode: worktree-interactive`) path routes structurally to the cd-shim with no persisted authorization. → ADR-0008: picker-selection authorizes `EnterWorktree` (supersedes ADR-0006).
- **Install-state shared-constant contract**: `cortex_command/init/install_state.py` is a stdlib-only module that defines the install-in-progress marker path (`XDG_STATE_HOME`-aware, 600s stale threshold) for the wheel-side `cortex init --ensure` consumer. `plugins/cortex-overnight/install_core.py` duplicates the same logic inline (vendor-style) because the SessionStart hook `hooks/cortex-cli-background-install.sh` invokes it via bare system `python3` with only `CLAUDE_PLUGIN_ROOT` on `sys.path` — the wheel's `cortex_command` package is not importable from that surface. Parity between the two implementations is enforced by `tests/test_install_state_path_parity.py`. The wheel never imports from `plugins/cortex-overnight/`.
- **`CORTEX_AUTO_ENSURE=0` opt-out**: mirrors the `CORTEX_AUTO_INSTALL=0` shape from the overnight plugin. Silences `cortex init --ensure` (and `cortex-lifecycle-init-ensure`) without disabling manual init verbs. Foreign-content protection for unanticipated misfires is structural (R19 gate) rather than reliant on this opt-out.
- **Backlog `grep -c` resolution**: Backlog tickets that include `grep -c "<token>"` as Done-When/acceptance checks must reference tokens that appear in `bin/.events-registry.md` or as literal strings under `cortex_command/`. Enforced by `tests/test_backlog_grep_targets_resolve.py`. Companion to the events-registry gate; prevents acceptance criteria from passing trivially against hallucinated event names.
- **Bare-Python skill-invocation prohibition (L201)**: Skill files (`skills/**/*.md`) and related corpus files must not contain bare-Python `cortex_command` imports (static `import`/`from import` or dynamic `importlib.util.find_spec`/`importlib.import_module`/`__import__` forms). Violations are structurally caught at pre-commit by `cortex-check-bare-python-import` (Phase 1.86, L201). Use `cortex-<skill>` console-script invocations instead. Where a bare-Python form is intentional (e.g., illustrative `## Touch points` prose), precede the python-source region with `<!-- bare-python-lint:ignore-next -->`.

## Quality Attributes

- **Graceful partial failure**: Tasks may fail. The system retries, optionally hands off to a fresh agent, fails gracefully — completing the rest.
- **Maintainability through simplicity**: Complexity is managed by iteratively trimming skills/workflows.
- **Iterative improvement**: Architecture tolerates exploratory development; design emerges through use.
- **Defense-in-depth for permissions**: `settings.json` ships minimal allow, comprehensive deny, sandbox on. For sandbox-excluded commands (git, gh, WebFetch) the allow/deny list is sole enforcement — keep global allows read-only. Overnight runs `--dangerously-skip-permissions`; sandbox is the critical surface.
- **Destructive operations preserve uncommitted state**: Cleanup scripts removing user-visible artifacts (worktrees, branches, sessions) SKIP on uncommitted state. Inline destructive sequences extract into named scripts.

## Project Boundaries

### In Scope

- AI workflow orchestration (skills, lifecycle, pipeline). Discovery and backlog are documented inline (no area docs): `skills/discovery/SKILL.md`, `cortex/backlog/index.md`. Ticket body authoring is enforced via `skills/backlog-author/` (the shared sub-skill) and validated at pre-commit by `bin/cortex-check-prescriptive-prose` (LEX-1 scanner, covering `## Why`, `## Role`, `## Integration`, `## Edges`).
- Overnight execution: framework, sessions, scheduled launch, morning report
- Dashboard (~1800 LOC FastAPI), conflict resolution pipeline (~2500 LOC), remote access (Tailscale/mosh/tmux/Cloudflare Tunnel)
- Observability (statusline, notifications, metrics, cost); global agent config
- Multi-agent: parallel dispatch, worktrees, Haiku/Sonnet/Opus selection

### Out of Scope

- Dotfiles, machine configuration, setup automation for new machines — belong in machine-config
- Application code or libraries — belong in their own repos
- Published packages or reusable modules for others — out of scope; cortex ships as a non-editable wheel

### Deferred

- Migration from file-based state if complexity demands it
- Cross-repo work in one overnight session

## Conditional Loading

- statusline/dashboard/notifications → cortex/requirements/observability.md
- pipeline/overnight runner/conflict resolution/deferral → cortex/requirements/pipeline.md
- remote access/tmux/mosh/Tailscale → cortex/requirements/remote-access.md
- agent spawning/parallel dispatch/worktrees/model selection → cortex/requirements/multi-agent.md

## Global Context

- glossary.md

## Optional

Content here is prunable under token pressure — skip without losing spec-required guidance.

- **Sandbox preflight gate**: `bin/cortex-check-parity` validates `cortex/lifecycle/{feature}/preflight.md` on sandbox-source diffs; fails on missing/invalid preflight or `claude --version` drift.
- **Two-mode gate pattern**: pre-commit gates pair `--staged` (diff schema) with `--audit` (time/repo-wide, `just <recipe>-audit`). See `bin/cortex-check-events-registry`; the `--staged` mode membership must be corpus-congruent with `--audit` (same files in scope at all depths) — enforced by `_in_scan_scope` in `cortex_command/lint/contract.py` using a recursive-glob matcher safe on Python 3.12+.
- **Workflow trimming**: unearned workflows are removed wholesale. Retirements in `CHANGELOG.md`.
