# Plan: add-sandbox-violation-tracker-hook-for-posttoolusebash

## Overview

Implement Alternative D from the spec: classify sandbox-routed Bash denials in the morning report at render time (no new hook). The work splits into three layers — (1) fix the latent session-id namespace bug in the existing `cortex-tool-failure-tracker.sh` so per-session captures actually flow into the lifecycle path the aggregator reads, (2) add per-spawn sidecar deny-list writes at both overnight spawn sites so the aggregator has authoritative deny-list context, and (3) extend `cortex_command/overnight/report.py` with a layered classifier, renderer, and `ReportData` wiring so a new `## Sandbox Denials` section surfaces classified counts. Tasks land in dependency order: tracker fix → reader-site fallback fix → sidecar writes (parallel pair) → classifier → renderer/wiring → fixture acceptance test → docs.

## Tasks

### Task 1: Tracker writes to lifecycle path and emits `command:` field

- **Files**: `claude/hooks/cortex-tool-failure-tracker.sh`
- **What**: When `$LIFECYCLE_SESSION_ID` is set and non-empty, redirect tracker output from `/tmp/claude-tool-failures-${INPUT.session_id}/` to `lifecycle/sessions/${LIFECYCLE_SESSION_ID}/tool-failures/`. When unset, retain the existing `/tmp` path. Additionally, add a `command:` YAML literal block scalar field per failure entry, alongside the existing `failure_num`, `tool`, `exit_code`, `timestamp`, `stderr` fields. Truncate command to first 4KB at write time. Spec: R1 + R3a.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Existing pattern for `$LIFECYCLE_SESSION_ID`-conditional path: `claude/hooks/cortex-permission-audit-log.sh:22-25` (modeled on per spec R1).
  - Existing tracker is 89 lines; the change is two write-target swaps plus one new YAML field write.
  - Use the same safe `mkdir -p ... 2>/dev/null || true` pattern already in the tracker for new directory creation.
  - YAML literal block scalar: `command: |\n  <indented-command-line(s)>` — same indentation pattern as the existing `stderr: |\n  …` block.
  - 4KB byte cap PLUS line-mode containment for YAML literal-block safety: pipe through `head -c 4096 | head -50 | sed 's/^/  /'` and ensure a trailing newline before the next field is appended. The byte-mode `head -c 4096` enforces the spec's 4KB cap; the subsequent `head -50` ensures the cut never lands mid-line (matching the existing `stderr` idiom of `echo … | head -20 | sed 's/^/  /'`); the `sed 's/^/  /'` indents continuation lines as the literal-block scalar contract requires; the trailing newline guarantees the next field's key starts on its own line. Without this composition, `yaml.safe_load_all` raises on the boundary case and the classifier sees no denials. Plain `head -c 4096` alone or shell parameter expansion alone is insufficient.
  - Hook MUST exit 0 unconditionally (preserve non-blocking observability invariant per spec Technical Constraints).
  - Dual-source: this is the canonical source. Plugin mirror at `plugins/cortex-overnight-integration/hooks/cortex-tool-failure-tracker.sh` is auto-synced by `just build-plugin`; do NOT hand-edit. Pre-commit will sync.
- **Verification**:
  - `bash -c 'LIFECYCLE_SESSION_ID=overnight-2026-01-01-0000 echo {\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"echo hi\"},\"tool_response\":{\"exit_code\":1,\"stderr\":\"x\"},\"session_id\":\"abc\"} | claude/hooks/cortex-tool-failure-tracker.sh && [[ -f lifecycle/sessions/overnight-2026-01-01-0000/tool-failures/bash.log ]] && echo PASS` — pass if PASS printed.
  - `grep -c '^command: |' lifecycle/sessions/overnight-2026-01-01-0000/tool-failures/bash.log` ≥ 1 — pass if count ≥ 1.
  - `bash -c 'unset LIFECYCLE_SESSION_ID; echo {\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"echo hi\"},\"tool_response\":{\"exit_code\":1,\"stderr\":\"y\"},\"session_id\":\"def\"} | claude/hooks/cortex-tool-failure-tracker.sh && [[ -f /tmp/claude-tool-failures-def/bash.log ]] && echo FALLBACK_PASS` — pass if FALLBACK_PASS printed (fallback path still works).
  - **Parser round-trip** (validates the truncation idiom emits parser-safe YAML for the spec edge cases): drive the hook with a multi-line command and a long (>4KB) command; then `python3 -c 'import yaml; docs=list(yaml.safe_load_all(open("lifecycle/sessions/overnight-2026-01-01-0000/tool-failures/bash.log"))); assert all(isinstance(d, dict) for d in docs if d); print("PARSER_PASS")'` — pass if PARSER_PASS printed.
