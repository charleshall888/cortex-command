# Research: Reference-file hygiene (cross-skill + ceremonial + #179 extractions)

## Codebase Analysis

### orchestrator-review.md — cross-skill duplication

**Two files exist:**
- `skills/discovery/references/orchestrator-review.md` (133 lines) — single phase (`research`); applicability rule explicitly disabled (line 5: "Discovery has no applicability skip rule"); paths use `research/{topic}/...`; fix-prompt template uses `{topic}`; one Post-Research checklist (R1–R5).
- `skills/lifecycle/references/orchestrator-review.md` (172 lines) — three phases (`research|specify|plan`); criticality×tier skip-rule matrix at lines 13–18; paths use `lifecycle/{feature}/...`; fix-prompt template uses `{feature}`; checklists for Post-Specify (S1–S7) and Post-Plan (P1–P10); model-selection guidance.

**Divergence is structural, not cosmetic.** Three independent parameter axes differ (events.log path, artifact path, prompt-token name); phase enum differs; applicability policy differs (always-on vs conditional); checklist sets are mutually exclusive. Approximately ~94 lines of *protocol shape* (review → log → fix-or-escalate) is shared; the *concrete instantiation* differs everywhere.

**Callsites:**
- `skills/discovery/references/research.md:6a` — "Before committing, read and follow `references/orchestrator-review.md` for the `research` phase"
- `skills/lifecycle/references/specify.md` — "for the `specify` phase"
- `skills/lifecycle/references/plan.md` — "for the `plan` phase"
- `skills/discovery/references/decompose.md:46` — **cites `orchestrator-review.md:22-30` by line number** (silent break risk on restructure)

**#172/#174 precedent (verified in `backlog/174-*.md`):** the refine `references/` files were **byte-identical** to lifecycle copies (diff confirmed except for one P8 row refine never reaches and trailing 23 lines refine documents skipping). The collapse was safe because the content was already textually identical. The orchestrator-review.md pair is **not** byte-identical — Agent 1's diff shows real per-skill divergence. The #174 precedent does not directly apply.

**Constraints table:** the only byte-identical block across the two files is the 4-row `Constraints` table at the bottom.

### requirements-load.md — inline-vs-keep

**File:** `skills/lifecycle/references/requirements-load.md` (11 lines; ~5 lines of actual protocol).

**Verified callsites in canonical files:**
- `skills/lifecycle/references/clarify.md:33` — "Apply the protocol in `requirements-load.md`. If no requirements files exist, skip to §3."
- `skills/lifecycle/references/specify.md:9` — "Apply the protocol in `requirements-load.md` to load project requirements."

**Discrepancy:** the file's own preamble (line 3) names *three* callsites: `clarify.md §2`, `research.md §0b`, `specify.md §1`. Only two exist in canonical. Either the preamble lies or `research.md §0b` is a missed/stale callsite — must resolve before deletion (see Open Questions).

**Math:** 11 lines (file) vs ~10 lines if inlined at both sites (5-line protocol × 2). Net byte cost is roughly equivalent; the win is removing one indirection hop and one file.

### clarify-critic.md — 5-branch parent-epic table

**Location:** `skills/refine/references/clarify-critic.md` lines 18–24.

**Five branches**, mirroring the closed-set status enum returned by `bin/cortex-load-parent-epic`:
- `no_parent` → omit, no warning
- `missing` → omit, warn (allowlisted template)
- `non_epic` → omit, no warning
- `loaded` → splice section
- `unreadable` → omit, warn (allowlisted template)

**Helper-spec parity:** the 5 branches mirror the helper's status enum 1:1. The spec explicitly says "The allowlist is closed; new branches require a spec amendment" (clarify-critic.md line 26). The 1:1 mirror IS the contract.

**Collapse opportunity:** 4 of 5 branches set `parent_epic_loaded=false` and omit the section; only the warning-emission behavior differs. A preamble could factor the shared clause without dropping branches.

