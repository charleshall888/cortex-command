# Plan: unify-lifecycle-phase-detection-around-claudecommon-with-statusline-exception

## Overview

Promote `cortex_command.common.detect_lifecycle_phase()` to a structured-dict canonical detector that distinguishes `implement` from `implement-rework`, replace its CLI's bare-string output with JSON, and rewire the bash hook to inline-batch a single `python3 -c` call that processes all `lifecycle/*/` dirs in one Python interpreter session (paying cold start once regardless of N). The skill prose still references the single-dir `detect-phase` CLI for individual queries; the hook owns its own batching to keep SessionStart latency constant. Three-layer parity tests guard the residual statusline bash mirror (kept structural for the < 500ms latency budget) and the hook's bash glue layer; a precondition check makes the hook's Python dependency explicit. The boundary projection at `current_phase` and `backlog/index.json` keeps the serialized scalar-string contract intact while expanding its vocabulary to include `"implement-rework"`. The vocabulary expansion is propagated through every literal-string consumer the critical review surfaced — including the prose writer in `skills/lifecycle/references/{implement,review}.md`, the `rework_cycles` counter at `cortex_command/dashboard/data.py:330`, and the BacklogItem dataclass docstring — so the new phase value is recognized everywhere it is produced or consumed, not just in the two callsites the spec originally enumerated.

## Tasks

### Task 1: Extend canonical detector and switch CLI to JSON

- **Files**: `cortex_command/common.py`
- **What**: Change `detect_lifecycle_phase(feature_dir: Path)` return type from `str` to `dict[str, str | int]` with keys `phase`, `checked`, `total`, `cycle`. Add `implement-rework` to the phase vocabulary (returned when `review.md` exists with the most recent `verdict` matching `CHANGES_REQUESTED`); compute `cycle` as the count of `verdict` regex matches in `review.md` (default 1 when absent). Switch `_cli_detect_phase` to emit one line of minified JSON to stdout.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Definition at `cortex_command/common.py:88-156`. CLI handler at `cortex_command/common.py:453-458`. CLI dispatch shim at L469-492.
  - Vocabulary per R1: `{"research", "specify", "plan", "implement", "implement-rework", "review", "complete", "escalated"}`.
  - Dict keys: `phase: str`, `checked: int`, `total: int`, `cycle: int`. Defaults when artifacts missing: `checked=0`, `total=0`, `cycle=1`.
  - Algorithm sketch: keep the existing artifact-ladder ordering. When `review.md` indicates CHANGES_REQUESTED-rework re-entry to implement (per the existing `phase = implement` branch in the artifact ladder for CHANGES_REQUESTED re-entry), return `phase = "implement-rework"` instead of `"implement"`. `cycle` reads `review.md` regex-match count for `verdict`.
  - Import graph stays stdlib-only (`json`, `os`, `re`, `sys`, `pathlib`). No new imports.
  - CLI emit format: `json.dumps({"phase": ..., "checked": ..., "total": ..., "cycle": ...}, separators=(",", ":"))` followed by a newline.
- **Verification**:
  - `python3 -c "from cortex_command.common import detect_lifecycle_phase; from pathlib import Path; r = detect_lifecycle_phase(Path('lifecycle/unify-lifecycle-phase-detection-around-claudecommon-with-statusline-exception')); assert isinstance(r, dict) and set(r.keys()) == {'phase', 'checked', 'total', 'cycle'}, r"` exits 0.
  - `python3 -m cortex_command.common detect-phase lifecycle/unify-lifecycle-phase-detection-around-claudecommon-with-statusline-exception | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert set(d.keys())=={'phase','checked','total','cycle'}, d"` exits 0.
- **Status**: [ ] pending

### Task 2: Boundary projection at dashboard and backlog index

- **Files**: `cortex_command/dashboard/data.py`, `backlog/generate_index.py`
- **What**: Adapt the two callers that consume `detect_lifecycle_phase`'s return value to project the new dict to a scalar string at the boundary. `current_phase` and `lifecycle_phase` remain scalar strings; the dict is the in-process API only.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - `cortex_command/dashboard/data.py:322` currently does `current_phase: str | None = detect_lifecycle_phase(feature_dir)` — change to read the `phase` field from the dict return (preserving the `None` branch when `feature_dir` is missing if existing semantics required it; per R10 detector returns dict with `phase="research"` for non-existent dirs).
  - `backlog/generate_index.py:148` currently does `lifecycle_phase: str | None = detect_lifecycle_phase(lc_dir)` — same projection. (Spec mentions L115; current line is L148 — drift; grep for the call site.)
  - The dashboard's existing `current_phase` literal-string assertions at `cortex_command/dashboard/tests/test_data.py:1150` and templates tests at `test_templates.py:156` continue to pin against the scalar string — boundary projection preserves these.
  - Vocabulary expansion: `current_phase` and `lifecycle_phase` may now hold the new value `"implement-rework"`.
