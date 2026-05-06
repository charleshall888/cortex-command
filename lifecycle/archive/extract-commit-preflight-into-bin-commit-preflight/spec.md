# Specification: Extract `/cortex-interactive:commit` Step 1 into `bin/cortex-commit-preflight`

> **Epic reference**: This ticket (105, C1) implements one component of the epic at `research/extract-scripts-from-agent-tool-sequences/research.md`. See `lifecycle/archive/extract-commit-preflight-into-bin-commit-preflight/research.md` for ticket-specific research, including DR-2 wire-format conventions and Adversarial-review findings on bootstrap commit ordering, JSON encoding flags, and shim symlink-safety.

## Problem Statement

`/cortex-interactive:commit` Step 1 currently runs three deterministic git commands (`git status`, `git diff HEAD`, `git log --oneline -10`) as separate Bash tool calls in `skills/commit/SKILL.md:12-13`. Each call costs a tool-call slot, and the SKILL.md prose describing the three commands is itself prompt overhead on every commit. Extracting the preflight into a single `bin/cortex-commit-preflight` script that emits a deterministic JSON document collapses the three calls into one, makes the preflight shape testable, and shortens SKILL.md. The work also retrofits a latent symlink-following bug (`os.path.abspath` → `os.path.realpath`) across all `bin/cortex-*` Python scripts at the same time.

## Requirements

1. **New Python script `bin/cortex-commit-preflight` exists and is executable.**
   - Acceptance: `test -x /Users/charlie.hall/Workspaces/cortex-command/bin/cortex-commit-preflight && head -1 /Users/charlie.hall/Workspaces/cortex-command/bin/cortex-commit-preflight | grep -q '^#!/usr/bin/env python3$'` exits 0.

2. **DR-7 telemetry shim is present in the first 50 lines of `bin/cortex-commit-preflight`, using `os.path.realpath(__file__)` (not `abspath`), and actually executes at runtime (not just present as a comment).**
   - Acceptance (smoke): `head -50 bin/cortex-commit-preflight | grep -F 'cortex-log-invocation' | grep -F 'os.path.realpath(__file__)'` returns at least one matching line.
   - Acceptance (binding, runtime): the test in R14's `test_shim_records_invocation` asserts the shim emits a JSONL record with a fresh timestamp by setting `LIFECYCLE_SESSION_ID` to a UUID, counting JSONL records before invocation, running the script, and asserting the record count delta is exactly 1 with `script == "cortex-commit-preflight"`. This binding check rules out comment-only "shims" that pass the grep but do not execute.

3. **`bin/cortex-invocation-report --check-shims` exits 0 after the new script is added.**
   - Acceptance: `bin/cortex-invocation-report --check-shims` exits with code 0.

4. **Script emits a single-line JSON document to stdout with the schema `{status: str, diff: str, recent_log: str, notes: list[str]}` in a normal (non-empty) git repository.**
   - Acceptance: `bin/cortex-commit-preflight | python3 -c 'import sys,json; o=json.loads(sys.stdin.read()); assert set(o.keys())=={"status","diff","recent_log","notes"}; assert all(isinstance(o[k], str) for k in ["status","diff","recent_log"]); assert isinstance(o["notes"], list); assert all(isinstance(n, str) for n in o["notes"])'` exits 0 from inside this repo.

5. **Output preserves "diff in full" doctrine — no script-level byte cap, no truncation flag, no summarization.**
   - Acceptance: in a temp git repo with a >10KB working-tree diff, `bin/cortex-commit-preflight` emits the full diff body inside the `diff` field. `python3 -c 'import json,subprocess,sys; o=json.loads(subprocess.check_output(["bin/cortex-commit-preflight"], cwd="<tmp_repo>")); assert len(o["diff"]) > 10000'` exits 0.

