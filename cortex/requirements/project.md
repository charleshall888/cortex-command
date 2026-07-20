# Requirements: cortex-command

> Last gathered: 2026-07-16

## Overview

Agentic workflow toolkit for AI-assisted software development on Claude Code: skills, lifecycle state machine, pipeline orchestrator, overnight execution. North star: autonomous multi-hour development — Claude works from a plan, spins up teams, reports afterward. Ships CLI-first as a non-editable wheel plus Claude Code plugins (→ ADR-0002). Token economy is a first-class quality bar: measured runtime cost is turns × context (`cache_read ∝ requests^1.68`; cache hit rate already ~98%), so the harness optimizes for short sessions, few turns, and narrow fan-out — not resident-prose micro-trims.

## Philosophy of Work

**Day/night split**: Daytime is iterative collaboration; overnight is handoff; morning is strategic review, not debugging.

**Handoff readiness**: A feature isn't overnight-ready until the spec has no open questions, criteria are agent-verifiable from zero context, artifacts self-contained.

**Failure handling**: Surface failures in the morning report; keep working unless blocked.

**Daytime work**: Research before asking; don't fill unknowns with assumptions.

**Complexity**: Must earn its place by solving a real problem now. When in doubt, simpler wins.

**Token economy (autonomy-lean)**: Runtime cost is turns × context — `cache_read ∝ requests^1.68` (orchestrator, r=0.98, n=126) and `∝ turns^1.55` (subagents); caching is already ~98% effective, so the levers are session length, turn count, and fan-out width. Keep the minimal machinery that makes overnight autonomy and disposable sessions possible (state machine, events.log, fan-out dispatch); anything that exists to police or observe the harness itself is presumed deletable unless it names specific evidence.

**Deletion bias**: Keeps, safeguards, and measurement tooling must clear the same evidence bar as new features — named, specific evidence, not hypotheticals; when a trim is proposed, the burden of proof sits on keeping, not deleting. Verify with existing tools (grep/read/one-off script) before building measurement tooling; the standing token-measurement tool is the ad-hoc prototype (`cortex/research/token-economics-2026-07-16/analyze.py`, dedup by `message.id`), and re-measurement follows shipped cuts rather than gating them.

**Solution horizon**: Long-term project — fixes reflect that. Before suggesting a fix, ask: do I already know this needs redoing (follow-up planned, patch applies in multiple known places, sidesteps a known constraint)? If yes, propose the durable version or surface both with tradeoff. If no, **Complexity** applies. A scoped phase of a multi-phase lifecycle is not a stop-gap (stop-gap means unplanned-redo). Test: current knowledge, not prediction. The same test applies symmetrically to keeps and safeguards — a defense retained without named evidence is complexity too (**Deletion bias**).

**Quality bar**: Tests pass; the feature works as specced. ROI matters — ship faster, not be a project.

**Multi-step lifecycle phases**: A lifecycle phase may be multi-step with a user-driven re-invocation point. The Complete phase is the canonical example — it creates a PR, exits with a handoff message, and finalizes only on re-invocation after the PR is merged on GitHub. Merge (not PR-open) is the terminal event for "Done", recorded in the `feature_complete` event with `merge_anchor: "merge"`. → ADR-0004: multi-step Complete + interactive-worktree lifecycle.

**Kept user pauses are a marked taxonomy** of the deliberate, in-scope user-facing pauses across the lifecycle and refine skills. Each pause carries a `kind` — `question` (a phase blocks for an interactive answer), `phase-exit-wait` (a phase exits cleanly and waits for the user to re-invoke after an out-of-band action, e.g. merging a PR on GitHub), `config-conditional` (a pause a config key can suppress), or `relayed-consent` (a substantive approval surface whose consent overnight relays pre-authorized) — plus an orthogonal optional `suppressed_by` (a `lifecycle.config.md` key, or `judgment` for model-conditional rendering). The durable source of truth is `skills/lifecycle/references/kept-pauses-data.toml` (one row per `<!-- pause: <slug> <kind> -->` marker in skill prose); `cortex-generate-kept-pauses` renders the human-readable `skills/lifecycle/references/kept-pauses.md` from it, and `tests/test_lifecycle_kept_pauses_parity.py` is the enforcement pair — asserting marker/data set-equality, inventory freshness, and per-kind semantic anchors. Under the 374 served loop the taxonomy also gains a **runtime consumer**: the `next` verb serves each state's pause spec in its envelope and the interactive loop renders it via AskUserQuestion, so the taxonomy is read at runtime — not only by the parity test. → ADR-0024.

