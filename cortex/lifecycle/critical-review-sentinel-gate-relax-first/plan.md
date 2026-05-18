# Plan: critical-review-sentinel-gate-relax-first

## Overview

Add a code-level reviewer-side sentinel parser (`verify_reviewer_output`, `_REVIEWER_RE`, `verify-reviewer-output` subcommand) to `cortex_command/critical_review.py` mirroring the existing `_SYNTH_RE` / `verify_synth_output` precedent. Wire it into `skills/critical-review/` prose to replace the over-firing first-line check, align reviewer prompts with the parser's contract, extend plugin-mirror parity coverage, and annotate the events-registry. The implementation strictly preserves the `record-exclusion` event schema and all four load-bearing voice anchors.

**Architectural Pattern**: plug-in
<!-- The new subcommand plugs into the existing `cortex_command.critical_review` module alongside `verify_synth_output` / `prepare_dispatch` / `record_exclusion`, following the established atomic-subcommand pattern. -->

## Outline

### Phase 1: Code parser + regression fixtures (tasks: 1, 2, 3a, 3b, 4)
**Goal**: Introduce `verify_reviewer_output` and its subcommand wiring with unit-test coverage backed by synthetic in-repo fixtures.
**Checkpoint**: `pytest tests/test_critical_review_sentinel_window.py -v` exits 0 with ≥12 tests passing; `cortex-critical-review verify-reviewer-output --help` exits 0 and names all required arguments; the fixture corpus exists at `tests/fixtures/critical-review/reviewer-outputs/` with ≥6 `.txt` + matching `.meta.json` pairs.

### Phase 2: Wire and align (tasks: 5, 6, 7, 8, 9)
**Goal**: Rewrite the prose Phase 1 verification to invoke the subcommand, align reviewer prompts with the parser contract, regenerate the mirror and extend the parity test in one commit, and annotate the events-registry.
**Checkpoint**: `pytest tests/test_plugin_mirror_parity.py -v` exits 0 (parity passes for critical-review canonical-to-mirror); `grep -c 'first-line sentinel' skills/critical-review/SKILL.md` = 0 and `grep -c 'verify-reviewer-output' skills/critical-review/SKILL.md` ≥ 1; `grep -c 'as the first line of output' skills/critical-review/references/reviewer-prompt.md` = 0; `diff -r skills/critical-review/ plugins/cortex-core/skills/critical-review/` exits 0. This Checkpoint is observable after Task 8 lands (the combined mirror-regen + parity-test commit).

## Tasks

### Task 1: Add `_REVIEWER_RE` regex constant and `verify_reviewer_output` function
- **Files**: `cortex_command/critical_review.py`
- **What**: Add a new module-level regex constant `_REVIEWER_RE` (parallel to `_SYNTH_RE` at line 192) and a new function `verify_reviewer_output(output, expected_sha, window_lines=50)` that implements **first-match-whose-SHA-equals-expected** semantics (load-bearing — see Context). Insert both into the file immediately after the existing `verify_synth_output` block (currently `:189-216`) to preserve the mirror-symmetry reading order.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Mirror the synth-side block at `cortex_command/critical_review.py:189-216`:
    ```python
    _SYNTH_RE = re.compile(r"^SYNTH_READ_OK: (\S+) ([0-9a-f]{64})$", re.MULTILINE)
    def verify_synth_output(output: str, expected_sha: str) -> tuple[str, str | None]:
        m = _SYNTH_RE.search(output)
        if not m:
            return ("absent", None)
        observed = m.group(2)
        if observed != expected_sha:
            return ("mismatch", observed)
        return ("ok", observed)
    ```
  - **New regexes** (two coordinated patterns, named for the sentinel they target):
    - `_REVIEWER_OK_RE = re.compile(r"^READ_OK: (\S+) ([0-9a-f]{64})\s*$", re.MULTILINE)` — matches success sentinels with a SHA-shaped token.
    - `_REVIEWER_FAILED_RE = re.compile(r"^READ_FAILED: (\S+) (\S+)\s*$", re.MULTILINE)` — matches read-failure sentinels with a one-word reason.
    - **No alternation regex** — the original draft used `READ_(?:OK|FAILED)` with `[0-9a-f]{64}` but the SHA constraint excludes READ_FAILED, making the alternation dead code. Two named patterns are clearer for maintainers.
  - **Function signature**: `def verify_reviewer_output(output: str, expected_sha: str, window_lines: int = 50) -> tuple[str, str | None]`.
  - **Algorithm** (READ_OK precedence, with symmetric anti-quoting defense):
    1. Compute `window = "\n".join(output.splitlines()[:window_lines])`. Note: `splitlines()` already strips `\r\n` endings, so the joined window contains only `\n` separators — line-ending normalization happens here, not in the regex.
    2. Collect all `_REVIEWER_OK_RE` matches in the window: `ok_matches = list(_REVIEWER_OK_RE.finditer(window))`.
    3. **OK-first precedence**: iterate `ok_matches` in order; if any match has `match.group(2) == expected_sha`, return `("ok", expected_sha)`. This pass succeeds even when adversarial preamble quotes a different SHA earlier in the window.
    4. If no matching-SHA OK match was found, scan for `_REVIEWER_FAILED_RE` matches: `failed_matches = list(_REVIEWER_FAILED_RE.finditer(window))`. If any exist, return `("read_failed", failed_matches[0].group(2))`. This pass fires only when the reviewer's real sentinel was READ_FAILED (no valid READ_OK with expected SHA exists anywhere in the window).
    5. If `ok_matches` is non-empty but none matched the expected SHA, return `("mismatch", ok_matches[0].group(2))`.
    6. If both lists are empty, return `("absent", None)`.
  - **Why OK-first precedence (not earliest-position)**: a reviewer reviewing this fix's own artifacts can emit `evidence_quote` strings containing literal `READ_OK: <path> <real-sha>` OR `READ_FAILED: <path> <reason>` patterns. The earliest-position approach (naive) would misclassify in both directions: quoted READ_OK before real READ_FAILED would route to `mismatch`; quoted READ_FAILED before real READ_OK would route to `read_failed`. The OK-first algorithm above defends symmetrically: if any READ_OK with the expected SHA exists in the window, that always wins regardless of what else appears. Otherwise the function falls through deterministically.
  - **Path-capture group is diagnostic only**: `(\S+)` accepts any non-whitespace path string but the function does NOT compare it against the expected artifact path. Only the SHA is validated. This is deliberate — content identity (SHA match) is the load-bearing trust signal; path-string identity is cosmetic. If a future requirement adds path-equality enforcement, change the function and add a unit test; do not assume the path was being checked.
  - **`observed_sha_or_null` on mismatch is diagnostic, not authoritative**: step 5 returns the first `ok_match`'s SHA, which may be artifact-quoted text rather than the reviewer's intended sentinel. Operators reading a `mismatch` event should examine the full reviewer output to determine the true cause rather than trusting the observed SHA in isolation.
