---
schema_version: "1"
uuid: 57cc39ed-be4a-4338-b988-a4ae2052de20
title: "Investigate and standardize path resolution for plugin-distributed skills (CLAUDE_SKILL_DIR not substituted in reference files, scripts, or subagent prompts)"
status: backlog
priority: medium
type: spike
created: 2026-06-03
updated: 2026-06-03
---
## Problem

`${CLAUDE_SKILL_DIR}` is a Claude Code load-time string substitution that resolves **only in a SKILL.md body**. It does NOT resolve in reference files (`references/*.md`), YAML frontmatter, the Bash shell, or in any subagent prompt the main agent composes. Several skills reference their own bundled files (`scripts/*.sh`, `references/*.md`) from those non-substituting contexts, or via bare relative paths that resolve against the working directory rather than the skill dir. Because skills are plugin-distributed under a version-hashed cache path (`~/.claude/plugins/cache/.../<git-sha12>/skills/<skill>/`), hardcoded and `~/.claude/skills/...` paths are also unavailable.

### Concrete harm (verified)
- **pr-review (worst, silent):** `references/protocol.md` Stage 3.5 runs `bash "${CLAUDE_SKILL_DIR:-$TMPDIR}/scripts/evidence-ground.sh" 2>/dev/null`. In a real shell the var is unset → `$TMPDIR/scripts/evidence-ground.sh` (nonexistent) → error swallowed → empty stdout → protocol's own rule routes to the synthesis-failure fallback. Evidence-grounding is **silently skipped on every faithful run**; it only appears to work when the running agent improvises the path.
- **critical-review / diagnose:** `${CLAUDE_SKILL_DIR}/references/...` embedded in a reference file (including the Opus synthesizer's prompt template). The literal token reaches the (sub)agent unresolved. Observed live: a `/cortex-core:critical-review` run required hand-substituting the absolute path to `a-to-b-downgrade-rubric.md`.

### Affected skills (9 skills / 11 files, verified)
- **Class 1 — `${CLAUDE_SKILL_DIR}` in a reference file:** pr-review (`protocol.md`), critical-review (`references/synthesizer-prompt.md`), diagnose (`references/phase-1-investigation.md`).
- **Class 2 — bare `../`/`../../` cross-skill refs (resolve against CWD):** research (`SKILL.md`), refine (`SKILL.md:70`; lines 168/177 use the correct `${CLAUDE_SKILL_DIR}/../` form), discovery (`references/clarify.md`, `references/research.md`), lifecycle (`references/clarify.md`).
- **Class 3 — repo-relative `.sh | bash` + bare `](references/)` hrefs:** lifecycle (`references/implement.md`), android-dev-extras r8-analyzer + android-cli (`SKILL.md`).
- **Canonical-source note:** the cortex-core six live in top-level `skills/` (mirrored into `plugins/cortex-core/` — fix in `skills/`, the mirror regenerates). pr-review + android-dev-extras are hand-maintained in `plugins/`. cortex-ui-extras and cortex-dev-extras verified clean (their `${CLAUDE_SKILL_DIR}` usages are all SKILL.md-body, which works).
- **Prior work:** this is the unfinished plugin-tier follow-on to the COMPLETE #010 / #085, which were plugin-aware and deliberately scoped `plugins/` out (their tilde-path remedy is not plugin-safe).

## Goal

Investigate and decide the best path-resolution mechanism for plugin-distributed skills, then apply it. The decision is genuinely open. Candidate directions to evaluate critically (do not assume the prior bake-off's conclusion):

- **Lean on the cortex CLI more.** critical-review already invokes `cortex-*` console scripts. One direction is to turn path-dependent steps (e.g. evidence-grounding, serving rubric/output-format content) into `cortex` subcommands so no skill-relative path resolution is needed. Consideration a prior bake-off raised: pr-review is currently standalone ("no extra prerequisites") and is designed to run in arbitrary repos where the cortex CLI may not be on PATH (the cortex PATH bootstrap hook is gated on `cortex/lifecycle/` in CWD, and macOS Dock-launched sessions get a minimal PATH). So this is partly a **contract** decision: is pr-review allowed to depend on the cortex toolchain?
- **Explicit path propagation from the SKILL.md body.** Resolve `${CLAUDE_SKILL_DIR}` in the body (where it works), then have the main agent use/propagate that absolute path into Bash invocations and into composed subagent prompts (reading reference files and inlining their content). This is what critical-review already does for its Opus dispatch. A prior bake-off scored this highest (no sandbox/PATH/injection dependency; the critical script step fails loud, not silent), with residual risk being model-behavior/compaction.
- **Hybrid / other.** e.g. load-time `` !`...` `` injection (currently unverified on this codebase — zero deployed uses; sandbox execution and `$TMPDIR`-parity unknown), or a mix (CLI for executable steps, body-propagation for reference content), or folding small reference files into the SKILL.md body.

A prior local investigation + 4-approach bake-off is summarized in `cortex/research/claude-skill-dir-fix/investigation.md`. It currently leans toward path-propagation and is skeptical of the CLI route (portability) and injection (unverified mechanism) — but those conclusions should be re-tested rather than inherited, since the operator explicitly wants the CLI option re-weighed.

## Open questions to resolve

1. Should the cortex suite **standardize one** resolution mechanism across all skills, or allow per-skill choices (CLI-dependent for cortex-internal skills like critical-review; standalone for pr-review)?
2. Is pr-review allowed to depend on the cortex CLI (changing its "no extra prerequisites" contract), or must it stay standalone and portable to any repo?
3. **§17741 empirical question (gates Class 2/3):** on the current Claude Code version, do bare relative paths in a SKILL.md / reference file resolve against the skill dir or the working directory? The repo's own archived research cites issue #17741 (closed "not planned") saying CWD; the docs imply skill-dir. Confirm empirically — it determines whether the Class-2/3 entries are actually broken off-repo.
4. Does load-time `` !`...` `` injection run for plugin skills under the sandbox, and does its `$TMPDIR` match the Bash-tool `$TMPDIR`? This gates the injection-based variants and is currently unverified — a short live test (author a throwaway skill with `` !`echo ...` `` that writes to `$TMPDIR`, invoke it, read it back from a Bash stage) would settle it.

## Acceptance criteria

- A decision on the resolution mechanism(s) with rationale, recorded (research doc, and an ADR if it standardizes a cross-skill convention).
- Open questions 3 and 4 answered **empirically**, not assumed.
- pr-review's evidence-grounding verified to actually run (the silent-skip closed), fix landed in canonical sources (pr-review + android-dev-extras in `plugins/`; the cortex-core six in `skills/` so the mirror regenerates).
- A documented authoring convention so new skills don't reintroduce the bug — extend `claude/reference/claude-skills.md` (per #010's precedent) to explicitly cover the plugin-distributed case and the reference-file / subagent-prompt / shell contexts.