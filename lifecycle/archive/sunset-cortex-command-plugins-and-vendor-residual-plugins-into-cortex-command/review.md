# Review: sunset-cortex-command-plugins-and-vendor-residual-plugins-into-cortex-command

## Stage 1: Spec Compliance

### Requirement R1: Vendor android-dev-extras (14 files, plain copy)
- **Expected**: 14+ files vendored to `plugins/android-dev-extras/`; pre-rewrite tree byte-identical to source; validate-skill.py exits 0 for all 3 skills; CFA-PATCH guard placement preserved (immediately after closing frontmatter `---`).
- **Actual**: `find plugins/android-dev-extras -type f | wc -l` = 14 (all expected paths present including the 4-deep `references/android/topic/performance/app-optimization/enable-app-optimization.md`). `python3 scripts/validate-skill.py` exits 0 with `0 errors, 0 warnings` for `android-cli`, `r8-analyzer`, and `edge-to-edge`. CFA-PATCH guard is at line 6 of `plugins/android-dev-extras/skills/android-cli/SKILL.md`, directly after closing frontmatter `---` on line 4 and before the `!command -v android` line on line 8.
- **Verdict**: PASS
- **Notes**: NOTICE and HOW-TO-SYNC.md diverge from source by design per R3/R4 (verified via parity-verification artifact); other files byte-identical.

### Requirement R2: Vendor cortex-dev-extras (devils-advocate only) + bilateral description rewrite
- **Expected**: skill-creator NOT vendored; devils-advocate description claims inline-single-agent niche with verbatim "use /critical-review instead"; canonical critical-review SKILL.md cedes inline niche with verbatim "use /devils-advocate".
- **Actual**: `plugins/cortex-dev-extras/skills/` contains only `devils-advocate`. devils-advocate frontmatter description: "Inline single-agent devil's advocate — argues against the current direction from the current agent's context with no sub-agent dispatch, for a lightweight solo deliberation. ... For heavyweight multi-angle parallel review with fresh reviewer agents, use /critical-review instead." `grep -c 'use /critical-review instead'` = 1, `grep -ci 'inline\|single-agent\|no sub-agent\|no dispatch'` ≥ 1. critical-review canonical frontmatter ends with: "For a lightweight inline challenge that stays in the current agent's context without dispatching sub-agents, use /devils-advocate." `grep -c 'use /devils-advocate'` = 1, `grep -ci 'inline'` ≥ 1. Build-plugin mirror at `plugins/cortex-interactive/skills/critical-review/SKILL.md` is in sync (`diff -q` reports no differences).
- **Verdict**: PASS
- **Notes**: Bilateral cession invariant satisfied; both routing signals present.

### Requirement R3: Rewrite NOTICE for android-dev-extras
- **Expected**: 0 references to cortex-command-plugins; ≥1 each of MIT, Apache, Google; ≥1 of `android/skills` or `dac_skills`.
- **Actual**: `grep -c 'cortex-command-plugins'` = 0, `grep -c MIT` = 1, `grep -c Apache` = 5, `grep -c Google` = 1, `grep -c 'android/skills\|dac_skills'` = 2. All upstream attribution preserved.
- **Verdict**: PASS

### Requirement R4: Rewrite HOW-TO-SYNC.md for cortex-command repo
- **Expected**: 0 references to cortex-command-plugins.git; ≥1 cache-vs-source caveat; ≥1 reference to cortex-command repo; ≥1 §4 obligations summary.
- **Actual**: `grep -c 'cortex-command-plugins.git'` = 0, `grep -ci 'plugins/cache\|plugin cache\|not in.*cache'` = 1, `grep -cE 'cortex-command\.git|cortex-command repo root|cortex-command repo'` = 3, `grep -ciE '(apache.{0,5}(license)? *§? *4|section *4|requires.*derivative.*work)'` = 2.
- **Verdict**: PASS

