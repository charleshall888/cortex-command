# Research: Migrate overnight-schedule to a LaunchAgent-based scheduler

**Date**: 2026-04-21
**Ticket**: [[112-migrate-overnight-schedule-to-launchagent-based-scheduler]]
**Tier**: complex · **Criticality**: high

## Epic Reference

This ticket was decomposed from the epic at [`research/overnight-runner-sandbox-launch/research.md`](../../research/overnight-runner-sandbox-launch/research.md), which converged on **F + E together** (F = per-call `dangerouslyDisableSandbox: true` for run-now; E = LaunchAgent for scheduled). F has shipped; this ticket implements only E. This file does not re-litigate E vs. A/B/C/D/F — it focuses on the implementation-level forks within E.

## Research Questions

### RQ1: `launchctl bootstrap` semantics on macOS 26.4

- **Canonical invocation**: `launchctl bootstrap gui/$(id -u) <plist-path>`. The plist must exist on disk — there is no stdin submission mode.
- **Legacy status**: `launchctl load`/`unload` are in `launchctl(1)`'s "LEGACY SUBCOMMANDS" section; the page recommends `bootstrap | bootout | enable | disable`. `load` has started failing outright on some macOS 13.6.7+ systems. Always use `bootstrap`.
- **Exit codes**: `launchctl(1)` does not enumerate them. Practically observed: `0` success; `5` I/O error catchall (already-bootstrapped, XML syntax, `Disabled=true`); `17` file exists; `113` not found; `122` bad ownership/permissions on the plist.
- **Error surfacing is poor**: malformed plists can fail with generic error 5. Always `plutil -lint <plist>` — better, `python3 -c "import plistlib; plistlib.loads(open(p, 'rb').read())"` for schema-aware validation (adversarial Finding 6).
- **Already-bootstrapped**: re-bootstrap fails. Must `bootout` first; even then, immediate re-bootstrap of the same label can silently fail per community reports (adversarial Finding 7).
- **Verification**: `launchctl print gui/$(id -u)/<label>` — exit 0 loaded, 113 not found. Apple's man page warns the printable output is "NOT API in any sense at all" — use for interactive debugging, not scripting.