- **Verification**:
  - `python3 -c "from cortex_command.common import detect_lifecycle_phase; from pathlib import Path; r = detect_lifecycle_phase(Path('lifecycle/unify-lifecycle-phase-detection-around-claudecommon-with-statusline-exception')); print(r['phase'])"` exits 0 with a single phase string.
  - `python3 backlog/generate_index.py && python3 -c "import json; data = json.load(open('backlog/index.json')); items = data.get('items', data) if isinstance(data, dict) else data; phases = [i.get('lifecycle_phase') for i in (items if isinstance(items, list) else items.values()) if i.get('lifecycle_phase') is not None]; assert all(isinstance(p, str) for p in phases), phases"` exits 0 (asserts `lifecycle_phase` remains a scalar string in `backlog/index.json` after the change).
- **Status**: [ ] pending

### Task 3: Fold `parse_plan_progress` into canonical detector

- **Files**: `cortex_command/dashboard/data.py`, `cortex_command/dashboard/poller.py`, `cortex_command/dashboard/seed.py`, `cortex_command/dashboard/tests/test_data.py`
- **What**: Delete the `parse_plan_progress` function at `cortex_command/dashboard/data.py:340-362`. Update its callers to consume `checked` and `total` from the canonical detector's dict via `parse_feature_events` (the dashboard's per-feature aggregator). Drop the test class `parse_plan_progress` tests at `cortex_command/dashboard/tests/test_data.py:178-265` (or migrate the fixture matrix to exercise `detect_lifecycle_phase` directly if equivalent coverage is desired).
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**:
  - Definition at `cortex_command/dashboard/data.py:340-362`.
  - Callers: `cortex_command/dashboard/poller.py:37` (import), `:178` (call); `cortex_command/dashboard/data.py:12` (docstring), `:40` (re-export?); `cortex_command/dashboard/seed.py:534` (comment); test imports at `cortex_command/dashboard/tests/test_data.py:8-9, 40, 178-265`.
  - Replace the poller's `pp = parse_plan_progress(slug, project_lifecycle_dir)` line with a call to the canonical detector for the same lifecycle dir, then read `pp = (result["checked"], result["total"])` (or whatever shape the surrounding code expects).
- **Verification**:
  - `grep -c 'def parse_plan_progress' cortex_command/dashboard/data.py` returns 0.
  - `grep -rc 'parse_plan_progress' cortex_command/dashboard/` returns 0.
  - `pytest cortex_command/dashboard/tests/ -x` exits 0.
- **Status**: [ ] pending

### Task 4: Update `compute_slow_flags` to handle `implement-rework`

- **Files**: `cortex_command/dashboard/data.py`, `cortex_command/dashboard/tests/test_data.py`
- **What**: Update the `current_phase == "implement"` branch in `compute_slow_flags` (around `cortex_command/dashboard/data.py:1196`) to match both `"implement"` AND `"implement-rework"` for stall-detection purposes. Add a test case in `test_data.py` that exercises the rework path: `current_phase = "implement-rework"`, last activity older than the threshold, asserts `slow_flag` is set.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Source line `cortex_command/dashboard/data.py:1196`.
  - Use a tuple membership check: `current_phase in ("implement", "implement-rework")`.
  - Test should mirror the structure of any existing slow-flag test for `current_phase == "implement"`.
- **Verification**:
  - `grep -E 'current_phase == "implement-rework"|current_phase in \(.*"implement-rework"' cortex_command/dashboard/data.py` returns ≥1 match.
  - `pytest cortex_command/dashboard/tests/test_data.py -x -k slow` exits 0.
- **Status**: [ ] pending

### Task 5: Align rework vocabulary across writers and consumers