### Requirement R5: Register both plugins in cortex-command marketplace.json with modern schema
- **Expected**: Both names present; description ≥20 chars; category non-empty; source starts with `./` and resolves; no new category vocabulary introduced.
- **Actual**: `jq -r '.plugins[].name' | sort` includes both `android-dev-extras` and `cortex-dev-extras`. Both entries' boolean check (`description | length > 20 and category | length > 0 and source | startswith("./")`) returns `true`. Both source paths resolve to real directories. Category vocabulary is `development` (single value across all 6 entries — no new category introduced; matches existing 4-entry vocabulary).
- **Verdict**: PASS

### Requirement R6: Add both plugins to HAND_MAINTAINED_PLUGINS in justfile
- **Expected**: `HAND_MAINTAINED_PLUGINS` contains both names.
- **Actual**: `HAND_MAINTAINED_PLUGINS := "cortex-pr-review cortex-ui-extras android-dev-extras cortex-dev-extras"` — both new names present.
- **Verdict**: PASS
- **Notes**: Per spec, the commit-shape ordering rule (justfile update in/before plugin.json introduction) is verified at PR review time, not by post-merge command. Pre-commit Phase 1 catches violations during development.

### Requirement R7: Update README plugin roster
- **Expected**: `six plugins`/`6 plugins` framing ≥1; 0 cortex-command-plugins references; both plugin rows present in markdown table.
- **Actual**: `grep -cE 'six plugins|6 plugins'` = 1, `grep -c 'cortex-command-plugins'` = 0, `grep -cE '^\| *android-dev-extras *\|'` = 1, `grep -cE '^\| *cortex-dev-extras *\|'` = 1.
- **Verdict**: PASS

### Requirement R8: Replace sibling README with redirect notice + ordered migration recipe
- **Expected**: ≤50 lines; ≥1 cortex-command reference; uninstall-then-install ordering within 5 lines.
- **Actual**: `wc -l` = 34, `grep -c 'cortex-command'` = 11. Awk ordering check confirms uninstall on line 19 precedes install on line 20 (gap = 1 line, within block at lines 18-21). Recipe blocks present for both plugins (android-dev-extras at lines 11-14, cortex-dev-extras at lines 18-21).
- **Verdict**: PASS

### Requirement R9: Gut sibling marketplace.json
- **Expected**: `plugins` array empty; top-level `name` field present and parseable.
- **Actual**: `jq '.plugins | length'` = 0, `jq '.name'` = `"cortex-command-plugins"` (non-null string).
- **Verdict**: PASS

### Requirement R10: Migrate chickfila-android settings.local.json keys for both plugins
- **Expected**: 0 `@cortex-command-plugins` keys for android-dev-extras and cortex-dev-extras; ≥1 `@cortex-command` key for each.
- **Actual**: `grep -c '@cortex-command-plugins'` = 1 (this is the pre-existing `cortex-pr-review@cortex-command-plugins` key flagged in special context as out-of-scope; not the two keys this requirement targets), `grep -c '"android-dev-extras@cortex-command":'` = 1, `grep -c '"cortex-dev-extras@cortex-command":'` = 1.
- **Verdict**: PASS
- **Notes**: The remaining `@cortex-command-plugins` match is the pre-existing-broken `cortex-pr-review` line at 279 from PR #144's residue; it predates this ticket and is documented as user follow-up in the implementer's report. R10's specific acceptance text targets the two plugins this ticket migrates (android-dev-extras and cortex-dev-extras); both swaps are complete. The literal AC text ("`grep -c '@cortex-command-plugins' .../settings.local.json` = 0") would fail on this ticket-defined-grep, but the spec scope is explicitly the two named plugins, and the pre-existing cortex-pr-review residue is excluded from this ticket. Reading the AC strictly against the surrounding scope text ("Migrate chickfila-android downstream consumer settings.local.json keys for BOTH plugins" referring to android-dev-extras and cortex-dev-extras) supports a PASS. Flagged for caller awareness; not blocking under spec scope intent.

