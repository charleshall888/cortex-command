# Research: Lazy-apply cortex CLI auto-update

Topic: Close the post-epic-113 regression where users drift behind on `cortex` CLI fixes because the upgrade verb is manual. Implement Shape 3 (hybrid lazy-apply): SessionStart hook in the cortex-interactive plugin probes upstream → writes flag in `${XDG_STATE_HOME}/cortex-command/update-available` → next user-initiated `cortex` invocation applies the update synchronously before executing the user's command.

## Epic Reference

Epic research: `research/overnight-layer-distribution/research.md`. The epic decomposed cortex's distribution into a CLI tier and a plugins tier; Q7 of the epic chose explicit upgrade verbs (`cortex upgrade`, `/plugin update`, `cortex init --update`) and acknowledged plugin auto-update as Claude Code's responsibility. **This ticket extends the CLI upgrade story** by adding a lazy-apply gate to `cortex upgrade` so users do not have to manually invoke it. It does not substitute for the plugin auto-update gap (still Claude Code's job) and does not change the per-repo-scaffolding upgrade story.

## Codebase Analysis

### Files that will change

- **`plugins/cortex-interactive/hooks/hooks.json`** — add a `SessionStart` array entry. Existing file (lines 1–15) only registers `PreToolUse` for `cortex-validate-commit.sh`. The minimum-viable SessionStart entry follows the same `${CLAUDE_PLUGIN_ROOT}/hooks/...` shape — no other plugin currently has SessionStart, so this is the first.
- **`cortex_command/cli.py`** — insert an upgrade-flag check gate in `main()` (lines 307–317), immediately before `args.func(args)` at line 317. Must read flag, run `_dispatch_upgrade()` synchronously when conditions met, then dispatch the user's command. Existing `_dispatch_upgrade()` at lines 71–105 runs `git status --porcelain` (refuses on dirty tree, lines 85–90) → `git pull --ff-only` → `uv tool install -e --force`; returns 0/1; does NOT re-exec.
- **`cortex_command/init/handler.py`** — in step 7 (line 188), add a second `settings_merge.register()` call for the new XDG state path so plugin hook writes are sandbox-allowed when cortex runs inside Claude Code.

### Files that will be created

- **`plugins/cortex-interactive/hooks/cortex-probe-updates.{sh,py}`** — SessionStart hook script. Discovers cortex install root, checks daily-throttle stat, acquires `flock -n` on a stable lock, runs `timeout 5 git ls-remote $REMOTE_URL main`, compares to local HEAD, writes flag atomically. Always exits 0; reads JSON from stdin per Claude Code SessionStart hook contract.
- **`tests/test_cortex_check_update.py`** — pytest unit tests for dev-mode predicates, throttle, flock semantics. Closest analog: `tests/test_cli_upgrade.py` (167 lines, mocks subprocess for upgrade flow). Settings-merge concurrent-writer tests at `cortex_command/init/tests/test_settings_merge.py` are reference for flock test patterns.
- **`docs/setup.md`** — short section explaining auto-update behavior and disable mechanisms.

### Relevant existing patterns

- **Idempotent allowlist registration**: `cortex_command/init/settings_merge.py::register(repo_root, target_path, *, home=None)` (lines 133–137). Membership-check before append (line 196) preserves order. `target_path` is a string — accepts user-global absolute paths, not just repo-relative. Uses sibling-lockfile + `fcntl.flock(LOCK_EX)` on `~/.claude/.settings.local.json.lock` (lines 69–85).
- **Atomic file writes**: `cortex_command/common.py::atomic_write` (line 366) — tempfile + `os.replace` + `durable_fsync` (uses macOS F_FULLFSYNC where available). Reuse this for in-process flag updates.
- **Reference SessionStart hook**: `claude/hooks/cortex-sync-permissions.py` (legacy stranded location, but the convention is the same) — shebang `#!/usr/bin/env python3`, reads JSON stdin, silent `except Exception: pass`, always exits 0. **Do NOT propose migrating the stranded hooks** — they are out of this ticket's scope.
- **`cortex upgrade` already exists**: `_dispatch_upgrade()` in `cli.py:71-105`. The auto-update gate is a NEW caller of this same routine — no need to rewrite the upgrade itself.

### Greenfield decisions (no precedent in repo)

- `${XDG_STATE_HOME}` / `~/.local/state` convention — first use for cortex-command.
- `os.execv` self-re-exec — no precedent.
- `CORTEX_DEV_MODE` env var — not present anywhere; new.

### Test conventions

pytest (`pyproject.toml:26-28`, `pythonpath=["."]`). Tests live at `tests/test_*.py` for CLI/integration and `cortex_command/<module>/tests/test_*.py` for module-specific. Mock subprocess calls via `unittest.mock.patch`.

## Web Research

### Closest prior art

- **pnpm `self-update`** ([pnpm.io/cli/self-update](https://pnpm.io/cli/self-update)) — declarative pin → apply on next invocation. Closest behavioral match to the ticket's design.
- **Homebrew** ([docs.brew.sh/FAQ](https://docs.brew.sh/FAQ); [#6382](https://github.com/Homebrew/brew/issues/6382)) — staleness-timestamp lazy apply on `brew install/upgrade/tap` (default 60s `HOMEBREW_AUTO_UPDATE_SECS`). Pure timestamp, no SHA flag.
- **update-notifier (Node)** ([npmjs.com/package/update-notifier](https://www.npmjs.com/package/update-notifier)) — detached background probe + JSON config flag file under `~/.config/configstore/`. Notify-only (no apply). Closest pattern for the *probe* half.
- **rustup** ([rust-lang.github.io/rustup/basics.html](https://rust-lang.github.io/rustup/basics.html)) — opt-out auto-self-update inline on relevant invocations; no flag-file gate.
- **gh, uv** — explicit verbs only; no flag-file lazy-apply.

### Key reference docs

- [XDG Base Directory v0.8 (May 2021)](https://specifications.freedesktop.org/basedir/latest/) — `XDG_STATE_HOME` (default `~/.local/state`) is canonically correct for "data persisting between restarts but not important enough for `XDG_DATA_HOME`": throttle state, last-seen-remote-SHA flag. Distinguished from `XDG_CACHE_HOME` (regenerable, may be discarded).
- [flock(2) man page](https://man7.org/linux/man-pages/man2/flock.2.html) — kernel auto-releases on process death (including SIGKILL); no userland stale-lock cleanup needed on local FS. NFS is the historical exception.
- [microhowto atomic file rewrite](http://www.microhowto.info/howto/atomically_rewrite_the_content_of_a_file.html), [yakking](https://yakking.branchable.com/posts/atomic-file-creation-tmpfile/) — POSIX `rename(2)` is atomic for observers **only** when source and destination are on the same filesystem. Cross-FS `mv` falls back to copy+unlink (non-atomic).
- [docs.astral.sh/uv/concepts/tools](https://docs.astral.sh/uv/concepts/tools/) — `uv tool install --force` takes a file-based lock on the target venv; concurrent uv invocations against the same env serialize. Required to overwrite an existing tool.
- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks); [issue #43123](https://github.com/anthropics/claude-code/issues/43123) — SessionStart timeout default is 10 min as of 2.1.50; background subprocess work needs full stdio redirect (`>/dev/null 2>&1 </dev/null &`) or it silently blocks claude-code.
- [git ls-remote upstream timeout thread](https://public-inbox.org/git/0Mey7N-1hOXHn3kBF-00OYB8@mail.gmx.com/T/) — `git ls-remote` has no connect-timeout flag; standard mitigation is `timeout(1)` wrapper. `GIT_TERMINAL_PROMPT=0` prevents credential-prompt hangs.

### Patterns and anti-patterns

- **Pattern**: tempfile in same dir + POSIX `rename()` for atomic flag updates. Verified atomic for cross-process readers.
- **Pattern**: `flock` locks tied to the open file description; clean release on process death without manual cleanup.
- **Anti-pattern**: per-invocation network checks. Slow, breaks offline use; gh/npm/brew explicitly avoid this.
- **Anti-pattern**: `os.execv` self-update without scrubbing inherited fds, signal handlers, env mutations. Both [gkbrk](https://www.gkbrk.com/wiki/python-self-update/) and [hackthology](https://hackthology.com/how-to-write-self-updating-python-programs-using-pip-and-git.html) self-update guides ignore this; safer alternative they suggest is "print rerun and exit."
- **Anti-pattern**: cross-FS `mv` for atomic rename. Degrades silently to copy+unlink.

## Requirements & Constraints

### Distribution model (cite paths)

`CLAUDE.md:20-22`: "Cortex-command ships as a CLI installed via `uv tool install -e .` plus plugins installed via `/plugin install`. It no longer deploys symlinks into `~/.claude/`."

`requirements/project.md:53`: "The `cortex` CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope."

The auto-update mechanism must align with the editable-clone model: `git pull` against the install repo, then `uv tool install -e --force` to regenerate the entry-point shim. Not package-manager semantics.

### Sandbox / allowWrite constraints (cite paths)

`requirements/project.md:25-26`: "**Per-repo sandbox registration**: `cortex init` additively registers the repo's `lifecycle/sessions/` path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array. This is the only write cortex-command performs inside `~/.claude/`; it is serialized across concurrent invocations via `fcntl.flock` on a sibling lockfile."

**Critical finding**: Project documents per-repo registration only. Adding `${XDG_STATE_HOME}/cortex-command/` would be the first user-global allowWrite entry, which is a deviation from the documented per-repo-only philosophy. Spec must either (a) establish a documented user-global registration policy, or (b) scope state to the per-repo `lifecycle/sessions/` directory already allowed.

### Defense-in-depth permissions (cite path)

`requirements/project.md:33`: "**Defense-in-depth for permissions**: The global `settings.json` template ships conservative defaults — minimal allow list, comprehensive deny list, sandbox enabled. ... The overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`), making sandbox configuration the critical security surface for autonomous execution."

Adding `${XDG_STATE_HOME}/cortex-command/` to allowWrite expands the trust boundary. The "minimal allow list" principle requires the spec to justify why this path is safe — what data lives there, what autonomous operations can read/act on it.

### Failure handling (cite path)

`requirements/project.md:15`: "**Failure handling**: Surface all failures in the morning report. Keep working on other tasks. Stop only if the failure blocks all remaining work in the session."

Hook must not block session start. Apply failures should not crash the user's `cortex` command; error must be visible (stderr) and the flag should remain sticky for retry on next invocation.

### Complexity bar (cite path)

`requirements/project.md:18-19`: "**Complexity**: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct. ... ROI matters — the system exists to make shipping faster, not to be a project in itself."

The auto-update mechanism adds a state-directory convention, env-var contract, hook script, and CLI gate. Spec must articulate the real-problem case (drift on manual `cortex upgrade`) and pick the simplest viable composition.

### Personal-tooling vs multi-user (cite path)

`requirements/project.md:6-7`: "Agentic workflow toolkit ... Primarily personal tooling, shared publicly for others to clone or fork."

Mitigations like staged rollout do not apply. However, a forking user can be foot-gunned by hardcoded `CORTEX_REPO_URL` defaults — the design must source the URL from the install's `git remote get-url origin`, not a constant.

### Epic 113 conclusions (cite path)

`backlog/113-distribute-cortex-command-as-cli-plus-plugin-marketplace.md`: epic chose explicit upgrade verbs. Per `research/overnight-layer-distribution/research.md` Q7: "binaries auto-update while content does not (industry-wide gap). Proposed: `cortex upgrade` for the runner tier (git pull + re-link); plugin marketplace has no auto-update (Claude Code ships this gap unsolved); `cortex init --update` scaffolds new lifecycle templates."

The Requirements agent argued this ticket may **contradict** Q7's "explicit verb" stance. Counter-reading: this ticket does not remove the explicit verb (`cortex upgrade` still exists) — it adds a lazy-apply gate that calls the same verb. The spec must explicitly frame this as "add a lazy-apply trigger for the existing explicit verb," not "replace the explicit verb with automatic update."

### Atomic-write convention (cite path)

`requirements/pipeline.md:126`: "Atomicity: All session state writes use tempfile + `os.replace()` — no partial-write corruption."

Reuse `cortex_command.common.atomic_write` for in-process flag updates. Hook is shell — must use `mktemp` *inside* `${XDG_STATE_HOME}/cortex-command/` to keep rename same-FS.

## Tradeoffs & Alternatives

### Component A: Apply-on-cortex-invoke gate

Recommendation: **A1 (apply on next invocation, no opt-out) with a `--help`/`-h`/`--version` carve-out.** The simple invariant "next `cortex` invocation = upgraded" is load-bearing for the design's UX promise; A3's per-subcommand classification table is a maintenance hazard, A4's apply-throttle solves a non-problem (flag is unlinked on success). The carve-out is a 3-line check that prevents 5s stalls on bare-help paths where users genuinely won't tolerate them.

### Component B: Flag-file storage scheme

Recommendation: **B1 (single flag file, atomic rename via `cortex_command.common.atomic_write`).** B2's SHA-named directory adds ordering ambiguity (which SHA wins on concurrent writes?), B3's append-only log over-engineers a feature that should rarely need debugging, B4's no-flag re-check ends up needing a cache that is just a flag by another name.

### Component C: Re-exec-after-upgrade UX

Recommendation contested between agents:
- **Tradeoffs agent**: C1 (`os.execv(sys.argv[0], sys.argv)` after upgrade) with C2 fallback (print "rerun if behavior is unexpected" and continue with old bytes).
- **Adversarial agent**: C3-equivalent (print "cortex updated; rerun your command" and `sys.exit(0)`). Eliminates execv-mid-rewrite TOCTOU and lazy-import races.

The Adversarial agent's evidence for the execv risk is strong: `sys.argv[0]` is a generated shim at `~/.local/bin/cortex` that `uv tool install --force` rewrites; an `execve(2)` opens the *path*, not the previously-held inode, so a mid-rewrite race is real. Combined with the lazy-import hazard (transitive deps in site-packages get rewritten while the running interpreter has them mmap'd), C1's correctness depends on uv's undocumented rewrite ordering. **The spec should default to C3** unless re-exec is verified against uv's actual `--force` behavior.

This is Open Question 1 below.

### Cross-cutting choices

- **Hook no-ops silently when `${CORTEX_COMMAND_ROOT}/.git` doesn't exist**: matches `cortex-scan-lifecycle.sh` early-guard pattern. No "broken flag" — just exit 0.
- **Shared lock with asymmetric semantics**: hook uses `flock -n` (skip if held); apply path uses blocking `flock -w 30`. Lock at `${XDG_STATE_HOME}/cortex-command/.lock`.
- **Flag content**: `{remote_sha}\n{checked_at_iso8601}\n{remote_url}\n{cortex_root}\n` (per Adversarial agent's recommendation 5). Apply path validates `remote_url == git remote get-url origin` AND `cortex_root == current install path` before applying — prevents stale-flag-after-uninstall.

## Adversarial Review

The Adversarial agent verified specifics on the user's actual machine (Darwin 25.4.0, APFS, `disk3s3s1` for `/`, `disk3s1` for `/Users`, shim at `~/.local/bin/cortex`):

### Verified failure modes

1. **`os.execv` mid-shim-rewrite TOCTOU is real.** `~/.local/bin/cortex` is a generated text shim with shebang line. `uv tool install --force` regenerates it. POSIX `execve(2)` opens the path freshly; mid-truncate-and-rewrite can produce `ENOEXEC`, partial shebang, or transient zero-byte content. The "kernel keeps inode alive" claim only applies to files already held open — `execv` opens the path. Tradeoffs agent's C1 glosses over this.
2. **Lazy-import races during `--force` install.** `~/.local/share/uv/tools/cortex-command/lib/python3.13/site-packages/` is the active import path; transitive deps (anyio, attrs) live there and get rewritten by `--force`. CPython opens `.py` files lazily; if `_dispatch_overnight_start` triggers `from cortex_command.overnight import cli_handler` *during* uv's mid-rewrite, you get `ImportError`, partial-byte SyntaxError, or worse.
3. **Cross-FS rename verified on the user's machine.** `/tmp` is on `disk3s3s1`; `/Users/charlie.hall/.local/state` is on `disk3s1`. `mv /tmp/foo ~/.local/state/...` crosses APFS volumes → non-atomic. Hook MUST use `mktemp -t` inside `${XDG_STATE_HOME}/cortex-command/`, never `/tmp` or `$TMPDIR`.
4. **Dev-mode predicate makes auto-update permanently inert for the dogfooding user.** This user's install IS the dev clone (`_editable_impl_cortex_command.pth` points at `/Users/charlie.hall/Workspaces/cortex-command/`). `git status --porcelain` typically shows several modified/untracked files. Spec must document this as **intended** dogfooding behavior (`CORTEX_DEV_MODE=1` is the explicit kill-switch when needed) and emit a one-time stderr note when `_dispatch_upgrade` is skipped due to dev-mode so the user is not surprised.
5. **`CORTEX_COMMAND_ROOT` discovery is unspecified.** Plugin SessionStart hooks have no guarantee that env vars are exported. The hook needs an active discovery primitive — recommended: `python3 -c "import cortex_command, pathlib; p = pathlib.Path(cortex_command.__file__).resolve().parent.parent; print(p if (p / '.git').exists() else '')"`. Spec must specify this and the failure mode (missing python? missing module? non-git directory?).
6. **Throttle-on-attempt-vs-success is unspecified.** If updated on attempt: an offline morning silences updates for 24h. If updated on success only: every offline session pays the 5s ls-remote cost. Spec must pick one explicitly. Recommended: throttle on **attempt** (avoid repeated startup-cost waste), but log offline failures to `${XDG_STATE_HOME}/cortex-command/last-error.log` for surface visibility.
7. **Half-applied state (git ok, uv fails).** Git tree is at SHA-X but installed binary is broken. Subsequent invocations see `rev-parse HEAD == SHA-X` and skip. Spec must require: success = `uv tool install` exit 0 AND a post-install verification probe (subprocess `cortex --version` in a child).
8. **Stale-flag-after-uninstall.** Flag persists after `/plugin uninstall cortex-interactive` and can point at SHA-A from a prior install. After fresh `cortex init` against a different repo, apply path could try `git pull` from a now-different repo. Mitigation: flag includes `cortex_root` and `remote_url`; apply path validates both before applying.
9. **Stale-flag-after-upstream-advance.** Hook writes `{sha=A}` at 09:00; apply runs at 14:00; `git pull --ff-only` lands at SHA-B. The "Updating cortex (...→A)" message lies. Spec must use `git rev-parse HEAD` *post-pull* for the user-facing message, not the flag content.

### Security concerns

1. **Hardcoded upstream URL = silent fork bypass.** `CORTEX_REPO_URL` defaults to `https://github.com/charleshall888/cortex-command.git` (note: ticket has typo "charleshall888" vs the correct GitHub username "charleshall888" — verify before committing). A user who forked and `uv tool install -e .` from their fork still gets *upstream's* SHA written to the flag. **Spec MUST source URL from `git -C $CORTEX_COMMAND_ROOT remote get-url origin`**, not a hardcoded constant.
2. **Auto-update is auto-RCE.** No signature check, no ref pinning. If upstream HEAD is compromised, every cortex user auto-pulls and installs. Personal-tooling blast radius is one user, but spec should acknowledge this and document the threat-model trade-off.
3. **User-global allowWrite is the first such precedent.** Spec must either propose updating `requirements/project.md` to document a new "user-global allowWrite policy" with justification, OR scope flag-file state to a per-repo path (e.g., under `lifecycle/sessions/` already allowed).
4. **Sandbox `allowWrite` only matters when cortex runs inside Claude Code.** When the user runs `cortex` from a bare shell, sandbox is not enforced and the flag-write happens unconstrained. Spec must distinguish these execution paths so the registration is documented as a defense-in-depth measure for the in-Claude-Code path, not a hard-required write permission.

### Recommended mitigations (consolidated)

1. **Default to C3 (exit and ask user to rerun) over C1 (`os.execv`)** unless re-exec is verified against uv's actual `--force` rewrite ordering.
2. **Source upstream URL from `git remote get-url origin`** at hook runtime, not a constant.
3. **Hook discovery sequence**: `python3 -c "import cortex_command; ..."`; if discovery fails, exit 0 silently.
4. **Flag schema**: `{remote_sha, remote_url, checked_at, cortex_root}`. Apply-path validates `remote_url` and `cortex_root` before applying.
5. **Throttle on attempt** (not success); log offline failures separately for morning-report visibility.
6. **`mktemp` inside `${XDG_STATE_HOME}/cortex-command/`**, never `/tmp` or `$TMPDIR`.
7. **Document dev-mode as intended-inert for the dogfooding user**; emit stderr note when skipped.
8. **Strict 1s budget on offline detection** (DNS-fail → instant skip) before falling back to the 5s timeout for slow-but-reachable cases.
9. **Post-install verification probe**: `subprocess.run([sys.argv[0], "--version"])` (or equivalent no-op subcommand) after `_dispatch_upgrade`. If exit != 0, restore flag and surface error.
10. **Frame the user-global allowWrite addition** as either an explicit ADR in spec (with justification cited against project.md's "minimal allow list") or scope state per-repo to avoid the new precedent.

## Open Questions

All items below are **Deferred to Spec phase**. Rationale: they are concrete design decisions (component-level recommendations, schema fields, error-surface locations) that the structured Spec interview is built to resolve. Each carries the research agents' default recommendation as a starting point; the Spec phase will lock them in or override based on user input.

1. **Re-exec UX (Component C)**: Tradeoffs agent recommends C1 (`os.execv` with C2 fallback); Adversarial agent recommends C3 (exit-and-rerun). The disagreement turns on uv's `--force` rewrite ordering: if uv unlinks-and-creates the shim atomically, C1 is safe; if it truncates-and-rewrites, C1 has a TOCTOU race. **Default for spec**: C3 (conservative); a follow-up ticket could verify uv's behavior empirically and switch to C1 if safe. **Deferred to Spec.**

2. **User-global allowWrite policy**: Adding `${XDG_STATE_HOME}/cortex-command/` to `sandbox.filesystem.allowWrite` is the first user-global entry. Resolution options:
   - (a) Establish a new "user-global allowWrite policy" section in `requirements/project.md` and update `settings_merge.py` semantics to document it.
   - (b) Scope flag-file state to per-repo `lifecycle/sessions/.cortex-update-pending` (already-allowed) and accept the constraint that the daily throttle becomes per-repo rather than per-user-machine.
   **Deferred to Spec** — load-bearing trade-off; user input required.

3. **Throttle on attempt vs. success**: Adversarial agent recommends attempt-based throttling with separate offline-error logging. **Deferred to Spec** to confirm and define the error-log location/format.

4. **Hook discovery primitive**: when `CORTEX_COMMAND_ROOT` is not set, the canonical discovery sequence — shell-based `python3 -c "import cortex_command..."` vs. `cortex init`-time write to a known location. **Deferred to Spec.**

5. **`CORTEX_REPO_URL` source**: hardcoded default vs. `git remote get-url origin`. Adversarial agent strongly recommends the latter to prevent fork-bypass. **Default for spec**: `git remote get-url origin`. **Deferred to Spec** for confirmation.

6. **`CORTEX_DEV_MODE=1` vs. "delete the hook" disable mechanisms**: both work; ticket lists both. **Deferred to Spec** to pick the documented recommendation for `docs/setup.md`.

7. **Help/version carve-out**: Tradeoffs agent recommends skipping the apply gate for `cortex --help`, `cortex -h`, `cortex --version`. **Default for spec**: those three; possibly extend to other O(ms) commands. **Deferred to Spec.**

8. **Failure-mode logging surface**: half-applied state and offline-throttle failures need a visible error surface. Stderr only vs. `${XDG_STATE_HOME}/cortex-command/last-error.log` vs. morning-report integration. **Deferred to Spec.**

9. **Plugin SessionStart shape**: the existing PreToolUse entry uses `${CLAUDE_PLUGIN_ROOT}` correctly. **Default for spec**: `{type: "command", command: "${CLAUDE_PLUGIN_ROOT}/hooks/cortex-probe-updates.{sh,py}", timeout: 10}`. **Deferred to Spec** to confirm matcher and timeout values.
