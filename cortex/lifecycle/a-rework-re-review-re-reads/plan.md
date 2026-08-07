# Plan: a-rework-re-review-re-reads

## Overview

A new wheel verb (`cortex-lifecycle-review-brief`) becomes the single source of the reviewer brief for both
the interactive and overnight paths. It archives the prior cycle's `review.md`, selects full vs rework-scoped
mode from `count_rework_cycles`, records a dispatch baseline SHA as an additive events.log row, and emits the
brief on stdout; `skills/build/references/review.md` keeps only control flow and the call, which is what funds
the zero-headroom byte budget. Overnight's cycle-2 prompt is rebuilt from the same brief, and the previously
unmeasured prompts directory gains a ratchet pin so review-shaping prose has no unpinned hiding place.

**Architectural Pattern**: layered
<!-- The brief is a pure builder layer (no I/O) beneath a CLI/IO layer; both consumers call inward. -->

Two decisions the spec left to Plan, resolved here and flagged in Risks:

- **Baseline-SHA storage.** Requirement 13 demands a machine-derived 40-hex SHA but names no store. events.log
  carries no SHA and no existing event fires at review dispatch, so the verb emits its own additive
  `review_dispatched` row (`cycle`, `mode`, `baseline_sha`) at every dispatch and reads the *prior* row's SHA
  as the rework baseline. ~130 bytes per dispatch — two orders of magnitude under the 5,672-byte `issues`
  array the spec rejected, and it makes requirements 7, 11 and 13 share one mechanism.
- **`PROTOCOL_VERSION` is not bumped.** Requirement 9 governs *shape changes*; introducing a verb changes no
  served payload, and requirement 19 deliberately makes a stale wheel degrade rather than halt — a floor bump
  would contradict that and strand out-of-repo consumers. The governance is *declared* in `protocol.py` so the
  next brief-shape change knows to bump. See Risks.

## Outline

### Phase 1: Scoped interactive review (tasks: 1, 2, 3, 4, 5, 6, 9, 10, 11, 13, 15)
**Goal**: the store, the verb and the `review.md` restructure that calls them ship as one live unit.
**Checkpoint**: a rework dispatch archives cycle N-1, emits a scoped brief carrying the prior issues, a
resolvable baseline SHA and a stated baseline decision, and `skills/build/references/` measures at or below
57964 with no new `# raised:` line.

### Phase 2: Overnight adoption (tasks: 7, 8, 12)
**Goal**: overnight's cycle-2 prompt is built from the shared brief in-process, and the template stops
biasing the reported cycle.
**Checkpoint**: the cycle-2 prompt contains the prior cycle's issue texts; no literal `"cycle": 1` example
reaches a rework reviewer.

### Phase 3: Ratchet parity (task: 14)
**Goal**: `cortex_command/pipeline/prompts/` is measured like every references directory.
**Checkpoint**: `tests/test_reference_size_ratchet.py` reports the prompts directory pinned and within pin,
and fails when the pin file is removed.

The resulting dependency waves are {1}, {2, 3, 4, 5, 6, 7, 8}, {9, 10, 11, 12, 14}, {13}, {15}; the two
single-task tail waves are inherent to the feature's spine — module → tests → prose restructure → end-to-end
proof — and are not a signal that the decomposition needs restructuring.

## Tasks

