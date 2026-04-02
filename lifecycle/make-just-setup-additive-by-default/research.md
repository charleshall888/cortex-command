# Research: Make `just setup` additive by default

## Epic Reference

This ticket is part of the shareable-install epic. See `research/shareable-install/research.md` for the full epic research — that document covers collision detection rubric (DR-5), settings.json merge strategy (DR-2), and the hook-prefix cascade (DR-3). This research scopes only to the `just setup` / `just setup-force` classification logic and the justfile recipe changes required.

---

## Codebase Analysis

### Files That Will Change

| File | Why |
|------|-----|
| `justfile` — `deploy-bin` (lines 26-41) | Add classification before 7 `ln -sf` calls to `~/.local/bin/` |
| `justfile` — `deploy-reference` (lines 44-49) | **Has no bash shebang** — must add one before classification logic can be added |
| `justfile` — `deploy-skills` (lines 52-59) | Add classification to `ln -sfn` loop for directory symlinks |
| `justfile` — `deploy-hooks` (lines 62-82) | Add classification to two loops (hooks/*.sh + claude/hooks/*) |
| `justfile` — `deploy-config` (lines 85-130) | Replace existing interactive `read -rp` prompts with new/update/conflict classifier; `settings.local.json` block remains unchanged |
| `justfile` — `setup` (lines 10-22) | Print pending conflict summary at end; outcome unchanged but output changes |
| `justfile` — `check-symlinks` (lines 445-491) | Must tolerate skipped conflict targets; also currently static (doesn't loop over skills/) |
| `justfile` — NEW `setup-force` recipe | Explicit destructive alias — calls current deploy-* chain without classification |

### Key Structural Findings

**`deploy-reference` has no bash shebang.** Lines 44-49 are plain `just` recipe commands, not a bash block. `just` runs each line through the system shell sequentially. Bash features (loops, arrays, variables, `set -euo pipefail`) are unavailable without adding `#!/usr/bin/env bash`. This is the only recipe that needs structural change before classification logic can be added.

**`check-symlinks` is static, not dynamic for skills.** Lines 477-480 loop over `skills/*/SKILL.md` to check skill symlinks, but the recipe still hardcodes the other targets. If a target is skipped as a conflict by `just setup`, `check-symlinks` will report it as missing and exit 1. This breaks `just verify-setup`.

**`deploy-config` uses interactive prompts.** Lines 91-98 and 105-113 use `read -rp` to ask the user before overwriting regular files. In additive mode, this prompt is replaced by the new classification behavior (regular file = conflict, skip with message, add to pending list).

**`settings.local.json` is exempt from classification.** Lines 119-130 always write it with jq-merge. However, the current jq expression replaces `allowWrite` entirely (`= [$path]`) rather than appending — this overwrites existing paths if a user has multiple clones. See Open Questions.

### Classification Logic

The correct classify function for a given `target` and expected `source`:

```
1. if target does not exist (! -e and ! -L):         → new
2. if target is symlink && readlink target == source: → update (points to this repo)
3. else:                                              → conflict (regular file, or symlink to elsewhere)
```

Important: `readlink "$target"` with no flags is portable. Current codebase uses `ln -sf $(pwd)/...` which stores absolute paths. This comparison works correctly as long as symlinks are created with absolute paths (current pattern).

Edge case: `! -e && -L` means a broken symlink (dangling). This should be treated as conflict (not new), since overwriting it might hide a configuration error.

---

## Web Research

### Prior Art — Three-State Classification Pattern

The new/already-correct/conflict classification is well-established in dotfile installers:

- **paulirish/dotfiles**: Compares `readlink "$target"` against expected source. Prompts on mismatch. Three output states: already correct, skipped, prompt.
- **holman/dotfiles**: Interactive batch-mode (skip_all / overwrite_all booleans). Most sophisticated UX.
- **benrozsa/dotfiles**: Full additive pattern — checks `-L + readlink ==` for already-correct, backs up conflicts, then installs.
- **stowsh**: `-n` flag for dry-run, `-s` for skip conflicts.

No existing tool implements the full collect-classify-print-pending-list-then-apply pattern. This needs to be built custom with bash arrays.

### readlink Portability

Plain `readlink "$path"` (no flags) is portable across macOS and Linux. `readlink -f` is a GNU extension — unavailable on macOS pre-12.3 (March 2022). Since we only need to compare the stored symlink target string (not resolve canonical paths), plain `readlink` is the correct choice.

### just Mode Control

Three approaches work in `just`:
- **Recipe parameter**: `setup force=""` — explicit, readable, not inherited by sub-recipes
- **Env var at top**: `FORCE := env("FORCE", "")` — inherits automatically
- **Exported parameter**: `setup $FORCE=""` — auto-exports to subshell

For the `setup-force` pattern (an explicit separate recipe), the simplest approach is to have `setup-force` call each deploy-* recipe with the force env var set via `FORCE=1 just deploy-bin`, etc.

---

## Requirements & Constraints

### Mandatory Requirements

- **Zero conflicts on re-run** (from backlog AC): existing owner install where all symlinks point to this repo must classify all targets as `update`, not `conflict`. This is load-bearing for the repo owner's daily workflow.
- **Classify before any changes**: all targets must be classified and reported before any install action begins. The user sees the plan before it executes.
- **`settings.local.json` always written**: exempt from classification, always written with jq-merge for correct `allowWrite` path.
- **`just setup-force` preserves destructive behavior**: unconditional `ln -sf` on all targets, no classification, no prompts.

### Scope Boundary

| In scope (ticket 006) | Out of scope |
|-----------------------|-------------|
| Collision detection and classification in all deploy-* recipes | settings.json content-aware merge (ticket 007 — `/setup-merge`) |
| Pending conflict list printed at end of setup | Conflict resolution UI |
| `just setup-force` alias | Hook prefix migration cascade (complete — ticket 005) |
| `settings.local.json` path write (exempt from classification) | CLAUDE.md merge-target (resolved — 005 used `~/.claude/rules/`) |

### Complexity Budget

Project requirements: "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct." The classification logic is ~30-50 lines of bash total across all recipes. No new tooling dependencies. This is the right scope.

---

## Tradeoffs & Alternatives

### Approach A — Inline classification per recipe

Each deploy-* recipe gets its own classify-then-install loop. No shared code. Recipes remain independently usable and additive.

- **Pro**: No target list duplication. Each recipe is self-contained. Running `just deploy-skills` directly is also additive.
- **Con**: The 3-state classification pattern repeats in each recipe (copy-paste). Harder to collect a unified pending list across all targets.

### Approach B — Monolithic `setup` bash script

`setup` becomes one large bash block that handles all targets directly. Individual deploy-* recipes unchanged (remain destructive). `setup-force` calls the deploy-* chain.

- **Pro**: Classification in one place. Single unified pending list.
- **Con**: Target lists duplicated (defined in deploy-* AND in the monolithic script). Recipes become stale/legacy code. Breaking change for users running individual deploy-* recipes.

### Approach C — Env var flag (FORCE=1)

Each deploy-* recipe checks `${FORCE:-0}`. `setup-force` sets `FORCE=1` before calling the chain.

- **Pro**: Single code path. No target list duplication. Recipes independently usable.
- **Con**: Env var threading in `just` is awkward. Behavior depends on invisible context. Fragile if a user runs individual recipes with mixed env state.

### Approach D — Shared bash helper script

Extract a `classify()` bash function into `bin/setup-helper.sh`. All deploy-* recipes source it.

- **Pro**: DRY, testable helper.
- **Con**: Adds a new file dependency. `source` calls in just bash blocks require careful paths. Adds maintenance surface.

### Recommended: Approach A with explicit `setup-force`

Given the adversarial review findings, Approach C's env var threading is fragile and invisible to users. Approach A (inline per recipe) is the simplest, most explicit path:

1. Add classification inline to each deploy-* recipe (3-state logic, ~8-10 lines per recipe)
2. Create `setup-force` as a recipe that calls the current deploy-* chain directly (no classification)
3. `setup` calls the (now-additive) deploy-* chain, then prints the aggregate pending list

The classification pattern is short enough that repetition (5 copies) is acceptable — especially since each recipe has slightly different target structures (single files vs. loops vs. directory symlinks). Inlining avoids the invisible-env-var problem and keeps each recipe independently readable.

---

## Adversarial Review

### Critical Issues

**`deploy-reference` cannot run bash code without a shebang.** It's the only recipe without `#!/usr/bin/env bash`. Classification logic requires bash features. Must add a shebang block — this is a one-line change but must be done.

**`check-symlinks` will fail if any target was skipped as a conflict.** Currently all 18 hardcoded targets must exist or the recipe exits 1. In additive mode, some targets may legitimately be skipped. `check-symlinks` needs a lenient mode (or must be informed of which targets were skipped) so it doesn't falsely report a conflict-skipped target as a missing symlink. One approach: `check-symlinks` warns rather than fails for targets that are not symlinks pointing to this repo (i.e., known conflicts).

**Interactive prompts in `deploy-config` block CI/CD.** The `read -rp` pattern in lines 91-98 blocks in non-tty environments (CI, piped shell scripts). In the new additive mode, these prompts are replaced by the classification behavior — regular files are automatically conflicts (skipped), no prompt needed. This is actually a simplification.

### High Priority Issues

**`settings.local.json` jq merge replaces rather than appends.** The current expression `.sandbox.filesystem.allowWrite = [$path]` overwrites any existing paths in the `allowWrite` array. A user with multiple clones of cortex-command would lose their other path entries on each setup run. Should use `+= [$path]` with a dedup pass, or check if the path is already present before appending.

**readlink comparison requires absolute paths.** The `update` classification (`readlink "$target" == expected_source`) only works correctly when both sides use absolute paths. Current `ln -sf $(pwd)/...` produces absolute paths. If a user ever creates a symlink manually with a relative path, they'll get a false "conflict." Document the absolute-path requirement and guard against relative-path symlinks in `setup-force`.

**Broken symlinks (dangling) need a fourth classification state.** `! -e && -L` indicates a broken symlink. The current 3-state rubric doesn't handle this — should be treated as conflict (skip with a specific "broken symlink" message) rather than new.

### Lower Priority

**Duplicate hook names across `hooks/` and `claude/hooks/` lack conflict detection.** The second loop overwrites the first if basenames match. Precedence rule (`claude/hooks/` wins) should be documented.

**`settings.local.json.tmp` can be left behind on failure.** The mv operation is atomic on the same filesystem, but if jq itself fails, the `.tmp` file is left. Add cleanup with `trap`.

**Dynamic skill list in `deploy-skills` vs. static in `check-symlinks`.** `deploy-skills` loops over `skills/*/SKILL.md`; `check-symlinks` has a static loop (lines 477-480 check dynamically but are wrapped in a hardcoded recipe). These will diverge if skills are added. Acceptable for now since `check-symlinks` already loops skills dynamically, but worth noting.

---

## Open Questions

- **`settings.local.json` allowWrite append vs. replace**: → **Resolved: fix in this ticket.** Use `+= [$path]` with a dedup pass. Multi-clone correctness improvement, small change, in-scope since we're already touching that code block.

- **`check-symlinks` lenient mode design**: → **Resolved: leave strict.** If a target was skipped as a conflict, `check-symlinks` correctly reports it as missing — signaling unresolved state. Ticket 007 (`/setup-merge`) handles resolution. After running 007, the user re-runs `check-symlinks` to confirm everything is installed. No coupling needed between the two recipes.
