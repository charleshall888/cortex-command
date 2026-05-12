# Research: Eliminate cross-skill duplication in `skills/refine/references/`

Goal: delete `skills/refine/references/orchestrator-review.md` and `skills/refine/references/specify.md`, redirect refine to read `skills/lifecycle/references/specify.md` (and pick up `skills/lifecycle/references/orchestrator-review.md` transitively), while preserving refine's existing Step 5 adaptations.

## Codebase Analysis

### Files that will change

**Deletions (canonical):**
- `skills/refine/references/orchestrator-review.md` (183 lines)
- `skills/refine/references/specify.md` (163 lines)

**Modification (canonical):**
- `skills/refine/SKILL.md` line 177 only — change `Read \`references/specify.md\` and follow its full protocol (§1–§4) with these adaptations:` to read from the lifecycle copy.

**Auto-pruned mirrors** (rsync `-a --delete` removes these on next `just build-plugin`):
- `plugins/cortex-core/skills/refine/references/orchestrator-review.md`
- `plugins/cortex-core/skills/refine/references/specify.md`

**Unchanged:**
- `skills/lifecycle/references/specify.md` (canonical superset; now read by refine)
- `skills/lifecycle/references/orchestrator-review.md` (lifecycle-only invoker today; refine reaches it transitively after the change)
- All other refine references files (`clarify.md`, `clarify-critic.md`) — out of scope for this ticket; covered by tickets 175 and 176.

### Ticket prescription correction (load-bearing)

The ticket says "Update SKILL.md Step 4 (orchestrator-review invocation) and Step 5 (specify invocation)." This is **wrong about Step 4**. Refine SKILL.md only directly references `references/`-prefixed files at lines 38, 65, 86 (all `clarify.md`) and line 177 (`specify.md`). It never directly references `orchestrator-review.md`. Step 4 is the Research phase; the orchestrator-review invocation is reached *transitively* via lifecycle's `specify.md:145` ("Before presenting the artifact to the user, read and follow `references/orchestrator-review.md` for the `specify` phase"). The actual SKILL.md edit envelope is **one line: line 177**.

### Diff baseline (verified against working tree)

- `skills/refine/references/orchestrator-review.md` (183 lines) vs `skills/lifecycle/references/orchestrator-review.md` (184 lines): differ by exactly one line — lifecycle has the `P8 Architectural Pattern` row at line 165; refine omits it because refine never reaches the plan phase. Body byte-identical.
- `skills/refine/references/specify.md` (163 lines) vs `skills/lifecycle/references/specify.md` (186 lines): refine drops the trailing 23 lines (the `### 5. Transition` block + `## Hard Gate` table). Body byte-identical for §1–§4.

The two files are NOT byte-identical; "near-byte-identical" is the correct framing. The *delta sections* are deliberate — refine SKILL.md Step 5 already documents the §5 Transition skip explicitly (line 183).

### Existing patterns and infrastructure

- **Dual-source parity test** (`tests/test_dual_source_reference_parity.py`): discovers canonical–mirror pairs via `skills/*/references/*.md` glob and asserts byte parity; deleted canonical files automatically drop from the parametrized count. Verification command in the ticket ("collected pairs drop by 2") will pass automatically.
- **`justfile build-plugin`**: `for s in "${SKILLS[@]}"; do rsync -a --delete "skills/$s/" "plugins/$p/skills/$s/"; done`. The `--delete` flag prunes orphaned mirror copies when canonical files are removed. No tooling change needed.
- **`.githooks/pre-commit` Phase 4 (Drift loop)**: runs `git diff --quiet plugins/$p/` after build-plugin; blocks the commit if mirror trees diverge from the index. After this ticket: must run `just build-plugin && git add plugins/cortex-core/skills/refine/` before committing.
- **No precedent for cross-skill SKILL.md → references/ reads**: grep across all SKILL.md files finds zero examples of one skill's SKILL.md pointing at another skill's `references/` file. This ticket establishes a new pattern.

### Refine SKILL.md Step 5 adaptation list (current state)