- **Files**: `cortex_command/overnight/report.py`, `cortex_command/dashboard/data.py`, `skills/lifecycle/references/implement.md`, `skills/lifecycle/references/review.md`, `cortex_command/overnight/backlog.py`
- **What**: Coordinate the rework vocabulary change across the **prose writer** (the actual writer is in skill markdown — there is no Python writer for the `review→implement` rework re-entry) and **all literal-string consumers** that branch on `"implement"` for rework detection:
  1. **Update the prose writers** in `skills/lifecycle/references/implement.md:258` and `skills/lifecycle/references/review.md:203` — change the documented `phase_transition` payload from `"to": "implement"` to `"to": "implement-rework"` for the CHANGES_REQUESTED re-entry case (the only place these files emit a `review→implement` transition template).
  2. **Update `report.py:632`** `reimplementing` membership check from `phase_transitions[-1].get("to") == "implement"` to `phase_transitions[-1].get("to") in {"implement", "implement-rework"}`.
  3. **Update `cortex_command/dashboard/data.py:330`** rework-cycle counter from `if prev_to == "review" and curr_to == "implement":` to `if prev_to == "review" and curr_to in ("implement", "implement-rework"):` — without this, the dashboard's `rework_cycles` field reports 0 for every post-CHANGES_REQUESTED re-entry once the writer change lands.
  4. **Update the docstring at `data.py:299-300`** (`rework_cycles` description) and the inline comment at `data.py:324-325` to reflect the new vocabulary.
  5. **Update `cortex_command/overnight/backlog.py:73-74`** BacklogItem dataclass docstring vocabulary list to include `implement-rework` (and `escalated` if currently missing).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - The rework re-entry transition (`from: review, to: implement`) is **not written by any Python file** — `grep '"to":.*"implement"' cortex_command/` returns only test fixtures (`seed.py:522` and `tests/test_data.py:1151,1172,1213`), all of which are *initial* `plan→implement` transitions and stay unchanged. The actual writer is the LLM-driven prose protocol in the two skill markdown files above.
  - Initial `plan→implement` transitions stay `"to": "implement"`. Only the CHANGES_REQUESTED re-entry becomes `"to": "implement-rework"`. Test fixtures using `from: plan, to: implement` stay unchanged.
  - The `rework_cycles` counter at `data.py:330` is the dashboard's existing rework metric. Failing to update it would invert the change's motivation — rework would become *less* visible on the dashboard.
- **Verification**:
  - `grep -c '"to": "implement-rework"' skills/lifecycle/references/implement.md skills/lifecycle/references/review.md` returns ≥2.
  - `grep -c 'implement-rework' cortex_command/overnight/report.py` returns ≥1.
  - `grep -E 'curr_to in \(.*"implement-rework"|curr_to == "implement-rework"' cortex_command/dashboard/data.py` returns ≥1 match in the `parse_feature_events` rework-cycle counter.
  - `grep -c 'implement-rework' cortex_command/overnight/backlog.py` returns ≥1.
  - `pytest cortex_command/overnight/tests/ cortex_command/dashboard/tests/ -x` exits 0.
- **Status**: [ ] pending

### Task 6: Delete sibling Python implementation; re-point consumers

