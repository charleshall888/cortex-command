# Specification: Extract /dev epic-map parse into bin/cortex-build-epic-map

## Problem Statement

`/dev`'s Step 3b currently performs deterministic parent-field normalization across `backlog/index.json` entries inline (`skills/dev/SKILL.md:151-167`). This is mechanical work — null/missing skip, quote strip, UUID skip, integer match — that an LLM can subtly miscode each invocation, and it consumes agent tokens/turns on every triage. Extracting it to a small `bin/cortex-build-epic-map` script gives reproducible correctness, ~1 turn of latency savings per `/dev` invocation, and a static-lintable wiring point for the SKILL.md-to-bin parity gate. The downstream Step 3c decision tree (status/spec/blocked → workflow recommendation) stays inline because that work *is* judgment, not parsing — moving it into a script would erode the agent-judgment surface that Step 3c needs.

## Requirements

1. **Wrapper script `bin/cortex-build-epic-map` follows the cortex-* convention.**
   Acceptance: `head -1 bin/cortex-build-epic-map` matches `#!/bin/bash`. The wrapper's first non-shebang line invokes `cortex-log-invocation` (fail-open). It contains the dual-branch dispatch (packaged form `cortex_command.backlog.build_epic_map`, then `CORTEX_COMMAND_ROOT` fallback), and an exit-2 not-found message. Verifiable: `grep -c 'cortex-log-invocation' bin/cortex-build-epic-map` ≥ 1; `grep -c 'cortex_command.backlog.build_epic_map' bin/cortex-build-epic-map` ≥ 1; `test -x bin/cortex-build-epic-map` (exit 0).

2. **Python implementation `backlog/build_epic_map.py` is importable and runnable.**
   Acceptance: importable as `cortex_command.backlog.build_epic_map`. Has a `main()` entry point invoked when run as `__main__`. Verifiable: `python3 -c 'from cortex_command.backlog.build_epic_map import main'` exit code = 0; `python3 backlog/build_epic_map.py --help` exit code = 0 and stdout contains the substring `index.json`.

3. **The script applies the four-step parent-field normalization from SKILL.md:159-167.**
   Acceptance: Given a fixture `index.json` whose active items contain combinations of `parent: null`, `parent: "103"`, `parent: 103`, `parent: "58f9eb72-1234-5678-90ab-cdef01234567"`, `parent: "abc-123"`, the script (a) excludes items with absent or null parent; (b) strips surrounding double or single quotes before matching; (c) excludes items whose stripped parent contains a `-` character (UUID heuristic); (d) parses the remaining value as an integer and matches against detected epic IDs. Verifiable: `pytest tests/test_build_epic_map.py::test_parent_normalization` exit code = 0.

4. **The script auto-detects epics by scanning `type: epic` across active entries in `index.json`.**
   Acceptance: Given a fixture with epics ID 100 and 101 (status varied: in-progress, blocked, refined) plus non-epic items, the script emits a map with keys `"100"` and `"101"` regardless of epic status. The "Ready" filter is applied downstream by Step 3b (Requirement 9), not by this script. Verifiable: `python3 backlog/build_epic_map.py tests/fixtures/build_epic_map/multi_epic.json | jq -r '.epics | keys | sort | join(",")'` returns the literal string `100,101`.

5. **Per-child output shape is the minimal four-field set.**
   Acceptance: Each child object in the emitted JSON has exactly these four fields: `id` (int — copied from `index.json`), `title` (str — copied from `index.json`), `status` (str — copied from `index.json`), `spec` (string-or-null — copied verbatim from `index.json`'s `spec` field; non-null non-empty string means refined per Step 3c's existing convention; null or missing in source becomes JSON `null` in output). No additional fields. The field name is `spec` (not `refined`) so that `skills/dev/SKILL.md` Step 3c (which keys its refinement indicator off "the child's `spec:` frontmatter field") can consume the script output without any text changes. Verifiable: `python3 backlog/build_epic_map.py tests/fixtures/build_epic_map/wide_shape.json | jq -r '.epics["100"].children[0] | keys | sort | join(",")'` returns the literal string `id,spec,status,title`.