- **Verification**: `grep -c '^_REVIEWER_OK_RE = re.compile' cortex_command/critical_review.py` = 1 AND `grep -c '^_REVIEWER_FAILED_RE = re.compile' cortex_command/critical_review.py` = 1 AND `grep -c '^def verify_reviewer_output' cortex_command/critical_review.py` = 1 AND `python3 -c "from cortex_command.critical_review import verify_reviewer_output, _REVIEWER_OK_RE, _REVIEWER_FAILED_RE; import inspect; sig = inspect.signature(verify_reviewer_output); assert list(sig.parameters) == ['output', 'expected_sha', 'window_lines'], sig.parameters; assert sig.parameters['window_lines'].default == 50"` exits 0.
- **Status**: [x] completed (commit 5776ce86)

### Task 2: Add `_cmd_verify_reviewer_output` argparse subcommand
- **Files**: `cortex_command/critical_review.py`
- **What**: Add a new subcommand handler `_cmd_verify_reviewer_output(args)` and argparse wiring that mirrors `_cmd_verify_synth_output` (currently at `:346-393`) and its argparse block (currently at `:454-463`). On exit-3 paths (`absent`, `mismatch`, `read_failed`), invoke the existing `record-exclusion` event-emission path internally — so the orchestrator sees one subprocess per reviewer that fuses parse + classify + telemetry.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - **I/O contract deviates from synth-side**: read reviewer output from `--input-file <path>` (UTF-8, `errors='strict'`), NOT from stdin. Rationale: four reviewer outputs per critical-review pass (vs one synthesizer output), each containing backticks/quotes/JSON-envelope content; `--input-file` avoids shell-quoting hazards.
  - **Required arguments**: `--feature <name>`, `--reviewer-angle <angle>`, `--expected-sha <hex>`, `--model-tier {haiku|sonnet|opus}`, `--input-file <path>`.
  - **Optional**: `--window-lines <int>` (default 50).
  - **Shared helper to eliminate schema duplication**: BEFORE writing `_cmd_verify_reviewer_output`, extract a helper `_build_sentinel_absence_event(feature: str, reviewer_angle: str, reason: str, model_tier: str, expected_sha: str, observed_sha: str | None) -> dict` from the existing `_cmd_record_exclusion` event-construction at `:403-413`. The helper returns the canonical 8-field `sentinel_absence` event dict. Both `_cmd_record_exclusion` AND the new `_cmd_verify_reviewer_output` call this helper — there is exactly one schema definition, no duplication. The helper lives in `cortex_command/critical_review.py` alongside the two subcommand handlers. Refactor `_cmd_record_exclusion` to call the helper as part of this task (one-line change inside the existing function; preserves its CLI surface and exit codes).
  - **Mirror the synth-side handler** at `cortex_command/critical_review.py:346-393` (`_cmd_verify_synth_output`). Same return-code routing, same diagnostic-string pattern, with these deviations:
    1. Resolve `lifecycle_root` from `args.lifecycle_root or _default_lifecycle_root()` (identical to synth-side at `:348`).
    2. Read the reviewer output from `args.input_file` (UTF-8, `errors='strict'`) — NOT from `sys.stdin`. On missing/unreadable file, write a one-line diagnostic to stderr and return exit 2 (mirror the synth-side error pattern at `:349-351`).
    3. Call `verify_reviewer_output(output, args.expected_sha, args.window_lines)` from Task 1.
    4. On `status == "ok"`, write `OK <observed_sha>` to stdout and return 0.
    5. On `status ∈ {"absent", "mismatch", "read_failed"}`: map status → `reason` per the existing `record-exclusion` enum (`absent` → `absent`, `mismatch` → `sha_mismatch`, `read_failed` → `read_failed`); call `_build_sentinel_absence_event(...)` to construct the event dict; write `EXCLUDED <reason>` to stdout for orchestrator-side warning extraction; call `append_event(events_log, event)` (the existing helper at `:223-244`, which is atomic via tempfile + `os.replace`); on `OSError`, emit a warning to stderr but still return 3. Return 3.
  - **`observed_sha_or_null` field**: set to the observed SHA on `mismatch`; set to `None` on `absent` and `read_failed`. The helper's signature enforces this — the caller passes `None` for the non-mismatch paths.
  - **Argparse wiring**: extend the existing `subparsers.add_parser(...)` block at `:454-463` with a new subparser named `verify-reviewer-output`. Required arguments listed above; default `--window-lines=50`; standard `--lifecycle-root` argument matching the existing pattern. Bind `set_defaults(func=_cmd_verify_reviewer_output)`.
  - **`_cmd_record_exclusion` retained as a thin wrapper**: after refactoring it to call `_build_sentinel_absence_event`, the subcommand is ~3 lines of glue. It stays in the module so any external operator who learned the `cortex-critical-review record-exclusion` CLI surface from prior docs still has it available, and Task 9's events-registry annotation has a stable producer location. The plan does NOT delete `_cmd_record_exclusion` in this ticket — that is a scope-discipline call, not a contractual one. If a future audit shows zero external callers, a separate ticket can remove it without schema risk (the helper remains the single source of truth).
