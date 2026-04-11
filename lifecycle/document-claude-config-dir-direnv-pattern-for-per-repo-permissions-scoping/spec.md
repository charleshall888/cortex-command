# Specification: Document CLAUDE_CONFIG_DIR + direnv pattern for per-repo permissions scoping

## Problem Statement

The cortex-command agentic framework currently offers no documentation for users who want to scope Claude Code permissions per repo. The commissioned use case is *"only use project permissions in this repo, ignore global allows."* Claude Code's settings merge is strictly additive (arrays concatenate, no negation, `deny` is monotonic), so layering alone cannot deliver subtraction. The supported mechanism is `CLAUDE_CONFIG_DIR` pointing at a shadow user scope, combined with direnv (or a shell alias / wrapper script) for per-directory env var injection.

Research §DR-7 audit (verdict: **WARM** as of 2026-04-10 — sustained community demand at ~80 combined reactions across anthropics/claude-code#12962 and #26489, zero Anthropic-side engagement in the past 3 months) supports documenting the pattern now with a "watch these upstream issues" preamble.

This ticket is deliberately scoped as **docs-only, one commit**. A large infrastructure scope (85+ edits to `justfile`, `merge_settings.py`, `evolve`, `bin/`, `claude/settings.json` to make cortex-command tooling honor `CLAUDE_CONFIG_DIR` transparently) was considered during refinement and **explicitly deferred** — see Non-Requirements for rationale. The docs warn about each foot-gun instead of fixing it; if any specific foot-gun starts biting in actual use, file a targeted follow-up ticket then. This matches the sibling ticket #064's foundation-cleanup descope and the project's "complexity must earn its place" principle.

## Requirements

**MoSCoW classification**: All 3 requirements below are **must-have**. R1 delivers the docs section itself. R2 is the one pre-flight safeguard that protects against shipping stale framing if upstream activity has moved between spec approval and execution. R3 is the minimal cross-link so the new section is discoverable. There are no should-haves; won't-do items are in `## Non-Requirements`.

1. **A "Per-repo permission scoping" section exists in `docs/setup.md` with all required content**: AC — all seven of the following checks pass against `docs/setup.md`. Each targets a distinct content element; the section fails acceptance if any one is missing.
   1. **Section heading present**: `grep -cE '^##+ .*[Pp]er-repo permission' docs/setup.md` ≥ 1.
   2. **WARM preamble references both primary upstream issues**: `grep -q 'issues/12962' docs/setup.md` AND `grep -q 'issues/26489' docs/setup.md`.
   3. **direnv walkthrough present**: `grep -c '\.envrc' docs/setup.md` ≥ 2 AND `grep -c 'CLAUDE_CONFIG_DIR' docs/setup.md` ≥ 4.
   4. **`cp -R` symlink trap warning present with explicit `rm` instructions**: `grep -cE 'cp -[rR]' docs/setup.md` ≥ 1 AND `grep -cE 'rm [^[:space:]]+' docs/setup.md` ≥ 1 AND `grep -c 'symlink' docs/setup.md` ≥ 2.
   5. **Limitations list covers all 5 distinct foot-guns** — each of these `grep -qi` checks must pass:
      - `grep -qi 'setup-merge' docs/setup.md` (do not run /setup-merge from a shadowed shell)
      - `grep -qi 'just setup' docs/setup.md` (re-run setup from the shadow shell when host changes)
      - `grep -qi 'notify' docs/setup.md` (notify hook fires from host literal path)
      - `grep -qi 'evolve\|auto-memory\|audit-doc\|count-tokens' docs/setup.md` (tooling walks from host)
      - `grep -qiE 'concurrent|multiple sessions|scope confusion|which scope' docs/setup.md` (scope-active confusion)
   6. **Upstream partial-support limitations noted**: `grep -qiE '#36172|skill.*lookup|partially honored' docs/setup.md` (Claude Code's own partial CLAUDE_CONFIG_DIR honoring).
   7. **Background link to research artifact**: `grep -c 'research/user-configurable-setup/research.md' docs/setup.md` ≥ 1.

2. **DR-7 audit re-check at execution time, before any file edits**: AC — interactive/session-dependent. As the first implementation step, the executing agent runs:
   ```bash
   gh issue view 12962 --repo anthropics/claude-code --json state,comments,labels,assignees > /tmp/dr7-12962-$$
   gh issue view 26489 --repo anthropics/claude-code --json state,comments,labels,assignees > /tmp/dr7-26489-$$
   ```
   and compares against the recorded WARM classification (both issues open, no Anthropic assignee, no roadmap label, no linked closing PR). If the audit STILL reads WARM, proceed with the docs as specified below. If the audit has materially changed (e.g., Anthropic PR linked, staff assignee added, state → closed with upstream landing, explicit roadmap label), halt execution and report to the user — do NOT ship docs that stake credibility on a stale classification. Rationale for interactive/session-dependent: the AC is a conditional branch on external GitHub state that cannot be verified from file contents.

3. **Section length and location are bounded**: AC — two checks:
   1. **Section added to existing `docs/setup.md`, not a new file**: `test -f docs/per-repo-permissions.md` returns 1 (i.e., the separate page does NOT exist — the content lives in `docs/setup.md`).
   2. **Section length is bounded**: the section body (between the heading and the next `## ` heading) is between 30 and 80 lines:
      ```bash
      awk '/^##+ .*[Pp]er-repo permission/{flag=1; c=0; next} flag && /^## /{exit} flag{c++} END{print c}' docs/setup.md
      ```
      Output must be between 30 and 80 inclusive. Rationale: the minimum viable scope is ~40 lines; the envelope is 30–80 to give the writer room without permitting a full-page expansion that would re-introduce the 250-line scope this ticket deliberately descoped from.

## Non-Requirements

- **A new `docs/per-repo-permissions.md` page.** The content lives as a section inside the existing `docs/setup.md`, not a new file. Discoverability is delivered via the table-of-contents or customization section of `docs/setup.md` — no cross-links from README or CLAUDE.md.
- **Infrastructure fixes to make `CLAUDE_CONFIG_DIR` transparently honored in cortex-command tooling.** The explicit deferrals:
  - `justfile` continues to hardcode `~/.claude` in all 69 locations. Users who want a shadow run `just setup` from a non-shadowed shell once, then launch Claude Code under the shadow. Documented as a foot-gun.
  - `.claude/skills/setup-merge/scripts/merge_settings.py` continues to hardcode `~/.claude`. Users are told NOT to run `/setup-merge` from a shadowed shell. Documented.
  - `skills/evolve/SKILL.md` continues to reference `~/.claude/projects/...` in its memory-path prose. Auto-memory under a shadow writes to the host scope. Documented.
  - `bin/audit-doc` and `bin/count-tokens` continue to walk from `cwd` and fall back to `~/.claude`. Users in a shadow get host results. Documented.
  - `claude/settings.json` continues to reference `~/.claude/notify.sh` literally. The notify hook always fires from the host path. Documented.
  Each of these is a real foot-gun the docs explicitly warn about. If any one of them starts biting in actual use, file a targeted follow-up ticket at that point. Let friction prove the need.
- **Cross-links from `README.md` or `CLAUDE.md`.** Discoverability lives inside `docs/setup.md` only. If the section starts being hard to find in practice, add a one-line pointer from README later.
- **A `bin/cortex-shadow-config` generator** or any new CLI surface. Manual `cp -R` with documented `rm` instructions is the smallest viable delivery.
- **Installing direnv for users.** The docs reference direnv as the recommended integration but do not bundle or configure it. Users without direnv follow the shell-alias or `./bin/claude` wrapper path documented in the same section.
- **SessionStart hook mutating `~/.claude/settings.json`** (Option D). Explicitly rejected by research DR-1. DR-8 preserves the 10-requirement real scope for any future reconsideration.
- **Fixing Claude Code's own partial `CLAUDE_CONFIG_DIR` handling** (#36172 skills lookup, #38641 `/context` display, #42217 MCP config, #34800 ide lock). Upstream-owned; documented as limitations.
- **A `cortex doctor` diagnostic CLI.** Deferred.
- **Any regression test infrastructure.** Docs-only changes don't need `just check-symlinks` gates.
- **Fixing pre-existing unrelated bugs** surfaced during research (e.g., the `conflicts+=` ordering bug in deploy-config).

## Edge Cases

- **macOS `cp -R` symlink preservation trap**: the single most severe footgun. Research §4.1 verified empirically that `~/.claude/settings.json`, `statusline.sh`, `notify.sh`, and `CLAUDE.md` are all symlinks back into the cortex-command repo. `cp -R` preserves symlinks by default on macOS, so a naive shadow copy shares files with the host. Mutating the shadow mutates the host. The section MUST lead with this warning and include the exact `rm` commands the user runs post-copy.
- **User runs `/setup-merge` from a shadowed shell**: silently writes to `~/.claude/`, bypassing the shadow. Documented as a don't-do; the docs list this as foot-gun #1.
- **User re-runs `just setup` from a non-shadowed shell after shadowing**: the host scope gets updated; the shadow does not. Documented: re-run `just setup` from the shadow shell, or `cp -R --update` the shadow.
- **Notify hook under shadow**: `claude/settings.json` references `~/.claude/notify.sh` literally. Under a shadow, the hook fires from the host path if a host-side `~/.claude/notify.sh` exists, or fails silently if it doesn't. Documented as a limitation; workaround is to keep a host install alongside the shadow.
- **DR-7 audit becomes stale between spec approval and execution**: R2 catches this at execution time.
- **User's `.envrc` loads but Claude Code was already running**: direnv loads on `cd`, but Claude Code reads `CLAUDE_CONFIG_DIR` at launch. Quit and relaunch.
- **User removes `.envrc` or revokes direnv trust**: session falls back to `~/.claude`.
- **Concurrent Claude Code sessions in different repos with different `CLAUDE_CONFIG_DIR` values**: each session honors its own launch env.

## Changes to Existing Behavior

- **ADDED**: New section in `docs/setup.md` titled "Per-repo permission scoping via `CLAUDE_CONFIG_DIR`" (or similar). 30–80 lines. Covers the WARM preamble with upstream issue links, a direnv walkthrough with `.envrc` example, the `cp -R` symlink trap warning with explicit `rm` instructions, a limitations list covering all 5 cortex-command foot-guns plus upstream Claude Code partial-support bugs, and a background link to `research/user-configurable-setup/research.md`.
- **No other files modified.** `justfile`, `merge_settings.py`, `evolve/SKILL.md`, `bin/audit-doc`, `bin/count-tokens`, `claude/settings.json`, `README.md`, `CLAUDE.md` — all unchanged.

## Technical Constraints

- **Research DR-7 verdict is WARM** as of 2026-04-10. The section ships with the WARM-shape preamble ("watch these upstream issues"), subject to the execution-time re-check in R2.
- **The `cp -R` symlink trap must lead the limitations** — it is the single most severe footgun and the most likely cause of data loss if the user ignores it. Research §4.1 verified the trap empirically on this machine.
- **Limitations must be listed as foot-guns, not fixes.** The docs say "don't do X" or "X has the following failure mode"; they do NOT say "cortex-command handles X for you." That would be a lie, because this ticket deliberately leaves the infrastructure fixes unshipped.
- **Portable shell in ACs**: all AC grep/awk snippets work under BSD coreutils (macOS default). No GNU-only sed address forms. awk used for line-range extraction.
- **No cross-links to this section from README or CLAUDE.md.** Discoverability is inside `docs/setup.md` only; adding more surface would expand scope for minimal benefit. If the section proves hard to find, add the cross-links in a follow-up.
- **One commit.** The entire deliverable is a single edit to `docs/setup.md`; it ships as one commit matching the `/commit` skill style.
- **Do not opportunistically fix pre-existing bugs** surfaced during research (e.g., `conflicts+=` / `conflicts=()` ordering bug in `deploy-config`). Scope is strictly docs.
- **Recommendation wording for fallback**: the section should recommend `cp -R` (preserves symlinks so the shadow inherits repo-sourced files), followed by explicit `rm` of the host-shared top-level files (at minimum `settings.json`, `statusline.sh`, `notify.sh`, `CLAUDE.md`) and a fresh minimal `settings.json` written from scratch. Do NOT recommend `cp -RL` as a blanket fix — it creates a frozen snapshot which is the wrong default for an evolving cortex install.

## Open Decisions

None. All prior research questions resolved. Scope descoped during refinement to match sibling ticket #064's foundation-cleanup pattern. No implementation-level ambiguity remains.