Sources: [launchctl(1) mirror](https://keith.github.io/xcode-man-pages/launchctl.1.html), [Homebrew services PR #112](https://github.com/Homebrew/homebrew-services/pull/112), [Bootstrap failed: 5 thread](https://developer.apple.com/forums/thread/665661).

### RQ2: Self-unload mechanism

The ticket's "self-unload on job completion" framing is **wrong as commonly stated**. Adversarial Finding 1 established:

- `launchctl bootout` SIGTERMs the job's entire process group (default `ExitTimeOut=20s`). `rm plist; exec launchctl bootout` from inside the job STILL kills children of the shell because they share the PGID. `disown` only removes from the shell's job table; `nohup` only blocks SIGHUP — neither changes PGID.
- `AbandonProcessGroup=true` on the plist only prevents the *launchd-side cleanup sweep* when the job exits naturally; it does not prevent explicit bootout from SIGTERMing the group.
- **Correct pattern**: the launcher script double-forks or `setsid`s the runner into a new PGID, then **exits 0 without calling bootout**. With `KeepAlive=false` (default) and no `RunAtLoad`, launchd treats the job as finished. Re-fire protection comes from `LaunchOnlyOnce=true` and the on-disk plist being removed before the next calendar match would fire.
- `LaunchOnlyOnce=true` **does exist** in `launchd.plist(5)` (contrary to the epic research's assumption). It means "once per boot" — useful as belt-and-suspenders, not alone sufficient.
- **Plist-lives-where**: placing the plist in `~/Library/LaunchAgents/` means launchd auto-scans it on next login and re-registers it (adversarial Finding 2). For a one-shot schedule, write the plist to `$TMPDIR/cortex-overnight-launch/{label}.plist` and `bootstrap` from that path. Launchd holds the in-memory registration after bootstrap; deleting the file does not unregister the job. The `~/Library/LaunchAgents/` auto-scan only applies to that directory.

**Adopted idiom** (to be refined in Spec):

```bash
#!/bin/bash
# launcher script invoked by launchd at fire time
set -euo pipefail

LABEL="$1"
STATE_PATH="$2"
TIMELIMIT="$3"

# 1. Detach the runner into its own session (new PGID, new SID)
#    so subsequent cleanup cannot signal it.
setsid nohup /usr/bin/caffeinate -i overnight-start "$STATE_PATH" "$TIMELIMIT" \
    </dev/null >>"$HOME/Library/Logs/cortex-overnight-$LABEL.out.log" \
                2>>"$HOME/Library/Logs/cortex-overnight-$LABEL.err.log" &

# 2. Remove our scheduling artifacts so we don't re-fire
rm -f "$TMPDIR/cortex-overnight-launch/$LABEL.plist"

# 3. Exit cleanly — launchd marks the job complete; no bootout needed
exit 0
```

### RQ3: Environment inheritance

Launchd-spawned agents in `gui/$UID` get `PATH=/usr/bin:/bin:/usr/sbin:/sbin` only. Homebrew (`/opt/homebrew/bin`), mise/asdf shims, `uv`, `node` are absent (adversarial Finding 14). `HOME`, `USER`, `LOGNAME` are set correctly. `TMPDIR` is per-user. `WorkingDirectory` defaults to `/`.

**`EnvironmentVariables` plist key** accepts literal strings only — no variable expansion, no globbing. The scheduler CLI must **snapshot** the user's interactive `$PATH` (plus any runner-critical env like `ANTHROPIC_API_KEY` if the runner requires it) and bake those literals into the plist at schedule time.

`ProgramArguments[0]` must be an absolute path to an executable with +x. Launchd does NOT read the shebang — it calls `execv` directly. For shell scripts, use `["/bin/bash", "/abs/path/to/launcher.sh", ...]` to be explicit.

### RQ4: Plist location and file management

- **Convention**: `~/Library/LaunchAgents/{label}.plist`, owner=user, mode `0644`, not group-writable.
- **But for this use case**: adversarial Finding 2 argues for `$TMPDIR/cortex-overnight-launch/{label}.plist` to avoid the auto-register-on-login footgun. The research sides with this: scheduled runs are ephemeral and the plist should not survive reboot.
- **Label**: reverse-DNS, per-run unique. Recommended format: `com.charleshall.cortex-command.overnight-schedule.{session_id}.{schedule_epoch}` — `{session_id}` alone is insufficient because `/overnight resume` reuses session IDs (adversarial Finding 7).
- **No stdin submission** — the plist must exist on disk before `bootstrap`.
- **Ownership/mode matter**: wrong permissions yield error 122.

### RQ5: Sandbox config decision

This is where the adversarial review produced the most important correction (Finding 19):

**`excludedCommands: ["launchctl:*"]` does NOT exempt a bash wrapper that invokes `launchctl`** — it only exempts *direct* Bash-tool invocations of `launchctl`. Per `claude/rules/sandbox-behaviors.md:26-31`: "Direct Bash invocations (`gpg ...`, `cat ~/.gnupg/...`) ARE sandboxed — this asymmetry can mislead diagnosis: git children are NOT sandboxed even though isolated Bash calls are." The rule's structure is that excluded-commands apply to commands the Bash tool invokes **directly**, and exempt that command plus its descendants. An intermediate `bash bin/overnight-schedule` layer does not qualify.

Therefore **Fork X (`launchctl:*` in `excludedCommands`) does not work with Fork B (bash wrapper)** as originally described. The coherent choices are:

- **Fork X' (excludedCommands + retire bash wrapper)**: the `/overnight` skill calls `launchctl` directly via the Bash tool. The bash wrapper is retired (Fork A for code location).
- **Fork Y (per-call `dangerouslyDisableSandbox: true`)**: symmetric with how run-now already invokes `overnight-start` today. The skill calls `overnight-schedule` (bash wrapper) with `dangerouslyDisableSandbox: true` on the Bash tool call. The wrapper itself runs unsandboxed and can freely call `launchctl`.

The research prefers **Fork Y** (see DR-2 below) because Fork B (bash wrapper) is preferred for testability and `jcc` usability (Fork 1), and Fork Y is the only sandbox-config option compatible with Fork B.

**Also**: `claude/settings.json:142` currently has `Bash(launchctl *)` in `permissions.deny`. Per adversarial Finding 3, `deny` takes precedence over `allow` and over `excludedCommands`. Any interactive call to `launchctl` is blocked by the deny rule regardless of exclusion — the deny must be narrowed or removed for the migration to work outside `dangerouslyDisableSandbox` contexts. But since Fork Y uses `dangerouslyDisableSandbox: true` (which bypasses the permission system entirely), the existing deny can stay untouched. This is a pleasant side-effect: the narrow deny continues to guard non-overnight contexts.

### RQ6: `bin/overnight-schedule` fate — wrapper vs. subsumed

Tradeoffs analysis recommended **Fork B (bash wrapper)** — rewrite `bin/overnight-schedule` internals around `launchctl bootstrap`, keep the CLI surface. Rationale:

- **Testability**: bash wrapper is testable (shellcheck + `tests/test_overnight_schedule.sh` with a stub `launchctl` on PATH). Skill steps are not.
- **`jcc` usability**: `jcc overnight-schedule 23:01` continues to work from any repo. Retiring the CLI breaks this.
- **Minimal skill diff**: `skills/overnight/SKILL.md` Step 7 changes from one bash-tool call to the same one bash-tool call; wrapper internals change.
- **Reschedule UX**: users can re-invoke the wrapper without entering Claude.
- **Error surface**: `set -euo pipefail` + explicit `echo "Error:"` idiom matches existing wrappers.

Cost: one file to keep in sync. That is the existing baseline.

### RQ7: Target-time validation reuse

`bin/overnight-schedule` lines 78-137 already handle HH:MM + ISO 8601 parsing, past-time rejection, 7-day ceiling, and "tomorrow" rollover. This logic is the most valuable reusable component of the current script. Under Fork B it stays in place; under Fork A it must be re-implemented in-skill (not testable) or extracted into a separate helper (partial retirement of the CLI).

Adversarial Finding 17 adds a validation gap: the existing logic does not defend against scheduled runs whose Month/Day combinations would re-fire annually if self-delete fails. Feb 29 on non-leap years silently never fires. Spec should add these edge-case checks.

### RQ8: `scheduled_start` state-file observability

Codebase analysis confirmed **zero current readers** of `OvernightState.scheduled_start` across dashboard templates, `status.py`, `bin/overnight-status`, orchestrator, seed, poller. The field was written by prior `bin/overnight-schedule` but never consumed. Tradeoffs — three options:

- **Drop**: remove the field from `state.py`. Minimal cost; but dashboard schedule-visibility (obvious next feature) has to re-add it.
- **Keep with no writer**: field exists but is always null. Misleading.
- **Keep and write**: wrapper writes `scheduled_start` at schedule time (atomic, per `requirements/pipeline.md:21,123`), post-bootstrap confirmation (adversarial Finding 18). Zero additional cost; field is ready for future observability work.

Research recommendation: **keep and write** (adversarial Finding 15). Cheap to maintain, premature to delete.

### RQ9: Wake-from-sleep coalescing and sleep-during-schedule

Verbatim from `launchd.plist(5)`:

> Unlike cron which skips job invocations when the computer is asleep, launchd will start the job the next time the computer wakes up. If multiple intervals transpire before the computer is woken, those events will be coalesced into one event upon wake from sleep.

This is the central correctness guarantee — coalesced to **one** event. `StartInterval` is strictly worse (loses missed fires).

**But** adversarial Finding 12 surfaces a critical counter-point: if the lid is closed at 22:45 for a 23:00 schedule, the Mac sleeps. The 23:00 fire is **queued**, not executed. When the lid opens at 08:00 the next morning, launchd fires the queued event — and the "overnight" run starts in the morning. `caffeinate -i` was solving this exact problem (keep machine awake so the scheduled run actually fires on time).

**Mitigation** (adopted in DR-5): the launcher script invokes `/usr/bin/caffeinate -i overnight-start ...` rather than raw `overnight-start`. This keeps the Mac awake for the duration of the run once the fire happens. It does NOT rescue the "sleep through the fire time" case — that remains a known limitation. Document in `docs/overnight-operations.md` as: "scheduled runs require the lid open (or clamshell-with-display) at the scheduled time; if asleep, the run fires at next wake."

Adversarial Finding 13 adds: between reboot and first user login, `gui/$UID` domain does not exist. A scheduled fire at 23:00 on a rebooted-but-not-logged-in machine slips to first login. Same failure mode as Finding 12; document same way.

### RQ10: Failure modes (silent misfires)

Top modes enumerated by web research + adversarial:

1. Wrong domain (`user/$UID` vs `gui/$UID` vs `system/`)
2. Hardcoded UID instead of `$(id -u)`
3. XML syntax errors (error 5 from bootstrap, opaque)
4. `Disabled=true` from prior `unload -w` persisting in `/var/db/com.apple.xpc.launchd/`
5. `ProgramArguments[0]` not executable (mode 0644 not 0755) — launchd uses `execv`, no shebang
6. Relative paths (`WorkingDirectory` defaults to `/`)
7. PATH not set — first `claude` / `git` / `uv` call fails "command not found"
8. Wrong plist ownership/permissions (error 122)
9. `EnvironmentVariables` assumed to expand — it doesn't
10. Schema typos (`StartCallendarInterval` — lint passes, bootstrap succeeds, job never fires)
11. TCC-protected paths (adversarial Finding 11 — launchd-spawned TCC subject is the binary, not the user's Terminal)
12. `Year` key missing from `StartCalendarInterval` — plists fire annually if stale (adversarial Finding 2)
13. `ExitTimeOut` killing the runner if launcher calls bootout (adversarial Finding 1)
14. SSH-session scheduling fails — `gui/$UID` unreachable (adversarial Finding 5)
15. Reboot between schedule and fire leaves plist in `~/Library/LaunchAgents/` for auto-register (adversarial Finding 2)
16. Concurrent schedule + run-now with no cross-cancellation (adversarial Finding 10)
17. Resume-after-schedule reuses the same session_id → same label → `bootstrap-after-bootout` silent failure (adversarial Finding 7)
18. `plutil -lint` passes schema typos (adversarial Finding 6)

## Codebase Analysis

### Files that will change

- **`bin/overnight-schedule`** (205 lines): internals rewritten around `launchctl bootstrap`. Target-time validation (lines 78-137) preserved. `__launch` re-entrant branch (lines 20-45) and `caffeinate -i sleep` deleted. `scheduled_start` state-file write (lines 148-167) preserved, sequenced AFTER confirmed bootstrap.
- **`skills/overnight/SKILL.md`** Step 7 (lines 212-237): schedule branch updated; command stays `overnight-schedule <target-time> <state-path> <time-limit>` invoked with `dangerouslyDisableSandbox: true`. Confirmation output text changes from "tmux session `overnight-scheduled`" to "LaunchAgent label `com.charleshall.cortex-command.overnight-schedule.{session_id}.{epoch}`". Success criterion #6 at line 318 wording adjusted.
- **`claude/settings.json`**: `Bash(launchctl *)` deny entry (line 142) stays. No `excludedCommands` change. No `sandbox.filesystem.allowWrite` change (plist writes go to `$TMPDIR` which is already writable).
- **`justfile`**: `overnight-schedule` recipe (605-607), `setup-force`, `deploy-bin`, `check-symlinks` entries all remain — Fork B keeps the bin wrapper.
- **`docs/overnight-operations.md`** lines 218-226: rewrite the "Scheduled Launch subsystem" section. Document LaunchAgent mechanism, plist ephemeral-in-TMPDIR location, log file location, cancel path (new `bin/overnight-cancel`).
- **`docs/overnight.md`**: Command Reference section — optional addition of `overnight-schedule` and `overnight-cancel` to the user-facing command list.
- **`claude/overnight/state.py`**: `scheduled_start` field (lines 193-195, 214, 342) retained. No change.

### Files that will be created

- **`bin/overnight-cancel`** (deploy-bin pattern): new CLI, symmetric with start/schedule/status.
  - `overnight-cancel` (no args): list active cortex-command scheduled plists (scan `$TMPDIR/cortex-overnight-launch/` + sidecar index), interactive select.
  - `overnight-cancel {session_id}`: targets that specific schedule.
  - Does: `launchctl bootout gui/$(id -u)/<label>`, `rm <plist>`, clear `scheduled_start` in state file.
- **Launcher script** — `claude/overnight/overnight-launcher.sh` (or similar, inside the repo): the `ProgramArguments` target that launchd invokes at fire time. Double-forks the runner via `setsid nohup ... & disown`, wraps in `caffeinate -i`, removes its own plist, exits cleanly.
- **Plist template** — `claude/overnight/overnight-launch.plist.template`: Python-string-format-substituted at schedule time. No static deploy; rendered fresh per schedule.
- **Sidecar index** — `~/.cache/cortex-command/scheduled-launches.json`: append-only map `{label: {session_id, plist_path, scheduled_for_iso}}`. Needed for `overnight-cancel` without args (adversarial Finding 9).

### Files that could be deleted

None under Fork B. Under Fork A (rejected) we would remove `bin/overnight-schedule`, its justfile recipe, and its `setup-force`/`deploy-bin`/`check-symlinks` entries.

### Current convention for bin/ CLI scripts

- Shebang: `#!/usr/bin/env bash` + `set -euo pipefail`.
- Header: one-line tagline, `Usage:`, `Examples:`, positional-syntax rule for overnight scripts.
- Argument validation: guards against `--flag=value`; print positional-syntax example on error.
- `deploy-bin` three-step contract (justfile:132-143, :46-55, :750-757): (1) `pair` line in `deploy-bin`, (2) same in `setup-force`, (3) `check ~/.local/bin/<name>` in `check-symlinks`. All three listed explicitly as "also update X" in the justfile.

### `scheduled_start` consumers (authoritative)

Writer: only `bin/overnight-schedule`. Storage: `claude/overnight/state.py` dataclass field + `load_state`. Readers: **zero production consumers** across `claude/**/*.py`, dashboard templates, `bin/overnight-status`, `claude/overnight/status.py`, seed, poller. The field round-trips via `dataclasses.asdict()` in `save_state()`.

### Skill integration surface

`skills/overnight/SKILL.md` Step 7 (lines 212-237) is the only integration point. The skill computes session_id (via `bootstrap_session` in Step 2), absolute state-file path, and time-limit string. The skill asks the user (run-now vs. schedule), then invokes the Bash tool with `dangerouslyDisableSandbox: true`. Success criterion #6 (line 318) names both commands.

### Test-harness entry points

**None** — `tests/` has zero matches for `overnight-schedule`, `scheduled_start`, `caffeinate`, `StartCalendarInterval`, `LaunchAgent`, `launchctl`, `plist`, or `ProgramArguments`. Greenfield. Migration introduces `tests/test_overnight_schedule.sh` (bash wrapper) and/or `tests/test_overnight_schedule.py` (plist generation via Python's `plistlib`).

### Deploy convention gotchas

- Plists are **real files**, not symlinks — launchd has issues with symlinked agents. But we're placing the plist in `$TMPDIR/` per-schedule (ephemeral), not `~/Library/LaunchAgents/`, so the symlink concern doesn't apply.
- `~/Library/LaunchAgents/` intentionally stays out of `sandbox.filesystem.allowWrite`. Scheduled plists live in `$TMPDIR` (already writable).
- `bin/jcc` integration preserved under Fork B.

### Notable absences / greenfield

- No existing plist, no existing `launchctl` invocation, no existing LaunchAgent convention in the repo. This ticket establishes the pattern.
- No plist deploy machinery needed (plists are ephemeral per schedule, not static deploy).
- No prior scheduling test harness.

## Web & Documentation Research

Authoritative sources used (all URLs):

- **`launchctl(1)`**: <https://keith.github.io/xcode-man-pages/launchctl.1.html> — bootstrap/bootout canonical syntax, deprecation of load/unload, "NOT API" warning on print output.
- **`launchd.plist(5)`**: <https://keith.github.io/xcode-man-pages/launchd.plist.5.html> — `StartCalendarInterval` wake-coalesce guarantee (verbatim quoted in RQ9), `LaunchOnlyOnce`, `AbandonProcessGroup`, `KeepAlive` defaults, `EnvironmentVariables` semantics, `ExitTimeOut` default 20s.
- **Microsoft Security Blog — CVE-2022-26706**: <https://www.microsoft.com/en-us/security/blog/2022/07/13/uncovering-a-macos-app-sandbox-escape-vulnerability-a-deep-dive-into-cve-2022-26706/> — "Since launchd creates the process, it's not restricted by the caller's sandbox." Architectural, not accidental.
- **A launchd Tutorial**: <https://www.launchd.info/> — PATH default, file permissions, `ProgramArguments` shebang-not-read semantics, `EnvironmentVariables` no-expansion behavior.
- **Homebrew services PR #112**: <https://github.com/Homebrew/homebrew-services/pull/112> — real-world migration from `load -w` to `bootstrap`, rationale (better error reporting).
- **Bootstrap failed: 5 thread**: <https://developer.apple.com/forums/thread/665661> — community catalog of error-5 causes.
- **Scheduling Timed Jobs (Apple archived docs)**: <https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html> — "if the machine is off when the job should have run, the job does not execute until the next designated time occurs." Wake-coalescing rescues sleep, not power-off.
- **"Launchctl 2.0 Syntax"** (babodee): <https://babodee.wordpress.com/2016/04/09/launchctl-2-0-syntax/> — domain target semantics.
- **JAMF community thread on self-unload**: <https://community.jamf.com/t5/jamf-pro/policy-not-running-correctly-when-called-from-launchdaemon/m-p/294936> — empirical confirmation that `launchctl bootout` SIGTERMs the job's subtree.
- **"Where is my PATH, launchD?"** (lucaspin on Medium): <https://lucaspin.medium.com/where-is-my-path-launchd-fc3fc5449864> — minimal PATH default for gui-domain agents.
- **"Accessing the macOS GUI in Automation Contexts"**: <https://aahlenst.dev/blog/accessing-the-macos-gui-in-automation-contexts/> — SSH sessions don't have `gui/` domain reliably.

## Requirements & Constraints

Relevant constraints (quoting the authoritative file:line):

- `requirements/project.md:32` — **Defense-in-depth for permissions**: "sandbox configuration is the critical security surface for autonomous execution."
- `requirements/project.md:25` — **File-based state only**: all state in plain files; no database.
- `requirements/pipeline.md:21, :123` — **Atomic state writes**: tempfile + `os.replace()`; partial-write corruption is not possible.
- `requirements/pipeline.md:131` — **No locks on state file**: writers use atomic replace; readers may observe mid-mutation; forward-only phase transitions make this safe.
- `requirements/remote-access.md:44-49` — tmux is tagged "subject to change" for session persistence; retiring tmux from scheduling does not violate requirements.
- `CLAUDE.md:60` — **docs source-of-truth**: `docs/overnight-operations.md` owns scheduling behavior. Do not duplicate.
- `claude/rules/sandbox-behaviors.md:33-39` (DR-6, already applied): `excludedCommands` is for "short-lived, transactional infrastructure tools whose children complete within seconds (git operations, API queries, single `launchctl` invocations)." Names `launchctl` explicitly; names `tmux` as non-compliant.
- `claude/rules/sandbox-behaviors.md:26-31` — **excluded-commands subtree asymmetry**: children of *direct* Bash-tool invocations of an excluded command bypass the sandbox; children of wrapper scripts that internally call the excluded command do NOT. This is the rule underlying adversarial Finding 19.
- `claude/rules/sandbox-behaviors.md:20-24` — **Global allow list minimality**: the `settings.json` allow list applies across ALL projects; read-only allows are safe globally, write operations should fall through to prompt.
- `requirements/observability.md:85` — dashboard/statusline/status CLI are **read-only** w.r.t. session state; cannot write `scheduled_start`.

Ticket scope boundaries (verbatim from `backlog/112`):

- **IN**: survive reboot; tolerate lid-close and wake-from-sleep; launch sandbox-clean (launchd parent, no seatbelt inheritance); retire `caffeinate -i sleep + tmux`.
- **OUT**: run-now path (F done); sandbox-on-runner (DR-2 deferred); reboot-recovery of in-flight sessions.

## Feasibility Assessment — Fork A vs. Fork B

| Dimension | Fork A (skill-embedded) | Fork B (bash wrapper) |
|---|---|---|
| `skills/overnight/SKILL.md` edit surface | +40 lines embedded plist + launchctl logic in Step 7 | ~5 lines (command name + args, confirmation text) |
| Testability | None — SKILL.md step not executable in tests | Bash wrapper + Python plist module unit-testable; stub `launchctl` on PATH |
| `jcc` cross-repo usability | Broken — scheduling only via `/overnight` | Preserved — `jcc overnight-schedule 23:01 ...` works from any repo |
| Reschedule UX | Re-enter `/overnight` (re-run Step 2 index regen, etc.) | Direct wrapper re-invocation |
| Error surface | Skill-level prose error handling | `set -euo pipefail` + explicit `echo "Error:"; exit 1` (consistent with sibling scripts) |
| `scheduled_start` write reuse | Re-implement in skill | Preserved in wrapper (lines 148-167) |
| Sandbox config compat | Only Fork X' (launchctl:* in excludedCommands, skill calls launchctl directly) | Only Fork Y (per-call `dangerouslyDisableSandbox: true`) |
| Interaction with `bin/overnight-cancel` (Fork 5 — new CLI) | Incongruous (retire CLI on schedule, add CLI on cancel) | Symmetric (start/schedule/status/cancel quartet) |

**Recommendation**: **Fork B (bash wrapper)**. The testability and `jcc` arguments are decisive; Fork A trades non-trivial validation logic (past-time, 7-day ceiling, format parsing, tomorrow-rollover) and plist rendering for un-exercised skill-level prose. The Fork 1/Fork 5 coherence argument reinforces it.

## Decision Records

### DR-1: Fork B (bash wrapper) for code location

- **Context**: Fork A (skill-embedded, retire CLI) vs. Fork B (rewrite wrapper).
- **Decision**: Fork B.
- **Rationale**: Testability + `jcc` + minimal-skill-diff (Feasibility table above). Symmetric with existing `bin/overnight-start`, `bin/overnight-status`. Preserves `jcc overnight-schedule` usage from other repos.
- **Trade-off**: one more file to keep aligned with SKILL.md's description — the existing baseline, not a regression.

### DR-2: Per-call `dangerouslyDisableSandbox: true` (Fork Y)

- **Context**: Adversarial Finding 19 showed `excludedCommands: ["launchctl:*"]` does NOT exempt `bin/overnight-schedule` (a bash wrapper that internally calls `launchctl`) — only direct Bash-tool `launchctl` calls.
- **Decision**: Skill invokes `overnight-schedule` with `dangerouslyDisableSandbox: true` on the Bash tool call. Symmetric with `overnight-start`'s run-now pattern.
- **Rationale**:
  - Only option compatible with Fork B (DR-1).
  - Prompt-gated in interactive contexts (one keystroke); silent in overnight `--dangerously-skip-permissions` contexts (which scheduling isn't used from).
  - Logged in session transcript (audit trail better than a silent config entry — adversarial Finding 4).
  - `claude/settings.json:142` `Bash(launchctl *)` deny can stay untouched; it continues to guard non-overnight `launchctl` calls across the machine.
  - No `sandbox.filesystem.allowWrite` addition needed — the wrapper runs unsandboxed and writes the plist to `$TMPDIR` (already writable) without needing `~/Library/LaunchAgents/` exemption.
- **Trade-off**: one prompt per schedule. Scheduling is infrequent (≤ once per day in practice). Acceptable.

### DR-3: Plist in `$TMPDIR`, not `~/Library/LaunchAgents/`

- **Context**: Adversarial Finding 2 identified that plists in `~/Library/LaunchAgents/` auto-register on next login. A plist whose self-delete failed (power loss, `rm` error, script kill) becomes an annual zombie because `StartCalendarInterval` has no `Year` sub-key.
- **Decision**: write plist to `$TMPDIR/cortex-overnight-launch/{label}.plist`. `launchctl bootstrap $TMPDIR/...` registers launchd's in-memory descriptor. Deleting the file after successful bootstrap does NOT unregister the job.
- **Rationale**: `$TMPDIR` is ephemeral (cleared per-boot on macOS); no auto-scan-and-re-register path; symmetric with the repo's existing `TMPDIR`-for-ephemeral convention. Avoids needing `~/Library/LaunchAgents/` in `sandbox.filesystem.allowWrite`.
- **Trade-off**: a reboot between schedule and fire drops the schedule entirely. This is **correct**: the session plan probably changed; re-scheduling after reboot is the right user action. `caffeinate -i` wrapping (DR-5) keeps the machine awake during the run; the reboot-loss case only applies to long leads (>= hours).

### DR-4: Exit-cleanly launcher, no self-bootout

- **Context**: Adversarial Finding 1 showed `launchctl bootout` SIGTERMs the process group; `rm plist; exec bootout` still kills the runner regardless of `disown`/`nohup` because PGID is shared.
- **Decision**: Launcher script uses `setsid nohup /usr/bin/caffeinate -i overnight-start ... &` (new PGID, new SID, reparented to init), then `rm` the plist, then `exit 0`. No `bootout`. Launchd treats the job as finished on natural exit (`KeepAlive=false` default). `LaunchOnlyOnce=true` on the plist adds belt-and-suspenders against a same-boot re-fire race.
- **Rationale**: Only pattern that makes the runner actually survive the launcher's completion. Matches widely-used "one-shot scheduled LaunchAgent" idioms from Homebrew services and JAMF-community discussions.
- **Trade-off**: if the launcher is killed between fork and `rm`, the plist survives in `$TMPDIR`. Since `$TMPDIR` is ephemeral, the plist is gone after reboot. Acceptable failure mode.

### DR-5: Launcher wraps runner in `/usr/bin/caffeinate -i`

- **Context**: Adversarial Finding 12 showed `StartCalendarInterval` defers fire if the machine is asleep at the calendar time — lid-close is NOT tolerant in the sense of "runs at 23:00 regardless." It's "runs at next wake after 23:00."
- **Decision**: Launcher invokes `/usr/bin/caffeinate -i overnight-start ...` not raw `overnight-start`. Keeps the machine awake for the duration of the run ONCE IT STARTS.
- **Rationale**: Preserves the original `caffeinate` property that's still valuable (run completes without sleep interruption). Does not rescue the pre-fire-sleep case — but the user can hold the lid open at schedule time, same as today.
- **Trade-off**: a 6h run with lid closed relies on AC power. Document this constraint in `docs/overnight-operations.md`. "Tolerate lid-close" in the ticket's Desired Outcome needs a precise caveat — see Open Questions.

### DR-6: Per-schedule-epoch label format

- **Context**: Adversarial Finding 7 showed `bootstrap` immediately after `bootout` of the same label can silently fail. `/overnight resume` re-uses session IDs — reusing session_id-only label would hit this.
- **Decision**: Label format `com.charleshall.cortex-command.overnight-schedule.{session_id}.{epoch_seconds}`. Never reuse a label.
- **Rationale**: Collision-safe; `overnight-cancel` can list all cortex-command schedules by grepping `$TMPDIR/cortex-overnight-launch/`. Adversarial Finding 9's "symmetric CLI" concern mitigated by the sidecar index file.
- **Trade-off**: label is longer; minor.

### DR-7: Sidecar index `~/.cache/cortex-command/scheduled-launches.json`

- **Context**: Adversarial Finding 9 — `overnight-cancel` without args needs to enumerate active schedules. `launchctl list` output is not machine-parseable API; `$TMPDIR/cortex-overnight-launch/*.plist` glob works but misses the mapping to session_id / human-readable target time.
- **Decision**: Schedule command appends `{label, session_id, plist_path, scheduled_for_iso}` to a JSON array; cancel command reads, acts, rewrites. Atomic writes (tempfile + replace) per `requirements/pipeline.md:21`.
- **Rationale**: Small, local, consistent with file-based-state philosophy (`requirements/project.md:25`).
- **Trade-off**: stale entries if the user manually `rm`s plists. Add `overnight-cancel --reap` to prune.

### DR-8: `/overnight` skill cancels prior schedules before run-now

- **Context**: Adversarial Finding 10 — user schedules 23:00, then at 20:00 invokes `/overnight` run-now. At 23:00 a second runner fires concurrent with the first. Overnight sessions sharing state = data corruption.
- **Decision**: `skills/overnight/SKILL.md` adds a pre-flight step (before Step 6 or inside Step 7): check for pending scheduled plists (via `overnight-cancel --list` or sidecar index). If any exist, prompt the user: cancel them, keep them (abort the new invocation), or proceed (both; only if user explicitly chooses).
- **Rationale**: Prevents the silent-concurrency failure mode. Low cost (one AskUserQuestion on a normally-empty condition).
- **Trade-off**: skill gets slightly longer. Acceptable.

### DR-9: `scheduled_start` kept and written

- **Decision**: Keep `claude/overnight/state.py:214` field; wrapper writes it post-bootstrap-confirmation; clear it from the launcher at fire time (same as current `__launch` branch clears it).
- **Rationale**: Zero runtime cost (field already exists). Ready for any future dashboard schedule-visibility feature. Removing it now = re-adding it shortly.

### DR-10: Schema-aware plist validation via `plistlib` (belt-and-suspenders `plutil -lint`)

- **Context**: Adversarial Finding 6 — `plutil -lint` validates XML syntax, not plist schema. A `StartCallendarInterval` typo passes lint and silently breaks the schedule.
- **Decision**: Wrapper uses `python3 -c "import plistlib; plistlib.loads(open(p, 'rb').read())"` for structural validation (stricter than `plutil -lint`). After `bootstrap`, run `launchctl print gui/$(id -u)/<label>` and grep for `state = waiting` to confirm registration. Only after this confirmation, write `scheduled_start` to the state file.
- **Rationale**: Post-bootstrap verification is the authoritative signal. Lint-alone gates are insufficient.
- **Trade-off**: a few hundred ms per schedule for validation. Negligible.

## Adversarial Review (synthesis)

20 findings from the adversarial pass; the three most consequential were integrated into DR-2, DR-3, DR-4, DR-5, DR-8, DR-10 above. Summary of severities:

**Catastrophic** (invalidated the originally-recommended approach):
1. `bootout` kills the runner's process group regardless of `rm`/`exec` ordering (→ DR-4 exit-cleanly launcher)
2. `excludedCommands: ["launchctl:*"]` does NOT exempt a bash wrapper's internal `launchctl` calls (→ DR-2 per-call `dangerouslyDisableSandbox`)

**Major** (shaped specific decisions):
3. `~/Library/LaunchAgents/` plists auto-register on login → annual zombie if self-delete fails (→ DR-3 `$TMPDIR` placement)
4. `excludedCommands` silent vs. `dangerouslyDisableSandbox` transcript-logged (→ DR-2)
5. `gui/$(id -u)` unreachable from SSH — `user/$UID` fallback needed (→ Open Question)
6. `plutil -lint` doesn't catch schema typos — `plistlib` or post-bootstrap verify required (→ DR-10)
7. `bootout` → immediate `bootstrap` of same label silently fails — never reuse labels (→ DR-6)
8. `permissions.deny` takes precedence over `excludedCommands` — three-way confusion (→ DR-2 sidesteps by using `dangerouslyDisableSandbox`)
9. `StartCalendarInterval` defers fire on sleep; lid-close tolerance is partial (→ DR-5 `caffeinate -i` wrap, Open Question re-scopes the ticket's outcome wording)
10. No cross-cancel between scheduled and run-now paths (→ DR-8 skill pre-flight)
11. TCC Full Disk Access bound to binary, not user — silent EPERM mid-run (→ Open Question)
12. `EnvironmentVariables` needs literal PATH baked at schedule time (→ Open Question)
13. Run-now (tmux) vs. scheduled (launchd) UX fragmentation (→ Open Question)

**Minor** (nice-to-have, defer to Spec):
14. Feb 29 non-leap silent never-fires; stale re-fire protection (→ Open Question)
15. `scheduled_start` premature removal (→ DR-9 keep it)
16. `launchctl` PATH-stubbing test fidelity concerns (→ Open Question)
17. `overnight-cancel` per-run label discovery (→ DR-7 sidecar index)
18. Bootstrap/state-write atomicity (→ DR-10 confirm-before-write)
19. `plutil` availability / hardened-runtime edge cases (→ low risk, DR-10 mitigates via `plistlib`)

## Open Questions

To be resolved in Spec:

- **OQ1: SSH session fallback**. When the user runs `claude` over SSH without a loginwindow Aqua session, `gui/$(id -u)` is unreachable (adversarial Finding 5). Should the wrapper detect `$SSH_CONNECTION` and fall back to `user/$UID` domain? `user/` domain exists in all sessions but has different sleep/wake-hook semantics. Alternative: reject SSH scheduling with a loud error and require the user to schedule from a local session. Decision pending — needs spec's user-requirements-interview phase.

- **OQ2: Ticket outcome wording — "tolerate lid-close"**. The ticket's Desired Outcome says "Tolerate lid-close and wake-from-sleep (calendar-interval coalescing)." Research confirms coalescing is correct — but a fire deferred to next wake is not "tolerated" in the user's operational sense (adversarial Finding 12). Spec should clarify: does "tolerate lid-close" mean "survives lid-close at schedule-time" (partially true — the fire slips to next wake) OR "scheduled runs complete even if lid closed at start time" (stronger, requires AC power + lid-stay-open)? The spec needs the user's intent here.

- **OQ3: PATH/env capture at schedule time**. `EnvironmentVariables` requires literal strings. Which env vars does the runner actually depend on? PATH must include `/opt/homebrew/bin`, `~/.local/bin`, and any mise/asdf shims. What about `ANTHROPIC_API_KEY`, `CLAUDE_CONFIG_DIR`, `CORTEX_COMMAND_ROOT`? Spec should enumerate the minimal env set by reading `runner.sh` + `overnight-start`.

- **OQ4: TCC prompt gap**. Adversarial Finding 11: launchd-spawned processes have a different TCC subject (the binary, not the Terminal). If the runner hits any TCC-protected path, it EPERM's silently mid-run. Which paths matter? `lifecycle/sessions/`, `git` operations, `claude` API calls, anything under `~/Documents` / `~/Desktop`. Spec should include a pre-flight TCC probe (stat + write test in each critical path) and loud failure if any fail.

- **OQ5: Runner UX fragmentation — tmux for run-now vs. launchd for scheduled**. Adversarial Finding 16: `overnight-status` / attach / cancel flows differ between the two paths. Options: (a) rely on `bin/overnight-status` reading state files (works for both — check whether current `overnight-status` works without tmux); (b) launchd-spawned runner also creates a tmux session inside itself (preserves current attach UX); (c) migrate run-now to launchd too (out of ticket scope). Spec should decide.

- **OQ6: Feb 29 validation**. Adversarial Finding 17. Should the wrapper reject Feb 29 scheduling outright or accept with a warning? Low frequency but loud-failure preference argues for outright reject. Deferred: will be resolved in Spec.

- **OQ7: Test surface scope**. Plist rendering (Python `plistlib`) and target-time validation (bash) are unit-testable. Bootstrap-then-fire is integration-only (requires real launchd). Should the spec include an integration smoke test (schedule 5-minutes-out, observe fire) marked macOS-only? Deferred: will be resolved in Spec.

- **OQ8: `bin/overnight-cancel` scope**. Tradeoffs recommends a new CLI. How much does it do beyond `bootout + rm + clear-state`? Should it handle stale-plist reaping (`--reap`)? List-active (`--list`)? Sidecar-index rebuild? Spec should define the full CLI surface.

- **OQ9: Launcher script location in repo**. `claude/overnight/overnight-launcher.sh` vs. `bin/overnight-launcher.sh` vs. generated per-schedule in `$TMPDIR`. Affects deploy-bin behavior, justfile symlink targets, and how the plist's `ProgramArguments` references it. The launcher itself is small (~20 lines); in-repo is fine. Spec decides the exact path.

- **OQ10: `docs/overnight-operations.md` rewrite scope**. The "Scheduled Launch subsystem" section needs a rewrite. How much detail about the plist format, the launchd mechanism, the TCC/SSH/caffeinate caveats should be there vs. in a separate doc? Per `CLAUDE.md:60` docs-source-of-truth rule, all scheduling content goes in `overnight-operations.md`. Spec decides the outline.
