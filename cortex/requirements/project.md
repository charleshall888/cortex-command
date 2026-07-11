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

**Multi-step lifecycle phases**: A lifecycle phase may be multi-step with a user-driven re-invocation point. The Complete phase is the canonical example — it creates a PR, exits with a handoff message, and finalizes only on re-invocation after the PR is merged on GitHub. Merge (not PR-open) is the terminal event for "Done", recorded in the `feature_complete` event with `merge_anchor: "merge"`. → ADR-0004: multi-step Complete + interactive-worktree lifecycle.

**Kept user pauses are a marked taxonomy** of the deliberate, in-scope user-facing pauses across the lifecycle and refine skills. Each pause carries a `kind` — `question` (a phase blocks for an interactive answer), `phase-exit-wait` (a phase exits cleanly and waits for the user to re-invoke after an out-of-band action, e.g. merging a PR on GitHub), `config-conditional` (a pause a config key can suppress), or `relayed-consent` (a substantive approval surface whose consent overnight relays pre-authorized) — plus an orthogonal optional `suppressed_by` (a `lifecycle.config.md` key, or `judgment` for model-conditional rendering). The durable source of truth is `skills/lifecycle/references/kept-pauses-data.toml` (one row per `<!-- pause: <slug> <kind> -->` marker in skill prose); `cortex-generate-kept-pauses` renders the human-readable `skills/lifecycle/references/kept-pauses.md` from it, and `tests/test_lifecycle_kept_pauses_parity.py` is the enforcement pair — asserting marker/data set-equality, inventory freshness, and per-kind semantic anchors.

## Architectural Constraints

