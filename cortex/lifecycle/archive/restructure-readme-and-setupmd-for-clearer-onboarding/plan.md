# Plan: restructure-readme-and-setupmd-for-clearer-onboarding

## Overview

Doc-only restructure across `README.md`, `docs/setup.md`, and `docs/agentic-layer.md`. Tasks decompose by file and section so each touches a bounded region: a 4-task README chain (pipeline pitch → Quick Start → cleanup → utilities), a 6-task setup.md chain (cortex init expansion → schema → worked example → verify → canonicalization → Dependencies note), an independent agentic-layer.md Mermaid augment, then two cross-file tasks (plugin roster byte-identical sync, maintainer note). H2 reorder (spec R8) is a no-op — current `docs/setup.md` H2 ordering already matches the spec target — so it folds into the Verification Strategy rather than its own task.

## Verification Doctrine

Two notes that apply to every task's Verification field below; do not duplicate per-task.

1. **AND aggregation.** All verification clauses chained by "AND" must pass for the task to pass; any single failure fails the task. The harness must run every clause — short-circuit behavior is not acceptable.

2. **Manual GitHub-render checks.** Spec ACs R6 (Mermaid render), R7 (`#authentication` anchor resolution), R16 (`#verify-install` anchor resolution) require human-side GitHub rendering and cannot be automated. For interactive lifecycle execution, the implementer performs these checks before marking the relevant task complete (commit, view on github.com, confirm). For overnight pipeline execution, these checks defer to human PR review — the pipeline cannot block on them. The structural greps in this plan catch the most likely defect modes; manual checks complement, not substitute.

3. **Line-number staleness.** Context fields below cite line numbers captured at plan time. Tasks 1-4 (README chain) and Tasks 6-11 (setup.md chain) edit the same file in serial; once the first edit lands, downstream line numbers in that file have drifted. Locate sections by **heading text or stable string** (e.g., `## Authentication`, `### 3. Per-repo setup`) rather than line number after any same-file task lands. Line numbers are reference, not contract.

## Tasks

