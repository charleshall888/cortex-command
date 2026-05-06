# Research: Inventory and confirm canonical replacements for every stale skill/doc reference in scope, verify the duplicated-block deletion target, and ground the post-fix verification surface

## Codebase Analysis

### Duplicated block (skills/refine/SKILL.md)

- Verified by `diff <(sed -n '117,136p' skills/refine/SKILL.md) <(sed -n '138,157p' skills/refine/SKILL.md)` returns no output → byte-identical.
- Verified by grep: exactly **two** occurrences of `### Alignment-Considerations Propagation` at lines 117 and 138 (the clarify-critic claim of three was wrong).
- Deletion target: lines 138–157 inclusive (the second copy). Line 137 is the blank-line separator between the two blocks; line 158 begins "After writing `research.md`, update `lifecycle/{lifecycle-slug}/index.md`" which must remain attached to the surviving heading at 117.
- Boundary risk (FM-3 from adversarial): anchor the Edit-tool `old_string` on the heading + body content, not on line numbers, to survive any drift.

### Exhaustive stale-reference inventory (in-scope per user §4 expansion + ticket original 5)

| Reference | Location | Action |
|---|---|---|
| `claude/common.py` | `skills/lifecycle/SKILL.md:3` (description-fence) | → `cortex_command/common.py` (intentional gating-rule correction) |
| `claude/common.py` | `skills/lifecycle/SKILL.md:35` (body, `slugify()` citation) | → `cortex_command/common.py` |
| `claude/common.py` | `skills/backlog/references/schema.md:22` | → `cortex_command/common.py` |
| `claude/common.py` | `docs/overnight-operations.md:101` | → `cortex_command/common.py` |
| `claude/common.py` | `docs/overnight-operations.md:103` | → `cortex_command/common.py` |
| `claude/common.py` | `docs/overnight-operations.md:326` | → `cortex_command/common.py` |
| `claude/common.py` | `docs/backlog.md:121` | → `cortex_command/common.py` |
| `claude/common.py` | `docs/backlog.md:174` | → `cortex_command/common.py` |
| `cortex-worktree-create.sh` (unqualified) | `skills/lifecycle/SKILL.md:378` | → `claude/hooks/cortex-worktree-create.sh` |
| `cortex-worktree-create.sh` (unqualified) | `skills/lifecycle/references/implement.md:206` | → `claude/hooks/cortex-worktree-create.sh` |
| `bin/overnight-status` | `skills/lifecycle/references/implement.md:68` | **DELETE entire sentence** ("This matches the detection pattern used by `bin/overnight-status`.") — token-only deletion would leave grammatical fragment |
| `backlog/generate_index.py` | `skills/lifecycle/references/complete.md:42` | → `cortex_command/backlog/generate_index.py` (preserve `test -f` guard structure) |
| `backlog/generate_index.py` | `skills/lifecycle/references/complete.md:65` | → `cortex_command/backlog/generate_index.py` (preserve `test -f` guard structure) |
| `update_item.py` | `skills/lifecycle/references/clarify.md:113` | → `cortex-update-item` (CLI name) |
| `update_item.py` | `skills/refine/references/clarify.md:119` | → `cortex-update-item` (CLI name) |
| `update_item.py` | `skills/refine/SKILL.md:231` (constraints table row 3, "I should use the lifecycle-slug as the update_item.py argument") | → `cortex-update-item` |
| `update_item.py` | `skills/refine/SKILL.md:232` (constraints table row 4, "If update_item.py fails I can skip it") | → `cortex-update-item` |

Total: 17 substitutions + 1 sentence deletion + 1 block deletion across 8 files.

### Out-of-scope hits surfaced by Agent 1 (NOT to fix in this ticket — flag for follow-up)

- `update_item.py` also lives in: `skills/morning-review/SKILL.md:113`, `skills/morning-review/references/walkthrough.md:469,:600,:601`, `skills/backlog/SKILL.md:66`, and many lines of `docs/backlog.md` (100, 103-104, 121, 157-205).
- `bin/overnight-status` also lives in `lifecycle/morning-report.md:24` (active observability requirements gap report referring to a script that never existed).
- `backlog/generate_index.py` references in `docs/backlog.md` and `skills/backlog/SKILL.md`.