### Task 1: Build the review-brief module (pure builders + CLI, archive, baseline capture, fail-open)
- **Files**: `cortex_command/lifecycle/review_brief.py`
- **What**: The whole feature's core — a pure brief-building layer with no I/O (`build_full_brief`,
  `build_rework_brief`, `parse_verdict_block`, `parse_carried_forward`, `decide_test_baseline`) plus a CLI
  layer that archives the prior cycle, captures the dispatch SHA, and fails open. One module because the two
  layers share the brief's field contract and splitting them would only serialize one file.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Discriminant: `from cortex_command.lifecycle.counters import count_rework_cycles`
    (`counters.py:53`). Dispatch cycle `N = rework_cycles + 1`; mode is `rework` iff `rework_cycles >= 1`.
  - Root resolution: `_resolve_user_project_root_from_cwd()` / `CortexProjectRootError` from
    `cortex_command.common`, matching `stage_artifacts.py:109-112`. A hidden `--lifecycle-dir` escape
    (default `cortex/lifecycle`) mirrors `counters.py:103-107` so tests can point at a temp tree.
  - **Archive** (reqs 1, 2): `shutil.copy2(review.md, review-cycle-{N-1}.md)`, **copy never move**, and a
    no-op when the target already exists. Unconditional at dispatch, so cycle 1 (no `review.md`) is a silent
    no-op. `review.md` must exist continuously — `common.py:390-410` falls through to the plan-based step
    when it is missing, reporting `review` instead of `implement-rework`.
  - **Verdict-block parser**: performs the same fenced-JSON verdict extraction that `parse_verdict` performs
    at `cortex_command/pipeline/review_dispatch.py:202`. Reimplement it **here** rather than importing
    `review_dispatch` — that module pulls the Claude Agent SDK, an optional extra. Phase 2 imports this
    module, never the reverse.
  - **Baseline capture** (req 13): `git rev-parse HEAD` in the resolved root; emit an additive events.log row
    via `cortex_command.lifecycle_event`'s shared `log_event` writer —
    `{"event": "review_dispatched", "feature": …, "cycle": N, "mode": "full"|"rework", "baseline_sha": "<40hex>"}`.
    Idempotent: skip the append when a row with the same `cycle` already exists (the cycle-qualified presence
    check `advance.py` uses at `:251`). The rework baseline is the `baseline_sha` of the row with
    `cycle == N-1`.
  - **Baseline decision** (req 11): re-run iff `git diff <baseline_sha>..HEAD --name-only` reports any path
    outside `cortex/lifecycle/{feature}/*.md`. `events.log` is **not** exempt —
    `tests/test_clarify_critic_alignment_integration.py::test_post_migration_clarify_critic_events_are_jsonl`
    walks the real events.log tree. Two-dot `..` is correct (the baseline is always an ancestor on a rework).
    The brief states exactly one of `reuse baseline` / `re-run`.
  - **Rework brief contents** (reqs 7, 8, 10, 18): one checklist entry per prior-cycle issue text; the commit
    range `<baseline_sha>..HEAD`; the baseline decision; the bounding statement that scoping bounds *reading*,
    never *concluding*; a required `## Out-of-Scope Findings` heading that must be filled affirmatively even
    when empty; a required `## Prior-Cycle Checklist` section with one explicit disposition per prior issue;
    the by-reference carry-forward form naming the cycle **and** the condition, with the **once-only** bound
    stated. `parse_carried_forward` reads the archive for `### Requirement:` headings whose verdict line
    matches `carried forward from cycle`, and the brief lists those as **requiring re-verification**.
  - **Full brief contents** (req 12): the narrative moved out of `review.md` §2 — Stage 1 / Stage 2
    definitions and their tier gate, the `## Requirements Drift` section format (State / Findings / Update
    needed) and the `## Suggested Requirements Update` entry format (File / Section / Content), the review.md
    structure, the verdict field-name prohibitions, and the PARTIAL / uncertain-drift guidance.
  - Both modes name the **absolute** path of `cortex/lifecycle/{feature}/review.md` (req 5). The brief reaches
    a subagent, so no `${CLAUDE_SKILL_DIR}` token may appear in it (ADR-0009).
  - **Fail-open contract** (req 19): exit **0** = brief served; exit **3** = degraded — a **full** brief is
    still written to stdout and a `DEGRADED: <reason>` line to stderr. Degrade (never emit a scoped brief) when
    the archive is missing/unreadable, its verdict block is unparseable, its `issues` array is empty, or no
    prior `review_dispatched` row supplies a baseline SHA. An empty checklist is never emitted as a scoped
    brief — `parse_verdict`'s sentinel `{"verdict": "ERROR", "cycle": 0, "issues": []}` (`review_dispatch.py:177`)
    makes "empty" and "failed" indistinguishable downstream.
  - Structure mirrors `stage_artifacts.py`: pure helpers plus a thin `main(argv) -> int`.
- **Verification**: `uv run python -m cortex_command.lifecycle.review_brief --help` exits 0 and its output
  contains `--feature`; `grep -c 'def build_rework_brief' cortex_command/lifecycle/review_brief.py` = 1;
  `grep -cE '^[[:space:]]*(from|import)[[:space:]]+cortex_command\.pipeline' cortex_command/lifecycle/review_brief.py` = 0
  (no import of the SDK-bearing module; the pattern is anchored to an import statement at line start, so citing
  `review_dispatch.py:202` in a docstring or comment cannot trip it).
