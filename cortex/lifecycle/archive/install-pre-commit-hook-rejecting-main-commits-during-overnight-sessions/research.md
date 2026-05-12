# Research: Install pre-commit hook rejecting main commits during overnight sessions

> **Discovery prior art**: `research/orchestrator-worktree-escape/research.md` DR-3 selected Option E (this ticket's mechanism) over Options A/B/C/D. This research validates Option E and explores integration shape.

## Codebase Analysis

### Files that will change

- **`.githooks/pre-commit`** — single 205-line bash script with seven phases (1, 1.5, 1.6, 1.7, 2, 3, 4). New logic adds a "Phase 0" block before Phase 1.
- **`tests/test_hooks.sh`** or a new `tests/test_overnight_main_commit_block.sh` — new regression test paralleling `tests/test_drift_enforcement.sh`.
- **`justfile`** — possible amendment to `setup-githooks` documentation, or addition of an install-flow hook.
- **`requirements/pipeline.md:24`** — drift candidate; see Open Questions §1.
- **`cortex_command/overnight/runner.py:421-446` (`_commit_followup_in_worktree`)** — possible amendment to surface silent commit failures (see Adversarial Review).
- **No changes needed in the runner's spawn sites** — `CORTEX_RUNNER_CHILD=1` is already set at `runner.py:714` (orchestrator) and `runner.py:901` (batch runner). Both spawn sites pre-date this ticket and provide the load-bearing gate signal.

### Spawn-site reality vs. ticket text

The ticket cites `runner.sh:595` and `runner.sh:635` — these are stale. `runner.sh` no longer exists in the repo. The runner has been fully migrated to Python:
- `cortex_command/overnight/runner.py:1633` — exports `LIFECYCLE_SESSION_ID = session_id` into `os.environ`. Inherited by all `subprocess.Popen` children.
- `cortex_command/overnight/runner.py:682-726` (`_spawn_orchestrator`) and `runner.py:858-903` (`_spawn_batch_runner`) — both runner spawn sites pass `env={**os.environ, "CORTEX_RUNNER_CHILD": "1"}`. Neither sets `cwd=worktree_path`; the orchestrator inherits the runner's cwd (= home repo). This is precisely the gap the session-1708 escape exploited.

### `LIFECYCLE_SESSION_ID` lifecycle (the load-bearing surprise)

`LIFECYCLE_SESSION_ID` is **overwritten** in `claude -p` child processes by `plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh:8-10`:
```bash
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
if [[ -n "$SESSION_ID" && -n "${CLAUDE_ENV_FILE:-}" ]]; then
  echo "export LIFECYCLE_SESSION_ID='$SESSION_ID'" >> "$CLAUDE_ENV_FILE"
```

Trace for the actual session-1708 escape vector:
1. Runner exports `LIFECYCLE_SESSION_ID=overnight-2026-04-21-1708` and spawns orchestrator with `claude -p ... --dangerously-skip-permissions`.
2. Claude Code starts; SessionStart hook fires; `cortex-scan-lifecycle.sh` writes `export LIFECYCLE_SESSION_ID='<Claude UUID>'` into `CLAUDE_ENV_FILE`.
3. Claude Code sources `CLAUDE_ENV_FILE` into the env it propagates to its Bash tool.
4. Orchestrator agent's Bash tool runs `cd /Users/charlie.hall/Workspaces/cortex-command && git commit`. The `git commit` process inherits `LIFECYCLE_SESSION_ID=<Claude UUID>`, **not** `overnight-*`.

**Implications**:
- A naive hook that gates on `[ -n "$LIFECYCLE_SESSION_ID" ]` blocks **all** interactive `/cortex-interactive:commit` invocations, because every interactive Claude Code session also has its UUID injected by SessionStart.
- A prefix-discrimination hook gating on `LIFECYCLE_SESSION_ID =~ ^overnight-` **does not fire** for the actual session-1708 escape, because the variable has been overwritten with the Claude UUID by the time `git commit` runs. The data-loss bug recurs.
- **`CORTEX_RUNNER_CHILD=1`** is the correct gate signal: it is set unconditionally by both runner spawn sites (`runner.py:714, 901`); is not overwritten by SessionStart (the hook only touches `LIFECYCLE_SESSION_ID`); is inherited through `cd && git commit` pipelines via the Bash tool's normal env propagation; and is never set in interactive Claude sessions.

### Other commit paths to local main

Full inventory of `git commit` invocations from runtime code:

| Site | cwd | Branch effect | Notes |
|------|-----|---------------|-------|
| `runner.py:421-446` (`_commit_followup_in_worktree`) | `cwd=str(worktree_path)` | integration branch only (in normal operation) | Single in-runner commit; uses `subprocess.run(check=False)` — silently swallows commit failures |
| `cortex_command/overnight/smoke_test.py:97` | tmp test repo | n/a | Test-only; ephemeral repo |
| `bin/cortex-commit-preflight` | invoker's cwd | n/a | Read-only — no `git commit` despite the name |
| `hooks/cortex-validate-commit.sh` | n/a | n/a | Validates commit message format on PreToolUse |
| `skills/commit/SKILL.md` (and plugin mirror) | user's cwd | depends on user | Interactive only — `CORTEX_RUNNER_CHILD` is unset |

The morning-report-commit-to-main path described in `research/orchestrator-worktree-escape/research.md` and the `requirements/pipeline.md:24` AC line ("The morning report commit is the only runner commit that stays on local `main`") **does not exist in current code**. `_generate_morning_report` at `runner.py:363-403` writes the file via `report.write_morning_report(...)` without a subsequent `git commit`. There is no other auto-commit path that targets local `main`. **No legitimate runner code path commits to `main` today.**

### Test harness

- **`tests/test_drift_enforcement.sh`** — the pattern for direct `.githooks/pre-commit` invocation: `set +e; HOOK_OUTPUT="$("$HOOK" 2>&1)"; HOOK_EXIT=$?; set -e` — assert exit code and stderr substring.
- **`tests/test_runner_followup_commit.py:54-100`** — worktree-construction scaffolding: `_init_repo` + `git worktree add ... <branch>` + locally-baked `user.email` and `commit.gpgsign=false`.
- **`tests/test_hooks.sh`** — umbrella runner; invoked from `just test-hooks`.
- **`just test-hooks`** (justfile:352-353) and `just test` (justfile:413-415, 444) — the test entry points.
- **Worktree-on-main gotcha**: `git worktree add <path> main` refuses if `main` is checked out elsewhere. Existing pattern uses a dedicated branch like `test-integration-branch`. The new test must initialize the home repo on a different branch (e.g. `--initial-branch=trunk`) and then `git worktree add wt main` — or use `--detach` followed by `checkout -b main`.

### Conventions to follow

- Multi-phase numbered hook style (`# ----- Phase N -----`).
- `bash` shebang, bash-3.2 compatibility (no `mapfile`, no associative arrays — comment at `.githooks/pre-commit:32-33` calls this out explicitly).
- `set -euo pipefail` inherited from the file; new code must use `${VAR:-}` defaults under `nounset`.
- `pre-commit:` stderr prefix for hook-level error messages (existing convention at `.githooks/pre-commit:49,68`).
- Existing hook composes external helpers (`bin/cortex-invocation-report`, `just _list-build-output-plugins`) — invoking external scripts from inside the hook is precedented.

## Web Research

### Worktrees and shared hooks (authoritative)

- `git-worktree(1)`: each linked worktree has a private `$GIT_DIR` at `.git/worktrees/<id>/`, while `$GIT_COMMON_DIR` resolves back to the main repo's `.git/`. Git config is **shared by default** — `core.hooksPath = .githooks` set in the home repo's `.git/config` propagates to all linked worktrees. This is not documented prominently in the man pages but is the directly-verified behavior; the well-known `pre-commit` framework bug ([pre-commit/pre-commit#808](https://github.com/pre-commit/pre-commit/issues/808)) installed into the per-worktree `.git/worktrees/<id>/hooks/` and silently never ran.
- A relative `core.hooksPath = .githooks` works correctly inside worktrees because git resolves it relative to the working-tree root, and each worktree checks out the same `.githooks/` files.
- `extensions.worktreeConfig=true` is a **bypass surface**: when enabled, a worktree can override `core.hooksPath` to e.g. `/dev/null` and skip the hook. Mitigation: hook self-checks via `git config --get extensions.worktreeConfig` and refuses to proceed if a per-worktree `core.hooksPath` is set; or simply accept that hooks are advisory.
- Absolute paths in `core.hooksPath` are brittle across worktrees ([lefthook/lefthook#1398](https://github.com/evilmartians/lefthook/issues/1398)). Stay relative.

### Branch-detection idioms

| Idiom | Detached HEAD behavior | Initial commit | Notes |
|-------|------------------------|----------------|-------|
| `git symbolic-ref HEAD` | exit 1, `fatal: ref HEAD is not a symbolic ref` — must catch | returns `refs/heads/<branch>` even on unborn branch | Canonical; pre-commit-hooks `no-commit-to-branch` uses this (catches and treats as "not on branch ⇒ allow") |
| `git rev-parse --abbrev-ref HEAD` | returns literal string `HEAD`, exit 0 | works | Theoretical collision: a branch literally named `HEAD` would alias |
| `git branch --show-current` (Git ≥ 2.22) | returns empty string | works | Cleanest semantics; requires version gate |

For "reject commits to `main`", the safe default on detached HEAD is **fail-open** (the agent isn't on `main`). The `pre_commit_hooks/no_commit_to_branch.py` reference does exactly this with a `try: cmd_output('git', 'symbolic-ref', 'HEAD') except CalledProcessError: return False`.

Sources: [pre_commit_hooks/no_commit_to_branch.py](https://github.com/pre-commit/pre-commit-hooks/blob/main/pre_commit_hooks/no_commit_to_branch.py), [efrecon/pre-commit-hook-branch-check](https://github.com/efrecon/pre-commit-hook-branch-check), [Adam Johnson on `--show-current`](https://adamj.eu/tech/2023/08/20/git-output-just-current-branch-name/).

### Multi-policy hook chaining

Git itself runs exactly one script per hook name. `pre-commit.d/` is **not** a git-native convention — it is a userspace pattern implemented by dispatcher tools ([webcoyote/git-multi-hook](https://github.com/webcoyote/git-multi-hook), [pivotal-cf/git-hooks-core](https://github.com/pivotal-cf/git-hooks-core)). The major frameworks (husky, pre-commit, lefthook) all use a **single-file dispatcher** model — multi-policy chaining happens in the YAML/JSON config, not the filesystem layout.

For an in-tree hand-rolled hook, the canonical idiom for ≤5 policies is the **single-file phased script** — exactly what `.githooks/pre-commit` already does.

### Idempotent install patterns

`core.hooksPath = .githooks` set by a setup recipe (the existing pattern) is idempotent (re-running rewrites the same value). Failure modes:
- Contributor forgets `just setup-githooks` → hook silently does nothing — **the dominant failure mode** matching the threat model.
- Lost executable bit on clone — git tracks `+x`, so this is not an issue if committed correctly.
- Old git (<2.9, June 2016) — `core.hooksPath` ignored. Not a concern in 2026.
- Global `core.hooksPath` in dotfiles (e.g. [gabyx/Githooks](https://github.com/gabyx/Githooks)) overrides per-repo — local config wins for local files.

### Bypass surface (anti-patterns)

Client-side hooks are advisory. Bypasses an adversarial-or-confused agent can exercise:
- `git commit --no-verify` — bypasses all client-side hooks unconditionally.
- `git -c core.hooksPath=/dev/null commit` — per-command override. **The cortex repo already documents this exact pattern** at `morning-review/walkthrough.md` for legitimate reasons.
- `GIT_DIR=/tmp/fake git commit` — re-roots git operations.
- `git update-ref refs/heads/main <sha>` — direct ref manipulation, doesn't run any hook.
- `git hash-object -w | git commit-tree | git update-ref refs/heads/main` — plumbing-level commits, no hook invocation.
- `chmod -x .githooks/pre-commit` or rewriting the file — the agent owns the files.

The hook catches **accidental escapes and tooling bugs**. It does not defend against an adversarial agent. Server-side enforcement (GitHub branch protection on `main`) is the only sound defense for an adversarial threat model.

Sources: [git-scm.com/docs/githooks](https://git-scm.com/docs/githooks), [git-scm.com/docs/git-worktree](https://git-scm.com/docs/git-worktree), [husky how-to](https://typicode.github.io/husky/how-to.html), [Bitbucket standardize hooks](https://support.atlassian.com/bitbucket-cloud/kb/standardize-git-hooks-across-a-repository/), [Kim Lindhard's prevent-commit-to-master](https://www.kim-lindhard.com/git-prevent-commit-to-master/).

## Requirements & Constraints

### Defense-in-depth (`requirements/project.md:34`)

> "The overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`), making sandbox configuration the critical security surface for autonomous execution."

This hook is a sibling enforcement layer alongside the sandbox. Sandbox blocks filesystem writes outside the allowlist; the hook blocks `git commit` to `main` from runner-spawned children.

### Session Orchestration AC (`requirements/pipeline.md:22-28`)

> "Integration branches (`overnight/{session_id}`) persist after session completion and are not auto-deleted — they are left for PR creation to main"
> "Artifact commits (lifecycle files, backlog status updates, session data) land on the integration branch, not local `main` — they travel with the PR"
> "The morning report commit is the only runner commit that stays on local `main` (needed before PR merge for morning review to read)"

The first two clauses match the hook's purpose exactly. **The third clause is stale**: the codebase agent confirmed `_generate_morning_report` does not commit. The drift between the requirements doc and the code is a load-bearing decision for this ticket — see Open Questions §1.

### Worktree Isolation AC (`requirements/multi-agent.md:26-36`)

> "Each feature executes in an isolated git worktree, providing independent file state and a dedicated branch to prevent interference between parallel agents."

This hook is the git-layer enforcement of the worktree isolation invariant. The `multi-agent.md` AC does not currently claim git-layer enforcement — the hook can be framed as the implementation of an implicit invariant rather than a new requirement.

### `LIFECYCLE_SESSION_ID` provenance (`requirements/observability.md:56`)

> "`LIFECYCLE_SESSION_ID` environment variable" — used by `bin/cortex-log-invocation` to route per-session JSONL telemetry.

This is the only normative reference to the variable. It is a session-scoped contract; no requirement forbids reusing it as a gate signal — but per the codebase findings, the variable is overwritten by `cortex-scan-lifecycle.sh` and is therefore not a reliable gate. `CORTEX_RUNNER_CHILD` is not currently mentioned in any requirements doc, so reusing it here is novel — this is worth documenting alongside the implementation.

### Existing hook policies (`.githooks/pre-commit`)

The hook is `bash` with `set -euo pipefail` and seven phases:
- **Phase 1** — plugin name validation & classification (every `plugins/*/.claude-plugin/plugin.json` requires non-empty `.name`; plugin dir must be in `BUILD_OUTPUT_PLUGINS` or `HAND_MAINTAINED_PLUGINS`).
- **Phase 1.5** — SKILL.md-to-bin parity check via `just check-parity --staged`, triggered by staged paths under skills/, bin/cortex-, justfile, requirements/, tests/, hooks/, etc.
- **Phase 1.6** — `bin/cortex-*` shim presence (`cortex-log-invocation` line in first 50 lines).
- **Phase 1.7** — backlog entry-point telemetry-call enforcement.
- **Phase 2** — build-needed decision.
- **Phase 3** — conditional `just build-plugin`.
- **Phase 4** — drift loop (`git diff --quiet -- "plugins/$p/"` per build-output plugin).

No existing check covers branch name, `LIFECYCLE_SESSION_ID`, `CORTEX_RUNNER_CHILD`, or any env-var-based gate. New logic is additive; the natural slot is **Phase 0** (before Phase 1) so it fails fast before expensive plugin work like `just _list-build-output-plugins`.

### Project conventions (`CLAUDE.md`)

- "Always commit using the `/cortex-interactive:commit` skill — never run `git commit` manually" — runner agents should not be running `git commit` manually; this hook formalizes that at the git layer.
- "Run `just setup-githooks` after clone to enable the dual-source drift pre-commit hook" — the activation pathway. New policy ships through the same `core.hooksPath=.githooks` mechanism.
- "Hook/notification scripts must be executable (`chmod +x`)."

## Tradeoffs & Alternatives

### Integration alternatives

- **Alternative A — Extend existing `.githooks/pre-commit` in-place (Phase 0)**: ~15 LOC; one file touched; matches the established phased-comment style; inherits `set -euo pipefail` and the resolved `REPO_ROOT`; sub-millisecond performance impact (single env-var check + `git symbolic-ref HEAD`). **Recommended.**
- **Alternative B — `pre-commit.d/*.sh` chain dispatcher**: significantly higher complexity (rewrite the dispatcher, move existing 205 lines to a sub-script, decide error-propagation semantics, handle shared state). Over-engineering for two policies; no precedent for `.d/` directories in this repo. Defer until the file crosses ~300 lines.
- **Alternative C — Standalone hook script invoked from existing hook**: ~10 LOC plus a 1-line invocation in the existing hook. Middle ground; valid but adds an extra fork+exec per commit and a category mismatch (security-only script lives in `.githooks/`, but cortex utility scripts live in `bin/`).
- **Alternative D — Bypass `.githooks/` entirely (`.git/hooks/pre-commit`)**: actively contradicts the established `core.hooksPath = .githooks` pattern; `.git/hooks/` is not version-controlled; defeats `setup-githooks`. **Reject.**

### Install strategies

- **Install-1 — Status quo (manual `just setup-githooks` post-clone)**: zero implementation; documented in CLAUDE.md. **Risk**: a fresh contributor running overnight before `setup-githooks` has zero protection. AC clause "survives `just setup` / repo reclone scenarios" reads naturally as "once installed, hooks don't drift away" — already satisfied.
- **Install-2 — Auto-run `setup-githooks` from `python-setup`**: ~3 LOC; closes the fresh-contributor gap. **Risk**: mutates `.git/config` silently; problematic for CI/release pipelines that legitimately do not want hooks; conflates dev-environment setup with git-config mutation.
- **Install-3 — Runner-startup verification**: `cortex overnight start` checks `git config --get core.hooksPath` and refuses to launch unless `.githooks` is configured and the hook is present. Fail-closed at the moment of risk, not opportunistically. **Recommended over Install-2** per Adversarial Review.
- **Install-4 — `init.templateDir` / husky-style `prepare`**: architectural mismatch (Python repo, no JS). **Reject.**

### Recommended approach

- **Integration: Alternative A** — extend `.githooks/pre-commit` with a Phase 0 block before Phase 1.
- **Install: Install-3** — runner-startup verification (fail-closed at the moment of risk). Keep the existing manual `just setup-githooks` as the documented dev-onboarding step.

## Adversarial Review

### Failure modes and edge cases

**FATAL (resolved): `LIFECYCLE_SESSION_ID` overwrite by SessionStart hook.** See Codebase Analysis §"`LIFECYCLE_SESSION_ID` lifecycle" for the verified trace. Mitigation: gate on `CORTEX_RUNNER_CHILD=1` instead.

**Test harness gotchas**:
- `git worktree add <path> main` refuses if `main` is checked out elsewhere — initialize home repo on `--initial-branch=trunk`, leave `main` unchecked-out, then `git worktree add wt main`.
- `commit.gpgsign` and `user.email` must be set repo-locally per `tests/test_runner_followup_commit.py:43-45,86-88` — tests that don't will hang or fail in CI.

**Phase 0 ordering**: must run *before* Phase 1 (currently the first), because Phase 1 invokes `just _list-build-output-plugins` (subprocess fork × ~30-80ms × 2). Failing fast on the security gate before any other code runs is the correct ordering. New code path must be careful with `${VAR:-}` defaults to play nicely with `set -u`.

**`_commit_followup_in_worktree` silent failure**: `runner.py:447` uses `subprocess.run(check=False)` and ignores commit failures. If the worktree is misconfigured (e.g., somehow on `main`) and Phase 0 rejects, followups are silently lost. Add explicit logging at the call site as a sibling change.

### Security concerns / anti-patterns

This hook catches **accidents and tooling bugs**, not adversarial agents. Bypass surface beyond `--no-verify`:
- `git -c core.hooksPath=/dev/null commit` — per-command config override (already documented in `morning-review/walkthrough.md`).
- `GIT_DIR=<elsewhere> git commit` — re-roots git operations.
- `git update-ref refs/heads/main <sha>` and `commit-tree | update-ref` — plumbing skips hooks entirely.
- Replacing the hook script (`chmod -x` or rewrite) — the agent owns the files.
- `extensions.worktreeConfig=true` + per-worktree `core.hooksPath` override.

**Mandatory mitigation**: the spec must explicitly state the threat model — accidents and tooling bugs only — and recommend GitHub branch protection on `main` as the canonical defense for the adversarial case.

### Assumptions that may not hold

- **`requirements/pipeline.md:24` morning-report-commit-to-main exception is stale** but unresolved. Either update the requirements doc as part of this ticket (matching current code) or carve out a runner-side bypass for legitimate runner commits. Choosing neither risks a future implementer silently breaking when they re-add the morning-report commit.
- **Auto-installing hooks from `python-setup` (Install-2)**: contaminates CI/release pipelines that legitimately do not want hooks; mutates local git config silently. Install-3 (runner-startup verification) is the safer alternative.
- **Detached HEAD / rebase / cherry-pick states**: `git symbolic-ref HEAD` fails — Phase 0 must catch and fail open (allow) since the commit isn't targeting `main`.

### Recommended mitigations

1. **Gate on `CORTEX_RUNNER_CHILD=1`, not `LIFECYCLE_SESSION_ID`.** This is the load-bearing change vs. the original ticket. Surface in Spec for explicit user resolution.
2. **Document the threat model honestly** in spec acceptance criteria: "catches accidental escapes and tooling bugs; does not defend against adversarial agents."
3. **Resolve the requirements/code drift on morning-report-on-main** before merge — either update `pipeline.md:24` to remove the stale clause, or design the hook to allow that specific path (which would require additional discrimination beyond `CORTEX_RUNNER_CHILD`).
4. **Install via Install-3 (runner-startup verification)**, not Install-2 (`python-setup` auto-mutate). Keep the existing manual `just setup-githooks` recipe; refuse to launch overnight without it.
5. **Test all four cases** in the regression test:
   - (a) main + `CORTEX_RUNNER_CHILD=1` from worktree → reject
   - (b) main + `CORTEX_RUNNER_CHILD=1` from `$REPO_ROOT` → reject (the actual session-1708 vector)
   - (c) main, no `CORTEX_RUNNER_CHILD` → allow (interactive case)
   - (d) integration branch + `CORTEX_RUNNER_CHILD=1` from worktree → allow (legitimate runner commit)
6. **Add explicit logging in `_commit_followup_in_worktree`** when the commit subprocess returns non-zero — surfaces silent rejections from this hook (and any other commit failure) to morning review.
7. **Document GitHub branch protection on `main`** as the canonical adversarial defense, in `requirements/pipeline.md` or a sibling change.

## Open Questions

All five questions resolved by user on 2026-04-29:

- **§1 — Gate signal: `CORTEX_RUNNER_CHILD` vs `LIFECYCLE_SESSION_ID`.** Verified: `cortex-scan-lifecycle.sh:8-10` overwrites `LIFECYCLE_SESSION_ID` with the Claude Code session UUID for *every* SessionStart, including the orchestrator's child. The original ticket's predicate (`reject when LIFECYCLE_SESSION_ID is set and non-empty`) does not catch the actual session-1708 escape. **Resolved: gate on `CORTEX_RUNNER_CHILD=1` only** (not on `LIFECYCLE_SESSION_ID`). Belt-and-suspenders is rejected because including `LIFECYCLE_SESSION_ID` would block all interactive `/cortex-interactive:commit` invocations (the SessionStart hook sets it for every interactive Claude Code session too). The branch-is-main predicate is the second condition. This is a load-bearing change to the original ticket's predicate.

- **§2 — Requirements doc drift on morning-report-on-main.** `requirements/pipeline.md:24` mandates "the morning report commit is the only runner commit that stays on local `main`," but `_generate_morning_report` (`runner.py:363-403`) writes to `lifecycle/sessions/{session_id}/morning-report.md` which is gitignored at `.gitignore:41` — no commit happens, and morning review reads the file directly from disk. **Resolved: option (a) — update `requirements/pipeline.md:24` as part of this ticket** to remove the stale clause and reflect that artifact commits land on the integration branch only; the morning report lives in the gitignored session directory and does not need a commit. No carve-out in the hook is required.

- **§3 — Install strategy: AC clause "survives `just setup` / repo reclone scenarios".** No `just setup` recipe exists; the closest match is `just python-setup`. CLI-install context: cortex now ships as `uv tool install -e .` plus plugins via `/plugin install`; the cortex-command repo itself is what this ticket protects (downstream user repos are out of scope). **Resolved: option (a) + (c)**:
  - (a) Reword the AC clause to "survives `just setup-githooks` / repo reclone scenarios" — there is no `just setup` to reference.
  - (c) Add runner-startup verification in `cortex overnight start` that refuses to launch if `core.hooksPath` is unset or the hook file lacks the Phase 0 signature. Actionable error: "Run `just setup-githooks` before launching overnight." Fail-closed at the moment of risk.
  - Reject (b) auto-mutating `core.hooksPath` from `python-setup` — silently mutating local git config is hostile to CI/release pipelines that legitimately do not want hooks.
  - Downstream-repo hook installation (when `cortex overnight start` runs against repos other than cortex-command) is a separate concern; defer to a follow-up ticket.

- **§4 — Threat model documentation.** **Resolved: yes — codebase is mature enough to enforce honest threat-model framing.** Spec must explicitly document: this hook catches accidents and tooling bugs only; adversarial agents can bypass via `--no-verify`, `git -c core.hooksPath=/dev/null`, `GIT_DIR=` overrides, plumbing-level commits (`git update-ref`, `commit-tree`), and self-modifying the hook script. The canonical adversarial defense is GitHub branch protection on `main` (require PR, disallow direct push) — recommend as a follow-up ticket if not already in place.

- **§5 — `_commit_followup_in_worktree` silent failure.** **Resolved: in scope for this ticket.** The runner's only legitimate commit path uses `subprocess.run(check=False)` and swallows errors; without explicit logging, a Phase 0 rejection from the new hook would be undebuggable. Add a stderr/log line at `runner.py:447` when the commit subprocess returns non-zero.
