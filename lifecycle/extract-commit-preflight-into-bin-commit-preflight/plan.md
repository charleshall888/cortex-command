# Plan: extract-commit-preflight-into-bin-commit-preflight

## Overview

Build `bin/cortex-commit-preflight` (Python, JSON output, hardened git env, exit-code taxonomy) plus its DR-7 shim using `realpath`; drive-by fix the same shim in six existing Python scripts; rewrite `skills/commit/SKILL.md` Step 1; land all of the above plus the auto-synced plugin mirror in a single atomic bootstrap commit; then add the pytest suite as a follow-up commit. Bootstrap atomicity is the central architectural constraint — Phase 4 of `.githooks/pre-commit` blocks any commit that touches `bin/cortex-*` without staging the corresponding `plugins/cortex-interactive/bin/` mirror, and Phase 4 inspects all build-output plugins (currently `cortex-interactive` AND `cortex-overnight-integration`), so pre-bootstrap drift in either plugin must be resolved before staging.

## Tasks

### Task 1: Create `bin/cortex-commit-preflight` and set executable bit

- **Files**: `bin/cortex-commit-preflight`
- **What**: Author the canonical Python script: shebang, DR-7 telemetry shim using `os.path.realpath(__file__)` in the first 50 lines, repo-state probing (`rev-parse --is-inside-work-tree`, `--is-bare-repository`, `--verify HEAD`), three hardened git invocations (`status`, `diff HEAD`, `log --oneline -10`), JSON-document emission to stdout, exit-code taxonomy (0/2/3/5), and chmod +x.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Pattern reference for shim + json.dumps + temp-git-repo testability: `bin/cortex-archive-rewrite-paths` (lines 1-3 for the canonical shim shape using `abspath`; substitute `realpath` for `abspath`; line 152 for the `errors="replace"` decode pattern).
  - Pattern reference for `subprocess.run` + git invocation with hardened env: do NOT copy `bin/cortex-check-parity:553,560` — those callsites use naked `["git", "show", …]` argvs without `-c color.ui=never`, `-c log.decorate=auto`, `--no-pager`, or env hardening, and would fail Task 6's AST verification. Synthesize the conforming pattern from the contracts below.
  - Argv prefix contract on every git call: the first six elements of every git argv list literal must be `"git"`, `"-c"`, `"color.ui=never"`, `"-c"`, `"log.decorate=auto"`, `"--no-pager"`. Subcommand and its arguments follow. This contract holds whether the calls are inlined or wrapped in a helper.
  - Subprocess `env` keyword contract: the `env` keyword must be passed and its source dict must contain both `GIT_OPTIONAL_LOCKS` (set to `"0"`) and `LC_ALL` (set to `"C.UTF-8"`), merged with `os.environ`. If the env dict is constructed via a Name reference at the call site (e.g., `env=GIT_ENV`), the dict's construction must be locally traceable in the same module (e.g., a top-level constant).
  - Capture stdout as bytes (no `text=True`), then decode with `errors="replace"`.
  - JSON shape: `{"status": str, "diff": str, "recent_log": str, "notes": list[str]}` — single-line, encoded with `ensure_ascii=False`.
  - Exit-code taxonomy: 0 = success or empty-repo (with `notes=["empty_repo"]`, `diff=""`, `recent_log=""`); 2 = not inside a git repo (stderr: "not inside a git repository"); 3 = bare repository (stderr: "bare repository — no working tree"); 5 = any other partial-failure case (do NOT emit partial JSON).
  - No CLI flags (no argparse). Reject extra argv positionally or simply ignore.
  - HEREDOC prohibition (`skills/commit/SKILL.md:53`) does NOT apply to the script's internal Python — only to /cortex-interactive:commit-adjacent shell composition.
  - chmod requirement: the exec bit (`st.st_mode & 0o111`) is load-bearing — `bin/cortex-check-parity:166–183` (`gather_deployed`) skips files without it, producing misleading E002 drift reports.