- **Files**: `tests/lifecycle_phase.py` (delete), `tests/test_lifecycle_state.py`
- **What**: Delete `tests/lifecycle_phase.py`. Update `tests/test_lifecycle_state.py` to import `detect_lifecycle_phase` from `cortex_command.common` instead of from the sibling, and update assertions to read the `phase` field from the dict return.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Sibling lives at `tests/lifecycle_phase.py:28-91` (verbatim copy of canonical's logic at the time it was authored).
  - Single consumer: `tests/test_lifecycle_state.py`.
  - Consumer assertions currently expect a bare string return; update each to read `result["phase"]`.
- **Verification**:
  - `test ! -f tests/lifecycle_phase.py` exits 0.
  - `grep -rc 'tests.lifecycle_phase\|from .lifecycle_phase\|from tests.lifecycle_phase' tests/` returns 0.
  - `pytest tests/test_lifecycle_state.py -x` exits 0.
- **Status**: [ ] pending

### Task 7: Replace bash hook ladder with inline-batch Python + glue

- **Files**: `hooks/cortex-scan-lifecycle.sh`, `plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh` (regenerated by `just build-plugin` and staged in this task's commit)
- **What**: Restructure the per-feature-dir loop in `hooks/cortex-scan-lifecycle.sh` so that **one inline `python3 -c` invocation** processes all `lifecycle/*/` dirs in a single Python interpreter session, emitting one NDJSON-or-tab-separated record per dir. Bash then iterates the records and applies R3's normative wire-format encoding per dir. The existing `determine_phase()` subroutine is split into two: a Python-side detector loop (called once, batched) and a bash-side glue function (called per dir, takes pre-parsed `phase, checked, total, cycle` as arguments — no subprocess inside). Re-emit using R3's normative encoding:
  - `phase=="implement"` AND `total>0` → `"implement:$checked/$total"`
  - `phase=="implement"` AND `total==0` → `"implement:0/0"`
  - `phase=="implement-rework"` → `"implement-rework:$cycle"`
  - any other phase → bare phase string verbatim
  After editing, run `just build-plugin` and stage **both** the canonical and mirror file in the same commit so the pre-commit drift hook (`.githooks/pre-commit:159` Phase 4) does not reject the commit.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - **Why inline-batch, not per-dir subprocess**: Python cold start is ~30-80ms per invocation. This repo currently has 34 active lifecycle dirs; per-dir subprocess would cost ~1-3s at every SessionStart. Inline batching pays the cold start once regardless of N, keeping SessionStart latency constant.
  - **Inline-batch shape (pattern reference)**: a single `python3 -c '<script>' <dir1> <dir2> ...` invocation that imports `from cortex_command.common import detect_lifecycle_phase`, iterates `sys.argv[1:]`, and prints one tab-separated record per dir to stdout: `<dir>\t<phase>\t<checked>\t<total>\t<cycle>`. Bash then reads via `while IFS=$'\t' read -r dir phase checked total cycle; do ...`.
  - **Single-dir CLI is unchanged**: `python3 -m cortex_command.common detect-phase <dir>` still emits a single JSON object per spec R2 — that surface is for the skill prose and ad-hoc callers. The hook does NOT use the single-dir CLI; it inlines its own batched detector.
  - Existing bash ladder at L170-207 with regexes like `grep -cE '^\s*-\s+\*\*Status\*\*: \[x\]'` and `sed -n` for `verdict` — all removed.
  - Existing precedent for `python3 -c` and `python3 -m` invocation in the same hook at `hooks/cortex-scan-lifecycle.sh:379` — pattern-match for shebang and stderr discipline.
  - The bash glue function is test-covered by Task 12 layer 12a; the inline-batch invocation's iteration behavior is test-covered by Task 14 layer 12c (which feeds it a fixture matrix of dirs).
  - Stderr discipline: subprocess stderr from `python3 -c` must NOT redirect to stdout — JSON/TSV parse will choke on stderr leak. Use `2>/dev/null` if the precondition (Task 8) has already validated `cortex_command.common` imports cleanly.
  - Comment at L168 (`Mirrors claude.common.detect_lifecycle_phase — keep in sync...`) is now misleading; rewrite to: `# Inline-batches cortex_command.common.detect_lifecycle_phase across all lifecycle/*/ dirs in one Python invocation. Statusline (claude/statusline.sh) is a separate documented bash-only mirror — see DR-6 / parity test tests/test_lifecycle_phase_parity.py.`
  - **Plugin mirror**: `.githooks/pre-commit` Phase 3 auto-runs `just build-plugin` when canonical-source paths are staged, but the regenerated mirror lands **unstaged** in the working tree. Phase 4's drift loop (`git diff --quiet -- "plugins/$p/"`) compares working tree to index and fails the commit unless the implementer also stages the mirror. Run `just build-plugin && git add hooks/cortex-scan-lifecycle.sh plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh` before each commit on this task.
- **Verification**:
  - `grep -c 'python3 -c' hooks/cortex-scan-lifecycle.sh` returns ≥1 (inline-batch invocation present in `determine_phase` region).
  - `grep -cE 'sed -n.*verdict|grep -cE.*Status.*\[ x\]' hooks/cortex-scan-lifecycle.sh` returns 0 (old ladder removed).
  - `bash -n hooks/cortex-scan-lifecycle.sh` exits 0 (syntax check).
  - `just build-plugin && git diff --quiet plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh` exits 0 (mirror byte-identity after regen).
  - End-to-end smoke test: `time bash hooks/cortex-scan-lifecycle.sh </dev/null` exits 0 in this repo (with N=34 lifecycle dirs) in **< 500ms wall clock**, confirming the inline-batch design pays the cold start once.
- **Status**: [ ] pending

### Task 8: Add hook precondition check after lifecycle-dir guard

- **Files**: `hooks/cortex-scan-lifecycle.sh`, `plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh` (regenerated; staged with canonical in this task's commit per Task 7's plugin-mirror Context note)
- **What**: Insert a precondition block after the existing `[[ -d "$LIFECYCLE_DIR" ]] || exit 0` guard at `hooks/cortex-scan-lifecycle.sh:21` and before the feature-dir iteration. The block runs `command -v python3 >/dev/null && python3 -c "import cortex_command.common" 2>/dev/null`; on failure it emits the diagnostic `cortex_command not available; cortex-scan-lifecycle hook requires the cortex CLI — install via 'uv tool install -e .' from the cortex-command repo` to stderr and exits non-zero. No bash fallback ladder. Run `just build-plugin && git add hooks/cortex-scan-lifecycle.sh plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh` before commit.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**:
  - Existing guard at L21: `[[ -d "$LIFECYCLE_DIR" ]] || exit 0`.
  - Iteration loop at L247.
  - The new block belongs strictly between these two regions so non-cortex repos exit silently at L21 and never trigger the precondition.
  - Diagnostic exact text per R4 acceptance.
  - Same plugin-mirror staging discipline as Task 7.
- **Verification**:
  - In a fresh tmpdir without `lifecycle/`: `cd "$(mktemp -d)" && PATH=/usr/bin bash <repo>/hooks/cortex-scan-lifecycle.sh </dev/null; echo $?` returns 0 (silent exit at L21 guard).
  - In a fresh tmpdir with `mkdir lifecycle`: `cd "$(mktemp -d)" && mkdir lifecycle && PATH=/usr/bin bash <repo>/hooks/cortex-scan-lifecycle.sh </dev/null 2>&1; echo $?` returns non-zero with the diagnostic on stderr (Python without `cortex_command` installed under restricted PATH).
  - `just build-plugin && git diff --quiet plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh` exits 0.
- **Status**: [ ] pending

### Task 9: Replace skill prose ladder with CLI invocation

- **Files**: `skills/lifecycle/SKILL.md`, `plugins/cortex-interactive/skills/lifecycle/SKILL.md` (regenerated by `just build-plugin` and staged in this task's commit)
- **What**: Replace the prose phase-detection pseudo-ladder in `skills/lifecycle/SKILL.md` Step 2 "Artifact-Based Phase Detection" (currently L43-66) with an instruction to invoke `python3 -m cortex_command.common detect-phase <feature_dir>` and route on the returned `phase` field. Retain a one-line-per-phase reference table mapping each `phase` value to its semantic meaning. After editing, run `just build-plugin && git add skills/lifecycle/SKILL.md plugins/cortex-interactive/skills/lifecycle/SKILL.md` so the per-task commit passes the drift hook (`.githooks/pre-commit:159` Phase 4).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Current Step 2 at L41-66 is a prose ladder mirroring the canonical detector.
  - Edit canonical (`skills/lifecycle/SKILL.md`) and stage the regenerated mirror in the same commit.
  - Reference table phases: `research`, `specify`, `plan`, `implement`, `implement-rework`, `review`, `complete`, `escalated`.
- **Verification**:
  - `grep -c 'python3 -m cortex_command.common detect-phase' skills/lifecycle/SKILL.md` returns ≥1.
  - `grep -cE 'plan\.md exists with all \[x\]' skills/lifecycle/SKILL.md` returns 0.
  - `grep -c 'implement-rework' skills/lifecycle/SKILL.md` returns ≥1 (reference table includes the new phase).
  - `just build-plugin && git diff --quiet plugins/cortex-interactive/skills/lifecycle/SKILL.md` exits 0.
- **Status**: [ ] pending

### Task 10: Document statusline structural exception

- **Files**: `claude/statusline.sh`
- **What**: Add a comment block above the bash phase ladder at `claude/statusline.sh:377-402` explaining the structural exception: the < 500ms latency budget (`requirements/observability.md:23, 91`) prohibits subprocessing to Python; this is a deliberate bash-only mirror of `cortex_command.common.detect_lifecycle_phase`; equivalence is enforced by the parity test at `tests/test_lifecycle_phase_parity.py`. Logic at L377-402 is unchanged.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Insert above L377. Existing comment at L377 (`# --- Phase detection (fast, mirrors cortex-scan-lifecycle.sh) ---`) is rewritten or extended.
  - The comment block must include the four substrings `bash-only mirror`, `< 500ms`, `parity test`, and `cortex_command.common` to satisfy R11 acceptance.
- **Verification**:
  - `sed -n '370,410p' claude/statusline.sh | grep -cE 'bash-only mirror|< 500ms|parity test|cortex_command\.common'` returns ≥3 (one match per searched substring; passes when at least three of the four are present, but all four are required by R11 — implementation should aim for all four).
  - `bash -n claude/statusline.sh` exits 0 (syntax check unaffected).
- **Status**: [ ] pending

### Task 11: Document `implement-rework` vocabulary expansion

- **Files**: `backlog/generate_index.py` (inline comment) — alternatively `skills/backlog/references/schema.md` if such a schema doc exists.
- **What**: Add a comment near the `lifecycle_phase` projection in `backlog/generate_index.py` enumerating the value set this field may hold — `{"research", "specify", "plan", "implement", "implement-rework", "review", "complete", "escalated"}` — and noting that `"implement-rework"` was added in this change. If `skills/backlog/references/schema.md` exists, prefer updating it instead and link from the inline comment.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**:
  - `lifecycle_phase` projection lives in `backlog/generate_index.py` near L148 (`detect_lifecycle_phase` call site).
  - Existence of `skills/backlog/references/schema.md` is uncertain — implementer should `test -f` first; if absent, inline comment is sufficient per R10.
- **Verification**:
  - `grep -c 'implement-rework' backlog/generate_index.py` returns ≥1, OR `grep -c 'implement-rework' skills/backlog/references/schema.md` returns ≥1.
- **Status**: [ ] pending

### Task 12: Parity test layer 12a — hook glue unit test

- **Files**: `tests/test_lifecycle_phase_parity.py` (new)
- **What**: Create the test file with the **glue unit test class** (R12a). For each fixture mapping `{phase, checked, total, cycle}` → expected wire-format string (per R3 normative encoding), invoke the hook's bash glue logic and assert byte-equal output. Cover the ≥10 cases enumerated in spec R12a.
- **Depends on**: [1, 7]
- **Complexity**: simple
- **Context**:
  - Test path: `tests/test_lifecycle_phase_parity.py`.
  - Glue invocation strategies (choose one): (i) source the relevant fragment of `hooks/cortex-scan-lifecycle.sh` via `bash -c` with a here-doc that pre-defines the JSON input, then captures stdout; (ii) use `subprocess.run(["bash", "-c", glue_fragment_with_input])` and compare stdout. Either approach passes — pick whichever is cleaner.
  - Fixture cases (verbatim from R12a): research/0/0/1→"research"; implement/0/0/1→"implement:0/0"; implement/2/5/1→"implement:2/5"; implement-rework/0/0/1→"implement-rework:1"; implement-rework/3/5/2→"implement-rework:2"; review/5/5/1→"review"; complete/5/5/1→"complete"; escalated/0/0/1→"escalated"; plan/0/0/1→"plan"; specify/0/0/1→"specify".
  - Test function naming: at least one function name matches the regex `def test_.*glue` (per R12 acceptance grep).
- **Verification**:
  - `pytest tests/test_lifecycle_phase_parity.py::test_hook_glue -v` (or matching test class) exits 0.
  - `grep -cE 'def test_.*glue' tests/test_lifecycle_phase_parity.py` returns ≥1.
- **Status**: [ ] pending

### Task 13: Parity test layer 12b — statusline ladder + parser vs canonical Python

- **Files**: `tests/test_lifecycle_phase_parity.py` (modify), `tests/fixtures/lifecycle_phase_parity/` (new fixture dirs)
- **What**: Add the **statusline-vs-canonical test class** (R12b), exercising **both** the upstream phase-detection ladder block (`claude/statusline.sh:377-402`) and the **downstream wire-format parser block** (`claude/statusline.sh:500-553`, including the `implement:N/M`-to-progress-bar splitter at L535-546):
  1. **Ladder sub-test**: Source `claude/statusline.sh:377-402` into a `bash -c` here-doc harness with `_lc_fdir` pre-defined to a fixture path. Parse the emitted `_lc_phase` value back into `(phase, checked, total)` (cycle excluded — statusline cycle-blindness). Invoke `detect_lifecycle_phase(fixture)` directly; compare `(phase, checked, total)` against the parsed dict. Map statusline `"implement"` to either Python `"implement"` or `"implement-rework"` per the documented cycle-blindness exception.
  2. **Parser sub-test**: Source the `claude/statusline.sh:500-553` parser block into a separate harness; feed it each wire-format string from R12a's fixture matrix (`"research"`, `"implement:0/0"`, `"implement:2/5"`, `"implement-rework:1"`, `"implement-rework:2"`, `"review"`, `"complete"`, `"escalated"`, `"plan"`, `"specify"`); assert the parser produces a sensible rendered display string for each — specifically that `implement-rework:N` does not crash, fall through silently, or produce malformed output. The exact display string is implementation-defined; the assertion is "parser handles every R12a wire-format value without error."
- **Depends on**: [1, 12]
- **Complexity**: simple
- **Context**:
  - Statusline ladder at `claude/statusline.sh:377-402` reads `verdict` not `cycle` (per L382-388).
  - Statusline parser block at `claude/statusline.sh:500-553` has the `implement-rework)` BARE case (L533) and `implement:*` (L535) — verify these handle the new vocabulary cleanly.
  - Fixture matrix per spec R12b: empty dir; research.md only; research+spec; plan.md with 0/N (N>0); plan.md with M/N (0<M<N); plan.md with N/N; review.md APPROVED; review.md CHANGES_REQUESTED at cycle 1 only; review.md REJECTED; events.log feature_complete.
  - Fixture dirs live under `tests/fixtures/lifecycle_phase_parity/<case-name>/`; this task creates them.
  - Test function naming: at least one matches `def test_.*statusline.*ladder` and one matches `def test_.*statusline.*parser`.
- **Verification**:
  - `pytest tests/test_lifecycle_phase_parity.py -k statusline -v` exits 0.
  - `grep -cE 'def test_.*statusline' tests/test_lifecycle_phase_parity.py` returns ≥2 (one for ladder, one for parser).
  - `ls tests/fixtures/lifecycle_phase_parity/ | wc -l` returns ≥9.
- **Status**: [ ] pending

### Task 14: Parity test layer 12c — hook end-to-end

- **Files**: `tests/test_lifecycle_phase_parity.py` (modify)
- **What**: Add the **hook end-to-end test class** (R12c). For each fixture dir from Task 13, invoke `bash hooks/cortex-scan-lifecycle.sh` (or its `determine_phase` wrapper if independently invokable — otherwise drive the hook via its main entry point with the fixture as the lifecycle target) and assert emit equals what Task 12's glue table predicts when given `detect_lifecycle_phase(fixture)` as input. This catches integration bugs between subprocess invocation and the glue.
- **Depends on**: [1, 7, 8, 12, 13]
- **Complexity**: simple
- **Context**:
  - Reuses fixture dirs created in Task 13.
  - Computes the expected output by combining Task 1's `detect_lifecycle_phase` call (to get the dict) with Task 12's R3 normative encoding table (to get the wire-format string).
  - Test function naming: at least one matches `def test_.*hook_end_to_end`.
- **Verification**:
  - `pytest tests/test_lifecycle_phase_parity.py -x` exits 0 (full file passes; covers all three layers together).
  - `grep -cE 'def test_.*hook_end_to_end' tests/test_lifecycle_phase_parity.py` returns ≥1.
  - `grep -cE 'def test_.*glue|def test_.*statusline|def test_.*hook_end_to_end' tests/test_lifecycle_phase_parity.py` returns ≥3 (R12 acceptance — three layers represented).
- **Status**: [ ] pending

### Task 15: Final byte-identity sanity check

- **Files**: `plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh`, `plugins/cortex-interactive/skills/lifecycle/SKILL.md` (read-only verification)
- **What**: Final verification that all canonical/mirror pairs are byte-identical at the end of the implement phase. Tasks 7, 8, and 9 each regenerate and stage their respective mirrors as part of their per-task commits (per their plugin-mirror Context notes), so this task is a sanity gate, not a regen step. Run `just build-plugin` once more (idempotent — should produce no diff) and confirm.
- **Depends on**: [7, 8, 9]
- **Complexity**: simple
- **Context**:
  - Build target at `justfile:475-507`.
  - Drift gate at `.githooks/pre-commit:149-176`.
  - If this task surfaces a diff, the per-task drift discipline in Tasks 7/8/9 broke down — investigate the offending commit rather than papering over with a fresh regen commit here.
- **Verification**:
  - `just build-plugin` exits 0 with no working-tree changes (`git diff --quiet plugins/`).
  - `diff hooks/cortex-scan-lifecycle.sh plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh` exits 0.
  - `diff skills/lifecycle/SKILL.md plugins/cortex-interactive/skills/lifecycle/SKILL.md` exits 0.
- **Status**: [ ] pending

## Verification Strategy

After all tasks complete:

1. **Full repo test suite**: `pytest -x` exits 0 (R14).
2. **Three-layer parity**: `pytest tests/test_lifecycle_phase_parity.py -v` shows all 12a, 12b, 12c cases passing.
3. **Hook end-to-end smoke**: `bash hooks/cortex-scan-lifecycle.sh </dev/null` in this repo exits 0; `cd "$(mktemp -d)" && bash <repo>/hooks/cortex-scan-lifecycle.sh </dev/null` exits 0 (no `lifecycle/` → silent).
4. **Plugin drift**: `.githooks/pre-commit` runs clean on staged files (Task 13 verification).
5. **Vocabulary spot-check**: After interacting with a feature in CHANGES_REQUESTED-rework state, `python3 -m cortex_command.common detect-phase <that-dir>` emits `{"phase":"implement-rework",...}` and `backlog/index.json` shows `"lifecycle_phase":"implement-rework"` for that item.

## Veto Surface

- **SessionStart latency: addressed by inline-batch design.** The original spec deferred latency mitigation to a "profile-then-conditional" gate; with N=34 active lifecycle dirs in this repo, that gate would have tripped on first run. Task 7 now uses inline batching (one `python3 -c` for the whole loop) so cold start is paid once regardless of N. The hook's verification includes a `time bash hooks/cortex-scan-lifecycle.sh` < 500ms wall-clock check on this repo's full lifecycle/ — if that fails, the inline-batch design didn't land correctly and Task 7 needs rework. No new CLI subcommand was added; the single-dir `detect-phase` CLI is unchanged.
- **Task 5 writer location is prose, not Python.** Verified during critical review: no Python file in `cortex_command/` writes `{"from": "review", "to": "implement"}`. The actual writer is the LLM-driven prose protocol in `skills/lifecycle/references/{implement,review}.md`. Task 5 includes prose updates in those files; the plan no longer relies on a Python writer that doesn't exist.
- **Task 12 fixture parity scope.** Spec R12b explicitly excludes `cycle` from the statusline parity dimension because the statusline ladder does not extract cycle. This is structural, not a test gap. If the user wants cycle parity enforced on the statusline side, R11 would need to permit a sed-extraction add to the ladder — but that costs latency budget and was rejected during spec.
- **Task 11 schema-doc presence.** R10 acceptance allows either `skills/backlog/references/schema.md` OR an inline comment in `backlog/generate_index.py`. Implementer chooses based on what exists.
- **Task 15 vs pre-commit auto-regeneration.** Tasks 7, 8, and 9 now stage their own plugin mirrors per the drift-hook discipline (`.githooks/pre-commit:159` Phase 4). Task 15 is therefore a final sanity gate, not a regen step. If the user prefers to let pre-commit auto-regenerate at the final commit boundary instead of staging-per-task, Tasks 7/8/9 can be bundled into a single composite commit that regenerates once at the end — but this loses per-task commit granularity.

## Scope Boundaries

Per spec Non-Requirements (verbatim from `lifecycle/.../spec.md`):

- **NOT migrating `backlog/index.json` schema or dashboard `current_phase` to a structured object.** Both remain scalar strings; the dict is the function's in-process API only. Boundary projection at consumers handles this (R10).
- **NOT adding a `--json` flag or `detect-phase-detailed` sibling subcommand.** The CLI default switches to JSON in this change. Bare-string output is retired.
- **NOT adding a bash fallback ladder in the hook for the case where Python is unavailable.** Hook hard-fails per R4 (after the lifecycle-dir guard).
- **NOT migrating the statusline to Python or codegen.** The < 500ms latency budget is structural; the bash ladder stays. Equivalence is enforced by the three-layer parity tests in R12.
- **NOT adding `cortex detect-phase` as a top-level `cortex` CLI subcommand.** Following the existing precedent at `hooks/cortex-scan-lifecycle.sh:379` (`python3 -m cortex_command.pipeline.metrics`), the hook uses `python3 -m cortex_command.common detect-phase`.
- **NOT modifying the plugin manifest at `plugins/cortex-overnight-integration/.claude-plugin/plugin.json` to declare a Python dependency.** Runtime check (R4) handles dependency enforcement; manifest schema change is out of scope.
- **NOT updating `cortex_command/overnight/backlog.py` `TERMINAL_STATUSES` (the duplicate noted at `cortex_command/common.py:41-42`).** Separate follow-up.
- **NOT enforcing cycle parity between statusline and canonical Python.** Statusline ladder does not extract `cycle`; R12b excludes the cycle dimension; cycle correctness is enforced by R12a (glue unit) and R12c (hook end-to-end) instead.
