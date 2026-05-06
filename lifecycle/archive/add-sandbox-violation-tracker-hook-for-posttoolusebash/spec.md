# Specification: Add sandbox-violation telemetry to morning report

> Backlog: [[164-add-sandbox-violation-tracker-hook-for-posttooluse-bash]]
> Parent epic: 162. Blocker: #163.
> Approach: **Alternative D** (Python at report-render time; no new hook). User-confirmed during spec interview.

## Problem Statement

After ticket #163 lands kernel-level `sandbox.filesystem.denyWrite` enforcement, sandbox-blocked Bash writes from overnight-spawned children surface as generic non-zero Bash exits with `Operation not permitted` in stderr — indistinguishable from chmod / ACL / EROFS denials. The morning report has no signal that an agent attempted a denied write, so a user cannot tell whether agents are routing toward escapes that #163 successfully blocked. This ticket classifies sandbox-routed denials in the morning report so misbehavior is visible even when the kernel correctly stopped it.

A latent precondition surfaced during research: the existing `cortex-tool-failure-tracker.sh` writes failure logs keyed on the Claude SDK session UUID, while every reader in `cortex_command/overnight/report.py` is keyed on the cortex overnight-id (`overnight-YYYY-MM-DD-HHMM`). The two namespaces never coincide, so the existing `tool_failures` aggregation reads paths the hook never writes to and is silently always empty. This bug must be fixed for any morning-report classification to deliver value, so it is in scope here per the spec interview.

## Requirements

1. **Tracker write-side namespace fix.** `claude/hooks/cortex-tool-failure-tracker.sh` reads `$LIFECYCLE_SESSION_ID` from its environment; when set and non-empty, it writes its `${TOOL_KEY}.count` and `${TOOL_KEY}.log` files under `lifecycle/sessions/${LIFECYCLE_SESSION_ID}/tool-failures/` instead of `/tmp/claude-tool-failures-${INPUT.session_id}/`. When `$LIFECYCLE_SESSION_ID` is unset (interactive sessions outside an overnight run), the tracker retains its current `/tmp/claude-tool-failures-${INPUT.session_id}/` path. Modeled on `claude/hooks/cortex-permission-audit-log.sh:22-25`.
   *Acceptance:* `bash -c 'LIFECYCLE_SESSION_ID=overnight-2026-01-01-0000 echo {\"tool_name\":\"Bash\",\"tool_response\":{\"exit_code\":1,\"stderr\":\"x\"},\"session_id\":\"abc\"} | claude/hooks/cortex-tool-failure-tracker.sh'` produces a file at `lifecycle/sessions/overnight-2026-01-01-0000/tool-failures/bash.log` (verified by `[[ -f lifecycle/sessions/overnight-2026-01-01-0000/tool-failures/bash.log ]] && echo PASS`). Same invocation without `LIFECYCLE_SESSION_ID` produces a file under `/tmp/claude-tool-failures-abc/bash.log`.

1a. **Aggregator read-side namespace fix.** All four `/tmp/claude-tool-failures-{session_id}` references in `cortex_command/overnight/report.py` — at lines 246 (in `collect_tool_failures` def at line 223), 1094 (in `collect_tool_failures` def at line 1079), and any equivalent reads in the `render_tool_failures` defs at lines 1156 and 1430 — are updated to prefer `lifecycle/sessions/{session_id}/tool-failures/` and fall back to `/tmp/claude-tool-failures-{session_id}/` only when the lifecycle path is absent. The two duplicate function definitions are not consolidated by this ticket (out of scope) but both must be patched or one must be removed if it is dead code; whichever path is dead must be deleted to prevent re-divergence.
   *Acceptance:* `grep -c '/tmp/claude-tool-failures-' cortex_command/overnight/report.py` returns the same count post-fix as pre-fix only if the `/tmp` paths remain as fallback-only conditionals; otherwise returns 0. After the change, `python3 -c 'from cortex_command.overnight.report import collect_tool_failures; import pathlib, json, os; os.makedirs("lifecycle/sessions/x/tool-failures", exist_ok=True); pathlib.Path("lifecycle/sessions/x/tool-failures/bash.count").write_text("3"); pathlib.Path("lifecycle/sessions/x/tool-failures/bash.log").write_text("---\nfailure_num: 3\ntool: Bash\nexit_code: 1\ntimestamp: 2026-05-04T00:00:00Z\nstderr: |\n  x\n"); print(collect_tool_failures("x"))'` returns a non-empty dict.

