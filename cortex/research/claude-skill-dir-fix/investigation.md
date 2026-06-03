# Investigation Conclusion + Proposed Fix Direction: `${CLAUDE_SKILL_DIR}` misuse in cortex-command skills

Status: post-bake-off (v3). Subject repo: `cortex-command` (the agentic harness / Claude Code plugin suite). Trigger: while running the plugin-distributed `cortex-pr-review:pr-review` skill, `${CLAUDE_SKILL_DIR}`-based paths failed to resolve. v2 incorporated a 4-angle adversarial review that invalidated v1's §3 mechanism; v3 incorporates a 4-approach implementation bake-off that selected Approach B and rejected v2's file-handoff (§3).

## 1. Diagnosis (claimed facts)

1. **Headline correctness bug (severity corrected from v1):** In `plugins/cortex-pr-review/skills/pr-review/references/protocol.md`, Stage 3.5 invokes the evidence-grounding script as:
   `... | bash "${CLAUDE_SKILL_DIR:-$TMPDIR}/scripts/evidence-ground.sh" 2>/dev/null`
   In a real shell `$CLAUDE_SKILL_DIR` is unset, so this resolves to `$TMPDIR/scripts/evidence-ground.sh`, which does not exist. `2>/dev/null` swallows the error → empty stdout → protocol.md's own Stage 3.5 rule routes empty stdout to the synthesis-failure fallback. That fallback is ANNOUNCED to the user (Stage 5 emits "Opus synthesis was unavailable due to an error... No cross-validation has been performed"), so the degradation is visible, not silent. The substantive defect: **evidence-grounding is skipped on every faithful literal execution**, masked only when the running agent improvises the correct path. (v1 overstated this as a "silent" failure that "drops to raw-Sonnet on every run"; corrected here.)

2. **Mechanism ground truth (docs-confirmed):** `${CLAUDE_SKILL_DIR}` is a Claude Code load-time STRING SUBSTITUTION applied to SKILL.md *bodies only* (expands to the skill's own subdirectory; for plugins the version-hashed cache path). It is NOT substituted in reference files, YAML frontmatter, the Bash shell, or in any subagent prompt the main agent dispatches. `!`cat ${CLAUDE_SKILL_DIR}/...`` (and `!`echo``/`!`printf``) injection DOES work in plugin SKILL.md bodies: substitution runs first, then the command executes at load time, output inlined. `CLAUDE_PLUGIN_ROOT` is hook-only, unavailable to Bash at skill runtime. The install `<hash>` is the first 12 chars of the release git commit SHA, so it changes every release.

3. **CRITICAL boundary (the load-bearing fact):** the SKILL.md body is the ONLY context where `${CLAUDE_SKILL_DIR}` resolves. Subagents (the four Stage 3 critics, the Stage 4 Opus synthesizer) are FRESH and receive only the prompt the main agent composes from protocol.md's fixed template; they do NOT inherit the main agent's context. Therefore any runtime consumer of the skill dir — a Bash invocation OR a file reference embedded in a dispatched subagent prompt — must receive the resolved value EXPLICITLY; it cannot rely on `${CLAUDE_SKILL_DIR}` and cannot rely on inlining into the main-agent body.

4. **Three misuse sites in protocol.md (a reference file):**
   - cache/diff paths `${CLAUDE_SKILL_DIR:-$TMPDIR}/.cache/...`: work BY ACCIDENT via the shell `:-$TMPDIR` fallback.
   - `${CLAUDE_SKILL_DIR}/references/rubric.md` and `output-format.md`, including inside the Stage 4 Opus *subagent* prompt template (which has no `{rubric}`/`{output_format}` placeholder): literal `${CLAUDE_SKILL_DIR}` text reaches the subagent, which cannot resolve it.
   - `bash "${CLAUDE_SKILL_DIR:-$TMPDIR}/scripts/evidence-ground.sh"`: the every-run skip above.

## 2. Scope (verified): ~11 distinct canonical files, three mechanism-classes

Counts exclude the `cortex-core`/`cortex-overnight` plugin trees, which are BUILD_OUTPUT mirrors regenerated from top-level `skills/` via `just build-plugin` (per `justfile:560-561`); fixing the canonical `skills/` source regenerates them, so they are not separate fixes. v1's "~18" double-counted the mirror and counted working SKILL.md-body usages as broken.

- **Class 1 — `${CLAUDE_SKILL_DIR}` in a reference file (broken by mechanism): 3 files.** `plugins/cortex-pr-review/skills/pr-review/references/protocol.md`, `skills/critical-review/references/synthesizer-prompt.md:30`, `skills/diagnose/references/phase-1-investigation.md:49`. (The latter two are the canonical sources for the cortex-core mirror.)
- **Class 2 — bare cross-skill relative load refs (resolve against CWD, fail off-repo): 5 files.** `skills/research/SKILL.md`, `skills/refine/SKILL.md:70` (bare `../lifecycle/...` missing the `${CLAUDE_SKILL_DIR}/` prefix), `skills/discovery/references/clarify.md`, `skills/discovery/references/research.md`, `skills/lifecycle/references/clarify.md`.
- **Class 3 — repo-relative `.sh` piped to bash + bare hrefs: 3 files.** `skills/lifecycle/references/implement.md:75,111` (`cat skills/lifecycle/references/_interactive_overnight_check.sh | bash`, breaks off-repo); `plugins/android-dev-extras/skills/r8-analyzer/SKILL.md` and `.../android-cli/SKILL.md` (bare `](references/...)` hrefs).

Audited and NOT broken: 10 SKILL.md-body `${CLAUDE_SKILL_DIR}` usages (substitution works there), including `cortex-ui-extras/skills/ui-brief/SKILL.md` (clean). Note `${CLAUDE_SKILL_DIR}/../sibling-skill/references/...` in a SKILL.md *body* (e.g. `refine/SKILL.md:168,177`) WORKS — substitution applies in the body and sibling skills are co-located in both the personal (`~/.claude/skills/`) and plugin (`<plugin>/skills/`) layouts; only the un-prefixed `../lifecycle/` at line 70 is broken.

**Prior-art relationship:** this is unfinished plugin-tier coverage of the COMPLETE lifecycles #010 (fix-skill-sub-file-path-bug) and #085, which were plugin-AWARE — their spec explicitly says "Do not use this pattern for plugin skills" and codified a SKILL.md-vs-reference-file rule — and deliberately scoped `plugins/` out, not plugin-blind. No OPEN backlog/research/ADR tracks the plugin-tier follow-on.

## 3. Proposed fix direction (v3 — selected via a 4-approach bake-off)

A parallel bake-off scored four candidates adversarially. Result: **Approach B wins (confidence 4/5); A, C, D all scored 2/5 / AVOID.** v2's load-time-injection file-handoff (Approach A) is REJECTED — its write-under-sandbox and `$TMPDIR`-parity assumptions are unverified and its failure mode is SILENT (it can silently reproduce the original bug).

Governing principle (from §1.3): every runtime consumer of the skill dir must receive the resolved value EXPLICITLY, via the one mechanism the entire skill suite already depends on — `${CLAUDE_SKILL_DIR}` substituting in the SKILL.md body so the main agent holds the real absolute path, then the main agent using/propagating it. No `!`-injection, no `$TMPDIR` handoff, no CLI/PATH dependency.

For pr-review's SKILL.md + protocol.md:
- **Establish the skill dir as a named constant in the SKILL.md body.** The body states: "Your skill directory is `${CLAUDE_SKILL_DIR}` (an absolute path). Wherever protocol.md references the skill's scripts or reference files, use this absolute path." Substitution resolves it at load time; the agent holds it for the run.
- **evidence-ground.sh → invoke by the known absolute path.** protocol.md drops the literal `${CLAUDE_SKILL_DIR}` and instructs `bash "<skill-dir>/scripts/evidence-ground.sh"` using the established path. Failure mode is LOUD: a wrong path exits non-zero and triggers the visible synthesis-failure fallback, not a silent skip. (Optional hardening: evidence-ground.sh is fully self-contained — reads stdin, uses `$TMPDIR`, no `$0`/`BASH_SOURCE`/sibling deps — so it can also be run path-free via `... | bash -s` after the agent Reads it. Not required.)
- **rubric.md / output-format.md → main-agent Reads and injects CONTENT into composed subagent prompts.** Add `{rubric}`/`{output_format}` placeholders to protocol.md's Stage 4 (and any Stage 3 critic) template, with an EXPLICIT IMPERATIVE step: "Read rubric.md and output-format.md now (at the established skill dir) and inline their content before composing the subagent prompt." Remove the dead `${CLAUDE_SKILL_DIR}/references/...` path references from the subagent templates. (This is exactly what the `critical-review` skill already does for its own Opus synthesizer dispatch — established precedent, not invention. The rubric's operative content is also already inlined in the Stage 4 template, giving a soft-degrade backstop.)
- **Cache/diff paths → plain `$TMPDIR/.cache/...`.** Drop the misleading `${CLAUDE_SKILL_DIR:-}` prefix; the skill dir is read-only under sandbox and cache must be writable.

