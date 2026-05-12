# Research: Trim cortex-log-invocation shim cost (per-call ~21ms)

Reduce `bin/cortex-log-invocation` per-call wall time on a best-effort basis, preserving the fail-open contract (`trap 'exit 0' EXIT`) and emitting JSONL records that remain functionally consumable by `cortex-invocation-report`. Caller-side cooperation is in scope wherever it is the highest-yield path.

## Codebase Analysis

### Files in play

- **Primary edit target**: `bin/cortex-log-invocation` (69 lines). The shim. Dual-source canonical; `plugins/cortex-core/bin/cortex-log-invocation` and `plugins/cortex-interactive/bin/cortex-log-invocation` regenerate by pre-commit hook / `just build-plugin` (verbatim rsync — no text substitution).
- **Lockstep mirror**: `cortex_command/backlog/_telemetry.py` — Python helper that mirrors the bash shim's JSONL line **byte-for-byte** for `update_item.py`, `create_item.py`, `generate_index.py`, `build_epic_map.py`. `_telemetry.py:_resolve_repo_root` calls `subprocess.run(["git", "rev-parse", "--show-toplevel"])`. **Any change in the shim's `repo_root` resolution must land in `_telemetry.py` in parallel** or the two diverge on edge cases (worktrees, symlinked CWD, GIT_DIR pollution).
- **Byte-identity test**: `cortex_command/backlog/tests/test_telemetry_byte_equivalence.py` — normalizes `ts` to `<TS>` before comparison; everything else is byte-for-byte. Asserts the 4-key set `{ts, script, argv_count, session_id}` and types (lines 32-38, 118-121). The test uses a clean tmp-path repo, so it never exercises worktree / symlinked / GIT_DIR cases.
- **Shim happy-path test**: `tests/test_commit_preflight.py:239-294` — subprocess test asserts exit 0, one new JSONL record appended, `script` field matches caller basename.

### Caller invocation patterns

`--check-shims` (`.githooks/pre-commit:101-117`) is a loose substring grep: literal `cortex-log-invocation` must appear in the first 50 lines of every `bin/cortex-*`. Free dimension for caller refactor as long as the literal stays in-window.

Two canonical forms in the repo today:

1. Bash leaf (10 scripts incl. `cortex-jcc:8`, `cortex-lifecycle-state:28`, `cortex-lifecycle-counters:35`, `cortex-backlog-ready:2`, `cortex-morning-review-*`, `cortex-git-sync-rebase:12`):
   ```bash
   "$(dirname "$0")/cortex-log-invocation" "$0" "$@" || true
   ```
2. Python one-liner (13+ scripts incl. `cortex-resolve-backlog-item:19`, `cortex-complexity-escalator:21`, `cortex-commit-preflight:29`, `cortex-check-parity:14`):
   ```python
   import os, subprocess, sys; subprocess.run([os.path.join(os.path.dirname(os.path.realpath(__file__)), "cortex-log-invocation"), sys.argv[0], *sys.argv[1:]], check=False)
   ```

### `LIFECYCLE_SESSION_ID` setters (slow-path producers)

- `hooks/cortex-scan-lifecycle.sh:9-10` (canonical) and `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh:9-10` (mirror) — SessionStart hook, sets via `CLAUDE_ENV_FILE`.
- `cortex_command/overnight/runner.py:2011-2014` — `os.environ["LIFECYCLE_SESSION_ID"] = session_id` for spawned children.
- `cortex_command/pipeline/dispatch.py:541-554` — explicit env allowlist forwarded to dispatched subprocesses.

All other call sites are readers that default to `"manual"` when unset.

### `CORTEX_REPO_ROOT` is already an established convention

- Defined and consumed in `cortex_command/common.py:75-77` — `_resolve_user_project_root` honors `CORTEX_REPO_ROOT` verbatim and skips CWD probing when set.
- Already allowlisted in `cortex_command/overnight/scheduler/macos.py:60`.
- Exercised by `cortex_command/overnight/tests/test_env_snapshot.py:37,53,62`.
- **Adversarial finding**: this is the established cache the shim should already be consulting before paying for `git rev-parse`. It is the same source of truth Python uses.

### Aggregator JSONL tolerance

`bin/cortex-invocation-report` (lines 51-81) reads with awk line-by-line and only `index($0, "\"script\":\"" name "\"")` matches against an inventory. Field order outside of `"script":"..."` does not affect tallies. `--self-test` (lines 83-105) substring-greps `"script":"cortex-self-test-probe"` on the last line. **The aggregator is tolerant of reordering and whitespace.** The strict constraint is the byte-equivalence test against `_telemetry.py`, not the aggregator.