- **File-based state**: → ADR-0001: File-based state, no database
- **Per-repo sandbox registration**: → ADR-0003: Per-repo sandbox registration
- **SKILL.md-to-bin parity enforcement**: `bin/cortex-*` scripts wire through an in-scope SKILL.md/requirements/docs/hooks/justfile/tests reference. `bin/cortex-check-parity` blocks drift; exceptions at `bin/.parity-exceptions.md`.
- **SKILL.md size cap**: 500 lines (`tests/test_skill_size_budget.py`). Exceptions via in-file `<!-- size-budget-exception: ... -->`. Default fix: extract to `skills/<name>/references/`.
- **Skill-helper modules**: when a SKILL.md dispatch ceremony invites paraphrase, collapse it into atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry. Promoted modules expose a `[project.scripts]` console-script entry (e.g. `cortex-<skill>`) as the recommended invocation idiom; `python3 -m cortex_command.<skill> <subcommand>` is retained as a readable fallback for ad-hoc invocation. New events register in `bin/.events-registry.md`.
- **Backlog status vocabulary**: Canonical terminal statuses are maintained in `cortex_command/common.py:TERMINAL_STATUSES` (frozenset) and mirrored in `cortex_command/overnight/plan.py:_TERMINAL`. Extensions to terminal status vocabulary (e.g. adding `superseded`) must update both locations and add a corresponding `normalize_status` map entry. The frozenset in `cortex_command/overnight/backlog.py` is a known divergence tracked for a separate follow-up.
- **Historical compatibility shim pattern**: When a pipeline module is deleted, read-side filters that detect its schema in archived event logs (e.g. `_DAYTIME_DISPATCH_FIELDS` in `pipeline/metrics.py`) are retained as historical-compat shims, not deleted, so archived `pipeline-events.log` data still parses.
- **Wheel-binstub vs working-tree invocation**: `cortex-<skill>` binstubs execute against the installed wheel's `site-packages/`, not the working tree; `python3 -m cortex_command.<skill>` runs against the working tree. So when a phase edits `common.py` and a later step invokes a binstub that reads it at runtime, either reinstall the wheel first or invoke via `python3 -m`. Setting `CORTEX_COMMAND_FORCE_SOURCE=1` makes the `bin/cortex-*` wrappers skip the wheel-import branch and run the working-tree module directly, regardless of whether a wheel is installed.
- **CLI/plugin version contract**: → ADR-0002: CLI wheel + plugin distribution
- **Architectural Decision Records**: `cortex/adr/` holds load-bearing decisions per `cortex/adr/README.md` (three-criteria gate, prose-only enforcement, MUST/MUST NOT/SHOULD consumer rules). Skills back-point to ADRs rather than restating rationale.
- **Consumer `EnterWorktree` authorization surface**: `cortex init` writes **no** clause to consumer `CLAUDE.md`; the lifecycle implement phase authorizes `EnterWorktree` via the user's live picker selection at implement time. → ADR-0008: picker-selection authorizes `EnterWorktree` (supersedes ADR-0006).
- **Install-state shared-constant contract**: the install-in-progress marker path (`XDG_STATE_HOME`-aware, 600s stale threshold) is defined by the stdlib-only `cortex_command/init/install_state.py` and duplicated inline in `plugins/cortex-overnight/install_core.py` because the SessionStart hook invokes it via bare system `python3` where the wheel is not importable. Parity is enforced by `tests/test_install_state_path_parity.py`; the wheel never imports from `plugins/cortex-overnight/`.
- **`CORTEX_AUTO_ENSURE=0` opt-out**: mirrors the `CORTEX_AUTO_INSTALL=0` shape from the overnight plugin. Silences `cortex init --ensure` (and `cortex-lifecycle-init-ensure`) without disabling manual init verbs. Foreign-content protection for unanticipated misfires is structural (R19 gate) rather than reliant on this opt-out.
- **Backlog `grep -c` resolution**: Backlog tickets that include `grep -c "<token>"` as Done-When/acceptance checks must reference tokens in `bin/.events-registry.md` or literal strings under `cortex_command/`, so acceptance criteria can't pass trivially against hallucinated event names. Enforced by `tests/test_backlog_grep_targets_resolve.py`.
- **Bare-Python skill-invocation prohibition (L201)**: skill files (`skills/**/*.md`) and related corpus must not carry bare-Python `cortex_command` imports (static or dynamic); use `cortex-<skill>` console-script invocations instead. Caught at pre-commit by `cortex-check-bare-python-import`; suppress an intentional illustrative form with `<!-- bare-python-lint:ignore-next -->`.
- **Skill-dir path-resolution invariant (SP001/SP002)**: enforced at pre-commit by `cortex-check-skill-path` (D1: raw `${CLAUDE_SKILL_DIR}` / bare `*.md` consult-ref inside a subagent prompt; D2: bare-relative Read/execute path not carried by a `${CLAUDE_SKILL_DIR}/` prefix); rationale in ADR-0009 and the CLAUDE.md skill-authoring design principle. Suppress an intentional illustrative form with `<!-- skill-path-lint:ignore-next -->`.
- **Distributed-CLI dependency bounds**: `uv tool install` from a git ref ignores `uv.lock`, so the `pyproject.toml` `[project.dependencies]` bounds that travel in the wheel's `requires-dist` are the only governance reaching every install path. Cap the drift-prone web stack at the next breaking major, and promote a transitive to a direct, capped dependency when an uncapped upstream parent would otherwise let it drift across a breaking boundary (bounds in `pyproject.toml`). The fresh-resolve route test (`cortex_command/dashboard/tests/test_routes_smoke.py`, run in `validate.yml`) is the structural anti-revert guard.
- **SKILL.md L1 surface ratchet**: each skill's L1 frontmatter surface (`description` + `when_to_use` byte sum) is bounded by a deliberate per-skill budget in `tests/test_l1_surface_ratchet.py`; equal-or-lower passes, and a new skill without a budget row fails a completeness gate. The one exemption surface is the routing-pressure cluster, whose skills carry irreducible disambiguation and path-routing tokens and get their own (higher) budget rows rather than the non-cluster default. Raising any budget row — including a cluster re-cap that cannot meet a target without dropping a trigger phrase — requires a documented rationale plus a lifecycle-id, so a legitimate re-cap is distinguishable from silent drift. New-skill authoring pointer: `CLAUDE.md`. → lifecycle 298.
- **Out-of-process runner supervision**: a persistent host-level launchd guardian plus a manual `cortex overnight recover` verb are the only session-state writers outside the runner itself (observability surfaces stay read-only). → ADR-0011: out-of-process overnight-runner supervision.
- **Worktree containment invariant**: `create_worktree` (`cortex_command/pipeline/worktree.py`) enforces that a same-repo worktree resolves inside the repo root; an out-of-repo `CORTEX_WORKTREE_ROOT` override raises a containment-specific `worktree_escapes_repo` ValueError → CLI exit 1, leaving nothing on disk. The cross-repo / `$TMPDIR` overnight branch (`repo_path` set) is legitimately outside the repo and is exempt; the same-repo overnight path (`repo_path=None`, `session_id` set) is NOT exempt and is governed by the guard. Contract is pinned by the `test_containment_*` block in `tests/test_worktree.py`.

