# Research: Non-destructive CLAUDE.md strategy

## Epic Reference

Epic research at `research/shareable-install/research.md` covers the full shareability initiative (tickets 003–007). This ticket implements DR-4: deploy cortex-command's global agent instructions without overwriting the user's existing `~/.claude/CLAUDE.md`, and refactor `claude/Agents.md` to separate generic from cortex-specific content.

---

## Codebase Analysis

### Files that will change

| Path | Change |
|------|--------|
| `claude/Agents.md` | Split into two files; cortex-specific half stays here |
| `claude/rules/global-agent-rules.md` | New file — generic rules for any Claude Code user |
| `justfile` | `deploy-config` recipe updated to deploy `~/.claude/rules/cortex-command.md` symlink instead of `~/.claude/CLAUDE.md` symlink |
| `justfile` | `check-symlinks` recipe updated to verify `~/.claude/rules/cortex-command.md` (not `~/.claude/CLAUDE.md`) |
| `docs/setup.md` | Update to reflect new non-destructive strategy and split architecture |
| `README.md` | Update backup warning section (lines 86-95) |

### Existing symlink deployment pattern

All config is deployed as individual file/directory symlinks via justfile recipes:
- `claude/settings.json` → `~/.claude/settings.json`
- `claude/reference/*` → `~/.claude/reference/`
- `hooks/*` → `~/.claude/hooks/`
- Skills/directories → `~/.claude/skills/`
- `claude/Agents.md` → `~/.claude/CLAUDE.md` (**current, to change**)

The proposed change follows this same pattern, replacing the CLAUDE.md symlink with a rules/ symlink:
- `claude/rules/global-agent-rules.md` → `~/.claude/rules/cortex-command.md`

The `deploy-config` recipe (justfile lines 85-116) handles config file deployment with conditional merge logic already present for `settings.local.json`. The `ln -sf` pattern used throughout is idempotent by design.

### Current `claude/Agents.md` content classification

| Section | Classification | Reason |
|---------|---------------|---------|
| Git Commands: Never Use `git -C` | **Cortex-adjacent** | Exists because of cortex-command's Bash allow rule structure; good general advice but contextually motivated by cortex-command's permission architecture |
| Compound Commands: Avoid Chaining | **Cortex-adjacent** | Same as above — general good practice but framed around cortex-command's allow rule matching |
| Git Commits: Always Use `/commit` Skill | **Cortex-specific** | References `/commit` skill (cortex-command-only); GPG signing references machine-specific setup |
| Settings Architecture | **Cortex-specific** | "symlinked from cortex-command/claude/settings.json" is only true after full install |
| Conditional Loading | **Cortex-specific** | References cortex-command skills by name (`/skill-creator`), paths under `~/.claude/reference/` deployed by this repo |

**Key question** (see Open Questions): The "Git Commands" and "Compound Commands" sections are defensively correct for any Claude Code user, but were written with cortex-command's permission architecture in mind. Need to decide whether they go in the generic file with added context, or stay cortex-specific.

### Root-level `Agents.md`

`/Agents.md` at repo root is a separate file (~60 lines of project README material — repository structure, symlink architecture, commands, dependencies). It is not global agent instructions and is not affected by this ticket.

### Integration points

- **`check-symlinks` recipe** (justfile lines 430-477): hardcodes expected symlink paths. Must be updated atomically with the split to check `~/.claude/rules/cortex-command.md` instead of `~/.claude/CLAUDE.md`.
- **`just setup-force`** (destructive path for repo owner): currently deploys `~/.claude/CLAUDE.md` symlink. After split, must be updated to deploy the appropriate file(s) — otherwise repo owner runs different active instructions than new users, making new-user path untestable.
- **Ticket 006** (`just setup` additive): must enumerate `~/.claude/rules/cortex-command.md` as a classifiable deployment target (`new`/`update`/`conflict`). The current ticket 006 acceptance criteria only mention `~/.claude/CLAUDE.md`.

---

## Web Research

### DR-4 resolved by official documentation

`~/.claude/rules/` user-scope loading is **officially documented by Anthropic**:

> "Personal rules in `~/.claude/rules/` apply to every project on your machine... User-level rules are loaded before project rules, giving project rules higher priority." — [code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory)

