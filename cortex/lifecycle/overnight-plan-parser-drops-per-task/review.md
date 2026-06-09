# Review: overnight-plan-parser-drops-per-task

## Stage 1: Spec Compliance

### Requirement R1: Normalize the bullet/colon dialect family (recover value-bearing variants)
- **Expected**: All four per-task field parsers (`_parse_field_files`, `_parse_field_depends_on`, `_parse_field_string` for Complexity, and `_parse_field_status` for Status) accept an optional leading bullet and the colon inside *or* outside the bold. Canonical form parses unchanged; `_parse_field_files`'s `re.DOTALL` multi-line capability preserved. New tests feed the no-bullet, bulleted-colon-inside, and no-bullet-colon-inside forms and assert the same parsed values.
- **Actual**: A shared `_field_match_shape(label)` helper (`parser.py:376-391`) builds the relaxed regex — `(?:[-*]\s+)?` optional bullet + colon-inside (`\*\*\s*Label\s*:\s*\*\*`) OR colon-outside (`\*\*\s*Label\s*\*\*\s*:`) — and is used by all four field parsers plus the label detector. `_parse_field_files` (`:418-422`) keeps the `re.DOTALL` terminator-lookahead capture `(?=\n(?:[-*]\s+)?\*\*|\n###|\n##|\Z)`. `TestR1DialectEquivalence` asserts canonical, no-bullet, bulleted-colon-inside, and no-bullet-colon-inside all yield `files == ["src/a.py","src/b.py"]` / `depends_on == [1,2]`. `TestR1MultiLineFiles` asserts the nested-path-bullet dialect parses to its path list with no raise. `TestR1StatusDialect` asserts recovered-dialect `Status` lines resolve to `done`. Targeted suite (47 tests) green.
- **Verdict**: PASS
- **Notes**: Status (`_parse_field_status`) and Complexity (`_parse_field_string`) were relaxed to the same dialect shape but correctly NOT made fail-loud — a missing Status defaults to `pending`, a missing/OOV Complexity defaults/coerces. Faithful to the plan's Task 1 Context note.

### Requirement R2: Fail-loud invariant — label present but no usable value → raise
- **Expected**: A `Files`/`Depends on` label present (bold token immediately colon-adjacent, at top-level non-nested task-body indentation) but yielding no usable value raises `ValueError`. Empty/whitespace value raises for *both* fields symmetrically. Raise propagates through `parse_feature_plan` to `feature_executor.py:567-574` → `status="failed", parse_error=True`.
- **Actual**: `_field_label_present` (`:394-406`) anchors the relaxed shape with `^` under `re.MULTILINE`, allowing only an optional `[-*]\s+` bullet prefix and NOT arbitrary leading indentation — the load-bearing line-leading anchor. `_parse_field_files` raises (`:425-431`) when the captured-and-stripped value is empty AND the label is present (symmetric empty-value path). `_parse_field_depends_on` raises on both no-match-but-label-present (`:489-495`) and empty value (`:499-503`). I verified empirically: a 2-space-indented `  - **Depends on**: see Task 1` Context sub-bullet returns `label_present == False`; a colon-free prose mention (`- **Files** are frozen`) returns `False`; top-level `- **Files**:` and no-bullet `**Files**:` return `True`. `TestR2FailLoud` asserts both empty-Files and empty-Depends-on raise. Crucially, the value-extraction regexes in `_parse_field_files` and `_parse_field_depends_on` use the SAME `^`-anchored shape, so a nested `  - **Depends on**: [2]` is not scraped either (returns `[]`, no phantom).
- **Verdict**: PASS
- **Notes**: The instructions flagged that the anchor must exclude nested ≥2-space Context sub-bullets and colon-free prose mentions, not merely key on colon-adjacency. Verified directly — the `^`-with-no-`\s*`-prefix anchoring rejects indented lines at both the label-detector and value-extraction sites. This is the discriminator the spec's "line-leading" framing required.

### Requirement R3: Legitimately-absent dependencies and prose-free values must NOT raise (no false positives)
- **Expected**: `- **Depends on**: none`, no-bullet `**Depends on**: none`, a task with no Depends-on label, and a multi-task all-`none` plan all parse to `[]`/their value with no raise. A prose mention of the bold token without an adjacent colon (nested Context bullet) must NOT trigger R2.
- **Actual**: `TestR3NonTriggers` covers `none` (no raise → `[]`), no-label-at-all, the nested colon-free `  - **Files** are frozen`, the nested colon-adjacent `  - **Depends on**: see Task 1` sub-bullet (top-level `none` wins, nested does not corrupt or trigger), the colon-inside prose span `- **Files: frozen** below` (does not match the colon-inside shape because text sits between colon and closing `**`), and a multi-task all-`none` plan. All assert no exception. Verified independently that a nested-only colon-adjacent sub-bullet with a bracketed digit (`  - **Depends on**: [2]`) still returns `[]`.
- **Verdict**: PASS

