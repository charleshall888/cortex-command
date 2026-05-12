# Research: Document CLAUDE_CONFIG_DIR + direnv pattern for per-repo permissions scoping

> **Scope anchor (clarified intent)**: Deliver a docs page for cortex-command users that documents the `CLAUDE_CONFIG_DIR` + direnv pattern for scoping Claude Code configuration per repo, gated on a DR-7 upstream audit whose outcome (quiet / warm / hot) shapes the page's depth. The page always ships; under hot it ships in a minimal wait-oriented form.

> **Tier**: simple. **Criticality**: high. The high criticality is reflected in the failure-mode enumeration (§4) and the explicit per-file precedence verification (§2). Tier=simple keeps the alternative-exploration section short.

---

## 1. DR-7 Upstream Audit — gating classification

**Verdict: WARM.** Evidence below.

### 1.1 Issue-by-issue findings (live data, fetched 2026-04-10)

| Issue | State | Comments | +1 reactions | Last activity | Anthropic engagement | Linked PRs |
|-------|-------|---------:|-------------:|---------------|---------------------|-----------|
| [#12962](https://github.com/anthropics/claude-code/issues/12962) — Settings.json parent directory traversal for monorepos | **OPEN** | 11 | **50** | 2026-03-29 (12 days ago) | None — labels are `enhancement` + `area:core` only, no assignees, no Anthropic-staff comments anywhere in the thread | None |
| [#37344](https://github.com/anthropics/claude-code/issues/37344) — Hierarchical .claude config discovery in monorepos | **CLOSED** (duplicate of #12962) | 4 | n/a | Locked 2026-04-01 | Auto-closed by github-actions bot | None |
| [#35561](https://github.com/anthropics/claude-code/issues/35561) — Hierarchical .claude/ discovery past git boundaries | **CLOSED** (duplicate of #26489) | 2 | n/a | Locked 2026-03-26 | Auto-closed by github-actions bot | None |
| [#26489](https://github.com/anthropics/claude-code/issues/26489) — skills/, agents/, commands/ should traverse parent directories | **OPEN** | 14 | **30** | 2026-04-10 (today) | None — `enhancement` label only, no assignees, no Anthropic-staff comments | None |

**Combined signal**: 80 +1 reactions across the two open issues, 25 comments, two of the four originally-listed issues already auto-closed as duplicates of the other two — strong evidence that this is a recurring user pain point that the community keeps re-filing. Latest community engagement is from today on #26489.

**Anthropic signal**: zero. None of the issues are assigned. None carry triage labels beyond the autoposted `enhancement` / `area:core`. No Anthropic-staff (`@anthropics/...` membership) appears in any of the comment threads. No linked PRs reference any of the four issue numbers.

### 1.2 Adjacent CLAUDE_CONFIG_DIR-specific issues

A `gh search issues "CLAUDE_CONFIG_DIR"` query returns 20+ open bug reports (not feature requests) about CLAUDE_CONFIG_DIR's actual behavior. None show Anthropic engagement. Highlights:

- [#3833](https://github.com/anthropics/claude-code/issues/3833) — "CLAUDE_CONFIG_DIR behavior unclear, still creates local .claude/ directories." Closed `NOT_PLANNED`. Community comment by @graelo (Dec 2025) reports that as of v2.0.42-74, `~/.claude.json` (the org-state file) DOES move under `$CLAUDE_CONFIG_DIR`, but other files don't. **The variable is partially and inconsistently honored across the codebase.**
- [#36172](https://github.com/anthropics/claude-code/issues/36172) — "Unknown skill when CLAUDE_CONFIG_DIR is set and skill lives in `$CLAUDE_CONFIG_DIR/skills/`." OPEN, no Anthropic response. **This is directly load-bearing for the cortex-command shadow approach.**
- [#38641](https://github.com/anthropics/claude-code/issues/38641) — "`/context` displays hardcoded `~/.claude/CLAUDE.md` path instead of respecting `$CLAUDE_CONFIG_DIR`." OPEN, no Anthropic response.
- [#34800](https://github.com/anthropics/claude-code/issues/34800) — "IDE lock files always written to `~/.claude/ide`, ignoring CLAUDE_CONFIG_DIR." OPEN.
- [#42217](https://github.com/anthropics/claude-code/issues/42217) — "MCP servers from mcp.json not loaded when CLAUDE_CONFIG_DIR is set." OPEN.
- [#44866](https://github.com/anthropics/claude-code/issues/44866) — "MCP config hierarchy is confusing and undocumented when using CLAUDE_CONFIG_DIR profiles." OPEN, filed 2026-04-07.
- [#25762](https://github.com/anthropics/claude-code/issues/25762) — "Add environment variable to configure .claude config directory location." OPEN. Community comment confirms `CLAUDE_CONFIG_DIR` already exists and works.

**Implication for the docs**: the troubleshooting section of the page MUST flag that `CLAUDE_CONFIG_DIR` is partially honored. Skills loading from `$CLAUDE_CONFIG_DIR/skills/` is **not guaranteed** in current Claude Code versions (#36172 is OPEN). The docs must verify with `/context` or equivalent which scope is actually live, not assume the variable swaps everything cleanly.

### 1.3 Claude Code release notes (last 3 months)

Release notes scanned for v2.1.90 → v2.1.101 (covering roughly January 2026 → April 2026, with v2.1.101 published 2026-04-10):

- **No release in the past 3 months touches**: `.claude` directory layout, parent-directory traversal for any config file, `CLAUDE_CONFIG_DIR` semantics, monorepo support, or `setting_sources` precedence in a way that would invalidate the shadow approach.
- **What did ship**, that is adjacent and relevant to cite as "this area is being touched, but not in a way that forecloses our pattern":
  - v2.1.101: `permissions.deny` rules now override `PreToolUse` hook `permissionDecision: "ask"`; in-app settings writes refresh the in-memory snapshot; unrecognized hook event names no longer cause the entire `settings.json` to be ignored.
  - v2.1.98: added `disableSkillShellExecution` setting; fixed `permissions.additionalDirectories` mid-session changes not applying.
  - v2.1.97: fixed permission rules with names matching JS prototype properties causing silent settings.json ignore; managed-settings allow rules now removed-on-removal.
  - v2.1.92: added `forceRemoteSettingsRefresh` policy; added `.husky` to protected directories.
- **What did NOT ship**: anything matching "settings parent traversal", "monorepo", "directory walk", "scope inheritance", "config dir relocation", or any reference to issues #12962, #26489, #25762.

Settings/permissions/hooks are an area of **active hardening** for Claude Code, but every change in the past 3 months is a defensive bug-fix or a new escape-hatch. **None of them are the structural change that would obsolete CLAUDE_CONFIG_DIR + shadow scope.** The structural rework that would ship #12962 (parent traversal) is significantly larger than any change in the past 3 months.

### 1.4 Classification: WARM

The DR-7 framework defines:

- **Quiet** (no recent activity, no Anthropic engagement) → ship full docs as primary mechanism.
- **Warm** (some activity, no commitments) → ship full docs with explicit "watch these upstream issues" callout.
- **Hot** (active PR, roadmap mention, or Anthropic staff commentary) → minimal wait-oriented page only.

The evidence places this squarely in **warm**:
- "Some activity": community engagement is sustained (80 reactions, today's comments, repeated re-filings as duplicates).
- "No commitments": Anthropic shows zero signal (no PRs, no triage, no staff comments, no roadmap mention, no release notes touching the area).
- It is NOT "hot" because no Anthropic-side artifact (PR, roadmap, staff comment, or release-note hint) suggests imminent action.
- It is NOT "quiet" because the issues are alive, the duplicates keep coming, and the topic is on the community's mind.

**Docs implication**: ship the full supported-pattern docs (walkthrough, fallbacks, troubleshooting). Add an explicit "watch these upstream issues" preamble linking to #12962 and #26489. Do NOT collapse to the minimal wait-oriented shape. The page is the primary documented mechanism.

---

## 2. CLAUDE_CONFIG_DIR mechanics verification

### 2.1 Official documentation (verified 2026-04-10)

Source: <https://code.claude.com/docs/en/env-vars> (official Claude Code env-vars reference)

> **CLAUDE_CONFIG_DIR** — Override the configuration directory (default: `~/.claude`). All settings, credentials, session history, and plugins are stored under this path. Useful for running multiple accounts side by side: for example, `alias claude-work='CLAUDE_CONFIG_DIR=~/.claude-work claude'`.

The official documentation enumerates four categories that move with the variable:
1. **Settings** — `settings.json`, `settings.local.json`
2. **Credentials** — auth tokens, API key state
3. **Session history** — `projects/<slug>/`, `history.jsonl`, `todos/`, `tasks/`
4. **Plugins** — `plugins/` cache directory

The documentation does **not** explicitly enumerate: `skills/`, `hooks/`, `agents/`, `commands/`, `reference/`, `rules/`, `statusline.sh`, `notify.sh`, `CLAUDE.md`, `keybindings.json`, `ide/`. These are **not officially documented as scoped by `CLAUDE_CONFIG_DIR`**.

### 2.2 Empirical behavior reported by community / open bug reports

The community evidence (issues #3833, #36172, #38641, #34800, #42217, #44866) is:

- **`skills/` and `commands/` lookup**: `$CLAUDE_CONFIG_DIR/skills/<name>/` is NOT reliably honored in current Claude Code versions — #36172 is open with no response. A user reports that placing a skill at `$CLAUDE_CONFIG_DIR/skills/foo/SKILL.md` fails to resolve. **Cortex-command's whole skill inventory therefore may not transparently move with the env var.**
- **`commands/` lookup for plugin skills**: #34144 reports the same problem for plugin slash commands.
- **`/context` display**: #38641 reports that `/context` hardcodes `~/.claude/CLAUDE.md` regardless of `$CLAUDE_CONFIG_DIR`. The user cannot trivially see which scope is live.
- **`ide/` lock files**: #34800 reports that IDE lock files always write to `~/.claude/ide/` regardless of the env var.
- **MCP `.mcp.json` loading**: #42217 reports that MCP servers from `mcp.json` are not loaded under a custom `CLAUDE_CONFIG_DIR`.

**Conclusion**: `CLAUDE_CONFIG_DIR` is partially and inconsistently honored. It reliably moves `settings.json`, credentials, and session history. It does NOT reliably move `skills/`, `commands/`, `ide/`, MCP config, or display paths. **The docs must call this out explicitly** rather than imply a clean swap.

### 2.3 Precedence order

When both `CLAUDE_CONFIG_DIR` is set and a project-level `.claude/` exists, the documented precedence order (from `~/.claude/reference/claude-skills.md` and `code.claude.com/docs/en/settings`) is:

1. **Managed settings** (enterprise / `/Library/Application Support/ClaudeCode/managed-settings.json` on macOS) — highest precedence
2. **Local settings** (`<cwd>/.claude/settings.local.json`)
3. **Project settings** (`<cwd>/.claude/settings.json`)
4. **User settings** (`$CLAUDE_CONFIG_DIR/settings.json`, default `~/.claude/settings.json`) — lowest precedence

**Key implication**: setting `CLAUDE_CONFIG_DIR` only swaps the **user scope**, not the project scope. Project `.claude/` is still discovered relative to CWD. So a shadow user scope plus a project `.claude/settings.local.json` will both apply, with the project file winning on scalars and concatenating arrays. The shadow approach gives the user "in this repo, my user-scope baseline is different" — it does not give "in this repo, the project file is the only thing that matters."

For the commissioned use case ("only use project permissions in this repo, ignore global allows"), the user must:
1. Point `CLAUDE_CONFIG_DIR` at a shadow scope whose `settings.json` has the desired minimal allow list.
2. Optionally remove or trim the project-level `.claude/settings.local.json` (which holds cortex-sync-permissions output).

The shadow approach does NOT delete the project scope — it replaces the user scope underneath it. This is a subtlety the docs must explain.

### 2.4 Does `/setup-merge` write to `$CLAUDE_CONFIG_DIR` or hardcode `~/.claude/`?

**It hardcodes `~/.claude/`. It does not honor `CLAUDE_CONFIG_DIR`.** This is a critical finding for the docs page.

Evidence from `.claude/skills/setup-merge/SKILL.md`:
- Line 15: `test -L ~/.claude/settings.json` (symlink guard reads literal `~/.claude/`)
- Line 21: `python3 ${CLAUDE_SKILL_DIR}/scripts/merge_settings.py migrate --settings ~/.claude/settings.json`
- Line 48: `python3 ${CLAUDE_SKILL_DIR}/scripts/merge_settings.py detect --repo-root $(git rev-parse --show-toplevel) --settings ~/.claude/settings.json`
- Line 319, 323: `test -f ~/.claude/get-api-key.sh`

Evidence from `.claude/skills/setup-merge/scripts/merge_settings.py`:
- Lines 113–183: `discover_symlinks()` constructs every target as `home / ".claude" / ...` where `home = Path.home()`. It does NOT consult `os.environ.get("CLAUDE_CONFIG_DIR")`.
- Line 990–991, 1045–1046: `--settings` argparse default is the literal string `"~/.claude/settings.json"`.

**Implication**: if a user has `CLAUDE_CONFIG_DIR=~/.cortex/repo-shadows/foo` set in a session and then runs `/setup-merge`, the skill will silently merge into `~/.claude/settings.json`, NOT into the shadow scope's `settings.json`. The docs page must warn against running `/setup-merge` from inside a shadowed shell.

**Spec implication for the page** (not for this ticket's scope, but worth noting): the most user-friendly fix is to teach `merge_settings.py` to honor `CLAUDE_CONFIG_DIR` when set, which is a 5-line patch (`home = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))).parent` or similar). That code change is OUT OF SCOPE for ticket #065 (which is docs-only) but should be filed as a follow-up backlog item.

### 2.5 Hardcoded `~/.claude` paths across the cortex-command repo

A repo-wide grep for `~/.claude`, `$HOME/.claude`, and `HOME/.claude` finds the following load-bearing references that would NOT transparently follow `CLAUDE_CONFIG_DIR`:

| File | Lines | What it hardcodes | Severity |
|------|-------|-------------------|----------|
| `justfile` | 57–98, 181–356, 391, 563–564, 782–833 | All `deploy-*` recipes, `check-symlinks`, `setup-bootstrap` | **Critical** — `just setup` only ever installs to `~/.claude/` |
| `.claude/skills/setup-merge/SKILL.md` | 15, 21, 48, 319, 323 | Reads/writes `~/.claude/settings.json` and `~/.claude/get-api-key.sh` | **Critical** — `/setup-merge` silently writes to global scope under shadow |
| `.claude/skills/setup-merge/scripts/merge_settings.py` | 113–183, 990, 1045 | All symlink targets and the `--settings` default | **Critical** — same as above |
| `bin/audit-doc` | 31, 40, 41, 50, 73 | Walks up from cwd looking for `.claude/settings*.json`, then falls back to `Path.home() / ".claude" / "settings.json"` | Medium — falls back to global, ignores env var |
| `bin/count-tokens` | 26, 35, 36, 45, 68 | Same pattern as `audit-doc` | Medium — same |
| `claude/Agents.md` (→ `~/.claude/CLAUDE.md`) | many | Cross-references like `~/.claude/reference/...` and `~/.claude/skills/...` are embedded in instruction prose | Low — instructions, not file lookups |
| `skills/skill-creator/SKILL.md` | 225, 226, 227, 330, 331, 369 | References like "deployed to `~/.claude/rules/cortex-global.md`" | Low — instructions |
| `skills/lifecycle/SKILL.md` | 273 | "see `~/.claude/reference/output-floors.md`" | Low — instructions |
| `skills/lifecycle/references/{specify,plan,research,clarify}.md` | several | "read and follow `~/.claude/skills/lifecycle/references/orchestrator-review.md`" | Low — reference paths |
| `skills/discovery/references/research.md` | 124 | Same | Low |
| `skills/skill-creator/references/{workflows,orchestrator-patterns}.md` | several | Same | Low |
| `skills/evolve/SKILL.md` | 54–57 | Constructs `~/.claude/projects/-<project-slug>/memory/MEMORY.md` for auto-memory lookup | Medium — actually reads a file, but Claude Code's auto-memory IS scoped by `CLAUDE_CONFIG_DIR` per docs |
| `skills/diagnose/SKILL.md` | 149 | "the sandbox allowlist expects an absolute path" — example only | Low — example text |
| `skills/ui-setup/SKILL.md` | 37 | "(`.claude/settings.json` or `~/.claude/settings.json`)" | Low |
| `skills/ui-check/SKILL.md` | 11, 74 | "must be available (`~/.claude/skills/ui-lint/SKILL.md`)" | Low — availability check by reading a literal absolute path |
| `hooks/cortex-cleanup-session.sh` | 46 | `awk '/^worktree/ && $2 ~ /\.claude\/worktrees\/agent-/'` — pattern-matches the literal `.claude/worktrees/` path in `git worktree list` output | Low — only matches output that already contains `.claude/`, doesn't read it |

The top three rows are the load-bearing failures: `just setup`, `/setup-merge`, and `merge_settings.py` all bypass `CLAUDE_CONFIG_DIR` entirely and write to `~/.claude/`. The `bin/` utilities (`audit-doc`, `count-tokens`) walk up looking for project settings then fall back to the literal `~/.claude/` path — also incorrect under a shadow scope.

The Low-severity rows are instruction text inside skills (`SKILL.md` and reference docs) that says things like "see `~/.claude/reference/foo.md`". When loaded under a shadow scope, the model-readable instructions still tell the agent to read paths under the literal `~/.claude/`, even though the active config dir is elsewhere. **In practice the agent will read those paths via a Read tool call, and as long as those files exist at the `~/.claude/` path the read succeeds — but the loaded content is from the original cortex install, not the shadow.** This is acceptable for reference docs that should be globally consistent, but it does mean the shadow can't have a different `output-floors.md` from the host.

`skills/evolve/SKILL.md` is a special case: the auto-memory file at `~/.claude/projects/-<slug>/memory/MEMORY.md` IS scoped by `CLAUDE_CONFIG_DIR` per the official docs ("session history" category). So the prompt's hardcoded `~/.claude/projects/...` path will read from the wrong location under a shadow scope. This is a mid-severity bug — not a docs issue, a follow-up code fix.

---

## 3. Existing cortex-command docs surface

### 3.1 `docs/` inventory

Files in `docs/`:
- `agentic-layer.md` — full skill/hook inventory, workflow diagrams, lifecycle phase map. Tone: reference, table-heavy, "What's Inside" framing.
- `setup.md` — installation walkthrough. Tone: instructional, step-by-step, "Before You Start" backup warnings, "What `just setup` Does" tables. **The closest tone match for a new per-repo permissions doc.**
- `overnight.md` — autonomous overnight runner reference.
- `dashboard.md` — web dashboard setup and usage.
- `backlog.md` — backlog YAML schema.
- `interactive-phases.md` — what to expect at each lifecycle phase.
- `pipeline.md` — internal pipeline orchestration module reference.
- `skills-reference.md` — per-skill detailed reference.
- `sdk.md` — SDK reference.

**Common template observations**:
- Every file starts with `[← Back to README](../README.md)` as line 1.
- Every file has an H1 title and a `**For:** ... **Assumes:** ...` audience line directly below.
- Section dividers are `---` between major H2 sections.
- Code blocks use fenced bash/json/text.
- Tables are common for inventories and capability matrices.
- Cross-links use markdown reference style.

The new docs page should follow this template for consistency.

### 3.2 Discoverability — README index and CLAUDE.md

- `README.md` lines 164–176: there is a "Documentation" section with a markdown table that lists each `docs/*.md` file with a one-line summary. **A new `docs/per-repo-permissions.md` page must be added to this table** so users discover it.
- `CLAUDE.md` (project root): does NOT mention permissions, scoping, or `CLAUDE_CONFIG_DIR`. It lists the symlink architecture and conventions. The new docs page should be cross-linked from CLAUDE.md's "Symlink Architecture" section, with a note like "For per-repo overrides see [`docs/per-repo-permissions.md`](docs/per-repo-permissions.md)."
- `docs/setup.md` Customization section (lines 132–161) talks about permissions allow/deny but does not mention per-repo scoping. It should gain a one-paragraph "Per-repo overrides" subsection that links to the new page.

### 3.3 Recommended file path

`docs/per-repo-permissions.md` is the natural choice. It is short, discoverable, matches the existing flat docs/ structure, and the slug matches the search terms a user would type.

Alternative names considered and rejected:
- `docs/claude-config-dir.md` — too implementation-focused; users searching for the concept type "permissions per repo," not "claude config dir."
- `docs/scoping.md` — too vague.
- `docs/per-repo-config.md` — slightly broader than needed; the page is specifically about permissions/scope override, not arbitrary per-repo config.
- `docs/customization-per-repo.md` — too long and clinical.

---

## 4. Failure-mode inventory for the shadow mechanism

This is the most important section of the research given criticality=high. Silent drift between the shadow and the host is the central risk.

### 4.1 The `cp -r` symlink trap (most severe)

**Scenario**: a user follows the obvious instruction `cp -r ~/.claude ~/.cortex/repo-shadows/foo` and then sets `CLAUDE_CONFIG_DIR=~/.cortex/repo-shadows/foo`.

**What goes wrong**: macOS `cp -R` defaults to `-P` (no symlinks followed). Linux `cp -r` is the same. The result: every symlink under `~/.claude/` is **copied as a symlink with the same target**, not as a deep copy. Specifically, in a typical cortex-command install:

```
~/.cortex/repo-shadows/foo/
├── settings.json    → /Users/.../cortex-command/claude/settings.json   (still symlinked!)
├── statusline.sh    → /Users/.../cortex-command/claude/statusline.sh   (still symlinked!)
├── notify.sh        → /Users/.../cortex-command/hooks/cortex-notify.sh (still symlinked!)
├── CLAUDE.md        → /Users/.../cortex-command/claude/Agents.md       (still symlinked!)
├── skills/
│   ├── commit/      → /Users/.../cortex-command/skills/commit          (still symlinked!)
│   └── …            (every skill still symlinked!)
├── hooks/
│   └── cortex-*.sh  → /Users/.../cortex-command/hooks/cortex-*.sh      (still symlinked!)
├── reference/
│   └── …            (still symlinked!)
└── rules/
    └── …            (still symlinked!)
```

**Verified**: `ls -la ~/.claude/` on this machine shows that every cortex-deployed entry is a symlink (`lrwxr-xr-x`) targeting an absolute path under `/Users/charlie.hall/Workspaces/cortex-command/...`. After `cp -R`, the shadow's entries are also symlinks pointing to the SAME absolute path.

**Consequence**: the shadow's `settings.json` is the SAME FILE as the host's `settings.json`. **Modifying the shadow's settings.json modifies the host's**. The shadow's permissions are not isolated from the host. The entire mechanism silently fails to deliver isolation, and the user has no warning.

**Mitigation**: the docs page must instruct users to do at least one of the following AFTER `cp -r`:
1. `rm ~/.cortex/repo-shadows/foo/settings.json` and then write a fresh standalone `settings.json` with the desired minimal allow list. (Required.)
2. (Optional, for stricter isolation) `rm` the symlinks for `statusline.sh`, `notify.sh`, `CLAUDE.md` if the user wants the shadow not to inherit those.
3. Skills and hooks SHOULD remain symlinked — that is the intended behavior so the shadow inherits skill/hook updates. But this means the shadow is NOT a frozen snapshot.

**Alternative copy pattern that avoids this**: `cp -RL ~/.claude ~/.cortex/repo-shadows/foo` follows symlinks and produces a true deep copy. This is the opposite trap: now the shadow is a frozen snapshot, completely cut off from upstream skill/hook updates. Whichever pattern the docs recommend, the trade-off must be explicit.

**Recommended docs framing**: recommend `cp -R` (no `-L`), then explicitly `rm` the host-symlinked top-level files that the user wants isolated (`settings.json` is the always-required one), then write a fresh `settings.json` for the shadow. This gives the user control: "what I rm is what I isolate; what I leave symlinked stays in sync."

### 4.2 `/setup-merge` writes to the wrong scope

Already covered in §2.4. Summary: running `/setup-merge` from a shadowed shell silently writes to `~/.claude/settings.json`, not the shadow's settings.json. The docs page must warn:

> Do NOT run `/setup-merge` from inside a directory where `CLAUDE_CONFIG_DIR` is set. The skill writes to `~/.claude/` regardless of the env var. To update your shadow's settings.json, edit it manually, or unset `CLAUDE_CONFIG_DIR` first.

### 4.3 `just setup` re-installs to `~/.claude/`, not the shadow

Same root cause: every `deploy-*` recipe in the `justfile` hardcodes `~/.claude/` as the target. So `just setup` from inside a shadowed shell will install/re-install symlinks under `~/.claude/`, leaving the shadow unmodified.

This is actually fine for the shadow's intended use (the shadow inherits via symlink anyway), but the user may be confused: "I ran `just setup` and my shadow didn't update." The docs should clarify: `just setup` always operates on `~/.claude/`; the shadow inherits skill/hook updates automatically through its symlinks (provided the user used `cp -R` not `cp -RL`).

### 4.4 Stale `settings.json` when host is updated

**Scenario**: the user creates a shadow, then later runs `/setup-merge` to pull updated cortex defaults into `~/.claude/settings.json`. The shadow's `settings.json` (which the user wrote standalone in §4.1 mitigation) is now stale relative to the new host defaults.

**Symptom**: cortex-command starts using a new sandbox `excludedCommands` entry or a new deny rule. The shadow doesn't have it. The host has it. The shadow user gets blocked by an unfamiliar denial in the shadow, or escapes a deny they should have inherited.

**Mitigation**: docs should suggest a re-sync workflow: "after running `/setup-merge` against `~/.claude/`, re-create your shadow with `cp -R`, then re-apply your custom edits." This is manual. A future bin utility `cortex-shadow-config refresh` (out of scope for this ticket) could automate it. **For now the docs document the pattern, not the tool.**

### 4.5 Stale auto-memory under `evolve` skill

**Scenario**: the `evolve` skill (skills/evolve/SKILL.md line 57) constructs `~/.claude/projects/-<slug>/memory/MEMORY.md` as a literal path, not via `$CLAUDE_CONFIG_DIR`. Under a shadow, `evolve` will read the host's auto-memory, not the shadow's.

**Severity**: medium. Auto-memory is per-project (slugged from the cwd), so the host and shadow could legitimately have different memories — they ARE different scopes. But the skill always reads from `~/.claude/`, so the shadow scope's auto-memory file is ignored.

**Mitigation**: not the docs page's job. File a follow-up to fix `evolve` to consult `$CLAUDE_CONFIG_DIR`. The docs page can mention "auto-memory tracking under `/evolve` is currently host-scoped only" as a limitation.

### 4.6 `bin/audit-doc` and `bin/count-tokens` fall back to host

Both utilities walk up from cwd looking for `.claude/settings*.json`, then fall back to `Path.home() / ".claude" / "settings.json"`. Under a shadow scope:
- If the user is inside a project that has its own `.claude/settings.local.json` with an `apiKeyHelper`, the utility uses that. Fine.
- If not, the utility falls back to the HOST `~/.claude/settings.json`, NOT the shadow's. So it picks up the host's `apiKeyHelper`, not the shadow's.

For most users this won't matter (the API key helper is the same regardless), but it's a silent inconsistency. The docs page should mention it as a limitation and link to a follow-up backlog item to fix the bin utilities.

### 4.7 direnv trust revocation and the resulting fallback UX

`direnv` has a security model: every `.envrc` requires explicit trust via `direnv allow`. If the user pulls a fresh clone, restores from backup, or `git checkout`s to a branch with a different `.envrc`, direnv automatically untrusts the file. The user sees:

```
direnv: error /path/to/.envrc is blocked. Run `direnv allow` to approve its content
```

And **`CLAUDE_CONFIG_DIR` is unset** — Claude Code falls back to `~/.claude/`. The user gets the host scope, not the shadow, with no warning unless they happen to look at their shell prompt.

**Mitigation**: docs page should include a "verify which scope is active" step. The simplest reliable check is to grep `CLAUDE_CONFIG_DIR` in the shell environment before launching `claude`:

```bash
echo "CLAUDE_CONFIG_DIR=${CLAUDE_CONFIG_DIR:-(not set, will use ~/.claude)}"
```

A shell helper function or a `just` recipe that does this check before launching is a nice-to-have but out of scope for the docs ticket.

### 4.8 Confusion about which scope Claude Code is reading

Per upstream issue [#38641](https://github.com/anthropics/claude-code/issues/38641), the `/context` command in Claude Code displays the literal path `~/.claude/CLAUDE.md` even when `CLAUDE_CONFIG_DIR` is set. This means the user CANNOT use `/context` to verify which scope is active. They must verify before launching the session, not from inside it.

**Reliable verification methods (from outside Claude Code):**
1. `echo $CLAUDE_CONFIG_DIR` — checks the env var.
2. `lsof -p $(pgrep -n claude) 2>/dev/null | grep settings.json` — checks which settings.json the running process actually opened. (Requires the process to be running.)
3. `cat $CLAUDE_CONFIG_DIR/settings.json` vs `cat ~/.claude/settings.json` — manual diff.

**Reliable verification methods (from inside Claude Code):**
1. None that work cleanly today. `/context` lies. Asking the agent to `Read $CLAUDE_CONFIG_DIR/settings.json` will work, but the agent must be told the env var is set.

The docs page should include a "How to verify" section with the env-var check as the primary recommendation.

### 4.9 Skills loading from `$CLAUDE_CONFIG_DIR/skills/` is not guaranteed

Per upstream issue [#36172](https://github.com/anthropics/claude-code/issues/36172), placing skills in `$CLAUDE_CONFIG_DIR/skills/<name>/` does not reliably resolve at slash-command time in current Claude Code versions. The bug is open with no Anthropic response.

**Implication for cortex-command**: even if a user shadows `~/.claude/`, the shadow's `skills/` directory may not be honored. The shadow can NOT be used to disable a cortex-command skill on a per-repo basis (one of the use cases the discovery research considered). The shadow CAN be used to swap settings.json (which is reliably scoped), so it CAN deliver the commissioned per-repo permissions use case — which is the use case this ticket is about.

**Docs framing**: the page should explicitly say "this swaps settings.json reliably; per-repo skill/hook disable is NOT a supported use case until upstream issue #36172 is resolved." This is a scope limitation, not a bug we can fix.

### 4.10 Concurrent sessions using the same shadow

**Scenario**: the user opens two Claude Code sessions in two different terminal panes, both with the same `CLAUDE_CONFIG_DIR` set. Both sessions write `settings.local.json`, `projects/<slug>/`, `history.jsonl` to the same shadow.

**Risk**: the same risk as concurrent sessions under `~/.claude/` — Claude Code's existing behavior. Not a shadow-specific failure mode. But worth noting: shadowing does NOT add isolation between concurrent sessions in the same repo.

### 4.11 Summary: failure modes ranked by severity

1. **Critical — `cp -r` silently fails to isolate** (§4.1) → must be documented prominently with the "rm symlinks before writing fresh settings.json" workflow.
2. **Critical — `/setup-merge` writes to wrong scope** (§4.2) → must be documented with a "do not run from shadowed shell" warning.
3. **Medium — stale settings.json on host updates** (§4.4) → document the manual re-sync workflow.
4. **Medium — silent fallback when direnv is untrusted** (§4.7) → document the verification step.
5. **Medium — `bin/audit-doc` and `bin/count-tokens` fall back to host** (§4.6) → document as a limitation, file follow-up.
6. **Medium — `evolve` reads host auto-memory** (§4.5) → document as limitation, file follow-up.
7. **Medium — `/context` lies about active path** (§4.8) → document the verification method.
8. **Medium — skills under `$CLAUDE_CONFIG_DIR/skills/` not guaranteed** (§4.9) → document as scope limitation.
9. **Low — `just setup` operates on host, not shadow** (§4.3) → document as expected behavior.
10. **Low — concurrent shadow sessions don't add isolation** (§4.10) → mention if space allows.

---

## 5. Alternative exploration

The clarified intent specifies direnv as the recommended integration with fallback to shell alias or `just launch`. Tier=simple means alternatives are encouraged but not required. Brief comparison below.

### 5.1 Mechanisms considered

| Mechanism | Setup cost | Per-repo discovery | Trust model | Fallback when missing | Cross-shell |
|-----------|-----------|--------------------|-------------|----------------------|-------------|
| **direnv `.envrc`** | Install direnv (`brew install direnv` + shell hook) once. Add `.envrc` per repo, run `direnv allow`. | Automatic on `cd` into the repo | Explicit `direnv allow` per file | `CLAUDE_CONFIG_DIR` unset; falls back to host | Yes (zsh, bash, fish, all supported) |
| **Shell alias** (`alias claude='CLAUDE_CONFIG_DIR=~/.cortex/repo-shadows/$(basename $PWD) claude'`) | Add one line to `.zshrc` or `.bashrc`. No per-repo setup. | Automatic from cwd basename | None (always-on) | If shadow doesn't exist, Claude Code creates an empty one | Per-shell only (must duplicate alias for each shell) |
| **Shell wrapper script in PATH** (`~/.local/bin/claude` that sets the env var then exec's the real binary) | Write the wrapper once. No per-repo setup. | Automatic from cwd | None | Same as alias | All shells; PATH-driven |
| **Wrapper script committed to the repo** (`./bin/claude` per repo, calls `CLAUDE_CONFIG_DIR=... command claude`) | One file per repo. No global setup. | Only when invoking `./bin/claude` | None — repo committed | User invokes `claude` (real binary) → host scope. User invokes `./bin/claude` → shadow. | All shells |
| **`just launch` recipe** (per-repo `just launch` recipe sets the env var then exec's `claude`) | One recipe per repo. Requires `just` already installed (cortex-command already requires this). | Only via `just launch` | None | User invokes `claude` directly → host scope. | All shells |
| **`mise` env var** (similar to direnv) | Install mise once. Add `.mise.toml` per repo. | Automatic on `cd` | Explicit trust on first use | Same as direnv | All shells |

### 5.2 Recommended primary + fallbacks

**Primary: direnv**, for the following reasons:
- The clarified intent already specifies it.
- It is the dominant per-directory env var injection tool in the wider dev ecosystem (mentioned in 3 of the 4 audited GitHub issues as "the workaround we already tried for permissions").
- Its trust model (explicit `direnv allow`) prevents accidental scope swaps when checking out unfamiliar branches or pulling from another machine.
- Automatic on `cd`, no need to remember to invoke a specific command.

**Fallback A: shell alias** for users who don't want direnv. Documented as a one-liner. Trade-off: works only in the shell where the alias is defined; no trust check; computes the shadow path from `$PWD` so it works for any repo without per-repo setup.

**Fallback B: wrapper script committed to the repo** at `./bin/claude` (or any name). This is the most "doesn't require any global setup" option for users who refuse to install direnv AND don't want to modify their shell profile. Trade-off: only works when the user invokes `./bin/claude` explicitly, not when they type `claude`. For users who muscle-memory `claude`, this fails silently (host scope). Pros: completely opt-in, repo-committed, no global state.

The clarified intent mentions `just launch` as a fallback, which is essentially the same shape as Fallback B (a per-repo invocation that the user has to remember to use). `just launch` has the small advantage of not needing a `bin/` directory but requires `just` to already be installed. The docs can mention it briefly as a variant.

### 5.3 Why NOT mise

`mise` is functionally equivalent to direnv for this purpose, and is mentioned in upstream issue #12962 by skorfmann as a workaround. We don't recommend it as primary for two reasons:
1. Adding it as a second recommended path doubles the docs surface for no functional gain.
2. The clarified intent already specifies direnv.

We can mention mise in a single line as "users who already have mise installed can use `[env]` in `.mise.toml` instead of `.envrc`" without expanding the docs surface.

---

## 6. Concrete budget for the "minimal wait-oriented page" hot outcome

This section is included even though §1.4 classified the audit as **warm** (so the hot shape will not ship). Including it future-proofs the spec phase against re-classification — if the audit somehow flips to hot during spec, the spec writer has a defensible budget to reach for.

**Hot-outcome shape (would-be, not shipping under warm classification):**

- **Title**: "Per-repo permissions: interim workaround"
- **Total length**: ~80 lines of markdown, ~600 words
- **Sections**:
  1. **Status preamble** (3 paragraphs, ~150 words): "Claude Code does not natively support per-repo scope override. Anthropic is tracking this in #12962 and #26489. This page documents an interim workaround. Once upstream lands, this page will be deprecated. Watch [these issues] for updates."
  2. **One-snippet workaround** (≤20 lines of bash): the minimum hand-edit a user needs to copy-paste — `cp -R ~/.claude ~/.cortex/repo-shadows/foo && rm ~/.cortex/repo-shadows/foo/settings.json && echo '{"permissions":{"allow":[],"deny":["..."]}}' > ~/.cortex/repo-shadows/foo/settings.json && export CLAUDE_CONFIG_DIR=~/.cortex/repo-shadows/foo`. One snippet, no fallbacks.
  3. **One-sentence troubleshooting** (1–2 sentences): "If Claude Code still uses your global allow list, verify `echo $CLAUDE_CONFIG_DIR` returns the shadow path before launching. Several Claude Code subsystems (skills, /context) do not fully honor `CLAUDE_CONFIG_DIR` — see issue #36172."
  4. **Cross-link to the upstream issues**: 4 bullet links, no body text.

That's it. No walkthrough. No fallbacks section. No explanation of trade-offs. The page exists so users who need the capability today have a path; the page is **not** a polished pattern doc.

Concrete numbers under hot:
- Paragraphs: 4 (status preamble: 3, workaround intro: 0, troubleshooting: 1, cross-links: 0).
- Lines of hand-edit snippet: ≤20.
- Links: 4 upstream issue links + 1 README cross-link = 5 total.
- Word count: ~600 words.
- Total file size: ~3 KB.

**Warm-outcome shape (the shape we ARE shipping)**:
- ~250 lines of markdown, ~2000 words.
- Sections: preamble with audit findings + watch list, mechanism explanation, walkthrough (`cp` → write fresh settings → set env var → verify), direnv integration, fallbacks (shell alias, wrapper script), troubleshooting (the 11 failure modes from §4 condensed to a 1-paragraph-each list), known limitations, cross-links.
- Failure modes section is the longest part — criticality=high demands explicit enumeration.

The spec phase will pin down the warm-shape word count. Research's role is to confirm that the warm shape is achievable in 2000 words without losing the failure-mode coverage (it is — §4 above is ~1500 words and could compress to ~800 in the published doc by trimming research-only context).

---

## 7. Recommended page outline (warm shape, for spec to refine)

```
# Per-repo permissions

[← Back to README]

**For:** Cortex-command users who want a single repo to have a different
Claude Code allow list, hook set, or sandbox config than their global setup.
**Assumes:** You have cortex-command installed via `just setup` and are
comfortable editing dotfiles.

## Status (April 2026)

[2-paragraph audit summary citing #12962 and #26489 by name with link.
Warm framing: "Anthropic is aware. Sustained community demand, no
commitment yet. This pattern is the documented workaround until upstream
lands. Watch the linked issues for updates."]

## How it works

[2 paragraphs: CLAUDE_CONFIG_DIR is an official Claude Code env var that
points the CLI at an alternate user-scope dir. Combine with direnv to set
it automatically per-repo. Result: a per-repo "shadow" of ~/.claude/ that
overrides the user scope without touching ~/.claude/ itself.]

## Setup (with direnv)

[Steps: install direnv, create the shadow directory, write a fresh
settings.json, write .envrc, run direnv allow, verify.]

## Setup (without direnv)

### Shell alias fallback
[3 lines.]

### Wrapper script fallback
[5 lines.]

## Verify which scope is active

[Pre-launch verification: echo $CLAUDE_CONFIG_DIR.
Note that /context lies — link to #38641.]

## Limitations and known issues

[Bulleted list of the §4 failure modes, condensed:
- The cp -r symlink trap (with the explicit mitigation)
- /setup-merge writes to host scope — do not run from shadowed shell
- Shadow goes stale when host updates
- Skills under $CLAUDE_CONFIG_DIR/skills/ not guaranteed (link #36172)
- bin/audit-doc and bin/count-tokens fall back to host
- evolve auto-memory reads host
- /context misreports active path]

## Tearing down

[rm the shadow dir, rm the .envrc, direnv reload.]

## Watch these upstream issues

[#12962, #26489, plus the CLAUDE_CONFIG_DIR-specific bugs #36172, #38641, #34800.]
```

This is a 250-line, ~2000-word page. Spec will pin numbers; research recommends this shape.

---

## Open Questions

- **Q1: Should the docs page recommend `cp -R` or `cp -RL`?** Resolved: recommend `cp -R` (preserves symlinks, so the shadow inherits skill/hook updates), with an explicit "now `rm` the top-level files you want isolated, starting with `settings.json`" follow-up step. `cp -RL` produces a frozen snapshot which is the wrong default for an evolving cortex install.

- **Q2: Should the docs warn against running `/setup-merge` from a shadowed shell, or should we file a code fix to make `/setup-merge` honor `CLAUDE_CONFIG_DIR`?** Resolved (split): the ticket is docs-only, so the page MUST include the warning. A separate follow-up backlog item should be filed to make `merge_settings.py` and `justfile` honor `CLAUDE_CONFIG_DIR`. That follow-up is out of scope for ticket #065 and should not block shipping the docs.

- **Q3: What is the right shadow directory location? `~/.cortex/repo-shadows/<repo>/` or `<repo>/.claude-shadow/` or something else?** Resolved: recommend `~/.cortex/repo-shadows/<basename>/` (outside the repo). Reasoning: keeping shadows out of the repo means they don't pollute `git status`, don't leak into commits, and survive `git clean -fdx`. The drawback is that the shadow is not version-controlled per-repo, but that drawback is unavoidable since shadows contain machine-specific paths and tokens. The docs can mention `~/.config/cortex/repo-shadows/` as an XDG-compliant alternative for users who prefer it.

- **Q4: Should the page recommend writing the shadow's `settings.json` from scratch or as a delta from `~/.claude/settings.json`?** Resolved: recommend from scratch with a minimal allow list. The whole point of the shadow is to NOT inherit the host's allow list. A delta-based approach (start from host, remove rules) would defeat the purpose. The page should include a 5–10 line example minimal `settings.json` with `permissions.allow: []`, `permissions.deny: [...standard cortex deny rules...]`, and `sandbox.enabled: true` if the repo uses sandbox.

- **Q5: Should the page document the verify-which-scope-is-active step as `echo $CLAUDE_CONFIG_DIR` or as a more elaborate `lsof` check?** Resolved: lead with `echo $CLAUDE_CONFIG_DIR` (one line, works pre-launch, no privileges needed). Mention `lsof -p $(pgrep -n claude)` as a "verify after launch" alternative for paranoid users.

- **Q6: Should the page link to the discovery research artifact at `research/user-configurable-setup/research.md`?** Resolved: yes, in a "Background" footer link, not the main body. Users who want the rationale (DR-1, DR-7, DR-8) can read the discovery research; users who just want the steps shouldn't have to.

- **Q7: Should the failure-mode list include all 11 from §4.11, or only the top 4 critical/medium?** **Deferred**: will be resolved in Spec by asking the user. Trade-off: full list is more honest but adds 30+ lines to the page; truncated list is shorter but hides known footguns. Spec phase should ask the user to pick a target page length and reverse-engineer which failure modes fit.

- **Q8: Should the spec ticket include filing follow-up backlog items for the `/setup-merge`, `bin/`, and `evolve` `CLAUDE_CONFIG_DIR` honoring fixes, or are those entirely separate tickets the user files when they want them?** **Deferred**: will be resolved in Spec by asking the user. Recommendation: spec should at least LIST the follow-up items as "out of scope but worth filing" so the user can decide. The docs ticket itself does not block on those follow-ups.

---

## Artifact Summary

The docs page can ship in its full warm shape and is the primary documented mechanism for per-repo permission scoping in cortex-command, with the following load-bearing findings:

1. **DR-7 audit verdict: WARM.** 80 combined +1 reactions across the two open upstream issues (#12962 with 50, #26489 with 30). Both open. Two of the four originally listed (#37344, #35561) are CLOSED as duplicates. Zero Anthropic engagement: no PRs, no triage labels, no staff comments, no roadmap mention, no release notes touching the area in the past 3 months. Sustained community demand without any Anthropic commitment maps cleanly to "warm" — ship the full pattern docs with a "watch these issues" preamble. Do not collapse to the minimal wait-oriented shape.

2. **`CLAUDE_CONFIG_DIR` is partially honored.** The official docs say it scopes "settings, credentials, session history, and plugins." Open upstream bugs (#3833, #36172, #38641, #34800, #42217, #44866) show that `skills/`, `commands/`, `ide/`, MCP `.mcp.json`, and `/context` display path do NOT reliably move with the env var. The docs page must call this out as a known limitation rather than imply a clean swap. The mechanism CAN reliably deliver the commissioned per-repo permissions use case (settings.json IS reliably scoped). It CANNOT deliver per-repo skill/hook disable until upstream issue #36172 is resolved.

3. **The `cp -r` symlink trap is the most severe failure mode.** Verified empirically on this machine: `~/.claude/settings.json`, `statusline.sh`, `notify.sh`, `CLAUDE.md` are all symlinks back into the cortex-command repo. macOS `cp -R` defaults to `-P` (preserve symlinks), so a naive `cp -r ~/.claude ~/.cortex/repo-shadows/foo` produces a shadow whose `settings.json` is the SAME file as the host's. Mutating it mutates the host. The user gets zero warning. The docs MUST instruct users to `rm` the host-symlinked top-level files (at minimum `settings.json`) and write fresh standalone replacements after the copy.

4. **`/setup-merge` and the entire `justfile` ignore `CLAUDE_CONFIG_DIR`.** They hardcode `~/.claude/` everywhere — `merge_settings.py` line 113 onward, `justfile` lines 57–833. Running `/setup-merge` from inside a shadowed shell silently writes to the host scope, not the shadow. This is a bug to file as a follow-up backlog item, but the docs page must warn against the foot-gun in the meantime.

5. **The page goes at `docs/per-repo-permissions.md`** with a markdown audience-line header matching the existing `docs/setup.md` template, with cross-links added to `README.md`'s Documentation table, `CLAUDE.md`'s Symlink Architecture section, and `docs/setup.md`'s Customization section. Recommended warm shape: ~250 lines, ~2000 words, with the 11 failure modes from §4.11 condensed into a Limitations section.

6. **direnv is the right primary recommendation** with shell alias and `./bin/claude` wrapper script as documented fallbacks. mise gets a one-line mention. `just launch` is mentioned as a variant of the wrapper-script approach for users who already have `just` installed (which all cortex-command users do).