- **Verification**:
  - `test -x bin/cortex-commit-preflight && head -1 bin/cortex-commit-preflight | grep -q '^#!/usr/bin/env python3$'` — pass if exit 0.
  - `head -50 bin/cortex-commit-preflight | grep -F 'cortex-log-invocation' | grep -F 'os.path.realpath(__file__)'` — pass if at least one matching line.
  - `bin/cortex-commit-preflight | python3 -c 'import sys,json; o=json.loads(sys.stdin.read()); assert set(o.keys())=={"status","diff","recent_log","notes"}; assert all(isinstance(o[k], str) for k in ["status","diff","recent_log"]); assert isinstance(o["notes"], list)'` — pass if exit 0.
  - `grep -F 'ensure_ascii=False' bin/cortex-commit-preflight | wc -l` — pass if ≥ 1.
  - `grep -E 'subprocess\.run\(.*text=True' bin/cortex-commit-preflight | wc -l` — pass if = 0.
  - Exit-code probe outside any repo: `PFLT="$PWD/bin/cortex-commit-preflight"; (cd /tmp && "$PFLT"); echo $?` — pass if = 2.
- **Status**: [x] complete

### Task 2a: Drive-by realpath fix in archive/audit Python scripts (group A)

- **Files**:
  - `bin/cortex-archive-rewrite-paths`
  - `bin/cortex-archive-sample-select`
  - `bin/cortex-audit-doc`
- **What**: Mechanical single-token replacement `os.path.abspath(__file__)` → `os.path.realpath(__file__)` in the DR-7 shim line of these three Python scripts.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **Motivation**: forward-compatible consistency with the new `bin/cortex-commit-preflight` script (which uses `realpath` from inception). None of these six scripts is currently invoked via a symlink, so for today's invocation paths the swap is a no-op; the fix only manifests behaviorally when the script is later deployed through a `~/.local/bin/` symlink or similar, where `realpath` correctly resolves to the canonical bin/ for sibling-helper lookup. No behavioral test is needed because no current behavior changes; verification is grep-based only.
  - Use `grep -n 'os.path.abspath(__file__)' bin/cortex-<name>` to locate each occurrence.
  - The change is a single-token replacement per file; preserve surrounding indentation, mode bits, and whitespace.
  - Each script uses `__file__` exactly once (the shim line); no other `__file__`-based path computation exists in any of the six scripts. Confirm with `grep -c '__file__' bin/cortex-<name>` before editing — expected count = 1 each.
  - Bash `bin/cortex-*` scripts are explicitly out of scope (resolved Open Question).
- **Verification**:
  - `for f in bin/cortex-archive-rewrite-paths bin/cortex-archive-sample-select bin/cortex-audit-doc; do grep -c 'os.path.realpath(__file__)' "$f"; done` — pass if prints `1` three times.
  - `for f in bin/cortex-archive-rewrite-paths bin/cortex-archive-sample-select bin/cortex-audit-doc; do grep -c 'os.path.abspath(__file__)' "$f"; done` — pass if prints `0` three times.
  - Shim window invariant: `for f in bin/cortex-archive-rewrite-paths bin/cortex-archive-sample-select bin/cortex-audit-doc; do head -50 "$f" | grep -F 'cortex-log-invocation' | wc -l; done` — pass if prints `1` three times (shim still within first 50 lines after edit).
- **Status**: [x] complete

### Task 2b: Drive-by realpath fix in check/count/validate Python scripts (group B)

- **Files**:
  - `bin/cortex-check-parity`
  - `bin/cortex-count-tokens`
  - `bin/cortex-validate-spec`
- **What**: Mechanical single-token replacement `os.path.abspath(__file__)` → `os.path.realpath(__file__)` in the DR-7 shim line of these three Python scripts. Identical change shape to Task 2a.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **Motivation**: same as Task 2a — forward-compatible consistency with the new script. `cortex-check-parity` is the parity-walking gatekeeper but uses `os.getcwd()` (line 1038) for its directory traversal, not `__file__` — confirm with `grep -c '__file__' bin/cortex-check-parity` (expected = 1, the shim line). The realpath swap does not change any parity-walk behavior.
  - Same pattern as Task 2a — single-token shim-line replacement, preserve all surrounding text and mode bits.
  - These three scripts are larger (`cortex-check-parity` is ~600+ lines), but the change is confined to the shim line in the first ~10 lines of each file.
