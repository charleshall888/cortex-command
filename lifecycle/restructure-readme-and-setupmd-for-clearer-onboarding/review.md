# Review: restructure-readme-and-setupmd-for-clearer-onboarding

## Stage 1: Spec Compliance

### Requirement R1: Remove README cross-platform promise
- **Expected**: `README.md:72`'s "For Linux or Windows setup, see docs/setup.md" line deleted; both `grep -ic 'for linux or windows'` and `grep -ic 'linux/windows\|linux or windows'` return 0.
- **Actual**: Both greps return 0. The line is absent from README.
- **Verdict**: PASS

### Requirement R2: Standardize plugin install syntax in README on `@cortex-command` form
- **Expected**: Every `/plugin install` line uses the scoped form; `grep -c '/plugin install'` equals `grep -c '/plugin install.*@cortex-command'`; Quick Start contains `@cortex-command`.
- **Actual**: Both counts return 4; scoped Quick Start grep returns 5 (`@cortex-command` appears in the 4 install lines plus the extras-tier prose sentence). All `/plugin install` lines use the scoped form.
- **Verdict**: PASS

### Requirement R3: Plugin count consistency in README
- **Expected**: Numeric plugin count in README matches `.claude-plugin/marketplace.json`'s actual count (6); Quick Start either covers all 6 or identifies a recommended subset.
- **Actual**: README line 69 reads "Cortex-command ships six plugins in this repo" — the word form "six" rather than the digit "6". Marketplace count is 6, so the count is accurate. The spec's own AC `grep -c "ships 6 plugins"` returns 0 because the implementation uses the word form; however, the spec text explicitly identified "the phrase 'ships six plugins'" as the current and expected phrase, making the digit-form grep an imprecision in the AC rather than a requirement violation. The second Quick Start AC: 4 install lines are present (not all 6), with a code-comment label "Install the recommended core plugins to start" (satisfying the `recommended` keyword) and a prose sentence linking to the Plugin roster for the remaining 2 plugins. The plan's own verification grep for the keyword returns 1 (match inside the code comment).
- **Verdict**: PASS
- **Notes**: The `grep -c "ships 6 plugins"` literal AC fails because the implementation uses "six" (word form), but the spec text explicitly named "ships six plugins" as the current phrase and the count is accurate. The subset-rationale path in the second AC is satisfied by the code-comment label rather than a standalone prose sentence — the plan's own verification accepted this. The Quick Start prose says "three steps" while the code block enumerates four numbered steps (bootstrap, PATH, marketplace, install); this is a minor prose-code inconsistency not covered by any spec AC and does not constitute a requirement failure.

### Requirement R4: Complete CLI utilities list in README
- **Expected**: Every `bin/cortex-*` executable appears backtick-anchored in README at least once.
- **Actual**: All 9 files (`cortex-archive-rewrite-paths`, `cortex-archive-sample-select`, `cortex-audit-doc`, `cortex-count-tokens`, `cortex-create-backlog-item`, `cortex-generate-backlog-index`, `cortex-git-sync-rebase`, `cortex-jcc`, `cortex-update-item`) appear in backticks in the README's `### What's Inside` table entry. Each returns ≥1 from the backtick-anchored grep.
- **Verdict**: PASS

### Requirement R5: Remove README pipeline ASCII diagram; replace with prose pitch linking to agentic-layer.md
- **Expected**: Box-drawing region removed; `grep -cE '^[ ]*[┌┐└┘├┤┬┴┼─│]{5,}' README.md` returns ≤6; prose pitch above Prerequisites names all four stages and links to `docs/agentic-layer.md`.
- **Actual**: The box-drawing grep returns 2 (two lines in the retained lifecycle phase flow diagram, well under the ≤6 budget). The pre-Prerequisites pitch paragraph names `discovery`, `backlog`, `refine/lifecycle`, and `overnight`, and links to `docs/agentic-layer.md#diagram-a--main-workflow-flow`. All three plan verification clauses pass.
- **Verdict**: PASS