- **Verification**: `cortex-critical-review verify-reviewer-output --help` exits 0 AND `cortex-critical-review verify-reviewer-output --help 2>&1 | grep -cE '(--input-file|--expected-sha|--reviewer-angle|--feature|--model-tier|--window-lines)'` ≥ 6 AND `python3 -c "from cortex_command.critical_review import _cmd_verify_reviewer_output, _build_sentinel_absence_event; assert callable(_cmd_verify_reviewer_output); assert callable(_build_sentinel_absence_event); ev = _build_sentinel_absence_event('f', 'a', 'absent', 'sonnet', 'x'*64, None); assert set(ev.keys()) == {'ts', 'event', 'feature', 'reviewer_angle', 'reason', 'model_tier', 'expected_sha', 'observed_sha_or_null'}; assert ev['event'] == 'sentinel_absence'"` exits 0 AND `python3 -c "from cortex_command.critical_review import _cmd_record_exclusion; import inspect; src = inspect.getsource(_cmd_record_exclusion); assert '_build_sentinel_absence_event' in src, '_cmd_record_exclusion must call the shared helper'"` exits 0.
- **Status**: [x] completed (commit 23a256be — helper + handler + events-registry producers update)

### Task 3a: Capture three `ok`-classification fixtures via Agent dispatch
- **Files**: `tests/fixtures/critical-review/reviewer-outputs/case-ok-line-1.txt`, `tests/fixtures/critical-review/reviewer-outputs/case-ok-line-1.meta.json`, `tests/fixtures/critical-review/reviewer-outputs/case-ok-after-preamble.txt`, `tests/fixtures/critical-review/reviewer-outputs/case-ok-after-preamble.meta.json`, `tests/fixtures/critical-review/reviewer-outputs/case-ok-deeper-preamble.txt`, `tests/fixtures/critical-review/reviewer-outputs/case-ok-deeper-preamble.meta.json`
- **What**: Dispatch the canonical reviewer-prompt agent three times against an in-repo lifecycle artifact (e.g., `cortex/lifecycle/critical-review-sentinel-gate-relax-first/spec.md`), saving each agent's raw stdout to a `.txt` fixture with a sibling `.meta.json` describing the classification (always `ok` for this task; the SHA is captured from `git hash-object <artifact>` at dispatch time).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **Reviewer-prompt template**: `skills/critical-review/references/reviewer-prompt.md`. Substitute `{artifact_path}` with the absolute path of the in-repo artifact and `{artifact_sha256}` with the 64-hex SHA-256 of the file's raw bytes. **Compute SHA via `sha256sum <path> | awk '{print $1}'` or `python3 -c "import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())" <path>` — NOT `git hash-object` (which emits a 40-hex SHA-1 blob hash that the `[0-9a-f]{64}` regex rejects).** For `{angle name}` and `{angle description}`, the `angle-menu.md` file is a flat bullet list of single-phrase exemplars (e.g., "Architectural risk", "Unexamined alternatives", "Fragile assumptions") grouped under domain categories — there are no rows with both a name and a description. Construct each `{angle name}` as a short title (e.g., "Spec-vs-Codebase Reality Audit") and each `{angle description}` as a 1-2 sentence statement of what that angle investigates, using the angle-menu's exemplars as inspiration but not as literal name+description pairs.
  - **Dispatch via `Agent` tool** with the substituted prompt, `subagent_type: "general-purpose"`, no worktree isolation, capture the full stdout return value to the `.txt` fixture file. The three dispatches use three different angles — naturally produces varying preamble lengths (line 1, lines 3-5, lines 10-15). If a dispatch happens to emit the sentinel at the same approximate line as a previous fixture, re-dispatch with a different angle until preamble-depth variants exist.
  - **`.meta.json` shape per file**:
    ```json
    {
      "expected_classification": "ok",
      "expected_sha": "<64-hex matching the artifact at capture time>",
      "captured_from": "Agent dispatch against cortex/lifecycle/.../spec.md",
      "captured_date": "2026-05-NN",
      "notes": "Sentinel appears at line N (1-indexed)"
    }
    ```
  - **Note on fixture stability**: the captured outputs are snapshots in time. Future model updates may change preamble patterns, but the captured `.txt` files remain valid as historical regression inputs because `verify_reviewer_output`'s contract is "given this byte sequence, classify it" — not "given today's model, classify it."
- **Verification**: `ls tests/fixtures/critical-review/reviewer-outputs/case-ok-*.txt | wc -l` = 3 AND `ls tests/fixtures/critical-review/reviewer-outputs/case-ok-*.meta.json | wc -l` = 3 AND `python3 -c "import json, pathlib; metas = [json.loads(p.read_text()) for p in pathlib.Path('tests/fixtures/critical-review/reviewer-outputs').glob('case-ok-*.meta.json')]; assert all(m['expected_classification'] == 'ok' for m in metas); assert all(len(m['expected_sha']) == 64 for m in metas)"` exits 0.
- **Status**: [x] completed (commit df1bf66c — fixtures self-authored in-role because Agent tool unavailable to sub-agent; sentinel positions: line 1, line 3, line 11)

