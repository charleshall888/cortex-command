# Specification: Restructure README and docs/setup.md for clearer onboarding

> Background: this ticket is decomposed from the **docs-setup-audit** epic. See `research/docs-setup-audit/research.md` for the full audit findings, OE-1 through OE-6 option evaluations, and the cold-reader simulation methodology note. Lifecycle research at `lifecycle/archive/restructure-readme-and-setupmd-for-clearer-onboarding/research.md` scopes those findings to this ticket and resolves the open questions surfaced during the structured interview.

## Problem Statement

The user-facing onboarding surface (`README.md` + `docs/setup.md`) carries codebase-verified defects (plugin install command syntax conflict between bare and `@cortex-command` forms, inconsistent plugin count, undocumented CLI utilities, duplicated authentication content) and a substantive per-repo flow gap (cortex init's 7 side effects, `lifecycle.config.md` schema, and no narrative bridge from `cortex init` to first `/cortex-interactive:lifecycle` invocation). These defects directly block the "shared publicly for others to clone or fork" mission stated in `requirements/project.md:7`. The fix restructures README to a trimmed value-prop + quickstart shape, expands setup.md's per-repo section in place to close the flow gap, removes the unmet cross-platform promise, and standardizes plugin install syntax on the Anthropic-documented scoped form.

## Requirements

1. **Remove README cross-platform promise**: `README.md:72`'s "For Linux or Windows setup, see docs/setup.md" line is deleted.
   - AC: `grep -ic "for linux or windows" README.md` returns 0 (case-insensitive to catch case variants).
   - AC: `grep -ic "linux/windows\|linux or windows" README.md` returns 0.

2. **Standardize plugin install syntax in README on `@cortex-command` form**: every `/plugin install <name>` example in README uses the scoped form. Verification is per-line, not aggregate.
   - AC: `grep -c "/plugin install" README.md` equals `grep -c "/plugin install.*@cortex-command" README.md` (every install line has the scope suffix).
   - AC: `grep -c "@cortex-command" README.md` returns ≥1 in the Quick Start section (positive existence check).

3. **Plugin count consistency in README**: prose claims about plugin count match `.claude-plugin/marketplace.json`'s actual count. Quick Start install steps either install all plugins listed in the roster, or explicitly identify a "recommended for first install" subset and link to the roster for the rest.
   - AC: Wherever a numeric plugin count appears in README (currently the phrase "ships six plugins" at L97 inside `### Plugin roster`), the number matches the row count of plugins in `.claude-plugin/marketplace.json`. Verification: `grep -c "ships $(jq '.plugins | length' .claude-plugin/marketplace.json) plugins" README.md` returns ≥1, OR no numeric "ships N plugins" prose exists in README.
   - AC: Either the Quick Start install command list contains exactly one `/plugin install` line per plugin in the roster, OR the Quick Start contains a sentence beginning with "Install" followed by a comma-separated list of plugin names AND a sentence containing one of the keywords `core`, `recommended`, `start with`, `start here`, or `essentials` to denote the subset rationale.

4. **Complete CLI utilities list in README**: every `bin/cortex-*` executable is listed in the README's utilities section, identified by name in backticks (the canonical convention).
   - AC: For each filename matched by `ls bin/cortex-*`, `grep -c "\`<filename>\`" README.md` returns ≥1 (the filename appears wrapped in backticks at least once). Backtick anchoring eliminates substring false positives between filenames that share root tokens (e.g., `cortex-create-backlog-item` vs. `cortex-generate-backlog-index`).
   - AC: This must cover the 2 currently-undocumented utilities (`cortex-archive-rewrite-paths`, `cortex-archive-sample-select`) and any future additions.

5. **Remove README pipeline ASCII diagram (L9-43)**: the box-art requirements→discovery→backlog→lifecycle pipeline diagram is removed from README. Replace with a 2-3 sentence prose summary that links to `docs/agentic-layer.md` for the full visual.
   - AC: README.md does not contain the box-drawing region. Verification: `grep -cE '^[ ]*[┌┐└┘├┤┬┴┼─│]{3,}' README.md` returns ≤ a small budget (≤6 lines) — this allows the lifecycle phase flow diagram at the current L45-63 to remain (which uses similar characters) but flags any reintroduction of a 35-line ASCII pipeline diagram. (R8-style note: the lifecycle diagram contains some box-drawing characters; if false positives result, narrow the regex to consecutive runs of ≥5 box-drawing chars on a single line, then re-test.)
   - AC: The pitch prose above Prerequisites mentions discovery, backlog, refine/lifecycle, and overnight in narrative form, AND links to `docs/agentic-layer.md` for the visual.

6. **Augment Mermaid Diagram A in `docs/agentic-layer.md`**: the existing `### Diagram A — Main Workflow Flow` (currently at L70-114) is augmented with content unique to the removed README ASCII diagram. Encoding guidance:
   - **`requirements/project.md` input node**: add a node `REQ([requirements/project.md])` with an edge `REQ -->|"informs scope"| DISC` (matches the "informs scope" label from the removed ASCII diagram).
   - **Backlog status state machine**: change the BACKLOG node from `BACKLOG[("Backlog")]` to `BACKLOG[("Backlog<br/>draft → refined → complete")]`. Mermaid `<br/>` is a literal HTML break inside a `[("...")]` cylinder label and renders correctly on GitHub.
   - **Interactive/autonomous edge labels**: existing edges from BACKLOG to LC and BACKLOG/REFINE pathways already carry operational labels. Augment the BACKLOG → REFINE edge with `|"autonomous · pick item"|` (replacing the existing `"pick item"`). Augment the BACKLOG → LC edge (currently routed via DEV) with `|"interactive · single feature"|` (replacing the existing `"single feature"`). The dot-separator `interactive · operational-label` and `autonomous · operational-label` is the chosen encoding; future contributors editing Diagram A must preserve this format.
   - AC: `grep -c "REQ" docs/agentic-layer.md` returns ≥1 inside Diagram A's Mermaid block (locate the block by finding the line `### Diagram A — Main Workflow Flow` and reading the next ` ```mermaid` fence).
   - AC: `grep -c "draft → refined → complete" docs/agentic-layer.md` returns ≥1.
   - AC: `grep -cE 'interactive [·•] |autonomous [·•] ' docs/agentic-layer.md` returns ≥2 (one for each axis label).

7. **Replace README authentication section with a pointer block**: `README.md:110-140` (full Authentication section, including `### API Key`, `### OAuth Token`, `### Using Both` subheadings) is replaced with a 2-3 line callout that links to `docs/setup.md#authentication`.
   - AC: README.md does not contain `### API Key`, `### OAuth Token`, or `### Using Both` as H3 subheadings. Verification: `grep -cE '^### (API Key|OAuth Token|Using Both)' README.md` returns 0.
   - AC: README.md contains a markdown link with target `docs/setup.md#authentication` (or equivalent fragment).
   - AC: After R8 is implemented, manually verify the `#authentication` anchor resolves on GitHub (the rendered anchor for `## Authentication` is `#authentication`).

8. **Reorder `docs/setup.md` to prose-walkthrough first, reference content second** (OE-2 Approach D). The per-repo flow stays as an H3 (`### 3. Per-repo setup`) inside the `## Install` H2 to match current structure; only H2 sections are reordered.
   - AC: `grep -nE '^## ' docs/setup.md` returns the H2 sections in this order: `Prerequisites` → `Install` → `Authentication` → `Customization` → `Per-repo permission scoping` → `macOS Notifications` → `Dependencies`. (No new H2 for per-repo flow; per-repo stays nested inside Install.)

9. **Expand cortex init flow in `docs/setup.md`** (currently L72-78, 6 lines) to document all 7 side effects:
   - AC: The expanded section names each of: (1) git repo root resolution / submodule refusal, (2) symlink-safety gate, (3) `~/.claude/settings.local.json` validation, (4) `.cortex-init` marker check, (5) scaffold dispatch (lifecycle/, backlog/, retros/, requirements/, marker file), (6) idempotent `.gitignore` append, (7) sandbox registration into `~/.claude/settings.local.json:sandbox.filesystem.allowWrite` with `fcntl.flock` serialization.
   - AC: Section length grows to ≥30 lines from the current 6.
   - AC: The sandbox registration description contains the exact phrases `additively registers` AND `the only write` AND `fcntl.flock` (without depending on the volatile `requirements/project.md:26` line number — match content directly so unrelated edits to `project.md` cannot drift the AC).

10. **Document `lifecycle.config.md` schema in `docs/setup.md`** with all 6 keys, accurately distinguishing actively-consumed keys from advisory ones:
    - AC: The schema reference names all 6 keys: `type`, `test-command`, `skip-specify`, `skip-review`, `commit-artifacts`, `demo-commands`.
    - AC: For `test-command`, the doc states it is read by `cortex_command/overnight/daytime_pipeline.py` and defaults to `just test` when missing.
    - AC: For `commit-artifacts`, the doc states it is read by the lifecycle skill's commit step (`skills/lifecycle/references/{complete,research,plan,specify}.md`) and that `commit-artifacts: false` excludes lifecycle artifacts from staging.
    - AC: For `demo-commands`, the doc states it is read by the morning-review skill (`skills/morning-review/SKILL.md` and `references/walkthrough.md`) for the post-overnight demo offer; that the schema accepts a list of `{label, command}` entries; and that it takes precedence over the legacy `demo-command:` single-string form when both are present.
    - AC: For each of `type`, `skip-specify`, `skip-review`, the doc contains the exact phrase `Currently advisory` (capitalized as shown) — no "or equivalent" loophole. These three keys are present in the scaffold template (`cortex_command/init/templates/lifecycle.config.md`) but not consumed by any code path or skill prose at present.

11. **Worked first-invocation example in `docs/setup.md`** demonstrating `cortex init` followed by a first `/cortex-interactive:lifecycle <feature>` invocation:
    - AC: The example contains a fenced code block (`\`\`\`bash` or `\`\`\`shell` or `\`\`\``) showing the literal command `cortex init` being run.
    - AC: The example contains a directory tree or file listing of what `cortex init` creates (e.g., `lifecycle/`, `backlog/`, `retros/`, `requirements/`, `.cortex-init`).
    - AC: The example contains a separate fenced code block showing `/cortex-interactive:lifecycle <feature>` being invoked (with a placeholder feature name like `<feature>` or `my-feature` or similar).
    - AC: Adjacent prose explicitly distinguishes outputs from `cortex init` versus outputs from the lifecycle invocation (use of phrasing like "After `cortex init` completes…" and "Then run `/cortex-interactive:lifecycle <feature>` to begin a new feature, which produces …" satisfies this).

12. **Install verification step in `docs/setup.md`**: at the end of the Install section, a smoke-test command verifies the install succeeded.
    - AC: The Install section ends with a fenced code block containing `cortex --print-root` AND `claude /plugin list` (in either order, on one or two lines). Note: the spec uses `cortex --print-root` (not `cortex --version`) because `cortex --version` is not implemented — the CLI's versioning surface is `cortex --print-root`, which returns versioned JSON. **Implementation must verify** the command works locally before pinning it in docs (run `cortex --print-root` and confirm it prints valid JSON containing a `version` key).
    - AC: Expected output is shown or described — at minimum, the doc says `cortex --print-root` prints JSON with `version`, `root`, `remote_url`, and `head_sha` fields, and that `claude /plugin list` lists the installed plugins from the `cortex-command` marketplace.

13. **Standardize plugin install syntax in `docs/setup.md` on `@cortex-command` form**: same canonicalization as R2.
    - AC: `grep -c "/plugin install" docs/setup.md` equals `grep -c "/plugin install.*@cortex-command" docs/setup.md`.
    - AC: All `/plugin install` examples use the scoped `<name>@cortex-command` form.

14. **Preserve plugin roster table in both README and `docs/setup.md` with byte-identical content** (per user decision to accept duplication tax). Verification uses literal text extraction, not "semantic" judgment:
    - AC: README contains a plugin roster table or list naming all plugins in `.claude-plugin/marketplace.json`.
    - AC: `docs/setup.md` contains a plugin roster naming all plugins in `.claude-plugin/marketplace.json`.
    - AC: Extract the plugin name + one-line description for each plugin from both rosters; the extracted (name, description) pairs are sorted and compared. The two sorted lists are byte-identical (`diff` returns no differences). Implementation must produce a small extraction script or use `awk`/`grep` against table rows; the extraction approach is left to implementation but the resulting diff must be empty.

15. **Quick Start in README documents the `/plugin marketplace add` precondition before any `/plugin install` command**: the marketplace-add step is required before scoped-form install commands resolve. Without it, fresh forkers hit "marketplace not found" on the first install command.
    - AC: README's Quick Start section (under `## Quick Start` H2) contains the literal command `/plugin marketplace add charleshall888/cortex-command` (or whatever the canonical owner/repo string is — verify against `docs/setup.md:37`'s current usage).
    - AC: The marketplace-add command appears BEFORE the first `/plugin install` line in README. Verification: `grep -n "/plugin marketplace add\|/plugin install" README.md | head -1` returns a `/plugin marketplace add` line.