6. **The script emits deterministic JSON to stdout.**
   Acceptance: Running the script twice on the same input produces byte-identical stdout. Output envelope: `{"schema_version": "1", "epics": {epic_id_string: {"children": [...]}, ...}}`. The envelope's `schema_version` is the JSON string `"1"` (matching the per-item `schema_version` convention used in `backlog/index.json` — round-trip symmetric). Epic-id keys are JSON strings (since JSON object keys must be strings). Children are sorted by `id` ascending; epics are sorted by integer-id ascending in the JSON object's serialization order. Verifiable: `python3 backlog/build_epic_map.py tests/fixtures/build_epic_map/multi_epic.json | sha256sum` produces the same digest on two consecutive runs; `python3 backlog/build_epic_map.py tests/fixtures/build_epic_map/multi_epic.json | jq -r '.schema_version'` returns the literal string `1`.

7. **The script hard-errors on `schema_version` mismatch.**
   Acceptance: If any active item in `index.json` has `schema_version` set to a value other than the JSON string `"1"` (null or missing is treated as `"1"` for legacy items), the script exits 2, writes to stderr a line matching the regex `cortex-build-epic-map: unsupported schema_version "[^"]*" — expected "1"`, and writes nothing to stdout. Verifiable: `python3 backlog/build_epic_map.py tests/fixtures/build_epic_map/v2_schema.json` exit code = 2; stderr matches the regex; stdout is empty.

8. **The script handles missing or malformed `index.json` with non-zero exit and a clear stderr message.**
   Acceptance: Running against a path that does not exist exits 1 with a stderr line containing the path. Running against a JSON-malformed file exits 1 with a stderr line naming a JSON parse error. Verifiable: `python3 backlog/build_epic_map.py /nonexistent/path/index.json` exit code = 1, stderr contains the substring `/nonexistent/path/index.json`; `printf 'not json' > "$TMPDIR/bad.json" && python3 backlog/build_epic_map.py "$TMPDIR/bad.json"` exit code = 1, stderr non-empty.

