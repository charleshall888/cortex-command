# Research: Extend `/setup-merge` with dynamic per-component opt-in for skills and hooks

Backlog item: `064-extend-setup-merge-with-dynamic-per-component-opt-in-for-skills-and-hooks`
Epic: `063-user-configurable-setup-per-component-opt-in-and-per-repo-permissions-scoping`
Discovery source: `research/user-configurable-setup/research.md` (background context only)
Tier / criticality: complex / high

## Codebase Analysis

### Files that will change

**Primary surfaces:**

- `.claude/skills/setup-merge/SKILL.md` — current `detect` → prompt → `merge` flow to extend with per-component skills/hooks prompts and install-floor handling. Prompt style today: plain `[Y/n]` text prompts, not `AskUserQuestion`.
- `.claude/skills/setup-merge/scripts/merge_settings.py` — helper script to extend with:
  - a new discovery routine covering `skills/*/SKILL.md` + both hook directories (currently only walks `hooks/cortex-*`, NOT `claude/hooks/` at all — existing gap)
  - a `lifecycle.config.md` YAML-frontmatter reader/writer (no PyYAML import currently exists in the repo)
  - install-floor classification (existing constants `REQUIRED_HOOK_SCRIPTS` — 9 hooks, and `OPTIONAL_HOOK_SCRIPTS` — 3 hooks — diverge from research Band C which is only 3 hooks)
  - new `detect` output fields for discovered skills/hooks and existing lifecycle.config.md state
  - new `merge` command behavior for the skills/hooks write-back
- `justfile` — `deploy-bin` recipe (L122-176) to gate bin utilities on lifecycle.config.md state. Only three bin utilities are actually skill-scoped today: `overnight-start`, `overnight-status`, `overnight-schedule` (`overnight-*` prefix). Everything else is skill-agnostic or Band C floor.
- `lifecycle.config.md` — repo-root config to receive new top-level `skills:` and `hooks:` sections (via setup-merge writes, not hand edits).
- `skills/lifecycle/assets/lifecycle.config.md` — template to gain commented-out examples of the new sections.

**Supporting surfaces that may need changes:**

- `justfile` `setup-force` recipe (L37-118) — has a hardcoded parallel install list that **already diverges** from `deploy-bin` (e.g., `setup-force` omits `overnight-status` and `git-sync-rebase.sh`). Spec phase must decide: include in scope, defer, or explicitly document as a "nuclear reinstall" escape hatch that bypasses lifecycle.config.md.
- `justfile` `deploy-skills` (L224-261) and `deploy-hooks` (L264-331) — purely additive symlink loops today. Spec phase must decide whether they also respect selections on re-run.
- `claude/settings.json` — hook registrations at L239 (`cortex-setup-gpg-sandbox-home.sh`), L279/L297 (`~/.claude/notify.sh`), and L333/L343 (worktree hooks using `$CWD/claude/hooks/...`) create split between hook registration and hook symlink presence — see Adversarial findings.

### Relevant existing patterns

- **Dynamic discovery template** — `discover_symlinks()` in `merge_settings.py` (L94-185) already walks `skills/*/` filtered by `SKILL.md` presence (L130-131). This is exactly the discovery rule the ticket proposes and needs no new work for skills. The hooks side needs extension.
- **Install-floor-silent / optional-prompted pattern** — SKILL.md Step 5a merges required hooks unconditionally; Step 5b prompts for optional hooks individually with `[Y/n]`. The new per-component skill/hook prompts mirror this split.
- **Atomic write pattern** — mtime-guarded tempfile + fsync + os.replace (merge_settings.py L636-690). Any lifecycle.config.md write must use this pattern; currently nothing writes to lifecycle.config.md so the guard does not exist yet.
- **Detect tempfile flow** — `detect` writes a JSON state file to a tempfile path and returns the path on stdout; SKILL.md parses the tempfile, runs prompts, tracks approvals; `merge` consumes tempfile + approval flags and writes atomically. The lifecycle.config.md write-back plugs into this flow as a second atomic write inside `merge`.
- **Plain `[Y/n]` prompts** — No `AskUserQuestion` usage in setup-merge. Per-component prompts must fit the existing conversational markdown idiom.

### Integration points and dependencies