### Requirement R6: Augment Mermaid Diagram A in `docs/agentic-layer.md`
- **Expected**: REQ node added with `informs scope` edge to DISC; BACKLOG label updated with `draft → refined → complete`; interactive/autonomous axis prefixes on at least 2 edges.
- **Actual**: Diagram A extraction returns non-empty. REQ appears 2 times in the Mermaid block (node definition + edge). `draft → refined → complete` appears 1 time. `interactive [·] ` and `autonomous [·] ` patterns match 3 times (both axes present on edges). All plan verification clauses pass.
- **Verdict**: PASS
- **Notes**: Manual GitHub-render check (Mermaid syntax error overlay) deferred to human PR-render verification per plan Verification Doctrine.

### Requirement R7: Replace README authentication section with pointer block
- **Expected**: H3 subheadings `### API Key`, `### OAuth Token`, `### Using Both` removed from README; link to `docs/setup.md#authentication` present; `## Authentication` H2 remains in README; `## Authentication` H2 present in setup.md for anchor resolution.
- **Actual**: `grep -cE '^### (API Key|OAuth Token|Using Both)' README.md` returns 0. `grep -c 'docs/setup.md#authentication' README.md` returns 1. `grep -cE '^## Authentication' README.md` returns 1 (pointer H2 retained). `grep -cE '^## Authentication' docs/setup.md` returns 1. All verification clauses pass.
- **Verdict**: PASS
- **Notes**: Manual GitHub `#authentication` anchor resolution check deferred to human PR-render verification.

### Requirement R8: Reorder `docs/setup.md` H2 sections to prose-walkthrough first
- **Expected**: H2 sections in order: Prerequisites → Install → Authentication → Customization → Per-repo permission scoping → macOS Notifications → Dependencies.
- **Actual**: `grep -nE '^## ' docs/setup.md` returns exactly this order: Prerequisites (11), Install (20), Authentication (195), Customization (248), Per-repo permission scoping (328), macOS Notifications (368), Dependencies (389). No new H2 sections introduced; `### 3. Per-repo setup` remains nested inside `## Install`. The `### Maintaining duplicated surfaces` H3 appears between `## macOS Notifications` and `## Dependencies` as a standalone H3 not nested inside an H2 — this placement was specified in the plan and spec as acceptable.
- **Verdict**: PASS

### Requirement R9: Expand cortex init flow in `docs/setup.md` to document all 7 side effects
- **Expected**: Section ≥30 lines; contains exact phrases `additively registers`, `the only write`, `fcntl.flock`; 7 distinct keywords from `submodule|symlink|settings\.local\.json|\.cortex-init|scaffold|\.gitignore|fcntl\.flock`.
- **Actual**: Per-repo section extracted to 118 lines (well over the ≥30 minimum). `additively registers`, `the only write`, and `fcntl.flock` all appear ≥1 time within the section. Distinct keyword count returns 7.
- **Verdict**: PASS

### Requirement R10: Document `lifecycle.config.md` schema in `docs/setup.md` with all 6 keys
- **Expected**: H4 heading `#### lifecycle.config.md schema` exists; all 6 keys present; `Currently advisory` ≥3 times; `daytime_pipeline.py` cited; `morning-review` cited; `just test` cited.
- **Actual**: Schema subsection is non-empty. Hyphenated key coverage returns 5 (the 5 non-`type` keys). `type` appears ≥1 time as a key reference. `Currently advisory` appears 4 times — 3 times for the 3 advisory keys and once more in the forward-looking note ("updated from `Currently advisory` to describe the consumer"). All 4 occurrences are scoped within the schema subsection. `daytime_pipeline.py` appears 1 time. `morning-review` appears 1 time. `just test` appears 2 times (once as the default value, once in the example YAML comment context).
- **Verdict**: PASS
- **Notes**: The 4th occurrence of `Currently advisory` is inside a blockquote note that explains the update obligation, not a fourth advisory key. The plan's AC requires ≥3, and 3 genuine key entries each have the phrase; the 4th is structural. Pass.