- **Status**: [x] done (4c61e56c 2026-08-07T08:56:46-04:00)

### Task 2: Deploy the verb (console script, bin wrapper, deployment row)
- **Files**: `pyproject.toml`, `bin/cortex-lifecycle-review-brief`, `tests/test_lifecycle_verb_deployment.py`
- **What**: Wires the module as `cortex-lifecycle-review-brief` so prose can call it and the contract lint can
  see its argparse surface.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `[project.scripts]` entry `cortex-lifecycle-review-brief = "cortex_command.lifecycle.review_brief:main"`.
  Copy `bin/cortex-lifecycle-counters` verbatim and re-point the four `cortex_command.lifecycle.counters`
  occurrences plus the two name literals; keep the four-branch order (FORCE_SOURCE → wheel probe →
  working-tree PYTHONPATH → exit 2 remediation) and `chmod +x`. Append the
  `(console_script, entry_point, bin_rel)` tuple to `VERBS` in `tests/test_lifecycle_verb_deployment.py` — the
  file's header rule is that the literal verb name must not appear there until both the pyproject row and the
  wrapper exist, so this task lands all three together. `plugins/cortex-core/bin/` is a mirror the pre-commit
  hook rebuilds from staged blobs; never stage it by hand.
- **Verification**: `test -x bin/cortex-lifecycle-review-brief` exits 0; `uv run pytest tests/test_lifecycle_verb_deployment.py -q` passes;
  `uv run cortex-check-contract` exits 0.
- **Status**: [x] done (cf246363 2026-08-07T09:29:35-04:00)

### Task 3: Commit the archive and correct the stale cycle docstring
- **Files**: `cortex_command/lifecycle/stage_artifacts.py`, `cortex_command/common.py`,
  `tests/test_stage_artifacts.py`