- **Status**: [x] complete (commit 893af90)

### Task 2: Tracker shell-test extension

- **Files**: `tests/test_tool_failure_tracker.sh`
- **What**: Add a new test case that drives the hook with `LIFECYCLE_SESSION_ID=overnight-fixture-test` set and asserts output appears at `lifecycle/sessions/overnight-fixture-test/tool-failures/bash.log` (NOT `/tmp/`). Existing tests (which drive without `LIFECYCLE_SESSION_ID`) remain unchanged and continue to assert the `/tmp` fallback path. Spec: R6a.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Test file follows shell-test conventions in `tests/`. Use the existing test pattern for setup/teardown of fixture directories.
  - Cleanup: ensure the test removes `lifecycle/sessions/overnight-fixture-test/` after assertion.
- **Verification**: `bash tests/test_tool_failure_tracker.sh` — pass if exit 0 with all assertions passing; `grep -c 'lifecycle/sessions' tests/test_tool_failure_tracker.sh` ≥ 1.
- **Status**: [x] complete (commit 07f74cf)

### Task 3: Aggregator readers prefer lifecycle path with `/tmp` fallback

- **Files**: `cortex_command/overnight/report.py`
- **What**: All four `/tmp/claude-tool-failures-{session_id}` references in `report.py` (lines 246, 1094, and the `render_tool_failures` references at 1156 and 1430) prefer `lifecycle/sessions/{session_id}/tool-failures/` and fall back to `/tmp/claude-tool-failures-{session_id}/` only when the lifecycle path is absent. Spec: R1a. The two duplicate `collect_tool_failures` definitions (lines 223 and 1079) and two duplicate `render_tool_failures` definitions (lines 1156 and 1430) are not consolidated by this ticket (out of scope per spec) BUT one of each duplicate may be dead code — analyze call sites to determine; if dead, delete to prevent re-divergence; if live, patch both.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Pre-fix line numbers (verified): `cortex_command/overnight/report.py:226` (docstring), `:246` (`track_dir = Path(...)`), `:1082` (docstring), `:1094` (`track_dir = ...`), `:1159` (docstring referencing the same path).
  - Function definitions: `collect_tool_failures` at 223 and 1079; `render_tool_failures` at 1156 and 1430.
  - Determine liveness via `grep -nE '(collect|render)_tool_failures\b' cortex_command/` excluding the definitions themselves; whichever has zero callers is dead.
  - Implementation pattern for fallback chain:
    - Construct `lifecycle_dir = Path(f"lifecycle/sessions/{session_id}/tool-failures")`.
    - If `lifecycle_dir.exists()`, use it; else fall back to `Path(f"/tmp/claude-tool-failures-{session_id}")`.
  - The fallback chain MUST preserve the existing semantics on the `/tmp` path so any pre-existing reader behavior is unchanged when the lifecycle path is absent.
  - Update docstrings at 226, 1082, 1159 to reflect the new lifecycle-first convention.
- **Verification**:
  - `grep -c 'lifecycle/sessions/' cortex_command/overnight/report.py` ≥ 4 (at least one per reader site post-fix) — pass if count ≥ 4.
  - `grep -c '/tmp/claude-tool-failures-' cortex_command/overnight/report.py` ≥ 1 (fallback retained) — pass if count ≥ 1.
  - Functional: `python3 -c 'import os, pathlib, shutil; from cortex_command.overnight.report import collect_tool_failures; sid="x-fixture"; d=pathlib.Path(f"lifecycle/sessions/{sid}/tool-failures"); d.mkdir(parents=True, exist_ok=True); (d/"bash.count").write_text("3"); (d/"bash.log").write_text("---\nfailure_num: 3\ntool: Bash\nexit_code: 1\ntimestamp: 2026-05-04T00:00:00Z\nstderr: |\n  x\n"); r=collect_tool_failures(sid); shutil.rmtree(f"lifecycle/sessions/{sid}"); assert r, "expected non-empty"; print("PASS")'` — pass if PASS printed.
- **Status**: [x] complete (commit 5723d98; dead duplicates deleted, live patched, functional verification PASS)

### Task 4: Sidecar deny-list write at orchestrator spawn

