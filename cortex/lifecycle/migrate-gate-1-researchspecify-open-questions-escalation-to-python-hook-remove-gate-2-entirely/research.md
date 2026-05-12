# Research: Migrate both complexity-escalation gates to deterministic Python hook (`cortex-complexity-escalator`)

## Scope Revision Addendum (2026-05-11)

**Current scope (Option B, post-adversarial review):** migrate BOTH gates to a uniform Python hook (`bin/cortex-complexity-escalator`). Gate 1 (Research → Specify, ≥2 `## Open Questions` bullets) AND Gate 2 (Specify → Plan, ≥3 `## Open Decisions` bullets) both invoke the same hook with a `--gate` parameter. **No deletions**; both gates' behavior is preserved by the new mechanism. The new `gate` provenance field on `complexity_override` events is emitted by both gates, immediately closing the FM-1 attribution gap.

**Previous scope (rejected):** "migrate Gate 1; remove Gate 2 entirely." Rejected because: (1) the "0 fires" empirical premise is unverifiable from the events.log corpus (FM-1); (2) the active-corpus low Gate-2-eligibility could be evidence the gate works as a forcing function, not that it's unused (FM-2 selection-effect); (3) the asymmetric scope inverted the audit's explicit "keep both gates, migrate both" resolution (A-1). Reverting to symmetric scope restores audit alignment without betting on the unverifiable premise.

**What carries over from the existing research below**: codebase analysis (hook location, payload shapes, schema source-of-truth correction, integration points, plugin-mirror enforcement); web research (Anthropic skills-vs-hooks framework, Claude Code hook taxonomy, FileChanged bugs); requirements & constraints (workflow trimming, SKILL.md cap, sandbox registration, audit Tier 3 framing); adversarial findings on bullet-counting (FM-3), trigger mechanisms (FM-4, FM-5, FM-6), idempotency (FM-7), sandbox (SEC-1), path traversal (SEC-2), and schema-shape diversity (A-3, A-4).

**What changes under Option B**:

- **Trigger mechanism**: Approach B (explicit invocation from SKILL.md) is unchanged; the hook is invoked at TWO transitions (research→specify and specify→plan) instead of one. Both invocations use the same script with different `--gate` arguments.
- **Hook surface**: one binary, one CLI shim line, one test file. The `--gate` parameter selects which file to read and which threshold to apply.
- **Algorithm**: two algorithm variants, one per gate. Both share idempotency, path-traversal hardening, read-after-write verification, and event-emission infrastructure.
- **#180 D4 consequence**: NO LONGER unblocked by this ticket. Gate 2 remains a Gate consumer of the Open Decisions section; D4's BLOCKED status in the audit's decomposition is preserved. This is the audit's intended state.
- **Workflow Trimming policy alignment**: the policy's "removed wholesale" framing no longer applies (no removals). Alignment shifts to the audit's Tier 3 hook-migration direction only.

### Gate 2 parallel analysis: `## Open Decisions` counting

**Section semantic** (per `skills/lifecycle/references/specify.md:91–97, 139–141`): an Open Decisions bullet is *"only when implementation-level context is required and unavailable at spec time — include a one-sentence reason why."* Each bullet inherently has a deferral rationale by template design. **Unlike Research's Open Questions, there is no resolved/deferred/bare-unannotated trichotomy** — items are inherently deferred-with-reason. The counting algorithm is therefore simpler: count bullets directly under the `## Open Decisions` heading.

**Current Gate 2 site (`skills/lifecycle/SKILL.md:270–274`)**:
> Otherwise, scan `lifecycle/{feature}/spec.md` for a `## Open Decisions` section. Count the number of bullet items (`-` or `*` lines) directly under that heading. If the section is absent or the count is fewer than 3, skip the check.

**Edge cases for the algorithm spec**:
- Template-placeholder bullet (`- [Only when implementation-level context is required...]`) — should not count as a real decision. The algorithm should either (a) ignore bullets matching the placeholder regex, or (b) be tolerant of 1 placeholder bullet at threshold ≥3.
- Sub-bullets (nested under a parent decision) — count parent only, consistent with Gate 1 (Refine-aligned).
- Fenced code blocks containing `-` lines — excluded.
- Blockquoted bullets — excluded.
- Empty section (`## Open Decisions` followed by blank lines or another heading) — count 0, skip.

**Threshold rationale (≥3, unchanged from current prose)**: per the audit's Hold-1 inspection, this threshold was set to align with the post-spec-write complexity signal. Spec phase will commit to keeping this threshold or revising it; current research provides no evidence for either direction.

### Recommended approach (revised under Option B)

**Approach B (explicit invocation) + symmetric both-gates migration + single `bin/cortex-complexity-escalator` binary with `--gate` parameter + additive `gate` provenance field on `complexity_override` events + Refine-aligned bullet-counting for Open Questions + template-placeholder-aware bullet-counting for Open Decisions.**

