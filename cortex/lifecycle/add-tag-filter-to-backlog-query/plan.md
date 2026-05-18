# Plan: add-tag-filter-to-backlog-query

## Overview

Add a `--tag <TAG>` argparse argument (repeatable, AND-semantics, case-sensitive) to `cortex/backlog/ready.py` and a dedicated behavior-test file for the new filter. The filter narrows the `records` input upstream of `partition_ready` so both the ready `groups` and the `--include-blocked` `ineligible` arrays consume the same filtered set; the `all_items_ns` blocker-resolution corpus stays unfiltered to keep cross-corpus blocker-status lookups correct. Phase 2 amends the upstream `discovery-output-density-investigate-author-centric` spec and review to reference `cortex-backlog-ready --tag` instead of the never-existed `cortex-backlog list --tag`, and adds a forward-pointer note recording that ticket #233 resolved the wiring gap.

## Outline

### Phase 1: CLI filter (tasks: 1, 2)
**Goal**: `cortex-backlog-ready --tag phase2-trigger` returns ticket #232 and the new test file passes.
**Checkpoint**: `pytest tests/test_backlog_ready_tag_filter.py -q && pytest tests/test_backlog_ready_render.py -q` exit 0; `cortex-backlog-ready --tag phase2-trigger` exits 0 with #232 in the result.

### Phase 2: Upstream spec hygiene (tasks: 3)
**Goal**: Upstream spec Req 15's literal grep references the now-existing `cortex-backlog-ready --tag` syntax, and review.md carries a forward-pointer to ticket #233.
**Checkpoint**: `grep -c 'cortex-backlog list --tag' cortex/lifecycle/discovery-output-density-investigate-author-centric/{spec,review}.md` = 0 in both files; `grep -c 'Resolved by ticket #233' cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md` ≥ 1 (forward-pointer present).

## Tasks