- **Verification**:
  - `for f in bin/cortex-check-parity bin/cortex-count-tokens bin/cortex-validate-spec; do grep -c 'os.path.realpath(__file__)' "$f"; done` — pass if prints `1` three times.
  - `for f in bin/cortex-check-parity bin/cortex-count-tokens bin/cortex-validate-spec; do grep -c 'os.path.abspath(__file__)' "$f"; done` — pass if prints `0` three times.
  - Shim window invariant: `for f in bin/cortex-check-parity bin/cortex-count-tokens bin/cortex-validate-spec; do head -50 "$f" | grep -F 'cortex-log-invocation' | wc -l; done` — pass if prints `1` three times.
- **Status**: [x] complete

### Task 3: Replace `skills/commit/SKILL.md` Step 1 with single-sentence inline-code wiring

- **Files**: `skills/commit/SKILL.md`
- **What**: Collapse the existing three-bullet Step 1 (and the former Step 2 calling out `git log --oneline -10`) into a single narrative-prose sentence that invokes `bin/cortex-commit-preflight` (path-qualified) via inline-code mention; renumber subsequent steps so total step count drops by one. The wiring must be in narrative prose, not a markdown table cell (R6 narrows table-only matches in the parity linter).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Existing Step 1 lives at `skills/commit/SKILL.md:12–14`; the existing Step 2 references `git log --oneline -10`.
  - **Path-qualified invocation**: use `` `bin/cortex-commit-preflight` `` (relative to repo root), not the bare `` `cortex-commit-preflight` ``. Bin scripts in this repo are not on `$PATH` by default (the project ships via `uv tool install -e .` which exposes only the `cortex` CLI), and the plugin mirror is consumed by Claude Code's slash-command loader rather than by the shell. Path-qualified invocation works from the repo root in every shell context.
  - Parity linter accepts inline-code form: `` `cortex-commit-preflight` `` or `` `bin/cortex-commit-preflight` `` in narrative prose. See `bin/cortex-check-parity:471–489` for the three accepted wiring patterns; both forms are detected.
  - HEREDOC prohibition is in `skills/commit/SKILL.md:53`. The replacement sentence must be ≤ 250 bytes, descriptive (mention status, diff, recent log) but not enumerate every legacy command name. Suggested wording: `Run `` `bin/cortex-commit-preflight` `` to get status, working-tree diff, and last 10 commits as a single JSON document.`
  - The Workflow section must contain zero occurrences of the literal substrings `git status`, `git diff HEAD`, and `git log --oneline` after the rewrite — verified by spec R11 multi-line Python check.
- **Verification**:
  - `python3 -c "
import re
doc = open('skills/commit/SKILL.md').read()
m = re.search(r'## Workflow\n(.*?)(?=\n## |\Z)', doc, re.DOTALL)
assert m, 'Workflow section missing'
w = m.group(1)
assert 'cortex-commit-preflight' in w, 'preflight script not wired'
assert 'git status' not in w, 'git status leftover'
assert 'git log --oneline' not in w, 'git log --oneline leftover'
assert 'git diff HEAD' not in w, 'git diff HEAD leftover'
"` — pass if exit 0.
  - `grep -c 'cortex-commit-preflight' skills/commit/SKILL.md` — pass if ≥ 1.
- **Status**: [x] complete

### Task 4: Sync plugin mirror via `just build-plugin` and confirm cross-plugin cleanliness

- **Files**: `plugins/cortex-interactive/bin/cortex-commit-preflight` (new mirror artifact), `plugins/cortex-interactive/skills/commit/SKILL.md` (regenerated mirror of Task 3 edit)
- **What**: Run `just build-plugin` to mirror the canonical sources into both build-output plugins. The recipe handles `--include='cortex-*' --exclude='*'` rsync into `plugins/cortex-interactive/bin/`, AND skill-tree mirroring for both `cortex-interactive` and `cortex-overnight-integration` plugins. Confirm there is no pre-existing drift in EITHER plugin tree before bootstrap commit.
- **Depends on**: [1, 2a, 2b, 3]
- **Complexity**: simple
- **Context**:
  - `just build-plugin` is the existing recipe; no edits to the recipe needed.
  - rsync `-a` preserves mode bits, so the chmod from Task 1 propagates.
  - **Cross-plugin gate scope**: pre-commit Phase 4 runs `git diff --quiet -- "plugins/$p/"` for each `$p` in the build-output array (currently `cortex-interactive` AND `cortex-overnight-integration`). If the cortex-overnight-integration tree had pre-existing drift before this task ran (e.g., a skill source edited but plugin mirror not regenerated), running `just build-plugin` regenerates the mirror but does NOT auto-stage it — the working-tree change becomes Phase-4 drift. The implementer must check both plugin trees and stage all regenerated paths before the bootstrap commit.
  - **rsync --delete semantics**: the `--delete --include='cortex-*' --exclude='*'` filter removes plugin-mirror files matching `cortex-*` that lack a `bin/` counterpart. If the working tree has any orphaned plugin-mirror file under `plugins/cortex-interactive/bin/cortex-*`, rsync deletes it; that deletion appears as drift to Phase 4 and must be staged or recovered before commit.
