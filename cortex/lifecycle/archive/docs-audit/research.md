# Research: Audit docs/ directory to identify gaps and rewrite

## Codebase Analysis

### Files in scope

| File | Size | Quality | Priority |
|------|------|---------|----------|
| `docs/agentic-layer.md` | 23.3 KB | Good | High |
| `docs/overnight.md` | 21.3 KB | Excellent | Medium |
| `docs/interactive-phases.md` | 12.8 KB | Very Good | Medium |
| `docs/backlog.md` | 11.4 KB | Excellent | Low |
| `docs/setup.md` | 11.4 KB | Very Good | Medium |
| `docs/skills-reference.md` | 11.2 KB | Moderate | High |
| `docs/pipeline.md` | 5.6 KB | Moderate | High |
| `docs/dashboard.md` | 3.8 KB | Good | Low |

### Per-file gap analysis

**`docs/skills-reference.md`** — MODERATE (High priority)
- References `serena-memory` skill which does not exist in `skills/` — broken reference
- Claims "30 skills" but only 29 exist; skill count inconsistency vs. `agentic-layer.md` which claims 29 or 34 depending on the section
- No guidance on when to use which skill category; no explanation of overlap between `/dev`, `/lifecycle`, `/overnight`

**`docs/agentic-layer.md`** — GOOD (High priority)
- Skill count inconsistency: claims 29 in one place, actual `skills/` directory has 34 SKILL.md files
- ASCII diagrams in mermaid blocks — rendering context confusion
- Missing: how `/dev` routing logic actually works; what criteria determine which path is taken
- Missing: hooks in `claude/hooks/` directory are listed in a table but not integrated into the workflow narrative
- Unclear: discovery bootstrap — when is `discovery_source` auto-loaded vs. manually handled

**`docs/overnight.md`** — EXCELLENT (Medium priority)
- Module table lists 15 modules but `claude/overnight/` has 17 .py files; `integration_recovery.py` and possibly `conflict.py` are missing
- Recovery section doesn't explain when/how a `running` status can occur in state (only mentions crash)
- "3–5 features per session" best practice has no rationale — why not 2 or 6?
- Missing: how concurrency interacts with git conflict detection

**`docs/interactive-phases.md`** — VERY GOOD (Medium priority)
- References `skills/refine/references/` and `skills/interview/references/` which do not exist — forward references to unimplemented content
- Complexity/criticality section doesn't explain what happens when a user manually escalates tier mid-lifecycle — is it persisted to backlog YAML?
- Missing: behavior when research/spec artifacts are stale (file existence check passes, but content may be months old)

**`docs/backlog.md`** — EXCELLENT (Low priority)
- `schema_version: "1"` with no versioning strategy explanation
- `TERMINAL_STATUSES` constants referenced but not enumerated in the doc
- Readiness gate callout ("file existence, not quality") is buried in Best Practices — should be prominent in the Gate section
- Missing: example of a "thin spec" and why it causes blocking deferrals

**`docs/setup.md`** — VERY GOOD (Medium priority)
- Windows Terminal section appears under the "Ghostty Terminal (macOS)" heading — structure/nesting confusion
- "Customize for Your Machine" table references `claude/settings.json` without explaining what MCP plugin patterns look like
- Unclear: `caffeinate-monitor.sh` as both a symlinked binary and potential launchd service — dual role not explained
- Missing: how to handle multiple machines sharing the same home directory symlinks

**`docs/pipeline.md`** — MODERATE (High priority)
- Module table lists 8 files; actual `claude/pipeline/` has 11 .py files
- Missing from table: `conflict.py`, `merge_recovery.py`, `parser.py`
- `parser.py` is used to parse `master-plan.md` and `plan.md` but entirely undocumented
- Recovery section mentions `revert_merge()` from `merge.py` without explaining pre-conditions
- No explanation of what `master-plan.md` vs. per-feature `plan.md` contains

**`docs/dashboard.md`** — GOOD (Low priority)
- "No authentication layer" limitation doesn't explain deployment scenarios (localhost only? proxied?)
- Data sources listed without schemas — what does `overnight-state.json` look like vs. `overnight-events.log`?
- Missing: HTMX polling interval and latency expectations

### Existing patterns to follow

1. **Back/forward link structure** — consistent use of `[← Back to X]` and cross-doc navigation links
2. **Module/file tables** with Role column (drifts when files are added; needs maintenance notes)
3. **State file documentation** — full JSON/YAML schema examples with field descriptions (gold standard in overnight.md and backlog.md)
4. **Recovery procedures** — dedicated section per failure mode with symptoms + diagnosis + options
5. **"For:" / "Assumes:" audience markers** at doc header — good pattern in use

### Integration points

- Skills reference `skills/*/SKILL.md` as authoritative — docs must stay in sync with actual skill counts and triggers
- Backlog gate logic is authoritative in `claude/overnight/backlog.py` — docs reference this file
- Session hooks (`hooks/scan-lifecycle.sh`) drive lifecycle phase detection across sessions — not explained in docs
- `requirements/` files are read by discovery and lifecycle research phases — docs don't explain their schema or who maintains them