### Requirement R11: Worked first-invocation example in `docs/setup.md`
- **Expected**: Fenced code block with `cortex init`; scaffold directory tree/listing; separate fenced block with `/cortex-interactive:lifecycle <feature>`; adjacent prose distinguishing `cortex init` outputs vs lifecycle outputs.
- **Actual**: `grep -cE '^(\$ )?cortex init( |$)'` in per-repo section returns 2 (the standalone `cortex init` command block plus a subsequent reference). `/cortex-interactive:lifecycle` appears 4 times. Output-distinguishing prose matches `After \`cortex init\` completes` and `Then run`. Scaffold paths at line start: 9 matches (≥4 threshold). All verification clauses pass.
- **Verdict**: PASS

### Requirement R12: Install verification step in `docs/setup.md` under `#### Verify install`
- **Expected**: `#### Verify install` H4 exists inside `## Install`; subsection contains `cortex --print-root`, `claude /plugin list`, `remote_url`, `head_sha`.
- **Actual**: `grep -cE '^#### Verify install'` in the Install section returns 1. The verify-install subsection is non-empty. `cortex --print-root` appears 2 times (in the code block and in the prose description). `claude /plugin list` appears 2 times. `remote_url` and `head_sha` each appear 1 time. All verification clauses pass. The previously-duplicate `#### Verify install` H4 under plugin troubleshooting was correctly renamed to `#### Troubleshooting plugin install` to preserve anchor uniqueness.
- **Verdict**: PASS

### Requirement R13: Standardize plugin install syntax in `docs/setup.md` on `@cortex-command` form
- **Expected**: `grep -c '/plugin install' docs/setup.md` equals `grep -c '/plugin install.*@cortex-command' docs/setup.md`; no bare-form lines.
- **Actual**: Both counts return 4. Bare-form count (without `@cortex-command`) returns 0. No-op as noted — setup.md was already canonical at implementation time.
- **Verdict**: PASS

### Requirement R14: Preserve plugin roster table in both README and `docs/setup.md` with byte-identical content
- **Expected**: Both roster extracts (name, description) match the sorted marketplace source; each extract has ≥6 non-empty lines; `diff` returns no output.
- **Actual**: Python-based extraction produced 6-entry sorted lists from both README (Plugin roster section) and setup.md (Install section). `diff` against the marketplace source returns empty for both. All 6 entries match verbatim: `android-dev-extras`, `cortex-dev-extras`, `cortex-interactive`, `cortex-overnight-integration`, `cortex-pr-review`, `cortex-ui-extras` with identical descriptions.
- **Verdict**: PASS

### Requirement R15: Quick Start documents `/plugin marketplace add` precondition before first `/plugin install`
- **Expected**: `/plugin marketplace add charleshall888/cortex-command` present in Quick Start; marketplace-add line appears before first `/plugin install` line.
- **Actual**: `grep -nE '/plugin marketplace add|/plugin install' README.md | head -1` returns line 52 (`claude /plugin marketplace add charleshall888/cortex-command`). First `/plugin install` is at line 55. Ordering is correct.
- **Verdict**: PASS

### Requirement R16: README Quick Start ends with a one-line verification reference
- **Expected**: Quick Start contains `claude /plugin list` inline or a pointer to `docs/setup.md#verify-install`; detectable via `grep -E "claude /plugin list|setup\.md#verify"` in Quick Start.
- **Actual**: The Quick Start contains "Verify the install with the smoke test in [Setup guide § Verify install](docs/setup.md#verify-install)." Scoped Quick Start grep returns 1. The `#### Verify install` anchor-producing heading exists in setup.md (verified in R12).
- **Verdict**: PASS
- **Notes**: The verification reference appears before the `### Plugin roster` subsection rather than as the final line of the entire Quick Start section (the section ends with a roster link "see `docs/setup.md`"). The spec says Quick Start "ends with" a verification line, but R16's AC is a presence check, not a last-line check. The AC passes. Manual `#verify-install` anchor resolution check deferred to human PR-render verification.