Approach B's only residual risk is model-behavior/compaction (the agent must use the stated constant across stages). Mitigations: the whole suite already relies on this and works; the critical script step fails loud; SKILL.md is re-readable and the harness-injected "Base directory for this skill" line is early context; rubric content is pre-inlined as backstop. The one mandatory drafting detail: use explicit imperative Read instructions, not passive placeholders.

Rejected by the bake-off: **(A) load-time-injection file-handoff** — unverified `!`-injection WRITE + `$TMPDIR`-parity; SILENT failure. **(C) cortex CLI subcommand** — portability FAILS in non-cortex / Dock-launched repos (the cortex PATH bootstrap is gated on `cortex/lifecycle/` in CWD), violates pr-review's "no extra prerequisites" contract, heavy wheel coupling; SILENT failure. **(D) full load-time inlining** — same unverified `!`-injection binary gate with catastrophic SILENT failure, plus ~16.8k tokens of unconditional context bloat per invocation. **(f) `CLAUDE_PLUGIN_ROOT`** — runtime-unavailable (hook-only).

Fix loci: pr-review + android-dev-extras edited directly in `plugins/` (hand-maintained); Class-2 cortex-core-family bugs fixed in canonical top-level `skills/` and regenerated into the mirror.

## 4. Recommended execution

Drive the fix through `/cortex-core:lifecycle` (required by repo rules before editing `skills/` and `plugins/cortex-pr-review/`). Scope breadth (pr-review-only vs the full ~11-file class) is an open decision for the operator.

## 5. Known unresolved conflict

The Claude Code docs say bare relative markdown links in a SKILL.md resolve against the skill dir and are fetched on demand; cortex-command's own archived research cites GitHub issue #17741 (closed "not planned") saying they resolve against CWD and fail. This conflict directly governs the Class-2 files (bare `../lifecycle/` and `references/` paths), so it must be re-confirmed empirically on the current Claude Code version before fixing those — the v2 fix direction otherwise uses only `${CLAUDE_SKILL_DIR}`-anchored or explicitly-propagated forms, which are not in dispute.