---

## Web Research

### Documentation quality framework: Diátaxis

The most important structural finding is the **Diátaxis framework**, which identifies four documentation types that must be kept separate:

| Type | User Need | Wrong if... |
|------|-----------|-------------|
| Tutorial | Learning through doing | Contains reference tables or "why" explanations |
| How-To Guide | Accomplish a specific task | Teaches concepts instead of completing a task |
| Reference | Look up technical facts | Editorializes or explains "why" |
| **Explanation** | **Understand the system** | Contains step-by-step instructions |

The most commonly missing type in developer workflow tools is **Explanation** — deep "how it works" docs that explain the mental model, why the design was chosen, and how components interact. This is distinct from how-to guides.

### What makes "how it works" explanations effective

1. **Separate mechanism from procedure** — explanation docs describe what happens and why, never what to do
2. **State diagrams for state machine systems** — LangGraph sets the standard here; developers can't reason about lifecycle phases without seeing the valid states and transitions
3. **Explain design decisions explicitly** — "why does the overnight runner use worktrees?" is a legitimate explanation question; if unanswered, behavior gets cargo-culted or broken
4. **Central vocabulary definition** — define each term once ("lifecycle phase," "hook event," "skill frontmatter") and reference that definition throughout
5. **Runtime data-flow diagrams** — how a user command flows through skills → hooks → execution is more valuable than per-component descriptions

### Hook system documentation standards (CLIG.dev)

- Document every exit code with non-default semantics (exit 0 = pass, exit 1 = generic fail, exit 2 = block — must be explicit)
- Document stdin/stdout contracts for each hook event type
- Show a minimal working hook example before anything else
- Explain ordering guarantees (which hooks run first, sequential vs. parallel)
- Cover failure modes: what happens when a hook times out, crashes, or produces malformed output?

### Most common CLI workflow tool documentation gaps

1. No "architecture overview" page — users can read 10 how-to guides with no coherent mental model
2. Missing failure mode documentation — what state is preserved on crash? How do you resume?
3. Conflation of deterministic vs. LLM-driven behavior
4. No troubleshooting index — errors only documented where they occur
5. Outdated examples — code samples drift from actual interface
6. Under-documented environment variables — mentioned in passing, never collected in reference

---

## Requirements & Constraints

**Source: `requirements/project.md`**

- **Maintainability through simplicity** (explicit quality attribute): "The system should remain navigable by Claude even as it grows." Documentation quality directly serves this goal.
- **Observability** is an in-scope core feature — docs must clearly cover statusline dashboard, notifications, and metrics interpretation
- **Daytime quality principle**: "Claude should not fill unknowns with assumptions." Documentation gaps force assumption-filling. Clear, complete docs prevent this.
- **Global agent configuration** (in-scope): settings, hooks, and reference docs are explicitly owned by this project

**Source: `CLAUDE.md`**

- **Symlink architecture** is a frequent source of confusion — docs must clearly state which files are symlinked and that the repo copy is the canonical version
- **File-based state** is a core architectural constraint — docs must explain how to navigate plain-text state files
- **deploy-bin pattern** and `jcc` wrapper have specific usage patterns that must be clearly documented

**Scope boundary**: `docs/` should NOT cover external tool setup (Tailscale, mosh, Cloudflare Tunnel details), shell configuration, or git workflows beyond what cortex-command specifically requires. Those belong in machine-config.

---

## Tradeoffs & Alternatives

**Approach A — Sequential deep-dive**: Pros: immediate visible progress, each doc gets full attention. Cons: no global view of gaps early; risk of rewriting a doc and later discovering it needs revision after reading adjacent docs.

**Approach B — Audit-first, then rewrite**: Pros: global view of gaps and redundancies before touching rewrites; smart prioritization by severity; produces a visible gap report artifact. Cons: two-phase process; audit overhead may not be justified if rewrites are small.

**Approach C — Template-driven rewrite**: Pros: consistent style; clear definition of done. Cons: template design upfront cost; risks over-standardizing docs that don't need all template elements; may miss doc-specific gaps.

**Approach D — Parallel agent dispatch per doc**: Pros: fastest wall-clock time. Cons: high risk of inconsistent style; cross-doc coordination headaches; coordination overhead exceeds time savings for only 8 docs.

**Recommended: Approach B** — 8 docs at mixed quality with known cross-doc dependencies. Audit first to identify the 3–4 highest-priority docs, then rewrite those with full context. Leave high-quality docs (overnight.md, backlog.md) with targeted fixes only. Produces a clear audit artifact before implementation begins.

---

## Open Questions

- Should the docs include a **hooks architecture explanation** covering exit codes, stdin/stdout contracts, and event types? This is currently missing but would be the most impactful addition based on web research. Deferred: ask in Spec.
- The `serena-memory` broken reference in `skills-reference.md` — **Resolved**: skill does not exist in `skills/`; remove the reference.
- Do the ASCII diagrams in `agentic-layer.md` need to be replaced or can they be cleaned up in place? Deferred: implementation-level decision; will be determined per-doc during rewrite.