- **Verification**:
  - `cmp bin/cortex-commit-preflight plugins/cortex-interactive/bin/cortex-commit-preflight` — pass if exit 0 (byte-identical).
  - `test -x plugins/cortex-interactive/bin/cortex-commit-preflight` — pass if exit 0 (mode preserved).
  - Cross-plugin drift check: `git status --porcelain plugins/cortex-interactive/ plugins/cortex-overnight-integration/ | grep -v -E '(plugins/cortex-interactive/bin/|plugins/cortex-interactive/skills/commit/SKILL\.md)' | wc -l` — pass if = 0 (every working-tree change in either plugin tree is either staged in Task 5 or absent; the grep -v filters out the expected Task 5 stage paths).
  - Pre-commit parity check (no actual commit): `bin/cortex-check-parity --staged 2>&1; echo $?` — pass if = 0 (verifies parity linter accepts the new bin/cortex-commit-preflight ↔ skills/commit/SKILL.md pairing before bootstrap commit attempts the same gate).
- **Status**: [x] complete

### Task 5: Bootstrap commit (single atomic commit of canonical + plugin mirror + SKILL.md)

- **Files**: none modified — this task is a git commit operation. It stages and commits outputs from Tasks 1, 2a, 2b, 3, and 4. Verification reads `git log` metadata after the commit succeeds.
- **What**: Stage all changes from Tasks 1, 2a, 2b, 3, and 4 (canonical bin scripts + plugin-mirror scripts + SKILL.md edit + plugin-mirror SKILL.md regenerated by build-plugin) and create a single commit. Pre-commit hook chain (Phase 1.5 parity, Phase 1.6 shim, Phase 3 build-plugin re-run, Phase 4 plugin-drift) must all pass.
- **Depends on**: [1, 2a, 2b, 3, 4]
- **Complexity**: simple
- **Context**:
  - **Dogfooding clarification**: by Task 5 time, Task 3 has edited `skills/commit/SKILL.md` and Task 4 has built the plugin mirror at `plugins/cortex-interactive/skills/commit/SKILL.md`. The Skill tool reads SKILL.md from disk at invocation time, so an `/cortex-interactive:commit` invocation here will load the NEW path-qualified wording (not the legacy three commands). The path-qualified `bin/cortex-commit-preflight` works from the repo root in any shell context, so this is the expected and correct behavior.
  - **Fallback if /cortex-interactive:commit fails for any reason** (e.g., script execution issue, hook abort that isn't auto-recoverable): the implementer falls back to direct `git add ... && git commit -m '...'` for this single bootstrap commit. CLAUDE.md's "always commit using /cortex-interactive:commit" rule has a one-time exception for the bootstrap because this is the only commit that modifies the commit skill itself. Subsequent commits (Task 7, etc.) return to using `/cortex-interactive:commit`.
  - Pre-commit Phase 3 will re-run `just build-plugin` defensively; Phase 4 then verifies no drift remains. As long as Task 4 ran AND staged all regenerated paths from BOTH plugins (not just cortex-interactive), Phase 4 passes.
  - The DR-7 shim presence check (Phase 1.6 via `cortex-invocation-report --check-shims`) inspects the on-disk `bin/cortex-*` scripts; Task 1 emits the shim within the first 50 lines, and Tasks 2a/2b verified the shim is still within line 50 for each of the six drive-by-fixed scripts.
  - Phase 1.5 parity already verified by Task 4's pre-commit parity check; Phase 1.5 should re-pass at commit time since the staged blobs are identical to what was checked.
  - All affected paths must be staged in a single `git add` before the commit; the constraint is atomicity (single commit), not how the staging is structured.
- **Verification**:
  - `git log -1 --name-only --format= | sort -u | grep -c -E '^(bin/cortex-(commit-preflight|archive-rewrite-paths|archive-sample-select|audit-doc|check-parity|count-tokens|validate-spec)|skills/commit/SKILL.md|plugins/cortex-interactive/(bin/cortex-(commit-preflight|archive-rewrite-paths|archive-sample-select|audit-doc|check-parity|count-tokens|validate-spec)|skills/commit/SKILL\.md))$'` — pass if = 16 (7 canonical bin + 7 plugin-mirror bin + canonical SKILL.md + plugin-mirror SKILL.md).
  - Pre-flight commit-existence check: `git log -1 --format=%s | head -c 200` — capture the commit subject; the implementer must visually confirm this matches the just-authored bootstrap commit and not an unrelated prior commit. (The cross-plugin and parity gates above already make pre-commit-abort the dominant failure mode; this check defends against silent verification false-positives by confirming the expected commit is the latest.)
  - `git status --porcelain | wc -l` — pass if = 0 (no leftover unstaged or untracked changes after the bootstrap commit).
- **Status**: [x] complete

### Task 6: Create `tests/test_commit_preflight.py` with six required test functions

- **Files**: `tests/test_commit_preflight.py`
- **What**: Author the pytest test file with all six top-level test functions named per spec R14: `test_normal_repo_emits_valid_json`, `test_bare_repo_exits_3`, `test_empty_repo_emits_empty_repo_note`, `test_binary_diff_no_crash`, `test_shim_records_invocation`, `test_git_env_hardening`. Tests invoke the script via subprocess against tmp git repos (or load module via `importlib.machinery.SourceFileLoader` for the AST test). Each test must be designed to fail when the property under test is absent — vacuous-pass paths are explicitly disallowed.
- **Depends on**: [5]
- **Complexity**: complex
- **Context**:
  - Pattern reference for `importlib.machinery.SourceFileLoader` + temp git repo fixture: `tests/test_archive_rewrite_paths.py:41–54`.
  - `test_normal_repo_emits_valid_json`: tmp `git init`, set user.name/user.email, make initial commit, stage a small text-file change, invoke script, assert exit 0, JSON parses with the exact 4-key schema, `notes == []`.
  - `test_bare_repo_exits_3`: `git init --bare` in tmpdir, invoke with that as cwd, assert exit code 3 and stderr contains "bare".
  - `test_empty_repo_emits_empty_repo_note`: fresh `git init` (no commits), invoke, assert exit 0, JSON `notes` contains `"empty_repo"`, `diff == ""`, `recent_log == ""`.
  - `test_binary_diff_no_crash`: tmp git repo with `user.name`/`user.email` configured and one initial commit; write a small text file containing the bytes `b'hello \xc3\x28 world\n'` (an invalid UTF-8 continuation sequence) to `invalid.txt`; commit it as the working-tree-vs-HEAD diff fixture (i.e., overwrite an existing file's contents with these bytes after first committing a placeholder, OR write the bytes for the first time and stage). The fixture must NOT contain NUL bytes — git's binary-detection short-circuit (which kicks in at the first NUL in the first ~8KB) emits the ASCII line `Binary files X and Y differ` instead of the invalid bytes, which would let any decode strategy pass the test. With NUL-free invalid UTF-8, git emits the bytes in the diff body and the script's `errors="replace"` handler must convert them to `�`. Assertions: exit 0, JSON parses, `diff` is `str`, `diff` contains the replacement char `�` (U+FFFD), and `diff` does NOT contain the literal substring `"Binary files"`. The negative assertion on `"Binary files"` confirms git did not short-circuit; the positive assertion on `�` confirms the script's decode hardening actually fired.
  - `test_shim_records_invocation`: set `LIFECYCLE_SESSION_ID` to a fresh UUID; create a tmp git repo (`git init` + initial commit); invoke the script with `cwd=tmp_repo` and `LIFECYCLE_SESSION_ID` in env; the JSONL log lands at `tmp_repo/lifecycle/sessions/<uuid>/bin-invocations.jsonl` (because `cortex-log-invocation` resolves `$repo_root` from the script's CWD's git toplevel, which is the tmp repo). Count records in that path before and after invocation; assert delta == 1 and the new record's `script` field equals `cortex-commit-preflight`. This pinning prevents both modes of failure: (a) JSONL never appearing (tmp repo not git-init'd), (b) JSONL polluting the cortex-command repo's `lifecycle/sessions/`.
  - `test_git_env_hardening`: AST-walk `bin/cortex-commit-preflight` with `ast.parse` + a custom visitor. The visitor must scan EVERY `subprocess.run`/`check_output`/`Popen` call in the module — not just calls inside one specific function — and inspect each call's first positional argument. If that argument is a `List` literal whose first element is a `Constant("git")`, treat it as a git argv; assert (a) the call's keywords include `env`, AND (b) the argv list literal begins with the six-element prefix `["git", "-c", "color.ui=never", "-c", "log.decorate=auto", "--no-pager"]`. Then, separately, walk for the env dict's source: if any subprocess call uses `env=NAME` (a Name reference), find the local module-level Assign or AugAssign that defines NAME and assert the dict literal contains both `"GIT_OPTIONAL_LOCKS"` and `"LC_ALL"` keys. Additionally, assert that AT LEAST ONE git argv list literal exists in the module (defends against vacuous pass when zero list literals match — e.g., if a future refactor uses `*args` such that no argv literal is constructed at module scope). The number of matched git argv list literals may be 1 (helper-extracted) or 3 (inlined); both satisfy the contract as long as every match passes (a) and (b) and the env-dict source is verified.
  - Each test should set required git config (`user.name`, `user.email`) when initializing tmp repos to avoid commit failures.
  - Test functions are top-level (not methods of a class) per the spec's `grep -E "PASSED" | grep -c PASSED == 6` verification.
- **Verification**:
  - `python3 -m pytest tests/test_commit_preflight.py -v 2>&1 | grep -E 'PASSED|FAILED' | grep -E 'test_normal_repo_emits_valid_json|test_bare_repo_exits_3|test_empty_repo_emits_empty_repo_note|test_binary_diff_no_crash|test_shim_records_invocation|test_git_env_hardening' | grep -c PASSED` — pass if = 6.
  - `python3 -m pytest tests/test_commit_preflight.py -v` — pass if exit 0.
- **Status**: [x] complete

### Task 7: Commit tests

- **Files**: `tests/test_commit_preflight.py`
- **What**: Stage the test file and commit via `/cortex-interactive:commit` (the now-landed new-wording version). This is a follow-up commit; the bootstrap atomicity constraint applied only to Task 5.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - Tests touch only `tests/`; no `bin/cortex-*` is staged, so Phase 3/4 of pre-commit do not re-run.
  - This commit happens AFTER Task 5 has landed, so /cortex-interactive:commit Step 1 will exercise the new `bin/cortex-commit-preflight` script — incidentally serving as a smoke test of the new commit path.
- **Verification**:
  - `git log -1 --name-only --format= | grep -c -E '^tests/test_commit_preflight\.py$'` — pass if = 1.
  - `git log -1 --name-only --format= | grep -v '^$' | wc -l` — pass if = 1 (only one file in the commit).
- **Status**: [x] complete

### Task 8: End-to-end verification (parity, shim aggregator, plugin byte-identity, JSONL telemetry)

- **Files**: none (verification-only task — no code changes)
- **What**: Run the parity linter, shim-presence aggregator, plugin byte-identity sweep across all seven mirror files, and a session-scoped JSONL telemetry round-trip to confirm the integration is intact. Acts as an integration gate before lifecycle review.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**:
  - Parity linter: `bin/cortex-check-parity` walks `bin/cortex-*` and `plugins/cortex-interactive/bin/cortex-*`, asserts no drift, asserts every script has at least one wiring reference. SKILL.md inline-code mention from Task 3 satisfies the wiring for `cortex-commit-preflight`.
  - Shim aggregator: `bin/cortex-invocation-report --check-shims` scans every `bin/cortex-*` script for the DR-7 shim line in the first 50 lines.
  - Plugin byte-identity: cmp the 7 canonical → mirror pairs (1 new + 6 drive-by-fixed) to confirm no drift. The 6 drive-by-fixed mirrors are the side-effect outputs of Task 4; this is the appropriate place to check them holistically.
  - JSONL telemetry: a new session id ensures no false-positive from stale leftover records.
- **Verification**:
  - `bin/cortex-check-parity; echo $?` — pass if = 0.
  - `bin/cortex-invocation-report --check-shims; echo $?` — pass if = 0.
  - `for f in cortex-commit-preflight cortex-archive-rewrite-paths cortex-archive-sample-select cortex-audit-doc cortex-check-parity cortex-count-tokens cortex-validate-spec; do cmp "bin/$f" "plugins/cortex-interactive/bin/$f" || echo "DRIFT: $f"; done | grep -c DRIFT` — pass if = 0.
  - `SID="lifecycle-105-verify-$(python3 -c 'import uuid; print(uuid.uuid4())')"; LOG="lifecycle/sessions/$SID/bin-invocations.jsonl"; mkdir -p "$(dirname "$LOG")"; LIFECYCLE_SESSION_ID="$SID" bin/cortex-commit-preflight >/dev/null 2>&1; grep -c '"script":"cortex-commit-preflight"' "$LOG"` — pass if ≥ 1.
- **Status**: [x] complete

## Verification Strategy

End-to-end verification at lifecycle review time:

1. **Per-task verification** runs as each task completes (commands above).
2. **Spec acceptance criteria** — re-run each acceptance command from `spec.md` Requirements 1–16; all must pass.
3. **Bootstrap-commit integrity** — `git log` must show the bootstrap commit (Task 5) as a single commit with all expected paths; no follow-up "fixup" commits required to satisfy pre-commit hooks.
4. **Test suite** — `python3 -m pytest tests/test_commit_preflight.py -v` exits 0 with all six named tests PASSED. The tests must be designed to fail when the property under test is absent (no vacuous-pass).
5. **Plugin byte-identity** — covered by Task 8's cmp sweep across all 7 mirrored pairs.
6. **Cross-plugin drift cleanliness** — `git status --porcelain plugins/` exits with no entries after Task 8 completes.
7. **Behavior parity with legacy three-call form** — manually trigger /cortex-interactive:commit on a working-tree change in a development branch; confirm the agent receives an equivalent context envelope (status text, diff text, recent log text).

## Veto Surface

- **Test suite size and depth.** Six required tests including a non-trivial AST walker (handles helper extraction and env-dict Name dereferencing) and an invalid-UTF-8 fixture for decode hardening. Reasonable for a `high` criticality script that gates the commit hot-path; the user could trim the AST walker's helper-handling complexity if they prefer to mandate inlined subprocess calls in the implementation (which simplifies the test but couples the implementation more tightly to a specific style).
- **Drive-by realpath fix included in the same lifecycle.** Tasks 2a and 2b modify six unrelated scripts. Inspection confirms the change is a true no-op for current invocation paths (none of the six scripts is symlink-invoked today) and a forward-compatible fix only in the symlink case — so the actual blast radius is narrow. The user could still split this off into a separate ticket for tighter commit-history attribution if preferred.
- **Path-qualified vs PATH-resolvable script invocation.** Task 3 wires `bin/cortex-commit-preflight` (path-qualified). The user could alternatively expose `cortex-commit-preflight` on `$PATH` (e.g., via the `cortex` CLI tool's entry-point list) and use the bare name. Path-qualified was chosen because it works zero-config in any shell context within the repo; PATH-based would require additional packaging work to be consistent across user environments.
- **Bootstrap commit fallback to direct `git commit`.** The plan permits a one-time exception to "always commit using /cortex-interactive:commit" if the bootstrap commit's first invocation fails for any reason. The user could insist on /cortex-interactive:commit only — which would force re-trying or debugging at Task 5 rather than allowing a fallback path.

## Scope Boundaries

Per `spec.md` Non-Requirements (lines 99–109), the following are explicitly OUT of scope and must NOT be added during implementation:

- No `--max-diff-bytes` flag, no `diff_truncated` field, no `diff_bytes_total` field.
- No structured `recent_log` (e.g., `[{sha, subject}]`). Plain string only.
- No `--cached` / staged-only diff.
- No branch metadata field (status already shows the branch).
- No CLI flags (no argparse).
- No bash `bin/cortex-*` scripts in the symlink-fix loop — Python-only per resolved Open Question.
- No changes to `/cortex-interactive:commit` Steps 3–5 (stage, compose, commit).
- No edits to the `just build-plugin` recipe.
- No new entry in `bin/.parity-exceptions.md`.
- No exposure of `bin/cortex-*` scripts on `$PATH` — path-qualified invocation only.