6. **Subprocess invocations harden the git environment.**
   - Acceptance (smoke): `grep -E "GIT_OPTIONAL_LOCKS|LC_ALL=C.UTF-8|color.ui=never|--no-pager" bin/cortex-commit-preflight | wc -l` returns ≥4.
   - Acceptance (binding, AST): a test in `tests/test_commit_preflight.py::test_git_env_hardening` parses `bin/cortex-commit-preflight` with the `ast` module, walks every `subprocess.run`/`subprocess.check_output`/`subprocess.Popen` call whose first argv element is the literal `"git"`, and asserts (a) the call passes an `env` keyword whose value (or its source dict) contains both `"GIT_OPTIONAL_LOCKS"` and `"LC_ALL"` keys, and (b) the argv list begins with the four-element prefix `["git", "-c", "color.ui=never", "-c", "log.decorate=auto", "--no-pager", ...]`. The smoke grep alone is insufficient because module-level docstrings or comments containing those literals could satisfy it without any runtime effect.

7. **Diff and other git outputs are captured as bytes and decoded with `errors="replace"`; not `text=True`.**
   - Acceptance (smoke): `grep -F 'errors="replace"' bin/cortex-commit-preflight` returns at least one match. `grep -E 'subprocess\.run\(.*text=True' bin/cortex-commit-preflight` returns no matches.
   - Acceptance (binding, runtime): a test in `tests/test_commit_preflight.py::test_binary_diff_no_crash` constructs a temp git repo, stages a small binary file change (e.g., `b"\x00\x01\x02\xff" * 100` written to `binary.bin`), invokes the script, and asserts (a) exit code is 0, (b) stdout parses as JSON, (c) the `diff` field is a `str` (no `UnicodeDecodeError` raised), (d) the `diff` field contains either the substring `"Binary files"` (git's default) or replaced character `�` markers — never raw NUL bytes. This binds the decode mode to the diff field specifically; an `errors="replace"` placed on an unrelated decode would fail this check.

8. **JSON output is encoded with `ensure_ascii=False`.**
   - Acceptance: `grep -F 'ensure_ascii=False' bin/cortex-commit-preflight` returns at least one match.

9. **Exit-code taxonomy is implemented as: 0 success or empty-repo, 2 not-in-repo, 3 bare-repo, 5 other git failure.**
   - Acceptance: in a tmp directory not under any git repo, `bin/cortex-commit-preflight; echo $?` prints `2`. In a `git init --bare` repo, `bin/cortex-commit-preflight; echo $?` prints `3`. In a fresh `git init` (no commits), `bin/cortex-commit-preflight; echo $?` prints `0` and the JSON includes `"empty_repo"` in `notes`.

10. **Empty-repo behavior emits `{status: <output>, diff: "", recent_log: "", notes: ["empty_repo"]}` and exits 0.**
    - Acceptance: in a fresh `git init` repo, `bin/cortex-commit-preflight | python3 -c 'import sys,json; o=json.loads(sys.stdin.read()); assert "empty_repo" in o["notes"]; assert o["diff"]=="" and o["recent_log"]==""'` exits 0.

11. **`skills/commit/SKILL.md` Step 1 is replaced with a single inline-code-wired sentence in narrative prose; original three-command Step 1+Step 2 collapse to one step.**
    - Acceptance (parity): `bin/cortex-check-parity` exits 0 (linter satisfied by the new wiring). `grep -c 'cortex-commit-preflight' skills/commit/SKILL.md` returns ≥1.
    - Acceptance (prose-removal, binding): the new Step 1 contains exactly one sentence describing the preflight script (≤ 250 bytes), and `skills/commit/SKILL.md` contains zero occurrences of the literal command names `git status` and `git log --oneline` in the Workflow section. Verifiable via:
      ```bash
      python3 -c "
      import re, sys
      doc = open('skills/commit/SKILL.md').read()
      m = re.search(r'## Workflow\n(.*?)(?=\n## |\Z)', doc, re.DOTALL)
      assert m, 'Workflow section missing'
      workflow = m.group(1)
      assert 'cortex-commit-preflight' in workflow, 'preflight script not wired in Workflow'
      assert 'git status' not in workflow, 'git status leftover in Workflow'
      assert 'git log --oneline' not in workflow, 'git log --oneline leftover in Workflow'
      assert 'git diff HEAD' not in workflow, 'git diff HEAD leftover in Workflow'
      "
      ```
      Exit 0 if all assertions hold. The Python check is multi-line-aware and rules out the failure mode where leftover commands appear on separate bulleted lines (which a single-line regex would miss).

12. **Drive-by replace `os.path.abspath(__file__)` with `os.path.realpath(__file__)` in the DR-7 shim line of the six existing Python `bin/cortex-*` scripts.**
    - Files: `bin/cortex-archive-rewrite-paths`, `bin/cortex-archive-sample-select`, `bin/cortex-audit-doc`, `bin/cortex-check-parity`, `bin/cortex-count-tokens`, `bin/cortex-validate-spec`.
    - Acceptance: `for f in bin/cortex-archive-rewrite-paths bin/cortex-archive-sample-select bin/cortex-audit-doc bin/cortex-check-parity bin/cortex-count-tokens bin/cortex-validate-spec; do grep -c 'os.path.realpath(__file__)' "$f"; done` prints `1` six times. The same loop with `os.path.abspath(__file__)` prints `0` six times.

13. **Plugin distribution byte-identity holds after `just build-plugin`.**
    - Acceptance: after running `just build-plugin`, `cmp bin/cortex-commit-preflight plugins/cortex-interactive/bin/cortex-commit-preflight` exits 0. `git diff --quiet -- plugins/cortex-interactive/bin/cortex-commit-preflight` exits 0 (no untracked drift after staging).

14. **A Python test file `tests/test_commit_preflight.py` exercises the script via subprocess and asserts five named scenarios pass.**
    - Required test names (each must exist as a top-level test function in the file):
      - `test_normal_repo_emits_valid_json` — stage a small text-file change in a temp git repo with at least one prior commit; assert exit 0, stdout is single-line JSON, schema matches `{status, diff, recent_log, notes}`, `notes == []`.
      - `test_bare_repo_exits_3` — `git init --bare` in a tmpdir; invoke script with that as cwd; assert exit code 3, stderr contains "bare".
      - `test_empty_repo_emits_empty_repo_note` — fresh `git init` (no commits); invoke; assert exit 0, JSON's `notes` list contains `"empty_repo"`, `diff == ""`, `recent_log == ""`.
      - `test_binary_diff_no_crash` — see R7 binding criterion; binary file change; assert no UnicodeDecodeError, JSON parses, `diff` is str.
      - `test_shim_records_invocation` — see R2 binding criterion; UUID-based session id; record-count delta check.
      - `test_git_env_hardening` — see R6 binding criterion; AST inspection.
    - Acceptance: `python3 -m pytest tests/test_commit_preflight.py -v` exits 0; the verbose output includes each of the six named test functions reported as PASSED. Verifiable via:
      ```bash
      python3 -m pytest tests/test_commit_preflight.py -v 2>&1 | grep -E "PASSED|FAILED" | grep -E "test_normal_repo_emits_valid_json|test_bare_repo_exits_3|test_empty_repo_emits_empty_repo_note|test_binary_diff_no_crash|test_shim_records_invocation|test_git_env_hardening" | grep -c PASSED
      ```
      Returns 6 (one PASSED line per required scenario).

15. **`bin/cortex-check-parity` (or `just check-parity`) exits 0 on the post-change repository.**
    - Acceptance: `bin/cortex-check-parity` exits 0.

16. **A NEW JSONL invocation record appears in `lifecycle/sessions/<LIFECYCLE_SESSION_ID>/bin-invocations.jsonl` after invoking the new script in an active session — verified by record-count delta to defeat stale-leftover false positives.**
    - Acceptance:
      ```bash
      SID="test-spec-105-$(uuidgen 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')"
      LOG="lifecycle/sessions/$SID/bin-invocations.jsonl"
      mkdir -p "$(dirname "$LOG")"
      BEFORE=$(grep -c '"script":"cortex-commit-preflight"' "$LOG" 2>/dev/null || echo 0)
      LIFECYCLE_SESSION_ID="$SID" bin/cortex-commit-preflight >/dev/null
      AFTER=$(grep -c '"script":"cortex-commit-preflight"' "$LOG" 2>/dev/null || echo 0)
      [ $((AFTER - BEFORE)) -ge 1 ]
      ```
      Exit 0 if delta ≥ 1. The unique-per-run session id rules out stale JSONL false positives. (`cortex-invocation-report --self-test` covers the byte-identity round trip separately.)

## Non-Requirements

- **No `--max-diff-bytes` flag, no `diff_truncated` field, no `diff_bytes_total` field.** Honor C1 ticket scope ("Diff emitted in full, not summarized") literally. If size becomes a real problem in practice, file a follow-up ticket.
- **No structured `recent_log` field (e.g., `[{sha, subject}]` array).** Plain string mirrors today's `git log --oneline -10` output verbatim. YAGNI for hypothetical PR-description / morning-review consumers.
- **No `--cached` / staged-only diff field.** Today's `/commit` flow does not inspect staged-only diff at preflight; adding it widens the schema beyond DR-2 narrow guidance.
- **No branch metadata field.** `git status` already shows the current branch in its first line.
- **No CLI flags on the script** (no argparse). Single positional invocation; reject extra args via standard sys.argv check (or simply ignore).
- **Bash `bin/cortex-*` scripts are NOT in scope for the symlink fix.** The user's answer to the symlink-fix scope question explicitly named "Python" only. Bash scripts use `dirname "$0"`, which has the same latent bug, but the fix shape differs (`readlink -f "$0"` vs Python's `realpath`); deferred to a separate ticket if needed.
- **No changes to `/cortex-interactive:commit` Steps 3–5** (stage, compose, commit). They remain agent-driven judgment calls.
- **No changes to the `just build-plugin` recipe.** The existing `--include='cortex-*' --exclude='*'` filter handles the new file automatically.
- **No new entry in `bin/.parity-exceptions.md`.** The script is wired via SKILL.md inline-code reference.

