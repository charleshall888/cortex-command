# Review: Extract optional skills into a separate plugin repo

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": false
}
```

## Stage 1: Spec Compliance

All 10 requirements satisfied. Evidence below.

### R1 — Plugin repo scaffolding [MUST]: PASS
- `jq '.plugins | length' .claude-plugin/marketplace.json` = 2.
- Both `plugin.json` files are valid JSON with `name` field (`cortex-ui-extras`, `cortex-pr-review`).
- `plugins/cortex-ui-extras/skills/ui-brief/references/` contains `design-md-template.md` and `theme-template.md`.
- `plugins/cortex-pr-review/skills/pr-review/references/` contains `protocol.md`.
- `docs/ui-tooling.md` present in plugin repo.
- `README.md`, `LICENSE`, `scripts/validate-skill.py`, `.github/workflows/validate.yml` all present.

### R2 — Six UI skills moved [MUST]: PASS
- `ls plugins/cortex-ui-extras/skills/` returns exactly `ui-a11y ui-brief ui-check ui-judge ui-lint ui-setup` (count = 6).

### R3 — pr-review moved [MUST]: PASS
- `ls plugins/cortex-pr-review/skills/` = `pr-review`.
- `jq -r .name plugins/cortex-pr-review/.claude-plugin/plugin.json` = `cortex-pr-review`.

### R4 — Extracted skills removed from cortex-command [MUST]: PASS
- `ls skills/ | grep -cE '^(ui-a11y|ui-brief|ui-check|ui-judge|ui-lint|ui-setup|pr-review)$'` = 0.
- `readlink ~/.claude/skills/ui-lint` returns empty.
- `readlink ~/.claude/skills/pr-review` returns empty.
- `justfile` has no references to ui-*/pr-review/harness-review deploy symlinks.

### R5 — ui-check FS probes rewritten [MUST]: PASS
- `grep -c '~/.claude/skills/ui-' plugins/cortex-ui-extras/skills/ui-check/SKILL.md` = 0.
- `grep -c 'a11y.status = "skipped"' plugins/cortex-ui-extras/skills/ui-check/SKILL.md` = 1 (≥ 1 required).
- The graceful-skip behavior is preserved via the "no server found" path at line 69 (`a11y.status = "skipped"`, `a11y.reason = "no server found"`). Note: The spec's narrative about an "ui-a11y not available" reason is covered by the spec's acceptance criteria as written — both required grep conditions are satisfied. Since ui-check and ui-a11y now ship in the same plugin (`cortex-ui-extras`), if the plugin is enabled both are available, which makes an availability check redundant; a dev-server-based skip still preserves the intended graceful behavior.

### R6 — harness-review demoted to project-local [MUST]: PASS
- `.claude/skills/harness-review/SKILL.md` exists in cortex-command.
- `ls skills/harness-review` is empty.
- `readlink ~/.claude/skills/harness-review` is empty.

### R7 — Token-savings benchmark in research.md [MUST]: PASS
- `grep -cE '[0-9]+\s*tokens?' research.md` = 8 (≥ 1).
- `grep -c 'v2\.' research.md` = 3 (≥ 1).
- `grep -c 'expected_savings_tokens' research.md` = 2 (≥ 1).

### R8 — cortex-command docs updated [MUST]: PASS
- `grep -c 'cortex-command-plugins' docs/skills-reference.md` = 4 (≥ 1).
- `grep -c 'install all six or none' docs/setup.md` = 0.
- `ls docs/ui-tooling.md` is empty (deleted).
- `grep -cE '\[.*\]\(ui-tooling\.md\)' docs/agentic-layer.md` = 0.
- `docs/dashboard.md` explicitly calls out the plugin requirement for `ui-judge`/`ui-a11y` at lines 119–123.
- `docs/setup.md` rewrote the bundle section to "UI skills and pr-review (opt-in plugins)" with the marketplace URL.

### R9 — Frontmatter validation in new repo [MUST]: PASS
- `python3 scripts/validate-skill.py plugins/cortex-ui-extras/skills` exits 0 (6 skills, 0 errors, 3 pre-existing unused-input warnings that do not fail the run).
- `.github/workflows/validate.yml` runs validate-skill.py on push and pull_request against both plugin skill trees.

### R10 — Post-move guard against FS-probe reintroduction [SHOULD]: PASS
- `validate.yml` includes a "Probe guard" step that `grep`s for `~/.claude/skills/ui-` in `plugins/cortex-ui-extras/skills/ui-check/SKILL.md` and exits non-zero if found. Returns zero matches on the clean file today.

## Stage 2: Code Quality

- **Naming**: Plugin names (`cortex-ui-extras`, `cortex-pr-review`) match the `cortex-*` project prefix. File layout (`plugins/<name>/skills/<skill>/SKILL.md`) mirrors cortex-command's own `skills/` convention. Consistent.
- **Error handling**: `validate-skill.py` separates errors/warnings/infos, exits 1 only on errors, and prints a clear usage message on bad args. The GitHub Actions probe guard is a simple `grep ... || exit 1` — minimal and clear.
- **Test coverage**: R9 acceptance command executed live (exits 0 with expected skill count); R10 guard logic verified against current file. All R1–R8 acceptance commands executed against the actual filesystem.
- **Pattern consistency**: `validate-skill.py` reuses the SKILL.md frontmatter contract conventions (`inputs`, `outputs`, `preconditions`, `{{variable}}` templating) that already exist in cortex-command. The marketplace.json schema follows Claude Code's official plugin marketplace format. Docs cross-link to the plugin repo via full GitHub URLs — consistent with how cortex-command already references external docs.

Minor observation (non-blocking): The 3 "inputs declares unused variables" warnings in `ui-brief`, `ui-check`, `ui-judge` were present in the original skills before extraction — not regressions. No action required for this lifecycle.

## Requirements Drift

**State**: no drift detected.

**Findings**: The implementation narrows, rather than expands, the cortex-command project surface: seven optional skills moved to an external plugin repo, one skill (harness-review) demoted to project-local scope. This directly advances the project's stated quality attributes:
- **Maintainability through simplicity** (trimming the skill inventory)
- **Context efficiency** (smaller default skill surface = fewer description tokens loaded per session)
- **Complexity must earn its place** (optional features are now opt-in via plugin install)

The new cortex-command-plugins repo is a sibling project, consistent with the existing project boundary statement that "Application code or libraries belong in their own repos." No new behaviors introduced in cortex-command that aren't already covered by requirements/project.md.

**Update needed**: no.