- **setup-merge ↔ justfile**: Today there is zero shared state. The ticket introduces a new edge: `deploy-bin` (and possibly `deploy-skills`, `deploy-hooks`) must read `lifecycle.config.md`. The justfile currently has no YAML parser — teaching `deploy-bin` to parse YAML frontmatter in bash is non-trivial.
- **setup-merge ↔ lifecycle.config.md**: Today there is zero reference. The ticket introduces a new write path; existing fields (`type`, `test-command`, `commit-artifacts`, `skip-specify`, `skip-review`, `default-tier`, `default-criticality`) and the free-form review-criteria body must be preserved.
- **Phase readers ↔ new frontmatter keys**: All six lifecycle.config.md readers (`skills/lifecycle/SKILL.md`, `skills/lifecycle/references/{research,specify,plan,complete}.md`, `skills/critical-review/SKILL.md`) are LLM-based — they read the file as prose and pattern-match on known keys (`test-command:`, `type:`, `commit-artifacts:`). None are strict schema validators. Unknown top-level keys (`skills:`, `hooks:`) will not break any current reader.
- **Band C classification → setup-merge**: Band C membership cannot be inferred from filesystem listings; it must live somewhere setup-merge can read. Candidates: a Python constant in merge_settings.py (existing pattern, current `REQUIRED_HOOK_SCRIPTS` is broader than Band C and must be narrowed/reconciled), per-component frontmatter flag (clean but 39-file migration), or a shared classification table in setup-merge/SKILL.md (drift surface).

### Conventions to follow

- No new config files (DR-2) — everything lands in `lifecycle.config.md`.
- Dynamic discovery, not curated manifest — walk filesystem at prompt time.
- Install floor merged unconditionally and silently (matches Step 5a pattern).
- Atomic writes with mtime guards (merge_settings.py L636-690 pattern).
- Plain `[Y/n]` prompts, not `AskUserQuestion`.
- Cluster groupings are display-only per DR-3; never persisted as identifiers.
- Never skip the `/commit` skill for git operations.

### Hook inventory (every file by name + extension)

**`hooks/`** (5 files, all `.sh`, all `cortex-*`):

- `cortex-cleanup-session.sh`
- `cortex-notify-remote.sh`
- `cortex-notify.sh` — symlinked to `~/.claude/notify.sh` (not `~/.claude/hooks/`)
- `cortex-scan-lifecycle.sh`
- `cortex-validate-commit.sh` (Band C)

**`claude/hooks/`** (11 files, mixed extensions):

- `bell.ps1` — NOT a hook (Windows bell asset)
- `cortex-output-filter.sh`
- `cortex-permission-audit-log.sh`
- `cortex-setup-gpg-sandbox-home.sh`
- `cortex-skill-edit-advisor.sh`
- `cortex-sync-permissions.py` — **Band C floor, Python, not shell**
- `cortex-tool-failure-tracker.sh`
- `cortex-worktree-create.sh`
- `cortex-worktree-remove.sh`
- `output-filters.conf` — NOT a hook (config file consumed by cortex-output-filter.sh)
- `setup-github-pat.sh` — NOT in deploy-hooks; installed via manual `ln -s` per justfile:507

**Verdict on discovery rule**: the ticket's proposed `*.sh` pattern MISSES `cortex-sync-permissions.py` (Band C) and may surface junk files (`bell.ps1`, `output-filters.conf`, `setup-github-pat.sh`). Recommended rule: `cortex-*` prefix across both `hooks/` and `claude/hooks/`. This filters the three non-hook files naturally and picks up `.py` and `.sh` alike.

### Phase reader audit — lifecycle.config.md

All six readers are LLM-based pattern-matches, not schema parsers:

| Reader | Parse approach | Keys consulted |
|---|---|---|
| `skills/lifecycle/SKILL.md:29` | LLM reads, looks for known keys | general context |
| `skills/lifecycle/references/research.md:195` | LLM reads as prose | `commit-artifacts` |
| `skills/lifecycle/references/specify.md:9,173` | LLM reads as prose | `commit-artifacts` + general context |
| `skills/lifecycle/references/plan.md:12,260` | LLM reads as prose | `commit-artifacts` |
| `skills/lifecycle/references/complete.md:9-13,78` | LLM reads, conditional on `test-command` presence | `test-command`, `commit-artifacts` |
| `skills/critical-review/SKILL.md:21-22` | LLM scans for `type:` (commented-out check) | `type` |

None of these break on unknown `skills:` / `hooks:` top-level keys today. **However**: see Adversarial findings for tokens-per-read and future-phase risks.

`backlog/update_item.py` has regex-based frontmatter parsing (L51-99) that only supports scalar values, but it is **only** called on backlog items, never on `lifecycle.config.md`. Verified by grep.

### Bin utility mapping

Only three bin utilities are skill-scoped-and-optional: the `overnight-*` trio. Everything else is skill-agnostic or Band C floor.

| bin utility | scoped to skill | deploy-bin behavior when skill opted out |
|---|---|---|
| `audit-doc` | none | always deploy |
| `count-tokens` | none | always deploy |
| `git-sync-rebase.sh` | none | always deploy |
| `jcc` | none (repo helper) | always deploy |
| `overnight-start` | `overnight` | skip if overnight not selected |
| `overnight-status` | `overnight` | skip if overnight not selected |
| `overnight-schedule` | `overnight` | skip if overnight not selected |
| `update-item` | `backlog` (Band C) | always deploy |
| `create-backlog-item` | `backlog` (Band C) | always deploy |
| `generate-backlog-index` | `backlog` (Band C) | always deploy |