**Open Questions list under Option B** (revised):
- **Gate 2 removal premise** — RESOLVED by Option B. No removal; both gates preserved. Gate provenance data unlocks future evidence-driven decisions.
- **Bullet-counting algorithm for Open Questions** — Refine-aligned bare-unannotated semantic (count only bullets that are not prefixed with "Resolved:"/"Deferred:" markers or matching Refine's deferred-rationale shape per `skills/refine/SKILL.md:149`). Pytest fixtures required.
- **Bullet-counting algorithm for Open Decisions** — count bullets under heading; ignore template-placeholder regex; count parent bullets only (no sub-bullets); exclude fenced code blocks and blockquotes. Pytest fixtures required.
- **Trigger mechanism** — Approach B for both gates. Honest framing: compression with algorithmic side-pin, not determinism migration. ACCEPT.
- **Idempotency monotonicity** — monotonic-upward, documented explicitly. Hook recognizes all three existing payload shapes when guarding.
- **Write-success verification** — read-after-write check before announcing. ACCEPT.
- **Path-traversal hardening** — feature-slug regex `^[a-zA-Z0-9._-]+$` + realpath containment under `lifecycle/`. ACCEPT.
- **#180 D4 consequence** — RESOLVED by Option B: D4 stays BLOCKED per the audit's intended state. No action in this ticket.
- **Schema source-of-truth correction** — references update from `cortex_command/overnight/events.py` to `cortex_command/pipeline/state.py:288`. ACCEPT.
- **Three event-payload shapes** — tolerate all three (consistent with `read_tier`'s permissive reading); document the tolerance in the hook's guard logic.
- **Rollback story** — preserved for future-self: the `gate` provenance field this ticket adds enables evidence-driven future decisions about either gate's retention. No rollback story needed for this ticket since no removals.

---

# Original Research (pre-revision, retained for traceability)

## Research scope (pre-revision)

The sections below were authored when the scope was "migrate Gate 1; remove Gate 2 entirely." Most findings carry over under Option B (the symmetric scope); the Gate 2 analysis sections (notably FM-1, FM-2 under Adversarial Review) are what triggered the scope revision. Read this lower section as historical analysis; the Scope Revision Addendum above is authoritative.

# Original Title: Migrate Gate 1 (research→specify Open-Questions escalation) to Python hook; remove Gate 2 entirely

## Codebase Analysis

### Files that will be created or modified

**Created (canonical sources):**
- `bin/cortex-complexity-escalator` — Python script (no `.py` suffix; cortex `bin/cortex-*` convention). Reads `lifecycle/{feature}/events.log` to detect active tier; reads `lifecycle/{feature}/research.md`, counts `## Open Questions` bullets, escalates by appending `complexity_override` event with `gate: "research_open_questions"` when threshold ≥2 and tier is not already `complex`.
- `tests/test_complexity_escalator.py` — pytest module modeled on `tests/test_common_utils.py` (which already exercises `complexity_override` event handling at lines 51, 76–89).

**Modified (canonical sources):**
- `skills/lifecycle/SKILL.md`:
  - Step 3 §5 (lines 259–268): Gate 1 protocol prose collapses to a one-line pointer to the hook. Today's prose, including the inline JSON example at line 265 and the cross-reference to Step 6 at line 268, currently spans 10 lines.
  - Step 3 §6 (lines 270–274): Gate 2 — delete entirely.
  - Line 268 cross-reference ("The same effect applies to Step 6 (Gate 2)…") — strip the Gate-2 phrase.
  - Line 81 ("Detect complexity tier") — remains unchanged; reads `complexity_override` events from any source.
  - Verification target: `wc -l` ≤ ~310 lines (down from 374). Well under the 500-line cap.

- `skills/refine/SKILL.md` — line 161 (§3b tier detection) already names `complexity_override` events as authoritative. No edit needed; the hook just replaces the source of those events.

**Modified (auto-generated mirror):**
- `plugins/cortex-core/skills/lifecycle/SKILL.md` — auto-regenerated by `just build-plugin` (pre-commit hook).
- `plugins/cortex-core/bin/cortex-complexity-escalator` — auto-mirrored by `justfile:521` rsync.

**Schema source-of-truth correction (load-bearing):**
The ticket and audit both name `cortex_command/overnight/events.py` as the `complexity_override` schema location. **This is incorrect.** That file's `EVENT_TYPES` validator (lines 32–148) does NOT include `complexity_override` — it governs `lifecycle/sessions/{session_id}/overnight-events-*.log`, a different file. The canonical per-feature `events.log` writer is **`cortex_command/pipeline/state.py:288 log_event(log_path, event_dict)`** — auto-adds `ts`, plain atomic append, **no schema enforcement**. Adding a `gate` field is unconditionally backward-compatible because no validator exists at that layer.

### Relevant existing patterns

**Hook trigger mechanisms (three candidates):**

1. **PostToolUse with `Write|Edit` matcher** — strongest in-repo precedent. Three existing hooks use this pattern: `claude/hooks/cortex-skill-edit-advisor.sh:18` (Write|Edit + filename filter), `cortex-tool-failure-tracker.sh` (PostToolUse Bash matcher). Settings registration in `plugins/cortex-core/hooks/hooks.json:23`. **Over-fire problem**: PostToolUse fires on every Write/Edit; during /cortex-core:refine's iterative research.md authoring, multiple writes mean multiple fires. Requires idempotency guard. See FM-4 below.

2. **`FileChanged` hook event** — Web research identified this as officially documented since Claude Code 2.1.83. **Codebase has zero references** to `FileChanged` in any hooks.json, settings.json, or docs. Known bugs: GitHub #44925 (doesn't always detect Bash-tool mutations); GitHub #14281 (`additionalContext` multiple-injection). Adoption here would make cortex the first `FileChanged` consumer in its tree. See FM-5.

3. **Explicit invocation from a one-line SKILL.md protocol step** — the ticket's own Risks-section fallback. SKILL.md says `Run cortex-complexity-escalator <feature>` at the research→specify boundary; the Python script does the deterministic work. **Determinism caveat**: the Python evaluation is deterministic, but invocation depends on the model executing one SKILL.md line. See FM-6.

**Hook location convention:**

| Tier | Path | Examples | Plugin mirror |
|------|------|----------|---------------|
| Repo hooks | `hooks/cortex-*.sh` | cortex-validate-commit.sh, cortex-scan-lifecycle.sh | `plugins/cortex-{core,overnight}/hooks/` |
| Agent-config hooks | `claude/hooks/cortex-*.sh` | cortex-skill-edit-advisor.sh, cortex-permission-audit-log.sh, cortex-worktree-create.sh | `plugins/cortex-{core,overnight}/hooks/` |
| CLI utilities | `bin/cortex-*` (no extension) | cortex-update-item, cortex-resolve-backlog-item, cortex-load-parent-epic | `plugins/cortex-core/bin/` (`justfile:521`) |

**Recommendation: `bin/cortex-complexity-escalator`** — pattern alignment with existing `cortex-*` utilities; auto-mirrored without manifest edit; parity linter satisfied via SKILL.md pointer (`bin/cortex-check-parity` scans skills/**/*.md at line 76 for `bin/cortex-*` references and verifies presence).

If Approach C (PostToolUse) is chosen, a Bash shim at `claude/hooks/cortex-complexity-escalator.sh` is also needed plus hooks.json registration. The thin shim shells out to `bin/cortex-complexity-escalator` (same Python implementation; PostToolUse just adds harness-triggering).

**Real-world `complexity_override` payload shape** (sampled from `lifecycle/archive/*/events.log`):
```
{"ts": "2026-04-23T02:05:16Z", "event": "complexity_override", "feature": "<name>", "from": "simple", "to": "complex"}
```
Three payload variants exist in the corpus:
- Standard JSON: `{from, to}` shape (~16 of 18 historical events)
- YAML-style: `event: complexity_override` (no from/to) — 2 pre-schema-v2 entries
- Test fixture: `{"event": "complexity_override", "tier": "complex"}` (third shape in `tests/test_common_utils.py:51`)

Adding `gate: "research_open_questions"` is purely additive — `cortex_command/common.py:read_tier` (lines 320–354) reads `tier`/`to` only. SKILL.md line 81 "Detect complexity tier" reads `to` field only. No reader fails on unknown keys.

### Integration points and dependencies

- **Audit traceability**: `research/vertical-planning/audit.md:400` ("Hold 1") explicitly names the gate migration as Tier 3 hook migration in Stream H. `research/vertical-planning/decomposed.md:22` lists ticket 183 with this scope.
- **Sequencing**: tickets #174 (cross-skill collapse) and #177 (SKILL.md trim) must precede #183. Both are closed per recent commits (`a0e3a3e Close #177: APPROVED verdict`).
- **Downstream dependency**: ticket #180 D4 (Open Decisions optional) is unblocked by #183's Gate 2 removal.
- **Tier reader downstream**: `cortex_command/common.py:read_tier` and `skills/lifecycle/SKILL.md:81` are source-agnostic. Hook-emitted events work for downstream tier routing — no consumer-side edits needed.
- **Settings registration**: Approach B requires no settings change. Approach C requires entry in `plugins/cortex-core/hooks/hooks.json` (mirroring `cortex-validate-commit.sh`'s pattern) plus manifest entry in `justfile:500` HOOKS=().
- **MUST-escalation policy (OQ3)**: This migration removes prose MUST language by replacing it with deterministic Python. Soft positive-routing recommended in the SKILL.md replacement pointer ("The `cortex-complexity-escalator` hook handles this automatically…") rather than MUST/REQUIRED phrasing.

### Conventions to follow

- **CLI shim line**: every `bin/cortex-*` script begins with the cortex-log-invocation telemetry line (see `bin/cortex-check-parity:14`; enforced by `.githooks/pre-commit:97–117` Phase 1.6). New script must include this line in its first 50 lines or pre-commit fails.
- **Atomic JSONL append**: plain `open(..., "a")` + single `f.write(json.dumps(entry) + "\n")` — matches `cortex_command/pipeline/state.py:303` and existing `log_event` precedent. Single JSONL line under PIPE_BUF (4 KB) is atomic on POSIX.
- **Timestamp**: `datetime.now(timezone.utc).isoformat()` — matches `_now_iso()` in `state.py`.
- **Graceful degradation**: hook must silently no-op when research.md is missing, `## Open Questions` is absent, tier is already complex, or events.log is unwritable. Match existing hook precedent (`cortex-skill-edit-advisor.sh:18–26`, `cortex-scan-lifecycle.sh:21`).
- **PostToolUse hook payload format** (Approach C only): JSON input contains `tool_name`, `tool_input.file_path`, `tool_response`. Output JSON shape: `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}` — announcement text goes into `additionalContext` (10,000-char cap).
- **Test layout**: `tests/test_complexity_escalator.py`, importable from `cortex_command.*` or invoking `bin/cortex-complexity-escalator` via subprocess. Closest precedent: `tests/test_common_utils.py` for unit-level event-log scanning logic.

## Web Research

### Anthropic skills-vs-hooks framework

Direct alignment: *"Must the action ALWAYS happen, regardless of Claude's judgment? If YES → Use Hook (deterministic). … Claude cannot skip, forget, or decide otherwise."* (MindStudio, summarizing Anthropic's distinction.) *"Hooks are about controlling behavior, skills are about expanding capability."* Counting bullets in `## Open Questions` is deterministic; encoding it as a protocol step makes it skip-able, which is the canonical anti-pattern.

### Claude Code hooks: supported triggers

Authoritative: <https://code.claude.com/docs/en/hooks>

- **Hook event taxonomy (three cadences):** per-session (`SessionStart`, `SessionEnd`, `Setup`), per-turn (`UserPromptSubmit`, `Stop`, `StopFailure`), per-tool-call (`PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PostToolBatch`). Plus reactive: `FileChanged`, `CwdChanged`, `SubagentStart`.
- **`FileChanged` is officially documented and stable (since Claude Code 2.1.83).** Matcher splits on `|`; segments are literal filenames. **Caveat**: GitHub issue #44925 reports `FileChanged` does not always detect modifications from the Bash tool — relevant if research.md is ever written via heredoc/bash rather than Write/Edit.
- **`additionalContext` mechanism — how hook output reaches the model:** supported on SessionStart, Setup, SubagentStart, UserPromptSubmit, UserPromptExpansion, PreToolUse, PostToolUse, PostToolUseFailure, PostToolBatch. The string is wrapped in a **system reminder** at the point the hook fired; Claude reads it on the next model request. **10,000-character cap** (excess saved to file with preview). **Known bug**: GitHub #14281 reports `additionalContext` injected multiple times.
- **Return shape**: `{"hookSpecificOutput": {"hookEventName": "...", "additionalContext": "..."}}`.
- **Exit codes**: 0 = parse stdout JSON; **2 = blocking** (stderr fed to Claude as error); other = non-blocking. Exit code 1 is treated as non-blocking — a non-intuitive trap.

### Skill-authoring guidance

Authoritative: <https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md>

- **"Tier 3" language is NOT in Anthropic docs** — this is cortex-internal vocabulary. Anthropic documents a three-level progressive-disclosure model (metadata → SKILL.md body → bundled resources), not a Tier 1/2/3 taxonomy.
- The functional guidance the audit invokes IS in skill-creator under different names: *"For assertions that can be checked programmatically, write and run a script rather than eyeballing it."* And: *"If you find yourself writing ALWAYS or NEVER in all caps, or using super rigid structures, that's a yellow flag."*
- Anthropic-recommended SKILL.md size: ~5K tokens / <500 lines.
- Anthropic explicitly uses a `PreToolUse` hook internally to log skill-usage frequency — direct precedent for hooks as the enforcement/observability layer around skills.

### Counter-evidence — when model-executed gates win

- *"LLM-as-a-judge enables evaluation of nuanced, open-ended tasks that are difficult to measure with deterministic methods."*
- *"If a hook is doing complex branching logic, that's a sign it might belong in a skill that Claude controls explicitly instead."* (inverse direction)
- For Gate 1, counting bullets is regex-grade — not in the model-judgment zone. Two genuine counter-arguments: (1) semantic vs syntactic counting (sub-bullets, resolved-inline bullets); (2) late-edit drift (multi-write iterations during refine).

### Key URLs

- [Hooks reference — Claude Code Docs](https://code.claude.com/docs/en/hooks)
- [Anthropic skill-creator SKILL.md](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)
- [Equipping Agents for the Real World with Agent Skills (Anthropic Engineering)](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Claude Code Skills vs Hooks: What's the Difference (MindStudio)](https://www.mindstudio.ai/blog/claude-code-skills-vs-hooks-difference)
- [\[Bug\] FileChanged hook doesn't detect file modifications from Bash tool execution (GitHub #44925)](https://github.com/anthropics/claude-code/issues/44925)
- [\[Bug\] Hook additionalContext injected multiple times (GitHub #14281)](https://github.com/anthropics/claude-code/issues/14281)

## Requirements & Constraints

### From `requirements/project.md`

- **Workflow trimming (lines 22–23)** — directly bears on Gate 2 removal: *"Workflows that have not earned their place are removed wholesale rather than deprecated in stages. Hard-deletion is preferred over deprecation notices… when the surface has zero downstream consumers (verified per-PR). Retired surfaces are documented in `CHANGELOG.md`."*
- **File-based state (line 27)**: No DB/server; hook continues operating on plain markdown/JSON files.
- **Per-repo sandbox registration (line 28)**: `cortex init` already registers `lifecycle/` in `sandbox.filesystem.allowWrite` — events.log writes won't prompt under sandbox.
- **SKILL.md-to-bin parity (line 29)**: `bin/cortex-*` must be wired through SKILL.md / requirements / docs / hooks / justfile / tests references. The one-line SKILL.md pointer satisfies this.
- **SKILL.md size cap (line 30)**: 500 lines, enforced by `tests/test_skill_size_budget.py`. Lifecycle/SKILL.md at 374 today; migration reduces further.
- **Defense-in-depth for permissions (line 38)**: Overnight runner uses `--dangerously-skip-permissions`; sandbox is the critical surface. **Implication**: silent write-denial is possible if `lifecycle/` is not in `allowWrite` (in-flight features started pre-deployment).

### From `requirements/pipeline.md`

- **State write atomicity (line 21, 126)**: tempfile + `os.replace()`. Single JSONL line append is also safe under PIPE_BUF.
- **State file locking constraint (line 134, permanent)**: *"State file reads are not protected by locks by design. Writers use atomic `os.replace()`; readers may observe a state mid-mutation, but forward-only transitions make this safe."*
- **Orchestrator rationale convention (line 130)**: *"When the orchestrator resolves an escalation or makes a non-obvious feature selection decision, the relevant events.log entry should include a `rationale` field explaining the reasoning."* The new `gate` field plays a similar attribution role.

### From `requirements/multi-agent.md`

- **Model Selection Matrix (lines 54–65)**: complexity tier is a routing primitive. `simple → complex` shifts model selection (haiku/sonnet → opus). The hook's escalation has structural downstream impact on overnight runs.

### From `CLAUDE.md`

- **MUST-escalation policy (OQ3, lines 51–59)**: Removing MUST prose by replacing it with deterministic mechanism is unencumbered; adding new MUST language requires F-row + `effort=high` evidence. The SKILL.md replacement pointer should use soft positive-routing.

### Audit document alignment evidence (load-bearing)

**Critical finding: There is no `## Tier 3 — Move execution out of the model entirely` *section* in `research/vertical-planning/audit.md`.** The phrase appears only inside the "**Resolved holds (2026-05-06)**" subsection. The Tier 3 framing is a compression-direction decision recorded inside one resolved-hold paragraph — not a structurally prominent recommendation of the audit corpus.

Verbatim from `audit.md:400` (inside "Resolved holds" > "Hold 1"):

> Hold 1 — Specify→Plan and Research→Specify escalation gates. **Resolution: keep both gates**. Inspecting the actual gate code (`lifecycle/SKILL.md:244-260, 294-312`), both auto-escalate `simple` → `complex` (≥3 Open Decisions bullets in spec, or ≥2 Open Questions bullets in research). Complex tier triggers `/cortex-core:critical-review`, runs orchestrator-review (which `low+simple` skips), and may shift model selection downstream. **Both gates are kept**; D4 (make Open Decisions optional) remains BLOCKED in the decomposition because making the section optional would silently disable D-gate escalation.
>
> The compression direction: **Tier 1 in-skill compression** (deduplicate the gate description that currently appears twice in SKILL.md, collapse two-gate prose into one unified paragraph, replace inlined `complexity_override` JSON with a schema pointer) — **~40 lines off SKILL.md, zero behavior change.** Goes into Stream B as a new ticket. Plus **Tier 3 hook migration** — move both gates to a deterministic Python hook (`cortex-complexity-escalator`) on research→specify and specify→plan transitions, removing gate logic from SKILL.md entirely. **Additional ~25 lines off SKILL.md, gate execution moves out of model context entirely** (no token spend at gate-evaluation time, deterministic behavior). New Stream H.

And from `decomposed.md:22`: `| 183 | Migrate complexity-escalation gates to deterministic Python hook (cortex-complexity-escalator) | medium | M | 174, 177 |`

**Alignment-and-divergence between child ticket and audit:**

1. **Gates named?** Yes. Audit cites both gates by description (Research→Specify, Specify→Plan); the "Gate 1 / Gate 2" numbering is downstream invention.
2. **Audit-prescribed scope**: **migrate BOTH gates** to the hook ("move both gates to a deterministic Python hook"). Child ticket diverges to "migrate Gate 1 only; remove Gate 2 entirely."
3. **Audit's Hold-1 resolution explicitly says "keep both gates."** Child ticket's "remove Gate 2 entirely" **inverts** this. The user's structural argument ("Gate 1 is the same-session forcing function for overnight contexts; Gate 2 has 0 fires") is a re-scoping that diverged from the audit's resolution.
4. **Audit explicitly couples Gate 2 to #180 D4**: *"D4 (make Open Decisions optional) remains BLOCKED in the decomposition because making the section optional would silently disable D-gate escalation."* Removing Gate 2 unblocks #180 D4 by **consequence**, not by intent.

The child ticket's scope is consistent with the audit's Tier 3 hook-migration direction (positive trace), but diverges from the audit's "keep both gates" resolution (negative trace).

## Tradeoffs & Alternatives

### Approach A: True deterministic hook on file-write watcher (`FileChanged`)

**Description**: Register a `FileChanged` hook matching `lifecycle/*/events.log` or `lifecycle/*/research.md`; Python script runs entirely outside the model.

**Pros**: Highest determinism — fires regardless of model behavior. Zero model-token cost. True separation of concerns.

**Cons**: First `FileChanged` adopter in cortex (zero precedent). Inherits known bugs: GitHub #44925 (Bash-tool mutations not always detected) and #14281 (additionalContext multi-injection). Glob/filename matching semantics are not battle-tested in this repo.

**Verdict**: Feasible per Anthropic docs but operationally untested in cortex. Spec must explicitly accept first-adopter risk.

### Approach B: Explicit invocation from SKILL.md protocol step

**Description**: Replace ~10 lines of Gate 1 prose with one line: *"Run `cortex-complexity-escalator <feature>` at the research→specify transition."* Python script does all evaluation.

**Pros**: Feasible today with zero harness extension. Token savings on gate prose. Matches existing precedent (cortex-update-item, cortex-resolve-backlog-item, cortex-load-parent-epic — all single-line model-invoked utilities). Hook failure surfaces visibly (exit code, stderr). No new trigger pattern.

**Cons**: Triggering still depends on the model executing the SKILL.md step — the same failure mode the migration is allegedly designed to prevent. The "deterministic" claim covers only post-invocation Python; the trigger is soft-routed. **See FM-6 below for the load-bearing critique.**

**Verdict**: Most feasible. Determinism claim is rhetorical, not structural.

### Approach C: PostToolUse matcher on Write|Edit

**Description**: PostToolUse hook on `Write|Edit`; hook self-classifies whether the write was research.md and emits escalation.

**Pros**: Fires deterministically from harness — no model routing. Hook event already exists; strong cortex precedent (3 existing hooks).

**Cons**: Triggers on *every* Write/Edit. Refine's iterative research.md authoring → multi-fire. The hook would escalate on the first write with ≥2 Open Questions, possibly mid-research. **The trigger granularity doesn't match the gate's conceptual boundary.** State-debouncing inside the hook (e.g., `.research-locked` flag) recreates SKILL.md prose fragility, just relocated.

**Verdict**: Semantically wrong. Trigger fires at write-events; gate semantic is at phase-transition.

### Approach D: Status quo

**Description**: Keep Gate 1 prose in SKILL.md as-is.

**Pros**: Zero implementation cost.

**Cons**: ~10 lines of detection prose in every prompt that reads lifecycle SKILL.md — non-trivial cumulative token cost. Model-executed counting is empirically inconsistent (audit's "tentative" classification).

**Verdict**: Loses on token cost.

### Approach E: Reframe gate as Spec-phase-entry guard

**Description**: Drop the protocol step at research→specify; instead, Spec phase's opening guard runs the script.

**Pros**: Co-locates gate with the phase that consumes the tier signal.

**Cons**: Equivalent to Approach B in failure-mode (still model-routed); slight discoverability cost.

**Verdict**: Equivalent to B.

### Sub-topic: Gate 2 removal scope-bundling

**Recommendation: Bundle** (Tradeoffs agent's call) — but **see FM-1, FM-2, A-1 below** for adversarial findings that materially weaken the bundling rationale.

### Sub-topic: Hook location

**Recommendation: `bin/cortex-complexity-escalator`** (no extension). Pattern alignment with existing `cortex-*` utilities; auto-mirrored without manifest edit; globally PATH-available after `uv tool install`.

### Sub-topic: Event schema migration

**Recommendation: Add `gate: "research_open_questions"` as pure additive field. Do not bump schema_version** — lifecycle events.log entries don't currently carry one. **But see A-3 below**: three payload shapes exist; a schema-version bump or canonicalization migration may be warranted.

### Recommended approach (pre-adversarial)

**Approach B + Gate 2 deletion bundled + `bin/cortex-complexity-escalator` + additive `gate` field.**

Anchored in: simplicity-first, file-based state, alignment with existing patterns (`cortex-*` utilities), OQ3 compatibility (no new MUST), plugin-mirror dual-source already covered.

## Adversarial Review

### Failure modes and edge cases

**FM-1: The "Gate 2 has 0 fires" claim is empirically unverifiable.** No events.log in the corpus records `gate` provenance — the 18 features with `complexity_override` events use the legacy `{from, to}` schema only. The "0 vs 11" attribution is timing-pattern heuristics (per this feature's own clarify_critic finding 1), not payload-level attribution. The Tradeoffs agent's "bundle Gate 2 deletion" recommendation rests on an unprovable empirical premise.

**FM-2: Strong selection-effect signal on Gate 2.** Running the actual bullet-count regex over `lifecycle/*/spec.md`: eleven specs have ≥3 bullets under `## Open Decisions` (maxima 16, 12, 9, 9, 8, 7, 6, 5, 5, 3, 3). Of those eleven, ten are in `archive/` (historical); only one is in active `lifecycle/`. Two interpretations: (a) the active workflow has correctly internalized "don't park ≥3 things in Open Decisions" — the gate works as a forcing function, low fire rate IS its success; (b) the workflow learned to relocate items to dodge the gate — silent failure mode. **Either interpretation breaks the "remove because unused" argument.**

**FM-3: Bullet-counting is semantically misaligned with Refine's own "open" definition.** Inspecting real research.md files:
- Some use `### Resolved at Research exit gate` sub-headings with **numbered** lists, not bulleted. Naive `^[\s]*[-*]` regex returns 0.
- Some research.md bullets begin with `- **FeatureResult**…Deferred: will be resolved in Spec by asking the user` — Refine's Research Exit Gate (`skills/refine/SKILL.md:149`) treats these as PASS (explicitly deferred). A bullet-counting hook on the literal `## Open Questions` section counts them as open and escalates, **contradicting Refine's own resolved/deferred semantic**.
- Fenced code blocks containing `-` lines, blockquoted bullets, multi-paragraph children — none handled.

**The hook's deterministic algorithm is determinism around the wrong predicate.** Refine defines "open" as bare-unannotated; bullet-count includes everything.

**FM-4: PostToolUse fires before content stabilization.** Refine authors research.md incrementally (Clarify → Research → critic-fix → exit-gate-resolve). The hook would escalate at the transient peak (mid-authoring with 3 transient questions) even if exit-gate resolves to 1. **PostToolUse has no access to lifecycle phase**, so it cannot enforce "evaluate at transition."

**FM-5: `FileChanged` operationally untested in cortex.** Officially documented but zero in-repo precedent. Adopting it for this gate means (a) becoming the first `FileChanged` consumer, (b) inheriting GitHub bugs #44925 and #14281, (c) discovering the per-tool detection caveats live.

**FM-6: Approach B's "determinism" is rhetorical.** The migration's stated rationale is "Gate 1 is the same-session forcing function for overnight contexts." If the model is still the trigger, the failure mode that motivated migration — model skips the gate step — is exactly preserved. What actually changes: token spend at evaluation moves out of context (small win); bullet-counting becomes specifiable in pytest (small win, **unless the algorithm doesn't match the semantic — see FM-3**); event shape becomes uniform. **The "determinism" claim covers only the post-invocation pipeline.** Calling this a "determinism migration" oversells the structural change. Honest framing: **prose compression with an algorithmic side-pin**, not deterministic gate execution.

**FM-7: Idempotency-by-state-check is necessary but not sufficient.**
- **Edit-down**: research.md edited to remove Open Questions after escalation — should tier downgrade? The codebase has one explicit downgrade event in `trim-and-instrument-overnight-plan-gen-prompt/events.log`. A `complex → simple` downgrade IS supported by the schema, but the gate's `from: simple` guard means a hook would silently fail to downgrade.
- **Schema evolution**: two pre-schema-v2 entries use a YAML-style form; the test fixture uses a third shape. The hook's "already exists" guard must recognize all three, or it re-escalates already-complex features.

### Security concerns and anti-patterns

**SEC-1: Silent write-denial in overnight contexts.** The hook depends on `lifecycle/` being in `sandbox.filesystem.allowWrite` (registered by `cortex init`). In-flight overnight sessions started before deployment hit either (a) sandbox prompts (interactive — disruptive) or (b) **silent denial** (overnight, `--dangerously-skip-permissions` masks it). Worse: the overnight context masks the write failure, announcement still prints, but no event lands, and resume-detection re-evaluates as simple. **Each subsequent round re-escalates and re-fails-silently — corrupting failure mode unique to migrating gates to Python.** Mitigation: read-after-write verification before announcing.

**SEC-2: Path-traversal hardening.** If a Bash shim (Approach C) extracts the feature slug from `tool_input.file_path` and uses it in `lifecycle/$FEATURE/events.log`, maliciously crafted path inputs (`../../../etc/passwd`) require defense. Spec must require feature-slug regex allowlist (`^[a-zA-Z0-9._-]+$`) and refuse to operate outside `lifecycle/`.

**SEC-3: Plugin-mirror drift on TWO files (Approach C).** Approach C adds both `bin/cortex-complexity-escalator` AND `claude/hooks/cortex-complexity-escalator.sh`, each with plugin mirrors. The parity linter checks file-content equivalence under matched paths but doesn't check hooks.json semantic equivalence. If `.claude/settings.json` registers the matcher but `plugins/cortex-core/hooks/hooks.json` doesn't, the hook fires in-repo but not for plugin-installed users.

### Assumptions that may not hold

**A-1: The audit's "Tier 3" framing is paraphrased — the audit's actual Hold-1 resolution was "keep BOTH gates."** Removing Gate 2 inverts the resolution. Removing Gate 2 ALSO unblocks #180 D4 by consequence, not intent.

**A-2: "Structural justification, not empirical" is a hedge.** The same ticket invokes Workflow Trimming (which hinges on empirical "hasn't earned its place") AND structural arguments. CLAUDE.md OQ3 governs escalation rigor by analogy; de-escalation deserves the same standard if Workflow Trimming is invoked. Spec must commit to one framing.

**A-3: Three event-payload shapes exist in production.** "Purely additive" is too narrow. Adding `gate` to NEW events compounds the schema zoo. Spec should mandate a one-time canonicalization, OR document the multi-shape tolerance requirement on readers.

**A-4: Schema source-of-truth correction.** `cortex_command/overnight/events.py` is the wrong file. Canonical writer is `cortex_command/pipeline/state.py:288 log_event`. No schema enforcement at that layer.

**A-5: Test surface for "gate fires in overnight" is achievable.** With Approach B, this is faith-based — the Python script is unit-testable but "model invokes SKILL.md step in overnight" is the soft surface the migration claims to escape. Real determinism win requires hook-level invocation.

### Recommended mitigations (spec MUST resolve)

1. Refute or accept FM-2 explicitly — produce gate-attributed fire-rate data OR reframe under Workflow Trimming with selection-effect risk accepted and rollback signal defined.
2. Specify the bullet-counting algorithm with named edge cases — regex form; numbered-list treatment; resolved/deferred prefix handling; fenced code blocks; blockquotes; alignment to Refine's bare-unannotated semantic. With pytest fixtures covering each case.
3. Pick ONE trigger mechanism and accept its failure mode. Approach B: drop "determinism" framing, call it compression. Approach C: handle multi-fire AND fix transition-vs-write semantic mismatch. Approach A: accept first-adopter status, reference bugs.
4. Define idempotency monotonicity (upward-only or bidirectional). Hook must recognize all three existing payload shapes.
5. Path-traversal hardening + write-success verification (SEC-1, SEC-2).
6. Schema-source-of-truth correction (A-4).
7. Define #180 D4 consequence (A-1).
8. Define rollback story for Gate 2 removal — watch-list, review cadence, restoration path.
9. Plugin-mirror hooks.json equivalence check (if Approach C).
10. Deployment story for in-flight features (SEC-1).

### Bottom-line challenge

(1) **The "Gate 2 has 0 fires" empirical claim is unsupported** — 11 historical specs would have been Gate-2-eligible by the prose-stated bullet-count rule; no payload encodes gate provenance.

(2) **Bullet-counting is not the same as open-question counting in this codebase** — Refine's own gate defines resolved/deferred/bare-unannotated semantics; the proposed hook's algorithm conflicts and will over-escalate.

Together: the migration as scoped will (a) remove a gate on a premise that can't be validated, and (b) install a "deterministic" replacement that's deterministically misaligned with the codebase's own definition of "open."

## Open Questions

Spec phase MUST resolve these before the migration lands. Each is annotated with a recommended disposition or framing for the structured interview to commit to.

- **Gate 2 removal premise**: Is the structural argument ("0 fires + redundant with §2b Pre-Write Checks + orchestrator-review S-checklist") sufficient justification, given FM-2's selection-effect risk and FM-1's data attribution gap? Recommended Spec resolution: accept structural argument with explicit rollback signal defined, OR de-scope Gate 2 deletion from this ticket and reopen as a separate evidence-gathering task.

- **Bullet-counting algorithm**: How does the hook count "Open Questions"? Bare bullet count, or aligned with Refine's resolved/deferred/bare-unannotated semantic (`skills/refine/SKILL.md:149`)? Numbered lists, sub-bullets, fenced code blocks — included or excluded? Recommended Spec resolution: align with Refine's semantic (count only bare-unannotated bullets at the top level of `## Open Questions`); add a pytest fixture covering each named edge case.

- **Trigger mechanism**: Approach B (explicit invocation from SKILL.md), Approach C (PostToolUse + idempotency guard), or Approach A (FileChanged, first cortex adopter)? Recommended Spec resolution: Approach B, with honest framing as "compression with algorithmic side-pin" rather than "determinism migration."

- **Idempotency monotonicity**: Upward-only escalation (current de-facto behavior), or bidirectional (downgrade on content-removal)? Recommended Spec resolution: monotonic-upward, documented explicitly. Hook recognizes all three existing payload shapes when guarding.

- **Write-success verification**: Read-after-write check before announcing escalation? Recommended Spec resolution: yes — defends against SEC-1 silent-denial.

- **Path-traversal hardening**: Required for any path-derived input? Recommended Spec resolution: required if Approach C; optional but recommended for Approach B (feature slug regex `^[a-zA-Z0-9._-]+$`, realpath containment under `lifecycle/`).

- **#180 D4 consequence**: Is removing Gate 2 understood as unblocking #180 D4 (per ticket body) AND surfacing the audit-resolution divergence (per A-1)? Recommended Spec resolution: document the unblocking explicitly and note that the audit's stated reason for blocking D4 is removed by side-effect.

- **Schema source-of-truth correction**: Update references from `cortex_command/overnight/events.py` to `cortex_command/pipeline/state.py:288`? Recommended Spec resolution: yes.

- **Three event-payload shapes**: Tolerate all three (status quo + new additive `gate` field), or canonicalize? Recommended Spec resolution: tolerate (consistent with `read_tier`'s permissive reading), with a comment documenting the tolerance.

- **Rollback story**: If Gate 2 removal silently degrades plan quality on a class of features, what's the signal and restoration path? Recommended Spec resolution: define a watch-list (specs with ≥3 Open Decisions that went simple-tier), a review cadence (4 weeks post-landing), and a restoration path (prose+tests only; Gate 2 has zero Python references).

## Considerations Addressed

- **The audit-trace consideration**: PARTIALLY VALIDATED. The audit-document trace IS direct — `research/vertical-planning/audit.md:400` and `research/vertical-planning/decomposed.md:22` both explicitly name the gate migration as Tier 3 hook migration in Stream H (ticket 183). Positive trace on direction. However, the audit's stated resolution was **"keep both gates and migrate both"**, which the child ticket inverts to "migrate Gate 1 only; remove Gate 2 entirely." The audit also explicitly couples Gate 2 to #180 D4 (D4 BLOCKED because Gate 2 needs the Open Decisions section). The child's intent is consistent with the audit's Tier 3 hook-migration direction but **divergent from the audit's "keep both" resolution**. Surfaced as Open Question on #180 D4 consequence — Spec must explicitly accept this divergence or reconsider.