## Quality Attributes

- **Graceful partial failure**: Tasks may fail. The system retries, optionally hands off to a fresh agent, fails gracefully — completing the rest.
- **Maintainability through simplicity**: Complexity is managed by iteratively trimming skills/workflows.
- **Iterative improvement**: Architecture tolerates exploratory development; design emerges through use.
- **Defense-in-depth for permissions**: `settings.json` ships minimal allow, comprehensive deny, sandbox on. For sandbox-excluded commands (git, gh, WebFetch) the allow/deny list is sole enforcement — keep global allows read-only. Overnight runs `--dangerously-skip-permissions`; sandbox is the critical surface.
- **Defense-in-depth for captured subprocess output**: child stderr captured for diagnostics is scrubbed at source by a cue-anchored credential allowlist (`pipeline/dispatch.py:_redact`) before it reaches the brain prompt or the morning report committed to local `main`. The allowlist is defense-in-depth, NOT complete (prefixless secrets and uncued families may pass); it deliberately uses no prefixless fixed-length blob matcher so benign high-entropy diagnostics (SHAs, UUIDs, base64) survive. → #309.
- **Destructive operations preserve uncommitted state**: Cleanup scripts removing user-visible artifacts (worktrees, branches, sessions) SKIP on uncommitted state. Inline destructive sequences extract into named scripts.

## Project Boundaries

### In Scope

- AI workflow orchestration (skills, lifecycle, pipeline). Discovery is documented inline (no area doc): `skills/discovery/SKILL.md`. Backlog has its own area doc (`cortex/requirements/backlog.md`); `cortex/backlog/index.md` is the local-backend (`cortex-backlog`) store. Ticket body authoring is enforced via `skills/backlog-author/` (the shared sub-skill) and validated at pre-commit by `bin/cortex-check-prescriptive-prose` (LEX-1 scanner, covering `## Why`, `## Role`, `## Integration`, `## Edges`).
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
- backlog/ticketing/issue tracker/backlog backend → cortex/requirements/backlog.md

## Global Context

- cortex/requirements/glossary.md

## Optional

Content here is prunable under token pressure — skip without losing spec-required guidance.

- **Sandbox preflight gate**: `bin/cortex-check-parity` validates `cortex/lifecycle/{feature}/preflight.md` on sandbox-source diffs, failing on a missing or invalid preflight.
- **Two-mode gate pattern**: pre-commit gates pair `--staged` (diff schema) with `--audit` (time/repo-wide, `just <recipe>-audit`); the `--staged` scope must stay corpus-congruent with `--audit` (same files at all depths). See `bin/cortex-check-events-registry`.
- **Workflow trimming**: unearned workflows are removed wholesale. Retirements in `CHANGELOG.md`.
