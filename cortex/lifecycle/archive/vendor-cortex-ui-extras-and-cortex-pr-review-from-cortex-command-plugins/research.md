# Research: Vendor cortex-ui-extras and cortex-pr-review from cortex-command-plugins

## Epic Reference

This ticket scopes from epic `research/overnight-layer-distribution/research.md`. The epic's DR-9 recommended keeping `cortex-command-plugins` separate as an extras marketplace; this ticket supersedes that decision for the `cortex-ui-extras`+`cortex-pr-review` subset only — `android-dev-extras` stays external. The epic's DR-2 pre-classifies future `cortex-overnight-integration` (ticket 121) as build-output. The dual-source drift contract inherited from ticket 120 Task 15 is the constraint this ticket must parameterize. See the epic for broader distribution context; this ticket's concern is narrow: mechanics of vendoring two plugins + expressing a per-plugin policy across build recipe, pre-commit hook, and drift tests.

## Codebase Analysis

### Current build-plugin recipe (`justfile` lines 395–404)

Hardcoded to `cortex-interactive` via a bash SKILLS array of 15 skill names. Performs 3 rsync operations per build:

1. `rsync -a --delete "skills/$s/" "plugins/cortex-interactive/skills/$s/"` — loop over SKILLS array
2. `rsync -a --delete --include='cortex-*' --exclude='*' bin/ plugins/cortex-interactive/bin/` — `cortex-*` executables only (7 scripts)
3. `rsync -a hooks/cortex-validate-commit.sh plugins/cortex-interactive/hooks/cortex-validate-commit.sh`

The `--delete` flag makes plugin tree a clean reflection of sources. Today's policy contract: exactly one build-output plugin.

### Current drift hook (`.githooks/pre-commit` lines 1–37)

Runs `just build-plugin`, then `git diff --quiet plugins/cortex-interactive/`. Exits 1 with `git diff --name-only` output if drift detected. Dual-source contract documented in the hook's header comment (lines 2–9). No differentiation between build-output and hand-maintained plugins — treats the entire `plugins/cortex-interactive/` tree as build-output.

### Current drift tests (`tests/test_drift_enforcement.sh` lines 1–113)

Two positive subtests:
- **Subtest A**: append HTML comment to `skills/commit/SKILL.md`, assert hook exits non-zero and mentions the file.
- **Subtest B**: append shell comment to `hooks/cortex-validate-commit.sh`, assert hook exits non-zero.

Uses EXIT trap calling `restore_all()` — invokes `git restore` on seeded paths and rebuilds. No negative subtests.

### External plugins being vendored

From `~/Workspaces/cortex-command-plugins/plugins/`:

- **cortex-ui-extras** (9 files): 6 skills (`ui-a11y`, `ui-brief`, `ui-check`, `ui-judge`, `ui-lint`, `ui-setup`), 2 reference templates under `ui-brief/references/`, 1 minimal `.claude-plugin/plugin.json` (33 bytes, `name` only). All files 644-mode. No hooks, no bin scripts, no executables.
- **cortex-pr-review** (6 files): 1 skill (`pr-review`) with 3 reference docs (protocol.md 31K, rubric.md 8.2K, output-format.md 6.1K) and **one executable at `skills/pr-review/scripts/evidence-ground.sh` (755-mode, 18K)**. Minimal `.claude-plugin/plugin.json` (33 bytes). Mode preservation is critical — the script is invoked between reviewer subagents and the synthesizer.

### Existing `plugins/cortex-interactive/` shape

Rich `plugin.json` (name + description + author). Directory layout: `skills/`, `bin/` (7 cortex-* executables), `hooks/` (executable scripts + `hooks.json` manifest). Convention: markdown/JSON 644, executable scripts 755.

### "Experimental" labeling precedent

None found. No `experimental`/`beta`/`alpha` in README.md, CLAUDE.md, plugin.json files, or skill frontmatter. The core vs optional distinction today lives in narrative (README points to separate cortex-command-plugins repo), not metadata.

### README.md plugin story

Lines 92–110 describe optional plugins via the companion repo. Installation instructions (85–88) only cover `cortex-interactive`. Change points: move ui-extras+pr-review from "external" to "in-tree optional", document the four-plugin roster, add experimental marker for ui-extras.

### Files that will change