Lines 178–184 enumerate five adaptations: §1 (Load Context redundant-loading skip), §2a (loop-back to Research), §3b (tier detection from events.log), §4 (Complexity/value gate addition), §5 (Transition skip). The list does **not** enumerate `## Hard Gate` — that section is structurally a top-level `##` heading in lifecycle/specify.md (lines 177–186), not a `###` subsection of `## Protocol`. The argument that "refine follows §1–§4 only, so Hard Gate is outside scope" is a reasonable reading but is not encoded in the adaptation list.

### Ticket 173 collision check

Ticket 173 (Z-stream, `status: backlog`) edits refine/SKILL.md lines 117–157 (the duplicate Alignment-Considerations Propagation block) and lines 231–232 (`update_item.py` → `cortex-update-item` rename in the Constraints table). Ticket 174 edits line 177. **No line overlap.** However, line numbers will shift if 173 lands first (it deletes ~40 lines of duplicate block at 117–157), so when applying 174, target the `Read \`references/specify.md\`` *string* rather than `line 177` — the SKILL.md edit must be content-addressed, not position-addressed.

### Refine SKILL.md path-style audit

Refine SKILL.md uses **bare relative** paths (`references/clarify.md`, `references/specify.md`) — lines 38, 65, 86, 177. Lifecycle SKILL.md uses **${CLAUDE_SKILL_DIR}-prefixed** paths (`${CLAUDE_SKILL_DIR}/references/...`). The proposed edit invents a third style: bare-but-cross-skill (`skills/lifecycle/references/specify.md`). This is a path-style proliferation worth resolving as a design decision.

### Plan-phase invariant for refine

Refine SKILL.md Steps 1–6 do not reach plan phase; the lifecycle skill owns plan. The `P8 Architectural Pattern` row is gated on `criticality = critical` AND fires only in plan-phase orchestrator-review. Refine never invokes plan-phase orchestrator-review, so the lifecycle copy's P8 row is harmless noise. There is no automated test enforcing "refine never reaches plan"; if a future change to refine adds a lite-plan step, P8 silently applies with no signal.

## Web Research

### Claude Code skill path resolution

- **Filesystem-based, not skill-relative.** Per Anthropic's Claude Code skills doc, Claude reads SKILL.md "from the filesystem via bash" and "uses bash Read tools to access SKILL.md and other files." There is no special skill-relative path resolver — Claude is shown the SKILL.md text and resolves references by issuing Read tool calls against whatever string it sees.
- **`${CLAUDE_SKILL_DIR}` is invoking-skill-only.** Documented as "the directory containing the skill's SKILL.md file. For plugin skills, this is the skill's subdirectory within the plugin, not the plugin root." There is no `${CLAUDE_OTHER_SKILL_DIR}` or `${CLAUDE_PLUGIN_ROOT}/skills/<other>` substitution. `${CLAUDE_SKILL_DIR}` is also NOT substituted in SKILL.md frontmatter hook commands (claude-code issue #36135).
- **Cross-plugin skill references are explicitly NOT first-class.** Claude-code GitHub issue #15944 (CLOSED, feature request, not implemented): "Currently, the `skills` field in `agents.md` only supports referencing skills within the same plugin. There is no way for an agent to load or invoke skills from other installed plugins." The proposed `plugin-b:external-skill` syntax is unimplemented. Issue #27332 documents that plugin skill resolution can fail against `.claude/skills/` rather than the plugin cache.
- **"One level deep" best-practice warning.** Anthropic skills best-practices doc: "Claude may partially read files when they're referenced from other referenced files. When encountering nested references, Claude might use commands like `head -100` to preview content rather than reading entire files, resulting in incomplete information. **Keep references one level deep from SKILL.md**." Pointing refine SKILL.md at lifecycle/references/specify.md (which itself references orchestrator-review.md) is exactly the two-hop pattern the docs flag.
- **Relative-path first-execution failure.** Claude-code issue #11011: "Skill plugin scripts fail on first execution with relative path resolution; on second try Claude Code uses the absolute path and successfully executes." Documents that relative paths are an unreliable resolution form.

### DRY patterns for agent-protocol markdown

Three published patterns, increasing fragility:
1. **Symlinks** — recommended in the AGENTS.md ecosystem for keeping `AGENTS.md`, `CLAUDE.md`, `.cursorrules` in sync. Risk for cortex: zero precedent under `skills/`; CLAUDE.md notes "ships as a CLI ... no longer deploys symlinks into ~/.claude/."
2. **File transclusion / `@imports`** — Claude Code's `CLAUDE.md` supports `@path/to/file`. Skills do **not** have a documented `@import` mechanism.
3. **Build-time mirroring** — cortex's existing dual-source pattern. Solves canonical-vs-mirror but does not address intra-canonical duplication (which is this ticket's target).

