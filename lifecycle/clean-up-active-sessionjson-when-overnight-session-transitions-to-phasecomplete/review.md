# Review: clean-up-active-sessionjson-when-overnight-session-transitions-to-phasecomplete (inline hotfix)

## Context

Retroactive read-only review of an inline bug fix that bypassed the normal `/lifecycle` review gate. The fix was filed and closed in the same session (ticket commit `9bcd3c6`, fix commit `88f4885`). No research/spec/plan artifacts exist for this item — only the backlog ticket and the commit itself.

- Commit under review: `88f4885` ("Delete active-session.json when session transitions to phase:complete (closes #134)")
- Ticket: `backlog/134-clean-up-active-sessionjson-when-overnight-session-transitions-to-phasecomplete.md`
- Files touched by the fix: `claude/overnight/runner.sh` (two identical pointer-sync blocks, lines 915-936 and 1667-1688), plus backlog index updates.

The change in both blocks: compute `new_phase = state.get('phase', data['phase'])`; if `new_phase == 'complete'`, call `pointer_path.unlink()` instead of atomic-rewrite; otherwise, atomic-rewrite with the new phase exactly as before.

## Findings by question

### 1. Correctness

**Base case is correct.** On POSIX, `Path.unlink()` invokes `unlink(2)`, which removes the directory entry immediately. If another process (e.g., the dashboard poller) happens to be holding the file open for read at the exact moment unlink runs, the kernel detaches the dentry but keeps the inode alive for the open handle; the reader finishes its syscall cleanly and the inode is freed on last-close. No leak.

**No race that leaks the file.** The pointer lives on a local filesystem under `~/.local/share/overnight-sessions/`. There is no retry loop, no `O_EXCL`-style contention, and no file-lock semantics: if the file is `exists()` true at line 921/1673 (inside the `try`), the `unlink()` is near-guaranteed to succeed. The one real loss path is `FileNotFoundError` if another writer removed it between the `exists()` check and the `unlink()` call, but that is swallowed by the bare `except Exception: pass` (pre-existing behavior) and the outcome — file absent — is the desired end state anyway.

**Re-creation risk: theoretical but not realistic in this codebase.** If a new `overnight` session started between the unlink at line 927/1679 and a downstream consumer, the consumer would see a fresh pointer for the new session. But the current code in `runner.sh` only writes the pointer once, at session startup (line 269, inside the same bash process). A subsequent session would be a *new* `runner.sh` invocation; and the Section 1650 block that contains the second sync site runs only on natural loop exit *after* the final `state.phase = complete` transition (line 908) has already taken effect, so re-writing the pointer at exit is not a path the current flow walks. **No concrete race leaks a stale complete pointer.**

One mild caveat: the `transition(state, 'complete')` on line 908 happens immediately before the 915 sync block. `state.phase` is `complete` by the time we read `STATE_PATH` on line 924, so the `new_phase == 'complete'` branch is taken on a well-ordered end-of-round-loop completion. If the completion block at 900-913 reports "N features still pending", `state.phase` stays `executing`, and the sync block correctly updates the pointer in-place — that path is also still correct.

### 2. Completeness

Inventoried via `grep -rn 'active-session\.json\|overnight-sessions/active' claude/ hooks/ bin/`:

**Write sites (runner.sh only):**
- Line 269: `pointer_path = pointer_dir / 'active-session.json'` — initial creation at session startup. `phase` is hard-coded `'executing'`.
- Line 505: in-place phase update to `'paused'` (cleanup trap, SIGINT/SIGTERM path). **Writes `phase: paused` unconditionally and does NOT delete.** This is consistent with the fix's intent: `paused` sessions remain resumable, so the pointer legitimately persists.
- Line 920: **patched** — complete-aware unlink after main-loop completion transition.
- Line 1672: **patched** — complete-aware unlink after symlink adjustment in post-session cleanup.

**Out-of-runner writer (morning-review skill):** `skills/morning-review/SKILL.md` line 48 instructs the skill to write `phase: "complete"` into the pointer file using `jq ... > ... .tmp; mv ...`. **This is an orthogonal write path that is NOT patched by the fix.** The morning-review flow runs in a fresh Claude session after the overnight runner has already exited. If a runner completes naturally, its second sync block (line 1672) deletes the pointer — so morning-review's Step 0 hits the fallback branch at SKILL.md line 30 and never touches the pointer. If a runner was paused/killed, the pointer persists at `phase: paused` or `phase: executing`, and morning-review will (per line 48) rewrite `phase: complete` onto it — **re-introducing exactly the stale-complete-pointer condition #134 targets.** This is a follow-up gap, not a regression from the current commit, but it deserves mention because the ticket's acceptance criterion ("file is absent after reaching complete") is only satisfied on the happy-path runner exit, not on the morning-review-after-interrupt path.