1. `justfile` — build-plugin recipe parameterization
2. `.githooks/pre-commit` — drift scope filtered to build-output plugins only
3. `tests/test_drift_enforcement.sh` — add negative subtests for hand-maintained plugins
4. `plugins/cortex-ui-extras/` (new) — vendored from sibling repo
5. `plugins/cortex-pr-review/` (new) — vendored from sibling repo (preserve evidence-ground.sh 755)
6. `README.md` — four-plugin roster, core/extras framing, experimental marker for ui-extras
7. Sibling repo `cortex-command-plugins` — delete the two vendored plugin directories (follow-up commit, not in this repo's diff)

## Web Research

- **Vendoring idiom** — `git subtree add --squash` is the canonical one-commit import that retains an upstream-sync escape hatch ([Atlassian subtree tutorial](https://www.atlassian.com/git/tutorials/git-subtree)). User explicitly chose raw copy instead — trades away the escape hatch and `git log --follow` across the move boundary, in exchange for simpler semantics and one fewer tool.
- **Generated-vs-source terminology** — GitHub's `linguist-generated` attribute ([linguist overrides](https://github.com/github-linguist/linguist/blob/main/docs/overrides.md)) is the established per-directory marker; primarily a GitHub-UI hint (collapses diffs) rather than a machine-readable policy. CODEOWNERS is the analogous per-directory ownership file. No industry-standard "per-plugin build policy" manifest pattern — closest analogs are `.gitattributes` or a CODEOWNERS-style file.
- **Pre-commit drift patterns** — `pre-commit` framework ([pre-commit.com](https://pre-commit.com/)) idiom: run generator, then `git diff --exit-code <scope>`. Scoping per-directory is the standard answer to "some dirs are generated, others aren't."
- **Claude Code plugins** — Official plugin schema at `.claude-plugin/plugin.json` has no first-class `experimental` or `beta` field ([Claude Code plugin marketplaces docs](https://code.claude.com/docs/en/plugin-marketplaces)). Community convention: README badge + description-prefix (e.g., `"description": "[Experimental] ..."`). Working multi-plugin monorepo example: [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official).
- **Deprecation/move-to-other-repo** — Apache Cordova's [deprecation.md template](https://github.com/apache/cordova-contribute/blob/master/deprecation.md) is the most-cited convention: README block + repo-description prefix pointing to the new canonical location. "Land then delete" across the two repos avoids gap windows for users.
- **Anti-patterns identified** — running drift checks uniformly across all plugins when some are hand-maintained trains contributors to bypass the hook via false positives (web consensus). Using `git subtree` without `--squash` for vendor-only (non-co-dev) imports pollutes log with sibling history.

## Requirements & Constraints

### From `requirements/project.md`

- **Simplicity principle** (line 19): "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct." — constrains policy-expression choices toward minimal new config surface.
- **File-based state** (lines 25–34): "Lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files (markdown, JSON, YAML frontmatter). No database or server." — if per-plugin policy becomes file-based, it must follow this pattern.
- **Plugin distribution is in scope** — the repo is mid-migration to plugin-based distribution (epic 113); this ticket's vendoring work aligns.

### From epic `research/overnight-layer-distribution/research.md`

- **DR-2**: two plugins split at runner boundary (`cortex-interactive` + `cortex-overnight-integration`). Both pre-classified as build-output.
- **DR-9**: cortex-command-plugins kept as extras marketplace — superseded by ticket 144 for ui-extras+pr-review subset per explicit user decision.
- **Plugin tier depends on CLI tier**: plugins promise modular *enablement* (pick interactive-only or add overnight), not modular *install*. CLI is always required. Relevant context: vendored plugins don't need Python modules from this repo — they're pure-skill / shell-script plugins.

### From CLAUDE.md + ticket 120

- Dual-source drift pre-commit hook enabled by `just setup-githooks`. Today's contract: top-level `skills/`, `bin/cortex-*`, `hooks/cortex-validate-commit.sh` are canonical; `plugins/cortex-interactive/` is build output.
- Ticket 144 introduces the per-plugin policy concept that parameterizes this inherited contract.

### Scope boundaries (ticket 144 body)

Explicitly out of scope: marketplace manifest publishing (ticket 122), retirement of cortex-command-plugins repo (keeps android-dev-extras), migration guide (ticket 124), cortex-overnight-integration plugin (ticket 121), vendoring android-dev-extras (stays external).

### Ticket 121 stance

DR-2 pre-classifies `cortex-overnight-integration` as build-output (runner-only hooks + overnight skill sourced from top-level). Ticket 144 must decide whether to pre-register that name in the build-output list (adversarial flagged this as front-running 121's design).

## Tradeoffs & Alternatives

### Tradeoff 1: Per-plugin policy expression

- **(a) Inline bash arrays in `justfile`** (`BUILD_OUTPUT_PLUGINS=(cortex-interactive)`, `HAND_MAINTAINED_PLUGINS=(cortex-ui-extras cortex-pr-review)`) — immediate visibility, matches existing SKILLS array pattern, no new file types. Con: hook must either grep justfile (fragile) or call `just list-plugin-policy` sub-recipe (doubles startup cost, fails opaquely if any unrelated recipe has a syntax error).
- **(b) Separate policy file** (`plugins/POLICY` — two labeled sections, plain text parseable by both `just` and bash) — decouples hook from justfile parsing; single source of truth; trivial shell parser. Con: introduces a new config file type in a repo that otherwise uses justfile + bash; minor "where does this live" cognitive cost.
- **(c) Per-plugin marker file** (`.hand-maintained` sentinel in each hand-maintained plugin dir) — self-documenting, colocated. Con: verbose; unclear default when no marker is present; easy to forget during vendoring.
- **(d) `.gitattributes linguist-generated`** — standard GitHub convention. Con: primarily a diff-collapse hint, not a policy mechanism; awkward inversion (you'd flag generated to exclude from drift, but the attribute reads "this is generated," not "check this for drift"); `.gitattributes` doesn't exist in this repo today.
- **(e) Naming convention** — e.g., "plugins with a corresponding top-level `skills/{name}/` dir are build-output." Con: brittle; confusing when `skills/commit/` exists but `cortex-interactive` is the plugin name; no clean way to encode cortex-overnight-integration's future addition.

**Initial recommendation**: (a) for minimal footprint. **Adversarial counter** (see below): the justfile-grepping fragility is underweighted. Revised recommendation: **(b) `plugins/POLICY`** — a tiny two-section plain-text file, parsed by a trivial `grep`/`cut` in the hook and a similar helper function in justfile. One extra file; decouples cross-tool concerns. This is flagged as an open question for the spec phase.

### Tradeoff 2: `just build-plugin` recipe shape

- **(a) Single recipe, loop internally** — `build-plugin` iterates over BUILD_OUTPUT_PLUGINS (however it's expressed per Tradeoff 1), rsyncs each plugin's sources. Hand-maintained plugins not in the loop.
- **(b) Split into per-plugin recipes** — `just build-cortex-interactive`, future `just build-cortex-overnight-integration`; no recipe for hand-maintained plugins. Con: breaks the single `just build-plugin` entry point the pre-commit hook calls.
- **(c) Parameterized recipe** — `just build-plugin <name>` that errors if name is hand-maintained or unknown. Con: changes CLI; pre-commit hook must iterate and call multiple times.

**Recommended**: **(a)** — minimal change to existing pattern. When ticket 121 lands, it adds its skills to a second inner loop or expands BUILD_OUTPUT_PLUGINS.

### Tradeoff 3: Drift-enforcement scoping in `.githooks/pre-commit`

- **(a) Iterate policy list, diff each path** — loop BUILD_OUTPUT_PLUGINS, run `git diff --quiet plugins/{name}/` per plugin. Precise; easy to debug.
- **(b) Single diff with pathspec excludes** — one `git diff --quiet plugins/ -- :(exclude)plugins/cortex-ui-extras ...`. Simpler one-liner but excludes must stay in lock-step with the policy list (duplication risk).
- **(c) Filter via `.gitattributes`** — only if Tradeoff 1 chose (d).

**Recommended**: **(a)** — aligns with Tradeoff 1 recommendation and keeps the drift check local per plugin.

### Tradeoff 4: Vendor-copy mechanics

- **(a) `rsync -a` or `cp -a`** — preserves 755 on `evidence-ground.sh` natively; matches existing `build-plugin` pattern.
- **(b) `git show` per file / `git cat-file`** — overcomplicated for one-time vendor.
- **(c) Plain `cp -R` + explicit `chmod`** — fragile; must enumerate executables.

**Recommended**: **(a) `rsync -a`** — matches existing usage; one-line invocation per plugin directory.

## Adversarial Review

The adversarial pass identified 14 concerns. The highest-priority findings, condensed:

1. **Hook cost scaling is real**: current hook runs `just build-plugin` (17 rsyncs) on every commit, including commits that touch only `backlog/` or `docs/`. Parameterization doesn't fix this. Consider a short-circuit that inspects `git diff --cached --name-only` and skips the build if no top-level source paths are staged. Flagged as potential spec scope.
2. **Policy coupling via grepping is fragile**: hook greps justfile → brittle against format changes; alternatively calls a sub-recipe → doubles startup cost, fails opaquely on unrelated recipe errors. Motivates Tradeoff 1 alternative (b) — a plain `plugins/POLICY` file parsed identically by both tools.
3. **Default-hand-maintained is unsafe**: if a contributor adds `plugins/foo/` without classifying, drift detection silently passes forever. Recommend fail-closed: hook enumerates `plugins/*/` and errors on any directory not in either policy list.
4. **Test cleanup can destroy real uncommitted work**: existing `git restore` in tests wipes edits. Extending this to hand-maintained plugins amplifies risk. Use `git stash push -- <paths>` / `git stash pop` or pre-flight dirty-check.
5. **`/plugin install` mode bits**: Claude Code likely `git clone`s, preserving the executable bit in Git's single x-bit slot — `evidence-ground.sh` should survive. But a tarball/ZIP install path drops modes. Mitigation: SKILL.md invokes the script as `bash scripts/evidence-ground.sh` rather than relying on the executable bit.
6. **Land-then-delete sequencing**: if vendor commit is reverted after external deletion, plugins disappear from both repos. Delete external copies only after vendor commit has settled AND ticket 122's manifest lists the in-repo copies.
7. **Ticket 122 ordering**: between 144 landing and 122 landing, the in-repo plugins aren't listed in any marketplace manifest. Not a user regression (old marketplace still works for old users) but an intermediate no-one-can-find state.
8. **Front-running ticket 121**: pre-classifying `cortex-overnight-integration` as build-output in 144's policy list usurps 121's design. Recommendation: leave 121 off both lists until it's written; combined with fail-closed default (#3), this forces 121 to classify itself.
9. **Hand-maintained == zero validation** is too weak: a malformed `plugin.json` (missing `name`) breaks the plugin silently. Add a cheap `jq -e .name` check for every `plugins/*/plugin.json` regardless of tier.
10. **`evidence-ground.sh` is 18K unreviewed executable shell**: vendoring makes this repo's maintainer responsible for it. Cheap insurance: `shellcheck` + manual read before the vendor commit.
11. **README badge is durability-fragile**: "experimental" in README only is documentation; a refactor can drop it. Nothing prevents adding `"experimental": true` as a custom key in `plugin.json` (Claude Code ignores unknown keys) — provides machine-readable intent at zero cost.
12. **Minor concerns**: `git blame`/`git log --follow` break at vendor boundary (acceptable per user choice, flag once); bash-array portability is fine given explicit bash shebangs.

### Recommended mitigations (highest-priority)

1. Fail-closed on unclassified `plugins/*/` directories.
2. Use `git stash push -- <paths>` in drift tests, not unconditional `git restore`.
3. Extract policy to a single plain file both justfile and hook read (Tradeoff 1 alternative b).
4. Add `jq -e .name` validation to the hook for every `plugins/*/plugin.json`.
5. Add a "staged diff touches top-level sources" short-circuit to keep pre-commit cost sublinear in common commits — or defer to a follow-up ticket.
6. Omit `cortex-overnight-integration` from both policy lists until ticket 121 lands.
7. `shellcheck` + manual read of `evidence-ground.sh` before committing the vendor.
8. Consider adding `"experimental": true` to `plugins/cortex-ui-extras/.claude-plugin/plugin.json` in addition to the README badge.

## Open Questions

1. **Policy-file location**: Tradeoff 1 (a) inline justfile arrays vs (b) standalone `plugins/POLICY` file. Initial recommendation was (a) for minimal footprint; adversarial argued (b) is safer against cross-tool grepping fragility. **Defer to Spec**: pick one and document the rationale.
2. **Fail-closed vs fail-open default**: should the hook error when `plugins/*/` contains a directory not in either BUILD_OUTPUT or HAND_MAINTAINED list? Recommend yes (per adversarial #3). **Defer to Spec**: confirm.
3. **Ticket 121 pre-registration**: should 144's policy list include `cortex-overnight-integration` in anticipation, or leave it unclassified so 121 must self-register? Adversarial argued the latter. **Defer to Spec**: decide.
4. **Pre-commit hook short-circuit**: should the hook inspect staged paths and skip the build when no top-level sources are touched? Adversarial flagged cost scaling; could be in-scope or deferred. **Defer to Spec**: decide in-scope or punt to a follow-up ticket.
5. **Hand-maintained plugin.json validation**: should the hook run `jq -e .name` on every `plugins/*/plugin.json` regardless of classification? Cheap insurance per adversarial #9. **Defer to Spec**: confirm.
6. **`"experimental": true` custom plugin.json key**: in addition to README badge, should `plugins/cortex-ui-extras/.claude-plugin/plugin.json` carry a custom `"experimental": true` key? Adversarial argued zero-cost machine-readable intent. **Defer to Spec**: decide.
7. **Fleshing out vendored plugin.json**: external plugins today have name-only plugin.json (33 bytes). Should the vendored copies gain `description` and `author` to match cortex-interactive? If so, what description is authoritative? **Defer to Spec**: propose values or mark as follow-up cleanup.
8. **`evidence-ground.sh` invocation style**: SKILL.md should invoke it as `bash scripts/evidence-ground.sh` vs relying on the x-bit — more portable across install paths. **Defer to Spec**: decide whether this ticket adjusts the SKILL.md invocation or leaves it untouched (scope creep vs resilience).