## Edge Cases

- **Outside any git repository**: `git rev-parse --is-inside-work-tree` returns false → script writes `not inside a git repository` to stderr and exits 2.
- **Bare repository**: `git rev-parse --is-bare-repository` returns true → script writes `bare repository — no working tree` to stderr and exits 3.
- **Empty repository (no HEAD yet)**: `git rev-parse --verify HEAD` fails → script emits `{status: <output>, diff: "", recent_log: "", notes: ["empty_repo"]}` and exits 0. The first commit on a new repo is a legitimate flow; the agent reads `notes` and adapts.
- **Concurrent invocation while another git is running**: `GIT_OPTIONAL_LOCKS=0` in subprocess env prevents `.git/index.lock` contention for `git status` refresh.
- **Diff containing invalid UTF-8 (true binary file)**: `git diff` defaults emit `Binary files X and Y differ` (no NUL bytes); decoder uses `errors="replace"` for any residual invalid sequences. The `--text` flag is explicitly NOT passed (would force-render binaries as garbled text).
- **Diff containing literal JSON-looking text** (e.g., a JSON file change): JSON-escaped inside the `diff` string field; the LLM consumer parses the envelope correctly. Downstream raw-grep consumers must use a JSON parser to extract `.diff` (noted in the script's docstring).
- **Partial command failure** (e.g., `git status` succeeds but `git log` errors unexpectedly): hard-fail with exit 5 and stderr diagnostic. Do not emit a partial JSON envelope. A half-complete envelope risks the agent composing a commit against a misleading view.
- **`LIFECYCLE_SESSION_ID` is unset** (e.g., script invoked outside a Claude Code session): the DR-7 shim writes a `no_session_id` breadcrumb to `~/.cache/cortex/log-invocation-errors.log` and exits 0 (existing fail-open behavior of `cortex-log-invocation:27-30`). Main script logic continues unaffected.
- **Symlinked invocation** (e.g., `~/.local/bin/cortex-commit-preflight` → repo's `bin/cortex-commit-preflight`): `os.path.realpath(__file__)` resolves to the canonical path, so the sibling `cortex-log-invocation` lookup succeeds.

## Changes to Existing Behavior

- **MODIFIED:** `skills/commit/SKILL.md` Step 1 — three commands (`git status`, `git diff HEAD`, `git log --oneline -10`) collapse to one invocation of `cortex-commit-preflight` returning a JSON document. Old Step 2 ("Run `git log --oneline -10`...") is folded in; subsequent steps renumber.
- **ADDED:** `bin/cortex-commit-preflight` — new Python script in the `bin/cortex-*` family with the DR-7 shim, JSON output, and exit-code taxonomy.
- **MODIFIED:** Six existing Python `bin/cortex-*` scripts — DR-7 shim line replaces `os.path.abspath(__file__)` with `os.path.realpath(__file__)` (single-token replacement; behavior change is symlink-safe lookup of sibling helper).
- **ADDED:** `tests/test_commit_preflight.py` — subprocess + temp-git-repo fixture tests covering normal, bare, and empty-repo scenarios.
- **AUTO-SYNCED:** `plugins/cortex-interactive/bin/cortex-commit-preflight` — written by `just build-plugin` from canonical `bin/` source; not a hand-edited artifact, but the first commit must include it (Phase 4 drift-check otherwise blocks the commit).

## Technical Constraints

- **DR-2 (epic research, line 145)**: "Location: `bin/`. Naming: kebab-case. Output: JSON for multi-field, plain text for single-value. **Narrow** schemas. Exit codes: 0 success, distinct non-zero per failure class."
- **SKILL.md-to-bin parity (project.md:27)**: every `bin/cortex-*` script must be wired through an in-scope SKILL.md / requirements / docs / hooks / justfile / tests reference. Wiring is detected by `bin/cortex-check-parity` via three patterns: path-qualified `bin/cortex-foo`, inline-code `` `cortex-foo` ``, fenced bash code block reference. Wiring solely in a markdown table cell is narrowed by R6 — must appear in narrative prose.
- **DR-7 telemetry (observability.md:53–59)**: every `bin/cortex-*` script must include the shim line in the first 50 lines. Pre-commit Phase 1.6 enforces presence via `cortex-invocation-report --check-shims`. Plugin byte-identity test mandates `bin/...` and `plugins/cortex-interactive/bin/...` produce byte-identical content (rsync `-a` preserves mode bits).
- **HEREDOC prohibition (`skills/commit/SKILL.md:53`)**: in `/cortex-interactive:commit`-adjacent code paths, `<<EOF` and `$(cat ...)` are forbidden. The script's invocation site is in this skill, so its execution context inherits the constraint. (The script's own internal Python is unaffected.)
- **Bootstrap commit ordering (Adversarial review)**: the first commit creating this script must include both `bin/cortex-commit-preflight` AND `plugins/cortex-interactive/bin/cortex-commit-preflight` AND the SKILL.md edit AND the six driveby-fixed Python scripts in a single commit. Phase 3 of `.githooks/pre-commit` runs `just build-plugin` if any `bin/cortex-*` is staged; Phase 4 fails the commit if `plugins/$p/` has unstaged drift. The implementer must `git add` the regenerated plugin mirror before committing.
- **`chmod +x` is load-bearing**: `gather_deployed` (`bin/cortex-check-parity:166–183`) requires the exec bit (`st.st_mode & 0o111`); without it the parity linter does not see the file and reports a misleading E002 drift on the SKILL.md reference.
- **The shim's `os.path.realpath` change must NOT break Bash-script callers**: only Python scripts use `os.path` calls; the bash shim line `"$(dirname "$0")/cortex-log-invocation" "$0" "$@" || true` is unchanged.

## Open Decisions

(None. All decisions raised during research were resolved at Research Exit Gate or during Spec write. Critical-review B-class concerns — including bootstrap atomic-staging discipline, plugin-cache reload semantics, and the framing of R12 as design-tightening rather than bug-fix — are recorded in `critical-review-residue.json` and surfaced in the morning report; they do not require spec changes but inform Plan-phase task ordering.)
