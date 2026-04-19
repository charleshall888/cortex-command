# Research: Run /claude-api migrate to opus-4-7 on throwaway branch and report diff

> Generated 2026-04-18. Spike — tier: simple, criticality: medium.

## Epic Reference

Parent epic research: `research/opus-4-7-harness-adaptation/research.md`. This spike answers Epic Open Question 1 (DR-7): "Does `/claude-api migrate this project to claude-opus-4-7` operate on SKILL.md prompts or only on Anthropic SDK/API Python code?" The answer scopes follow-on ticket #085 (prompt audit against DR-2 P1–P6 patterns + DR-5 `consider`-hedge sites). The epic artifact is background context; this research does not reproduce its pattern catalogs.

## Codebase Analysis

### Symlink architecture (load-bearing — verified by inode inspection)

- `~/.claude/*` are the symlinks; `/Users/charlie.hall/Workspaces/cortex-command/{skills,hooks,claude/*}` are the real files. Writes to the main repo's tracked paths are **immediately visible to every subsequent Claude Code session on this machine**.
- Full symlink surface targeting this repo:
  - `~/.claude/skills/<name>` → `{repo}/skills/<name>` (21 skill directories)
  - `~/.claude/hooks/<name>` → `{repo}/hooks/<name>` or `{repo}/claude/hooks/<name>` (24 files, mixed sources)
  - `~/.claude/notify.sh` → `{repo}/hooks/cortex-notify.sh`
  - `~/.claude/statusline.sh` → `{repo}/claude/statusline.sh`
  - `~/.claude/settings.json` → `{repo}/claude/settings.json`
  - `~/.claude/CLAUDE.md` → `{repo}/claude/Agents.md` (global instructions — **not** the repo-root `Agents.md`, which is a separate project-level file)
  - `~/.claude/reference/<name>` → `{repo}/claude/reference/<name>` (5 files)
  - `~/.claude/rules/*` → `{repo}/claude/rules/*`
  - `~/.local/bin/*` → `{repo}/bin/*` plus select `backlog/*.py` scripts

### Setup flow and worktree safety

- Every `just deploy-*` recipe checks `git rev-parse --git-dir != --git-common-dir` and **errors out when run from a worktree** (`justfile:41-44, 125-129`). This is self-enforcing: even an accidental `just setup` from a worktree cannot retarget the global symlinks. Installs run only from the main repo.
- Worktrees hold **physically separate files** — verified: `skills/commit/SKILL.md` in main is inode 56989105 (shared with `~/.claude/skills/commit/SKILL.md`); the same file in the existing worktree `.claude/worktrees/outer-probe/` is inode 56511027. A worktree's `skills/`, `hooks/`, `claude/` are real directories, not symlinks back to main.
- Existing precedent: `.claude/worktrees/` is the repo's established throwaway-worktree location, managed by `hooks/cortex-worktree-create.sh` / `cortex-worktree-remove.sh`.

### Integration points