### #179 extractions — verified incomplete

**Spec targets (from `backlog/179-extract-conditional-content-blocks-to-references.md`):**
| Source | Lines | Target file | Target line count for parent |
|---|---|---|---|
| `lifecycle/references/implement.md §1a` (daytime dispatch) | ~70 | `lifecycle/references/implement-daytime.md` | ~210 |
| `critical-review/SKILL.md` lines 212–260 (8 worked examples) | ~49 | `critical-review/references/a-b-downgrade-rubric.md` | ~315 |

**Current state (verified):**
- `skills/critical-review/references/a-b-downgrade-rubric.md` — **does not exist**
- `skills/lifecycle/references/implement-daytime.md` — **does not exist**
- `skills/critical-review/SKILL.md` — **369 lines** (target ~315; ~54 lines over, matches the ~49-line extraction that never happened)
- `skills/lifecycle/references/implement.md` — **283 lines** (target ~210; ~73 lines over, matches the ~70-line extraction that never happened)

**Line-range drift:** Agent 1 confirms current line counts are within ~5% of what the original #179 spec assumed; the extraction targets are still valid. Re-validation found no significant content drift.

### Injection-resistance paragraph — `skills/research/SKILL.md`

**Actually 6 callsites, not 5** (Agent 1's count, verified): lines 63, 85, 109, 129, 151, 174. The paragraph is verbatim across all 6 — no parameter to substitute.

**Existing substitution mechanism:** the same SKILL.md already uses `{topic}`, `{research_considerations_bullets}`, `{summarized_findings_from_agents_1_through_4}` placeholders successfully in the same agent dispatch templates. Pattern is well-established.

**The paragraph is invariant.** There is no per-agent variation. "Parameter substitution" is a misnomer — what's needed is **prose factoring** (define-once + reference), not template substitution.

### Mirror sync & drift enforcement

- **Build:** `just build-plugin` uses `rsync -a --delete` to mirror `skills/` and `hooks/`. `--delete` prunes mirrors when canonical files are removed.
- **Drift test:** `tests/test_drift_enforcement.sh` (4-phase: identify staged → classify → conditional rebuild → drift loop). Catches edits to mirrors and uncommitted mirror updates.
- **Parity test:** `tests/test_dual_source_reference_parity.py` discovers canonical→mirror pairs via glob; new reference files are auto-discovered (no manual wiring).
- **Asymmetric-deletion case** (canonical removed from one skill but present in another): handled correctly by `--delete` flag, but no explicit test asserts orphan mirrors don't accumulate. Agent 5 flagged this as a small testing gap (out of scope for this ticket).

### Spot-check: ≤30-line reference files

Only `skills/lifecycle/references/requirements-load.md` (11 lines) qualifies. No other `skills/*/references/*.md` files fall under the 30-line threshold. Per user direction (Q1 answer): if additional ceremonial files are found later, they will be filed as separate backlog items — not bundled into this ticket. Current sweep yields nothing additional.

## Web Research

**Anthropic skill-authoring best practices** (canonical, [platform.claude.com docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)):
- 500-line cap is for **SKILL.md body specifically**; **no documented minimum** for reference files.
- **"Overreliance on certain sections" is a named anti-pattern**: *"If Claude repeatedly reads the same file, consider whether that content should be in the main SKILL.md instead."* This is a direct argument for inlining `requirements-load.md` (always-read at every clarify and specify entry).
- Keep references **one level deep** from SKILL.md; nested references trigger partial reads.
- References >100 lines need a TOC.
- **No first-party guidance on cross-skill shared files** — the official model treats each skill as self-contained.

**Cross-skill duplication patterns (third-party):**
- MindStudio recommends a project-level `/shared-reference/` directory for *stable* cross-skill content (style guides, format specs). Workflow-specific content is risky to share because changes ripple to every consumer.
- The orchestrator-review.md case is workflow-specific (each skill has its own checklist set, applicability policy, and event paths) — not the "stable shared content" archetype.

**Prompt template deduplication:**
- Standard pattern in Jinja-based frameworks (LangChain, Semantic Kernel, Haystack, Instructor) is `{% include %}` or macros for repeated fragments.
- In markdown-only skills with no template runtime, the equivalent is one reference file referenced by name from each substitution point — but for **invariant paragraphs that are part of an Agent dispatch prompt**, the safer pattern is prose factoring within the SKILL.md, not file extraction.

## Requirements & Constraints

**From `requirements/project.md`:**
- "Workflows that have not earned their place are removed wholesale" (line 23) — supports inlining `requirements-load.md` if it's pure ceremony.
- SKILL.md size cap = 500 lines; default remediation is extracting to `skills/<name>/references/` (line 30) — applies to oversized SKILL.md, not to small references.
- "Complexity must earn its place by solving a real problem that exists now" (philosophy section) — argues against keeping `requirements-load.md` for hypothetical future expansion.
- Mirror sync via `just build-plugin`; pre-commit drift hook enforces canonical-source-only edits (line 29).

**From `requirements/multi-agent.md`:**
- Dual-layer prompts use `{token}` (single-brace, runtime-substituted by `runner.sh`) and `{{feature_X}}` (double-brace, orchestrator-substituted at dispatch). This is the existing convention for the overnight orchestrator round prompt; SKILL.md prompt templates use single-brace `{name}` for orchestrator-substituted placeholders.

**From `CLAUDE.md`:**
- MUST-escalation policy: prefer soft positive-routing phrasing for new authoring; this affects how the 5-branch table's "warn vs. fail" tone is rewritten if collapsed.

**Backlog precedents:**
- **#172/#174** — collapsed *byte-identical* refine/lifecycle reference pairs. The orchestrator-review.md pair is not byte-identical, so the precedent does not directly apply.
- **#179** — original spec verified; targets still valid; closure-quality gap owned by **#194** (separate spike, status: complete; verdict: this ticket carries the narrow remediation).
- **#187 sequencing** — #192 should land before #193 (cross-skill collapse settles canonical files before in-place hygiene edits).

## Tradeoffs & Alternatives

### Sub-task A: orchestrator-review.md collapse

| Approach | Pros | Cons |
|---|---|---|
| **A1** — Collapse to lifecycle canonical, discovery references it | Single source for protocol shape; mirrors #174 pattern. | Lifecycle file uses `{feature}` and `lifecycle/{feature}/...` paths, discovery uses `{topic}` and `research/{topic}/...` — collapse requires per-skill rewriting at callsites or parameterizing the canonical. Discovery's "no skip rule" semantics get lost (lifecycle has the matrix). Breaks `decompose.md:46` line citation silently. |
| **A2** — `_shared/references/orchestrator-review.md` | Symmetric; no skill owns a peer's reference. | Introduces a new top-level convention not used anywhere else; one-off pattern is itself debt. |
| **A3** — Inline into both SKILL.md files | Zero indirection. | Locks in 305 lines of dup; defeats the ticket's intent. |
| **A4** — Extract shared `_common.md`, keep skill-specific files | Preserves divergence (paths, phase enum, applicability policy); thin per-skill files retain checklist-set differences. | Three files to maintain; readers chase two hops; after factoring 3 parameter axes + phase enum + skip-rule + checklist sets, the "common" core is small and the per-skill thin files still carry most of the divergence. |
| **A5** — Keep both files; extract only the byte-identical `Constraints` table | Honest about real divergence; minimal change with minimal risk; no callsite rewrites; line-citation in `decompose.md` survives. | Smallest token-savings of the alternatives (~4 rows of table extracted, ~5 lines per file × 2 = ~10 lines saved). |

**Recommended: A5.** The protocol *shape* is shared; the *concrete instantiation* is workflow-specific (per Anthropic's "shared content should be stable" guidance and MindStudio's pattern). The ~94 lines of "shared shape" Agent 1 cited is mostly *structurally* similar text, not *literally* shared text — extracting it forces parameterization that adds complexity beyond what duplication costs. The token win for A1/A4 is overstated when you account for the parameterization scaffolding required. **Open Question O1 below** asks the user to confirm vs. fall back to A1.

### Sub-task B: requirements-load.md inline-vs-keep

| Approach | Pros | Cons |
|---|---|---|
| **B1** — Inline + delete | Removes always-read indirection (Anthropic anti-pattern); ~zero net byte cost; one fewer file. | Loses single-source-of-truth if a third callsite ever appears (low likelihood — protocol is 4 bullets). |
| **B2** — Keep | Preserves single source for hypothetical future. | Violates "complexity must earn its place by solving a real problem that exists now"; perpetuates the always-read-thin-file anti-pattern. |

**Recommended: B1.** Three of four agents (2, 4, 5) plus Anthropic's official "overreliance" guidance converge on inline. The "future expansion" argument is hypothetical-future-requirement reasoning the project explicitly rejects. **Caveat:** verify the file's preamble claim that `research.md §0b` is a callsite — see Open Question O2.

### Sub-task C: clarify-critic 5-branch table

| Approach | Pros | Cons |
|---|---|---|
| **C1** — Collapse to "loaded vs all-others" | Saves ~7 lines; cleaner default-omit semantic. | **Severs 1:1 mirror with the helper's closed-set status enum** — the spec explicitly names this contract. Future helper status additions require re-expanding the table with no mechanical reminder. |
| **C2** — Status quo with preamble tweak ("All branches except `loaded` set `parent_epic_loaded=false` and omit the section; differences below are warning behavior only") | Preserves helper-parity contract; trims the visual repetition of "Set `parent_epic_loaded = false`. Omit the section." across 4 branches; saves ~3 lines. | Less aggressive collapse than the ticket envisioned. |

**Recommended: C2.** The 5-branch table's value is the 1:1 mirror with the helper's closed-set status enum — that *is* the contract per the spec's own wording. Preamble factoring trims the visible repetition without breaking the contract. **Open Question O3** asks the user to confirm vs. ticket-default C1.

### Sub-task D: #179 extractions

| Approach | Pros | Cons |
|---|---|---|
| **D1** — Land what #179 specified, with line-range re-validation gate | Faithful to pressure-tested spec; line counts confirmed within ~5% of original assumptions. | None significant. |

**Recommended: D1.** Re-validation already done (Agent 1 confirms targets still valid). Acceptance criterion must be **file-existence-gated** (`test -f` style) to prevent the same closure-quality gap that produced the #194 spike — see Open Question O4 for the strengthened acceptance language.

### Sub-task E: injection-resistance paragraph hoist

| Approach | Pros | Cons |
|---|---|---|
| **E1** — Define once at top of Step 3, reference by `{INJECTION_RESISTANCE_PARAGRAPH}` placeholder | Mirrors existing `{topic}`/`{research_considerations_bullets}` pattern. | The paragraph is **invariant** — there is no parameter to substitute. The placeholder is decorative, not parameterizing. |
| **E2** — Move to `references/injection-resistance.md` | Single file; cross-skill reusable. | Adds an I/O step per dispatch; the paragraph is small enough that file-extraction overhead exceeds savings. |
| **E3** — Prose factoring: define once at top of Step 3 as a named block, instruct each agent prompt section to "include the injection-resistance instruction defined above (verbatim)" | Single source; no placeholder mechanics; explicit instruction to dispatcher. | Requires authoring discipline at dispatch time (the orchestrator must *actually* paste the paragraph into the Agent prompt, not just write the reference comment). |
| **E4** — Accept duplication | Mechanically guaranteed correct (verbatim text in each callsite is what gets dispatched). | ~125 words / ~300 tokens of dup per `/cortex-core:research` invocation across 6 sites. |

**Recommended: E1 with one adaptation** — use `{shared:injection_resistance}` placeholder convention (or `{INJECTION_RESISTANCE_INSTRUCTION}`) and define the canonical paragraph in a new `### Shared agent-prompt fragments` subsection at the top of Step 3. Agent 4's E4 (do nothing) is overcautious — the existing 3 placeholder mechanisms in the same file are already proven to work; there's no observed evidence of Opus 4.7 literalism breaking them. Agent 5's E3 (prose-factoring without placeholder) is the safer second-best. **Open Question O5** lets the user pick among E1/E3/E4.

## Adversarial Review

**Disagreements between agents (surfaced for spec resolution):**

1. **orchestrator-review.md** — Agent 1: collapse-to-lifecycle. Agent 4: `_common.md` factor. Agent 5 (adversarial): keep both, extract only Constraints table. The disagreement is real because the divergence is structural, not cosmetic.

2. **requirements-load.md** — Agent 1: keep. Agents 2, 4, 5: inline + delete. Anthropic's anti-pattern guidance favors inline. Agent 1's "future-expansion" rationale conflicts with project philosophy.

3. **5-branch table** — Agent 1: collapse. Agents 4, 5: preserve with preamble tweak. The table mirrors a closed-set helper enum that's explicitly named as the contract.

4. **Injection-resistance hoist** — Agent 4: do nothing (literalism risk). Agent 5: prose-factor without placeholder. Agent 4's literalism risk is unsupported by observation — existing placeholders in the same file work fine.

**Failure modes flagged:**

- **Line-citation in `decompose.md:46`** cites `orchestrator-review.md:22-30` by line number. If sub-task A is anything other than A5 (or A1 with a careful update to that citation), the citation silently breaks. Mirror-sync won't catch this.

- **`research.md §0b` ghost callsite** — `requirements-load.md` preamble names a callsite that doesn't appear in canonical. Either the preamble is wrong or there's a missed callsite. Resolve before deletion.

- **#179 closure-pattern recurrence** — #179 was marked complete with deliverables that don't exist. If #192's acceptance criteria are not bound to **file-existence checks** (not just spec text), the same gap can recur. The acceptance signals must include `test -f` style gates and the PR description must include a fresh-run transcript or `ls` output evidence.

- **Asymmetric mirror deletion** — when canonical is deleted from one skill but present in another, `rsync -a --delete` handles it correctly but no test asserts orphan mirrors are absent. Out of scope for this ticket; flag for a separate follow-up.

## Open Questions (resolved during research phase — see Decisions Resolved below)

These were the spec-level decisions arising from agent disagreement. All have been resolved during the research phase via user input + targeted investigation.

**O1 — orchestrator-review.md approach**: Three viable alternatives surfaced (A1 collapse-to-lifecycle, A4 `_common.md` factor, A5 keep-both + extract Constraints table only). Research recommended A5; user pushed back asking for the long-term-best refactor. **Resolved: A6 — do nothing; reframe parent epic's "duplication" finding as misleading.** See Decisions Resolved.

**O2 — `requirements-load.md` ghost callsite**: The file's preamble claims `research.md §0b` is a callsite, but only `clarify.md` and `specify.md` actually reference it. **Resolved: investigate during spec phase before deletion.** If `research.md §0b` is a real missed callsite, inline the protocol there too; if preamble is stale, delete cleanly.

**O3 — clarify-critic 5-branch table**: **Resolved: C2** (preamble tweak, preserve 1:1 helper-enum mirror).

**O4 — #179 acceptance language strengthening**: Premise was wrong. **Resolved: moot.** See Decisions Resolved — investigation shows #179 was correctly closed; no closure-quality gap exists for that ticket. The general spec-evolution-gap pattern #194 identified is not in this ticket's scope.

**O5 — Injection-resistance hoist mechanism**: **Resolved: E1** (placeholder substitution `{INJECTION_RESISTANCE_INSTRUCTION}` with canonical paragraph defined in a new `### Shared agent-prompt fragments` subsection at the top of Step 3).

**O6 — Sub-task ordering and atomicity**: **Resolved: one PR with separate commits per sub-task** (default; user did not override). Any individual sub-task can be reverted without unwinding the others.

## Decisions Resolved

### #179 investigation (resolves O4 + reshapes Sub-task D)

Read `lifecycle/extract-conditional-content-blocks-to-references-a-b-downgrade-rubric-implement-daytime-trimmed-scope/spec.md` (the actual #179 spec). Verbatim from line 3:

> *"Scope revision from the backlog item body. The original backlog item (#179) scoped two wholesale `references/*.md` extractions. Research and the adversarial review found that (a) Extract B's existing deterministic test gives false confidence, (b) the worked-examples extraction would establish a first-of-its-kind sub-agent-prompt-template anti-pattern in the codebase, (c) the §1a wholesale relocation breaks `test_skill_contracts`'s regex anchor, and (d) ~50–75% of §1a is unique main-session orchestration that #177 explicitly preserved. The user confirmed Path 1: in-place trim of §1a only, with Extract B replaced by an expansion of the synthesizer test suite to cover Triggers 2/3/4. **This spec replaces the backlog item's original 'wholesale relocation, both extractions' remedy.**"*

And Non-Requirements §58–60 explicitly say the ticket does NOT extract `implement-daytime.md` or `a-b-downgrade-rubric.md`. The implementation correctly delivered Path 1 (`review.md`: APPROVED, all 7 requirements PASS). The deferral reasons (a–d) all still hold.

**The #194 spike misclassified #179.** #194's findings.md says: *"Spec called for extracting [...]. Files do not exist. [...] the trimmed scope itself was specified, but the trimmed deliverables never landed."* This is wrong — #194 read the backlog body's stale "2 extractions" framing rather than spec.md. The real spec.md (Path 1) does not call for those extractions. Same methodology error likely affects #194's #178 and #181 verdicts.

**Resolution for #192:**
- **Sub-task D dropped entirely.** The "process gap from ticket #179" framing in #192's ticket body is factually correct (deliverables don't exist) but interpretively wrong (deliverables were deliberately not created per a documented spec revision).
- **New sub-task F added (bundled into this ticket):** Update #179's backlog body with a "Scope revision" note pointing to spec.md. This prevents the same misread from happening again. Trivial (~5-line edit) and directly related to the hygiene work in #192. Cheaper bundled than as a separate ticket.

### Sub-task A — orchestrator-review.md (resolves O1)

**Resolved: A6 — do nothing.** The two files share a protocol *shape* but diverge on every concrete instantiation: events.log paths (`research/{topic}` vs `lifecycle/{feature}`), prompt tokens (`{topic}` vs `{feature}`), applicability policy (always-on vs criticality×tier matrix), checklist sets (R1–R5 vs S1–S7+P1–P10), phase enum (single vs three). The #174 byte-identical-collapse precedent does not apply.

Anthropic's official guidance treats each skill as self-contained. MindStudio's "share only stable content" guidance flags workflow-specific protocol content as risky to share. The "duplication" the parent epic flagged is *appearance* (similar protocol shape) not *substance* (literal text). Forced convergence — even via `_common.md` — creates parameterization scaffolding that exceeds the savings.

**Reframing for the parent epic:** the "Reference-file duplication: discovery/lifecycle `orchestrator-review.md` duplicates ~130 lines cross-skill" finding in epic #187 is misleading. The shared lines are protocol-shape mirrors, not literal duplication. This finding does not justify a remediation ticket on its own. (Documented here for future audits.)

### Sub-task B — requirements-load.md (resolves O2)

**Resolved: B1 (inline + delete) with §0b investigation gate.** Anthropic's "overreliance on certain sections" anti-pattern explicitly recommends inlining always-read references. requirements-load.md is always-read (loaded at the start of every clarify and specify). The "future expansion" rationale violates the project's "complexity must earn its place" philosophy.

**Spec-phase investigation gate:** Before deletion, verify whether `research.md §0b` should be a callsite. Two possible outcomes:
- (a) Preamble is stale → delete file + inline at clarify.md and specify.md.
- (b) `research.md §0b` is a real missed callsite (latent bug) → inline at all three sites.

### Sub-task C — clarify-critic 5-branch table (resolves O3)

**Resolved: C2 (preamble tweak, preserve 5 branches).** The 5-branch table mirrors the closed-set status enum returned by `bin/cortex-load-parent-epic` 1:1. The spec explicitly names this as the contract ("The allowlist is closed; new branches require a spec amendment"). Collapsing to "loaded vs all-others" severs the helper-spec parity contract for marginal token savings.

Add a one-line preamble: *"All branches except `loaded` set `parent_epic_loaded=false` and omit the section; the differences below are warning-emission behavior only."* Trims visual repetition without breaking the contract. Saves ~3 lines.

### Sub-task D — #179 extractions (DROPPED — see #179 investigation above)

### Sub-task E — Injection-resistance paragraph hoist (resolves O5)

**Resolved: E1 (placeholder substitution).** Mirrors the existing `{topic}` / `{research_considerations_bullets}` / `{summarized_findings_from_agents_1_through_4}` substitution pattern already proven to work in the same SKILL.md. Agent 4's Opus 4.7 literalism concern is theoretical and contradicted by the existing pattern's success.

**Mechanism:**
- Add a new `### Shared agent-prompt fragments` subsection at the top of Step 3 in `skills/research/SKILL.md` defining the canonical paragraph.
- Replace each of the 6 verbatim copies (lines 63, 85, 109, 129, 151, 174) with `{INJECTION_RESISTANCE_INSTRUCTION}`.
- The orchestrator (Claude executing the skill) substitutes the canonical paragraph at dispatch time, just as it currently substitutes `{topic}` etc.

### Sub-task F — Update #179 backlog body (NEW; bundled per investigation)

**Resolved: bundled into this ticket.** Add a "Scope revision" note to `backlog/179-*.md` body pointing to `lifecycle/extract-conditional-content-blocks-to-references-a-b-downgrade-rubric-implement-daytime-trimmed-scope/spec.md` line 3 as the authoritative source for what was actually delivered. Prevents future audits from making the same misread.

### Out-of-scope follow-on tickets (recommended, NOT bundled)

The investigation surfaced two larger issues that deserve separate tickets — bundling them into #192 would expand scope inappropriately:

1. **Re-audit #194's #178 and #181 findings using spec.md as source-of-truth.** #194's methodology (backlog-body-as-source-of-truth) likely produced false-positives. Medium investigative task. File as a backlog item under epic #187 (closure-quality cluster).
2. **Spec-evolution gap remediation (#194's actual recommendation).** #194 recommended *"spec re-acceptance at the moment of mid-flight change"* but the recommendation was never ticketed. Substantial feature work in `/cortex-core:lifecycle`. File as a separate backlog item under epic #187.

### Sub-task ordering (resolves O6)

**Resolved: one PR, separate commits per sub-task** (A excluded since it's now A6/no-op). Each sub-task is independently revertable. Recommended commit order:
1. Sub-task F (update #179 body) — smallest, sets the record straight.
2. Sub-task B (inline requirements-load.md) — after §0b investigation.
3. Sub-task C (5-branch table preamble tweak).
4. Sub-task E (injection-resistance hoist) — riskiest per Agent 4; isolating in its own commit makes rollback clean.

Sub-task A becomes documentation-only: a brief note (in a follow-up ticket or PR description) reframing the parent epic's misleading "duplication" finding.

## Considerations Addressed

(No `research-considerations` were passed to this research dispatch — the section is omitted per Step 4 of `/cortex-core:research`.)