## Architectural Constraints

- **File-based state**: → ADR-0001: File-based state, no database
- **Per-repo sandbox registration**: → ADR-0003: Per-repo sandbox registration
- **Phase boundaries are session boundaries**: the default workflow splits sessions at lifecycle phase boundaries — a fresh session after refine (spec approval) runs plan+implement, and a plan that consumed heavy context hands implement to another fresh session; phase-keyed `resume` routing is the re-entry path. Rationale: session carry is superlinear in turns (measured 37–61% of orchestrator spend); a fresh session re-caches for ~50k tokens (~0.7% of one long session's cache-read).
- **Critical-review gates at spec only**: the adversarial review gate runs on the spec; the plan phase carries no critical-review gate (the end-of-implementation review is the backstop). Default width is 2 reviewers routed to Sonnet with an Opus synthesizer; escalate to 3–4 reviewers when criticality is high/critical or the artifact introduces claims the spec lacked. Supersedes #383.
- **Dispatched agents are bounded**: every dispatched agent carries a turn cap (~40; on hit it returns what it has), and dispatch handling includes a returned-nothing branch routing hung agents to the existing Partial-coverage path. Rationale: 2.9% of agents exceed 60 turns and consume 19% of fan-out spend (`∝ turns^1.55`).
- **The short road**: one predicate governs every phase fork — `criticality ∈ {high, critical} OR tier == complex` takes the long road, everything else takes the short one. Applied at spec exit (`spec.approved-direct`: specify→implement, no Plan phase, implement works from spec acceptance criteria) and at implement exit (implement→complete, no Review phase — the pre-existing rule this generalizes). Corrupted reductions always take the long road. Research width follows tier the same direction (fanout.md: simple = Codebase-mandatory only). The complexity escalator is the safety valve: doubt classifies down at Clarify, evidence ratchets up.
- **Enforcement gates carry named evidence**: a pre-commit/CI gate survives only by naming the specific, evidenced failure it prevents (commit-message validation, worktree containment, sandbox preflight, shipped-bug regressions). Prose-scanners, parity/citation audits, and similar self-policing lints retire; per-gate disposition lands via a lifecycle. Reference prose follows verb-first with a stated size direction: behavior moves into CLI verbs, prose keeps only control flow, targeting ~10x reduction of `skills/*/references/`.
- **SKILL.md size cap**: 500 lines (`tests/test_skill_size_budget.py`). Exceptions via in-file `<!-- size-budget-exception: ... -->`. Default fix: extract to `skills/<name>/references/`.
- **Skill-helper modules**: when a SKILL.md dispatch ceremony invites paraphrase, collapse it into atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry. Promoted modules expose a `[project.scripts]` console-script entry (e.g. `cortex-<skill>`) as the recommended invocation idiom; `python3 -m cortex_command.<skill> <subcommand>` is retained as a readable fallback for ad-hoc invocation. New events register in `bin/.events-registry.md`.
- **Backlog status vocabulary**: Canonical terminal statuses are maintained in `cortex_command/common.py:TERMINAL_STATUSES` (frozenset) and mirrored in `cortex_command/overnight/plan.py:_TERMINAL`. Extensions to terminal status vocabulary (e.g. adding `superseded`) must update both locations and add a corresponding `normalize_status` map entry. The frozenset in `cortex_command/overnight/backlog.py` is a known divergence tracked for a separate follow-up.
- **Historical compatibility shim pattern**: When a pipeline module is deleted, read-side filters that detect its schema in archived event logs (e.g. `_DAYTIME_DISPATCH_FIELDS` in `pipeline/metrics.py`) are retained as historical-compat shims, not deleted, so archived `pipeline-events.log` data still parses.
- **Wheel-binstub vs working-tree invocation**: `cortex-<skill>` binstubs execute against the installed wheel's `site-packages/`, not the working tree; `python3 -m cortex_command.<skill>` runs against the working tree. So when a phase edits `common.py` and a later step invokes a binstub that reads it at runtime, either reinstall the wheel first or invoke via `python3 -m`. Setting `CORTEX_COMMAND_FORCE_SOURCE=1` makes the `bin/cortex-*` wrappers skip the wheel-import branch and run the working-tree module directly, regardless of whether a wheel is installed.
- **CLI/plugin version contract**: → ADR-0002: CLI wheel + plugin distribution
- **Architectural Decision Records**: `cortex/adr/` holds load-bearing decisions per `cortex/adr/README.md` (three-criteria gate, prose-only enforcement, MUST/MUST NOT/SHOULD consumer rules). Skills back-point to ADRs rather than restating rationale.
- **Served lifecycle verb class**: `next`/`advance`/`describe` are a bounded, wheel-owned exception to ADR-0019's dumb-arg-actor rule — they read config, resolve identity, evaluate guards, and serve instructions from the closed transition table; the legacy typed transition verbs stay callable through a coexistence window closed only by an operator-decided protocol-floor bump. Events are the authoritative phase source wherever machine rows exist (artifact derivation is the legacy fallback), which forfeits the cheap prose-side revert — so the standing exit is the roll-forward procedure at `docs/rollforward-exit.md`, not a revert. → ADR-0024 (served-verb class + coexistence); ADR-0025 (events-as-phase-authority).
- **Consumer `EnterWorktree` authorization surface**: `cortex init` writes **no** clause to consumer `CLAUDE.md`; the lifecycle implement phase authorizes `EnterWorktree` via the user's live picker selection at implement time. → ADR-0008: picker-selection authorizes `EnterWorktree` (supersedes ADR-0006).
- **Install-state shared-constant contract**: the install-in-progress marker path (`XDG_STATE_HOME`-aware, 600s stale threshold) is defined by the stdlib-only `cortex_command/init/install_state.py` and duplicated inline in `plugins/cortex-overnight/install_core.py` because the SessionStart hook invokes it via bare system `python3` where the wheel is not importable. Parity is enforced by `tests/test_install_state_path_parity.py`; the wheel never imports from `plugins/cortex-overnight/`.
- **`CORTEX_AUTO_ENSURE=0` opt-out**: mirrors the `CORTEX_AUTO_INSTALL=0` shape from the overnight plugin. Silences `cortex init --ensure` (and `cortex-lifecycle-init-ensure`) without disabling manual init verbs. Foreign-content protection for unanticipated misfires is structural (R19 gate) rather than reliant on this opt-out. The R19 gate is scoped to genuinely foreign content: a marker-less `cortex/` tree carrying committed signature templates (the marker is gitignored, so no clone has one) is adopted additively — marker written, nothing overwritten — instead of declined (#387).
- **Skill-dir path-resolution invariant (SP001/SP002)**: enforced at pre-commit by `cortex-check-skill-path` (D1: raw `${CLAUDE_SKILL_DIR}` / bare `*.md` consult-ref inside a subagent prompt; D2: bare-relative Read/execute path not carried by a `${CLAUDE_SKILL_DIR}/` prefix); rationale in ADR-0009 and the CLAUDE.md skill-authoring design principle. Suppress an intentional illustrative form with `<!-- skill-path-lint:ignore-next -->`.
- **Distributed-CLI dependency bounds**: `uv tool install` from a git ref ignores `uv.lock`, so the `pyproject.toml` `[project.dependencies]` bounds that travel in the wheel's `requires-dist` are the only governance reaching every install path. Cap the drift-prone web stack at the next breaking major, and promote a transitive to a direct, capped dependency when an uncapped upstream parent would otherwise let it drift across a breaking boundary (bounds in `pyproject.toml`). The fresh-resolve route test (`cortex_command/dashboard/tests/test_routes_smoke.py`, run in `validate.yml`) is the structural anti-revert guard.
- **SKILL.md L1 surface ratchet**: each skill's L1 frontmatter surface (`description` + `when_to_use` byte sum) is bounded by a deliberate per-skill budget in `tests/test_l1_surface_ratchet.py`; equal-or-lower passes, and a new skill without a budget row fails a completeness gate. The one exemption surface is the routing-pressure cluster, whose skills carry irreducible disambiguation and path-routing tokens and get their own (higher) budget rows rather than the non-cluster default. Raising any budget row — including a cluster re-cap that cannot meet a target without dropping a trigger phrase — requires a documented rationale plus a lifecycle-id, so a legitimate re-cap is distinguishable from silent drift. New-skill authoring pointer: `CLAUDE.md`. → lifecycle 298.
- **Out-of-process runner supervision**: a persistent host-level launchd guardian plus a manual `cortex overnight recover` verb are the only session-state writers outside the runner itself (observability surfaces stay read-only). → ADR-0011: out-of-process overnight-runner supervision.
- **Worktree containment invariant**: `create_worktree` (`cortex_command/pipeline/worktree.py`) enforces that a same-repo worktree resolves inside the repo root; an out-of-repo `CORTEX_WORKTREE_ROOT` override raises a containment-specific `worktree_escapes_repo` ValueError → CLI exit 1, leaving nothing on disk. The cross-repo / `$TMPDIR` overnight branch (`repo_path` set) is legitimately outside the repo and is exempt; the same-repo overnight path (`repo_path=None`, `session_id` set) is NOT exempt and is governed by the guard. Contract is pinned by the `test_containment_*` block in `tests/test_worktree.py`.
- **Frontmatter-scalar write contract**: Hand-rolled backlog/lifecycle frontmatter scalars are emitted through the single key-scoped quoter `cortex_command/backlog/frontmatter_quote.py` (`STRING_INTENDED_KEYS` allowlist; None sentinel and dates stay bare). A new string-intended, numeric-looking field left off the allowlist re-exposes the type-leak; `tests/test_lifecycle_references_resolve.py` (CI-wired) is the backstop. → ADR-0027.
- **Lifecycle identity is the canonical slug**: a lifecycle's identity is the backlog item's canonical `lifecycle_slug` (`resolve_item.py`'s chain: frontmatter → spec/research dirname → capped `slugify(title)`); ticket numbers, uuid prefixes, and filename stems are input normalization — accepted everywhere, stored nowhere *by the served loop*. The rule governs the `resolve_invocation`-mediated path (`next` → `enter`) only: a hand-typed `cortex-lifecycle-enter --feature <number> --phase none` still creates a numeric-keyed dir and stays permitted (`374/`, `378/`), so not every lifecycle dir on disk is slug-keyed. Consequence: the #378 defensive str-coercions (`resolve.py`, `resolve_item.py:137-141`) MUST be retained — the hand-typed path keeps producing the values they defend. `enter` is the enforcement point (unsafe-slug, missing-lifecycle, and cross-item-uuid guards → stderr + exit 3, no side effect). → ADR-0029.

## Quality Attributes

- **Graceful partial failure**: Tasks may fail. The system retries, optionally hands off to a fresh agent, fails gracefully — completing the rest.
- **Maintainability through simplicity**: Complexity is managed by iteratively trimming skills, workflows, and — symmetrically — safeguards and enforcement layers (**Deletion bias**).
- **Iterative improvement**: Architecture tolerates exploratory development; design emerges through use.
- **Defense-in-depth for permissions**: `settings.json` ships minimal allow, comprehensive deny, sandbox on. For sandbox-excluded commands (git, gh, WebFetch) the allow/deny list is sole enforcement — keep global allows read-only. Overnight runs `--dangerously-skip-permissions`; sandbox is the critical surface.
- **Defense-in-depth for captured subprocess output**: child stderr captured for diagnostics is scrubbed at source by a cue-anchored credential allowlist (`pipeline/dispatch.py:_redact`) before it reaches the brain prompt or the morning report committed to local `main`. The allowlist is defense-in-depth, NOT complete (prefixless secrets and uncued families may pass); it deliberately uses no prefixless fixed-length blob matcher so benign high-entropy diagnostics (SHAs, UUIDs, base64) survive. → #309.
- **Destructive operations preserve uncommitted state**: Cleanup scripts removing user-visible artifacts (worktrees, branches, sessions) SKIP on uncommitted state. Inline destructive sequences extract into named scripts.

## Project Boundaries

### In Scope

- AI workflow orchestration (skills, lifecycle, pipeline). Discovery is documented inline (no area doc): `skills/discovery/SKILL.md`. Backlog has its own area doc (`cortex/requirements/backlog.md`); `cortex/backlog/index.md` is the local-backend (`cortex-backlog`) store. Ticket body authoring is via `skills/backlog-author/` (the shared sub-skill).
- Overnight execution: framework, sessions, scheduled launch, morning report
- Dashboard (~1800 LOC FastAPI), conflict resolution pipeline (~2500 LOC), remote access (Tailscale/mosh/tmux/Cloudflare Tunnel)
- Observability (statusline, notifications, metrics, cost); global agent config
- Multi-agent: parallel dispatch, worktrees, Haiku/Sonnet/Opus selection
- Published teaching *content* under `docs/` (landing page, training scene deck) — a deliberate carve-out from the "no published modules" boundary below; area doc: `cortex/requirements/training.md`

### Out of Scope

- Dotfiles, machine configuration, setup automation for new machines — belong in machine-config
- Application code or libraries — belong in their own repos
- Published packages or reusable modules for others — out of scope; cortex ships as a non-editable wheel

### Deferred

- Migration from file-based state if complexity demands it
- Cross-repo work in one overnight session
- Merging Clarify+Research+Spec into one tracked state — measured token value ~0.3% and they already run in one session, so no split point is lost; fold into the lifecycle reference shrink when that reworks the transition surface, not before

## Conditional Loading

- statusline/dashboard/notifications → cortex/requirements/observability.md
- pipeline/overnight runner/conflict resolution/deferral → cortex/requirements/pipeline.md
- remote access/tmux/mosh/Tailscale → cortex/requirements/remote-access.md
- agent spawning/subagents/multi-agent/parallel dispatch/worktrees/model selection → cortex/requirements/multi-agent.md
- backlog/ticketing/issue tracker/backlog backend → cortex/requirements/backlog.md
- training/workshop/presentation/scene deck → cortex/requirements/training.md

## Global Context

- cortex/requirements/glossary.md

## Optional

Content here is prunable under token pressure — skip without losing spec-required guidance.

- **Sandbox preflight gate**: `bin/cortex-check-parity` validates `cortex/lifecycle/{feature}/preflight.md` on sandbox-source diffs, failing on a missing or invalid preflight.
- **Two-mode gate pattern**: pre-commit gates pair `--staged` (diff schema) with `--audit` (time/repo-wide, `just <recipe>-audit`); the `--staged` scope must stay corpus-congruent with `--audit` (same files at all depths). See `bin/cortex-check-events-registry`.
- **Workflow trimming**: unearned workflows are removed wholesale. Retirements in `CHANGELOG.md`.
- **Known-bad numbers (2026-07-16 token audit)**: verb-turn counts in #390/#391 were computed on undeduplicated JSONL lines — true billed counts are 2.7–30x lower (`cortex-lifecycle-state` ≈5, not 160); the corpus dollar total re-measured ~$5.3k, not $4,473. Rule: dedup by `message.id` before summing `usage`.
- **Reaching subagent records (method changed)**: `isSidechain` no longer splits orchestrator from subagent — it is False on every record in the live corpus (0 of 97,737, re-measured 2026-07-20; the 2026-07-16 corpus that made it a valid splitter has rotated out). Subagent transcripts now live in session-scoped `/private/tmp/**/tasks/*.output`, reachable only via a dispatch record's `toolUseResult.outputFile`, and are cleaned over time — so any turn-count sample skews recent and should say so. Worked example: `cortex/lifecycle/archive/the-synthesizer-and-fallback-reviewer-are/measure.py` (#399).