9. **`skills/dev/SKILL.md` Step 3b is updated with: script invocation, Ready intersection, fallback prose, and exit-code handling.**
   Acceptance: The rewritten Step 3b prose (replacing the four-step inline parent-field normalization narrative at `skills/dev/SKILL.md:151-167`) includes ALL of the following:
   - **(a) Script invocation reference** in inline-code form (`` `cortex-build-epic-map` ``) at least once. Verifiable: `grep -c '`cortex-build-epic-map`' skills/dev/SKILL.md` ≥ 1.
   - **(b) Output schema description** sufficient for the agent to consume the JSON without reading the script's source: name the four per-child fields (`id`, `title`, `status`, `spec`) and the envelope (`{"schema_version": "1", "epics": {...}}`).
   - **(c) Ready intersection step**: after running the script, Step 3b retains its existing "extract the Ready section" narrative (`SKILL.md:143-149`) and intersects the script's emitted epic map with the Ready set — i.e., only epics whose ID appears in the Ready section are passed to Step 3c for rendering. Verifiable: `grep -E 'Ready (set|section)' skills/dev/SKILL.md` returns ≥ 1 line in Step 3b's region.
   - **(d) Missing-index fallback preservation**: the existing prose at `SKILL.md:153` ("If missing after Step 3a ran, warn and fall back to reading `index.md`") is preserved or restated in the rewritten Step 3b. Verifiable: `grep -c 'fall back to .*index.md' skills/dev/SKILL.md` ≥ 1 in Step 3b's region.
   - **(e) Exit-code handling**: explicit prose covering both non-zero exit codes the script can produce — on exit 1 (missing or malformed `index.json`), the agent warns and falls back to reading `index.md` table columns (same target as the existing 3a fallback); on exit 2 (`schema_version` mismatch), the agent reports the mismatch to the user and halts triage rather than silently degrading. Verifiable: `grep -E 'exit (code )?(1|2)' skills/dev/SKILL.md` ≥ 1 line in Step 3b's region; `grep -c 'schema_version' skills/dev/SKILL.md` ≥ 1.
   - **(f) Step 3a is unchanged.** The `cortex-generate-backlog-index` invocation in Step 3a remains exactly as it is today. Verifiable: `git diff -U0 skills/dev/SKILL.md` shows no edits to lines 135–141 (Step 3a region).
   - **(g) Step 3c is unchanged.** The decision-tree narrative for workflow recommendations remains exactly as it is today (the `spec` field name in 3c is preserved by Requirement 5's choice of field name). Verifiable: `git diff -U0 skills/dev/SKILL.md` shows no edits to lines 168 onward.
   - **(h) Parity gate passes.** Verifiable: `bin/cortex-check-parity` exit code = 0.

10. **Plugin mirror is committed via `just build-plugin`.**
    Acceptance: After `just build-plugin`, `plugins/cortex-interactive/bin/cortex-build-epic-map` exists and is byte-identical to `bin/cortex-build-epic-map`. The pre-commit drift hook passes (`git diff --exit-code plugins/cortex-interactive/bin/` returns 0 after a fresh build). Verifiable: `cmp bin/cortex-build-epic-map plugins/cortex-interactive/bin/cortex-build-epic-map` exit code = 0; `git diff --exit-code -- plugins/cortex-interactive/bin/cortex-build-epic-map` exit code = 0 after `just build-plugin`.

11. **Tests cover normalization rules, schema validation, edge cases, and CLI invocation.**
    Acceptance: `tests/test_build_epic_map.py` exists and includes (a) unit tests covering each of the four normalization rules — null/missing parent, quote-strip, UUID-skip, integer-match; (b) end-to-end subprocess tests invoking `bin/cortex-build-epic-map` against fixtures `multi_epic.json`, `wide_shape.json` (renamed semantically — fixture exercises the four-field shape), `no_epics.json`, `malformed_json.json`, `v2_schema.json`; (c) `spec`-field passthrough tests for `spec: null`, `spec` missing, `spec: ""`, `spec: "lifecycle/x/spec.md"` — all four values copied verbatim into the emitted child object's `spec` field. Verifiable: `pytest tests/test_build_epic_map.py` exit code = 0; `pytest tests/test_build_epic_map.py --collect-only -q | grep -c '::test_'` ≥ 8.

12. **`backlog/build_epic_map.py` is reachable through the wrapper in both packaged and `CORTEX_COMMAND_ROOT` modes.**
    Acceptance: With `cortex_command` package available on `PYTHONPATH`, `bin/cortex-build-epic-map tests/fixtures/build_epic_map/multi_epic.json` exits 0 and emits a non-empty JSON map (pass = via packaged branch). The wrapper's branch (b) `CORTEX_COMMAND_ROOT` fallback follows the same pattern as `bin/cortex-update-item` and `bin/cortex-generate-backlog-index` — interactive validation only, no separate test required (the wrapper is mechanical). Verifiable: `bin/cortex-build-epic-map tests/fixtures/build_epic_map/multi_epic.json` exit code = 0; `diff <(grep -A 3 'CORTEX_COMMAND_ROOT' bin/cortex-build-epic-map) <(grep -A 3 'CORTEX_COMMAND_ROOT' bin/cortex-generate-backlog-index)` shows the same dispatch pattern (interactive: visual review).

## Non-Requirements

- The script does NOT implement Step 3c's decision tree (workflow recommendations from children's `status`/`spec` flags). That logic stays inline in `skills/dev/SKILL.md`.
- The script does NOT compute "Ready" itself. The script auto-detects all `type:epic` items in `index.json` regardless of status; Step 3b is responsible for intersecting the script's emitted epic map with the Ready set extracted from `backlog/index.md` (Requirement 9c). The Ready filter lives in Step 3b's prose, not in the script and not in Step 3c.
- The script does NOT modify or write to `backlog/index.json`. It is read-only.
- The script does NOT generate `backlog/index.json` itself — that responsibility stays with `cortex-generate-backlog-index`.
- The script does NOT support migration from `schema_version: "1"` to a future version. A schema bump requires coordinated updates to both `generate_index.py` and `build_epic_map.py`; this script hard-errors on mismatch (Requirement 7) rather than attempting forward compatibility.
- The script is NOT added to `bin/.parity-exceptions.md`. It is wired via `skills/dev/SKILL.md` and must remain so; an allowlist entry would mask future refactor regressions.
- The script does NOT support an `--out FILE` flag. Stdout-only output (Requirement 6).
- The script does NOT support an `--epic-ids ID,ID,...` filter flag. Auto-detection only (Requirement 4); the flag is reserved as a future extension if needed.
- The Python implementation is NOT centralized into `cortex_command/common.py`. It lives in `backlog/build_epic_map.py` per the existing `bin/cortex-* → backlog/*.py` pattern; centralization is rejected per the research §Tradeoffs Alt B analysis.
- The per-child output does NOT include `priority`, `blocked_by`, or `type`. Step 3c does not consume these fields (its blocked-children count derives from `status: blocked`, not `blocked_by`); shipping unread fields would lock CI to a contract no behavior depends on. If a future caller needs them, they can be added behind a flag (e.g., `--include=blocked_by,priority`) without a breaking change.
- The script does NOT preserve a copy of the four-step normalization narrative in agent-readable form. Diagnostic vocabulary for "why was this child silently dropped" (UUID-era parent, integer mismatch, null parent) lives in the script's source code only — not in `skills/dev/SKILL.md`. This is an intentional trade-off: the agent gains determinism at the cost of in-context diagnostic phrasing. If a user asks "why didn't ticket X show up under epic Y," the agent must read `backlog/build_epic_map.py` to answer in detail.