Closest published precedent: the `coreyhaines31/marketingskills` foundation-context pattern — implemented as prose instruction in each consumer SKILL.md, smoke-test verified, no formal mechanism.

### rsync `-a --delete` confirmed safe for mirror cleanup

Verified the `--delete` flag will prune orphaned mirror files. The risk is that rsync faithfully reproduces dangling SKILL.md references — the mirror does not validate that referenced files still exist. Mitigation requires a grep-based gate that asserts every `Read references/<file>` string in any SKILL.md resolves. Ticket 181 plans such a test (test #3 reference-file path resolution); currently `status: backlog`, `blocked-by: [178]`.

### URLs

- https://code.claude.com/docs/en/skills
- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- https://github.com/anthropics/claude-code/issues/15944 (cross-plugin skill refs feature request, CLOSED)
- https://github.com/anthropics/claude-code/issues/11011 (relative-path failure mode)
- https://github.com/anthropics/claude-code/issues/30578 (`${CLAUDE_SKILL_DIR}` shipped in v2.1.64)
- https://github.com/anthropics/claude-code/issues/36135 (`${CLAUDE_SKILL_DIR}` not substituted in frontmatter hooks)
- https://github.com/anthropics/skills (no cross-skill reference pattern in published examples)

## Requirements & Constraints

### From `requirements/project.md`

- **Maintainability through simplicity**: "Complexity is managed by iteratively trimming skills and workflows. The system should remain navigable by Claude even as it grows." → directly aligns with this ticket.
- **Complexity must earn its place**: "When in doubt, the simpler solution is correct." → the dedup proposal is the simpler runtime; the question is whether the cross-skill coupling is simpler than the duplication.
- **Workflow trimming**: "Hard-deletion is preferred over deprecation notices, tombstone skills, or env-var soft-deletes when the surface has zero downstream consumers (verified per-PR)." → straightforward hard-deletion of the two files matches the directive.
- **SKILL.md-to-bin parity enforcement**: applies to `bin/cortex-*` scripts, not skill reference files. Doesn't directly govern this change but the dual-source pattern it codifies is the model.
- **Sandbox preflight gate**: fires only when staged diffs touch sandbox source files (`cortex_command/overnight/sandbox_settings.py`, `cortex_command/pipeline/dispatch.py`, `cortex_command/overnight/runner.py`, `pyproject.toml`). This ticket touches none → preflight does NOT apply.

### From `CLAUDE.md`

- MUST-escalation policy: this ticket adds no MUST language → no escalation note required.
- 100-line cap: ticket does not edit CLAUDE.md → not triggered.

### From `bin/.parity-exceptions.md`

Closed-enum categories (`maintainer-only-tool`, `library-internal`, `deprecated-pending-removal`) — none apply; no parity exception needed.

### From parent epic 172

Frames this as **stream A** (cross-skill collapse) — prerequisite for stream F (vertical-planning adoption, ticket 182). Stream Z (ticket 173, copy-paste-bug fix in refine/SKILL.md) is sequenced before A. This ticket is on the critical path between Z and F. Audit (`research/vertical-planning/audit.md`) explicitly recommended this exact approach (lines 125–126, 350–351); also explicitly flagged the gap "No cross-skill handoff integration tests" (audit.md:287) — covered by ticket 181, currently `status: backlog`.

## Tradeoffs & Alternatives

Six approaches considered:

### Approach A: Cross-skill direct read (the ticket's proposal)
Refine SKILL.md line 177 → `Read skills/lifecycle/references/specify.md`. Transitive resolution picks up orchestrator-review.md.
- **Complexity**: Lowest — 2 deletions + 1 SKILL.md edit + 1 build-plugin run. Existing parity infra handles deletion automatically.
- **Maintainability**: Adding sections to lifecycle/specify.md propagates to refine automatically. Forward-coupling cost: refine SKILL.md adaptation list must be re-audited every time lifecycle/specify.md grows. No owner today.
- **Performance**: Token cost during refine runs *increases* by ~23 lines (refine now reads §5 + Hard Gate it doesn't need). Static repo size drops by 346 lines.
- **Pattern alignment**: Matches the audit's recommendation. Establishes a new cross-skill prose-reference pattern with no existing precedent in the repo.

### Approach B: Symlink
`skills/refine/references/specify.md` becomes a symlink to `../../lifecycle/references/specify.md`.
- Zero precedent under `skills/`; CLAUDE.md explicitly notes "no longer deploys symlinks." Inverts the dual-source contract; symlinks across canonical skill dirs surface odd states in the mirror tree.
- **Rejected.**

### Approach C: Shared `_shared/references/` directory
Promote both files to a new shared location.
- Breaks the implicit invariant that each `skills/X/` is a deployable skill (no SKILL.md in `_shared/`). `justfile build-plugin` would need plugin-mapping logic. Higher complexity, no precedent.
- **Rejected.**

### Approach D: 1-line stub include
Reduce refine's references/specify.md to one line: `Read skills/lifecycle/references/specify.md and follow §1–§4.`
- Inverts progressive disclosure (SKILL.md → stub → real file). No precedent for stub reference files. Adds an extra read per invocation.
- **Rejected** — except as a *targeted* mitigation for the orchestrator-review transitive-resolution risk (see Open Questions).

### Approach E: Status quo
Keep duplication.
- Violates "complexity must earn its place." Manual sync has empirically failed (the audit found 1-line drift). Pays ~346 lines in static corpus cost permanently.
- **Rejected.**

### Approach F: Generated copies (build-time templating)
Refine's references/ files generated by stripping refine-irrelevant sections from lifecycle's at build time.
- New tooling burden; new "what is canonical" question; breaks the dual-source mental model.
- **Rejected** — tooling-heavy, no precedent.

### Recommended: Approach A — but with three mitigations applied to address adversarial findings (see Open Questions). Without those mitigations, A has at least three independent failure modes the proposed smoke test will not catch.

## Adversarial Review

### Failure modes the smoke test will not catch

**(F1) Smoke test likely won't exercise the orchestrator-review path.** Lifecycle/references/orchestrator-review.md lines 9–11 SKIP the entire orchestrator-review when `criticality: low` AND `tier: simple`. The path of least resistance for a smoke test is a simple+low fixture, in which case the second-hop reference is never followed and a transitive-resolution bug doesn't surface. The ticket's verification ("a fresh refine run completes Clarify → Research → Specify successfully") doesn't mandate a non-skipping criticality+tier combination.

**(F2) Spurious `phase_transition` event emission risk.** Refine SKILL.md line 183 says "§5 (Transition): Skip — /cortex-core:refine does not log phase transitions." But that skip note lives in refine SKILL.md, NOT in the file refine reads. When Claude reads `lifecycle/references/specify.md`, lines 165–175 give an explicit, copy-paste-ready event JSON template ("Append a `phase_transition` event...") plus a follow-on commit instruction. Post-Opus-4.7 prompt-following is more literal than 4.5. Risk: a refine session emits a `from: "specify", to: "plan"` event into events.log when refine never actually transitions to plan — corrupting the event log used by morning-review and overnight selection. Smoke test passes; bogus event row is a delayed-detection bug.

**(F3) Hard Gate inheritance.** Refine SKILL.md Step 5 enumerates §1, §2a, §3b, §4, §5 — **not** `## Hard Gate`. Hard Gate is a top-level `##` heading (same level as `## Protocol`), not a `###` subsection. The "outside §1–§4" argument is a reasonable reading but isn't encoded; the file refine reads contains a top-level "Do NOT write any implementation code during this phase" instruction the adaptation list doesn't acknowledge. In practice harmless (refine doesn't write impl code), but it's a documentation-correctness gap.

**(F4) Anthropic "one level deep" violation.** Currently refine has a one-level architecture: `refine/SKILL.md → refine/references/specify.md → STOP` (orchestrator-review hop is local). After: `refine/SKILL.md → lifecycle/references/specify.md → lifecycle/references/orchestrator-review.md` — two-level chain across skill boundaries. The Anthropic best-practices doc warns about exactly this. `head -100` of `lifecycle/references/orchestrator-review.md` cuts off at line 100 (inside the Fix Dispatch section), missing the S1–S6 Post-Specify Checklist (lines 125–165). Failure mode: refine runs orchestrator review with a partial checklist and silently passes on items it never read.

**(F5) Path resolution ambiguity in plugin-cache install.** Refine ships in `~/.claude/plugins/cache/<mkt>/cortex-core/<version>/skills/refine/SKILL.md`. The proposed edit "Read skills/lifecycle/references/specify.md" is bare-relative from no defined root. Resolves against Claude Code's CWD (the user's repo, often), which works for cortex-command development but is undefined for end-user installs where the user's CWD has no `skills/` dir. Should use `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` style or path-qualify with `${CLAUDE_PLUGIN_ROOT}` (which doesn't exist as a substitution).

### Assumptions that may not hold

**(F6) "Refine never reaches plan phase" is true today, not enforced.** No test, no parity check, no SKILL.md statement codifies this invariant. If a future refine change adds a lite-plan step (e.g., as part of stream F), the P8 row would silently apply with no signal.

**(F7) Forward-coupling cost is significant and unowned.** Stream F (ticket 182, vertical-planning adoption) explicitly adds new sections (`## Phases`, P9/S7 gates) to lifecycle/specify.md. After 174 lands, every change to lifecycle/specify.md is a behavior change for two skills. Refine SKILL.md adaptation list becomes the only defense against unwanted propagation. There is no owner for re-auditing it.

**(F8) Audit's safety reasoning is partially circular.** The audit rated cross-skill collapse "low risk (refine SKILL.md already enumerates the deltas)" — but the safety check author also wrote both sides. The audit also explicitly listed "No cross-skill handoff integration tests exist" — meaning the test that would prove this dedup safe doesn't exist yet. Per backlog/181, that test is `blocked-by: [178]` and `status: backlog`. Landing 174 before 181 lands removes the file the test would target before the test exists.

### Recommended mitigations

**(M1)** Edit `skills/lifecycle/references/specify.md:145` to use a path-qualified pointer: `Read skills/lifecycle/references/orchestrator-review.md` instead of bare `Read references/orchestrator-review.md`. One-line edit in lifecycle's owned file. Eliminates the entire transitive-resolution class of failures globally — for refine's new cross-skill read AND for any future cross-skill consumer. **Highest leverage.**

**(M2)** Add explicit acknowledgments to refine SKILL.md Step 5 adaptation list for the three sections refine inherits unannotated: `## Hard Gate` (apply or skip rationale), `### 5. Transition` (the existing skip; tighten the language to also say "do NOT log phase_transition events from this section's JSON template" so the file's instruction can't accidentally fire), and `## Constraints` table at the bottom. Closes the F2 + F3 documentation gaps.

**(M3)** Tighten the smoke test in this ticket's verification to use a `tier: complex, criticality: medium` fixture that actually reaches orchestrator-review. Optionally augment with `grep -c orchestrator_review lifecycle/{slug}/events.log >= 1` to confirm the transitive hop fired.

**(M4)** Use `${CLAUDE_SKILL_DIR}` style for the cross-skill path: `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` matches lifecycle SKILL.md's existing path-style convention and resolves correctly under both repo-development CWD and plugin-cache install. (Verify with a sample read in a fresh session before adopting.)

**(M5)** Apply the SKILL.md edit by content-addressing the `Read \`references/specify.md\`` string, not by line number — defends against ticket 173 landing first and shifting line numbers.

**(M6)** Audit assertion: refine never reaches plan phase. Add a comment-line note to refine SKILL.md that explicitly states this invariant, so a future refactor sees the constraint when adding plan-phase logic.

## Open Questions

These require explicit user resolution before Spec phase.

- **OQ1 (transitive resolution mitigation choice)**: Adopt mitigation **(M1)** in this ticket — edit `skills/lifecycle/references/specify.md:145` to path-qualify the orchestrator-review pointer? **Recommendation: YES**, this is the cheapest defense (1-line edit in lifecycle's own file) and removes the entire transitive-resolution-ambiguity class of failures. Alternatives: (a) keep refine's orchestrator-review.md as a 1-line stub (Approach D applied selectively); (c) accept empirical risk + smoke-run-only — relies on halt-on-fail to surface regressions; cost: smallest, risk: production refine session hits the resolution failure first. *Defer to user.*

- **OQ2 (cross-skill path style)**: Use bare `skills/lifecycle/references/specify.md` (cortex-command-only, doesn't survive plugin cache install), or `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` (matches lifecycle SKILL.md style and resolves correctly under plugin install)? **Recommendation: `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md`** — the `${CLAUDE_SKILL_DIR}` style is already used in lifecycle SKILL.md; matching it preserves path-style consistency. *Defer to user; needs a sample-read verification.*

- **OQ3 (smoke test fixture)**: Run the smoke-test verification with a `tier: complex, criticality: medium` (or higher) fixture that actually exercises orchestrator-review, rather than the simple+low default? **Recommendation: YES** — without this, F1 is undetected. *Defer to user.*

- **OQ4 (Hard Gate / §5 acknowledgment in refine SKILL.md)**: Should refine SKILL.md Step 5 add an explicit `## Hard Gate` row to its adaptation list, and tighten the §5 row to forbid emitting the `phase_transition` JSON template? **Recommendation: YES** — closes documentation-correctness gaps F2 and F3 at near-zero cost. *Defer to user.*

- **OQ5 (ticket 181 ordering)**: Adversarial recommends blocking 174 on 181 (cross-skill handoff test lands first). 181 currently `blocked-by: [178]`, `status: backlog`. Reordering would delay 174 significantly. Trade-off: ship 174 now with M1+M3 mitigations and accept smoke-test-only verification, OR delay until 181 ships an automated test? **Recommendation: ship 174 now with mitigations (M1, M2, M3, M4) — the mitigations close the highest-impact failure modes; full automated test coverage from 181 follows when its blocker (178) clears.** *Defer to user.*

## Considerations Addressed

- **Path-resolution semantics for transitive `references/` paths**: Investigated (web research: no programmatic resolver; bare relative paths are a documented failure mode in claude-code issue #11011; `${CLAUDE_SKILL_DIR}` is invoking-skill-only). Adversarial F5 + recommended mitigations M1 and M4 in Open Questions OQ1 and OQ2.
- **Refine SKILL.md Step 5 adaptation coverage of `### 5. Transition` block, `## Hard Gate` table, and orchestrator-review.md's P8 plan-phase row**: Investigated. §5 Transition skip note exists but lives in refine SKILL.md (not in the file refine reads); F2 spurious-emission risk identified. Hard Gate not enumerated; F3 documentation gap. P8 row harmless (refine never reaches plan; F6 invariant unchecked but acceptable). Recommended mitigation M2 in OQ4.
- **Verification adequacy**: Investigated. Adversarial F1 demonstrates the proposed smoke test likely doesn't exercise the orchestrator-review path. Recommended mitigation M3 in OQ3.
- **Ordering dependency with ticket 173 (Z-stream copy-paste bug fix)**: Investigated. No line overlap; lines 117–157 + 231–232 (173) vs line 177 (174). However, 173 deletes ~40 lines so line 177 will shift if 173 lands first. Mitigation M5: content-address the SKILL.md edit, not position-address. Both tickets currently `status: backlog`; either ordering is mechanically safe.
- **Step 4 prescription correction**: Confirmed. Refine SKILL.md Step 4 is the Research phase; it does NOT contain an orchestrator-review invocation. The actual SKILL.md edit envelope is one line: line 177 (Step 5 specify.md reference). The ticket's "Step 4 (orchestrator-review invocation)" prescription is a labeling error to fix in Spec.
