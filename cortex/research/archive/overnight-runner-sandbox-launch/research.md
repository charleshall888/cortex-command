# Research: Overnight runner launch from a sandboxed Claude Code session

**Date**: 2026-04-21
**Topic**: How should the overnight runner be launched and persisted when the invoking Claude Code session is sandboxed? Decide whether the current `tmux:*` in `sandbox.excludedCommands` workaround is correct, and what replaces it.

> **Revision 2** (post critical review): Earlier version recommended Option D (hand-off) as primary. Review flagged: (1) `!` prefix inherits sandbox (verified via Claude Code docs) so D-via-`!` doesn't escape; only a fully separate terminal process works — strictly worse UX than claimed. (2) Options A and D produce the same runner-subtree security posture; the only concrete delta is daytime-tmux sandboxing, which was never quantified. (3) D alone does not fix `overnight-schedule` — `caffeinate -i sleep` inside tmux still needs tmux. (4) Option F (`dangerouslyDisableSandbox: true` per-call) has the same table-stated advantages as D *plus* preserves one-button automation. (5) Option E (LaunchAgent) is the canonical scheduling answer per RQ4 and fixes a present-tense lid-close defect, not just reboot survival. Artifact now frames F and E as primary candidates, with D ruled out.

## Research Questions

1. **Threat model** → The sandbox on the runner subtree meaningfully restricts non-repo filesystem writes and network egress beyond whitelisted domains. It does **not** restrict in-repo writes (subagents commit to `$TMPDIR/overnight-worktrees/{id}/`, which is always writable). Loss of the sandbox for the runner's 6–10 hour subtree is a defense-in-depth regression — `--dangerously-skip-permissions` disables only the *permission* layer, not seatbelt's scoping. **However**: whether this protection is truly load-bearing has not been validated (see DR-2). All non-sandboxed-runner options (A, D, F) pay the same runner-subtree cost; only **Option E (LaunchAgent)** runs the scheduled runner clean without modifying the sandbox, because launchd-spawned processes do not inherit the caller's seatbelt.

2. **Scoped profile widening** → **Impossible.** macOS seatbelt inheritance is one-way: children can narrow but never widen. Nested `sandbox-exec` inside an already-sandboxed process fails with `sandbox_apply_container: Operation not permitted`. Sandbox extension SPIs (`sandbox_extension_issue`) are Apple-private.

3. **Nested Claude CLI escape** → **No blanket disable flag exists.** `sandbox.enabled: false` in nested settings does not override inherited seatbelt at the OS layer. `sandbox.excludedCommands` is the documented per-command escape hatch. The Bash tool's `dangerouslyDisableSandbox: true` parameter provides a per-invocation bypass with a user permission prompt — this is the core mechanism behind Option F.

4. **macOS scheduling primitives** → **LaunchAgent with `StartCalendarInterval` is canonical.** Survives reboot (plist persists), coalesces missed firings on wake-from-sleep (per `launchd.plist(5)`), and `launchctl bootstrap`-spawned jobs **do not inherit** the caller's seatbelt profile. `at(1)` is disabled by default and requires sudo. `caffeinate -i` prevents *only* idle sleep — **not lid-close or low-battery sleep** — so today's `overnight-schedule` is brittle in the most common laptop scenario, not merely vulnerable to reboots.