- **What**: Requirement 4 — the explicit allowlist gains `review-cycle-*.md` so archives enter git; and
  requirement 17 — `common.py`'s docstring stops describing `cycle` as a review.md regex count.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: In `collect_paths` (`stage_artifacts.py:324-376`) the `complete` branch enumerates fixed names.
  Archives are variable in number, so add a helper alongside `_capture_files` (`:177`) that enumerates
  `(root / lifecycle_rel).glob("review-cycle-*.md")` into explicit repo-relative paths — the module's
  explicit-add discipline forbids handing git a *directory* pathspec, not building the list by glob (see the
  module docstring's "Explicit-add discipline" section, which already licenses exactly this for `captures/`).
  Add the archives to the `complete` phase only. Update the module docstring's "Per-phase staged set" section
  to name them. `tests/test_stage_artifacts.py` asserts the complete-phase staged set **exactly** —
  `assert result["staged_paths"] == expected` against the `LIFECYCLE_COMPLETE` constant, at roughly `:252-253`
  and `:415-416` — so those exact-set assertions must gain the archive paths in this same task; a builder
  cannot repair a file outside its own list. In `common.py:462-463` replace `regex matches in review.md` with
  a line naming `review_verdict` events as what `cycle` counts (the implementation is at `:355`; the migration
  note is at `:308-309`). `common.py` is lifecycle-gated by CLAUDE.md — we are in the lifecycle.
- **Verification**: `grep -c 'regex matches in review.md' cortex_command/common.py` = 0 and
  `grep -c 'review_verdict' cortex_command/common.py` ≥ 1 in the docstring region;
  `grep -c 'review-cycle-\*' cortex_command/lifecycle/stage_artifacts.py` ≥ 1;
  `uv run pytest tests/test_stage_artifacts.py -q` passes.
- **Status**: [x] done (64aa2f18 2026-08-07T09:30:56-04:00)

### Task 4: Give the new event a typed subcommand
- **Files**: `cortex_command/lifecycle_event.py`, `tests/test_lifecycle_event_roundtrip.py`,
  `cortex_command/tests/test_lifecycle_event.py`
- **What**: Adds a `review-dispatched` entry to `_EVENT_SUBCOMMANDS` so the row's field contract is declared
  once in the ADR-0020 uniform shape rather than living only inside the brief verb.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `_EVENT_SUBCOMMANDS` at `cortex_command/lifecycle_event.py:257` maps subcommand →
  `(event_name, [FieldSpec…])`, each FieldSpec following the `(flag, emit_key, kind, required, choices)` tuple
  shape with `kind` drawn from `{_STR, _JSON}`. Add a subcommand named `review-dispatched` mapping to event
  name `review_dispatched`, with three FieldSpecs: `--cycle` (JSON kind, required, no choices); `--mode` (str
  kind, required, choices `full` / `rework`); `--baseline-sha` (str kind, required, no choices). The
  subcommand name is the event name with `_` rendered as `-`. This event is **not** in the ADR-0020
  hand-written exempt set (`clarify_critic`, `pr_opened`), so it gets a subcommand. Both test files may
  enumerate the subcommand table and so need a row for the new subcommand.
- **Verification**: `uv run cortex-lifecycle-event review-dispatched --help` exits 0;
  `uv run pytest tests/test_lifecycle_event_roundtrip.py cortex_command/tests/test_lifecycle_event.py -q` passes.
- **Status**: [x] done (d58a4fa2 2026-08-07T09:30:44-04:00)

### Task 5: Declare the brief protocol-governed
- **Files**: `cortex_command/lifecycle/protocol.py`
- **What**: Requirement 9 — records in the constant's own comment block that the reviewer brief's shape is
  part of the wheel↔prose contract, so a future shape change moves `PROTOCOL_VERSION` and the expectation
  range together. The integer is deliberately **not** moved here (see Overview and Risks).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: The append-only comment ladder above `PROTOCOL_VERSION = 3` (`protocol.py:34-41`) documents what
  each integer bought. Add a governance note there naming `cortex-lifecycle-review-brief` and stating that a
  brief-shape change the prose depends on is a floor bump; and extend the module docstring's two-sided
  description to say the brief is one of the served surfaces it governs.
- **Verification**: `grep -c 'review-brief' cortex_command/lifecycle/protocol.py` ≥ 1;
  `uv run pytest tests/test_protocol_parity.py -q` passes.
- **Status**: [x] done (67db2f28 2026-08-07T09:30:02-04:00)

### Task 6: Record ADR 0035
- **Files**: `cortex/adr/0035-reviewer-brief-emitted-by-verb-not-reference-prose.md`
- **What**: Writes the spec's Proposed ADR as an accepted ADR. **Renumbered**: the spec proposed `0030`, which
  is already taken by `0030-mode-agnostic-interactive-dispatch.md`; the next free number is 0035.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Body is the spec's "Proposed ADR" section (Context / Decision / Trade-off) verbatim, with the
  ADR-file front matter and heading shape used by `cortex/adr/0034-*.md`. Record the not-bumping decision from
  this plan's Overview as a consequence, so the next reader does not re-derive it. `cortex-adr-citation-audit`
  checks ADR citations; run it.
- **Verification**: `uv run cortex-adr-citation-audit` exits 0; `ls cortex/adr/0035-*.md` lists exactly one file.
- **Status**: [x] done (291a2338 2026-08-07T09:30:40-04:00)

### Task 7: Build overnight's cycle-2 prompt from the shared brief
- **Files**: `cortex_command/pipeline/review_dispatch.py`,
  `cortex_command/pipeline/tests/test_review_dispatch.py`
- **What**: Requirement 14 — cycle 2 stops reloading the cycle-1 template and appending a sentence, and
  instead builds its prompt from the shared brief with the in-process `issues` list.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: The current construction is `review_dispatch.py:596-609`; `issues` is a local in scope from
  `:401` and is already spliced into the fix agent's prompt at `:499`. Call
  `review_brief.build_rework_brief(...)` **in-process** — overnight must not go through the CLI entry point,
  because it needs no archive (it holds the prior issues in memory) and forcing it through a file it does not
  need is exactly what requirement 1 scopes out. Overnight already has its SHA pair at `:489-495` for the
  circuit breaker; thread `before_sha` as the baseline. Keep the existing `except (FileNotFoundError, OSError)`
  deferral path intact — a brief-construction failure must still write the deferral rather than raise.
  ADR-0015: `DispatchResult.success` / `could_not_run` discriminants and the `review_no_artifact` cause class
  must not move. `cortex_command/pipeline/tests/test_review_dispatch.py` exercises the cycle-2 prompt
  construction this task changes, so it is in Files for repair; task 12 then extends the same file.
- **Verification**: `grep -c 'Focus on whether the flagged issues were resolved' cortex_command/pipeline/review_dispatch.py` = 0;
  `grep -c 'build_rework_brief' cortex_command/pipeline/review_dispatch.py` ≥ 1;
  `uv run pytest cortex_command/pipeline/tests/test_review_dispatch.py -q` passes.
- **Status**: [x] done (13fc03c2 2026-08-07T09:33:31-04:00)

### Task 8: Stop the overnight template biasing the reported cycle
- **Files**: `cortex_command/pipeline/prompts/review.md`
- **What**: Requirement 15 — the worked Verdict JSON example at `:96` hardcodes `"cycle": 1`, which a cycle-2
  reviewer copies verbatim.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Line 96 sits inside the outer illustrative fence (lines 64–98), so a non-literal placeholder is
  correct there. Replace the hardcoded value with the placeholder token `{cycle number}` — the same `{…}` style
  the template already uses for `{requirement text}` (`:69`) — and keep line 55's "the review cycle number
  (integer)" description as the authority. Ordered after the brief module exists rather than after the
  overnight wiring, because once the hardcoded example is removed it is the brief — not task 7's wiring — that
  supplies a cycle-2 reviewer's cycle guidance.
- **Verification**: `grep -c '"cycle": 1' cortex_command/pipeline/prompts/review.md` = 0;
  `grep -c '{cycle number}' cortex_command/pipeline/prompts/review.md` = 1 (the placeholder is present in the
  worked example).
- **Status**: [x] done (6a922cd5 2026-08-07T09:30:27-04:00)

### Task 9: Test the archive, mode selection, and the fail-open contract
- **Files**: `cortex_command/lifecycle/tests/test_review_brief_cli.py`
- **What**: Pins requirements 1, 2, 5, 6 and 19 — the CLI-layer behaviors.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Build temp lifecycles with a real `git init` tree (the verb runs `git rev-parse`/`git diff`).
  Cases: cycle-1 dispatch with no `review.md` archives nothing and emits the full brief at exit 0; cycle-2
  dispatch copies `review.md` to `review-cycle-1.md` **byte-identically** while `review.md` still exists;
  running twice produces an identical tree (`find … -type f | sort` plus per-file checksums) and leaves a
  pre-existing archive's checksum unchanged; a lifecycle with one `CHANGES_REQUESTED` row yields the rework
  brief even though `common.py`'s reduced `cycle` reads 1 (req 6); both modes exit 0 and both name the review
  artifact path (req 5). Fail-open cases (req 19): archive deleted, archive with an unparseable verdict block,
  archive with an empty `issues` array, and no prior `review_dispatched` row — each must exit 3, write a
  **full** brief to stdout, name the reason on stderr, and emit **no** scoped-brief markers.
- **Verification**: `uv run pytest cortex_command/lifecycle/tests/test_review_brief_cli.py -q` passes.
- **Status**: [x] done (a7cdcb6c 2026-08-07T09:36:35-04:00)

### Task 10: Test brief content, carry-forward, baseline rule, and the SHA
- **Files**: `cortex_command/lifecycle/tests/test_review_brief_content.py`
- **What**: Pins requirements 7, 8, 10, 11, 13 and 18 — the pure-builder behaviors plus the git-derived rule.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Fixture lifecycle with a 3-issue prior verdict. Assert the emitted brief contains all three
  issue texts, a `git diff`-expressible range, and exactly one of `reuse baseline` / `re-run` (req 7); the
  bounding statement plus a required out-of-scope findings heading, and that a nothing-found review must still
  state it affirmatively (req 8); the carry-forward form, the once-only bound, and that a fixture whose prior
  review already marks an item carried-forward lists that item as requiring re-verification (req 10); three
  dispositions demanded, one per prior issue (req 18). Baseline rule (req 11) as three cases over a real temp
  repo: a diff touching only `cortex/lifecycle/{feature}/plan.md` → `reuse`; one touching
  `cortex/lifecycle/{feature}/events.log` → `re-run`; any source path → `re-run`. SHA (req 13): the rework
  brief matches `\b[0-9a-f]{40}\b` and `git cat-file -e <sha>^{commit}` exits 0.
- **Verification**: `uv run pytest cortex_command/lifecycle/tests/test_review_brief_content.py -q` passes.
- **Status**: [x] done (089260fd 2026-08-07T09:37:35-04:00)

### Task 11: Test archive staging and phase-detection invariance
- **Files**: `cortex_command/lifecycle/tests/test_stage_artifacts_review_archive.py`
- **What**: Pins requirements 3 and 4 — archives are committed, and their presence does not move the detected
  phase.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: For req 4, stage a temp lifecycle carrying `review.md` plus `review-cycle-1.md` at
  `--phase complete` and assert the archive appears in `staged_paths` and that
  `git status --porcelain` reports no untracked `review-cycle-*.md`. Existing per-phase staged-set tests are
  the shape to follow — find them via `grep -rl "collect_paths" cortex_command/lifecycle/tests tests`. For
  req 3, assert `common.detect_lifecycle_phase` (and `cortex-lifecycle-state --feature …`) return the same
  phase for the same tree with and without archives present, including the `implement-rework` case, since
  `_stat_key(review.md)` (`common.py:467`) is a memoization key over that exact path.
- **Verification**: `uv run pytest cortex_command/lifecycle/tests/test_stage_artifacts_review_archive.py -q` passes.
- **Status**: [x] done (4798fb65 2026-08-07T09:37:02-04:00)

### Task 12: Test the overnight cycle-2 prompt
- **Files**: `cortex_command/pipeline/tests/test_review_dispatch.py`
- **What**: Pins requirement 14's acceptance — the cycle-2 prompt carries the prior cycle's issue texts, which
  today it does not despite `issues` being in scope.
- **Depends on**: [7] (write-serialization: cortex_command/pipeline/tests/test_review_dispatch.py)
- **Complexity**: simple
- **Context**: Extend the existing cycle-2 coverage in this file (the module already exercises the rework path
  — see the `deferred_dir.glob(f"{feature}-q*.md")` cases at `:325`/`:377`/`:475`/`:725`). Capture the prompt
  handed to the second `dispatch_task` call and assert each cycle-1 issue string appears in it. Also assert the
  brief-construction failure path still writes the deferral rather than raising.
- **Verification**: `uv run pytest cortex_command/pipeline/tests/test_review_dispatch.py -q` passes.
- **Status**: [x] done (3b172cf8 2026-08-07T09:36:43-04:00)

### Task 13: Restructure review.md prose onto the verb
- **Files**: `skills/build/references/review.md`, `skills/build/references/size-pin.txt`,
  `plugins/cortex-core/skills/build/references/size-pin.txt`
- **What**: Requirement 12 — §§1–2 lose the narrative output-shape prescription to the verb and gain the verb
  call, the fail-open control flow, and the baseline pointer. Net byte change for the directory must be ≤ 0.
- **Depends on**: [9, 10]
- **Complexity**: complex
- **Context**:
  - **Delete** (moved into the brief by task 1): line 19 (stage definitions and the drift observation rule,
    564 B), line 21 (the review.md structure and drift/suggested-update formats, 495 B), line 29 (PARTIAL and
    uncertain-drift guidance, 186 B), and the now-redundant input enumeration inside line 15.
  - **Retain**: line 17's single-writer rule, §3/§3a/§4 in full, and — explicitly — the Verdict JSON fenced
    block at lines 25–27 (143 B). It is the contract `parse_verdict` depends on and must not be reachable only
    through a subprocess.
  - **Add**: a `cortex-lifecycle-review-brief --feature {feature}` bash call in §2; one sentence that the verb
    archives the prior cycle, selects its own mode, records the dispatch baseline, and emits the brief to hand
    the reviewer verbatim; the fail-open rule ("non-zero exit or no output → run a **full** review against the
    Verdict contract below and report the degradation; never dispatch a scoped review on a missing or empty
    checklist"); and one clause in §1's Test baseline paragraph pointing at the brief's reuse/re-run decision.
    Requirement 13's SHA capture needs **no** prose — the verb owns it.
  - **Budget arithmetic** (measured, not asserted): §2 is 2119 B of which the retained JSON block is 143, so
    ≤ 1976 B is movable; the genuinely movable set above is ~1475 B against ~640 B of additions, i.e. ~-835 B.
    **If the arithmetic does not close, trim elsewhere in the directory — never drop a requirement, never
    raise the pin.** Surface a shortfall rather than silently omitting the cheapest addition; the archive call
    is the addition with no other test guarding it and is therefore the one at risk.
  - **Sync sequence** (order is load-bearing): `just ratchet-refs` → `just build-plugin` → `just ratchet-refs`.
    `build-plugin` does not carry `size-pin.txt`, so the mirror's pin is the one mirror path staged by hand;
    every other `plugins/cortex-core/` path is rebuilt from staged blobs by the pre-commit hook. The dedupe
    test reads the working tree, not the index.
  - ADR-0009: resolve `${CLAUDE_SKILL_DIR}` only in the SKILL.md body; no raw token may appear in this file.
  - No `<!-- pause: -->` marker exists in this file, so kept-pauses parity is untouched — confirm with a grep
    before editing.
- **Verification**: `uv run python -c "import sys;sys.path.insert(0,'scripts');import ratchet_refs;from pathlib import Path;print(ratchet_refs.measure(Path('skills/build/references')))"`
  prints a value ≤ 57964; `grep -c '# raised:' skills/build/references/size-pin.txt` = 2 (unchanged);
  `uv run pytest tests/test_reference_size_ratchet.py tests/test_dual_source_reference_parity.py tests/test_plugin_mirror_parity.py tests/test_check_skill_path.py -q` passes;
  `uv run cortex-check-contract` exits 0.
- **Status**: [x] done (a6a4478d 2026-08-07T09:42:08-04:00)

### Task 14: Ratchet the prompts directory
- **Files**: `scripts/ratchet_refs.py`, `cortex_command/pipeline/prompts/size-pin.txt`,
  `tests/test_reference_size_ratchet.py`
- **What**: Requirement 16 — the prompts directory gains a size pin and enters the ratchet's enumeration, so
  review-shaping prose has no unmeasured hiding place.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: `enumerate_reference_dirs` (`scripts/ratchet_refs.py:57`) builds `candidates` from
  `skills/*/references` and `plugins/*/skills/*/references`; append `cortex_command/pipeline/prompts` to that
  list. Its callers are `ratchet_write` and `check` in the same file, `tests/test_reference_size_ratchet.py`
  (already in Files), and the `ratchet-refs` recipe at `justfile:203-204`, which invokes the script unchanged
  and therefore needs **no** edit. Content-hash dedupe and the pin-file exclusion in `measure()` (which counts
  **all** regular files, not just `.md`) both apply unchanged. Seed the pin with `just ratchet-refs` — never
  hand-write it — which is why this task follows task 8: the template must be byte-final first. In
  `tests/test_reference_size_ratchet.py`, `test_mirror_dirs_deduplicate` partitions on
  `d.parent.parent == repo_root()/"skills"`, so the new directory lands in `plugin_names` as `pipeline`; there
  is no `skills/pipeline/`, so no overlap is introduced — assert that rather than leaving it incidental. Add
  the requirement's own criterion: the prompts directory is enumerated and within its pin, and removing the pin
  file makes `classify` report the missing-pin error.
- **Verification**: `uv run pytest tests/test_reference_size_ratchet.py -q` passes and
  `uv run python scripts/ratchet_refs.py` prints a `pinned` line naming `cortex_command/pipeline/prompts`.
- **Status**: [x] done (7dcff0f3 2026-08-07T09:34:30-04:00)

### Task 15: Prove the scoped path actually runs end to end
- **Files**: `cortex_command/lifecycle/tests/test_review_brief_end_to_end.py`,
  `cortex/lifecycle/a-rework-re-review-re-reads/captures/`
- **What**: Requirement 20 — every other criterion certifies an artifact exists and behaves in isolation; none
  would fail if the scoped path never ran. This one closes that.
- **Depends on**: [13, 14]
- **Complexity**: complex
- **Context**: Two halves, because the machine-checkable part cannot reach the reviewer agent.
  (a) An integration test, `@pytest.mark.serial` (it spawns real subprocesses), that drives a temp lifecycle
  through cycle-1 dispatch → a `CHANGES_REQUESTED` `review_verdict` row with a 3-issue verdict written to
  `review.md` → a rework commit → cycle-2 dispatch, invoking the real `bin/cortex-lifecycle-review-brief`
  wrapper with `CORTEX_COMMAND_FORCE_SOURCE=1` (per the wheel-vs-worktree hazard: `cortex-*` on PATH is the
  released wheel, so an unforced invocation would test the wrong code). Assert `review-cycle-1.md` exists and
  is byte-identical to the pre-dispatch `review.md`, and that the cycle-2 brief contains at least one cycle-1
  issue text and a resolvable SHA.
  (b) The disposition half (req 20's third clause) needs a real reviewer, so capture it from this lifecycle's
  own review: record the emitted brief and the resulting `review.md` under
  `cortex/lifecycle/a-rework-re-review-re-reads/captures/`, which `stage_artifacts._capture_files` already
  stages at every phase. Before relying on that rig, **produce and validate a discarded sample of the exact
  committed-evidence shape end to end** — write a throwaway capture, confirm it is enumerated by
  `_capture_files` and appears in `staged_paths`, then delete it.
- **Verification**: `uv run pytest cortex_command/lifecycle/tests/test_review_brief_end_to_end.py -q` passes;
  and `Interactive/session-dependent: the disposition half is evidenced by this lifecycle's own review capture,
  which cannot exist until the review phase runs.`
- **Status**: [x] done (914bc89d 2026-08-07T09:53:55-04:00)

## Risks

- **#454 sequencing.** The spec names this the strongest argument for holding Phase 1: a scoped reviewer told
  to escalate genuine out-of-checklist findings drives traffic into `escalated`, which has no verb to land
  operator direction in. #454 is in Plan in a concurrent session. The spec judges it non-blocking because
  escalation works and halts with findings presented — but it explicitly says that if #454 slips, that is a
  reason to hold Phase 1 rather than ship into it. **This is the one call worth making at approval.**
- **`PROTOCOL_VERSION` is not bumped.** Requirement 9's own acceptance ("the parity test passes at HEAD")
  passes on the unmodified repo, so it cannot decide this. The plan declares the governance without moving the
  floor, on the reasoning that no served shape changed and requirement 19 wants a stale wheel to degrade, not
  halt. The alternative — bump to 4 with the range widened to `[3, 4]` — costs a spurious halt for anyone
  holding an old plugin against a new wheel and buys nothing observable. Reversible either way; say so if you
  want the bump.
- **The brief and `prompts/review.md` still both carry the output shape.** Phase 2 rewires cycle 2 only, per
  requirement 14's scope. Cycle 1's overnight prompt keeps the template, so the ADR's "one source of truth"
  claim is true for the interactive path and for overnight rework, not yet for overnight cycle 1. Folding
  cycle 1 in would risk regressions across the whole overnight review path for no requirement; task 14's pin
  at least makes further drift visible.
- **A new events.log row on a hot path.** `review_dispatched` is ~130 bytes and events.log is parsed per line
  on every phase detection, statusline render, dashboard poll and hook. That is the cost the spec's rejected
  alternative measured at 5,672 bytes; this is ~2% of that, once per review dispatch. Additive rows are
  already pinned as inert by `tests/test_lifecycle_reverse_golden.py`, but if a reviewer wants zero new rows
  the fallback is a gitignored dotfile, at the cost of losing the SHA on a fresh clone.
- **ADR renumbered 0030 → 0035.** The spec's proposed number is taken. Flagged rather than silently changed.

## Acceptance

A rework re-review dispatched interactively archives cycle N-1 to `review-cycle-{N-1}.md` (with `review.md`
still present), receives a brief naming every prior-cycle issue, a resolvable 40-hex baseline SHA, a
`{sha}..HEAD` reading range and one stated reuse/re-run decision, and writes a `review.md` carrying one
disposition per prior issue plus an affirmative out-of-scope findings section; `just test` is green;
`skills/build/references/` measures at or below 57964 with no new `# raised:` line; and
`cortex_command/pipeline/prompts/` is enumerated and pinned by the reference-size ratchet.
