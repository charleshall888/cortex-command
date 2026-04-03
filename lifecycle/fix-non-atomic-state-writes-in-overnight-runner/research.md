# Research: Fix non-atomic state writes in overnight runner

## Epic Reference

Background research at `research/harness-design-long-running-apps/research.md` covers the broader overnight harness design. This ticket addresses the four specific reliability gaps identified there: non-atomic writes to `overnight-state.json`, `batch-{N}-results.json`, `escalations.jsonl`, and `recovery_attempts`.

---

## Codebase Analysis

### Files That Will Change

**1. `claude/overnight/prompts/orchestrator-round.md`**
Contains pseudocode at Steps 0d, 3c, and 4a that writes `overnight-state.json` via `Path(...).write_text(json.dumps(state, indent=2))`. Multiple escalation append calls also use raw `open(..., "a")` without fsync (lines 101, 128, 144). The fix requires replacing these pseudocode instructions to direct the agent to call `save_state()`, `update_feature_status()`, and the fsync-safe `write_escalation()` instead.

**2. `claude/overnight/batch_runner.py`**
- Lines ~1956–1963: writes `batch-{N}-results.json` via `result_path.write_text(json.dumps(...))` — non-atomic
- Lines 1920–1931: loads state, updates `recovery_attempts` per-feature, calls `save_state()` — but only at end-of-batch; a mid-batch kill loses all increments from that batch

**3. `claude/overnight/deferral.py`**
- `write_escalation()` (lines 355–382): appends to `escalations.jsonl` via `open(..., "a")` without `f.flush()` or `os.fsync()` — a crash after write but before the OS flushes to disk silently loses the escalation record

### Existing Atomic Write Pattern: `save_state()` (state.py:336–376)

This is the authoritative pattern to replicate for JSON writes:

```python
fd, tmp_path = tempfile.mkstemp(dir=state_path.parent, prefix=".overnight-state-", suffix=".tmp")
closed = False
try:
    os.write(fd, payload.encode("utf-8"))
    os.close(fd)
    closed = True
    os.replace(tmp_path, state_path)
except BaseException:
    if not closed:
        try: os.close(fd)
        except OSError: pass
    try: os.unlink(tmp_path)
    except OSError: pass
    raise
```

Key elements: `tempfile.mkstemp(dir=target.parent)` (same filesystem), `os.write()` (not `write_text`), explicit `os.close()` before `os.replace()`, full cleanup on `BaseException`.

**Critical finding (adversarial)**: `save_state()` and the existing `atomic_write()` helper in `claude/common.py:273–312` both omit `f.flush()` / `os.fsync()`. They are atomic (tempfile+replace) but not durable — a crash after `os.replace()` but before the OS write-back cache is flushed to disk can still lose data. This is a pre-existing gap across all three write helpers.

### Integration Points

- `state.py` exports: `save_state()`, `update_feature_status()`, `load_state()`, `OvernightFeatureStatus` (which has `recovery_attempts: int`)
- `deferral.py` exports: `write_escalation()`, `EscalationEntry`
- `claude/common.py` exports: `atomic_write()` — already available but not used by `save_state()` or batch results
- `batch_runner.py` already imports `save_state()` and calls it at other points (lines 1560, 1942)
- `map_results.py`'s `TestMissingResultsFallback` already handles truncated/missing batch results gracefully — partial mitigation exists

### recovery_attempts Tracking Detail

`recovery_attempts` is already tracked per-feature in a local dict (`recovery_attempts_map`, keyed by feature name). The per-feature granularity is correct; only the save-back is batched at end-of-run. Moving the save to per-feature requires calling `load_state() → increment → save_state()` immediately after dispatch — this is a read-modify-write that must be done carefully to avoid the same race window shifting rather than closing.

---

## Web Research

### Canonical Atomic Write Pattern (Python stdlib)

```python
import os, tempfile
fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())   # flush kernel buffer to storage before rename
    os.replace(tmp_path, target)
except:
    try: os.unlink(tmp_path)
    except OSError: pass
    raise
```

### os.replace vs os.rename