These are NOT in the user's §4 scope-expansion choice (which targeted only `claude/common.py`). The agent should NOT silently fix them — surface to user as a follow-up ticket candidate at completion.

### Auto-mirror regeneration mechanism

- Canonical sources (`skills/`, `hooks/cortex-*`, `claude/hooks/cortex-*`, `bin/cortex-*`) are mirrored byte-identically to `plugins/cortex-core/{skills,hooks,bin}/` by `just build-plugin` (justfile L486-518).
- Pre-commit hook `.githooks/pre-commit` enforces:
  - Phase 1.5: `just check-parity --staged` (SKILL.md-to-bin parity linter)
  - Phase 2/3: detects staged canonical-source paths, automatically invokes `just build-plugin`
  - Phase 4: fails commit if `git diff --quiet plugins/` shows mirror drift
- Ordering implication: do NOT run `just build-plugin` ahead of staging. Stage canonical-source edits, let the hook own regeneration.

### Conventions to follow

- Single Edit per substitution (rejected: sed batch — cannot dedup the structural block; risks unintended hits in CHANGELOG/lifecycle event logs that record history).
- One commit for the full set of mechanical substitutions + the dedup deletion (rejected: per-token commits — multiplies review load with no atomicity benefit, multiplies mirror-regen).
- Commit message must call out the description-fence behavior change at `skills/lifecycle/SKILL.md:3` (see SEC-1 in Adversarial Review).
- Use `/cortex-core:commit` per CLAUDE.md, no `--no-verify` bypass.

## Web Research

### Description-field semantics (load-bearing)

The SKILL.md `description:` field is injected into Claude Code's system prompt at startup; only `name` + `description` are pre-loaded. Claude matches incoming user requests against these descriptions to decide which skill to invoke (Anthropic best-practices doc: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices; Skills overview: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview).

Implication: a "Required before editing any file in `claude/common.py`..." clause inside the description is prose used by the LLM as a triggering hint. The path is *semantically* load-bearing — the LLM reads it when deciding whether to fire the skill on a file edit. If the path doesn't exist, the skill still loads (no schema-level filesystem validation), but the routing prose lies to the model.

**Confirmed: replacing `claude/common.py` with `cortex_command/common.py` in skills/lifecycle/SKILL.md:3 is a structurally meaningful gating-rule correction, not cosmetic.** This is the user-acknowledged "intentional behavior change" called out in the F3 disposition of events.log.

### Verification tooling