### Edge Case: Dependencies macOS-only annotation
- **Expected**: One-line preamble in Dependencies section containing exact phrase `primarily developed and tested on macOS`.
- **Actual**: "Commands shown use Homebrew (macOS); the project is primarily developed and tested on macOS." appears as the first line of the Dependencies section body. Exact phrase grep within section returns 1.
- **Verdict**: PASS

### Edge Case: Three duplication surfaces note
- **Expected**: `### Maintaining duplicated surfaces` H3 exists in setup.md; section names plugin roster, CLI utilities list, and auth pointer.
- **Actual**: Section exists, is non-empty, and is placed between `## macOS Notifications` and `## Dependencies`. `plugin roster` appears 1 time, `CLI utilities` appears 1 time, `auth pointer` appears 1 time. All three surfaces enumerated.
- **Verdict**: PASS

---

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

The implementation is strictly doc-only. The cortex init side-effect documentation (R9), lifecycle.config.md schema (R10), and `cortex --print-root` output fields (R12) describe existing, empirically-verified behavior — they create no new code contracts beyond what already exists. `requirements/project.md:26` already documents the per-repo sandbox registration behavior that R9 expands on. No new code paths, CLI flags, or behavioral contracts are introduced.

---

## Stage 2: Code Quality

- **Naming conventions**: Heading levels are consistent. H4 headings (`#### lifecycle.config.md schema`, `#### Verify install`, `#### Troubleshooting plugin install`, `#### Worked example: cortex init + first lifecycle invocation`) are correctly nested under the `### 3. Per-repo setup` H3. Backtick usage is consistent throughout — CLI commands, file paths, and key names are all backtick-wrapped. The scoped plugin install form `<name>@cortex-command` is used uniformly across both files.

- **Pattern consistency**: Plugin roster table format is byte-identical between README and setup.md — verified by diff against marketplace source. The `### Maintaining duplicated surfaces` section correctly enumerates all three surfaces. The `#### Verify install` heading placement (end of `## Install`, after the per-repo subsection) is structurally sound. The H2 ordering in setup.md is canonical per R8 and was preserved through all 13 tasks.

- **Anchor / slug correctness**: `docs/setup.md#authentication` — `## Authentication` H2 exists at line 195, slug resolves. `docs/setup.md#verify-install` — `#### Verify install` H4 exists inside `## Install`, slug resolves. The renamed `#### Troubleshooting plugin install` heading removes the prior anchor collision that would have caused `#verify-install` to be ambiguous. All structural checks pass; GitHub render verification for Mermaid (R6), `#authentication` (R7), and `#verify-install` (R16) are deferred to human PR review per plan Verification Doctrine.

- **Completeness**: The maintainer note correctly enumerates exactly the three duplication surfaces the spec mandated (plugin roster, CLI utilities list, auth pointer) and explicitly excludes the doc/code contract surfaces from Tasks 6/7/9 per the plan's Scope Boundaries. The cortex init worked example lists the scaffold output at the correct level of detail without over-specifying. The `lifecycle.config.md` schema section accurately distinguishes 3 active keys (with named consumers) from 3 advisory keys (with the exact phrase `Currently advisory`), and includes a forward-looking note for the advisory-key promotion obligation. Minor prose-code inconsistency: the Quick Start prose says "Installation has three steps" while the code block contains four numbered steps (bootstrap, PATH update, marketplace add, plugin install). This is not covered by any spec AC and does not affect functional correctness.

---

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