### Requirement R4: Depends-on value must be list-conformant (no phantom dependencies)
- **Expected**: Extract task numbers only from a list-conformant value (`[N]`, `[N, M]`, `N`, `N, M`, `none`). Free prose with an incidental digit (`after Phase 1 is green`) raises rather than scraping the digit. The phantom-dependency case `none (parallel-eligible with Task 1)` must resolve to `[]`, not `[1]`.
- **Actual**: `_DEPENDS_ON_LIST_CONFORMANT` (`:459-462`) anchors a full-string match of `none` or a comma-separated sequence of bracketed/bare task ids. `_parse_field_depends_on` (`:505-516`) strips parenthetical `(...)` spans and a trailing em/en-dash note, then requires the stripped remainder to be list-conformant before extracting integers. I verified: `after Phase 1 is green` → RAISE; `none (parallel-eligible with Task 1)` → `[]` (the phantom `[1]` bug is fixed); `[1] (note), [4] (note)` → `[1,4]`; `Task 1 and Task 2`, `1, 2, and 3`, `[1] then [2]`, `[1]; [2]`, `[1, 2` (unbalanced) all RAISE. `TestR4DependsOnListConformance` asserts the prose-raise and the tolerated forms.
- **Verdict**: PASS

### Corpus-driven dialect expansion (letter-suffix `[2a]`, trailing em-dash annotation) — soundness vs over-broadening
- **Expected** (per review instructions): assess whether the expansion beyond the spec's enumerated forms recovers known-safe dialects and raises only on unrecoverable drift, without introducing a false-negative (a genuinely-malformed value that now silently parses).
- **Actual**: The letter-suffix is `\d+[a-z]?` — a digit run plus at most one optional letter (case-insensitive). I stress-tested it: `3A`/`[3z]` → `[3]` (the integer; the suffix collapses, matching the pre-existing digit-scrape integer and documented at `:521-525`); multi-char garbage (`1abc`, `3a4`, `Phase1`, `[1.5]`) all RAISE. The trailing-annotation regex `_DEPENDS_ON_TRAILING_ANNOTATION` (`:468`) requires a spaced em/en-dash or spaced `--` followed by a space — deliberately NOT a single hyphen (which appears in ordinary hyphenated prose), so it cannot accidentally truncate a hyphenated value. The 106-plan live-corpus audit (Task 1's mandated verification) runs clean with no offender. Two accepted residual cases surfaced — a real dependency *inside* a parenthetical (`[1] (covers [2])` → `[1]`) and a dep hidden in a trailing note after `none` (`none — but actually [3]` → `[]`) — but both are exotic, non-canonical inputs the spec's accepted forms (deps before annotations) exclude, and the plan's Risks section names this exact residual explicitly. No false-negative against the spec's intent: any value that is not a canonical/corpus list form still raises.
- **Verdict**: PASS — sound and faithful. The expansion recovers exactly the two live-corpus dialects the audit surfaced (each tightly bounded) and does not broaden the raise-escape surface for malformed prose.

### Requirement R5: Raise-routing is verified — parser ValueError → parse_error=True
- **Expected**: A test asserts a parser `ValueError` is mapped by the feature-execution path to `FeatureResult(status="failed", parse_error=True)`, exercising `feature_executor.py:566-574`. The raise must route through `parse_feature_plan`, NOT through `compute_dependency_batches`.
- **Actual**: `test_parse_feature_plan_valueerror_returns_failed_parse_error` (`test_lead_unit.py:1222-1253`) patches `parse_feature_plan` with `side_effect=ValueError` and asserts `result.status == "failed"` AND `result.parse_error is True`. I confirmed in `feature_executor.py` that `parse_feature_plan` is called at `:567` inside a `try` whose `except (FileNotFoundError, ValueError)` (`:568`) sets `parse_error=True` (`:573`); the separate `compute_dependency_batches` call at `:596-602` has its own `except ValueError` returning `failed` WITHOUT `parse_error` (the cycle path, correctly not exempt). Routing is exactly as the spec's Technical Constraints require. Test passes.
- **Verdict**: PASS

### Requirement R6: Direct tests for compute_dependency_batches
- **Expected**: First direct tests — topological batching for a chain, the all-empty-`depends_on` collapse, and cycle-detection raises.
- **Actual**: `TestComputeDependencyBatches` (`test_common.py:128-171`) covers `[1]→[2]→[3]` → `[[1],[2],[3]]`, three all-empty tasks → one batch `[1,2,3]` (with a docstring noting this is now unreachable for label-present plans), and a mutual `1↔2` cycle → `assertRaises(ValueError)`. All pass.
- **Verdict**: PASS

### Requirement R7: Pin the plan format in the overnight generator prompt
- **Expected**: `orchestrator-round.md` §3b shows the literal canonical field syntax and cites `skills/lifecycle/references/plan.md`. `grep -c -- '- \*\*Depends on\*\*:' ≥ 1` AND references `references/plan.md`.
- **Actual**: The bare paraphrase was replaced (`:411-425`) with the literal seven-field block (leading bullet, colon outside bold) plus a "Do not paraphrase... move the colon inside the bold span" instruction and a `skills/lifecycle/references/plan.md` citation. Greps: `- **Depends on**:` count = 1; `references/plan.md` count = 3. The `{{feature_*}}` double-brace substitution contract is preserved; the introduced `{exact paths...}` single-brace tokens are inert — `fill_prompt()` (`fill_prompt.py:35-40`) does six targeted `.replace()` calls for named session tokens only and uses no generic `.format()`, so the descriptive placeholders pass through verbatim to the sub-agent (intended generator-prompt prose).
- **Verdict**: PASS

### Requirement R8: Document intra-feature ordering in pipeline requirements
- **Expected**: A statement in `pipeline.md` (Feature Execution and Failure Handling) naming `compute_dependency_batches` and the fail-loud-on-unparseable posture. `grep -c 'compute_dependency_batches' ≥ 1`.
- **Actual**: A new acceptance-criteria bullet was added to the section (`pipeline.md`, after the fail-forward-model bullet) stating ordering is derived via `compute_dependency_batches` from per-task `Depends on` metadata and that unparseable ordering metadata fails the feature loudly (`parse_error`) rather than degrading silently, with the fail-forward-vs-mis-dispatch reconciliation. Grep count = 1. Style consistent with surrounding bullets.
- **Verdict**: PASS

### Requirement R9: Minimal field-name guard against template/parser rename drift
- **Expected**: One focused test asserting the parser extracts the ordering-critical `Files`/`Depends on` fields the canonical template declares, so a rename surfaces as a failing assertion rather than a silent drop. Scope: ordering-critical names only, not a full parity harness.
- **Actual**: `TestR9FieldNameRenameDriftGuard.test_ordering_critical_field_labels_extract_non_empty` (`test_parser.py:849-882`) renders a minimal task with literal `Files`/`Depends on` labels and asserts `files == ["a.py"]` and `depends_on == [1]` (both non-empty). The docstring explains why R2 cannot catch a rename (it keys on the literal tokens). Scope is exactly the two ordering-critical names — the full SKILL↔parser parity harness remains an explicit Non-Requirement.
- **Verdict**: PASS

### Acceptance (plan-level)
- **Expected**: The full acceptance narrative — dialect-family plans parse equivalently, label-present-no-value raises and maps to `parse_error`, legitimately-absent deps parse to `[]` with no phantom, every active plan parses with no unexpected raise, `just test` exits 0 (modulo the known sandbox-network failure).
- **Actual**: All four parser behavior classes verified by tests and direct probing. Live-corpus audit clean across 106 plans. The spec's named drift example (`scale-research-fanout-by-complexity/plan.md`) now recovers its full dependency graph (Tasks 2-11 carry real `depends_on` values; previously all `[]`). Targeted suites (parser 47, batches 3, routing 1) all green.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent with the existing parser. The new `_field_match_shape` / `_field_label_present` private helpers follow the `_parse_field_*` private-function convention; module-level `_DEPENDS_ON_*` regex constants use the established uppercase-with-leading-underscore style (matching `VALID_COMPLEXITIES`). Test classes follow the `TestR<N><Behavior>` and `_PlanParseMixin` patterns already in the file.
- **Error handling**: Appropriate and central to the feature. `ValueError` is raised with feature/task/path context in the message, surfaced through `parse_feature_plan` to the single `except (FileNotFoundError, ValueError)` boundary, and correctly kept distinct from the `compute_dependency_batches` cycle path so the circuit-breaker-exempt `parse_error` flag is set only for parse failures. The fail-loud posture is symmetric across Files and Depends-on as the spec requires.
- **Test coverage**: Strong and non-vacuous. R1 equivalence asserts concrete parsed values (`["src/a.py","src/b.py"]`, `[1,2]`) rather than mere non-raise; R2/R4 raise-cases use `assertRaises`; R3 non-triggers assert the actual `[]`/path-list outcome. The R3 suite genuinely exercises the line-leading anchor (nested colon-adjacent sub-bullet, colon-inside prose span) — not just colon-adjacency. The plan's two verification gates were both honored: the targeted suites pass, and the mandated live-corpus audit runs clean over 106 plans (I re-ran it). R5 pins the consumer half of the routing; Task 1's `assertRaises(ValueError)` pins the producer half.
- **Pattern consistency**: Follows project conventions — stdlib-only parser (no logging, per the module docstring; recovery is silent, only unrecoverable drift raises), shared regex-shape helper to keep the four parsers DRY, doc change matched to the conditionally-loaded `pipeline.md` requirements area, and the generator-prompt edit preserved the documented double-brace substitution contract. The corpus-tolerance additions are documented inline with rationale and cross-referenced to the spec's accepted-forms boundary.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