2. **Sandbox deny-list sidecar contract.** Both overnight spawn sites — `cortex_command/overnight/runner.py` (orchestrator spawn) and `cortex_command/pipeline/dispatch.py` (per-feature dispatch) — write a per-spawn JSON file at `lifecycle/sessions/<overnight-id>/sandbox-deny-lists/<spawn-id>.json` immediately after constructing the `--settings` deny-list for the spawn. Files are NEVER overwritten — each spawn writes a new file keyed by `<spawn-id>` (a uniquely-generated identifier per spawn; e.g., orchestrator spawns use `orchestrator-<round-N>` and per-feature dispatches use `feature-<feature-slug>-<dispatch-N>`). Writes are atomic via tempfile + `os.replace` (write to `lifecycle/sessions/<id>/sandbox-deny-lists/.<spawn-id>.json.tmp` then `os.replace` to the final path).
   *Sidecar JSON schema:*
   ```json
   {
     "schema_version": 2,
     "written_at": "2026-05-04T03:14:15Z",
     "spawn_kind": "orchestrator" | "feature_dispatch",
     "spawn_id": "<unique-per-spawn>",
     "deny_paths": [
       "/abs/path/.git/refs/heads/main",
       "/other/repo/.git/refs/heads/main",
       ...
     ]
   }
   ```
   `deny_paths` is a flat `list[str]` — no category metadata. The runner's deny-list construction (#163's responsibility) produces only paths; this ticket's aggregator owns classification. The sidecar's only job is to record which paths were denied at each spawn so the aggregator can union across all spawns and avoid losing entries when multiple spawns occur in one session.
   *Acceptance:* `python3 -c 'import json,glob,sys; files=sorted(glob.glob("lifecycle/sessions/$LATEST_OVERNIGHT_ID/sandbox-deny-lists/*.json")); assert len(files) >= 1; [json.load(open(f)) for f in files]; assert all(json.load(open(f))["schema_version"]==2 and isinstance(json.load(open(f))["deny_paths"], list) for f in files)'` exits 0 after one orchestrator spawn followed by ≥1 per-feature dispatch.