### Task 1: Add `--tag` argparse flag and AND-semantics filter to `cortex-backlog-ready`
- **Files**: `cortex/backlog/ready.py`
- **What**: Register a repeatable `--tag` argument in `_parse_args` and apply an AND-semantics, case-sensitive set-membership filter on each record's `tags` field inside `_build_result` before `partition_ready` runs. The filter narrows the `records` input only — `all_items_ns` (the second positional, used for cross-corpus blocker resolution) must remain unfiltered. `_item_payload` is NOT modified — `tags` remain filter-input only, not wire-format output.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - File anchors in `cortex/backlog/ready.py`:
    - `_parse_args(argv) -> argparse.Namespace` at lines 375–392. Currently registers `--include-blocked` only. Register a new repeatable string flag named `--tag` using argparse's append action with a `None` default (do not use `[]` — see pitfall reference below), and provide help text describing repeatable AND semantics and case-sensitivity. After parsing, coerce a `None` value to an empty list before downstream use.
    - `_build_result(records, all_items_ns, *, include_blocked) -> dict` at lines 307–372. Extend the keyword surface with a `required_tags: list[str]` parameter. The filter step runs on `records` BEFORE the `namespaces` list-comprehension at line 320 — apply a set-membership predicate via stdlib `set` operations. The predicate must read each record's tag list via dict-`get` with a fallback to the empty list (records produced before the `tags` propagation landed may lack the key); a direct `r["tags"]` access would raise `KeyError` on tagless records and crash the no-`--tag` call path used by `/cortex-core:backlog pick` and `ready`. Pre-partition placement causes both `partition.ready` and `partition.ineligible` arrays (lines 348–370) to derive from the same already-filtered `namespaces` input — this is upstream input narrowing, not downstream inheritance.
    - **`all_items_ns` scoping invariant** (load-bearing): `all_items_ns` is the second positional argument passed to `partition_ready` at line 422. It MUST NOT be tag-filtered. `partition_ready` uses it to build `_build_status_lookup` (cortex_command/backlog/readiness.py:71–86), which resolves blocker references — a tagged item blocked by an untagged item must still see the untagged blocker's actual status, otherwise the reason string silently degrades to `"blocker not found: <uuid>"` or `"external blocker: <ref>"`.
    - `main(argv)` at lines 395–433. Thread the coerced tag list into the `_build_result` call at line 422.
  - Empty-`required_tags` semantics: subset-of-anything is vacuously true, so the no-`--tag` path is a no-op — existing byte-equivalent output preserved (covers Req 7). The dict-`get` fallback on `tags` also ensures the no-`--tag` path does not crash on the existing snapshot fixture's tagless records.
  - Pitfall reference: avoid `default=[]` on append actions ([Python bug 16399](https://bugs.python.org/issue16399)) — the mutable default is shared across parser instances and produces wrong-after-first-call behavior.
  - `tags` field availability in `index.json` records is guaranteed by `cortex_command/backlog/generate_index.py:177` for items the generator produced; however, fixtures and hand-built dicts (the snapshot test's `_FIXTURE_RECORDS`) may omit the key — hence the dict-`get` fallback above.
  - Reason-string contract in `cortex_command/backlog/readiness.py` is untouched — the filter excludes records before classification, so no new reason strings are introduced.
  - JSON error contract (`_emit_error` at line 98) and stale-index warning (`_check_stale_index` at line 105) remain unchanged; both run before any `--tag` filtering would matter.
- **Verification**:
  - `cortex-backlog-ready --help | grep -c '\-\-tag'` = 1 (validates argparse registration + Req 8).
  - `cortex-backlog-ready --tag phase2-trigger; echo $?` prints `0` (validates Req 1 — argparse accepts the flag without error).
  - `cortex-backlog-ready; echo $?` prints `0` and stdout JSON parses without error (validates the dict-`get` fallback on tagless records — the no-`--tag` path must not crash on real-world records lacking `tags`).
- **Status**: [x] done

### Task 2: Create `tests/test_backlog_ready_tag_filter.py` covering Reqs 2–7
- **Files**: `tests/test_backlog_ready_tag_filter.py`
- **What**: New behavior-test file with a lean per-test fixture (3–6 backlog records per test, written directly as `index.json` dicts via `json.dumps` plus minimal `.md` files) that exercises the `--tag` filter end-to-end via subprocess invocation of `cortex/backlog/ready.py`. Six test functions: `test_single_tag_match` (Req 2), `test_multi_tag_and_semantics` (Req 3), `test_case_sensitive_match` (Req 4), `test_zero_match_exits_zero_with_empty_groups` (Req 5), `test_filter_applies_to_ineligible` (Req 6), `test_blocker_resolution_uses_unfiltered_corpus` (validates the `all_items_ns` scoping invariant from Task 1). Keep fixtures separate from the snapshot test's `_FIXTURE_RECORDS`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - **Subprocess invocation form** (use this exact shape; the `python -m` variant fails because `cortex/__init__.py` and `cortex/backlog/__init__.py` do not exist):
    - `subprocess.run([sys.executable, str(REPO_ROOT / "cortex" / "backlog" / "ready.py"), *cli_args], capture_output=True, text=True, cwd=tmp_path)` where `REPO_ROOT = Path(__file__).resolve().parent.parent` (mirroring the path-resolution pattern in `tests/test_backlog_ready_render.py`).
    - The script self-injects its repo into `sys.path` via `_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent`, so `cortex_command` imports resolve against the real repo even when `cwd=tmp_path`. `BACKLOG_DIR = Path.cwd() / "cortex" / "backlog"` reads from the subprocess cwd, so the test fixture's `cortex/backlog/` tree under `tmp_path` is what the script consumes.
    - Do NOT invoke `bin/cortex-backlog-ready` (the bash shim) — direct subprocess against the `.py` avoids shim overhead and `CORTEX_COMMAND_ROOT` env wrangling.
  - **Fixture-build pattern** (mirrors the render test's self-contained approach):
    - Construct `index.json` directly via `json.dumps` rather than invoking `cortex_command/backlog/generate_index.py`. Generated records must include the `tags` key as a list-of-strings (e.g., `"tags": ["phase2-trigger"]`) — `_build_result` reads `r.get("tags") or []` from the index dict, NOT from re-parsed frontmatter. The test fixture's `.md` files only need to satisfy the stale-index check (their `tags:` frontmatter is not read by the filter).
    - Each fixture record dict mirrors the render test's `_FIXTURE_RECORDS` shape (`id`, `uuid`, `status`, `priority`, `type`, `blocked_by`, `parent`) plus the new `tags` key. Helper functions may be hand-written per the new test file's needs; do not import or extend `_FIXTURE_RECORDS` from the render test.
  - **Test specifics**:
    - `test_single_tag_match`: 3 records — one with `tags: ["phase2-trigger"]`, one with `tags: ["other"]`, one with `tags: []`. Assert `--tag phase2-trigger` returns only the first.
    - `test_multi_tag_and_semantics`: 4 records — `["tooling-gap"]`, `["X"]`, `["tooling-gap", "X"]`, `[]`. Assert `--tag tooling-gap --tag X` returns only the `["tooling-gap", "X"]` record.
    - `test_case_sensitive_match`: 2 records — `["phase2-trigger"]` and `["PHASE2-TRIGGER"]`. Assert `--tag PHASE2-TRIGGER` returns only the second, and `--tag phase2-trigger` returns only the first.
    - `test_zero_match_exits_zero_with_empty_groups`: 3 records, none with `nonexistent-tag-xyz`. Assert exit code 0, stdout JSON parses, and every group's `items` array is empty.
    - `test_filter_applies_to_ineligible`: 4 records — one ready with `["phase2-trigger"]`, one ready with `["other"]`, one blocked with `["phase2-trigger"]`, one blocked with `["other"]`. Run with `--tag phase2-trigger --include-blocked`. Assert both `groups[*].items` and `ineligible[*].items` contain only the `phase2-trigger`-tagged records.
    - `test_blocker_resolution_uses_unfiltered_corpus`: 2 records — record A `status: backlog, tags: ["phase2-trigger"], blocked_by: ["B"]`; record B `status: backlog, tags: ["other"]` (NOT tag-matching). Run with `--tag phase2-trigger --include-blocked`. Assert: A appears in `ineligible` with a reason string containing `"blocked by B: backlog"` (proves B's actual status was resolved from `all_items_ns` despite B being tag-filtered out of `records`). If the implementer incorrectly filters `all_items_ns` too, the reason will degrade to `"blocker not found: B"` or `"external blocker: B"` and the assertion fails.
- **Verification**:
  - `pytest tests/test_backlog_ready_tag_filter.py -q` exits 0 (validates Reqs 2, 3, 4, 5, 6 and the `all_items_ns` scoping invariant).
  - `pytest tests/test_backlog_ready_render.py -q` exits 0 (validates Req 7 — existing snapshot test unchanged; also catches any `record["tags"]` KeyError regression because the snapshot's tagless records pass through the new filter step).
- **Status**: [x] done

### Task 3: Amend upstream `discovery-output-density-investigate-author-centric` spec and review to reference `cortex-backlog-ready --tag`
- **Files**: `cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md`, `cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md`
- **What**: Update the command-name references in spec.md (lines 44, 64, 87) and review.md (lines 85, 88). On review.md, leave the historical "Actual" line on line 86 verbatim (it documents the pre-fix CLI state and does NOT contain the substring `cortex-backlog list --tag`) and append a forward-pointer sentence noting that ticket #233 resolved the gap. The forward-pointer's exact phrasing — `Resolved by ticket #233 (add-tag-filter-to-backlog-query) on 2026-05-18 — cortex-backlog-ready --tag phase2-trigger now functions.` — is verified by a presence-grep in this task's Verification, paired with the absence-grep, so mechanical substitution that erases institutional memory cannot satisfy the gate.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **Edits to `cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md`** (3 lines):
    - Line 44 (Req 15): contains the substring `cortex-backlog list --tag phase2-trigger` twice — once in the body sentence and once in the acceptance grep. Replace both occurrences with `cortex-backlog-ready --tag phase2-trigger`. The same line also contains a third reference inside parentheses: `"if cortex-backlog does not currently support --tag filtering, file a separate wiring ticket rather than dropping this requirement"` — this is the escape-hatch clause that justified ticket #233 existing in the first place. Leave this clause verbatim: it is intentional historical context recording the spec's contingency design, not a current-state claim. Editing it would erase the rationale for ticket #233's existence.
    - Line 64: contains `cortex-backlog list --tag not supported`. Replace with `cortex-backlog-ready --tag was not supported (resolved by ticket #233)` — this preserves the historical edge-case context while reflecting the now-resolved state.
    - Line 87: contains the broader Solution-Horizon framing sentence: `"The cadence of trigger evaluation is the operator's responsibility (via periodic cortex-backlog list --tag phase2-trigger), not an automated guarantee."` Replace `cortex-backlog list --tag phase2-trigger` with `cortex-backlog-ready --tag phase2-trigger`. Preserve all surrounding prose verbatim — the Solution-Horizon framing about operator responsibility is load-bearing.
  - **Edits to `cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md`** (2 lines amended + 1 line left verbatim + 1 line appended):
    - Line 85: contains `surfaces in cortex-backlog list --tag phase2-trigger queries`. Replace with `surfaces in cortex-backlog-ready --tag phase2-trigger queries`.
    - Line 86: do NOT modify. This line documents the pre-fix CLI state (`cortex-backlog-ready --tag phase2-trigger errors with "unrecognized arguments..."`) and is institutional memory. Verified: this line does NOT contain the substring `cortex-backlog list --tag` (it uses the hyphenated form), so the absence-grep on Verification still passes with line 86 unchanged.
    - Append immediately after line 86 (or wherever the historical "Actual" finding ends): a new line/sentence reading exactly `Resolved by ticket #233 (add-tag-filter-to-backlog-query) on 2026-05-18 — cortex-backlog-ready --tag phase2-trigger now functions.` This is the forward-pointer; the presence-grep verifies it.
    - Line 88: contains `Spec's acceptance grep cortex-backlog list --tag phase2-trigger | grep -c "discovery-output-density" ≥ 1 cannot be satisfied today because the CLI does not implement --tag.` Replace the command-name prefix `cortex-backlog list` with `cortex-backlog-ready`, and replace the trailing clause `cannot be satisfied today because the CLI does not implement --tag` with `was unsatisfiable at review time; ticket #233 landed --tag and the grep now passes.` The two-clause edit reflects the post-fix state without erasing the pre-fix observation.
  - Do NOT modify ticket #232's frontmatter or the originating ticket #233 — explicit non-requirement.
- **Verification**:
  - `grep -c 'cortex-backlog list --tag' cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` = 0 (validates Req 9 absence half).
  - `grep -c 'cortex-backlog-ready --tag phase2-trigger' cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` ≥ 1 (validates Req 9 positive case).
  - `grep -c 'cortex-backlog list --tag' cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md` = 0 (validates Req 10 absence half).
  - `grep -c 'Resolved by ticket #233' cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md` ≥ 1 (validates the forward-pointer; combined with the absence-grep, this distinguishes "preserved with forward-pointer" from "mechanically substituted").
  - `grep -c 'if cortex-backlog does not currently support --tag filtering, file a separate wiring ticket' cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` ≥ 1 (validates the escape-hatch clause on line 44 was NOT swept up in mechanical substitution — preserves the rationale for ticket #233 existing).
- **Status**: [x] done

## Risks

- **Dual-source mirror coverage**: `bin/cortex-backlog-ready` is canonical and `plugins/cortex-core/bin/cortex-backlog-ready` is the auto-mirrored copy enforced by a pre-commit hook. Task 1 does NOT modify the shim (the shim is a pass-through `exec ... "$@"`), so the mirror stays aligned. The pre-commit hook's build-trigger pattern (`^(skills/|bin/cortex-|hooks/cortex-|claude/hooks/cortex-)`) does not include `cortex/backlog/*` or `tests/*`, so `just build-plugin` will not auto-run when only this ticket's files are staged. Mitigation: verify shim contents are byte-identical post-commit; if they ever diverge, run `just build-plugin` manually.
- **Latent dead-shim-branch trap (forward-compat note)**: `bin/cortex-backlog-ready` branch (a) prefers `python3 -m cortex_command.backlog.ready`, which is currently dead (no such module exists). If a future ticket promotes the script into `cortex_command/backlog/ready.py` (the staged endpoint), `--tag` will silently disappear for `uv tool install` users unless that promotion ticket carries the `--tag` argument forward. Out of scope for #233; flag for the eventual promotion ticket via a note in `cortex_command/backlog/readiness.py:5,17` docstrings or as a separate backlog item.
- **Consumer-coverage cross-check**: Downstream consumers `/cortex-core:backlog pick` and `ready` at `skills/backlog/SKILL.md:82,99` (and its mirror at `plugins/cortex-core/skills/backlog/SKILL.md:82,99`) invoke `cortex-backlog-ready` with no args. Their unchanged behavior depends on Task 1's dict-`get` fallback (covered by Task 1 Verification's third gate). No SKILL.md edits are needed — both consumers remain unchanged. The `cortex_command/backlog/readiness.py:5,17` docstrings mention `cortex-backlog-ready` but do not document its arg surface, so no docstring update is required.
- **AND-semantics opinion deviates from in-house `--status` OR precedent**: Documented in the spec as a deliberate one-time deviation matching external convention and ticket text. The risk is purely institutional — if someone later normalizes the codebase on OR semantics, this filter would be the odd one out. Mitigation: spec records the rationale; if revisited later, the change is local to `_parse_args` and the filter predicate.
- **Phase 2 commits a different lifecycle's artifacts**: Task 3 touches `cortex/lifecycle/discovery-output-density-investigate-author-centric/{spec,review}.md`. This is novel — a search of the git history shows no prior ticket has retroactively rewritten a closed lifecycle's APPROVED review. Mitigation: the edits are tightly scoped (command-name swap + forward-pointer append), preserve institutional memory via the verbatim line 86 and the escape-hatch clause on line 44, and are independently verifiable via paired absence/presence greps. If the institutional posture turns out to be "review.md is frozen," the alternative is an addendum file (`cortex/lifecycle/discovery-output-density-investigate-author-centric/addendum-ticket-233.md`) — Phase 2 can be re-routed without re-doing Phase 1.

## Acceptance

After all three tasks complete and merge:
- `cortex-backlog-ready --tag phase2-trigger` exits 0 and returns ticket #232 in its `groups` array (whole-feature end-state).
- `grep -c 'cortex-backlog list --tag' cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md` returns `0` for both files (upstream spec Req 15 grep now references the existing CLI).
- `grep -c 'Resolved by ticket #233' cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md` ≥ 1 (forward-pointer present; combined with the absence-grep, distinguishes context-preserving amendment from mechanical substitution).
- `pytest tests/test_backlog_ready_tag_filter.py tests/test_backlog_ready_render.py -q` exits 0 (new filter is covered, existing snapshot is preserved, and the `all_items_ns` scoping invariant is locked in by `test_blocker_resolution_uses_unfiltered_corpus`).