### Task 1: Replace README pipeline ASCII diagram with prose pitch + agentic-layer link
- **Files**: `README.md`
- **What**: Removes the box-art requirements→discovery→backlog→lifecycle pipeline diagram (currently `README.md:9-43`) and replaces it with a 2-3 sentence prose pitch above the `## Prerequisites` H2. The prose names discovery, backlog, refine/lifecycle, and overnight, and links to `docs/agentic-layer.md` for the visual.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing diagram region: `README.md:9-43` (35 lines of box-drawing ASCII). Lifecycle phase flow diagram at `README.md:45-63` is preserved. The pitch lives between the README's top-of-file content and `## Prerequisites`. The pitch must mention all four pipeline stages (`discovery`, `backlog`, `refine`/`lifecycle`, `overnight`) so the prose carries the same conceptual surface as the deleted diagram. Link target uses the form `[docs/agentic-layer.md](docs/agentic-layer.md#diagram-a--main-workflow-flow)` or `docs/agentic-layer.md` (anchor optional but preferred). Spec requirements covered: R5.
- **Verification**: `grep -cE '^[ ]*[┌┐└┘├┤┬┴┼─│]{5,}' README.md` returns ≤ 6 — pass if count ≤ 6 (allows the lifecycle phase flow diagram at L45-63 to remain while flagging any reintroduction of a 35-line ASCII pipeline diagram); AND scoped to the pre-Prerequisites pitch region: `awk '/^## Prerequisites/{exit} {print}' README.md | grep -cE 'discovery.*backlog.*(refine|lifecycle).*overnight|discovery.*backlog.*overnight'` returns ≥ 1 — pass if pitch prose contains the four-stage narrative; AND `awk '/^## Prerequisites/{exit} {print}' README.md | grep -c 'docs/agentic-layer.md'` returns ≥ 1 — pass if pitch links to agentic-layer.md (scoped to pitch region so existing doc-index links elsewhere don't satisfy this).
- **Status**: [x] complete

### Task 2: Overhaul README Quick Start (marketplace-add precondition, scoped install form, plugin count consistency, verification reference)
- **Files**: `README.md`
- **What**: Restructures the Quick Start section so that (a) `/plugin marketplace add charleshall888/cortex-command` appears before the first `/plugin install` line; (b) every `/plugin install` example uses the scoped `<name>@cortex-command` form; (c) the install command list either covers all 6 plugins listed in the roster OR identifies a recommended subset using one of the keywords `core`, `recommended`, `start with`, `start here`, or `essentials`; (d) the Quick Start ends with a one-line verification reference linking to `docs/setup.md#verify-install` (preferred — avoids duplicating R12 content) OR using the inline command `claude /plugin list`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Current Quick Start: `README.md:86-91` at plan time (4 install commands in bare form). Locate by `## Quick Start` H2 after Task 1 lands. Marketplace exists at `charleshall888/cortex-command` per `docs/setup.md:37`. Plugin roster (6 entries) at `README.md:97-106` at plan time; locate by `### Plugin roster` heading after Task 1. Marketplace plugins (verified): `android-dev-extras`, `cortex-dev-extras`, `cortex-interactive`, `cortex-overnight-integration`, `cortex-pr-review`, `cortex-ui-extras`. If using "recommended subset" form, it should still mention all 6 plugins exist (link to roster). If using the link form for verification reference, the link target must be `docs/setup.md#verify-install` exactly (matching the heading slug Task 9 produces — see R16 anchor-existence AC). Spec requirements covered: R2, R3 (Quick Start AC), R15, R16.
- **Verification**: `grep -c '/plugin install' README.md` equals `grep -c '/plugin install.*@cortex-command' README.md` — pass if equal (every install line scoped); AND `grep -nE '/plugin marketplace add|/plugin install' README.md | head -1` returns a `/plugin marketplace add` line — pass if first match is the marketplace-add line; AND scoped to Quick Start region (between `## Quick Start` and the next `## ` heading), `awk '/^## Quick Start/{flag=1; next} /^## /{flag=0} flag' README.md | grep -E 'claude /plugin list|setup\.md#verify-install'` returns ≥ 1 — pass if Quick Start contains the verification reference (note: matches `verify-install` exactly, not the loose `setup.md#verify` substring).
- **Status**: [x] complete

### Task 3: Remove README cross-platform line and replace Authentication section with pointer block
- **Files**: `README.md`
- **What**: Deletes the "For Linux or Windows setup, see docs/setup.md" line entirely (currently `README.md:72`). Replaces the full Authentication section (currently `README.md:110-140`, including `### API Key`, `### OAuth Token`, `### Using Both` H3 subheadings) with a 2-3 line callout under a `## Authentication` H2 linking to `docs/setup.md#authentication`.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Cross-platform pointer line is at `README.md:72` at plan time; locate by the literal string "For Linux or Windows setup". Authentication section spans `README.md:110-140` at plan time; locate by `## Authentication` H2 after Tasks 1-2 land. The replacement pointer block preserves the `## Authentication` H2 (so the heading still appears in the README ToC if any) but contains only a 2-3 line note like: "Authentication setup (API key vs. OAuth token) is documented in [Setup guide § Authentication](docs/setup.md#authentication)." Spec requirements covered: R1, R7.
- **Verification**: `grep -ic 'for linux or windows' README.md` returns 0 — pass; AND `grep -ic 'linux/windows\|linux or windows' README.md` returns 0 — pass; AND `grep -cE '^### (API Key|OAuth Token|Using Both)' README.md` returns 0 — pass (H3 subheadings of original auth section gone); AND `grep -c 'docs/setup.md#authentication' README.md` returns ≥ 1 — pass; AND `grep -cE '^## Authentication' README.md` returns 1 — pass (single Authentication H2 remains).
- **Status**: [x] complete

### Task 4: Complete README CLI utilities list (cover all 9 bin/cortex-* executables with backtick-anchored names)
- **Files**: `README.md`
- **What**: Updates the utilities list (currently around `README.md:152` at plan time, listing 7 utilities) to enumerate all 9 `bin/cortex-*` executables, each wrapped in backticks. Adds the 2 currently-undocumented utilities: `cortex-archive-rewrite-paths`, `cortex-archive-sample-select`. Prefers compact list/table format over per-utility prose so future additions are mechanical.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Locate the utilities list by content (existing backticked utility names like `` `cortex-jcc` `` or section heading) rather than line number — Tasks 1-3 have shifted line positions by ~60 lines net. Verified `bin/cortex-*` filenames (9 total): `cortex-archive-rewrite-paths`, `cortex-archive-sample-select`, `cortex-audit-doc`, `cortex-count-tokens`, `cortex-create-backlog-item`, `cortex-generate-backlog-index`, `cortex-git-sync-rebase`, `cortex-jcc`, `cortex-update-item`. Spec R4 AC requires backtick-anchoring (`` `<filename>` ``) — substring match without backticks creates false positives between filenames sharing root tokens. Spec requirements covered: R4.
- **Verification**: `for f in $(ls bin/cortex-* | xargs -n1 basename); do c=$(grep -c "\`$f\`" README.md); [ $c -ge 1 ] || echo "MISSING: $f"; done` produces no output — pass if all 9 names appear in backticks at least once (any "MISSING:" output is a fail signal).
- **Status**: [x] complete

### Task 5: Augment Diagram A in docs/agentic-layer.md (REQ input node, BACKLOG state machine label, interactive/autonomous edge axes)
- **Files**: `docs/agentic-layer.md`
- **What**: Edits the Mermaid block under `### Diagram A — Main Workflow Flow` to add three augmentations: (1) a `REQ([requirements/project.md])` node with edge `REQ -->|"informs scope"| DISC`; (2) change the BACKLOG node label from `BACKLOG[("Backlog")]` to `BACKLOG[("Backlog<br/>draft → refined → complete")]`; (3) update existing BACKLOG → REFINE and BACKLOG → LC edges (or BACKLOG → DEV → LC) to carry `interactive · ` and `autonomous · ` axis prefixes on their existing operational labels (e.g., replace `"pick item"` with `"autonomous · pick item"`, replace `"single feature"` with `"interactive · single feature"`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Diagram A heading: `docs/agentic-layer.md:70` at plan time. Mermaid uses `<br/>` as a literal HTML break inside `[("...")]` cylinder labels and renders correctly on current GitHub Mermaid. The dot-separator (`·`, U+00B7) is the chosen encoding for axis prefixes; future contributors editing Diagram A must preserve this format. **Mermaid pre-flight (mandatory before marking complete):** after editing, the implementer commits the change to a branch, pushes to GitHub, and views the rendered file in github.com to confirm Diagram A renders without "Syntax error" overlay. If GitHub rejects `<br/>` in the cylinder label or `·` in edge labels, revise (e.g., use `\n` or drop the state-machine inline annotation) before marking the task complete. This pre-flight is required for interactive runs; for overnight runs it defers to PR review per the Verification Doctrine. Spec requirements covered: R6.
- **Verification**: Extract Diagram A's mermaid fence to a tempfile, then grep within: `awk '/^### Diagram A/{flag=1; next} /^### |^## /{if(flag>=1)flag=0} /^\`\`\`mermaid/{if(flag==1){flag=2; next}} /^\`\`\`/{if(flag==2)flag=3} flag==2' docs/agentic-layer.md > /tmp/diagram-a-mermaid.txt`. Then: `grep -c 'REQ' /tmp/diagram-a-mermaid.txt` returns ≥ 1 — pass if REQ node appears inside Diagram A's mermaid block (scoped, not whole-file); AND `grep -c 'draft → refined → complete' /tmp/diagram-a-mermaid.txt` returns ≥ 1 — pass; AND `grep -cE 'interactive [·•] |autonomous [·•] ' /tmp/diagram-a-mermaid.txt` returns ≥ 2 — pass (both axis labels in Diagram A's edges, not in Diagram B or prose); AND `[ -s /tmp/diagram-a-mermaid.txt ]` — pass (extracted file is non-empty; guards against awk extraction returning empty when the heading or fence pattern shifts).
- **Status**: [x] complete (manual github.com Mermaid render check deferred to PR review)

### Task 6: Expand cortex init flow in docs/setup.md to document all 7 side effects
- **Files**: `docs/setup.md`
- **What**: Expands the per-repo flow section (currently `docs/setup.md:72-78` at plan time, 6 lines, nested as `### 3. Per-repo setup` inside `## Install`) to ≥30 lines, naming each of cortex init's 7 side effects in order: (1) git repo root resolution / submodule refusal, (2) symlink-safety gate, (3) `~/.claude/settings.local.json` validation, (4) `.cortex-init` marker check, (5) scaffold dispatch (lifecycle/, backlog/, retros/, requirements/, marker file), (6) idempotent `.gitignore` append, (7) sandbox registration into `~/.claude/settings.local.json:sandbox.filesystem.allowWrite` with `fcntl.flock` serialization. The sandbox-registration paragraph contains the exact phrases `additively registers`, `the only write`, and `fcntl.flock`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current cortex init description: `docs/setup.md:72-78` at plan time (6 lines); locate by `### 3. Per-repo setup` heading. Authoritative source for side effects: `cortex_command/init/handler.py:44-223`. Constraint: do NOT cross-link or reference volatile line numbers in `requirements/project.md`. The R9 AC matches phrases by content (`additively registers`, `the only write`, `fcntl.flock`) so unrelated edits to `project.md` cannot drift the AC. Per-repo stays nested under `## Install` as an H3 — do not promote to a new H2. Spec requirements covered: R9.
- **Verification**: Extract the per-repo section: `awk '/^### 3\. Per-repo setup/{flag=1; next} /^### |^## /{flag=0} flag' docs/setup.md > /tmp/per-repo.txt`. Then: `wc -l < /tmp/per-repo.txt` returns ≥ 30 — pass; AND `[ -s /tmp/per-repo.txt ]` — pass (extracted non-empty); AND within section: `grep -c 'additively registers' /tmp/per-repo.txt` returns ≥ 1; AND `grep -c 'the only write' /tmp/per-repo.txt` returns ≥ 1; AND `grep -c 'fcntl.flock' /tmp/per-repo.txt` returns ≥ 1; AND distinct side-effect keyword coverage (counts unique alternation branches matched, not matching lines): `grep -oE 'submodule|symlink|settings\.local\.json|\.cortex-init|scaffold|\.gitignore|fcntl\.flock' /tmp/per-repo.txt | sort -u | wc -l` returns 7 — pass if all 7 distinct keywords appear within the per-repo section (this replaces the broken `grep -cE ... ≥ 7` formulation; `grep -oE | sort -u | wc -l` correctly counts distinct branches).
- **Status**: [x] complete

### Task 7: Document lifecycle.config.md schema in docs/setup.md (all 6 keys with active/advisory distinction)
- **Files**: `docs/setup.md`
- **What**: Adds a schema reference under a new H4 heading `#### lifecycle.config.md schema` (within `### 3. Per-repo setup`, immediately after the cortex init flow expansion from Task 6). The reference names all 6 keys: `type`, `test-command`, `skip-specify`, `skip-review`, `commit-artifacts`, `demo-commands`. For each active key, names the consumer: `test-command` consumed by `cortex_command/overnight/daytime_pipeline.py` (defaults to `just test`); `commit-artifacts` consumed by `skills/lifecycle/references/{complete,research,plan,specify}.md` (`commit-artifacts: false` excludes lifecycle artifacts from staging); `demo-commands` consumed by `skills/morning-review/SKILL.md` and `skills/morning-review/references/walkthrough.md` (accepts list of `{label, command}` entries; takes precedence over legacy `demo-command:` single-string form). For each of `type`, `skip-specify`, `skip-review`, the reference contains the exact phrase `Currently advisory` (capitalized).
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Scaffold template: `cortex_command/init/templates/lifecycle.config.md`. Empirically-verified consumers documented in spec.md "Technical Constraints". The phrase `Currently advisory` must appear exactly (capitalized) for each of the 3 advisory keys — no "or equivalent" substitution. The new H4 heading anchors the verification scope. Spec requirements covered: R10.
- **Verification**: Extract the schema reference subsection: `awk '/^#### lifecycle\.config\.md schema/{flag=1; next} /^#### |^### |^## /{flag=0} flag' docs/setup.md > /tmp/schema-ref.txt`. Then: `[ -s /tmp/schema-ref.txt ]` — pass (extracted non-empty; confirms the H4 heading exists); AND distinct-key coverage: `grep -oE 'test-command|skip-specify|skip-review|commit-artifacts|demo-commands' /tmp/schema-ref.txt | sort -u | wc -l` returns 5 — pass (5 of 6 keys with hyphens; `type` excluded from this check because it's a common English noun — handled separately below); AND `grep -cE '\btype\b' /tmp/schema-ref.txt` returns ≥ 1 — pass (`type` appears in section as a key reference); AND `grep -c 'Currently advisory' /tmp/schema-ref.txt` returns ≥ 3 — pass (3 advisory keys); AND `grep -c 'daytime_pipeline.py' /tmp/schema-ref.txt` returns ≥ 1 — pass (test-command consumer cited); AND `grep -c 'morning-review' /tmp/schema-ref.txt` returns ≥ 1 — pass (demo-commands consumer cited); AND `grep -c 'just test' /tmp/schema-ref.txt` returns ≥ 1 — pass (test-command default cited).
- **Status**: [x] complete

### Task 8: Add worked first-invocation example to docs/setup.md (cortex init + first /cortex-interactive:lifecycle invocation)
- **Files**: `docs/setup.md`
- **What**: Adds a worked example (within or immediately after `### 3. Per-repo setup`) demonstrating: (a) a fenced code block showing the literal command `cortex init`; (b) a directory tree or file listing of what `cortex init` creates (`lifecycle/`, `backlog/`, `retros/`, `requirements/`, `.cortex-init`); (c) a separate fenced code block showing `/cortex-interactive:lifecycle <feature>` being invoked (placeholder feature name like `<feature>` or `my-feature`); (d) adjacent prose distinguishing outputs from `cortex init` vs. outputs from the lifecycle invocation (e.g., "After `cortex init` completes…" / "Then run `/cortex-interactive:lifecycle <feature>` to begin a new feature, which produces …").
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Scaffold list authoritative source: `cortex_command/init/scaffold.py`. The example doubles as end-to-end verification per OE-5. Implementer must run `cortex init` on a clean checkout (a temp directory) to confirm the actual scaffold output before pinning specifics in docs — do NOT trust scaffold.py source alone if there's a discrepancy. The example accepts a leading `$ ` shell-prompt prefix in fenced blocks if the implementer prefers that style (the verification grep tolerates it). Spec requirements covered: R11.
- **Verification**: Extract the per-repo section (which contains the worked example): `awk '/^### 3\. Per-repo setup/{flag=1; next} /^### |^## /{flag=0} flag' docs/setup.md > /tmp/per-repo.txt`. Then: `grep -cE '^(\$ )?cortex init( |$)' /tmp/per-repo.txt` returns ≥ 1 — pass (literal command line `cortex init` or `$ cortex init`, optionally followed by args, appears within the section); AND `grep -c '/cortex-interactive:lifecycle' /tmp/per-repo.txt` returns ≥ 1 — pass (lifecycle invocation appears within section); AND `grep -cE 'After [\`]?cortex init[\`]?|Then run' /tmp/per-repo.txt` returns ≥ 1 — pass (output-distinguishing prose within section); AND `grep -cE '^(lifecycle/|backlog/|retros/|requirements/|\.cortex-init)' /tmp/per-repo.txt` returns ≥ 4 — pass (≥ 4 of 5 scaffold paths appear at line-start, indicating tree-listing format).
- **Status**: [x] complete

### Task 9: Add install verification step to docs/setup.md (cortex --print-root + claude /plugin list, under #### Verify install heading)
- **Files**: `docs/setup.md`
- **What**: Adds a smoke-test verification step at the end of the `## Install` section under a new H4 heading `#### Verify install` (the heading text generates the GitHub anchor slug `verify-install`, which Task 2's R16 link target depends on). The verification is a fenced code block containing both `cortex --print-root` and `claude /plugin list` (in either order). Adjacent prose describes expected output — at minimum: `cortex --print-root` prints JSON with `version`, `root`, `remote_url`, and `head_sha` fields; `claude /plugin list` lists the installed plugins from the `cortex-command` marketplace. Implementer must run `cortex --print-root` locally and confirm the output keys match before pinning the description.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: Spec uses `cortex --print-root` (NOT `cortex --version`) because `cortex --version` is not implemented (verified empirically: returns "unrecognized arguments"). Place the H4 heading at the end of `## Install`, after `### 3. Per-repo setup` and its subsections. The `#### Verify install` heading is the anchor target for Task 2's R16 link (`docs/setup.md#verify-install`). GitHub slugifies `Verify install` → `verify-install`. Spec requirements covered: R12.
- **Verification**: Extract the Install section: `awk '/^## Install/{flag=1; next} /^## /{flag=0} flag' docs/setup.md > /tmp/install.txt`. Then: `[ -s /tmp/install.txt ]` — pass; AND `grep -cE '^#### Verify install' /tmp/install.txt` returns 1 — pass (anchor-producing H4 heading exists; this gates R16); AND extract the verify-install subsection: `awk '/^#### Verify install/{flag=1; next} /^#### |^### |^## /{flag=0} flag' docs/setup.md > /tmp/verify-install.txt`; AND `[ -s /tmp/verify-install.txt ]` — pass; AND `grep -c 'cortex --print-root' /tmp/verify-install.txt` returns ≥ 1 — pass (within verify-install subsection); AND `grep -c 'claude /plugin list' /tmp/verify-install.txt` returns ≥ 1 — pass; AND `grep -c 'remote_url' /tmp/verify-install.txt` returns ≥ 1 — pass; AND `grep -c 'head_sha' /tmp/verify-install.txt` returns ≥ 1 — pass.
- **Status**: [x] complete (also renamed prior duplicate `#### Verify install` heading under §2 to `#### Troubleshooting plugin install` to keep the verify-install anchor unique)

### Task 10: Standardize plugin install syntax in docs/setup.md on @cortex-command form
- **Files**: `docs/setup.md`
- **What**: Audits every `/plugin install` example in `docs/setup.md` and ensures all use the scoped `<name>@cortex-command` form. Where bare-form examples exist, converts them. Per spec, setup.md may already largely use scoped form — this task verifies and locks.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: Anthropic-documented form is `/plugin install <plugin>@<marketplace>`. Bare form is undocumented and unreliable when marketplace names collide. Marketplace name (verified): `cortex-command`. Spec requirements covered: R13.
- **Verification**: `grep -c '/plugin install' docs/setup.md` equals `grep -c '/plugin install.*@cortex-command' docs/setup.md` — pass if equal; AND `grep -cE '/plugin install [a-z][a-z0-9-]*( |$)' docs/setup.md | head -1` count of bare-form (no `@`) lines, computed as `grep -E '/plugin install [a-z][a-z0-9-]*( |$)' docs/setup.md | grep -vc '@cortex-command'` returns 0 — pass.
- **Status**: [x] complete (no-op: setup.md was already canonical — install count 4, scoped count 4, bare-form count 0)

### Task 11: Annotate docs/setup.md Dependencies table as macOS-only
- **Files**: `docs/setup.md`
- **What**: Adds a one-line preamble immediately above the Dependencies table (currently around `docs/setup.md:266-276` at plan time, locate by `## Dependencies` H2) stating the table reflects macOS-only support. Use this exact phrase or a substring containing it: `primarily developed and tested on macOS`. Suggested wording: "Commands shown use Homebrew (macOS); the project is primarily developed and tested on macOS."
- **Depends on**: [10]
- **Complexity**: simple
- **Context**: Dependencies table location: `## Dependencies` H2; line range may shift after Tasks 6-10 add content above. Implementer locates `## Dependencies` H2 and places the preamble between the heading and the table. The verification anchors on the exact phrase `primarily developed and tested on macOS` so it cannot pass on pre-existing `brew install` mentions in the table. Spec requirements covered: Edge Cases (Dependencies macOS-only annotation).
- **Verification**: Extract the Dependencies section: `awk '/^## Dependencies/{flag=1; next} /^## /{flag=0} flag' docs/setup.md > /tmp/dependencies.txt`. Then: `[ -s /tmp/dependencies.txt ]` — pass; AND `grep -c 'primarily developed and tested on macOS' /tmp/dependencies.txt` returns ≥ 1 — pass (exact phrase matches the new annotation, not pre-existing brew references).
- **Status**: [x] complete

### Task 12: Sync plugin roster byte-identical between README and docs/setup.md (and fix plugin count claim)
- **Files**: `README.md`, `docs/setup.md`
- **What**: Ensures the plugin roster table or list in both `README.md` and `docs/setup.md` lists all 6 plugins from `.claude-plugin/marketplace.json` with byte-identical (name, description) pairs. Updates the "ships six plugins" prose at `README.md:97` (and any analogous prose in setup.md) so the count matches `jq '.plugins | length' .claude-plugin/marketplace.json` (currently 6). Both rosters must produce identical sorted output when (name, description) pairs are extracted.
- **Depends on**: [4, 11]
- **Complexity**: simple
- **Context**: Marketplace plugin count (verified): 6. Plugin names: `android-dev-extras`, `cortex-dev-extras`, `cortex-interactive`, `cortex-overnight-integration`, `cortex-pr-review`, `cortex-ui-extras`. Implementer must extract the source of truth for descriptions from `.claude-plugin/marketplace.json` (each plugin has a `description` field), use those verbatim in both rosters. Extraction approach for verification: `jq -r '.plugins[] | "\(.name): \(.description)"' .claude-plugin/marketplace.json | sort > /tmp/marketplace-roster.txt`, then extract from each doc and `diff` against source. The implementer-constructed extractor must be sanity-checked: each extract must produce ≥ 6 non-empty lines before the diff comparison (this gates the self-sealing failure mode where empty extractor output paired with empty source passes a trivially empty diff). Spec requirements covered: R14, R3 (count consistency AC).
- **Verification**: Build source-of-truth: `jq -r '.plugins[] | "\(.name): \(.description)"' .claude-plugin/marketplace.json | sort > /tmp/marketplace-roster.txt`; AND `[ $(wc -l < /tmp/marketplace-roster.txt) -ge 6 ]` — pass (source has ≥ 6 plugins; guards against silent jq failure); AND implementer writes a small awk/grep extractor for each doc and runs: extract README → `/tmp/readme-roster.txt` and extract setup → `/tmp/setup-roster.txt`. Then: `[ $(wc -l < /tmp/readme-roster.txt) -ge 6 ]` — pass (README extractor produced ≥ 6 lines; minimum-output sanity check); AND `[ $(wc -l < /tmp/setup-roster.txt) -ge 6 ]` — pass (setup extractor produced ≥ 6 lines); AND `diff /tmp/readme-roster.txt /tmp/marketplace-roster.txt` returns no output — pass; AND `diff /tmp/setup-roster.txt /tmp/marketplace-roster.txt` returns no output — pass; AND count-claim consistency: `grep -c "ships $(jq '.plugins | length' .claude-plugin/marketplace.json) plugins" README.md` returns ≥ 1 OR `grep -c 'ships [0-9]\+ plugins' README.md` returns 0 — pass (count claim either matches marketplace count or is removed entirely).
- **Status**: [x] complete

### Task 13: Add maintainer note to docs/setup.md enumerating 3 duplication surfaces
- **Files**: `docs/setup.md`
- **What**: Adds a one-paragraph callout under a new H3 heading `### Maintaining duplicated surfaces` (placement: between `## macOS Notifications` and `## Dependencies`, OR as a new H3 inside an existing reference H2 — implementer chooses for narrative flow) that names exactly three duplication surfaces requiring two-file edits when content changes: (1) plugin roster (README + setup.md), (2) CLI utilities list (README), (3) auth pointer (README pointer + setup.md canonical content). The callout instructs future contributors to update both files atomically when any of these surfaces changes.
- **Depends on**: [12]
- **Complexity**: simple
- **Context**: This callout is a contributor-facing note, not user-facing setup info. Placement near the bottom of `docs/setup.md` keeps it out of the prose-walkthrough. Spec edge-cases drives this requirement — the spec mandates "ALL THREE surfaces" be enumerated: plugin roster, CLI utilities list, auth pointer. Spec requirements covered: Edge Cases (3 duplication surfaces note).
- **Verification**: Extract the maintainer-note subsection: `awk '/^### Maintaining duplicated surfaces/{flag=1; next} /^### |^## /{flag=0} flag' docs/setup.md > /tmp/maintainer-note.txt`. Then: `[ -s /tmp/maintainer-note.txt ]` — pass (the H3 heading exists and the section is non-empty; co-location is enforced by single-section extraction); AND `grep -c 'plugin roster' /tmp/maintainer-note.txt` returns ≥ 1 — pass (within maintainer note); AND `grep -c 'CLI utilities' /tmp/maintainer-note.txt` returns ≥ 1 — pass; AND `grep -cE 'auth pointer|authentication pointer' /tmp/maintainer-note.txt` returns ≥ 1 — pass.
- **Status**: [x] complete (orchestrator demoted unspec'd `## Maintaining this document` H2 wrapper to keep R8 H2 ordering canonical; H3 stands alone between `## macOS Notifications` and `## Dependencies`)

## Verification Strategy

After all 13 tasks complete, run the full spec AC sweep before opening the implementation PR. Note: this sweep re-validates the same scoped checks the per-task Verification fields use, providing a final gate. Per the Verification Doctrine above, manual GitHub-render checks (R6, R7, R16) are advisory complements — the implementer performs them on github.com after pushing, but the structural ACs below are the binary gates.

**R1**: `grep -ic 'for linux or windows' README.md` returns 0; `grep -ic 'linux/windows\|linux or windows' README.md` returns 0.

**R2**: `grep -c '/plugin install' README.md` equals `grep -c '/plugin install.*@cortex-command' README.md`; `grep -c '@cortex-command' README.md` returns ≥ 1 in the Quick Start section (`awk '/^## Quick Start/{flag=1; next} /^## /{flag=0} flag' README.md | grep -c '@cortex-command'` returns ≥ 1).

**R3**: `grep -c "ships $(jq '.plugins | length' .claude-plugin/marketplace.json) plugins" README.md` returns ≥ 1 OR no numeric "ships N plugins" prose exists in README; AND Quick Start either lists install commands for all 6 plugins or contains a recommended-subset rationale keyword (`core|recommended|start with|start here|essentials`).

**R4**: For each filename in `ls bin/cortex-*` (9 total), `grep -c '\`<filename>\`' README.md` returns ≥ 1.

**R5**: `grep -cE '^[ ]*[┌┐└┘├┤┬┴┼─│]{5,}' README.md` returns ≤ 6 (allows lifecycle phase flow diagram only); AND README pitch prose mentions discovery, backlog, refine/lifecycle, overnight (`awk '/^## Prerequisites/{exit} {print}' README.md | grep -cE 'discovery.*backlog.*(refine|lifecycle).*overnight|discovery.*backlog.*overnight'` returns ≥ 1); AND scoped: `awk '/^## Prerequisites/{exit} {print}' README.md | grep -c 'docs/agentic-layer.md'` returns ≥ 1.

**R6** (scoped to Diagram A's mermaid block): extract `awk '/^### Diagram A/{flag=1; next} /^### |^## /{if(flag>=1)flag=0} /^\`\`\`mermaid/{if(flag==1){flag=2; next}} /^\`\`\`/{if(flag==2)flag=3} flag==2' docs/agentic-layer.md > /tmp/diagram-a.txt`; AND `[ -s /tmp/diagram-a.txt ]`; AND `grep -c 'REQ' /tmp/diagram-a.txt` returns ≥ 1; AND `grep -c 'draft → refined → complete' /tmp/diagram-a.txt` returns ≥ 1; AND `grep -cE 'interactive [·•] |autonomous [·•] ' /tmp/diagram-a.txt` returns ≥ 2. **Manual complement (interactive only):** view rendered Diagram A on github.com after push.

**R7**: `grep -cE '^### (API Key|OAuth Token|Using Both)' README.md` returns 0; `grep -c 'docs/setup.md#authentication' README.md` returns ≥ 1; AND `grep -cE '^## Authentication' docs/setup.md` returns 1 (single H2 with anchor-producing slug `authentication`). **Manual complement (interactive only):** click the README link on github.com and confirm anchor resolves.

**R8** (folded here, no edit task): `grep -nE '^## ' docs/setup.md` returns these H2 sections in order: `Prerequisites`, `Install`, `Authentication`, `Customization`, `Per-repo permission scoping`, `macOS Notifications`, `Dependencies`. Already true at plan time; verify it stayed true after Tasks 6-13.

**R9**: Per-repo section in `docs/setup.md` ≥ 30 lines (`awk '/^### 3\. Per-repo setup/{flag=1; next} /^### |^## /{flag=0} flag' docs/setup.md | wc -l` returns ≥ 30); contains `additively registers`, `the only write`, `fcntl.flock`; distinct keyword count returns 7 via `grep -oE 'submodule|symlink|settings\.local\.json|\.cortex-init|scaffold|\.gitignore|fcntl\.flock' /tmp/per-repo.txt | sort -u | wc -l`.

**R10**: Schema reference subsection (`#### lifecycle.config.md schema`) exists and contains all 6 keys, `Currently advisory` ≥ 3 occurrences, and consumer paths for `test-command`, `commit-artifacts`, `demo-commands` — all scoped to `awk '/^#### lifecycle\.config\.md schema/{flag=1; next} /^#### |^### |^## /{flag=0} flag' docs/setup.md > /tmp/schema-ref.txt` extract.

**R11**: Per-repo section worked example contains `cortex init` literal command line, scaffold listing, `/cortex-interactive:lifecycle`, and output-distinguishing prose — all scoped via `awk '/^### 3\. Per-repo setup/{flag=1; next} /^### |^## /{flag=0} flag' docs/setup.md` extract.

**R12**: `#### Verify install` H4 exists in `## Install` section; verify-install subsection contains `cortex --print-root` AND `claude /plugin list` AND `remote_url` AND `head_sha`.

**R13**: `grep -c '/plugin install' docs/setup.md` equals `grep -c '/plugin install.*@cortex-command' docs/setup.md`.

**R14**: Plugin roster (name, description) pairs from `README.md` and `docs/setup.md` both equal the source-of-truth extract from `.claude-plugin/marketplace.json` — `diff` returns no output AND each extract has ≥ 6 non-empty lines (minimum-output sanity).

**R15**: `grep -nE '/plugin marketplace add|/plugin install' README.md | head -1` returns the marketplace-add line.

**R16**: Quick Start contains the verification reference: `awk '/^## Quick Start/{flag=1; next} /^## /{flag=0} flag' README.md | grep -E 'claude /plugin list|setup\.md#verify-install'` returns ≥ 1 (note: `verify-install` exact, not loose `verify` substring); AND if the link form was chosen, the target heading exists in setup.md (Task 9's `#### Verify install` heading produces the slug — verified in R12 above).

**Edge-case verifications**: macOS-only annotation present in `docs/setup.md` Dependencies section (`primarily developed and tested on macOS` exact phrase); maintainer note enumerates plugin roster, CLI utilities, auth pointer (scoped to `### Maintaining duplicated surfaces` extract).

**Manual complements (interactive runs; advisory for overnight)**:
- Diagram A Mermaid block renders without syntax error on github.com (Task 5 pre-flight covers this for interactive runs).
- The `docs/setup.md#authentication` anchor link from README resolves on github.com.
- The `docs/setup.md#verify-install` anchor link from README (if R16 chose the link option) resolves on github.com.

## Veto Surface

- **R8 H2 reorder fold**: Spec R8 lists target H2 ordering. Current `docs/setup.md` ordering already matches the target (Prerequisites → Install → Authentication → Customization → Per-repo permission scoping → macOS Notifications → Dependencies). Plan folds R8 into Verification Strategy rather than allocating a dedicated task. If user prefers an explicit verification task at edit time, restore as Task 6a.
- **R3 plugin count handling in Task 12**: Plan groups the plugin count prose fix with the byte-identical roster sync (Task 12) since both touch the roster region. Alternative: split count fix into Task 2 (Quick Start) for proximity to install commands. Plan keeps it in Task 12 because the count claim currently lives in `README.md:97` (Plugin Roster section, not Quick Start).
- **R16 verification choice (inline vs. pointer)**: Spec accepts either `claude /plugin list` inline OR a pointer to `docs/setup.md#verify-install`. Plan strongly prefers the pointer form (avoids duplicating R12 content) but accepts inline. The R16 verification grep matches either; the anchor-existence AC in Task 9 only matters if pointer form is chosen.
- **Sandbox-registration phrasing in R9**: Spec R9 AC requires exact phrases `additively registers`, `the only write`, `fcntl.flock` to appear in the cortex init flow expansion. Implementer must match these phrases literally. If a reviewer prefers different wording for prose flow, the AC rules; revise the AC in spec.md (separate change) before deviating.
- **Dependencies on file-edit serialization**: Tasks 1→2→3→4 (README chain) and Tasks 6→7→8→9→10→11 (setup.md chain) are serialized via `Depends on` to avoid Edit-tool collisions on the same file AND to provide stable section-edit ordering. Serialization does NOT refresh stale plan-time line numbers in later tasks' Context fields — implementer must locate sections by heading text after the first edit lands per the Verification Doctrine note. Line numbers in Context are reference, not contract.
- **Manual GitHub-render checks**: R6/R7/R16 deliverables (Mermaid renders, anchor resolves) are observable only via human GitHub-side checks. Plan documents these as advisory complements. For interactive runs, the implementer commits, pushes, and views rendered files on github.com before marking the task complete. For overnight runs, manual checks defer to PR review. The structural ACs above gate completion in both modes; manual checks catch a residual failure surface that the structural greps cannot reach.
- **Implementer-constructed extractor for R14**: Task 12's roster sync requires the implementer to write a small extractor matching the table format in each doc. The plan adds a minimum-output sanity check (`wc -l ≥ 6` on each extract) that gates the self-sealing failure mode where an empty extractor paired with an empty source produces a passing empty diff. The extractor implementation choice is left to the implementer; the post-extract gates are firm.

## Scope Boundaries

Maps to the spec's Non-Requirements section:

- **No edits to deep reference docs** (`docs/skills-reference.md`, `docs/mcp-server.md`, `docs/pipeline.md`, `docs/sdk.md`, `docs/overnight-operations.md`).
- **No splitting `docs/setup.md`** into multiple files (Approach E rejected upstream).
- **No hosted docs site** (Vercel, Mintlify, mdBook, etc.).
- **No Linux/Windows install steps** authored. Remediation is removing the unmet README cross-platform promise (R1) plus annotating `docs/setup.md` Dependencies table as macOS-only (Task 11), not authoring untested cross-platform install commands.
- **No pre-commit drift check** for plugin roster, CLI utilities list, or any other duplicated content surface. Manual maintenance via the duplication-surfaces note (Task 13) is the accepted approach.
- **No expansion of the maintainer note's surface enumeration** beyond the spec's three (plugin roster, CLI utilities, auth pointer). Doc/code contract surfaces created by Tasks 6, 7, 9 (cortex init side effects, lifecycle.config.md schema, `cortex --print-root` keys) are out of scope for the maintainer note in this ticket. If durability of those contracts becomes a problem, that's a separate spec change.
- **No changes to `README.md:45-63`** (lifecycle phase flow diagram stays).
- **No code changes to `cortex_command/init/handler.py`** or `lifecycle.config.md` consumers. This ticket only documents existing behavior; activating the 3 advisory keys (`type`, `skip-specify`, `skip-review`) is a separate ticket if/when warranted.
- **No reorganization of `docs/agentic-layer.md`** beyond augmenting Diagram A. Diagram B and other sections are untouched.
- **No mermaid-cli or other tooling dependency** added for automated Mermaid validation. Pre-flight render is a manual github.com check on interactive runs; overnight defers to PR review.