## Edge Cases

- **Empty `index.json` (no active items)**: exit 0, emit `{"schema_version": "1", "epics": {}}` to stdout.
- **No `type: epic` items detected**: exit 0, emit `{"schema_version": "1", "epics": {}}` to stdout.
- **Epic with no children**: emit `{"epics": {"NNN": {"children": []}}, ...}`. Empty array, key still present.
- **Child whose parent is the integer/string of a non-epic active item**: silently dropped — only items whose normalized parent matches a detected epic ID are appended.
- **Child whose parent is an integer that matches no detected epic**: silently dropped (no epic to attach to).
- **Multiple children with the same `id`**: the script does not dedup; trusts upstream `generate_index.py` invariants. If duplication occurs, both entries appear in the children array.
- **`spec` field present but empty string `""`**: copied verbatim as `""` into the child output. Step 3c's existing convention treats only non-null non-empty strings as refined.
- **`spec` field is `null`**: copied verbatim as JSON `null` into the child output.
- **`spec` field is missing entirely**: emitted as JSON `null` in the child output (normalize "missing" and "explicitly null" to the same external representation so Step 3c's `is null` check handles both uniformly).
- **`schema_version` is `null` or missing on an item**: treat as `"1"` (legacy items predating explicit versioning).
- **`schema_version` is the JSON string `"1"`**: passes validation.
- **`schema_version` is anything else (e.g., the string `"2"`, integer `1`, array, object)**: hard error, exit 2 (Requirement 7). Note: integer `1` is treated as a mismatch — the script compares against the JSON string `"1"` exactly. This is a forward-compat guard; current `backlog/generate_index.py` always emits string values via `_opt()` so integer `1` is not reachable through the canonical producer today, but the validator defends against future changes or hand-edits.
- **`CORTEX_COMMAND_ROOT` pointing at a non-cortex-command checkout**: wrapper branch (b) checks `pyproject.toml` `name = "cortex-command"`; if not present, falls through to branch (c) and exits 2 with the standard "cortex-command CLI not found" message.
- **Concurrent `/dev` invocations call the script in parallel**: safe — read-only stdout, no shared mutable state, no file writes.
- **`bin/cortex-build-epic-map` invoked from outside the repo (e.g., from a plugin install)**: the wrapper resolves the implementation via packaged module first, then falls back to `CORTEX_COMMAND_ROOT`. The positional `index_path` argument can be an absolute path; if relative, it is resolved against the current working directory. Step 3b passes an absolute or repo-relative path.
- **Script exits 1 (missing/malformed `index.json`)**: Step 3b warns the user and falls back to reading `index.md` table columns (same fallback as Step 3a's existing `cortex-generate-backlog-index` failure path). Per Requirement 9d/9e.
- **Script exits 2 (`schema_version` mismatch)**: Step 3b reports the mismatch to the user and halts triage. A schema bump is a coordinated-change signal, not a degraded-path signal — silently falling back to `index.md` would mask the upgrade requirement. Per Requirement 9e.

## Changes to Existing Behavior

- **MODIFIED: `skills/dev/SKILL.md` Step 3b** — the inline four-step parent-field normalization narrative (currently lines 151–167, ~17 lines) is replaced by: a one-paragraph script invocation, a four-line schema description, two lines of Ready intersection prose, two lines of fallback prose, and three lines of exit-code handling. Net SKILL.md line delta is approximately neutral (≈10–15 lines removed, ≈10–15 lines added). The size win was never the point — the value is in correctness, lintability, and removing token-cost-per-invocation parsing work from the agent's hot path. Functionally equivalent: same epic→children map shape (with the field set narrowed to the four Step 3c actually reads), produced by the script rather than by agent reasoning over `index.json`.
- **ADDED: `bin/cortex-build-epic-map`, `backlog/build_epic_map.py`, `tests/test_build_epic_map.py`, `tests/fixtures/build_epic_map/*.json`** — new artifacts.
- **ADDED: `plugins/cortex-interactive/bin/cortex-build-epic-map`** — auto-generated mirror of `bin/cortex-build-epic-map` via `just build-plugin`. Not a hand-edited file; it is regenerated on every plugin build and verified by the pre-commit drift hook.

## Technical Constraints

- Wrapper convention is locked: shebang `#!/bin/bash`; `cortex-log-invocation` shim line; `set -euo pipefail`; dual-branch dispatch (packaged form via `python3 -c 'import cortex_command.backlog.build_epic_map'` probe, then `CORTEX_COMMAND_ROOT` env-var path); exit-2 fallback with the standard "cortex-command CLI not found" message. Mirror the existing `bin/cortex-generate-backlog-index` and `bin/cortex-update-item` wrappers; do not invent a new convention.
- Python implementation must be importable as `cortex_command.backlog.build_epic_map` — file location is `backlog/build_epic_map.py` (the existing package layout maps `backlog/*.py` to `cortex_command.backlog.*`).
- argparse only (no click). Positional `index_path` argument with default of `backlog/index.json` resolved relative to the current working directory.
- JSON output uses `json.dumps(..., sort_keys=True, indent=2)` for deterministic key ordering and pretty-printing. Children sorted by `id` ascending; epics sorted by integer-id ascending within the JSON object's serialization order.
- "Ready" is informal narrative in `skills/dev/SKILL.md`, not a code-level concept. `backlog/index.md` has sections `## Refined`, `## Backlog`, `## In-Progress`, and (optional) `## Warnings` — emitted by `backlog/generate_index.py`. The agent's "Ready" reading is "items in Refined or Backlog with no unresolved blockers." Step 3b's Ready intersection (Requirement 9c) operates on this narrative reading; if `generate_index.py` later emits an explicit `## Ready` section or an in-JSON `ready: bool` flag, Step 3b's intersection logic can be simplified, but doing so is out of scope for this ticket.
- The script must work when invoked from outside the repo (e.g., from a `cortex-interactive` plugin install). The `index_path` argument can be absolute or relative-to-CWD.
- `skills/dev/SKILL.md` Step 3b must reference `cortex-build-epic-map` in inline-code form (`` ` `` ... `` ` ``) to satisfy `bin/cortex-check-parity` detection. A bare-token mention without backticks would also satisfy the linter's bare-invocation pattern, but inline-code is the convention in this repo.
- The plugin mirror is byte-identical to the source via `rsync -a --delete --include='cortex-*' --exclude='*'`. The `.githooks/pre-commit` drift loop enforces sync.
- The wrapper file's executable bit must be set in git (`git update-index --chmod=+x bin/cortex-build-epic-map` if filemode tracking is not auto-set on the developer's filesystem).
- The script does not import from `claude/common.py` or other claude-side modules; it depends only on stdlib (json, argparse, sys, pathlib) and optionally `cortex_command.common` if a shared helper is needed.
- Output is fully self-contained per invocation; no caching, no state files. Re-running on the same input produces identical output (Requirement 6).
- Round-trip type symmetry: the envelope's `schema_version` is the JSON string `"1"`, matching the per-item `schema_version` convention in `backlog/index.json` (which `backlog/generate_index.py` emits as a string via `_opt()`). Using the same type at both the envelope and per-item level prevents a latent contract bug where a downstream consumer applying the same validator to the script's output would self-reject.

## Open Decisions

(None — all five Open Questions from research were resolved during the spec interview, and the critical-review pass narrowed the schema choice to the minimal four-field set: `id`, `title`, `status`, `spec`. Ready intersection lives in Step 3b's prose. Step 3c is truly unchanged because the field name `spec` is preserved.)