`os.replace()` is the correct choice. On Unix/macOS both wrap POSIX `rename(2)` (guaranteed atomic by the kernel). On Windows, `os.rename()` raises `FileExistsError` if the target exists; `os.replace()` handles it correctly. Use `os.replace()` exclusively.

### fsync for JSONL Appends

For `escalations.jsonl` (append-only, not temp+replace):

```python
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(record) + "\n")
    f.flush()          # Python buffer → OS kernel buffer
    os.fsync(f.fileno())   # OS kernel buffer → physical storage
```

`f.flush()` before `os.fsync()` is mandatory. Calling `os.fsync()` without `f.flush()` first is a silent no-op — the Python-buffered data was never sent to the kernel.

### macOS: F_FULLFSYNC Consideration

On macOS, `os.fsync()` calls `fsync(2)` which only flushes to the drive's internal write cache — not to physical storage. For true power-loss durability on macOS, `fcntl.fcntl(fd, fcntl.F_FULLFSYNC)` is required. Since this runner operates on macOS and runs unattended overnight, this is a real concern. Mitigation: use a platform check:

```python
import sys, fcntl
def durable_fsync(fd: int) -> None:
    if sys.platform == "darwin":
        fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    else:
        os.fsync(fd)
```

### Known Pitfalls

- **EXDEV**: `tempfile.mkstemp()` without `dir=` may land in `/tmp` on a different filesystem. Always pass `dir=target.parent`.
- **Permissions**: `mkstemp` creates files with mode `0600`. If the original file has different permissions, transfer them before `os.replace()`.
- **Orphaned temp files**: if the process crashes after `mkstemp` but before `os.replace`, `.tmp` files accumulate. Use recognizable prefixes for cleanup.

---

## Requirements & Constraints

From `requirements/project.md`:
- **"Graceful partial failure"**: "Individual tasks in an autonomous plan may fail. The system should retry, potentially hand off to a fresh agent with clean context, and fail that task gracefully if unresolvable — while completing the rest." — directly requires that batch state corruption not kill the session.
- **"Failure handling"**: "Surface all failures in the morning report." — requires escalations.jsonl to be durable so all escalations appear in the morning report.
- **"File-based state"**: No database. State lives in plain files. Atomic write patterns are the correct abstraction layer.

### Existing Tests (affected)

- `claude/overnight/tests/test_deferral.py`: `TestWriteEscalation` — covers field presence and append behavior; does not test fsync/durability
- `claude/overnight/tests/test_map_results.py`: `TestMissingResultsFallback` — already handles corrupt/missing batch results gracefully; this is a partial mitigator for Bug 2 today
- `claude/overnight/tests/test_overnight_state.py`: `test_round_trip` — covers save/load of recovery_attempts; does not test crash-safety

---

## Tradeoffs & Alternatives

### Bug 1: Orchestrator Prompt Fix

**Alt A — Prompt-only instruction change**: Edit `orchestrator-round.md` to replace pseudocode `write_text` with `save_state()` calls. Minimal change; relies entirely on the AI agent following the updated instruction. Non-deterministic — no test can verify the agent complied.

**Alt B — Python wrapper module `orchestrator_io.py`**: Create a module that exports only safe functions (`save_state`, `update_feature_status`, `write_escalation`). Update the prompt to use `orchestrator_io` imports exclusively. Code structure prevents the agent from accessing raw write primitives.

**Recommendation**: Alt B. The adversarial review confirms this should be mandatory: a prompt-only fix has no enforcement mechanism. The overnight runner is unattended; a broken prompt fix that goes undetected until the next session is unacceptable. The overhead is low (a thin re-export module). This also documents intent — the `orchestrator_io` module surface is the sanctioned API for agent code in the orchestrator.

### Bug 2: batch-{N}-results.json Atomic Write

**Alt A — Inline tempfile+replace** at the write site in `batch_runner.py`. One-off fix; pattern duplicated.

**Alt B — Extract `save_batch_result()` helper** in `state.py` or a new module. Consistent with `save_state()`; single point of definition.