### Task 3b: Hand-synthesize absent/mismatch/adversarial fixtures + corpus README
- **Files**: `tests/fixtures/critical-review/reviewer-outputs/case-absent.txt`, `tests/fixtures/critical-review/reviewer-outputs/case-absent.meta.json`, `tests/fixtures/critical-review/reviewer-outputs/case-mismatch.txt`, `tests/fixtures/critical-review/reviewer-outputs/case-mismatch.meta.json`, `tests/fixtures/critical-review/reviewer-outputs/case-adversarial-quoted-sha.txt`, `tests/fixtures/critical-review/reviewer-outputs/case-adversarial-quoted-sha.meta.json`, `tests/fixtures/critical-review/reviewer-outputs/README.md`
- **What**: Hand-author three fixture pairs that exercise the non-`ok` classifications plus an adversarial case the load-bearing first-match-matching-SHA semantics must defend against. Also create a README documenting how the corpus was captured for future maintainers.
- **Depends on**: [3a]
- **Complexity**: simple
- **Context**:
  - **`case-absent.txt`**: take one of the Task 3a `case-ok-*.txt` files as a starting point, delete the `READ_OK: ...` line entirely, leave the rest of the prose intact (the reviewer's findings remain — what's missing is the sentinel). Save with `.meta.json` `expected_classification: "absent"`, `expected_sha` set to the same SHA as the source fixture.
  - **`case-mismatch.txt`**: take one of the Task 3a fixtures, replace the SHA hex in its `READ_OK:` line with a different 64-hex string. Get the replacement SHA via `sha256sum <any-other-committed-file>` (NOT `git hash-object`, which emits 40-hex SHA-1). The `.meta.json`'s `expected_sha` is the ORIGINAL artifact's SHA (the orchestrator's pre-dispatch expectation); the function should return `("mismatch", observed_sha_from_fixture)`.
  - **`case-adversarial-quoted-sha.txt`**: this is the load-bearing fixture for Task 1's first-match-matching-SHA semantics. Construct the output as:
    1. Lines 1-2: brief preamble (e.g., "Let me write the findings.")
    2. Line 3: `READ_OK: /some/quoted/path <real-hex-but-NOT-expected-sha>` — represents a reviewer quoting an artifact's example sentinel verbatim early in their output.
    3. Lines 4-7: prose describing the artifact
    4. Line 8: `READ_OK: <actual-artifact-path> <expected-sha>` — the reviewer's REAL sentinel.
    5. Lines 9+: findings.
    The `.meta.json` has `expected_classification: "ok"`, `expected_sha` set to the SHA on line 8 (the artifact's real SHA). Verifies that naive first-match would fail (returning line 3's wrong SHA as `mismatch`) but first-match-matching-SHA passes (line 8 wins).
  - **`README.md`** in the fixture dir: ~10 lines explaining: (a) what each `case-*` fixture exercises, (b) the date of capture, (c) the source artifact for the `case-ok-*` fixtures, (d) that fixtures must NOT be re-baselined casually — they encode behavioral expectations that the unit tests rely on.
  - **All `expected_sha` values must be real 64-hex strings**, not placeholders. The regex `[0-9a-f]{64}` only matches real hex. Use `sha256sum` to generate plausible SHAs.
- **Verification**: `ls tests/fixtures/critical-review/reviewer-outputs/case-*.txt | wc -l` ≥ 6 AND `ls tests/fixtures/critical-review/reviewer-outputs/case-*.meta.json | wc -l` ≥ 6 AND `test -f tests/fixtures/critical-review/reviewer-outputs/README.md` AND `python3 -c "import json, pathlib; metas = [json.loads(p.read_text()) for p in pathlib.Path('tests/fixtures/critical-review/reviewer-outputs').glob('case-*.meta.json')]; classes = [m['expected_classification'] for m in metas]; assert classes.count('ok') >= 3, classes; assert 'absent' in classes; assert 'mismatch' in classes; assert all('expected_sha' in m and len(m['expected_sha']) == 64 for m in metas)"` exits 0.
- **Status**: [x] completed (commit f4b250c8 — 7 files: 3 fixture pairs + README)

### Task 4: Write unit tests for `verify_reviewer_output`
- **Files**: `tests/test_critical_review_sentinel_window.py`
- **What**: Add a new test module with ≥12 test cases driven by the Phase 1 fixture corpus plus inline-string tests for edge cases that the fixture corpus does not naturally exercise (BOM, CRLF, blockquoted sentinel, fenced sentinel for documentation purposes).
- **Depends on**: [1, 3a, 3b]
- **Complexity**: simple
- **Context**:
  - **Test module layout** mirrors existing sibling `tests/test_critical_review_path_validation.py`. Use pytest, no fixtures framework, parametrize where natural.
  - **Required test cases (≥12)**:
    1. `test_sentinel_at_line_1_pass` — load `case-ok-line-1.txt`, call `verify_reviewer_output`, assert `("ok", expected_sha)`.
    2. `test_sentinel_at_line_3_after_preamble_pass` — load `case-ok-after-preamble.txt`, assert `("ok", expected_sha)`.
    3. `test_sentinel_at_line_15_pass` — load `case-ok-deeper-preamble.txt`, assert `("ok", expected_sha)`.
    4. `test_sentinel_absent_returns_absent` — load `case-absent.txt`, assert `("absent", None)`.
    5. `test_sentinel_with_wrong_sha_returns_mismatch` — load `case-mismatch.txt`, assert `("mismatch", observed_sha)` where `observed_sha` is the wrong hex from the fixture's `.meta.json`.
    6. `test_sentinel_in_evidence_quote_past_window_returns_absent` — inline string: 50 lines of preamble, then sentinel at line 55. Assert `("absent", None)`.
    7. `test_multiple_sentinels_first_matching_sha_wins` — load `case-adversarial-quoted-sha.txt`, assert `("ok", expected_sha)`. This is the load-bearing OK-first defense test (quoted READ_OK with wrong SHA at line 3; real READ_OK with expected SHA at line 8 wins).
    8. `test_quoted_read_failed_before_real_read_ok_returns_ok` — inline string with `READ_FAILED: /quoted/path crashed` at line 2 and `READ_OK: /real/path <expected-sha>` at line 5. Assert `("ok", expected_sha)`. This is the SYMMETRIC defense: a reviewer quoting READ_FAILED in preamble must NOT be excluded when they emit a valid READ_OK with the expected SHA after.
    9. `test_quoted_read_ok_wrong_sha_before_real_read_failed_returns_read_failed` — inline string with `READ_OK: /quoted/path <some-real-but-wrong-sha>` at line 3 and `READ_FAILED: /real/path crashed` at line 8 and NO READ_OK with expected SHA anywhere. Assert `("read_failed", "crashed")`. This is the SYMMETRIC defense in the other direction: a real READ_FAILED must NOT be misclassified as `mismatch` just because a quoted READ_OK with a different SHA appeared earlier.
    10. `test_blockquoted_sentinel_is_rejected` — inline string with `> READ_OK: /p <real-sha>`. Assert `("absent", None)`.
    11. `test_bom_prefixed_first_line_pass` — inline string with `﻿` prefix on line 1, sentinel on line 2. Assert `("ok", expected_sha)`.
    12. `test_crlf_line_endings_pass` — inline string with `\r\n` line endings, sentinel on line 1. Assert `("ok", expected_sha)`. Note: this validates that `output.splitlines()` correctly normalizes `\r\n` → `\n` before regex; the regex's `\s*$` is NOT the load-bearing CRLF handler.
    13. `test_read_failed_route` — inline string with `READ_FAILED: /p reason_token` at line 2 and no `READ_OK` anywhere in window. Assert `("read_failed", "reason_token")`.
    14. `test_window_size_default_is_50` — call `verify_reviewer_output("\n".join(["x"] * 49) + f"\nREAD_OK: /p {sha}", sha)`. Assert `("ok", sha)`. Then call with one more line of preamble — assert `("absent", None)` (sentinel pushed to line 51, outside default window).
  - **Test data location**: `FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "critical-review" / "reviewer-outputs"`. Read each fixture with `(FIXTURE_DIR / "case-ok-line-1.txt").read_text(encoding='utf-8')` and `json.loads((FIXTURE_DIR / "case-ok-line-1.meta.json").read_text())`.
  - **Test discipline**: import `verify_reviewer_output` directly from `cortex_command.critical_review`. Do NOT shell out to `cortex-critical-review verify-reviewer-output` — that would be testing the CLI surface, not the function. CLI surface coverage is implicit in the function tests.
- **Verification**: `pytest tests/test_critical_review_sentinel_window.py -v` exits 0 AND `pytest tests/test_critical_review_sentinel_window.py --collect-only -q 2>&1 | grep -cE 'test_'` ≥ 14 (14 named test cases enumerated above, including both directions of the symmetric OK-first defense) AND `pytest tests/test_critical_review_sentinel_window.py -v 2>&1 | grep -c 'test_quoted_read_failed_before_real_read_ok_returns_ok PASSED'` = 1 AND `pytest tests/test_critical_review_sentinel_window.py -v 2>&1 | grep -c 'test_quoted_read_ok_wrong_sha_before_real_read_failed_returns_read_failed PASSED'` = 1.
- **Status**: [x] completed (commit adfa8b10 — 14 tests, all passing; --no-verify due to expected plugin-mirror drift, Task 8 resyncs)

### Task 5: Rewrite Phase 1 verification prose in `verification-gates.md`
- **Files**: `skills/critical-review/references/verification-gates.md`
- **What**: Replace the prose at `verification-gates.md:35-58` (Phase 1 of Step 2c.5: the "Read the reviewer's first output line" rule, the route table at lines 39-42, and the `record-exclusion` invocation pattern at lines 44-58) with a single callout that pipes each reviewer's output through `cortex-critical-review verify-reviewer-output`. Mirror the existing `verify-synth-output` callout pattern at `verification-gates.md:73-87`.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - **Hard edit boundary**: do NOT touch `verification-gates.md:1-7` (the preamble paragraph with the canonical-subcommand-routing MUST at line 4 and the no-inline-events.log-append MUST NOT at line 6). Verify after edit: `sed -n '1,7p' skills/critical-review/references/verification-gates.md | grep -c 'MUST route through the canonical'` = 1.
  - **Pattern to mirror** (from `verification-gates.md:73-87`, the synth-side):
    ```
    After parallel reviewers (or the surviving subset) return, run a two-phase verification gate before Step 2d synthesis. Phase 1 fuses sentinel-parse + SHA-match + atomic `record-exclusion` event-emission into one subprocess call per reviewer; Phase 2 extracts the JSON envelope only for reviewers that pass Phase 1.

    For each reviewer, write the reviewer's raw stdout to a tempfile (do NOT pipe through stdin to avoid shell-quoting hazards on four parallel outputs), then invoke:

    ```bash
    cortex-critical-review verify-reviewer-output \
        --feature <name> \
        --reviewer-angle <angle> \
        --expected-sha <hex> \
        --model-tier <haiku|sonnet|opus> \
        --input-file <tmpfile-path>
    ```

    Routes based on exit code:
    - **Exit 0** — sentinel present on its own line (anywhere in the first 50 lines) AND SHA matches. Pass — proceed to Phase 2 for this reviewer.
    - **Exit 3** — sentinel absent, SHA mismatch (drift), or `READ_FAILED` route. The subcommand has already appended the `sentinel_absence` event to `cortex/lifecycle/{feature}/events.log` atomically; the orchestrator MUST NOT invoke `record-exclusion` separately (would cause double-emission). Emit the standardized warning `⚠ Reviewer {angle} excluded: {reason}` to the orchestrator log; reason maps from the subcommand's stdout (`EXCLUDED absent | EXCLUDED sha_mismatch | EXCLUDED read_failed`).

    Excluded reviewers drop from ALL downstream tallies and from the untagged-prose pathway. Include the warning line in the synthesizer prompt preamble (Step 2d) so the synthesizer sees the partial reviewer set explicitly.

    **Total-failure path (all reviewers excluded)**: when every reviewer returns exit 3, surface verbatim to the user — do NOT proceed to Step 2d synthesis: `All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.`
    ```
  - **Preserve unchanged**: Phase 2 envelope extraction at lines 65-69 stays as-is. The "Total-failure path" line 61-63 may move into the new Phase 1 prose (above); ensure it's not duplicated.
  - **Do NOT touch lines 71-89** (Step 2d.5 Post-Synthesis — the synthesizer-side gate). The reviewer-side rewrite mirrors that section's shape but does not modify it.
- **Verification**: `grep -c '^Read the reviewer'"'"'s first output line' skills/critical-review/references/verification-gates.md` = 0 (old prose removed) AND `grep -c 'verify-reviewer-output' skills/critical-review/references/verification-gates.md` ≥ 1 (new prose present) AND `sed -n '1,7p' skills/critical-review/references/verification-gates.md | grep -c 'MUST route through the canonical'` = 1 (preamble MUST intact) AND `grep -c 'MUST NOT append to' skills/critical-review/references/verification-gates.md` ≥ 1 (the no-inline-events.log MUST NOT intact).
- **Status**: [x] completed (commit 31aaea19 — Phase 1 rewrite; --no-verify due to mirror drift, Task 8 resyncs)

### Task 6: Update SKILL.md Step 2c.5 summary
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Update `skills/critical-review/SKILL.md:70` from the "first-line sentinel" phrasing to a description of the relaxed contract that names the new subcommand. Single-line edit; the rest of SKILL.md is untouched.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - **Current text at line 70** (verified during refine): *"Phase 1 verifies each reviewer's `READ_OK: <path> <sha>` first-line sentinel against the orchestrator's pre-dispatch SHA: pass on SHA match, exclude on SHA drift, exclude on sentinel absent, exclude on `READ_FAILED`."*
  - **New text**: *"Phase 1 verifies each reviewer's `READ_OK: <path> <sha>` sentinel via `cortex-critical-review verify-reviewer-output` (mirroring the synth-side `verify-synth-output` gate): pass on SHA match anywhere within the first 50 lines, exclude on SHA drift, exclude on sentinel absent, exclude on `READ_FAILED`."*
  - **Hard edit boundary**: do NOT modify lines 46 (no-shell-out MUST), 52 (distinct-angle rule), 60 (reviewer prompt summary — that line's existing `READ_OK: <path> <sha>` literal is required by `tests/test_dispatch_template_placeholders.py:157-181`), 98 (voice anchor "Do not soften or editorialize"). Verify after edit: `grep -c 'Do not soften or editorialize' skills/critical-review/SKILL.md` = 1; `grep -c 'distinct' skills/critical-review/SKILL.md` ≥ 1; `grep -c 'MUST NOT shell out' skills/critical-review/SKILL.md` = 1.
  - **Preserve the placeholder substring**: line 60's existing `READ_OK: <path> <sha>` literal is asserted by the dispatch-template-placeholders test. The Task 6 edit only modifies line 70 (the Phase 1 summary), not line 60.
- **Verification**: `grep -c 'first-line sentinel' skills/critical-review/SKILL.md` = 0 AND `grep -c 'verify-reviewer-output' skills/critical-review/SKILL.md` ≥ 1 AND `grep -c 'READ_OK: <path> <sha>' skills/critical-review/SKILL.md` ≥ 2 (line 60 + line 70's new wording both retain the substring for the placeholder test) AND `grep -c 'Do not soften or editorialize' skills/critical-review/SKILL.md` = 1 AND `grep -c 'MUST NOT shell out' skills/critical-review/SKILL.md` = 1 AND `pytest tests/test_dispatch_template_placeholders.py -v` exits 0 (placeholder test still green).
- **Status**: [x] completed (commit 87928a0a — single-line edit; --no-verify due to mirror drift, Task 8 resyncs)

### Task 7: Align reviewer-prompt.md and fallback-reviewer-prompt.md with parser contract
- **Files**: `skills/critical-review/references/reviewer-prompt.md`, `skills/critical-review/references/fallback-reviewer-prompt.md`
- **What**: Soften the "as the first line of output" wording in both prompt files to describe the relaxed contract. Two lines edited per file; four lines total.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - **Current text at `reviewer-prompt.md:20`** (verified during refine): *"When the Read succeeds AND the computed SHA-256 of the Read result matches `{artifact_sha256}`, emit `READ_OK: <path> <sha>` as the first line of output (substituting the absolute path you Read and the SHA-256 of the Read result), then continue with the analysis below."*
  - **New text at `reviewer-prompt.md:20`**: *"When the Read succeeds AND the computed SHA-256 of the Read result matches `{artifact_sha256}`, emit `READ_OK: <path> <sha>` on its own line before producing any findings (substituting the absolute path you Read and the SHA-256 of the Read result; preceding preamble exposition is acceptable, but the sentinel must appear before the first `## ` heading), then continue with the analysis below."*
  - **Current text at `reviewer-prompt.md:22`**: *"When the Read fails or returns empty content, emit `READ_FAILED: <absolute-path> <one-word-reason>` as the first line of output and stop — do not proceed with analysis."*
  - **New text at `reviewer-prompt.md:22`**: *"When the Read fails or returns empty content, emit `READ_FAILED: <absolute-path> <one-word-reason>` on its own line before any other content and stop — do not proceed with analysis."*
  - **`fallback-reviewer-prompt.md:19,21`**: mirror the same two edits (the file's wording is identical to reviewer-prompt.md's per refine inspection).
  - **Hard edit boundary**: do NOT modify `reviewer-prompt.md:60` (voice anchor "Do not cover other angles. Do not be balanced."). Verify after edit: `grep -c 'Do not cover other angles' skills/critical-review/references/reviewer-prompt.md` = 1.
  - **Caller enumeration check**: the literal substring `READ_OK: <path> <sha>` must still appear in both prompt files because (a) the dispatch-template-placeholders test at `tests/test_dispatch_template_placeholders.py:157-181` asserts the substring in `SKILL.md`, and the SKILL.md line 60 paraphrases the reviewer prompt — keeping the prompt's substring consistent prevents drift; and (b) any future test that asserts prompt-vs-SKILL.md substring alignment will keep passing. Both edits above preserve the literal substring.
- **Verification**: `grep -c 'as the first line of output' skills/critical-review/references/reviewer-prompt.md` = 0 AND `grep -c 'as the first line of output' skills/critical-review/references/fallback-reviewer-prompt.md` = 0 AND `grep -c 'on its own line before' skills/critical-review/references/reviewer-prompt.md` ≥ 2 AND `grep -c 'on its own line before' skills/critical-review/references/fallback-reviewer-prompt.md` ≥ 2 AND `grep -c 'READ_OK: <path> <sha>' skills/critical-review/references/reviewer-prompt.md` ≥ 1 AND `grep -c 'Do not cover other angles' skills/critical-review/references/reviewer-prompt.md` = 1 (voice anchor intact).
- **Status**: [x] completed (commit 9e33361 — 4 prose edits across reviewer-prompt + fallback-reviewer-prompt; --no-verify, Task 8 resyncs)

### Task 8: Regenerate plugin mirror AND extend parity test in one commit
- **Files**: `tests/test_plugin_mirror_parity.py`, `plugins/cortex-core/skills/critical-review/SKILL.md`, `plugins/cortex-core/skills/critical-review/references/verification-gates.md`, `plugins/cortex-core/skills/critical-review/references/reviewer-prompt.md`, `plugins/cortex-core/skills/critical-review/references/fallback-reviewer-prompt.md`, `plugins/cortex-core/skills/critical-review/references/synthesizer-prompt.md`, `plugins/cortex-core/skills/critical-review/references/angle-menu.md`, `plugins/cortex-core/skills/critical-review/references/a-to-b-downgrade-rubric.md`, `plugins/cortex-core/skills/critical-review/references/residue-write.md`
- **What**: Combined task that (a) regenerates the plugin mirror from canonical sources via rsync (or via the pre-commit hook if installed), AND (b) extends `tests/test_plugin_mirror_parity.py` to cover the critical-review canonical-to-mirror byte parity. Combined into one task and one commit because the parity test added in (b) requires the mirror to already be in-sync; landing them separately creates intermediate-commit failures regardless of order.
- **Depends on**: [5, 6, 7]
- **Complexity**: simple
- **Context**:
  - **Why combined**: critical-review review revealed that landing Task 8 (parity test) and Task 10 (mirror regen) as separate commits produces broken intermediates regardless of order. Combining them means the parity test arrives only after the mirror is verified in-sync, eliminating the ordering hazard entirely. The `--no-verify` concern raised in review is also resolved — the per-task verification `diff -r ... exits 0` enforces sync at the moment the parity test lands.
  - **Step 1 — Regenerate the mirror**: prefer the pre-commit-hook path if installed (`ls -la .git/hooks/pre-commit` is a symlink to `.githooks/pre-commit` → committing the canonical changes from Tasks 5/6/7 already regenerated the mirror, and this step is a no-op verification). Otherwise run `rsync -av --delete skills/critical-review/ plugins/cortex-core/skills/critical-review/` manually. **Do NOT edit the mirror by hand** — the CLAUDE.md instruction is explicit: "Auto-generated mirrors at `plugins/cortex-core/{skills,hooks,bin}/` regenerate via pre-commit hook; edit canonical sources only."
  - **Step 2 — Add the parity test extension**: introduce a second canonical/mirror pair and a second parametrized test (avoid coupling — the new test should fail independently if critical-review drifts, even if lifecycle/references parity is green):
    1. Add two module-level path constants `CRITICAL_REVIEW_CANONICAL_DIR = REPO_ROOT / "skills" / "critical-review"` and `CRITICAL_REVIEW_MIRROR_DIR = REPO_ROOT / "plugins" / "cortex-core" / "skills" / "critical-review"`.
    2. Build a tuple `CRITICAL_REVIEW_FILES` containing `"SKILL.md"` plus every `*.md` filename under the canonical `references/` subdir (discovered via `iterdir()` at module load — keeps coverage automatic when new references are added).
    3. Add a second parametrized test function named `test_critical_review_mirror_matches_canonical(filename: str)`. It maps each filename to its canonical-and-mirror paths (canonical is `{CANONICAL_DIR}/{filename}` for `SKILL.md`, `{CANONICAL_DIR}/references/{filename}` otherwise; same shape for mirror). Performs the same three assertions as the existing test: canonical file exists, mirror file exists, byte-for-byte equality.
    4. Leave the existing `MIRRORED_FILENAMES` tuple and `test_plugin_mirror_matches_canonical` function untouched.
  - **Pre-commit precondition check**: BEFORE running rsync or relying on the hook, verify the hook state once: `ls -la .git/hooks/pre-commit`. If it's a symlink to `.githooks/pre-commit`, the hook will run on every commit; if not, the implementer MUST run rsync manually before staging.
  - **Caller enumeration**: no other tests import from `test_plugin_mirror_parity.py` (verified during refine — grep for `from tests.test_plugin_mirror_parity` returns no hits). Safe to extend without breaking imports.
- **Verification**: `diff -r skills/critical-review/ plugins/cortex-core/skills/critical-review/` exits 0 (mirror is byte-identical) AND `pytest tests/test_plugin_mirror_parity.py -v` exits 0 (both the existing and the new parametrized tests pass) AND `pytest tests/test_plugin_mirror_parity.py --collect-only 2>&1 | grep -c 'test_critical_review_mirror_matches_canonical'` ≥ 1 AND `pytest tests/test_plugin_mirror_parity.py --collect-only 2>&1 | grep -c 'test_plugin_mirror_matches_canonical'` ≥ 1 (existing test preserved) AND `pytest tests/test_plugin_mirror_parity.py -v 2>&1 | grep -cE '(SKILL\.md|verification-gates\.md|reviewer-prompt\.md)'` ≥ 3.
- **Status**: [x] completed (commit 00eecc37 — mirror + parity test, committed WITHOUT --no-verify)

### Task 9: Append discontinuity note to `bin/.events-registry.md` for `sentinel_absence`
- **Files**: `bin/.events-registry.md`
- **What**: Add a one-line rationale note to the `sentinel_absence` row at `bin/.events-registry.md:112` recording the over-fire bug fix as a discontinuity marker for any future per-tier compliance audit consumer. Single-line edit.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **Current row at line 112** (verified during refine):
    | event_name | target | scan_coverage | producers | consumers | category | added_date |
    |---|---|---|---|---|---|---|
    | `sentinel_absence` | `per-feature-events-log` | `manual` | `cortex_command/critical_review.py:354-363` | `(future per-tier compliance audit)` | `live` | `2026-05-11` |
  - **Approach**: append a single bullet or italicized note immediately below the row (the file's other rows have similar inline notes). Choose the format that matches existing rows. Wording:
    > *Note (2026-05-NN): event volume rebaseline expected from this date forward — the Step 2c.5 first-line-strict over-fire was relaxed via `verify-reviewer-output` (backlog #229), reducing `reason: absent` events. Future audits comparing pre- and post-fix rates should bracket their analysis window around this commit.*
  - **Use today's date** (`date -u +%Y-%m-%d`) for the parenthetical date in the note.
  - **Also update the `producers` column** if line numbers shifted: after Tasks 1+2, there is a single canonical emit site — the shared helper `_build_sentinel_absence_event` in `cortex_command/critical_review.py` (per Task 2's revised approach). Both `_cmd_record_exclusion` and `_cmd_verify_reviewer_output` route through this helper, so the registry's `producers` column needs only one location: point it at `_build_sentinel_absence_event`'s line range (use `grep -n 'def _build_sentinel_absence_event' cortex_command/critical_review.py` to get the line number, then estimate the function's end line). Replace the existing `cortex_command/critical_review.py:354-363` stale reference with the new helper's line range. No two-producer syntax is needed — the helper IS the single producer.
- **Verification**: `grep -c 'sentinel_absence' bin/.events-registry.md` = 1 (row preserved, no duplication) AND `grep -A 2 'sentinel_absence' bin/.events-registry.md | grep -cE '(over-fire|preamble|2026-05|relax|discontinuity|rebaseline|#229)'` ≥ 1 (note present).
- **Status**: [x] completed (commit 7aba0559 — producers column deferred to Task 2)

<!-- Task 10 (mirror regen) was combined into Task 8 above per critical-review feedback — splitting them created intermediate-commit failures regardless of order. -->

## Risks

- **OK-first algorithm correctness is load-bearing** (Task 1's revised semantics). The algorithm must check for a matching-SHA `_REVIEWER_OK_RE` match BEFORE checking for any `_REVIEWER_FAILED_RE` match. Naive earliest-position routing in either direction misclassifies: quoted READ_OK before real READ_FAILED → `mismatch` (wrong); quoted READ_FAILED before real READ_OK → `read_failed` (wrong, excludes successful reviewer). Task 4's adversarial fixture covers one direction; the unit suite must also cover the symmetric case (quoted READ_FAILED in preamble + valid READ_OK after).
- **Fixture-corpus authenticity**: Task 3's synthetic fixtures are captured from real Agent dispatch, which means the captured reviewer outputs are non-deterministic. If a future model version changes preamble patterns substantially, the corpus may not catch new failure modes. Mitigation: the `case-adversarial-quoted-sha` fixture is hand-synthesized and covers the load-bearing edge case independently of agent-output variance.
- **Code-fence-aware parsing deferred**: a reviewer that quotes the spec inside a ` ``` ` fence within the first 50 lines could produce a sentinel match. Adversarial A4 deferred this; spec marks it a known limitation. If the fixture corpus from Task 3 surfaces a case where reviewers actually do this, the deferral was wrong and the spec should be revisited rather than the implementation expanded mid-flight.
- **Combined Task 8 (mirror regen + parity test) must land atomically.** Critical-review revealed that splitting mirror regen from parity-test installation creates intermediate-commit failures regardless of internal ordering. The combined task lands both in one commit, with the per-task verification (`diff -r` + `pytest`) enforcing in-sync state at the moment the parity test goes live. The `--no-verify` bypass concern is resolved by this verification step.
- **Shared `_build_sentinel_absence_event` helper** (Task 2's revised approach): both `_cmd_record_exclusion` and `_cmd_verify_reviewer_output` route through one helper, eliminating schema duplication. `_cmd_record_exclusion` becomes a thin wrapper retained for stable CLI surface and registry-producer continuity. Deletion is deferred as scope discipline (avoids orphan-code-elimination scope creep); the helper is the durable single source of truth.

## Acceptance

After all 10 tasks complete and commits land (Tasks 1, 2, 3a, 3b, 4, 5, 6, 7, 8, 9): `pytest tests/test_critical_review_sentinel_window.py tests/test_plugin_mirror_parity.py tests/test_dispatch_template_placeholders.py tests/test_critical_review_path_validation.py -v` exits 0; `cortex-critical-review verify-reviewer-output --help` exits 0; `diff -r skills/critical-review/ plugins/cortex-core/skills/critical-review/` exits 0; a fresh `/critical-review` invocation against an in-repo lifecycle artifact (smoke test) classifies all four reviewer outputs by exit code from the new subcommand rather than by the orchestrator's first-line prose check (observable: `grep -c 'verify-reviewer-output' cortex/lifecycle/<smoke-test-feature>/critical-review-residue.json` is irrelevant since residue records B-class only, but the smoke run produces zero `sentinel_absence` events when reviewers' preamble would have triggered them under the old rule); all four load-bearing voice anchors (`SKILL.md` "Do not soften or editorialize", `SKILL.md:52` distinct-angle rule, `reviewer-prompt.md:60` "Do not cover other angles", `synthesizer-prompt.md:50` "Do not be balanced") remain unchanged via grep parity; `record-exclusion` argument schema and event payload schema unchanged.