**Read sites:**
- `bin/overnight-status` — `phase: complete` treated as stale (see Q3).
- `claude/dashboard/poller.py` — only uses the pointer if `phase == 'executing'`; otherwise falls back to `latest-overnight`. Absent pointer hits the same fallback.
- `tests/test_daytime_preflight.py` — guard helper returns "proceed" if pointer is absent or phase is not `executing`. Safe either way.
- `skills/morning-review/SKILL.md` — explicit fallback when pointer is absent/unreadable/phase≠`executing`.

**Both runner.sh sync sites are covered.** No other runner-side write site needs the same treatment. The morning-review skill is the only external writer and represents a follow-up concern, not a completeness failure of the current fix.

### 3. Consumer compatibility

Verified by reading each consumer:

- **`bin/overnight-status` (line 41-43):** `if [[ "$phase" == "complete" ]]; then return 1; fi` — explicit fall-through to the `discover_from_sessions_dir` fallback that sorts `lifecycle/sessions/overnight-*` by name and uses the most recent. When the pointer is absent, `[[ ! -f ... ]]` at line 28 returns 1 immediately and hits the same fallback. **Behaviorally identical.** The commit body's claim is correct.

- **`claude/dashboard/poller.py` `_resolve_session_path` (line 107-118):** only returns the pointer's paths when `phase == 'executing'`. Any other phase (including missing file — `read_text()` raises FileNotFoundError, swallowed) returns the hardcoded fallback. **Behaviorally identical.**

- **`skills/morning-review/SKILL.md` Step 0 (line 29-31):** pointer check requires `phase == 'executing'` to use `state_path`; any other condition falls back to `latest-overnight`. Absent pointer hits fallback. **Behaviorally identical.**

- **`tests/test_daytime_preflight.py` `_check_overnight_guard`:** absent-file branch returns `(False, "proceed")` immediately (line 82-83). Present-with-`phase≠executing` branch also returns `(False, "proceed")` at line 95-96. **Behaviorally identical.**

No consumer distinguishes "file absent" from "file present with phase=complete" — the second case was always a degenerate form that every reader had to handle as "stale, fall through." The fix makes the degenerate form impossible on the happy path and strictly simplifies the state space.

### 4. Test coverage

The commit body acknowledges no test was added: "adding one would require a full session-completion harness." I largely agree this is reasonable, but there is a cheaper test available that is worth flagging as a follow-up:

- **Extract-helper option:** Both sync blocks are identical inline Python. Extracting them to a single `sync_pointer_phase(pointer_path, state_path)` Python function (either in `claude/overnight/state.py` or a sibling module) would (a) eliminate the duplication, (b) make the unit test trivial — four cases: phase-complete-unlinks, phase-paused-rewrites, phase-executing-rewrites, pointer-absent-noops — and (c) remove the `pointer_path.exists()` / `unlink()` TOCTOU micro-window by letting the helper use a single `try: pointer_path.unlink(missing_ok=True)` or `try: ... except FileNotFoundError: pass`.

- **No-refactor option:** A subprocess-style test that writes a pointer + a state JSON with `phase: complete`, runs a minimal `python3 -c "..."` snippet copy-pasted from the sync block, and asserts the pointer is absent afterward. This sidesteps the session-completion harness cost entirely because the sync block is already pure-Python inline that reads only `STATE_PATH` env and the filesystem. The existing `tests/test_runner_signal.py` fixture is over-scoped for this.

The acknowledged gap is reasonable *given the inline shape of the current code*, but the refactor-and-test option is cheap enough that it deserves a follow-up ticket. (This is orthogonal to whether the fix itself is correct — it is — but it reduces the "no test today" concession.)

### 5. Pattern consistency

The two sync blocks are byte-for-byte identical (~18 lines of inline Python each). The fix was applied cleanly via an exact-match edit at both sites. Threshold judgment:

- Argument for leaving it: two is the minimum arity for meaningful duplication. The blocks are small, the logic is simple, and the bash-embedded-Python shape is pervasive in this runner.
- Argument for extracting: the fact that this fix had to be applied in two places is itself evidence that future changes will also need to be applied in two places. A third sync site exists at line 505 in the `cleanup()` trap — it has a different shape (session-id guard, hardcoded `paused`), so it didn't need patching here, but if future phases get added the drift surface grows.

Given there are now three near-identical pointer-mutation sites and one delete site, I'd call this load-bearing duplication worth consolidating in a follow-up — but not a blocker for the current fix. Flag as **follow-up, not CHANGES_REQUESTED**.

### 6. Error handling

Pre-existing `try/except Exception: pass` swallows everything. The new `unlink()` call inherits this — specifically it could silently fail on:

- `PermissionError` — the pointer dir is under the user's home, so practically never, but possible if another user ran the runner via sudo.
- `FileNotFoundError` — benign; the file is already gone and the end state is correct.
- `IsADirectoryError` — only if the pointer path somehow became a directory, not realistic.
- `OSError` (disk/fs errors) — real but shared with the pre-existing atomic-rewrite path, so no net new risk.