16. **README Quick Start ends with a one-line verification reference**: closes the README-side verification gap that the trim direction's "verification" item promised but was previously placed only in setup.md.
    - AC: README's Quick Start section ends with a verification line — either an inline command (`claude /plugin list` to confirm plugins installed) OR an explicit pointer ("Verify the install with the smoke test in [Setup guide § Verify install](docs/setup.md#verify-install)" or equivalent linking to the R12 verification block in setup.md).
    - AC: Whichever option is chosen must be detectable: `grep -E "claude /plugin list|setup\.md#verify" README.md` returns ≥1 match in the Quick Start.

## Non-Requirements

- **No edits to deep reference docs**: `docs/skills-reference.md`, `docs/mcp-server.md`, `docs/pipeline.md`, `docs/sdk.md`, `docs/overnight-operations.md` are out of scope per `CLAUDE.md:50`'s owning-doc rule.
- **No splitting `docs/setup.md` into multiple files** (Approach E rejected upstream — out of the user's stated binary).
- **No hosted docs site** (Vercel, Mintlify, mdBook, etc.).
- **No Linux/Windows install steps**: cross-platform delivery dropped during Clarify in deference to "primarily personal tooling" / "favors highly customized... over generic solutions" per `requirements/project.md:7`. The remediation is removing the unmet promise (R1) and annotating setup.md's Dependencies table as macOS-only (see Edge Cases), not authoring untested install steps.
- **No pre-commit drift check** for the plugin roster duplication, the CLI utilities list, or any other duplicated content surface. The duplication tax is accepted manually; automation is out of OE-1 scope.
- **No changes to `README.md:45-63` lifecycle phase flow diagram**: this diagram stays in README per OE-4.
- **No code changes to `cortex_command/init/handler.py`** or `lifecycle.config.md` consumers: this ticket only documents existing behavior. Making the 3 truly advisory `lifecycle.config.md` keys (`type`, `skip-specify`, `skip-review`) actually read by code is a separate ticket if/when warranted.
- **No reorganization of `docs/agentic-layer.md`** beyond augmenting Diagram A. Diagram B (lifecycle phase sequence) and other sections are untouched.

## Edge Cases

- **Three duplication surfaces, not one**: this spec accepts a manual duplication tax across (a) plugin roster (R14, README + setup.md), (b) CLI utilities list (R4, currently README only but with overlap if a similar list lands in `docs/agentic-layer.md`), and (c) auth pointer (R7, README pointer + setup.md canonical content). A maintainer note in `docs/setup.md` (or in `CLAUDE.md`'s Conventions section) must enumerate ALL THREE surfaces so future contributors update them atomically. → Implementation must add a one-paragraph `### Maintaining duplicated surfaces` callout in setup.md (or a comparable note in CLAUDE.md) that names plugin roster, CLI utilities list, and auth pointer as the three surfaces requiring two-file edits.
- **Plugin addition (post-merge maintenance)**: adding a new plugin to `.claude-plugin/marketplace.json` requires updating the plugin roster table in BOTH `README.md` and `docs/setup.md`, plus the install command list in the README Quick Start (R3, R14, R15). → The maintainer note above covers this case.
- **CLI utility addition**: adding a new `bin/cortex-*` executable requires updating the README utilities list (R4). → Same maintainer note.
- **Marketplace name change**: if the `cortex-command` marketplace is renamed, every `@cortex-command` reference in README and setup.md must update, including R15's `/plugin marketplace add` line. → Implementation may parameterize the install snippets with a placeholder (`<plugin>@<marketplace-name>`) noted near the Quick Start, with `cortex-command` as the current value, so future renames have a single conceptual locus to update.
- **Mermaid render failure**: `docs/agentic-layer.md` Diagram A rendered as Mermaid fails to display in environments that don't support it (raw GitHub view supports Mermaid; other markdown viewers may not). → Mitigation: README's prose summary of the pipeline (per R5) ensures the value-prop is conveyed even if the Mermaid diagram doesn't render.
- **Worked example drift**: the cortex init worked example (R11) shows specific files/directories created. If `cortex init`'s scaffolds change in `cortex_command/init/scaffold.py`, the example must update. → Document the scaffold list in the example as the contract; if scaffolds change, the example must be updated as part of that change.
- **Setup.md Dependencies table is macOS-only**: the table at `docs/setup.md:266-276` uses `brew install` exclusively. Removing README.md:72's cross-platform pointer (R1) without annotating this table would convert an unmet promise into an unstated platform exclusion. → Implementation must add a one-line preamble to the Dependencies table such as "Commands shown use Homebrew (macOS); the project is primarily developed and tested on macOS." This honors the explicit-exclusion principle without committing to cross-platform support.
- **Anchor stability**: R7's link to `docs/setup.md#authentication` resolves only if `## Authentication` exists as an H2 in setup.md after R8's reorder. R8 explicitly preserves `## Authentication` as an H2; verify the rendered anchor on GitHub during implementation as a final manual check.
- **Lifecycle.config.md key activation in future**: if a future ticket activates one of the 3 advisory keys (`type`, `skip-specify`, `skip-review`) by adding a code consumer, the schema doc in setup.md must update from `Currently advisory` to a description of the consumer. This forward coupling is unowned by an explicit follow-up ticket; it is the responsibility of whichever future ticket adds the consumer to also update the schema doc atomically.

## Changes to Existing Behavior

- **MODIFIED**: README opening (L1-43) — replaces 35-line ASCII pipeline diagram with 2-3 sentence prose pitch + link to `docs/agentic-layer.md`. The lifecycle phase flow diagram at L45-63 stays.
- **MODIFIED**: README Quick Start (L86-91) — adds `/plugin marketplace add` precondition (R15); plugin install commands switch from bare to `@cortex-command`-scoped form; install commands either cover all roster entries OR identify a recommended subset; ends with a one-line verification reference (R16).
- **MODIFIED**: README plugin count claim — verified consistent with `.claude-plugin/marketplace.json`; intro/roster/Quick Start counts all align.
- **MODIFIED**: README utilities list (L152) — extended to cover all 9 `bin/cortex-*` executables with backtick-anchored names.
- **MODIFIED**: README cross-platform statement (L72) — removed entirely.
- **MODIFIED**: README authentication section (L110-140) — collapsed to a 2-3 line pointer block referencing `docs/setup.md#authentication`.
- **MODIFIED**: `docs/setup.md` H2 ordering — reorganized so prose-walkthrough sections (Prerequisites, Install with nested per-repo H3, Authentication) precede reference-style sections (Customization, Permission scoping, Notifications, Dependencies).
- **MODIFIED**: `docs/setup.md` per-repo flow (currently nested as `### 3. Per-repo setup` inside `## Install`) — expanded from 6 lines to ≥30 lines covering all 7 cortex init side effects + `lifecycle.config.md` schema reference + worked first-invocation example.
- **MODIFIED**: `docs/setup.md` plugin install commands — already use scoped form; verify and lock during the canonicalization pass.
- **MODIFIED**: `docs/setup.md` Dependencies table (L266-276) — adds a one-line macOS-only annotation preamble (per Edge Cases).
- **MODIFIED**: `docs/agentic-layer.md` Diagram A (Mermaid) — augmented per R6's encoding guidance.
- **ADDED**: `docs/setup.md` lifecycle.config.md schema reference covering all 6 keys, accurately identifying 3 active consumers (`test-command`, `commit-artifacts`, `demo-commands`) and 3 advisory keys (`type`, `skip-specify`, `skip-review`).
- **ADDED**: `docs/setup.md` install verification step at the end of the Install section using `cortex --print-root` and `claude /plugin list`.
- **ADDED**: `docs/setup.md` (or `CLAUDE.md`) maintainer note enumerating the 3 duplication surfaces (plugin roster, CLI utilities, auth pointer).
- **ADDED**: README Quick Start verification line (R16) closing the README-side verification gap.
- **REMOVED**: `README.md:9-43` (pipeline ASCII diagram).
- **REMOVED**: `README.md:72` (cross-platform Linux/Windows pointer).
- **REMOVED**: `README.md:110-140` (full Authentication section, replaced by pointer per R7).

## Technical Constraints

- **Owning-doc rule (`CLAUDE.md:50`)**: must not duplicate or move content from `docs/overnight-operations.md`, `docs/pipeline.md`, `docs/sdk.md`, or `docs/mcp-server.md` into README or `docs/setup.md`. Cross-link, don't reproduce.
- **Distribution constraint (`CLAUDE.md`)**: docs must reflect the canonical install path — `uv tool install -e .` (CLI) + `/plugin install <name>@cortex-command` (plugins, after `/plugin marketplace add` precondition) + `cortex init` (per-repo). Not PyPI, not brew, not symlinks.
- **Sandbox / per-repo registration constraint (`requirements/project.md`)**: cortex init's `~/.claude/settings.local.json` write must be documented as **additive** (appends to `sandbox.filesystem.allowWrite`, does not overwrite), serialized via `fcntl.flock`, and the **only** write cortex-command performs inside `~/.claude/`. Users do not hand-edit (per existing `docs/setup.md:180`). The R9 AC matches these phrases by content rather than by line number to avoid drift.
- **Defense-in-depth permissions constraint**: docs must not advise hand-editing `sandbox.filesystem.allowWrite` or `~/.claude/settings.json` allow lists; the `cortex init`-driven path is the supported channel.
- **Anthropic plugin install convention** ([code.claude.com/docs/en/discover-plugins](https://code.claude.com/docs/en/discover-plugins)): the documented form is `/plugin install <plugin>@<marketplace>`; the bare form is undocumented and unreliable when marketplace names collide ([anthropics/claude-code#20593](https://github.com/anthropics/claude-code/issues/20593)). Standardization on the scoped form (R2, R13) plus the marketplace-add precondition (R15) aligns with Anthropic's pattern.
- **`cortex --print-root` is the verification surface, not `cortex --version`**: the CLI does not implement `--version` (verified empirically: `cortex --version` returns "unrecognized arguments"). The implementation must verify `cortex --print-root` works locally before pinning it in docs (R12).
- **lifecycle.config.md consumers (verified empirically)**:
  - `test-command` is read by `cortex_command/overnight/daytime_pipeline.py:173-191`.
  - `commit-artifacts` is read by `skills/lifecycle/references/{complete,research,plan,specify}.md` (skill prose: "If `commit-artifacts: false`, exclude lifecycle artifacts from staging").
  - `demo-commands` is read by `skills/morning-review/SKILL.md:101` and `skills/morning-review/references/walkthrough.md` (extensive parsing rules; takes precedence over legacy `demo-command:` single-string form).
  - `type`, `skip-specify`, `skip-review` are present in scaffold templates (`cortex_command/init/templates/lifecycle.config.md`) but not consumed by any code or skill prose at present.
- **Settings JSON validity**: any `~/.claude/settings.local.json` JSON snippets quoted in docs must parse as valid JSON.
- **Markdown anchor compatibility**: section anchor links (`docs/setup.md#authentication`) must match GitHub's auto-generated anchor format. Verify each cross-link resolves on GitHub web during implementation.

## Open Decisions

None. All decisions surfaced during research, the structured interview, and critical review have been resolved within the spec.