**Recommendation**: Alt B. The codebase already has `save_state()` and `write_deferral()` as named helpers. Consistency is the primary value. This is also the natural extension of the "atomic write helpers" surface in `state.py`.

### Bug 3: escalations.jsonl fsync

No alternative — the correct fix for an append-only JSONL log is `f.flush()` + `os.fsync()` inside the `with open(...)` block. Temp+replace would destroy append semantics. Cost: ~1–2ms per escalation (1–5 per batch); negligible. Consider platform-specific F_FULLFSYNC for macOS durability.

### Bug 4: recovery_attempts Per-Feature Save

**Alt A — Per-feature save immediately after increment**: After each `recovery_attempts_map[name] += 1` at lines 1544 and 1711, call `load_state() → update → save_state()` immediately.

**Adversarial caveat**: this shifts the race window but does not eliminate it. The load→increment→save sequence must be atomic (or locked) to prevent a crash between the in-memory increment and the save from losing the update. Verify whether the existing async lock covers these call sites.

**Alt B — Save end-of-batch, accept the risk**: Current behavior. A mid-batch kill causes one re-dispatch of the repair agent. Low probability, low severity relative to other bugs.

**Recommendation**: Alt A with care. The recovery_attempts budget is a correctness invariant. The overhead is small (1–3 extra saves per batch at ~10–15ms each). The implementation must load fresh state, increment, and save atomically within the lock scope to avoid the race.

---

## Adversarial Review

### Fsync Gap is Wider Than the Four Fix Sites

`save_state()` and `atomic_write()` both use `os.write()` + `os.replace()` without `f.flush()` or `os.fsync()`. They are atomic (corruption-safe) but not durable (power-loss-safe). **The four-bug fix as scoped does not close this gap** — it adds atomicity where missing, but does not add durability to any existing atomic helpers. If durability across crashes (not just atomicity) is the requirement, the scope expands to include adding fsync to `save_state()` and `atomic_write()`.

### orchestrator_io Wrapper Should Be Mandatory

The prompt fix for Bug 1 is non-deterministic — there is no mechanism to verify the agent followed the updated instruction. Treating `orchestrator_io.py` as optional accepts that the fix could silently be ignored. Given that the overnight runner is unattended, this failure mode is invisible until morning review.

### Per-Feature recovery_attempts Save Race

The adversarial agent identifies that per-feature saves for `recovery_attempts` still have a race: if the process is killed between the in-memory increment and the `save_state()` call, the increment is lost. Mitigation: ensure the load→increment→save happens within the existing async lock that protects the recovery dispatch path.

### Pre-Existing: next_question_id() Race Under Concurrent Async Tasks

`next_question_id()` in `deferral.py` scans the filesystem for existing files and returns `max_id + 1`. Under `asyncio.gather` (concurrent batch execution), two features could read the same max_id and generate duplicate question IDs. This is a pre-existing bug not introduced by these fixes — flagged as out of scope but worth a follow-up backlog item.

### atomic_write Consolidation Risk

Three separate implementations of the atomic write pattern exist: `save_state()`, `atomic_write()` in `common.py`, and the pattern will be added for batch results. Future improvements (adding fsync, F_FULLFSYNC, directory fsync) must be applied to all three. Consider consolidating `save_state()` to call `atomic_write()` rather than reimplementing.

---

## Open Questions

- **Fsync scope**: Should `save_state()` and `atomic_write()` also receive fsync/F_FULLFSYNC treatment, or is "atomic but not durable" acceptable for JSON state files? Expanding scope here adds durability but touches more code. Deferred: will be resolved in Spec by asking the user.
- **orchestrator_io.py mandatory vs optional**: The adversarial review argues the wrapper is mandatory because prompt-only fixes have no enforcement mechanism. Deferred: spec will lock in whether the wrapper is mandatory or optional based on user direction.
- **recovery_attempts race**: Does the load→increment→save for Bug 4 happen within the existing async lock scope at lines 1544/1711 in batch_runner.py? Deferred: implementation must verify lock scope before writing code; spec will note the invariant to verify.