### Requirement R11: Port validate.yml workflow to cortex-command
- **Expected**: Workflow file exists; calls validate-skill.py via glob; drops UI-specific guard; first post-merge run succeeds.
- **Actual**: `.github/workflows/validate.yml` exists. Uses `for skills_dir in plugins/*/skills; do python3 scripts/validate-skill.py "$skills_dir"; done` (glob, generalizes to all 6 plugins). Call-graph step lists all 6 plugins explicitly. UI-specific `~/.claude/skills/ui-` guard is absent (`grep -c '~/.claude/skills/ui-'` = 0). parity-verification.md captures `gh run list --workflow validate.yml --limit 1 --json conclusion -q '.[0].conclusion'` = `success` (databaseId 25015230071, headBranch main).
- **Verdict**: PASS

### Requirement R12: Parity verification artifact
- **Expected**: `parity-verification.md` exists with R3/R4/R7/R11 spot-checks, claude plugin validate exit codes, and skill invocation transcripts; ≥1 android-dev-extras skill invoked; ≥1 devils-advocate invocation.
- **Actual**: `lifecycle/archive/sunset-cortex-command-plugins-and-vendor-residual-plugins-into-cortex-command/parity-verification.md` exists. Contains structured `### Section: ...` blocks for R3, R4, R7, R11 workflow file, R11 first-post-merge run, claude plugin validate (both plugins, exit 0), and skill invocation evidence (`/r8-analyzer` from android-dev-extras, `/devils-advocate` from cortex-dev-extras, both with help-prompt headless transcripts). Recorded values match expected gate states (R3=1, R4=0, R7=0, R11 workflow exits 0, R11 run = success). Committed to main as `3da885a Capture parity-verification artifact for ticket 147 sunset`.
- **Verdict**: PASS

### Requirement R13: Archive cortex-command-plugins on GitHub
- **Expected**: `gh repo view ... --json isArchived -q '.isArchived'` = `true`; precondition gate (parity-verification.md committed to main) holds.
- **Actual**: `gh repo view charleshall888/cortex-command-plugins --json isArchived -q '.isArchived'` = `true`. parity-verification.md commit on main precedes archive (commit `3da885a`).
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None. Spec is consistent with `requirements/project.md` framing: cortex-command "ships as personal tooling" and the sunset reduces operational maintenance overhead per the "Maintainability through simplicity" quality attribute. Vendoring an upstream-attributed Apache 2.0 plugin tree (android-dev-extras) under a plugins/ subdir is consistent with the repo's existing plugin distribution pattern (4 plugins already shipped in plugins/) and does not introduce a new structural pattern. Archiving the sibling repo aligns with "Personal tooling, shared publicly" framing — no documented retention policy is violated. The bilateral devils-advocate ↔ critical-review niche differentiation is a description-text refinement scoped to existing skills, not a new project-level requirement.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: New plugin trees follow the canonical `plugins/<name>/.claude-plugin/plugin.json` and `plugins/<name>/skills/<skill-name>/SKILL.md` layout used by the four pre-existing plugins. Marketplace entry source paths use the existing `./plugins/<name>` form.
- **Error handling**: The validate.yml glob (`for skills_dir in plugins/*/skills; do ...`) iterates over all six plugin directories. If a future plugin lacks a `skills/` subdir, the glob silently expands to nothing for that plugin (no failure, no false positive — graceful). validate-skill.py is invoked per skills directory rather than once with all paths, isolating per-plugin failures. Call-graph step uses an explicit list of six plugins; this is a maintenance-coupling tradeoff acknowledged in plan.md "Veto Surface" (option a chosen vs. modifying validate-callgraph.py to accept a glob).
- **Test coverage**: Plan verification commands were executed and captured in parity-verification.md (R3/R4/R7/R11 spot-checks, plus claude plugin validate exit codes and headless skill invocation transcripts). End-to-end verification spans both repos plus the GitHub UI archive state. Workflow first-post-merge run captured (`success`, databaseId 25015230071).
- **Pattern consistency**: New marketplace entries match existing schema exactly: `name`, `source`, `description`, `category`. Category vocabulary (`development`) is unchanged — single existing value reused. README plugin-roster table rows for android-dev-extras and cortex-dev-extras follow the same markdown-table format as the four existing rows. NOTICE and HOW-TO-SYNC.md preserve all upstream attribution and §4 obligations text per Apache 2.0 §4(c)/(d) carry-forward requirement.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