- **ripgrep** is the right tool for stale-reference inventory: `rg -n 'claude/common\.py' -t md` honors `.gitignore` and is faster than sed/find. ast-grep is for AST/structural code refactors and offers no advantage for prose-embedded path strings (https://ast-grep.github.io/advanced/tool-comparison.html).
- **python-frontmatter** for YAML-frontmatter parse verification: `import frontmatter; frontmatter.load("skills/lifecycle/SKILL.md")` raises on malformed YAML (https://python-frontmatter.readthedocs.io/, https://pypi.org/project/python-frontmatter/).
- Cheap alternative without frontmatter dep: `python -c "import yaml; yaml.safe_load(open('skills/lifecycle/SKILL.md').read().split('---')[1])"`.
- **md-dead-link-check** detects file-link breakage in markdown — out of scope here, follow-up ticket if drift recurs (https://pypi.org/project/md-dead-link-check/).

### Anti-pattern: blanket sed across docs tree

`sed -i 's|claude/common.py|cortex_command/common.py|g'` rejected — would over-match into CHANGELOG, lifecycle event logs, archived research, and ticket bodies that intentionally preserve historical references. Line-precise Edit calls preserve adjacent context (e.g., `complete.md:42` test-f guard).

## Requirements & Constraints

### Architectural constraint: dual-source canonical/mirror enforcement

- `requirements/project.md:27`: SKILL.md-to-bin parity enforcement is a pre-commit-blocking failure mode.
- `CLAUDE.md`: canonical sources only — auto-generated mirrors at `plugins/cortex-core/{skills,hooks,bin}/` are regenerated by the pre-commit hook from canonical sources; edit canonical sources only.
- The `.githooks/pre-commit` enforcement runs in 4 phases (parity check → build needed? → build → drift detect). Manual `--no-verify` bypass is the only failure mode that lets drift through.

### Architectural constraint: maintainability through simplicity

- `requirements/project.md` Quality Attributes: "Maintainability through simplicity" — complexity managed by iteratively trimming skills and workflows. Supports the user's §4 scope expansion to all stale `claude/common.py` references rather than fixing only the audit's enumerated 5.

### Scope boundary

- In: 8 files containing 17 substitutions + 1 sentence deletion + 1 block deletion (per inventory above).
- Out: out-of-scope hits surfaced by Agent 1 (`update_item.py` in morning-review/, `bin/overnight-status` in `lifecycle/morning-report.md:24`, etc.). User chose to expand only the `claude/common.py` token, not the others.

### MUST-escalation policy (project CLAUDE.md)

CLAUDE.md MUST-escalation policy applies to *adding* new MUST language without effort=high evidence. This ticket adds no MUST language; the description-fence path correction expands the *factual scope* of an existing rule, not its language strength. Policy does not block.

## Tradeoffs & Alternatives

### Implementation strategy

| Strategy | Pros | Cons |
|---|---|---|
| **A. Single Edit per substitution, one commit (RECOMMENDED)** | Edit's exact-match contract catches ticket-vs-reality drift early; surgical and reviewable; one atomic revert | ~17 Edit calls; relies on pre-commit hook for mirror regen |
| B. sed batch | One-shot, idempotent | Cannot dedup the structural block; over-matches CHANGELOG/archives/event logs; silent over-application is the canonical sed footgun |
| C. Per-token commits | Atomic revert per token; bisect-friendly | Mechanical name swaps have no behavioral coupling; multiplies review load + mirror-regen with no upside |
| D. Skills commit + docs commit + dedup commit | Plugin-mirror regen only on skills commit | Mild benefit; no inter-file dependencies make this immaterial |

**Recommendation: A.** Plus: use Edit's `replace_all` per-file (not multi-file) when a token appears multiple times in one file (e.g., skills/lifecycle/SKILL.md has `claude/common.py` at both line 3 and line 35).

### Verification surface

| Level | Cost | Catches |
|---|---|---|
| Minimum (ticket's grep-zero) | Trivial | Missed token swaps in two named files |
| **+ frontmatter parse (RECOMMENDED)** | One command | YAML breakage in description field (low risk per A-3 below, but cheap) |
| + mirror regen + git diff | Subsumed by pre-commit | Mirror drift |
| + ripgrep -t md sweep across the 8 in-scope files | One command | Missed swaps within scope (catches if Edit silently no-ops) |
| + skill-trigger smoke test | High | Live triggering regression — no harness instrumentation exists for this |
| + e2e refine/lifecycle invocation | Very high | Routing regression — disproportionate for doc-only edits |

**Recommendation: minimum + frontmatter parse + ripgrep sweep across the 8 modified files (NOT repo-wide; see FM-2 in Adversarial).**

### Mirror regeneration ordering

Pre-commit hook auto-runs `just build-plugin` on staged canonical-source paths. Recommendation: **do not pre-run** `just build-plugin`. Stage canonical edits, let the hook regenerate mirrors. Manual pre-run is wasteful and risks staging stale mirror.

**Mitigation (A-2 in Adversarial)**: before the FIRST edit, run `just build-plugin && git diff --exit-code plugins/` to detect any pre-existing drift unrelated to this ticket. If drift exists, surface to user before adding edits.

### Frontmatter-edit safety verdict

The skills/lifecycle/SKILL.md:3 `description:` field is YAML flow-style on a single line. The token `claude/common.py` appears in unquoted backticks (markdown, not YAML-special). Substituting `cortex_command/common.py`:
- Introduces no YAML-special chars (`:`, `"`, `'`, `\n`, `#`, `&`).
- All YAML-significant chars absent from both old and new tokens.
- Provably YAML-safe; no quoting change required.

Still cheap to verify post-edit with `python -c "import yaml; yaml.safe_load(...)"`.

## Adversarial Review

### Failure modes (high-impact)

- **FM-3 (boundary risk on dedup deletion)**: anchor `old_string` on heading text + body content, not line numbers. Verified blank-line at 137 and "After writing" continuation at 158 — deleting 138–157 inclusive is correct, but Edit-tool exact-match on content is safer than line-range awareness.
- **FM-4 (bin/overnight-status removal leaves grammatical fragment)**: implement.md:68 reads *"This matches the detection pattern used by `bin/overnight-status`."* — the entire sentence must be deleted, not just the backticked token. Removing only the token leaves "This matches the detection pattern used by `.`" Substantively meaningless.
- **FM-2 (verification scope)**: ticket's grep-zero check is scoped to two specific files. A repo-wide grep would false-flag ~80+ archive/historical hits and active tickets (e.g., `backlog/110-...md` whose title contains `claude.common`). Verification regex must be scoped to the 8 modified files.
- **FM-6 (out-of-scope hits)**: do NOT extend the fix to `lifecycle/morning-report.md:24` (active observability gap report referencing the never-existed `bin/overnight-status` script) or to `update_item.py` hits in `skills/morning-review/`, `skills/backlog/SKILL.md`, or `docs/backlog.md`. User's §4 expansion was scoped to `claude/common.py` only.

### Security/behavior concerns

- **SEC-1 (description-fence behavior change)**: replacing `claude/common.py` with `cortex_command/common.py` in skills/lifecycle/SKILL.md:3 will now trigger lifecycle-skill gating on edits to the live shared-helpers file (which previously never triggered because the fenced path didn't exist). This IS a behavior change; the commit body must call this out.
- **A-4 (runtime path shift in complete.md fallback chain)**: the test-f guard at complete.md:42/:65 currently emits "via `backlog/generate_index.py`" when the file exists. After the path-fix, `cortex_command/backlog/generate_index.py` always exists (it's part of the package), so the test-f guard always fires the file-path branch and the second-tier `cortex-generate-backlog-index` CLI fallback never fires. Functional behavior is identical (both invocations produce the same index regen) but the emit-message differs. Documented in commit body; not a re-Ask.

### Assumptions to verify mid-implementation

- **A-1 (parity linter false-positives)**: run `just check-parity --staged` BEFORE the agent attempts commit. Surfaces linter false-positives early instead of after editing 8 files.
- **A-2 (pre-existing mirror drift)**: run `just build-plugin && git diff --exit-code plugins/` before the FIRST edit. Surface any pre-existing drift to user; do not fold it into this PR's diff.

### False alarm from adversarial agent

- The adversarial agent's FM-1 ("synthesis lost the ticket's clarify.md targets") is a misread — Agent 1's full inventory DID include skills/lifecycle/references/clarify.md:113, skills/refine/references/clarify.md:119, and skills/refine/SKILL.md:231-232. The synthesis is complete on those targets.

### Recommended mitigations (synthesis)

1. Use Edit's `replace_all` per-file for tokens that appear multiple times in one file.
2. Anchor dedup `old_string` on heading + body content, not line numbers.
3. For bin/overnight-status, delete the whole sentence at implement.md:68.
4. Run drift-baseline check (`just build-plugin && git diff --exit-code plugins/`) before first edit.
5. Run `just check-parity --staged` before commit attempt.
6. Verification: file-scoped grep + frontmatter parse + ripgrep sweep across 8 modified files.
7. Commit body calls out the description-fence behavior change explicitly.
8. No `--no-verify` bypass.

## Open Questions

None — all open questions from clarify-critic were resolved in §4 Q&A (scope-expansion to all `claude/common.py` refs; path-fix for `backlog/generate_index.py`). No new ambiguities surfaced during research.

## Considerations Addressed

- **Description-fence as gating-rule correction (not cosmetic)** — Addressed by Web Research §1 (description-field load-bearing semantics confirmed via Anthropic spec) and Adversarial SEC-1 (behavior-change callout required in commit body).
- **Scope expansion to all `claude/common.py` refs (8 sites total)** — Addressed by Codebase exhaustive inventory (table above) and Requirements §scope-boundary clarification (in: 8 files, out: morning-review/, lifecycle/morning-report.md, etc.).
- **Path-fix for `backlog/generate_index.py` preserving test-f guard** — Addressed by Codebase complete.md:42/:65 substitution table and Adversarial A-4 callout (runtime path shifts from CLI-fallback to file-path-branch; documented in commit body, not a re-Ask).
- **Verification surface beyond grep-zero** — Addressed by Web Research §verification-tooling (python-frontmatter parse + ripgrep sweep) and Tradeoffs §verification-surface (recommended level: minimum + frontmatter + scoped ripgrep).