3. **Aggregator: classifier.** New module-level constant in `cortex_command/overnight/report.py`:
   ```
   PLUMBING_TOOLS = {"git", "gh", "npm", "pnpm", "yarn", "cargo", "hg", "jj"}
   ```
   plus a known-plumbing-write-target mapping (e.g., `git commit` → candidate write targets `<repo>/.git/refs/heads/<HEAD>`, `<repo>/.git/HEAD`, `<repo>/.git/packed-refs`, `<repo>/.git/index`; `git push <remote> <branch>` → `<repo>/.git/refs/remotes/<remote>/<branch>`, `<repo>/.git/packed-refs`; `git tag <name>` → `<repo>/.git/refs/tags/<name>`; `git fetch` → `<repo>/.git/refs/remotes/...`, `<repo>/.git/FETCH_HEAD`; `git merge`, `git rebase`, `git reset`, `git commit --amend` → equivalent to `git commit`). Repo-relative targets are resolved by parsing `cd <dir> && …` prefixes and (where present) matching against the deny-list's repo prefixes.

   New function `collect_sandbox_denials(session_id: str) -> dict[str, int]`. Reads:
   - `lifecycle/sessions/<session_id>/tool-failures/bash.log` (the tracker's per-session bash failure log produced by R1).
   - `lifecycle/sessions/<session_id>/sandbox-deny-lists/*.json` (UNION of all sidecar deny-lists from all spawns in the session, produced by R2).

   For each YAML-block entry in `bash.log`: parse the `tool_input.command` field (R3a) and the `stderr` field. Filter to entries where stderr contains `Operation not permitted`. For each entry, extract candidate write targets in this order:
   - **Layer 1 — shell redirection**: scan command for `>file`, `>>file`, `tee file`, `echo … > file`, `cat … > file` forms. Extract redirect target(s).
   - **Layer 2 — plumbing-tool mapping**: if the leading command word (after optional `cd <dir> && …` prefix) is in `PLUMBING_TOOLS`, look up the subcommand in the known-plumbing-write-target mapping; if found, generate candidate write targets relative to the repo dir (the `cd` arg or the runner's known repo paths).
   - **Layer 3 — plumbing-tool fallback**: if the leading command is in `PLUMBING_TOOLS` but no specific subcommand mapping matched, mark as `plumbing_eperm` candidate.
   - **Layer 4 — fallthrough**: otherwise, mark as `unclassified_eperm` candidate.

   Then for each candidate write target from Layers 1 or 2, look it up in the union of all sidecar `deny_paths` arrays. If matched, classify the entry by path-pattern derived in Python:
   - `<home_repo_root>/.git/refs/heads/*` → `home_repo_refs`
   - `<home_repo_root>/.git/HEAD` → `home_repo_head`
   - `<home_repo_root>/.git/packed-refs` → `home_repo_packed_refs`
   - `<cross_repo_root>/.git/refs/heads/*` → `cross_repo_refs`
   - `<cross_repo_root>/.git/HEAD` → `cross_repo_head`
   - `<cross_repo_root>/.git/packed-refs` → `cross_repo_packed_refs`
   - any other path in the sidecar deny-list → `other_deny_path`

   The home-repo root and cross-repo roots are inferred at classification time by reading `lifecycle/overnight-state.json` (or equivalent state surface) — NOT from the sidecar (which contains paths only).

   If Layer 1 or Layer 2 produced a candidate target but the deny-list lookup did NOT match, fall through to the Layer 3/4 buckets above. Returns a dict mapping category → count. Categories enum: `home_repo_refs`, `cross_repo_refs`, `home_repo_head`, `home_repo_packed_refs`, `cross_repo_head`, `cross_repo_packed_refs`, `other_deny_path`, `plumbing_eperm`, `unclassified_eperm`.

   *Acceptance:* `python3 -c 'from cortex_command.overnight.report import collect_sandbox_denials; print(collect_sandbox_denials("test-fixture-session"))'` against the fixture session in `tests/fixtures/` returns the expected dict with both a `home_repo_refs` count from a `git commit` entry AND a `home_repo_refs` count from an `echo > .git/refs/heads/main` entry (test fixture spec'd in R6).

3a. **Tracker captures `tool_input.command`.** The tracker is extended to write a `command:` field in each failure log entry alongside the existing `stderr:` block, so the aggregator can parse write targets. Field is multiline-safe (YAML literal block scalar, `command: |`). Truncate command to the first 4KB at write time to bound storage; matches existing 20-line `stderr` cap.
   *Acceptance:* `grep -A1 '^command: |' lifecycle/sessions/<id>/tool-failures/bash.log | head` after a denial-induced failure shows the original command string.

4. **Aggregator: render_sandbox_denials.** New function `render_sandbox_denials(data: ReportData) -> str` in `cortex_command/overnight/report.py`. Returns the empty string when `data.sandbox_denials` is empty (no section in the report). Otherwise returns a markdown section in the form:
   ```markdown
   ## Sandbox Denials (<total>)

   Bash-routed sandbox denials caught by per-spawn `denyWrite` enforcement (#163). Within Bash scope, `git`/`gh`/`npm`-class plumbing denials are classified by command-target inference (precise) when the subcommand is in the known mapping and falls through to the `plumbing_eperm` bucket otherwise. Write/Edit/MCP escape paths are NOT covered — see #163 V1 scope.

   - Home-repo refs: N
   - Home-repo HEAD: N
   - Home-repo packed-refs: N
   - Cross-repo refs: M
   - Cross-repo HEAD: M
   - Cross-repo packed-refs: M
   - Other deny-list paths: K
   - Plumbing EPERM (likely sandbox, unmapped subcommand): P
   - Unclassified EPERM (likely non-sandbox: chmod / ACL / EROFS / gpg): U
   ```
   Suppress zero-count category lines from the output (only emit lines for categories with count ≥ 1). The two-sentence prose paragraph above the bullet list MUST appear verbatim — it is the disclosure paragraph required by Adversarial #A9 plus the within-Bash plumbing caveat raised by critical review.
   *Acceptance:* `grep -F 'Bash-routed sandbox denials' lifecycle/sessions/<id>/morning-report.md` returns one match after a session with ≥1 denial. `grep -F 'V1 scope' lifecycle/sessions/<id>/morning-report.md` returns one match. `grep -F 'plumbing_eperm' lifecycle/sessions/<id>/morning-report.md` returns one match.

5. **ReportData and generate_report integration.** `ReportData` gains a `sandbox_denials: dict[str, int] = field(default_factory=dict)` field. `collect_report_data()` populates it via `collect_sandbox_denials(data.session_id)` after the existing `collect_tool_failures` call. `generate_report()` appends `render_sandbox_denials(data)` to its sections list, conditional on non-empty result.
   *Acceptance:* `python3 -c 'from cortex_command.overnight.report import ReportData; r=ReportData(); assert "sandbox_denials" in r.__dataclass_fields__'` exits 0.

6. **Positive-control acceptance test.** A test in `tests/test_report_sandbox_denials.py` (or equivalent path matching repo convention) constructs a fixture session under a temp directory containing:
   - A fake `tool-failures/bash.log` with TWO entries:
     - Entry A: command = `cd /fixture && echo x > .git/refs/heads/main`, stderr contains `Operation not permitted`. Tests Layer 1 (shell redirection).
     - Entry B: command = `cd /fixture && git commit -am 'msg'`, stderr contains `Operation not permitted`. Tests Layer 2 (plumbing-tool mapping for `git commit`).
   - A `sandbox-deny-lists/orchestrator-1.json` listing `/fixture/.git/refs/heads/main`, `/fixture/.git/HEAD`, `/fixture/.git/packed-refs`.
   - A `sandbox-deny-lists/feature-foo-1.json` listing only `/other-repo/.git/refs/heads/main` (a different deny-list to verify the union behavior).
   - A minimal `overnight-state.json` declaring `/fixture` as the home-repo root.

   Asserts `collect_sandbox_denials(fixture_id)` returns a dict where `home_repo_refs >= 2` (one from entry A, one from entry B; entry B may also contribute to `home_repo_head` or `home_repo_packed_refs` since `git commit` writes multiple refs — assert at least the `home_repo_refs` count is ≥ 1 from each entry's write-target match). Asserts `render_sandbox_denials(...)` output contains the disclosure paragraph and at least one non-zero category line.

   Add a third entry C: command = `git push origin some-unmapped-subcommand-variant`, stderr contains `Operation not permitted`, but the subcommand is hand-crafted to NOT match the known-plumbing mapping. Assert this entry contributes to `plumbing_eperm`, demonstrating the Layer 3 fallthrough.
   *Acceptance:* `just test` exits 0; the new test is observed by `pytest -v tests/test_report_sandbox_denials.py | grep -c PASSED >= 3`.

6a. **Tracker shell-test extension.** `tests/test_tool_failure_tracker.sh` is extended with a new test case that drives the hook with `LIFECYCLE_SESSION_ID=overnight-fixture-test` set and asserts the output appears at `lifecycle/sessions/overnight-fixture-test/tool-failures/bash.log` (NOT `/tmp/claude-tool-failures-*/`). Existing test cases (which drive without LIFECYCLE_SESSION_ID) remain unchanged and continue to assert the `/tmp` fallback path.
   *Acceptance:* `bash tests/test_tool_failure_tracker.sh` exits 0; the existing assertions and the new lifecycle-path assertion both pass; `grep -c 'lifecycle/sessions' tests/test_tool_failure_tracker.sh >= 1`.

7. **End-to-end smoke verification documented (recommended, non-blocking).** `docs/overnight-operations.md` includes a one-paragraph manual smoke recipe under the new Sandbox-Violation Telemetry subsection: how to construct a session with a deliberately-induced denial (e.g., a prompt that drives `cd $REPO_ROOT && git commit --allow-empty -m 'sandbox test'` from the orchestrator's Bash tool against a temp git repo with a known deny-list including `.git/refs/heads/main`) and confirm the morning report shows the count under `home_repo_refs`. Recipe runs against #163's machinery; cannot run as an automated test because it requires a sandboxed `claude -p` invocation. This is documentation, not a CI check.
   *Acceptance:* `grep -c '^### Sandbox-Violation Telemetry' docs/overnight-operations.md` returns 1.

8. **Documentation subsection.** `docs/overnight-operations.md` gains a new `### Sandbox-Violation Telemetry` subsection inside the Observability section (slot it adjacent to the existing tool-failures-tracker mention). Subsection covers: where denial signals come from (tracker captures, sidecar deny-lists), how the morning-report categorization works (shell-redirection layer, plumbing-tool mapping layer, plumbing-fallback layer, unclassified fallthrough), what each category means, the Bash-only scope caveat, the within-Bash plumbing caveat, and the manual smoke recipe (R7).
   *Acceptance:* `grep -c '^### Sandbox-Violation Telemetry' docs/overnight-operations.md` returns 1; the subsection contains the strings `unclassified_eperm`, `plumbing_eperm`, `Bash-only`, and `sandbox-deny-lists/`.

9. **Defensive env-var propagation in dispatch path.** `cortex_command/pipeline/dispatch.py` (around lines 530–534, where `_env` is constructed) explicitly adds `LIFECYCLE_SESSION_ID` to `_env` if present in `os.environ`. Without this, the per-feature dispatch path's PostToolUse hook spawn relies on subprocess-inheritance behavior asserted by an inline comment ("the SDK merges options.env on top of os.environ") that the spec does not verify; making the propagation explicit removes the dependency on that unverified assumption and ensures R1's lifecycle-path branch fires for dispatch-spawned children.
   *Acceptance:* `grep -F 'LIFECYCLE_SESSION_ID' cortex_command/pipeline/dispatch.py` returns ≥1 match. `python3 -c 'import inspect; from cortex_command.pipeline.dispatch import dispatch_task; src = inspect.getsource(dispatch_task); assert "LIFECYCLE_SESSION_ID" in src'` exits 0.

## Non-Requirements

- **No new hook ships.** Alternative D explicitly rejects the original ticket's "new sibling hook" approach. Classification is in Python at report-render time, not in shell at every Bash tool call.
- **No new event type in events.log.** No `sandbox_denial` event is emitted to `lifecycle/sessions/<id>/overnight-events.log` because verified analysis showed no consumer of typed events.log entries beyond the morning report (Codebase Analysis cross-checked `dashboard/data.py` and `runner.py:read_events`). If a future consumer needs typed events, file a follow-up; do not pre-emit.
- **No additionalContext in-session signal.** Under D, the existing tool-failure-tracker still emits its threshold-3 generic-failure additionalContext; this ticket adds NO new in-session nudge for sandbox-classified failures specifically. Behavior change happens at morning-report time only.
- **No env-var gate via `CORTEX_RUNNER_CHILD`.** Under D, there is no new hook to gate, and the tracker fix (R1) keys on `$LIFECYCLE_SESSION_ID` (set in overnight contexts only, per `runner.py:1920` for the orchestrator spawn and R9's defensive addition for the dispatch spawn). The proposed `CORTEX_RUNNER_CHILD=1` gate from the original ticket is moot.
- **No coverage of Write/Edit/MCP escape paths.** Per #163's V1 threat-model boundary, only Bash-routed denials are observed. The morning-report wording (R4) discloses this explicitly to prevent false reassurance.
- **No coverage of plumbing tools beyond the known-mapping enumeration.** The plumbing-tool mapping in R3 covers `git` core operations (commit, push, fetch, tag, merge, rebase, reset, commit --amend) plus the closed enumeration of plumbing-tool prefix words in `PLUMBING_TOOLS`. Other tools (e.g., `mercurial`, `svn`, `bazaar`, future package managers) fall into `unclassified_eperm` until the mapping is extended. Tools in `PLUMBING_TOOLS` whose subcommand is NOT in the mapping fall into `plumbing_eperm` (a safer bucket than `unclassified_eperm`). Adding new tools or new git subcommands is a future-ticket extension, not a regression.
- **No `git` subcommand parse beyond the known mapping.** `git rev-parse … | xargs git update-ref` and similar low-level plumbing chains fall into `plumbing_eperm`; this is acceptable because (a) those forms are rare in agent-generated commands and (b) the `plumbing_eperm` bucket is signal-rich enough to flag suspicion.
- **No retroactive backfill.** This ticket only classifies denials in sessions written AFTER the tracker fix and sidecar contract land. Pre-existing session directories are not migrated.
- **Duplicate `collect_tool_failures` / `render_tool_failures` definitions in `report.py` are not consolidated.** R1a fixes both (or removes whichever is dead), but cleaning up the duplicate-definition smell itself is out of scope.

## Edge Cases

- **Sidecar directory missing.** `lifecycle/sessions/<id>/sandbox-deny-lists/` does not exist (e.g., session ran before this ticket landed, or both spawn-write steps crashed). Aggregator returns an empty dict for the union; render produces no section. This is non-blocking — morning report still renders for everything else.
- **Sidecar file present but malformed JSON.** Concurrent or interrupted writes to a sidecar could in principle produce torn JSON, although R2's tempfile + `os.replace` pattern is intended to prevent this (POSIX `rename` is atomic on the same filesystem). Aggregator catches `json.JSONDecodeError` per file, logs a warning to stderr, and skips that file's entries from the union. Other files in the directory still contribute. Non-blocking.
- **Tool-failures log missing.** `lifecycle/sessions/<id>/tool-failures/bash.log` does not exist (e.g., no Bash failures occurred in the session). Aggregator returns an empty dict; render produces no section.
- **Mid-overnight upgrade (split storage).** A long-running overnight session begins with the pre-fix tracker writing to `/tmp/claude-tool-failures-<UUID>/`, the user upgrades cortex mid-session, and post-upgrade Bash failures land at `lifecycle/sessions/<overnight-id>/tool-failures/bash.log`. The aggregator at report time reads ONLY the lifecycle path (it does NOT correlate UUID-keyed `/tmp` dirs to overnight-id). Pre-upgrade failures in `/tmp` are silently dropped from this session's classification. This is documented as a known limitation; users who upgrade mid-overnight should re-run any in-flight features to capture telemetry. Acceptable post-migration; pre-migration this preserves the existing silent-empty behavior.
- **Tool-failures log present but tracker is pre-fix version.** When the tracker hasn't been upgraded but the aggregator has (transition window), the log lives at `/tmp/claude-tool-failures-<UUID>/bash.log`. R1a's fallback chain (lifecycle path preferred; `/tmp` fallback) means the aggregator finds the `/tmp` log if the lifecycle path is absent — but only if the SDK UUID happens to match the overnight-id (it doesn't). So pre-fix tracker logs remain unread. Acceptable: this is the fallback-chain order, not a regression.
- **Sidecar present but `deny_paths` is empty.** Aggregator's union is non-empty (the file existed) but no entries match because the deny-list contained no paths. All EPERM entries fall through to Layer 3/4 (`plumbing_eperm` or `unclassified_eperm`). Reasonable behavior — if no paths were denied, no targeted classifications are possible.
- **Concurrent spawn writes.** Per-feature dispatches run in parallel. R2 mandates per-spawn-keyed file paths so two spawns NEVER write to the same file. This eliminates the torn-write race entirely.
- **Command field contains binary data or extreme length.** Tracker emits via YAML literal block scalar (`command: |`); aggregator reads via Python YAML parser. Tracker truncates command to first 4KB at write time per R3a.
- **`Operation not permitted` in stderr but command writes nothing matching the deny-list.** Examples: `gpg --sign` against ACL-restricted `~/.gnupg/`, `chmod` against an ACL-protected file, `cargo build` link-time EPERM. These bucket as `unclassified_eperm` (NOT `plumbing_eperm`, since the leading command word is not in `PLUMBING_TOOLS`). The morning-report disclosure paragraph discloses this bucket's likely-non-sandbox composition explicitly.
- **`Operation not permitted` from a `PLUMBING_TOOLS` command but no specific subcommand match.** Example: `git config --global …` (which writes `~/.gitconfig`, denied by sandbox if `~/.gitconfig` is in the deny-list — though this is unusual). Buckets as `plumbing_eperm`.
- **Same denied path written twice in one session.** Two entries in `bash.log`, two count increments. The morning-report shows total attempts; not deduplicated by path. (If deduplication is desired later, the aggregator can be extended; not in scope.)
- **`git commit` writes multiple ref paths simultaneously.** `git commit` updates `.git/refs/heads/<HEAD>`, `.git/HEAD`, `.git/packed-refs`, `.git/index`. The sandbox blocks the FIRST denied write the kernel encounters, and stderr typically reflects only that one. The aggregator generates ALL candidate write targets from the mapping and matches against the deny-list; if any match, the entry classifies under the matched category. This may inflate counts slightly (one denied attempt → one count) but the count is per-attempt, not per-distinct-path.
- **`$LIFECYCLE_SESSION_ID` is set but `lifecycle/sessions/<id>/` does not exist on disk.** Tracker creates the directory via `mkdir -p ... 2>/dev/null || true` (the existing pattern). If creation fails (read-only fs, permission denied), the append falls through silently and the hook still exits 0. Non-blocking observability invariant preserved.
- **Sidecar's `<spawn-id>` collides across two overnight sessions in the same lifecycle dir.** Cannot happen — each session has its own `lifecycle/sessions/<overnight-id>/` directory, so spawn-id collisions across sessions don't share a directory.

## Changes to Existing Behavior

- **MODIFIED**: `claude/hooks/cortex-tool-failure-tracker.sh` storage location. Currently writes to `/tmp/claude-tool-failures-${INPUT.session_id}/`. After this ticket: writes to `lifecycle/sessions/${LIFECYCLE_SESSION_ID}/tool-failures/` when `$LIFECYCLE_SESSION_ID` is set; falls back to `/tmp/claude-tool-failures-${INPUT.session_id}/` otherwise. Net effect on overnight runs: storage moves from `/tmp` to a session-scoped lifecycle path. Net effect on interactive runs: unchanged.
- **MODIFIED**: all four `/tmp/claude-tool-failures-{session_id}` reader references in `cortex_command/overnight/report.py` (R1a) — both `collect_tool_failures` defs (lines 223 and 1079) and both `render_tool_failures` defs (lines 1156 and 1430). Each is updated to prefer `lifecycle/sessions/{session_id}/tool-failures/` and fall back to `/tmp` only when the lifecycle path is absent. The "two duplicate function definitions" smell is preserved (out of scope to consolidate).
- **MODIFIED**: `cortex_command/pipeline/dispatch.py` `_env` construction (around lines 530–534). Adds an explicit conditional propagation of `LIFECYCLE_SESSION_ID` from `os.environ` to `_env`, removing dependence on the unverified subprocess-inheritance comment.
- **ADDED**: tracker emits a `command:` field per failure entry (R3a), in addition to existing `failure_num`, `tool`, `exit_code`, `timestamp`, `stderr` fields. Backward-compatible: any consumer that doesn't know about `command:` ignores the extra field.
- **ADDED**: `lifecycle/sessions/<id>/sandbox-deny-lists/<spawn-id>.json` files written by the runner at each overnight spawn site. New persistent state directory and per-spawn JSON files, schema-versioned. Lives under the existing `lifecycle/sessions/` allowlist (no `cortex init` change required).
- **ADDED**: `## Sandbox Denials` section in morning report when ≥1 classified denial occurs.
- **ADDED**: `### Sandbox-Violation Telemetry` subsection in `docs/overnight-operations.md`.
- **ADDED**: a new entry in `tests/test_tool_failure_tracker.sh` covering the `$LIFECYCLE_SESSION_ID` branch (R6a). Existing test cases remain.

## Technical Constraints

- **Plugin-hook env-var propagation gap.** anthropics/claude-code#9447 reports custom env vars do not propagate to plugin-hook spawn. Under Alternative D, no new hook is added — the tracker remains in `claude/hooks/` (canonical, not plugin-form), and the existing `cortex-permission-audit-log.sh:22-25` precedent confirms `$LIFECYCLE_SESSION_ID` IS visible to canonical-form hooks today. This collapses the propagation concern that the original ticket's hook design surfaced. R9 further removes any remaining ambiguity for the dispatch path by explicitly propagating the env var instead of depending on inheritance.
- **macOS Seatbelt structured denials go to unified log, not stderr.** The aggregator never sees the structured `Sandbox: bash(PID) deny(1) ...` line; classification depends on `tool_input.command` parse + sidecar match, not stderr regex pattern matching. Bare-stderr `Operation not permitted` matching is the documented anti-pattern (openai/codex#18711) and is explicitly avoided here — the aggregator uses stderr ONLY to confirm a non-zero exit was an EPERM-shaped failure, not to classify which kind of EPERM.
- **Linux bwrap denials produce pure POSIX EPERM with no marker.** Same approach works: command-target match against sidecar deny-list. No platform-specific code path required.
- **Plumbing-tool mapping coupling to git internals.** The known-plumbing-write-target mapping in R3 encodes git's internal ref-write paths (`.git/refs/heads/<HEAD>`, etc.). If git's on-disk format changes (extremely unlikely in the near term), the mapping will go stale. This is acceptable: the `plumbing_eperm` fallback bucket catches denials that the precise mapping misses, so signal is preserved even when precision degrades.
- **Sidecar write must be additive at #163's spawn sites.** This ticket modifies `runner.py` and `pipeline/dispatch.py` at the exact lines #163 already modifies. Implementation must coordinate with #163's branch state — the sidecar-write code is layered after #163's deny-list construction (it consumes the same deny-list value, treated as a flat `list[str]` per R2's schema), so #163 must land first or the two PRs must merge together. The schema is decoupled from #163's internal categorization (none required from #163).
- **`LIFECYCLE_SESSION_ID` is exported in `cortex_command/overnight/runner.py:1920`** before any spawn. Inherited by orchestrator-spawn child processes via the runner's `os.environ` mutation. For dispatch-path children, R9 explicitly propagates the var into the SDK options env to remove inheritance ambiguity.
- **`log_event()` in `cortex_command/overnight/events.py:194` is NOT used.** This ticket explicitly does not emit a typed event (Non-Requirements). Aggregator reads tracker logs and the sidecar files directly.
- **Hook fails non-blocking.** `claude/hooks/cortex-tool-failure-tracker.sh` already exits 0 unconditionally and uses `2>/dev/null || true` for write paths. The R1/R3a edits preserve this invariant.
- **`docs/overnight-operations.md` is the canonical owner per CLAUDE.md.** No new doc files are created; existing doc gains a subsection.

## Open Decisions

- **Cross-ticket interface with #163 is a known dependency.** #163 carries `status: ready` (not yet refined). This spec assumes #163's deny-list construction emits a flat `list[str]` of denied paths (the simplest possible shape consistent with `sandbox.filesystem.denyWrite`'s actual schema, per parent research DR-1). If #163's spec phase produces a richer shape (e.g., a structured object with metadata), R2's sidecar code can still consume the flat-paths projection — but if #163's deny-list construction is refactored into a shared helper that prevents in-place sidecar writing at the spawn sites, R2 may need to be revised to write the sidecar from inside the helper. This dependency is enumerated, not resolved — implementation must coordinate with #163's eventual spec/PR.
- **Whether to consolidate the duplicate `collect_tool_failures` / `render_tool_failures` definitions in `report.py`.** Out of scope per Non-Requirements. The deferral reason: collapsing the two function definitions requires cross-cutting analysis of which call sites use which, and at least one of the duplicates is likely dead code that should be deleted rather than merged. That analysis belongs in a separate cleanup ticket.