CLI symlink following in `~/.claude/rules/` is confirmed working in practice (GitHub issue #13914).

**Caveat**: `~/.claude/rules/` does not currently exist on this machine. Documentation confirms the feature works; live verification (per ticket's acceptance criteria) is still required before implementation begins.

### CLAUDE.md loading hierarchy (official)

1. `/Library/Application Support/ClaudeCode/CLAUDE.md` — managed policy, cannot be excluded
2. `~/.claude/CLAUDE.md` — user scope, all projects
3. `~/.claude/rules/*.md` — user-level rules, loaded before project rules
4. `./CLAUDE.md` / `./.claude/CLAUDE.md` — project scope
5. `./.claude/rules/*.md` — project-scope rules

### `@import` syntax: confirmed working with caveats

- Syntax: `@path/to/file` — absolute paths (`@/etc/file`) and tilde paths (`@~/...`) supported in docs
- Maximum recursion: 5 hops
- **Known regression (issue #8765, closed NOT_PLANNED)**: `@~/.claude/` import paths silently fail — the file does not appear in `/context` output. Specific to paths inside the `.claude/` subdirectory.
- **Tilde expansion bug (issue #19531)**: Node.js does not treat `~` as an absolute path, causing tool failures with `@~/` imports in some contexts
- **Approval dialog**: fires once per project on first encounter of external imports — UX friction for an install-time injection

**Key finding**: The `@~/.claude/` import approach (which would be the natural fallback path, pointing to a file inside `~/.claude/`) is specifically broken by a known, NOT_PLANNED bug. If the fallback is needed, it must use a path OUTSIDE `~/.claude/`.

### VSCode extension known issue

`~/.claude/rules/` is not loaded by the VSCode extension (issue #13914). This affects users of the extension only. Out of scope for this ticket but worth documenting.

---

## Requirements & Constraints

### From `requirements/project.md`

- "Global agent configuration (settings, hooks, reference docs)" is explicitly in scope
- "Multi-agent instructions" are a core feature area
- Complexity must earn its place; simpler solution is correct when in doubt
- Project is personal tooling shared publicly for others to clone or fork — shareability is a first-class goal

### From parent epic (003) and sibling ticket (006)

- `~/.claude/CLAUDE.md` **must never be replaced** for new users — this is the primary constraint
- Hook rename to `cortex-*` prefix is handled by ticket 004 (prerequisite)
- Ticket 006 handles collision detection for `just setup`'s additive mode — any new deployment targets from this ticket must be enumerated in 006's classifier
- If the `@import` fallback path is taken: ticket 006 must treat `~/.claude/CLAUDE.md` as a merge target rather than conflict-skip target

### Scope boundaries for this ticket

**In scope**: verify `~/.claude/rules/` user-scope loading, audit and split `claude/Agents.md`, implement symlink deployment in `deploy-config`, update `check-symlinks`, update docs, (if fallback is taken) update ticket 006 acceptance criteria.

**Out of scope**: skill directory symlink bug (#14836), settings.json merge logic (ticket 007), hook file renaming (ticket 004), `just setup` collision detection implementation (ticket 006).

---

## Tradeoffs & Alternatives

### Approach A: `~/.claude/rules/cortex-command.md` symlink (recommended)

Deploy `~/.claude/rules/cortex-command.md` → `claude/rules/global-agent-rules.md`.

**Pros**: Non-destructive by definition. Officially documented. Consistent with existing symlink deploy pattern. No absolute paths baked into user files. `ln -sf` is inherently idempotent. Clean upgrade path — updating the source file updates all deployments.

**Cons**: `~/.claude/rules/` directory does not exist yet on this machine — must be created. Live verification required before implementation.

### Approach B: `@import` injection into `~/.claude/CLAUDE.md` (fallback — do not implement as code)

Append `@/absolute/path/to/claude/Agents.md` to the user's `~/.claude/CLAUDE.md`.

**Pros**: Does not depend on `~/.claude/rules/` feature. Works on older Claude Code.

**Cons**: Hard-codes absolute installation path — breaks if repo moves. Mutates a user-owned file. `@~/.claude/` import has a known regression bug (NOT_PLANNED). Approval dialog fires per project. No repair mechanism if the path becomes stale. More complex idempotency logic required. Not atomic.

**Recommendation**: Do not implement B as code. Document as a manual recovery step for edge cases only.

### Approach C: Deploy both (belt-and-suspenders)

**Rejected**: Double-loads instructions (context waste), invasive, contradicts non-destructive goal.

### Approach D: Manual documentation only

**Rejected**: Instructions don't apply after install without extra user steps — defeats the purpose.

### Agents.md split strategy

**Audience-based split** (recommended over stability-based):
- `claude/rules/global-agent-rules.md` — rules valid for any Claude Code user, regardless of cortex-command install state
- `claude/Agents.md` — cortex-command-specific instructions, deployed to `~/.claude/CLAUDE.md` only for repo owner via `just setup-force`

**Why not stability-based**: Stability is a judgment call that drifts. Audience is a fixed property: either a rule applies to all users or it requires cortex-command. The boundary is unambiguous and doesn't change over time.

**The `setup-force` path**: Repo owner runs `just setup-force` which deploys the full cortex-specific `claude/Agents.md` to `~/.claude/CLAUDE.md`. New users get only the generic rules via `~/.claude/rules/cortex-command.md`. This means repo owner and new users have different active instructions — repo owner has more. This is acceptable: the repo owner also has cortex-command's full infrastructure installed, so the cortex-specific instructions are valid.

---

## Adversarial Review

### Failure modes

**1. DR-4 verification gap**: The machine does not have `~/.claude/rules/` at all. Official documentation confirms the feature works, but the ticket's acceptance criteria explicitly require live verification. Do not implement on documentation alone — the test is 3 commands and takes 2 minutes.

**2. "Generic" rules may carry hidden cortex-command assumptions**: The "Git Commands: Never Use `git -C`" and "Compound Commands: Avoid Chaining" sections exist because of cortex-command's Bash allow/deny rule architecture. A user without cortex-command's `settings.json` has no such rules — the instructions are still defensively good advice, but the *framing* assumes an infrastructure the user may not have. The generic file should either (a) include these as general best-practices without referencing cortex-command's permission system, or (b) keep them in the cortex-specific file. This decision needs to be made at spec time.

**3. Ordering hazard**: If the rules/ symlink is deployed before the Agents.md content audit is complete, the unrefactored cortex-specific content (Settings Architecture, etc.) would be globally injected into all users' sessions. The split and the deploy must happen atomically in the same commit.

**4. `check-symlinks` and `setup-force` must update atomically**: Any PR creating the split must also update `check-symlinks` to verify `~/.claude/rules/cortex-command.md` and update `setup-force` to deploy the correct file(s). These cannot be separate follow-up PRs.

**5. Ticket 006 scope gap**: `~/.claude/rules/cortex-command.md` is a new deployment target that ticket 006's collision detection classifier does not enumerate. Must be added to 006's acceptance criteria.

**6. `@import` absolute path breaks on repo move**: If the fallback is ever taken, the `$(pwd)`-derived absolute path baked into `~/.claude/CLAUDE.md` becomes a dead link if the repo moves. Symlinks self-heal; injected text does not. No repair mechanism exists.

**7. Skill-creator documentation drift**: `skills/skill-creator/SKILL.md` documents the "write once in Agents.md, symlink for each agent" pattern. After the split, this documentation is stale and will mislead future contributors. Must be updated as part of the split PR.

### Assumptions that hold

- `~/.claude/rules/` user-scope loading: confirmed in official docs, likely to work in practice for plain unconditional rules (no `paths:` frontmatter, CLI usage).
- `@~/.claude/` import bug is NOT_PLANNED: reliable enough assumption that implementing the fallback as code is not worth the complexity.
- Symlink deployment is idempotent: `ln -sf` already used throughout the codebase.

---

## Open Questions

- **OQ-1 (blocks implementation)**: Has the live verification test for `~/.claude/rules/` user-scope loading been run? Until it has, the primary implementation path is unverified. *Deferred to implementation phase: user must run the verification test as the first implementation step. If it fails, fall back to approach B documented as manual steps only.*

- **OQ-2 (spec decision)**: Do the "Git Commands: Never Use `git -C`" and "Compound Commands: Avoid Chaining" sections belong in the generic file or the cortex-specific file? They are defensively correct for any Claude Code user but were written for cortex-command's permission architecture. *Requires user decision at spec time.*