### Per-segment cost measurements (from adversarial profiling, n=50)

- Total: ~19ms (not 21ms; ticket's number is a rounded aggregate from #190 spec.md:79).
- `git rev-parse --show-toplevel`: ~6.1ms (~32%).
- `date -u +%Y-%m-%dT%H:%M:%SZ` × 2 (line 49 and `_log_breadcrumb` line 22): ~3.6ms (~19%).
- `mkdir -p` (warm — dir exists): ~1.5ms (~8%).
- `basename` fork (line 46): largest remainder.
- Bash startup (`/bin/bash -c 'exit 0'`): ~2.7ms — fixed floor, unrecoverable.
- File open/append/close + case glob + parameter setup: ~5ms residual.

### Spec R5 budget (from archived spec `lifecycle/archive/add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7/spec.md:19`)

- `< 0.05s real time` per invocation. Bash + POSIX utilities only. **No `jq`, no Python interpreter spawn.** The 21ms is already inside R5's 50ms budget but eats most of the per-call envelope of `cortex-lifecycle-state` (the #190 benchmark).

### macOS bash version reality

- `/bin/bash` is 3.2.57 (Apple GPLv3 freeze). Shebang is `#!/usr/bin/env bash` → resolves first-on-PATH.
- `printf '%(%Y-%m-%dT%H:%M:%SZ)T' -1` requires bash 4.2+. On 3.2 it errors to **stderr** (`printf: '(': invalid format character`), not silent fallback.
- `EPOCHSECONDS`/`EPOCHREALTIME` require bash 5.0+.
- Launchd-spawned subprocesses may not have Homebrew bash in `$PATH`.
- Adversarial confirmed: `printf '%(...)T'` does NOT shift to UTC even on bash 5+ unless `TZ=UTC` is set; literal `Z` in format string is just a character.

## Web Research

### `git rev-parse --show-toplevel` cost & avoidance

- ~11-15ms typical per call (Terragrunt issue #2344 cumulative metric: 679 × ~12ms = ~8s). Local measurement here: ~6.1ms.
- Avoidance options ranked by web-prior-art:
  1. Parent injects env var (e.g., `CORTEX_REPO_ROOT`) — strongest pattern.
  2. `GIT_DIR` env to disable discovery — fragile, has historical security implications.
  3. Pure-bash walk-up loop for `.git` marker — fast but diverges from `git rev-parse` semantics in worktree / submodule / bare / `.git`-inside-CWD cases.
- Sources: git-scm Environment Variables; Terragrunt #2344; git-rev-parse docs.

### `mkdir -p` warm-path cost

- `mkdir -p` is idempotent but still pays fork + `stat()`.
- `[ -d "$dir" ] || mkdir -p "$dir"` short-circuits to a builtin on the common (already-exists) path; saves ~1-2ms.
- Standard idempotent-script idiom (arslan.io; MoldStud bash perf guide).

### `date` vs bash builtins

- `printf '%(...)T'` builtin requires bash 4.2+; `EPOCHSECONDS`/`EPOCHREALTIME` require bash 5.0+. macOS default bash is 3.2.
- Without `TZ=UTC` exported, builtin time format produces local time even with `Z` suffix in format string. Byte-equivalence breaks silently.
- Sources: shell-tips date formatting; bashsupport EPOCHREALTIME; blog.dnmfarrell.com.

### Append atomicity

- POSIX `O_APPEND` writes ≤ `PIPE_BUF` (4 KiB Linux, 512 POSIX min) are atomic on local FS. Records are < 1 KB and bounded ≤ 4 KB by spec; safe under concurrent shims.
- `exec {fd}>>$file` opens FD once — saves nothing for a single-write-per-invocation shim.
- Sources: pvk.ca atomic appends; nullprogram blog; linux-fsdevel thread.

### Fail-open trap

- `trap 'exit 0' EXIT` is the canonical fail-open primitive.
- For SIGINT/SIGTERM coverage: `trap 'exit 0' INT TERM EXIT`.
- Anti-pattern: writing telemetry to stdout/stderr inherited from caller (corrupts caller output). Current shim writes to dedicated log file — correct.

### Sourcing vs exec

- Sourcing eliminates ~2-5ms bash startup. Only applicable when caller is itself bash. Current callers are mixed (bash + Python). Sourcing is not a portable shim contract — rejected as too invasive.

## Requirements & Constraints

### Frozen by `requirements/observability.md` §Runtime Adoption Telemetry (P1)

- Shim path: `lifecycle/sessions/<id>/bin-invocations.jsonl`.
- Inputs: shim line in each `bin/cortex-*`; `LIFECYCLE_SESSION_ID` env var.
- Outputs: per-session JSONL log; aggregator stdout; breadcrumb at `~/.cache/cortex/log-invocation-errors.log`.
- Acceptance criteria reference Spec R1–R18 from the archived spec.

### Frozen by archived spec `lifecycle/archive/add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7/spec.md`

- **R2 (JSONL schema)**: keys `{ts, script, argv_count, session_id}`; `ts` is ISO 8601 UTC; each record ≤ 4 KB to preserve `O_APPEND` atomicity. Argv values NOT recorded (privacy minimization — only count).
- **R3 (fail-open on missing session)**: `LIFECYCLE_SESSION_ID= bin/cortex-log-invocation /tmp/x; echo $?` → `0` and writes nothing.
- **R4 (fail-open on write failure + breadcrumb)**: exit 0 unconditionally; on failure write one-line diagnostic to `~/.cache/cortex/log-invocation-errors.log` with one of `no_session_id|no_repo_root|session_dir_missing|write_denied|other`.
- **R5 (perf budget)**: `< 0.05s` per invocation. **Bash + POSIX only; no `jq`, no Python interpreter spawn.**
- **R6 / R11 / R14 (shim presence gate)**: literal `cortex-log-invocation` in the first 50 lines of every `bin/cortex-*`.
- **R13 (self-test round-trip)**: exits 0 iff helper resolves log path + probe write + probe read-back succeed.
- **R15 (plugin distribution byte-identity)**: `diff bin/cortex-log-invocation plugins/cortex-interactive/bin/cortex-log-invocation` exits 0 after `just build-plugin`.
- **R18**: `just test` passes.

### Implicit from `cortex_command/backlog/_telemetry.py` byte-equivalence test

- Field order frozen: `ts`, `script`, `argv_count`, `session_id` in that sequence. JSON separators `(",", ":")`, `ensure_ascii=False`, trailing `\n`.

### `requirements/project.md` architectural constraints

- **Graceful partial failure** (line 37) — reinforces fail-open.
- **Sandbox preflight gate** — does not fire for `bin/cortex-log-invocation` (not in the sandbox-source set).
- **SKILL.md-to-bin parity** — no exception for this shim in `bin/.parity-exceptions.md`.
- **Dual-source enforcement** — edit canonical `bin/`, plugin mirrors regenerate.

### Out of scope per archived spec Non-Requirements

- PreToolUse hook, log rotation policy, argv value capture, pipeline integration, per-script tags, backfill of historical adoption data.

## Tradeoffs & Alternatives

### Per-segment cost ceiling (from adversarial profiling)

| Segment | Cost | Recoverable? |
|---|---|---|
| Bash startup | ~2.7ms | No (fixed floor) |
| `git rev-parse --show-toplevel` | ~6.1ms | Yes (cached env var) |
| `date -u` × 2 | ~3.6ms | Partial (bash 5+ builtin with `TZ=UTC`) |
| `mkdir -p` (warm) | ~1.5ms | Yes (`[ -d ] ||` guard) |
| `basename` | residual | Yes (`${var##*/}`) |
| Append + open + close + case + setup | ~5ms | Marginal |

**Realistic savings ceiling**: ~10ms (from ~19ms to ~9ms). Not the agents' initially-quoted ~12-16ms.

### Alternatives evaluated

**A. In-shim micro-optimizations** — `[ -d ] || mkdir -p` guard; replace `basename` with `${path##*/}`; (optionally) bash-5+ `printf '%(...)T'` with `TZ=UTC` guard.
- Pros: single-file change; preserves shim's hermetic, fail-open property; no caller cooperation.
- Cons: `printf '%T'` portability hazard (macOS bash 3.2; stderr noise on guard; TZ-not-UTC silent regression). Without it, save ~2-3ms.
- File-count delta: 1 (the shim).
- Recommended subset: mkdir guard + basename builtin. Defer the date builtin until a value-equivalence test exists.

**B. Env-var cache from cooperating parents (`CORTEX_REPO_ROOT`)** — *Recommended after adversarial review.*
- Pros: ~6ms saved on every invocation from a producer-cooperating shell (overnight runner, SessionStart hook, dashboard). One-line shim change: `repo_root="${CORTEX_REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null)}"`. The env var is already established, allowlisted, exercised, read by Python (`common.py:75-77`). Falls back identically to today's behavior when unset.
- Cons: Requires producers to actually export it. Inspection: `runner.py:2011-2014` already sets `LIFECYCLE_SESSION_ID`; adding a sibling `CORTEX_REPO_ROOT` export is a one-line addition. `hooks/cortex-scan-lifecycle.sh:9-10` SessionStart hook can also write it to `CLAUDE_ENV_FILE`. `dispatch.py:541-554` already allowlists env vars — adding `CORTEX_REPO_ROOT` to the allowlist is a 1-line edit.
- File-count delta: shim (+1 line) + 2-3 producer sites (+1 line each).
- **Safety check**: shim must validate the env var (`[ -d "$CORTEX_REPO_ROOT/.git" ] || [ -f "$CORTEX_REPO_ROOT/.git" ]`) before trusting, to defend against stale env after `cd` into another repo. Falls back to `git rev-parse` when validation fails.

**C. File-based cookie cache (`~/.cache/cortex/repo-roots/<pwd-hash>`)** — Rejected.
- Cache key is fragile (per-cwd entries; required walk-up for hash key duplicates D's logic with worse semantics).

**D. Pure-bash walk-up loop replacing `git rev-parse`** — **Rejected after adversarial review.**
- Diverges from `git rev-parse --show-toplevel` in:
  - Stale `.claude/worktrees/agent-*` directories (`.git` file points to pruned gitdir): walk-up returns the worktree path; git correctly fails. Telemetry fragments to orphan dirs.
  - Symlinked CWD: walk-up returns symlinked path; `git rev-parse` returns canonical. JSONL writes go to a different session dir than consumers expect.
  - `GIT_DIR` pollution: runner.py:455 explicitly scrubs `GIT_DIR` before subprocess calls — evidence that the project considers env-var inheritance a real hazard.
  - CWD inside `.git/`: walk-up may infinite-loop if guard is `[ "$d" != "/" ]` without `[ -n "$d" ]`.
  - Bare/submodule edge cases.
- Walk-up would break byte-equivalence with `_telemetry.py` (which uses `git rev-parse`). The byte-equivalence test would still pass (clean tmp-repo) while production regresses silently.
- **Correctness regression**, not just a savings reduction. Reject.

**E. Batched/async daemon write** — Rejected. Contradicts shim's one-shot fail-open envelope; introduces long-lived process dependency.

**F. Pre-forked unix-socket daemon** — Rejected decisively.

### Recommended approach

**B + narrow A.** The shim:

1. Read `CORTEX_REPO_ROOT` env var first; validate it has a `.git` entry; fall back to `git rev-parse` if unset or invalid. Saves ~6ms on the cooperating-parent path.
2. Guard `mkdir -p` with `[ -d "$session_dir" ]`. Saves ~1.5ms on warm path.
3. Replace `basename` fork with `${script_path##*/}`. Saves the basename-fork cost.

Producers (small follow-on):

- `cortex_command/overnight/runner.py:2011-2014` — alongside `LIFECYCLE_SESSION_ID`, set `os.environ["CORTEX_REPO_ROOT"]` from the resolved project root.
- `hooks/cortex-scan-lifecycle.sh:10` (canonical) + `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh:10` (mirror) — emit `CORTEX_REPO_ROOT` into `CLAUDE_ENV_FILE` alongside `LIFECYCLE_SESSION_ID`.
- `cortex_command/pipeline/dispatch.py:541-554` — add `"CORTEX_REPO_ROOT"` to the allowlist.

Defer:

- Replacing `date -u` with `printf '%(...)T'`. The portability + `TZ=UTC` correctness hazard is real; the ~3.6ms savings is not worth the complexity at this milestone.
- Replacing `_log_breadcrumb`'s own `date -u` call. The breadcrumb path runs only on failure; not on the hot path.
- Caller cooperation beyond the named producers — diminishing returns.

Add a perf test (`tests/test_log_invocation_perf.py`) that asserts a wall-time budget against a representative invocation (e.g., one-line under N ms p50 across M trials). Without this, future drift erases gains silently.

Update `cortex_command/backlog/_telemetry.py` to consult `CORTEX_REPO_ROOT` symmetrically before calling `git rev-parse`. Otherwise Python and bash producers diverge in fragmentation cases.

Expected outcome: ~19ms → ~11ms on cooperating-parent path; ~19ms → ~17ms on non-cooperating path (mkdir guard + basename only).

## Adversarial Review

### Failure modes that invalidated the initial A+D plan

- **Walk-up replacement for `git rev-parse` is a correctness regression**, not just a perf trade. It diverges on stale worktree gitdirs, symlinked CWD, `GIT_DIR` pollution (the runner explicitly scrubs this — evidence of known hazard), CWD inside `.git/` (infinite-loop risk without `[ -n "$d" ]` guard), bare repos, submodules. Byte-equivalence test would pass; production telemetry would fragment. **Pivoted recommendation away from D.**
- **`printf '%(...)T'` is broken on macOS bash 3.2** — hard error on stderr, not silent fallback. Even on bash 5+, the literal `Z` in format string does NOT shift to UTC; requires `TZ=UTC` export. Without value-equivalence testing (current byte-equivalence test normalizes `ts` to `<TS>`), TZ regressions are invisible. **Deferred this optimization.**
- **Agents' ~12-16ms savings estimate was inflated.** Bash startup alone is ~2.7ms fixed floor. Realistic ceiling is ~10ms total. The actual recommended subset (B + narrow A) hits ~8ms savings.
- **Call frequency premise is partially overstated.** Dashboard polls don't invoke bin/cortex-* shims (they read JSONL/state files directly). Lifecycle skill phase entries fire once per phase transition. The high-frequency path is loops inside specific scripts like `cortex-update-item` invoked from decompose/triage.

### Security & anti-patterns

- **Walk-up vs malicious `.git` planting**: A walk-up loop's `[ -e .git ]` accepts any file (including attacker-planted). `git rev-parse` validates as gitdir-pointer. Low likelihood, real reduction in safety. Another reason to prefer B over D.
- **`command printf`** preferred over bare `printf` if the printf-builtin route is taken later — defends against alias shadowing.
- **Trap order**: `trap 'exit 0' EXIT` already correct; keep as-is.

### Assumptions that may not hold

- **`CORTEX_REPO_ROOT` is honored verbatim** by `common.py:75-77` without validation. The shim should validate the path has `.git` before trusting, to defend against stale env after `cd` into another repo. (Also reapply this guard in `common.py` if we want symmetric defense.)
- **Byte-equivalence test does not exercise edge cases** — only clean tmp-repo. Any shim/Python divergence on worktree/symlink/GIT_DIR cases is invisible. Add scenario tests if either path's `repo_root` resolution changes meaningfully.

### Mitigations adopted

- Drop walk-up (D).
- Defer `printf '%T'` builtin.
- Validate `CORTEX_REPO_ROOT` (`[ -d "$CORTEX_REPO_ROOT/.git" ] || [ -f "$CORTEX_REPO_ROOT/.git" ]`) before trusting.
- Update `_telemetry.py` symmetrically.
- Add a perf-budget test.
- Keep `mkdir -p` guard and `${var##*/}` basename replacement.

## Open Questions

- **Q1**: Should `cortex_command/backlog/_telemetry.py:_resolve_repo_root` be updated symmetrically to consult `CORTEX_REPO_ROOT` before invoking `git rev-parse`? Deferred: will be resolved in Spec — bash and Python emitters must agree on repo-root resolution semantics under the byte-equivalence test; symmetric update is the safe default unless the user wants to scope this ticket to the bash shim only.
- **Q2**: Should the perf-budget test (`tests/test_log_invocation_perf.py`) be authored as part of this ticket, or deferred to a follow-on? Deferred: will be resolved in Spec — opinion is to author it inline so the optimization has a regression gate, but the user may prefer a separate ticket to keep this trim focused on the shim edit.
- **Q3**: Should producers (`runner.py`, scan-lifecycle hook, `dispatch.py` allowlist) all be touched in this ticket, or only `runner.py` (where the overnight hot path lives)? Deferred: will be resolved in Spec — opinion is to touch all three since each is a one-line change and the partial set leaves coverage gaps.
- **Q4**: Should the `_log_breadcrumb` `date -u` call (the first of the two `date` forks) also be optimized? Deferred: will be resolved in Spec — opinion is no: the breadcrumb path runs only on failure (no `LIFECYCLE_SESSION_ID`, no repo root, etc.); it is not on the hot path and the ~1.8ms there is irrelevant to the dashboard/loop scenarios this ticket cares about.