The skill-to-bin mapping is small enough that a single rule ("bins matching `overnight-*` belong to `overnight` skill") covers everything today. The convention will need a small extension each time a new skill gains dedicated bin utilities.

## Web Research

### Prior art — dynamic discovery + explicit activation

- **Oh My Zsh** is the closest structural match: plugins are auto-discovered in `$ZSH/plugins` via `is_plugin()` (filesystem scan), but a plugin only loads when listed in `plugins=(...)` in `.zshrc`. Discovery dynamic, activation explicit, selections persisted to a hand-edited file.
- **Claude Code skills (native)** have no setup merge flow. Skills live at three scopes (`~/.claude/skills/`, `.claude/skills/`, plugin-provided) and are filesystem-discovered automatically. Enable/disable happens via permission rules and per-skill frontmatter (`disable-model-invocation`, `user-invocable`). No "pick which skills to install" step exists.
- **`alirezarezvani/claude-skills`** (community) offers three install granularities via CLI: universal, bundle-by-domain, individual. Direct copy, no merge, supports `--dry-run`, re-select by re-running.
- **chezmoi** uses `.chezmoiignore` as a negative opt-out list (templated). Source tree is the authoritative manifest; ignore patterns carve out exclusions. Excludes beat includes.
- **Brewfile** is the closest CLI verb vocabulary: `install`, `add`, `remove`, `dump` (reflect current state into manifest), `check` (drift), `cleanup` (remove anything not in manifest). `brew bundle cleanup` + autoremove (Homebrew issue #21350) is cited as the anti-pattern for silent destructive sync.
- **mise, ESLint, tmux TPM, lazy.nvim, Prettier**: explicit-manifest-dominant. Oh My Zsh is the only widely-used tool with dynamic discovery as the enumerator — and even it requires explicit activation.

### YAML frontmatter as a config surface

Rare-but-idiomatic-within-cortex-command. Jekyll, Hugo, MDX, Obsidian use frontmatter for metadata *about the document*, not configuration of the surrounding system. Claude Code's own skill frontmatter (`disable-model-invocation`, `allowed-tools`, `paths`, `hooks`) is the strongest precedent and is already inside the project's idiom. Unknown-keys handling across Jekyll/Hugo/Obsidian is permissive by default; strict schema validation is opt-in.

### Install floor / required modules — idioms

- **Debian**: `Essential: yes` (separate boolean from `Priority: required`). Two-tier.
- **npm `peerDependencies`**, **Homebrew `depends_on`**, **pacman groups**: per-component declaration.
- **lazy.nvim `cond = function()`**, **chezmoi `.chezmoiignore` template**: runtime-evaluated inclusion.

Consistent idiom: a per-component flag evaluated at selection time. Cortex-command's decision to keep Band C as a separate list (in research or in setup-merge) deviates from this convention for pragmatic reasons (small stable set, 39-file migration cost for per-component frontmatter).

### Context cost argument — unique to Claude Code skills

Each Claude Code skill costs ~100 tokens of metadata at startup (SKILL.md frontmatter always loads). A large skill collection installed whole directly consumes context the user never wanted. **This is the strongest value case for the epic** and is unique to Claude Code — it did not exist in zsh/tmux analogs. It is the concrete motivation for per-component opt-in beyond "some users want less clutter."

### `CLAUDE_CONFIG_DIR` status

- **Undocumented in official docs** (as of search date 2026-04-10).
- **Partially working**: relocates `.claude.json`, credentials, `projects/`, `shell-snapshots/`, `statsig/`, `todos/`. Does NOT affect project-local `.claude/` dirs or `settings.local.json`.
- **GitHub issue #3833** closed as `NOT_PLANNED` without explanation.
- **GitHub issue #25762** open with 23 upvotes, no Anthropic response.
- **Community working pattern**: SessionStart hook walks up from `$CLAUDE_PROJECT_DIR` to find `.envrc`, with git-worktree fallbacks (eshaham gist). Needed because Claude Code runs each Bash command in a fresh shell, defeating direnv's standard shell hook.

Implication: #065's direnv pattern is real and working, but `CLAUDE_CONFIG_DIR` behavior is only documented by bug reports. #064 must not rely on undocumented behavior.

### Re-run idempotency patterns

Three observed patterns in prior art:

1. **Add-only** (most install scripts): re-running only adds; revocation is manual.
2. **Manifest + reconcile** (Brewfile, Ansible `state: absent`, Puppet): manifest is source of truth; `install`/`apply` brings system to match, including removing things not listed — usually gated behind explicit flag to avoid surprise deletion.
3. **Dump** (`brew bundle dump`): write current system reality into the manifest.

For #064, the safe pattern per DR-6 is (1) add-only. Re-run can surface drift but must not silently delete.

## Requirements & Constraints

### Requirements from `requirements/project.md`

- **"Complexity must earn its place"** (Philosophy of Work § Complexity) — constrains every new layer. The decompose summary explicitly invokes this principle.
- **"Tests pass and the feature works as specced. ROI matters"** (Quality bar) — supports deferring `cortex-doctor`, shadow generator, Band B resolver.
- **File-based state constraint** (Architectural Constraints) — "plain files (markdown, JSON, YAML frontmatter). No database or server." Honored by writing selections to `lifecycle.config.md` frontmatter.
- **"Maintainability through simplicity"** (Quality Attributes) — supports DR-2's refusal of a new config file and dynamic discovery over curated manifest.
- **"Defense-in-depth for permissions"** (Quality Attributes) — **critical intersection**. `cortex-sync-permissions.py` is Band C specifically because it merges global permissions into project `.claude/settings.local.json` at SessionStart. It is a workaround for Claude Code bug #17017. The global allow/deny list is "the sole enforcement layer" for sandbox-excluded commands; opting out of this hook silently breaks the enforcement model.
- **"Global agent configuration (settings, hooks, reference docs)"** (Project Boundaries § In Scope) — `/setup-merge` extension is clearly in scope.
- **"Setup automation for new machines (owned by machine-config)"** (Project Boundaries § Out of Scope) — boundary tension: #064 extends setup for cortex-command components only, not machine provisioning.

### Decision records (from `research/user-configurable-setup/research.md`)

- **DR-1** (per-repo permission override uses `CLAUDE_CONFIG_DIR`, not settings mutation): primarily #065's concern. Constrains #064 to NOT introduce runtime mutation hooks for per-repo disable.
- **DR-2** (reuse `lifecycle.config.md`, do not add a new config file): **primary constraint**. Selections land in the existing file as new top-level YAML frontmatter sections. New sections must be ignored by existing phase readers. File rename cost is explicitly accepted.
- **DR-3** (no named bundles, per-component enable is the unit): **primary constraint**. Cluster groupings in UI must be display-only, never persisted as bundle identifiers.
- **DR-4** (install-time selection for skills/hooks, via `/setup-merge`): **primary constraint**. Runtime self-exit guards for hooks are deferred (out of scope). Per-repo hook disable routes to `CLAUDE_CONFIG_DIR` shadow.
- **DR-5** (independently shippable tickets, no phased rollout, no schema commitments that force rework): #064 and #065 are independently shippable. #064's schema additions must not pre-commit the design space for a future `permissions:` section.
- **DR-6** (non-destructive): **primary constraint**. `enable: false` does NOT uninstall. Re-run is strictly additive. This creates tension with Success Signal #1 on re-runs — see Adversarial Review.
- **DR-7** (upstream activity audit gating #065): not in #064's dependency path.
- **DR-8** (Option D preserved-for-future-eyes): #064 must NOT introduce a SessionStart mutation hook under any name.

### Scope boundaries for #064

**In scope:**

- Extend `/setup-merge` with dynamic discovery of skills and hooks
- Per-component prompts grouped by cluster (display-only)
- Write selections to new top-level `skills:` and `hooks:` sections in `lifecycle.config.md`
- Unconditional Band C install-floor merge
- `deploy-bin` justfile extension to skip bin utilities scoped to opted-out skills
- Template update in `skills/lifecycle/assets/lifecycle.config.md`

**Out of scope:**

- Runtime opt-out for auto-invoked skills (`critical-review` `skip-review`)
- Band B dependency resolution
- New config files beyond `lifecycle.config.md`
- Named bundles
- SessionStart mutation hooks
- Runtime hook guards for per-repo disable
- `cortex-doctor` diagnostic CLI
- `bin/cortex-shadow-config` generator
- Uninstall semantics beyond "skip on fresh install"
- Per-repo permissions scoping (owned by #065)
- Upstream audit (owned by #065)

## Tradeoffs & Alternatives

The ticket carries implementation suggestions (dynamic filesystem scan, `*.sh` glob, top-level YAML sections, justfile YAML parsing, per-component cluster-grouped prompts). Per the refine skill's alternative-exploration requirement for complex/high-criticality tickets, the following dimensions were evaluated with explicit alternatives.

### Dimension 1 — Component discovery mechanism

- **Ticket (dynamic filesystem scan)**: zero drift, auto-surfaces new components, matches existing `discover_symlinks` pattern. Con: cluster labels, Band C membership, and prompt text cannot be inferred from directory listings — *something* has to own classification data.
- **A1 — Hand-curated `skills/components.yaml`**: explicit, greppable. Con: pure drift surface; two-file change per new skill; fails simplicity-earns-its-place.
- **A2 — Per-component frontmatter fields** (`install-floor: true`, `cluster: overnight`, `bin-utilities: [...]`): zero drift, metadata co-located with component, machine-readable for tests. Con: 39-file migration; hooks don't currently have frontmatter (would need header comment convention).
- **A3 — Dynamic scan + small classification table inside `/setup-merge`**: scan enumerates existence, classification table handles labels/bands/prompt text. Con: small drift surface when adding new skills — but scan surfaces uncategorized items loudly.

**Tradeoffs agent recommendation**: A3.
**Adversarial counter**: A3 is the same pattern `setup-force`'s hardcoded parallel list exhibits — drift will accumulate. A2 (per-component frontmatter) is the long-term correct answer despite migration cost; the comment-in-SKILL.md "see research §2" is the first thing to bit-rot.

**Spec decision needed**: A3 (pragmatic) vs A2 (canonical). The spec interview should ask.

### Dimension 2 — Selection storage

- **Ticket (top-level `skills:` / `hooks:` sections in `lifecycle.config.md`)**: DR-2 compliant, single file, committed, visible in git history.
- **B1 — New `.cortex/components.yaml`**: **explicitly ruled out by DR-2**.
- **B2 — Single flat `components:` key**: minimal schema churn but loses skills-vs-hooks distinction.
- **B3 — JSON sidecar**: simpler for justfile to parse but adds a new file (partial DR-2 violation).
- **B4 — `settings.json` under `cortex:` key**: cross-repo leakage, upstream schema conflict risk, DR-8 anti-pattern.

**Recommendation**: Ticket's approach.
**Adversarial counter**: `lifecycle.config.md` is committed to the repo, so per-user install state lands in git history and cross-user worktrees overwrite each other. `commit-artifacts: true` default will auto-stage selections on next `/commit`. This mixes project-shared config with per-user install state in one committed file — the spec phase should decide whether to use a user-scoped prefix (`user-skills:`, `user-hooks:`), move to `~/.claude/lifecycle.config.md`, or explicitly accept the tension.

**Spec decision needed**: accept tension (ticket default), use user-scoped prefix, or split to user-scope file.

### Dimension 3 — Prompt granularity

- **Ticket (per-component prompts grouped by cluster, display-only headers)**: maximum control, matches DR-3 intent.
- **C1 — Per-cluster drill-in** ("enable all / none / custom"): fewer top-level prompts.
- **C2 — Flat per-component list**: simplest UX, loses scannability.
- **C3 — Bulk enable/disable opt-out inversion**: default everything-enabled, hide the feature from users.
- **C4 — Hybrid per-cluster-first with drill-in**: fast path for bulk, full control on drill-in.

**Tradeoffs agent recommendation**: C4 (hybrid).
**Adversarial counter**: The "49 prompts is too many" friction number is not backed by research. Ticket's per-component prompts is 26 skills + 13 hooks = 39, not 49. `/setup-merge` is a plain `[Y/n]` markdown prompt skill, not a TUI — implementing "enable all / none / custom" requires the LLM to track state across 10+ conversational turns without losing the plot. The hybrid UX is not free; it is new skill-authoring complexity.

**Spec decision needed**: ticket's per-component (simple but friction-heavy), C4 hybrid (complex state-tracking), or an out-of-band approach (user edits a pasted YAML block) — see Adversarial mitigation.

### Dimension 4 — `deploy-bin` gating mechanism

- **Ticket (`deploy-bin` reads `lifecycle.config.md` directly)**: single source of truth. Con: **justfile has zero YAML parsers today**; teaching bash to parse YAML frontmatter is non-trivial and pulls dependencies (`yq`, or Python-with-PyYAML).
- **D1 — Derived allowlist** at `~/.claude/.cortex-bin-allowlist`: setup-merge emits a newline-delimited list, justfile greps. Justfile stays pure bash.
- **D2 — Per-skill install recipes** (`just install-overnight`): justfile stays bash-only but sprawls.
- **D3 — Python helper `bin/cortex-deploy`** called from thin justfile wrapper: matches existing `backlog/*.py` pattern; consolidates deploy-* recipes.

**Tradeoffs agent recommendation**: D1.
**Adversarial counter**: `~/.claude/.cortex-bin-allowlist` is a new attack surface with no signing, ownership check, or mtime validation. A stale or tampered file causes `deploy-bin` to trust bogus state. Not a blocker, but the spec must at least add mtime validation like the settings.json write path.

**Spec decision needed**: D1 (simple allowlist), D3 (Python helper — more work but cleaner), or the ticket's approach with an explicit decision on how the justfile parses YAML.

### Dimension 5 — Re-run behavior

- **Ticket + DR-6 (fresh-install-only, non-destructive)**: safe, matches brew-bundle-cleanup anti-pattern avoidance.
- **E1 — Re-run-to-opt-out (active symlink removal)**: matches user mental model. Violates DR-6.
- **E2 — Fresh-install-only + explicit `just uninstall-X` recipes**: honors DR-6, gives escape hatch. Uninstall recipes are already out of scope.
- **E3 — Fresh-install-only + prominent drift surfacing**: honors DR-6, educates users, no destructive action.

**Tradeoffs agent recommendation**: E3.
**Adversarial counter**: drift surfacing requires reading `~/.claude/skills/` filesystem state — exactly the coupling the ticket wanted to avoid. Success Signal #1 ("`ls ~/.claude/skills/` reflects only their selections") is only true on first install and silently stops working on re-run if a user opts out of something previously installed. The spec must either weaken Success Signal #1 to "after fresh install, `ls` reflects selections" or commit to drift surfacing (which has implementation cost).

**Spec decision needed**: weaken success signal, add drift surfacing, or accept silent re-run divergence.

### Dimension 6 — Band C classification source

- **F1 — Hardcoded list in `/setup-merge` with comment pointing to research §2**: one place to edit, alongside prompt text.
- **F2 — `install-floor: true` frontmatter on each SKILL.md / hook header**: co-located, machine-readable, zero drift. Con: 39-file migration.
- **F3 — Scrape from `research/user-configurable-setup/research.md`**: single source but fragile.
- **F4 — New `COMPONENTS.md` at repo root**: one file, but another surface for data one consumer reads.

**Tradeoffs agent recommendation**: F1.
**Adversarial counter**: F1 is the exact pattern `setup-force`'s hardcoded parallel list exhibits — which the decompose explicitly called out as a drift anti-pattern. Double standard. F2 is long-term correct. The existing Python constant `REQUIRED_HOOK_SCRIPTS` (9 hooks) and `OPTIONAL_HOOK_SCRIPTS` (3 hooks) diverge from research §2 Band C (3 hooks) today; any hardcoded approach inherits the reconciliation burden.

**Spec decision needed**: F1 (pragmatic, accept drift) vs F2 (canonical, pay migration cost). The decision should account for the existing `REQUIRED_HOOK_SCRIPTS` constant reconciliation regardless.

## Adversarial Review

The adversarial pass identified multiple existing latent bugs and architectural assumptions that the ticket would inherit or exacerbate without surfacing them.

### Failure modes

1. **Worktree hooks cannot be opted out via symlink removal.** `claude/settings.json` L333/L343 wires `WorktreeCreate`/`WorktreeRemove` as `bash -c '[ -f "$CWD/claude/hooks/cortex-worktree-create.sh" ] && bash "$CWD/claude/hooks/cortex-worktree-create.sh"'`. `$CWD` resolves to the cortex-command checkout, not `~/.claude/hooks/`. Removing the `~/.claude/hooks/` symlink has zero effect on whether the hook runs. **The ticket's core "opt-out = don't symlink" semantic silently fails for these two hooks.**

2. **`~/.claude/notify.sh` is unconditionally invoked from the Notification and Stop hooks** (`claude/settings.json` L279, L297). If a user opts out of `cortex-notify.sh`, the symlink is not created but the hook registration still fires — producing command-not-found noise on every permission prompt and every Stop event.

3. **`cortex-setup-gpg-sandbox-home.sh` is wired as an unconditional SessionStart hook** (`claude/settings.json` L239) but is also in `OPTIONAL_HOOK_SCRIPTS`. Opting out leaves a hook registration pointing to a missing script — a blocking SessionStart failure.

4. **`discover_symlinks` already disagrees with `deploy-config` on rules file names.** `discover_symlinks` writes rules as `global-agent-rules.md` / `sandbox-behaviors.md`; `deploy-config` (justfile L355-356) renames them to `cortex-global.md` / `cortex-sandbox.md`. The dynamic scan is already wrong about naming for 2 of 6 rules. Expanding the scan without fixing this foundation amplifies the drift.

5. **`claude/hooks/` is entirely outside `discover_symlinks` coverage today.** The ticket presumes extending discovery; it actually requires fixing a 6-hook black hole first.

6. **`*.sh` glob in the ticket body literally excludes `cortex-sync-permissions.py`** — the single most load-bearing Band C hook. If spec phase takes ticket body literally, the install floor silently breaks.

7. **Malformed SKILL.md still surfaces in the scan** (`(item / "SKILL.md").exists()` — presence check only, not validation). A half-committed skill in working tree would surface in the prompt.

8. **TOCTOU race: detect snapshots discovery; merge applies.** If a user clones a new skill into `skills/` while prompts are running, merge won't see it. The ticket's "always current with repo state" is only true at detect time.

9. **Concurrent `/setup-merge` runs from two terminals will overwrite `lifecycle.config.md`.** The existing mtime-guard only protects `settings.json`; lifecycle.config.md has no write guard today.

### Security concerns

1. **`cortex-validate-commit.sh` is the ONLY enforcement layer for cortex-command commit message format.** There is no CI-level enforcement. If spec-phase install-floor resolution is "default yes with warning," a tired user can disable commit validation by tabbing through prompts.

2. **`cortex-sync-permissions.py` is the sole workaround for Claude Code bug #17017** (project-level permissions replacing global instead of merging). Opting out silently breaks the defense-in-depth permissions model. A hardcoded Band C list in setup-merge is a single-point-of-drift for security-critical classification.

3. **Dynamic filesystem scan is a code-execution-on-discovery hazard.** A malicious PR adding `skills/evil/SKILL.md` surfaces as "Install `evil`? [Y/n]" in the same prompt flow. Attacker-controlled prompt text. A blanket-accept user enables an attacker's skill — Claude Code now discovers it on every session. The current hardcoded-manifest model at least requires PRs to touch the justfile (higher-visibility review surface).

4. **The derived allowlist file (`~/.claude/.cortex-bin-allowlist`)** has no signing, ownership check, or mtime validation. Anything on the user's machine that writes to that path gets trusted by `deploy-bin`.

5. **Committing user install state to the repo** via `lifecycle.config.md` may leak "who is a team member on this repo with lighter install" information. In a shared repo, selections are version-controlled.

### Assumptions that may not hold

1. **"Existing phase readers are tolerant"** — true today and brittle tomorrow. Every phase reader's LLM carries 200+ lines of YAML list in context on every read, every session. Adding future strict-schema validation breaks silently. Critical-review reading `skills: [list]` may surface spurious review findings.

2. **"Hybrid cluster drill-in UX is free"** — `/setup-merge` is plain `[Y/n]` markdown, not TUI. Drill-in requires LLM state tracking across 10+ conversational turns.

3. **"Band C hardcoded-with-comment is fine"** — same double-standard as `setup-force`'s parallel list.

4. **"49 prompts is too many"** — not backed by research; the real count is 39, and the friction threshold is empirical and unmeasured.

5. **"User clones cortex-command once per machine"** — breaks with multiple worktrees or multiple `CLAUDE_CONFIG_DIR` shadows from #065.

6. **"`setup-force` is a safe nuclear option"** — `setup-force` already diverges from `deploy-bin` on 2 bin utilities (`overnight-status`, `git-sync-rebase.sh`). The divergence is current-state.

7. **"Fresh-install-only honors DR-6"** — DR-6 compliance is correct, but the user-facing re-run experience ("I opted out but `ls` still shows it") mismatches the mental model every comparable tool teaches.

### Recommended mitigations (from adversarial agent)

1. **Close the symlink/hook-registration split before extending.** Either remove hook registrations when a hook is opted out, or wrap hook commands in `test -f` guards. Worktree hooks need special handling.
2. **Fix `claude/hooks/` coverage in `discover_symlinks` as a prerequisite.** Ship the coverage fix before extending to opt-in.
3. **Move install-floor classification to per-component frontmatter** (canonical Dimension 6 F2 answer).
4. **Write selections to a user-scoped file**, not the committed `lifecycle.config.md` — or refuse to stage.
5. **Add a file lock on `lifecycle.config.md`** during detect-through-merge.
6. **Refuse to extend dynamic discovery without a skill-contract validation check.**
7. **Pre-empt the `CLAUDE_CONFIG_DIR` footgun** before either ticket ships — document whether setup-merge honors `$CLAUDE_CONFIG_DIR` or ignores it.
8. **Drop the hybrid cluster-drill-in UX** in favor of an edit-a-pasted-YAML-block flow.
9. **Add an integration test** that runs `/setup-merge` → verifies `deploy-bin` → asserts `setup-force` and `deploy-bin` agree on the full install set.
10. **Narrow `REQUIRED_HOOK_SCRIPTS` to Band C** and reclassify the other 6 before extending.

## Open Questions

Open questions from the Clarify phase and new questions surfaced by research. Items marked **Resolved** have an inline answer. Items marked **Deferred** will be resolved during the Spec phase's structured interview.

### Clarify-phase questions

1. **Discovery rule for hooks — what file pattern correctly surfaces every Band C hook without sweeping up non-hook files?**
   **Resolved**: Use `cortex-*` prefix across both `hooks/` and `claude/hooks/` (not `*.sh`). This includes `cortex-sync-permissions.py` (Band C) and filters `bell.ps1`, `output-filters.conf`, `setup-github-pat.sh` naturally. Alternative recommended by codebase agent: derive the hook list from `settings.json` hook block references — picks up only wired-in hooks, misses disk-only hooks. The `cortex-*` prefix rule is the recommended default; `settings.json`-derived is a fallback for future consideration.

2. **`CLAUDE_CONFIG_DIR` interaction — how does `/setup-merge` behave when run inside a repo that has `CLAUDE_CONFIG_DIR` set via #065's direnv pattern?**
   **Partially resolved, spec decision needed**: `merge_settings.py` currently hardcodes `Path.home() / ".claude"` at 7 call sites (L105, L119, L132, L150, L152, L166, L177). None consult `$CLAUDE_CONFIG_DIR`. The two options are: (a) #064 honors `$CLAUDE_CONFIG_DIR` by reading it into the path base (small change, ~7 call sites) and documents the interaction, or (b) #064 explicitly documents that it ignores `$CLAUDE_CONFIG_DIR` and warns users who set it. **Deferred**: this is a consequential choice about whether shadow-scope users get per-shadow install selections or a single global selection. The spec interview should ask.

3. **Phase reader tolerance — will existing lifecycle phase readers tolerate unknown top-level `skills:` and `hooks:` keys in `lifecycle.config.md` frontmatter?**
   **Resolved**: All six current readers (lifecycle SKILL.md, research.md, specify.md, plan.md, complete.md, critical-review SKILL.md) are LLM-based pattern-matches on known keys. None are schema validators. Unknown top-level keys will not break any current reader. **Caveat**: the adversarial pass flagged token-cost and future-phase risk — each phase's context now carries the new YAML list on every read. The mitigation is to keep the sections compact (list-of-names, not nested dicts) and to revisit if a future phase needs strict schema.

### New questions surfaced by research — deferred to Spec interview

4. **Classification source — per-component frontmatter (F2) vs hardcoded table in setup-merge (F1)?**
   **Deferred**: will be resolved in Spec by asking the user. F2 is canonical but requires 39-file migration + hook-header-comment convention; F1 is pragmatic but drift-prone (same pattern as `setup-force`'s parallel list). The existing `REQUIRED_HOOK_SCRIPTS` / `OPTIONAL_HOOK_SCRIPTS` constants also need reconciliation regardless of which path is chosen.

5. **Selection storage — accept the project/user state mixing in `lifecycle.config.md`, use user-scoped keys (`user-skills:`, `user-hooks:`), or move to `~/.claude/lifecycle.config.md`?**
   **Deferred**: will be resolved in Spec by asking the user. Project is "primarily personal tooling" per DR-2's own rationale, so the teammate-overwrite concern may be theoretical — but `commit-artifacts: true` default will auto-stage selections on next `/commit`, which is a concrete footgun.

6. **Prompt granularity — ticket's per-component (friction-heavy but simple to implement), hybrid per-cluster drill-in (complex LLM state tracking), or paste-a-YAML-block edit flow (out-of-band)?**
   **Deferred**: will be resolved in Spec by asking the user. Research Q1 flagged this explicitly as a user call.

7. **`deploy-bin` gating mechanism — derived allowlist file (D1), Python helper (D3), or YAML-parsing in justfile?**
   **Deferred**: will be resolved in Spec by asking the user. D1 is the simplest short-term answer but the adversarial pass flagged no-mtime-guard / no-signing concerns for `~/.claude/.cortex-bin-allowlist`.

8. **Re-run behavior success signal — weaken Success Signal #1 to "on fresh install, `ls` reflects selections", add drift surfacing, or accept silent divergence?**
   **Deferred**: will be resolved in Spec by asking the user. DR-6 binds the non-destructive constraint; the choice is about how the UX communicates that constraint.

9. **Worktree hooks and `$CWD`-scoped hook invocations — how should #064 handle the existing `$CWD/claude/hooks/...` worktree hook pattern that cannot be opted out via symlink removal?**
   **Deferred**: will be resolved in Spec by asking the user. Options: (a) convert worktree hooks to `~/.claude/hooks/...` as a prerequisite, (b) exclude worktree hooks from the opt-out UI with a footnote, (c) defer to a follow-up ticket.

10. **Hook registration cleanup on opt-out — should opting out of a hook also remove its entry from `claude/settings.json`'s hooks block, or add `test -f` guards to hook commands, or leave the registration dangling?**
    **Deferred**: will be resolved in Spec by asking the user. The `cortex-notify.sh` and `cortex-setup-gpg-sandbox-home.sh` cases are concrete — opting out of either today leaves a broken hook registration.

11. **`REQUIRED_HOOK_SCRIPTS` reconciliation — narrow to research §2 Band C (3 hooks) before extending, or keep the current 9-hook set as a second "required" band?**
    **Deferred**: will be resolved in Spec by asking the user. The existing broader set may encode valid constraints the Band C research missed.

12. **`claude/hooks/` coverage gap fix — prerequisite inside #064 scope, separate dependency ticket, or bundle as part of the ticket's discovery-rule change?**
    **Deferred**: will be resolved in Spec by asking the user. The fix is small but it is a real prerequisite for the ticket's dynamic-discovery promise.

13. **`setup-force` reconciliation — include in scope (update to read lifecycle.config.md), exclude explicitly (document as clean-reinstall escape hatch), or bundle as cleanup?**
    **Deferred**: will be resolved in Spec by asking the user. `setup-force` already diverges from `deploy-bin` today.

14. **Concurrent `/setup-merge` runs — add file lock on `lifecycle.config.md`, document as unsupported, or reuse the existing mtime-guard pattern?**
    **Deferred**: will be resolved in Spec by asking the user. Low-probability but high-impact footgun.

15. **Skill-contract validation gate — should `/setup-merge` reject candidate SKILL.md files that fail contract validation, or surface them with a warning, or trust filesystem presence?**
    **Deferred**: will be resolved in Spec by asking the user. Security and data-integrity implication.

16. **Integration test coverage — mandatory for shipping, or follow-up work?**
    **Deferred**: will be resolved in Spec by asking the user. There are zero existing tests for `/setup-merge` today.