- Spike deliverable: `research/opus-4-7-harness-adaptation/claude-api-migrate-results.md` (does not exist yet; parent directory exists with `research.md`, `decomposed.md`, `events.log`).
- Report consumer: `backlog/085-…` (declared blocked-by #083 and #084 in `decomposed.md`).
- The `/claude-api` skill is available as a Claude Code built-in (auto-loaded; no plugin cache entry). It will route to the same skill regardless of cwd.

### Conventions

- Spike reports live under `research/<topic-slug>/` at paths specified in the parent backlog.
- Commit via `/commit` skill; never direct `git commit`. Multi-line messages use multiple `-m` flags (no heredocs in sandbox).
- **Do not run `just setup` / `just deploy-*` from a throwaway checkout** — self-blocks from worktrees; would retarget global symlinks if run from a clone.

## Web Research

### What `/claude-api migrate` targets (authoritative)

**Source:** [`anthropics/skills/main/skills/claude-api/shared/model-migration.md`](https://raw.githubusercontent.com/anthropics/skills/main/skills/claude-api/shared/model-migration.md).

The skill targets **files calling the Anthropic SDK** (`anthropic` / `@anthropic-ai/sdk`). File-discovery heuristic explicitly excludes markdown:

> `rg -l "<old-model-id>" --type-not md | cut -d/ -f1 | sort | uniq -c | sort -rn`
>
> "Markdown files (`--type-not md`) are excluded from counting unless the user explicitly asks to update documentation."

Explicit non-targets:

> "[Does not] modify documentation, comments, or non-code references (except system prompts in the same call site)."

Per the [claude-api skill docs page](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/claude-api-skill), auto-activation conditions are SDK imports — not prompt/instruction files.

File classification before any edit: **callers** (swap model + apply breaking changes), **definers** (registries/specs — add alongside, never blind-replace), **opaque string references** (capability gates, test fixtures — swap with check), **suffixed variant IDs** (e.g., `-fast`, `[1m]` — verify before changing).

### What changes it makes

Per [claude-api skill docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/claude-api-skill#migrating-to-a-newer-claude-model):

- Model ID swaps (including typed SDK constants: `Model.CLAUDE_OPUS_4_6` → `Model.CLAUDE_OPUS_4_7`).
- Breaking parameter changes — remove `temperature`, `top_p`, `top_k` for 4.7; convert `thinking: {type: "enabled", budget_tokens: N}` → `thinking: {type: "adaptive"}`.
- Prefill replacement — assistant-message prefill → structured outputs.
- Beta header cleanup — remove GA'd headers (`effort-2025-11-24`, `fine-grained-tool-streaming-2025-05-14`, `interleaved-thinking-2025-05-14`); switch `client.beta.messages.create` → `client.messages.create`.
- Effort calibration — recommends `output_config.effort` (e.g., `xhigh` for coding/agentic on 4.7).
- **Prompt-behavior tuning — flagging only**, scoped to system prompts *in the same call site* as the SDK invocation. Does NOT rewrite standalone `.md` prompt files.
- Silent default handling — opts into `thinking.display: "summarized"` when reasoning surfaces to users on 4.7.

End-of-run manual checklist for items the skill flags but does not apply automatically: integration tests, length-control prompt tuning, cost/rate-limit re-baselining.

### Invocation syntax and flags

No CLI flags. Scope passed as natural prose in the invocation:

```
/claude-api migrate this project to claude-opus-4-7
/claude-api migrate everything under src/ to claude-opus-4-7
/claude-api migrate apps/api.py and apps/worker.py to claude-opus-4-7
```

When scope is bare (e.g., `/claude-api migrate to claude-opus-4-7`), the skill prompts for confirmation — entire working directory, subdirectory, or explicit file list — before editing.

### Precedent — 4.5 and 4.6 migrations

- **4.5**: standalone plugin at [`anthropics/claude-code/plugins/claude-opus-4-5-migration`](https://github.com/anthropics/claude-code/tree/main/plugins/claude-opus-4-5-migration), scoped to "model strings, beta headers, and other configuration details."
- **4.6/4.7**: functionality folded into the general-purpose `claude-api` skill as the `migrate` subcommand — no `claude-opus-4-7-migration` plugin exists. This explains the epic's observed 404 on 2026-04-17 (structural, not transient). Canonical source is `github.com/anthropics/skills/tree/main/skills/claude-api/`.

### Bottom line (HIGH confidence)

**`/claude-api migrate` will not touch cortex-command's SKILL.md files, `Agents.md`, `CLAUDE.md`, reference docs, hooks, or settings JSON.** It targets Python/TypeScript SDK call sites and system prompts inlined at those call sites only. The epic's DR-7 concern that the command might "absorb most of DR-2+DR-5" is refuted by the docs — DR-2 and DR-5 scope (prompt-audit work in `.md` files) is not migration-automation territory.

**Practical implication**: the spike's run is likely to produce a small change set (cortex-command has limited SDK call-site code — `claude/pipeline/dispatch.py`, possibly `claude/sdk/*`, `claude/dashboard/`). The value of still running it is (a) empirical confirmation of the doc-based prediction, (b) catalog of SDK/code migrations the team will adopt separately from the prompt audit, and (c) surfacing any edge cases in cortex-command's codebase that the docs don't anticipate.

## Requirements & Constraints

### `requirements/project.md`

- **Daytime work quality** (l.17): "Research before asking. Don't fill unknowns with assumptions." Directly legitimizes the spike shape.
- **Complexity must earn its place** (l.19): argues for minimum-viable isolation — not layered safeguards.
- **Handoff readiness** (l.13): spike report must be usable by a zero-context agent — concrete file paths and classifications required.
- **Defense-in-depth for permissions** (l.32): sandbox is the critical security surface; overnight bypasses permissions — so this spike is inherently *interactive* (see timing tradeoff below).
- **File-based state** (l.25): markdown report is consistent with project convention.

### `requirements/multi-agent.md`

- **Model Selection Matrix** (l.51–62) + **escalation ladder** (l.75): codifies trivial+low→haiku, simple+high/critical→sonnet, complex+high/critical→opus, no intra-session downgrade. Most likely target of `/claude-api migrate` edits if they reach model-ID strings in `claude/pipeline/dispatch.py`.
- **Worktree precedent**: cross-repo worktrees live at `$TMPDIR/overnight-worktrees/{session_id}/{feature}/` (l.35, l.74). Existing repo precedent for `$TMPDIR` as a safe external-checkout location.

### Constraints that do NOT apply

- No requirements-level "dry-run first" / "run in `$TMPDIR` first" rule for vendor automation. The symlink-propagation guardrail lives only in the project-root `CLAUDE.md`, not in `requirements/`.
- No requirements file prescribes a format/audience/structure for spike reports under `research/`. The three-bullet deliverable structure originates in ticket #083 itself.
- No requirements file covers the "simple + medium" tier for exploratory commands that edit files. The matrix in `multi-agent.md` governs agent model-assignment, not human-safety for vendor automation.

## Tradeoffs & Alternatives

### Isolation strategy (primary)

- **A. `git clone` to `$TMPDIR`** — SAFE. Fresh clone's `skills/`, `hooks/`, `claude/*` are real files in the clone; `~/.claude/*` still target main repo. Diffing back requires `git remote add` / format-patch. Cleanup: `rm -rf`. Con: the `just setup` footgun applies (would retarget symlinks if run).
- **B. `git worktree add` to a non-`.claude/` path** (e.g., `$TMPDIR/cortex-command-083-spike`) — SAFE, self-enforcing. Worktree files are physically separate; `~/.claude/*` still target main repo. `just deploy-*` refuses to run from a worktree, so even accidental `just setup` cannot retarget symlinks. Shared `.git/` gives native `git diff main...<branch>` ergonomics. `git worktree remove` + branch delete for cleanup.
- **C. In-place branch** — **UNSAFE**. Any edit to `skills/*/SKILL.md`, `claude/settings.json`, `claude/Agents.md`, etc. propagates live through symlinks. Any concurrent Claude Code session inherits mutated prompts. The migrate session driving the command is itself running on symlinked skills, so rewriting them mid-run makes behavior undefined. Disqualified.

**Recommended: B (worktree at non-`.claude/` path).** Self-enforcing against the `just setup` footgun, native diff ergonomics, aligns with existing worktree precedent.

### Execution timing

- (i) Immediately (pre-other-work): clean baseline; unblocks #085 fastest. Some uncommitted churn already in `git status` on main — worktree starts from the last commit, so main's dirty state is isolated.
- (ii) Overnight: **disqualified** — `/claude-api migrate` is interactive (confirms scope before editing); overnight pipelines are non-interactive.
- (iii) Doc-read first: 5–10 min reading the claude-api skill docs before running. This research has already done that work (see Web Research above).

**Recommended: (i) with (iii) already absorbed into this research.** Proceed to implementation.

### Report shape

- (i) Raw diff only: zero interpretation; #085 re-does categorization.
- (ii) Summary prose + categorized examples: answers the three deliverable bullets; loses fidelity without diff.
- (iii) Both: summary drives the decision, diff is the receipt. Matches repo's "cite evidence verbatim" pattern.

**Recommended: (iii).** Categorize by file type (SDK Python/TS | SKILL.md | reference/*.md | settings/hooks | other) and change kind (model-ID swap | parameter removal | prefill | header cleanup | effort calibration | flagged-only). If diff is large, emit a sibling `claude-api-migrate.diff` file.

### Scope boundary

- (i) Stop at reporting (strict): cleanest handoff; matches ticket as written. #085 re-does mergeability judgment.
- (ii) Reporting + "Mergeable-candidates" appendix (tentative, #085-revalidates): captures executor's in-context judgment while clearly labeling it as non-binding. Directly supports #085's explicit scope-branching on this spike's output.
- (iii) Propose #085's scope cuts: exceeds spike remit; preempts #085's Plan phase and critical-review gate.

**Recommended: (ii).** One extra section labeled "Tentative mergeability assessment — #085 to re-validate." Value-dense for #085; scoped.

### Runbook seed (for Plan phase)

```
1. Note main-repo HEAD SHA (baseline reference for the report).
2. `git worktree add -b spike/083-claude-api-migrate $TMPDIR/cortex-command-083-spike HEAD`
   (Absolutely NOT under .claude/; NOT an in-place branch.)
3. `cd $TMPDIR/cortex-command-083-spike`. DO NOT run `just setup`.
4. In an interactive Claude Code session at cwd = worktree, run:
   `/claude-api migrate this project to claude-opus-4-7`
   Capture full transcript (including any skill-surfaced checklist).
5. `git status` + `git diff HEAD` in worktree; save diff to $TMPDIR/083-migrate.diff.
6. Back in main repo, write research/opus-4-7-harness-adaptation/claude-api-migrate-results.md:
   - Files touched (grouped by type)
   - Change categories with verbatim examples
   - "Usable as-is for #085?" — direct answer
   - End-of-run checklist reproduced from the skill's output
   - Tentative mergeability assessment (labeled, non-binding)
   - Raw diff (inline if <500 lines; else sibling file referenced)
7. Commit report via `/commit`.
8. `git worktree remove $TMPDIR/cortex-command-083-spike` + delete spike branch.
```

## Open Questions

- Given HIGH-confidence doc evidence that `/claude-api migrate` will not touch SKILL.md files, is running the command still the right next step, or is the doc analysis dispositive enough to close the spike without empirical execution? (Spec phase to resolve with user — the ticket body asks for an empirical run; the research has pre-answered the primary question from docs. Empirical value is now confirmation + SDK-migration catalog, not SKILL.md discovery.) **Deferred: will be resolved in Spec by asking the user.**