- **Files**: `cortex_command/overnight/runner.py`
- **What**: Immediately after constructing the `--settings` deny-list for an orchestrator spawn, write a per-spawn JSON sidecar at `lifecycle/sessions/<overnight-id>/sandbox-deny-lists/orchestrator-<round-N>.json` with the schema-v2 envelope (`schema_version: 2`, `written_at`, `spawn_kind: "orchestrator"`, `spawn_id`, `deny_paths`). Write atomically via tempfile + `os.replace`. Spec: R2 (orchestrator portion).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - The orchestrator spawn site is the existing site that constructs the deny-list (post-#163). Locate via `grep -n 'denyWrite\|deny.write\|sandbox.filesystem' cortex_command/overnight/runner.py`. The spawn-site changes added by #163 are the natural insertion point — the sidecar write consumes the same `list[str]` of denied paths.
  - **Pre-write structural guard (required)**: before serializing the sidecar, assert the deny-list value matches the contract — `assert isinstance(deny_paths, list) and all(isinstance(p, str) for p in deny_paths)`. If #163 ships a richer shape than flat `list[str]`, this assertion fails fast at write time rather than producing a sidecar whose `deny_paths` value silently breaks the classifier's membership tests downstream.
  - **Pre-#163 ordering**: this task assumes #163 has landed (or co-merges). If `grep` finds no deny-list construction at the spawn site, do NOT invent a placeholder, hardcoded list, or stub deny-list — surface the dependency to the operator and stall the task until #163 lands. A placeholder passes verification but corrupts the contract this task is supposed to establish.
  - Round counter `<round-N>` is the orchestrator round number already tracked by the runner state (round_idx or equivalent). Identify by reading the round-loop in runner.py.
  - Sidecar JSON schema (verbatim per spec):
    ```
    {
      "schema_version": 2,
      "written_at": "<ISO 8601 UTC>",
      "spawn_kind": "orchestrator",
      "spawn_id": "orchestrator-<round-N>",
      "deny_paths": [<flat list[str]>]
    }
    ```
  - Atomic write pattern: write to `lifecycle/sessions/<id>/sandbox-deny-lists/.<spawn-id>.json.tmp`, then `os.replace(tmp, final)`. POSIX `rename` is atomic on the same filesystem.
  - Files are NEVER overwritten — each spawn writes a new file keyed by `<spawn-id>`.
  - `mkdir(parents=True, exist_ok=True)` for the sandbox-deny-lists directory.
  - This task lands in coordination with #163 — the deny-list value being written is already in scope as a flat `list[str]` per spec Technical Constraints.
- **Verification**:
  - `grep -c 'sandbox-deny-lists' cortex_command/overnight/runner.py` ≥ 1 — pass if count ≥ 1.
  - `grep -c 'os.replace' cortex_command/overnight/runner.py` ≥ 1 — pass if count ≥ 1.
  - `grep -c 'isinstance(deny_paths, list)' cortex_command/overnight/runner.py` ≥ 1 — pass if count ≥ 1 (proves the structural guard for #163 shape compatibility is in place).
  - `python3 -c 'import inspect, cortex_command.overnight.runner as m; src=inspect.getsource(m); assert "sandbox-deny-lists" in src and "schema_version" in src and "isinstance(deny_paths" in src; print("PASS")'` — pass if PASS printed.
- **Status**: [x] complete (commit b804417)

### Task 5: Sidecar deny-list write at dispatch + LIFECYCLE_SESSION_ID env propagation

- **Files**: `cortex_command/pipeline/dispatch.py`
- **What**: (a) Mirror Task 4's sidecar write pattern at the per-feature dispatch site: write `lifecycle/sessions/<overnight-id>/sandbox-deny-lists/feature-<feature-slug>-<dispatch-N>.json` with `spawn_kind: "feature_dispatch"` after constructing the dispatch's deny-list. (b) In the `_env` construction block (around lines 530–534), explicitly add `LIFECYCLE_SESSION_ID` from `os.environ` to `_env` if present. Spec: R2 (dispatch portion) + R9.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Dispatch deny-list construction site: same as #163's modification point in `dispatch.py`. Locate via `grep -n 'denyWrite\|deny.write\|sandbox.filesystem' cortex_command/pipeline/dispatch.py`.
  - Feature slug is the per-feature dispatch's `feature_slug` (or equivalent identifier already present in the dispatch context). Dispatch counter `<dispatch-N>` is per-feature; if no counter exists, generate via a per-feature dispatch index passed in or derived.
  - Sidecar JSON schema is identical to T4 except `spawn_kind: "feature_dispatch"` and `spawn_id: "feature-<slug>-<dispatch-N>"`.
  - Env propagation pattern (R9): in the `_env: dict[str, str] = {"CLAUDECODE": ""}` block at lines 530–534, add a conditional propagation of `LIFECYCLE_SESSION_ID` from `os.environ` to `_env`. Mirror the walrus-assignment idiom already used immediately above for `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` — the implementer should follow that adjacent pattern verbatim, with `LIFECYCLE_SESSION_ID` substituted for the env-var name and dict key.
  - Atomic write same as T4: tempfile + `os.replace`. Per-feature dispatches run in parallel, so per-spawn-keyed paths are essential — never overwrite.
  - **Pre-write structural guard (required)**: same as T4 — `assert isinstance(deny_paths, list) and all(isinstance(p, str) for p in deny_paths)` before serializing the sidecar. Fails fast on #163 shape drift.
  - **Pre-#163 ordering**: same as T4 — if no deny-list construction exists at the dispatch site, do NOT stub or placeholder; surface the dependency and stall.
- **Verification**:
  - `grep -c 'sandbox-deny-lists' cortex_command/pipeline/dispatch.py` ≥ 1 — pass if count ≥ 1.
  - `grep -c 'LIFECYCLE_SESSION_ID' cortex_command/pipeline/dispatch.py` ≥ 1 — pass if count ≥ 1.
  - `grep -c 'isinstance(deny_paths, list)' cortex_command/pipeline/dispatch.py` ≥ 1 — pass if count ≥ 1 (structural guard for #163 shape).
  - `python3 -c 'import inspect; from cortex_command.pipeline.dispatch import dispatch_task; src=inspect.getsource(dispatch_task); assert "LIFECYCLE_SESSION_ID" in src; print("PASS")'` — pass if PASS printed.
- **Status**: [x] complete (commit 3937f13; spawn-id format uses skill+attempt+cycle for per-spawn uniqueness)

### Task 6: Add `collect_sandbox_denials` classifier

- **Files**: `cortex_command/overnight/report.py`
- **What**: Add module-level `PLUMBING_TOOLS` constant and known-plumbing-write-target mapping (per spec R3 enumeration). Implement `collect_sandbox_denials(session_id: str) -> dict[str, int]` that reads `lifecycle/sessions/<session_id>/tool-failures/bash.log` (YAML entries with `command:` and `stderr:` fields) and `lifecycle/sessions/<session_id>/sandbox-deny-lists/*.json` (UNION across all sidecar files), filters to entries whose stderr contains `Operation not permitted`, then runs the four-layer extraction: (L1) shell redirection targets; (L2) plumbing-tool subcommand mapping; (L3) plumbing fallthrough → `plumbing_eperm`; (L4) other fallthrough → `unclassified_eperm`. For L1/L2 candidate targets, look up against the union of sidecar `deny_paths` and classify by path-pattern (home_repo_refs/head/packed-refs, cross_repo_refs/head/packed-refs, other_deny_path). Read home/cross repo roots from `lifecycle/overnight-state.json`. Spec: R3.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**:
  - Module location: add to `cortex_command/overnight/report.py` near the existing `collect_tool_failures` function so naming/style match.
  - PLUMBING_TOOLS constant (verbatim per spec):
    ```
    PLUMBING_TOOLS = {"git", "gh", "npm", "pnpm", "yarn", "cargo", "hg", "jj"}
    ```
  - Known-plumbing-write-target mapping (verbatim subcommand→targets per spec):
    - `git commit` (and `git commit --amend`, `git merge`, `git rebase`, `git reset`) → `<repo>/.git/refs/heads/<HEAD>`, `<repo>/.git/HEAD`, `<repo>/.git/packed-refs`, `<repo>/.git/index`
    - `git push <remote> <branch>` → `<repo>/.git/refs/remotes/<remote>/<branch>`, `<repo>/.git/packed-refs`
    - `git tag <name>` → `<repo>/.git/refs/tags/<name>`
    - `git fetch` → `<repo>/.git/refs/remotes/...`, `<repo>/.git/FETCH_HEAD`
  - Layer 1 (shell redirection): scan command for `>file`, `>>file`, `tee file`, `echo … > file`, `cat … > file`. Use a focused tokenizer — full Bash parser not required.
  - Layer 2 (plumbing-tool mapping): strip optional `cd <dir> && …` prefix; if leading word in PLUMBING_TOOLS and subcommand in mapping → generate candidates relative to the `cd` arg or runner's known repo paths.
  - Layer 3: leading word in PLUMBING_TOOLS but no subcommand match → `plumbing_eperm`.
  - Layer 4: no plumbing leader → `unclassified_eperm`.
  - Path-pattern classification (after L1/L2 deny-list match):
    - `<home_repo_root>/.git/refs/heads/*` → `home_repo_refs`
    - `<home_repo_root>/.git/HEAD` → `home_repo_head`
    - `<home_repo_root>/.git/packed-refs` → `home_repo_packed_refs`
    - `<cross_repo_root>/.git/refs/heads/*` → `cross_repo_refs`
    - `<cross_repo_root>/.git/HEAD` → `cross_repo_head`
    - `<cross_repo_root>/.git/packed-refs` → `cross_repo_packed_refs`
    - any other path in deny-list → `other_deny_path`
  - **Repo-root resolution (heuristic, mirroring existing report.py:520 precedent)**: `OvernightState` (`cortex_command/overnight/state.py:255-274`) does not expose `home_repo_root` / `cross_repo_root` fields directly; closest available are `project_root: Optional[str]`, `integration_branches: dict[str, str]`, and per-feature `repo_path`. Use the same heuristic the existing `report.py:520` aggregator already uses for home/cross inference — derive at classification time, not via schema extension:
    - `home_repo_root = state.project_root` (the cortex repo running the overnight session). When `project_root` is None, treat home as unresolved.
    - `cross_repo_roots = sorted({f.repo_path for f in state.features if f.repo_path is not None and f.repo_path != state.project_root})` (the set of distinct non-home per-feature repo paths). When this set is empty, treat cross as unresolved.
    - For path-pattern matching, classify a sidecar deny-list path under `home_repo_*` if it lives under `home_repo_root`, or under `cross_repo_*` if it lives under any element of `cross_repo_roots`. Otherwise → `other_deny_path`.
    - **Heuristic limit (documented)**: when `project_root` is None or all features' `repo_path` values match `project_root`, the home vs cross distinction collapses and entries fall through to `other_deny_path`. This matches the existing `report.py:520` precedent's behavior. If the heuristic proves empirically insufficient (e.g., the morning report shows widespread `other_deny_path` counts that should be `home_repo_*`), file a follow-up ticket to extend the OvernightState schema explicitly — do not patch the heuristic in place.
  - **Top-level exception envelope (required)**: wrap the entire function body in a `try/except Exception as e:` that logs a warning to stderr and returns `{}`. This mirrors the existing `collect_tool_failures` precedent in `cortex_command/overnight/report.py` which wraps OSError/ValueError to prevent a single bad file from crashing the morning report. Without this envelope, an unhandled exception (yaml.YAMLError on malformed bash.log, OSError on permissions, AttributeError on non-dict YAML doc, KeyError on schema mismatch) propagates up through `collect_report_data` and kills the entire morning report — including completed-features, failed-features, and tool-failures sections that are unrelated to this change.
  - **Structural deny_paths guard (required)**: when reading each sidecar's `deny_paths` field, validate `isinstance(deny_paths, list) and all(isinstance(p, str) for p in deny_paths)` before adding to the union. If invalid, log a warning to stderr and skip that file's entries (treat as malformed). This is the reader-side mirror of T4/T5's writer-side guard — defense in depth against #163 shape drift across cortex versions.
  - **Per-entry shape guard**: when iterating YAML docs from `bash.log`, skip any doc that is not a dict (None, list, str). Use `if not isinstance(doc, dict): continue` before any `.get()` call.
  - Sidecar file handling: catch `json.JSONDecodeError` per file, log warning to stderr, skip malformed entries from the union.
  - Use Python YAML parser (e.g., `yaml.safe_load_all`) to parse the multi-document `bash.log` file format. The top-level exception envelope catches `yaml.YAMLError` from this call.
  - Return type: `dict[str, int]` mapping category → count. Categories enum (closed list per spec): `home_repo_refs`, `cross_repo_refs`, `home_repo_head`, `home_repo_packed_refs`, `cross_repo_head`, `cross_repo_packed_refs`, `other_deny_path`, `plumbing_eperm`, `unclassified_eperm`.
- **Verification**:
  - `python3 -c 'from cortex_command.overnight.report import collect_sandbox_denials, PLUMBING_TOOLS; assert "git" in PLUMBING_TOOLS and "gh" in PLUMBING_TOOLS; assert callable(collect_sandbox_denials); print("PASS")'` — pass if PASS printed.
  - **Exception envelope check**: `python3 -c 'from cortex_command.overnight.report import collect_sandbox_denials; r = collect_sandbox_denials("nonexistent-session-fixture-xyz"); assert r == {}; print("ENVELOPE_PASS")'` — pass if ENVELOPE_PASS printed (proves the function returns empty dict on absent session, not raising).
  - **Failure-injection** (proves the top-level envelope holds): construct a fixture session with a deliberately-malformed bash.log (e.g., `lifecycle/sessions/x-malformed/tool-failures/bash.log` containing `not: valid: yaml: at: all: ::: ---\n`); `python3 -c 'from cortex_command.overnight.report import collect_sandbox_denials; r = collect_sandbox_denials("x-malformed"); assert r == {}; print("INJECTION_PASS")'` — pass if INJECTION_PASS printed.
  - Functional positive-control: covered by Task 8's pytest fixture.
- **Status**: [x] complete (commit 54a23ce)

### Task 7: Add `render_sandbox_denials` + ReportData/generate_report wiring

- **Files**: `cortex_command/overnight/report.py`
- **What**: (a) Add `render_sandbox_denials(data: ReportData) -> str` that returns empty when `data.sandbox_denials` is empty; otherwise emits the markdown section per spec R4 (verbatim disclosure paragraph + bullet list with zero-count categories suppressed). (b) Add `sandbox_denials: dict[str, int] = field(default_factory=dict)` to `ReportData`. (c) Populate `data.sandbox_denials` in `collect_report_data()` via `collect_sandbox_denials(data.session_id)` after the existing `collect_tool_failures` call. (d) Append `render_sandbox_denials(data)` to `generate_report()`'s sections list, conditional on non-empty result. Spec: R4 + R5.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - Disclosure paragraph (verbatim per spec — must match exactly for grep verification):
    > Bash-routed sandbox denials caught by per-spawn `denyWrite` enforcement (#163). Within Bash scope, `git`/`gh`/`npm`-class plumbing denials are classified by command-target inference (precise) when the subcommand is in the known mapping and falls through to the `plumbing_eperm` bucket otherwise. Write/Edit/MCP escape paths are NOT covered — see #163 V1 scope.
  - Bullet rendering: emit one line per category with count ≥ 1; suppress zero-count lines. Order per spec:
    1. Home-repo refs
    2. Home-repo HEAD
    3. Home-repo packed-refs
    4. Cross-repo refs
    5. Cross-repo HEAD
    6. Cross-repo packed-refs
    7. Other deny-list paths
    8. Plumbing EPERM (likely sandbox, unmapped subcommand)
    9. Unclassified EPERM (likely non-sandbox: chmod / ACL / EROFS / gpg)
  - Total in heading: `## Sandbox Denials (<sum-of-all-counts>)`.
  - `ReportData` is a dataclass — locate via `grep -n '@dataclass\|class ReportData' cortex_command/overnight/report.py`. Add the new field with `field(default_factory=dict)` so backward compat is preserved (existing callers that don't set it get empty dict).
  - `collect_report_data` currently calls `collect_tool_failures(data.session_id)` — add the new `collect_sandbox_denials(data.session_id)` call directly after.
  - `generate_report` builds a sections list. Append `render_sandbox_denials(data)` conditionally (truthy check on the rendered string, since empty string evaluates falsy).
- **Verification**:
  - `python3 -c 'from cortex_command.overnight.report import ReportData, render_sandbox_denials; r=ReportData(); assert "sandbox_denials" in r.__dataclass_fields__; print("PASS")'` — pass if PASS printed.
  - `python3 -c 'from cortex_command.overnight.report import ReportData, render_sandbox_denials; r=ReportData(); r.sandbox_denials={"home_repo_refs": 2, "plumbing_eperm": 1}; out = render_sandbox_denials(r); assert "Bash-routed sandbox denials" in out and "Home-repo refs: 2" in out and "Plumbing EPERM" in out and "V1 scope" in out; print("PASS")'` — pass if PASS printed.
  - `python3 -c 'from cortex_command.overnight.report import ReportData, render_sandbox_denials; r=ReportData(); assert render_sandbox_denials(r) == ""; print("PASS")'` — pass if empty case returns empty string.
- **Status**: [x] complete (commit 1b4db34)

### Task 8: Positive-control acceptance test

- **Files**: `tests/test_report_sandbox_denials.py`
- **What**: New pytest test that constructs a fixture session under a temp directory containing: a fake `tool-failures/bash.log` with three YAML entries (Entry A: `cd /fixture && echo x > .git/refs/heads/main` → tests L1 redirection; Entry B: `cd /fixture && git commit -am 'msg'` → tests L2 plumbing mapping; Entry C: a `git`-prefixed command crafted to NOT match the known mapping → tests L3 fallthrough); two sidecar files (`orchestrator-1.json` listing `/fixture/.git/refs/heads/main`, `/fixture/.git/HEAD`, `/fixture/.git/packed-refs`; `feature-foo-1.json` listing `/other-repo/.git/refs/heads/main` to verify union behavior); a minimal `overnight-state.json` populating `project_root: "/fixture"` and a `features` list with one entry having `repo_path: "/other-repo"` (matching T6's heuristic for home/cross resolution). Asserts `collect_sandbox_denials(fixture_id)` returns ≥1 `home_repo_refs` count from each entry's match (entry A from L1, entry B from L2 mapping); asserts entry C contributes to `plumbing_eperm`. Asserts `render_sandbox_denials(data)` output contains the disclosure paragraph and at least one non-zero category line. Spec: R6.
- **Depends on**: [3, 6, 7]
- **Complexity**: complex
- **Context**:
  - Use `tmp_path` pytest fixture for isolation; chdir into the tmp path during test setup so the lifecycle path resolution works.
  - bash.log YAML format must match what Task 1 emits — multi-document YAML with `failure_num`, `tool`, `exit_code`, `timestamp`, `stderr` (literal block), `command` (literal block) per entry. Cross-reference Task 1's tracker output format to keep fixture in sync.
  - Sidecar JSON format must match Task 4/5 schema (`schema_version: 2`, `written_at`, `spawn_kind`, `spawn_id`, `deny_paths`).
  - `overnight-state.json` minimal shape: must populate `project_root: "/fixture"` (matching T6's home-repo heuristic) and a `features: [...]` list where one feature has `repo_path: "/other-repo"` (matching T6's cross-repo heuristic). The fixture must mirror the actual `OvernightState.to_dict()` shape — locate the canonical schema via `grep -n 'def to_dict\|def from_dict' cortex_command/overnight/state.py`.
  - Test assertions from spec: `home_repo_refs >= 1` from entry A, `home_repo_refs >= 1` from entry B (or distributed across `home_repo_head`/`home_repo_packed_refs`); `plumbing_eperm >= 1` from entry C; rendered output contains `"Bash-routed sandbox denials"` and `"V1 scope"`.
  - **Fixture scope clarity**: T8's fixture validates classifier reading against hand-authored input — it does NOT verify writer-reader integration (T1 tracker emission ↔ T6 classifier input, or T4/T5 sidecar emission ↔ T6 classifier input). The `home-repo root` field in the fixture's `overnight-state.json` and the flat-list shape of fixture sidecars match the contract T6 reads, but no automated test forces the runtime producers to honor that same contract. Writer-reader integration is verified manually via the smoke recipe in T9; T8 alone passing does not certify production correctness.
  - Cleanup is automatic via `tmp_path`.
- **Verification**: `pytest -v tests/test_report_sandbox_denials.py` — pass if exit 0 with all test cases PASSED. Acceptance threshold per spec: at least 3 PASSED tests (3 layer assertions or 3 fixture entries).
- **Status**: [x] complete (commit abc782b; 4 PASSED, ≥3 threshold met)

### Task 9: Documentation subsection + manual smoke recipe

- **Files**: `docs/overnight-operations.md`
- **What**: Add a new `### Sandbox-Violation Telemetry` subsection inside the Observability section (slot adjacent to the existing tool-failures-tracker mention). Cover: where denial signals come from (tracker captures `command` + `stderr`, sidecar deny-lists at each spawn), how morning-report categorization works (4 layers), what each category means, the Bash-only scope caveat, the within-Bash plumbing caveat, and a manual smoke recipe to deliberately induce a denial via a sandboxed `claude -p` invocation (e.g., a prompt that runs `cd $REPO_ROOT && git commit --allow-empty -m 'sandbox test'` from the orchestrator's Bash tool against a temp git repo with a known deny-list including `.git/refs/heads/main`) and confirm the morning report shows the count under `home_repo_refs`. Spec: R7 + R8.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - File: `docs/overnight-operations.md`. Locate the Observability section via `grep -n '^## Observability\|tool-failures' docs/overnight-operations.md`.
  - Slot the new `### Sandbox-Violation Telemetry` subsection immediately after the existing tool-failures content.
  - Required strings present in the subsection (per spec acceptance): `unclassified_eperm`, `plumbing_eperm`, `Bash-only`, `sandbox-deny-lists/`.
  - Manual smoke recipe is documentation only (cannot run as automated CI per spec — requires sandboxed `claude -p` invocation).
  - Keep prose concise; this is reference documentation, not a tutorial.
- **Verification**:
  - `grep -c '^### Sandbox-Violation Telemetry' docs/overnight-operations.md` = 1 — pass if exactly 1.
  - `grep -c 'unclassified_eperm' docs/overnight-operations.md` ≥ 1 AND `grep -c 'plumbing_eperm' docs/overnight-operations.md` ≥ 1 AND `grep -c 'Bash-only' docs/overnight-operations.md` ≥ 1 AND `grep -c 'sandbox-deny-lists/' docs/overnight-operations.md` ≥ 1 — pass if all four ≥ 1.
- **Status**: [x] complete (commit bf29b7a)

## Verification Strategy

End-to-end verification proceeds in four layers:

1. **Unit-level** — Tasks 1, 3, 4, 5, 6, 7, 9 each have grep-and-import command verifications proving the change landed at the right file/site, plus structural guards (T4/T5 `isinstance(deny_paths, list)` checks) proving cross-ticket contracts hold.
2. **Integration-level** — Task 2 (tracker shell test) and Task 8 (Python pytest fixture) exercise the tracker write-path and the classifier+renderer end-to-end against synthetic fixtures. Task 8 validates classifier reading only — writer-reader integration is verified by Layer 4.
3. **Failure-injection** — Task 1's parser-round-trip verification (multi-line + >4KB command emission round-trips through `yaml.safe_load_all`) and Task 6's exception-envelope checks (absent session returns empty dict; deliberately-malformed bash.log returns empty dict) prove the system fails closed rather than crashing the morning report.
4. **Live-system smoke (manual, documented in Task 9)** — Run an overnight session with a deliberately-induced denial (e.g., orchestrator child writes to `<tmp>/.git/refs/heads/main` with that path in deny-list); confirm `lifecycle/sessions/<id>/morning-report.md` contains the `## Sandbox Denials` section with the appropriate count and the disclosure paragraph. Layer 4 is the only path that exercises the real T1 tracker → T4/T5 sidecar writer → T6 classifier round-trip — Layers 2 and 3 cannot detect writer-reader contract drift. This is documentation, not an automated test, per spec R7.

The full automated suite is `just test` — pass if exit 0 after all tasks land.

## Veto Surface

- **Duplicate function consolidation in report.py is out of scope.** Spec explicitly defers this to a future cleanup ticket. Task 3 patches both duplicate definitions OR deletes the dead one if liveness analysis identifies one as dead. The smell itself remains. If reviewer prefers to bundle consolidation, expand T3 — but expect a ~4–8 task addition for safe cross-call-site refactoring.
- **Round/dispatch counter source.** Tasks 4 and 5 assume the runner already tracks a per-orchestrator-round counter and a per-feature dispatch counter. If neither exists, the task expands to add lightweight counters (likely 5 LOC each, but adds a small architectural decision the operator may want to weigh in on).
- **Repo-root identification source — RESOLVED (heuristic).** Critical-review found that `OvernightState` (`cortex_command/overnight/state.py:255-274`) exposes no `home_repo_root` / `cross_repo_root` fields. Resolution: T6 derives home/cross from existing fields using the same heuristic the existing `report.py:520` aggregator already uses — `home = state.project_root`; `cross = sorted({f.repo_path for f in state.features if f.repo_path is not None and f.repo_path != state.project_root})`. Path-pattern matches against these resolved roots; entries fall through to `other_deny_path` when both project_root and per-feature repo_path are unresolved. Documented limit: if the heuristic proves empirically insufficient (e.g., widespread `other_deny_path` counts that should be home/cross), file a follow-up ticket to extend the schema rather than patch the heuristic in place. Path (a) — explicit schema extension — was rejected as premature given the existing in-codebase precedent. Path (c) — drop the taxonomy — was rejected as discarding information the existing infrastructure already produces correctly.
- **Collector exception envelope is in scope (load-bearing).** T6's `collect_sandbox_denials` is wired upstream of every render call in `collect_report_data`. Without a top-level try/except (added by this plan's T6 update), a malformed `bash.log` YAML doc kills the entire morning report — including completed-features, failed-features, and tool-failures sections. The envelope mirrors the existing `collect_tool_failures` precedent. If reviewer prefers a finer-grained exception strategy (per-entry try/except, distinct logging tags per failure mode), expand T6 — but the broad-envelope default is the conservative ship.
- **Pre-#163 ordering is not enforced by task verification.** Tasks 4 and 5 assume #163 has landed (or co-merges); their structural guards fail fast if the deny-list value is wrong shape, but neither the plan's ordering nor any verification command enforces "do not merge #164 before #163." If #164 lands first, T4/T5 implementation cannot proceed (no insertion anchor, no deny-list value to consume) — the `## Veto Surface` policy is "stall the task and surface the dependency to the operator," NOT "stub a placeholder."

## Scope Boundaries

(Mirrors spec Non-Requirements.)

- No new hook ships — Alternative D handles classification at report-render time in Python.
- No new `sandbox_denial` event type emitted to events.log — verified zero downstream consumers beyond morning report.
- No new `additionalContext` in-session signal — existing tracker's threshold-3 generic-failure surface is unchanged.
- No `CORTEX_RUNNER_CHILD` env-var gate — moot under D since no new hook to gate.
- No coverage of Write/Edit/MCP escape paths — Bash-only per #163 V1 scope; morning-report wording discloses this.
- No coverage of plumbing tools beyond the closed `PLUMBING_TOOLS` enumeration; unmapped subcommands fall to `plumbing_eperm`.
- No retroactive backfill of pre-existing session directories.
- No consolidation of duplicate `collect_tool_failures` / `render_tool_failures` definitions in report.py (out of scope; one may be dead-code-deleted in T3).