**Failure mode that would leave the bug intact:** a silently-swallowed `PermissionError` on the unlink would leave the file with `phase: complete` on disk, exactly the state #134 describes. No event is logged — this matches the ticket's "fails silently" impact bullet. The fix does not make error handling worse, but it also doesn't improve the diagnostic surface for the very failure mode the ticket calls out.

This is **not** blocking — the silent-swallow is pre-existing and pervasive throughout the file — but the follow-up ticket below notes it as a "could be strictly better" opportunity.

### 7. Acceptance criteria match

From the ticket:

1. **"After an overnight session reaches `phase: complete`, `~/.local/share/overnight-sessions/active-session.json` is either absent OR the file's canonical path is understood by downstream tooling to mean 'the file itself is the signal of activity — absence means no runner'."**
   - **Partial PASS.** Happy-path natural-exit sessions (both sync blocks fire after `transition(state, 'complete')`) end with the pointer absent. Interrupted sessions resumed via morning-review still go through the SKILL.md line 48 rewrite, which reintroduces the stale-complete state. The clause "OR...understood as a signal" is weakly satisfied since all consumers do treat absent and complete the same.

2. **"A test covering the 'session-complete triggers active-session.json cleanup' path."**
   - **NOT MET.** Explicitly acknowledged in commit body.

3. **"No regression in session resume or status-check tools."**
   - **PASS.** `bin/overnight-status` fallback is exercised identically. Dashboard fallback is exercised identically. Morning-review fallback is exercised identically. Session resume relies on `phase: paused` (set by the cleanup trap at line 510, which the fix does not touch) and `worktree_path` in state — neither depends on the active-session pointer persisting past completion.

Two of three criteria met outright; criterion 2 is unmet but the gap is acknowledged; criterion 1 is partially met due to the orthogonal morning-review write path.

### 8. Blast radius

Per the R8b/R8c pattern documented in lifecycle `disambiguate-orchestrator-prompt-tokens-to-stop-lexical-priming-escape/spec.md` line 45 and `requirements/multi-agent.md` line 51:

> `runner.sh` is sourced once per session and its `fill_prompt()` body is held in memory for the full session lifetime; a mid-session prompt/runner skew is silently mis-substituting.

The R8b/R8c concern applies to changes that couple in-memory bash function bodies with on-disk prompt substitution tokens. This fix is different in character:

- Both patched sync blocks are **inline `python3 -c "..."` heredocs**, not bash functions. The heredoc content is re-parsed by `python3` each time the block is reached. There is no persistent in-memory shell function body holding the old substitution logic.
- The edit is **self-contained within each sync block** — no other file was changed, no prompt-template token renaming occurred, no cross-file coupling exists.
- Therefore, a mid-session deploy of this change would leave the currently-running runner executing the old sync logic (leaving stale complete pointers) until the next session starts, at which point the new logic takes over cleanly. **The failure mode R8b prevents (silent mis-substitution) does not apply here.**

However, strictly: per the project's operator-discipline rule, `runner.sh` edits are "sourced once per session" and "not re-read mid-session." So an active session would not pick up the fix. That is a missed-improvement window (the currently-running runner doesn't fix the bug for its own exit), not a correctness regression. The only observable mid-session side effect is that an active runner, after this commit has been pulled onto the worktree or home repo, will still leave one final stale pointer on its own natural exit (matching pre-fix behavior) — the very next session's startup (line 262-284) atomically rewrites the pointer with a fresh `phase: executing`, masking the prior session's residue.

**Safe to deploy while a session is active.** No mitigation window required. The fix takes effect at the next runner start.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": []}
```

## Follow-ups (optional)

1. **Morning-review skill parity (non-blocking).** `skills/morning-review/SKILL.md` line 48 currently rewrites the pointer to `phase: "complete"` via `jq`. For full alignment with ticket #134's acceptance criterion 1 on the interrupted-session path, this step should `rm -f` the pointer instead of rewriting it. Small ticket; unlocks the "pointer absent after complete" invariant everywhere.

2. **Extract pointer-sync helper (non-blocking).** Three near-identical inline Python blocks at runner.sh:505 (paused), 920 (executing/complete), and 1672 (executing/complete) would benefit from consolidation into a `claude/overnight/pointer.py` helper with a single well-tested function: `sync_pointer(pointer_path, *, new_phase: str, session_id: str | None = None)`. Delivers (a) unit tests for all four cases — complete/paused/executing/absent — which closes the commit's acknowledged test gap, and (b) a single code path to evolve when future phases or invariants are added.

3. **Surface unlink errors (non-blocking, quality-of-life).** The `except Exception: pass` pattern is pervasive; not this fix's job to cure. But if the helper extraction in #2 happens, that's the natural place to emit `log_event("pointer_sync_failed", ...)` on failure so silent-swallow doesn't leave #134's exact failure mode undiagnosable next time.

4. **Backfill a test against the helper.** If #2 is adopted, add `tests/test_pointer_sync.py` with four cases — the cost concern in the commit body ("would require a full session-completion harness") disappears once the logic is extracted from the inline heredoc.