5. **Hand-off UX precedent** → Established only for *optional* work. `docs/overnight.md:31` and `skills/overnight/SKILL.md:208` cite terminal hand-off for overnight-start and the dashboard — but dashboard is *optional observability*; launch is *critical path every session*. **Verified: the `!` prefix runs commands in the same Claude Code session environment, inheriting the sandbox** (per [Claude Code interactive-mode docs](https://code.claude.com/docs/en/interactive-mode.md#bash-mode-with--prefix)). `!` is not a sandbox-escape mechanism. A working hand-off requires the user to exit Claude and paste into a genuinely separate terminal process.

6. **Observability trade-off** → **Minimal.** File-based observability (`overnight-state.json`, `overnight-events.log`, `.runner.lock`, `bin/overnight-status`, dashboard) covers everything `tmux attach` provides, except live countdown display during a scheduled delay (already written to `scheduled_start` in the state file).

7. **`excludedCommands` contract** → **Implicit, not explicit.** Current entries (`gh:*`, `git:*`, `WebFetch`, `WebSearch`) are short-lived transactional tools whose children finish within seconds. `tmux:*` is qualitatively different: its subtree runs 6–10 hours. Also — every daytime tmux usage on the machine now bypasses seatbelt, not just overnight. The present cost of keeping `tmux:*` is this daytime exposure; it is not further runner-subtree regression (all non-E options leave the runner unsandboxed anyway).

## Codebase Analysis

**Launch path** (`bin/overnight-start`, `bin/overnight-schedule`):
- Both spawn detached tmux sessions via `tmux new-session -d`. `overnight-schedule` uses `caffeinate -i sleep N` inside tmux to delay launch — which fails on lid-close sleep.
- Neither survives reboot.
- Both deployed to `~/.local/bin/` (available in any user terminal).

**Callers**:
- `skills/overnight/SKILL.md:223,296` — invokes both via Bash tool from within the sandboxed skill (Step 7 uses `AskUserQuestion` to branch run-now vs. scheduled, with time-format validation — this interactive flow lives in the skill, not in a one-line printable command).
- `docs/overnight.md:31` — instructs user to "Run `overnight-start` in a terminal" (user-facing, optional path).
- `justfile:569,599` — `overnight-run` recipes invoke `runner.sh` directly for testing.

**Sandbox-excluded commands** (`claude/settings.json:365-371`):
```json
"excludedCommands": ["gh:*", "git:*", "tmux:*", "WebFetch", "WebSearch"]
```
Documented semantics at `claude/rules/sandbox-behaviors.md:26-31` (children inherit unsandboxed status); no documented rule for what belongs in the list.

**Runner's actual write targets**:
- Worktree code edits: `$TMPDIR/overnight-worktrees/{session_id}/` — always writable.
- State & events: `lifecycle/sessions/{id}/` — in `sandbox.filesystem.allowWrite`.
- No writes outside the repo or `$TMPDIR` are required. A comprehensive `allowWrite` could potentially keep the runner sandboxed (Option G, not proposed here — see DR-2).

**Observability primitives that do NOT require tmux**:
- `overnight-state.json`, `overnight-events.log` (JSONL, tail-able), `.runner.lock` (PID for `kill -0`), `bin/overnight-status`, `just dashboard` (FastAPI at `localhost:8080`).
- Cross-repo session pointer: `~/.local/share/overnight-sessions/active-session.json`.

**No existing scheduling primitive besides tmux+caffeinate.** `Bash(launchctl *)` and `Bash(crontab *)` are both in the settings.json deny list today.

**No `!` prefix convention is documented in any skill or repo doc** — and per the interactive-mode docs above, it wouldn't help anyway: `!`-prefixed commands run in the same session and inherit the sandbox.

**`jcc` wrapper** (`bin/jcc`) is the established "run project recipes from any terminal" primitive. Supports cross-repo invocation via `CORTEX_COMMAND_ROOT`.

**Remote access pattern** (`docs/sdk.md:173`): Charlie's documented remote workflow is Tailscale + mosh + tmux — meaning Claude Code runs *inside* a tmux session on the remote Mac. "Open a separate terminal" in that topology is another tmux pane (same tmux server), not an independent terminal process.

## Web & Documentation Research

**macOS seatbelt inheritance** (authoritative, cited):
- `sandbox-exec(1)` man page: deprecated but functional. Profile loading via `-f`, `-p`, `-n`, `-D`.
- Mark Rowe, [Sandboxing on macOS](https://bdash.net.nz/posts/sandboxing-on-macos/): "Once a process is sandboxed, it is not possible for it to disable or remove the sandbox, nor is it possible for it to apply additional sandbox policies."
- [Homebrew discussion #59](https://github.com/orgs/Homebrew/discussions/59): documents `sandbox_apply_container: Operation not permitted` when xcodebuild's nested sandbox-exec hits a sandboxed parent.

**LaunchAgent as sandbox-escape primitive** (authoritative, cited):
- `launchctl(1)` (macOS 26.4): `bootstrap gui/<uid> <plist>` is the modern submission mechanism.
- `launchd.plist(5)`: `StartCalendarInterval` fires on wake-from-sleep if the interval elapsed, coalescing missed firings into one.
- [A New Era of macOS Sandbox Escapes](https://jhftss.github.io/A-New-Era-of-macOS-Sandbox-Escapes/), [Microsoft CVE-2022-26706](https://www.microsoft.com/en-us/security/blog/2022/07/13/uncovering-a-macos-app-sandbox-escape-vulnerability-a-deep-dive-into-cve-2022-26706/): `launchd`-spawned children don't inherit the caller's seatbelt because the parent is PID 1 / per-user launchd. **Architectural, not accidental.**

**Claude Code sandbox model**:
- [Sandboxing docs](https://code.claude.com/docs/en/sandboxing.md): "OS-level restrictions ensure all child processes spawned by Claude Code's commands inherit the same security boundaries."
- [Interactive-mode docs](https://code.claude.com/docs/en/interactive-mode.md#bash-mode-with--prefix): `!`-prefixed commands run in the same session environment → inherit the sandbox. **Verified during this research: `!` is not a hand-off escape.**
- No `--no-sandbox` / `CLAUDE_DISABLE_SANDBOX` flag exists. `--dangerously-skip-permissions` affects only the permission layer.
- `dangerouslyDisableSandbox: true` parameter on the Bash tool provides per-invocation bypass, prompt-gated — the mechanism behind Option F.

**Agent SDK escape route**: Runs outside sandbox *if* launched from a non-sandboxed process; inherits if launched from a sandboxed Bash call.

## Domain & Prior Art

- **Homebrew, Bazel, Nix**: treat `sandbox-exec` as strictly outer layer; pattern is "disable inner sandboxing," never widen.
- **Anthropic Agent SDK docs**: recommend containerized or separate-process execution for long-running autonomous workloads.
- **xcodebuild nested-sandbox problem**: directly analogous; kernel enforces no-widening; workaround is always "don't nest."

## Feasibility Assessment

| Approach | Effort | Reboot-survives? | Lid-close tolerant? | Runner subtree security | Daytime tmux sandbox | Launch UX |
|----------|--------|------------------|---------------------|--------------------------|-----------------------|-----------|
| **A** Keep `tmux:*` in `excludedCommands` | None | No | No (caffeinate hack) | Unsandboxed | **Bypassed (permanent)** | One-button via skill |
| **B** `/private/tmp/tmux-*` in `allowWrite` | S | No | No | Partially sandboxed (may break subagent ops) | Sandboxed | One-button via skill |
| **C** `TMUX_TMPDIR=$TMPDIR` | S | No | No | Same as B | Sandboxed | One-button via skill |
| **D** Hand-off to separate terminal | S | No (unchanged) | No (unchanged) | Unsandboxed (same as A, outside Claude context) | Sandboxed | **User exits Claude; pastes into separate terminal. `!` prefix does NOT work (inherits sandbox). Mosh+tmux remote users pay extra friction.** Resume flow pays this every cycle. |
| **E** LaunchAgent scheduling + optional wrapper | M | **Yes** (plist persists) | **Yes** (coalesces on wake) | **Unsandboxed, launchd-spawned (no seatbelt inheritance — no config bypass needed)** | Sandboxed | Skill writes plist + `launchctl bootstrap` for scheduled; needs run-now path separately |
| **F** Per-call `dangerouslyDisableSandbox: true` | S | No | No (caffeinate hack) | Unsandboxed (same as A/D at runtime) | Sandboxed | One-button via skill + one keystroke on permission prompt. Logged in session transcript. |

**Effort key**: S = <1 day, M = 1–3 days.

**Key observation**: At the runner subtree level, Options A, D, and F are equivalent — all leave the 6–10 hour subtree unsandboxed. Only Option E actually sandboxes the scheduled-path runner (via launchd's clean spawn). The differences among A/D/F are entirely in *how the concession is expressed*: permanent config edit (A), relocation outside Claude context (D), or explicit per-launch consent (F).

## Decision Records

### DR-1: `tmux:*` should not stay in `excludedCommands`

- **Context**: Including `tmux:*` in the exclusion list permanently exempts every tmux usage — daytime sessions included — from seatbelt. The other entries (`git`, `gh`, `WebFetch`, `WebSearch`) are short-lived transactional tools; `tmux` is a persistence primitive with arbitrarily long-lived subtrees.
- **What reverting actually changes**: Only the daytime-tmux exposure is closed. The overnight runner subtree remains unsandboxed under any replacement (A, D, F) except E. This is narrower than "reverting restores runner-subtree security" — which it does not.
- **Options**: keep A, replace with D/E/F.
- **Recommendation**: Revert. The daytime-tmux hole is a real defense-in-depth cost and the replacement options are tractable.
- **Trade-offs**: Must adopt F, E, or both to keep the overnight launch path working.

### DR-2: Sandbox-on-runner as load-bearing is unexamined

- **Context**: The runner's core writes target `$TMPDIR/overnight-worktrees/{id}/` (always writable) and `lifecycle/sessions/` (in `allowWrite`). A comprehensive `allowWrite` + network allowlist might permit the runner to operate under inherited sandbox (Option G, not pursued).
- **Honest caveat**: If sandbox-on-runner turns out to be essential, **only Option E** actually delivers it for scheduled launches (launchd-spawned = no inheritance). Options A, D, F all leave the runner unsandboxed, differing only in how that concession is recorded.
- **Recommendation**: Defer Option G. If a concrete threat emerges that requires sandboxing the runner subtree, E is the only non-G option that addresses it.
- **Trade-offs**: Keeps today's runner unsandboxed. The choice of A/D/F among themselves is operational, not a security change at the runner level.

### DR-3: Option D (hand-off) is off the table as a primary

- **Context**: The prior draft recommended D as primary, arguing `!` prefix + one keystroke. Review (verified against Claude Code docs) found that `!`-prefixed commands run in the same session environment and inherit the sandbox — so the `!` path does **not** achieve hand-off. Only a fully separate terminal process works.
- **Concrete costs of D with the corrected UX model**:
  - Every overnight launch requires user to exit the Claude session and paste into a separate terminal.
  - The skill's `AskUserQuestion` interactive branch (run-now vs. scheduled, time-format validation) collapses into "print one of two commands and let the user figure it out."
  - `/overnight resume` flow pays the friction every resume cycle (user is *already inside* Claude when they realize they need to resume).
  - Mosh+tmux remote workflow (`docs/sdk.md:173`) makes "separate terminal" mean "another tmux pane" — same tmux server, still needs tmux to work.
- **D does not fix scheduling**: `overnight-schedule` still spawns tmux with `caffeinate -i sleep`. Either `tmux:*` stays (contradicting DR-1) or scheduling must migrate to E. D alone cannot close the loop.
- **Recommendation**: Reject D. The corrected UX model and the scheduling gap both disqualify it.
- **Trade-offs**: None — the precedent argument (dashboard hand-off) didn't transfer (dashboard is optional; launch is critical path).

### DR-4: Option F is a legitimate primary candidate, not merely a fallback

- **Context**: Feasibility table row F: "No permanent sandbox hole," "better at audit trail." These are the exact properties the recommendation is optimizing for. F preserves one-button launch inside the skill, requires explicit per-launch consent via the documented `dangerouslyDisableSandbox: true` parameter (permission-gated, logged in session transcript), and leaves `excludedCommands` untouched.
- **F's actual costs**:
  - Permission prompt per overnight launch (one keystroke to accept).
  - Runtime runner-subtree security: same as A and D (unsandboxed).
  - Does not fix `overnight-schedule` — `caffeinate -i sleep` lid-close defect remains.
  - F handles the run-now path; E still needed for the scheduled path if tmux:* is reverted.
- **Comparison to D**:
  - Automation: F preserves; D breaks.
  - Audit trail: F prompt logged in transcript; D paste un-logged.
  - Remote-access compat: F works identically in mosh+tmux; D breaks.
  - Resume-flow cost: F none; D pays every cycle.
  - Sandbox-contract purity: equivalent (neither touches config).
- **Recommendation**: F is a strong primary for the run-now launch path. Ship F alone to unblock today without committing to E.

### DR-5: Option E is the right answer for `overnight-schedule`, and lid-close is a present-tense defect

- **Context**: `caffeinate -i` prevents *only* idle sleep. It does not block lid-close or low-battery sleep. A laptop scheduled to launch at 23:00 with the lid closing at 22:30 will fail the scheduled run — today, not hypothetically. RQ4 already returned LaunchAgent as the canonical primitive, and Assumption #5 in this artifact calls "scheduling needs tmux" explicitly **wrong**.
- **E's properties**:
  - Reboot-survive (plist persists).
  - Wake-from-sleep coalescing (per `launchd.plist(5)`).
  - Lid-close tolerant.
  - Launched process does not inherit caller's seatbelt (launchd-spawned, cleanly unsandboxed without any `excludedCommands` addition).
- **Costs**:
  - Medium effort (~1–3 days): plist template, wrapper for self-unload, test coverage for wake-coalesce edge cases.
  - Requires `~/Library/LaunchAgents/` in `sandbox.filesystem.allowWrite` and `launchctl:*` in `excludedCommands` (or equivalent scoping) so the skill can submit the plist from within the sandbox. This is a *narrower* exclusion than `tmux:*`: `launchctl` is short-lived (single command) and its children are owned by launchd, not by the caller's subtree.
- **Recommendation**: Adopt E for the scheduled path. Pairs naturally with F for the run-now path.

### DR-6: Document the `excludedCommands` contract (unchanged)

- **Context**: Without a documented rule, `excludedCommands` drifts. Backlog #081 (gpg signing) closed as "premise was wrong" partly because the contract wasn't explicit.
- **Recommendation**: Add to `claude/rules/sandbox-behaviors.md`: "`excludedCommands` is for short-lived, transactional infrastructure tools whose children complete within seconds (git operations, API queries, single `launchctl` invocations). Do not use it to bypass the sandbox for long-running subtrees (runners, daemons, interactive sessions); use a LaunchAgent handoff or per-call `dangerouslyDisableSandbox: true` for those."
- **Note**: This rule blesses `launchctl:*` (if E is adopted) as compliant — short-lived, transactional — while ruling out `tmux:*` — long-lived persistence.

## Assumptions from the prior session to flag as possibly wrong

1. **"Option B (`/private/tmp/tmux-*` in allowWrite) is functionally broken because nested Claude can't Edit arbitrary project files."** — Partially wrong. Subagents edit the worktree at `$TMPDIR/overnight-worktrees/{id}/`, which is writable under sandbox-exec by default. What breaks isn't file writes but likely subagent-invoked tools. Option B might work for some workloads and fail silently for others.

2. **"The sandbox on the runner subtree is load-bearing."** — Unexamined (see DR-2). All non-E options leave the runner unsandboxed; the choice among A/D/F doesn't change this.

3. **"`tmux:*` in `excludedCommands` is a narrow fix."** — Wrong. It's the broadest possible fix. The present cost is the *daytime-tmux* bypass, not runner-subtree regression.

4. **"Option D (hand-off) costs little UX because of dashboard precedent and the `!` prefix."** — Wrong on both counts. Dashboard is optional; launch is critical path. `!` prefix inherits the sandbox (verified). The remaining hand-off path — paste into a separate terminal process — is strictly worse UX than the original framing claimed, and breaks on mosh+tmux and on `/overnight resume`.

5. **"Scheduling needs tmux."** — Wrong. LaunchAgent with `StartCalendarInterval` is the canonical primitive, sandbox-clean when bootstrapped, and fixes a present-tense lid-close defect, not just reboot survival. Today's `overnight-schedule` is brittle in the most common laptop operating mode.

## Open Questions

- **Is a permission prompt per overnight launch acceptable UX (Option F)?** The friction is one keystroke. User judgment required — not resolvable from research.
- **Should E be adopted now (as the scheduled path), deferred, or considered the whole solution (including run-now)?** Sizing matters; user priority call.
- **Is Option G (sandbox-on-runner via comprehensive allowWrite) worth exploring?** Only if a concrete threat to the runner subtree emerges.

## Recommendation

**Adopted: F + E together.**

- **Run-now path (F)**: Revert `tmux:*` from `excludedCommands`. Update `/overnight`'s Bash-tool launch call to use `dangerouslyDisableSandbox: true`. Accept permission prompt per launch (one keystroke). Preserves skill automation, keeps the `excludedCommands` contract tight, and is prompt-gated + logged in the session transcript.

- **Scheduled path (E)**: Migrate `overnight-schedule` to a macOS LaunchAgent with `StartCalendarInterval`. The skill writes a plist to `~/Library/LaunchAgents/` and `launchctl bootstrap`s it. Requires `~/Library/LaunchAgents/` in `sandbox.filesystem.allowWrite` and `launchctl:*` in `excludedCommands` (narrow — `launchctl` is short-lived and transactional, consistent with DR-6's contract). The scheduled runner launches clean (launchd-spawned → no seatbelt inheritance), survives reboot, and is tolerant of lid-close and wake-from-sleep.

- **Supporting (DR-6)**: Document the `excludedCommands` contract in `claude/rules/sandbox-behaviors.md`. Blesses `launchctl:*` and `gh:*`/`git:*`/`WebFetch`/`WebSearch` (short-lived transactional). Rules out `tmux:*` (long-lived persistence).

Together this revises three touchpoints: `claude/settings.json` (remove `tmux:*`, add `launchctl:*` + `~/Library/LaunchAgents/`), `skills/overnight/SKILL.md` (launch via `dangerouslyDisableSandbox`; scheduled path constructs a plist), and `bin/overnight-schedule` (rewrite around `launchctl bootstrap`, retire `caffeinate -i sleep + tmux`).

**Rejected:**
- **A** — permanent daytime-tmux sandbox hole with no corresponding runner-subtree benefit.
- **B/C** — ambiguous outcomes; may fail silently mid-session.
- **D** — `!` prefix inherits sandbox (verified); "separate terminal" hand-off breaks remote workflow and resume UX, and doesn't address scheduling.
- **F alone / F-now-E-later** — not chosen; accepting the present-tense lid-close defect in `overnight-schedule` as an open gap is out of scope for this decision.
