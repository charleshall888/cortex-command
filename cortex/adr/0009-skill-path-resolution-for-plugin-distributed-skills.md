---
status: accepted
---

# Skill path-resolution for plugin-distributed skills: body-propagation

## Context

`${CLAUDE_SKILL_DIR}` is a Claude Code load-time substitution that resolves **only in a SKILL.md body** — not in reference files, the shell, YAML frontmatter, or composed subagent prompts. Bare relative paths resolve against **CWD, not the skill dir** (verified live on Claude Code 2.1.168; re-verified unchanged on 2.1.191, 2026-06-25 — still body-only, no new first-class mechanism for reference files / shell / subagent prompts in the changelog through 2.1.178; the docs do now sanction `${CLAUDE_SKILL_DIR}` inside body-level `!`-bash-injection, the path this ADR rejected as unverified). Plugin-distributed skills ship under a version-hashed cache path, so hardcoded and `~/.claude/skills/...` paths are also unavailable off-repo.

The result was a class of latent off-repo defects: raw `${CLAUDE_SKILL_DIR}` tokens and bare consult-references embedded *inside* composed subagent prompts (a fresh subagent cannot resolve them), and bare-relative skill-load paths that break when CWD is not the repo root. The worst case was pr-review's Stage 3.5 evidence-grounding, where `${CLAUDE_SKILL_DIR:-$TMPDIR}/scripts/evidence-ground.sh` resolved to a nonexistent `$TMPDIR` path in the shell, silently skipping evidence-grounding on every faithful run. The recurrence root cause: the authoring convention that prevented this was deleted with no lint enforcing it.

## Decision

Standardize the **invariant**: no reference-file region that reaches a fresh subagent (a composed prompt) may carry a raw `${CLAUDE_SKILL_DIR}` token or a bare consult-reference, and no bare-relative path may appear in a Read/execute context. Every such consumer receives the resolved value explicitly via **body-propagation**: only the owning SKILL.md body resolves `${CLAUDE_SKILL_DIR}` (its own dir directly, or a sibling via `${CLAUDE_SKILL_DIR}/../<sibling>`), then propagates the absolute path — or inlines the reference content — to every reference file, shell line, and composed subagent prompt that needs it.

The CLI mechanism is **reserved for executable/state steps in skills already coupled to the cortex toolchain**; it is **not** adopted for pr-review. For pr-review, CLI would add an unprotected plugin↔wheel version-skew surface for zero gain and would not by itself fix the actual path bug.

The invariant is enforced **structurally** by a context-scoped lint (`cortex-check-skill-path`), not by prose alone. The CLAUDE.md authoring principle back-points to this ADR rather than restating its rationale.

## Three-criteria gate clearance

- **Hard to reverse**: the decision is a cross-skill convention plus a lint that enforces it; reversing it would require coordinated changes across every skill that propagates the resolved path or inlines content, plus the lint module and its fixtures — not a one-file edit.
- **Surprising without context**: a contributor reading a SKILL.md body that resolves `${CLAUDE_SKILL_DIR}` and threads the absolute path into a subagent prompt would reasonably propose simplifying it back to a raw token or a bare relative path — unaware that the body-only substitution boundary and the CWD resolution of bare paths make those forms break off-repo. This ADR records why the propagation is load-bearing.
- **Real trade-off**: the CLI mechanism and load-time `!`-injection were both credible alternatives, considered and rejected for stated reasons (below).

## Rejected alternatives

- **Pure-CLI for pr-review (rejected)**: route pr-review's script/reference loads through a `cortex-*` console script instead of body-propagation. Rejected because it adds a net-new `cortex_command/pr_review/` wheel package, an **unprotected** plugin↔wheel version-skew surface (pr-review has no MCP server / no CLI_PIN to gate skew), and a new dual-source drift surface — for zero token saving and no reliability gain. The bug is the path, not a missing CLI; CLI does not by itself fix it.
- **Load-time `!`-injection (rejected)**: inject the resolved path at load time via a `!`-prefixed command form. Rejected as unverified — its sandbox-write and `$TMPDIR`-parity behavior was never established — and silent-failure-prone.
- **Recreating a standalone `claude/reference/` doc (rejected)**: relocate the lost authoring convention into a fresh standalone reference doc. Rejected because a standalone doc carries the same orphaning risk that lost the prior convention (it was deleted with no enforcement and never relocated). The invariant lives in a lint plus a CLAUDE.md back-pointer to this ADR instead.
