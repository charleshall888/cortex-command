# Research: Classify /critical-review findings by class and add B-class action surface

## Epic Reference

This ticket is scoped to FP1 (reviewer classification) + FP2 (synthesizer restructure) + the B-class action surface from the parent epic [`research/critical-review-scope-expansion-bias/research.md`](../../research/critical-review-scope-expansion-bias/research.md). The epic decomposed into three tickets; FP5 (pattern anchor) is deferred per epic DR-6, FP6 (input-side framing) is a separate epic, and FP3/FP4 (operator-interface guardrails) form a third epic. This research does not reproduce epic-level material; it addresses ticket-132-specific open questions left for planning.

## Codebase Analysis

### Files that will change (with paths)

**Primary target — `skills/critical-review/SKILL.md`** (the entire skill is one file; all three AC axes land here):

- **Step 2c reviewer prompt template** (lines 74–105, specifically the format block at 92–103): add per-finding class tagging + taxonomy worked examples + straddle-case protocol. Current format is `### What's wrong` / `### Assumptions at risk` / `### Convergence signal`. Line 103's `Do not cover other angles. Do not be balanced.` needs re-evaluation — the "Do not be balanced" pairing with the verdict-framing H3 defect should be checked against the new taxonomy's framing.
- **Step 2c fallback prompt** (lines 113–142): the total-failure fallback single-agent prompt also produces the Objections/Through-lines/Tensions/Concerns shape. Spec must decide whether the fallback output shape follows the same class tagging or is explicitly out of scope. The ticket AC section is silent on the fallback.
- **Step 2d synthesis prompt template** (lines 148–181): rewrite instruction #2 (line 162 — "Find the through-lines — claims or concerns that appear across multiple angles") to scope through-line aggregation to same-class findings, and add the B→A non-promotion rule. Line 166's closing (`"These are the strongest objections. Proceed as you see fit."`) is part of the verdict-framing tone per epic DR-2 H3. Line 179 (`"Do not be balanced. Do not reassure. Find the through-lines and make the strongest case."`) is the H3 anchor.
- **Step 4 classification / Apply bar** (lines 201–226): AC6 permits "C-class → Ask routing tightening." That affects line 207 (Ask definition), line 226 (Apply bar), and lines 205/209 (anchor checks). The B-class action-surface mechanism may also require a new Step 5 or an appendix to Step 4 if it's a file-emission step rather than an Ask-surface extension.

**Conditional targets (depend on action-surface mechanism choice):**

- (a) Auto-ticket: no new code files required — `backlog/create_item.py` via `~/.local/bin/create-backlog-item` is the API. SKILL.md gets invocation instructions.
- (b) Residue file: SKILL.md adds a write-file step. No events.log schema is registered for /critical-review today. A sidecar file adjacent to the lifecycle feature directory (e.g., `lifecycle/{feature}/critical-review-residue.{json,md}`) would be a new pattern.
- (c) Ask appendix: SKILL.md Step 4 consolidation clause (lines 215–225) extends to include a "B-class residue" section in the user-facing Ask surface.

**Definitely not touched**: `skills/lifecycle/references/specify.md:151`, `skills/lifecycle/references/plan.md:243`, `skills/discovery/references/research.md:128`, `skills/refine/SKILL.md:131` — all four invoke /critical-review and "present synthesis to the user before approval," none parse the output shape.

### Relevant existing patterns

**Structured output contract precedent** — `skills/lifecycle/references/clarify-critic.md` (only skill in repo adopting a structured output contract for reviewer-style work):

- Lines 52–58: reviewer agent emits labeled `Finding:` / `Concern:` prose — no classification by the agent; orchestrator classifies.
- Lines 81–88 (`### Dispositioning Output Contract`): "The sole output of the dispositioning step is the structured YAML artifact."
- Lines 96–147 (`## Event Logging`): schema `ts`, `event: clarify_critic`, `feature`, `findings[]`, `dispositions{apply, dismiss, ask}`, `applied_fixes[]`, `dismissals[{finding_index, rationale}]`, `status`. Invariant: `len(dismissals) == dispositions.dismiss`. Counts are post-self-resolution.
- **Wire-format nuance**: clarify-critic.md's example shows YAML block format (lines 126–146), but live `events.log` entries are JSONL (single-line JSON per entry). See this lifecycle's own `events.log` for the precedent — documentation shows YAML for readability; the enforced wire format is JSONL.

**Backlog creation API** — `backlog/create_item.py`:

- CLI: `create-backlog-item --title T --status S --type T [--priority P] [--parent NNN] [--rework-of N]`.
- Required YAML frontmatter fields: `schema_version`, `uuid`, `title`, `status`, `priority`, `type`, `created`, `updated`. Optional: `rework_of`, `parent`.
- **Known wrinkle**: requires `PYTHONPATH=/Users/charlie.hall/Workspaces/cortex-command` on invocation. CLI does not accept `--tags`, `--areas`, `--body`, or `--discovery_source` — body/tags must be written separately via Write/Edit after creation.
- Emits a `status_changed` event to a sidecar `{nnn-slug}.events.jsonl` adjacent to each backlog item (create_item.py:67–89). This is the closest precedent to "residue file adjacent to artifact."
- Envvar: reads `LIFECYCLE_SESSION_ID` for event metadata.

**Events.log JSONL append pattern** — `claude/common.py:113`, `:182`, `:223`. Reading is line-by-line `json.loads`; writing is append-only.

**Pipeline deferral system** (pipeline.md:83–91) as residue-artifact precedent: the pipeline writes structured deferral questions to `lifecycle/deferred/{feature}-q{NNN}.md` with fields `severity` (blocking/non-blocking/informational), `context`, `question`, `options_considered`, `pipeline_action_attempted`, `default_choice`. Atomic writes via tempfile + `os.replace()` (pipeline.md:121). This is a strong in-repo precedent for "structured residue artifact for findings that can't be resolved autonomously" — scoped to the overnight pipeline, but the pattern is portable.

**Step 4 Apply/Dismiss/Ask framework** (SKILL.md:201–226): ticket 067 (complete) restructured the Step 4 compact summary to suppress Dismiss narration; current behavior is `Dismiss: N objections` count line with N=0 omission. Ticket 132's AC6 explicitly must not regress this.

### Downstream consumer audit

**Verdict: ZERO programmatic consumers of /critical-review's output section headers (`## Objections`, `## Through-lines`, `## Tensions`, `## Concerns`).**

Greps run across: repo root, `claude/`, `hooks/`, `bin/`, `tests/`, `claude/pipeline/`, `claude/overnight/`, `claude/dashboard/`, `claude/hooks/`. Only hits:

- Three documentation files (SKILL.md itself, two historical lifecycle notes) — narrative, no parsing.
- `tests/test_skill_callgraph.py` — callee-existence fixture, does not test output format.

**Output-shape changes in Step 2c/2d are safe from programmatic-consumer breakage.** The only constraint is human-reading callsites (specify.md, plan.md, research.md, refine.md), all of which pass the synthesis through to user presentation unaltered.

### Action-surface mechanism code surfaces

**(a) Auto-emit follow-up backlog ticket** — via `create-backlog-item` CLI. Per-finding cost: 1 subprocess + 1 body write + possible `update-item` call. Regenerates `backlog/index.md` + `backlog/index.json` as a side effect per creation. Linkage via `parent` field (no `discovery_source` CLI flag — written manually if needed). Two-step choreography required: CLI creates shell → skill writes body.

**(b) Structured residue file / events.log entries** — no existing precedent for /critical-review specifically. Critical path issues:

- Critical-review runs **outside a lifecycle** too (ad-hoc invocation); no guaranteed `lifecycle/{feature}/events.log` path. Mechanism must gate on caller being inside a lifecycle, or use a different location (e.g., sidecar next to artifact), or fail gracefully.
- Spec 067 R8 explicitly required that `SKILL.md` contain zero `events.log` references as an acceptance criterion. A residue-via-events-log mechanism rewrites that constraint and must be flagged.

**(c) Synthesis appendix / Ask-channel escalation** — extends the Step 4 compact-summary consolidation clause (SKILL.md:215–225). Precedent shape: the existing "Ask items consolidate into a single message when any remain" clause. No other Ask surface exists — /critical-review has no events-log writes, no dashboard surface, no notification hook.

### Conventions to follow

- Edit `skills/critical-review/SKILL.md` as the primary locus; allow cross-file edits if action-surface mechanism demands them (AC6 does not scope-cap the ticket).
- Preserve Steps 1, 2a, 2b intact unless tagging changes demand Step 2a tweaks. Epic DR-3 defers H2 and H6.
- Maintain JSONL format for any events.log emission (not the YAML block form shown in clarify-critic.md).
- Follow clarify-critic.md's structured-output-contract pattern verbatim: orchestrator classifies, fresh agent returns prose, count-array invariants enforced, `status: ok|failed` mandatory.
- Don't introduce a hard dependency on lifecycle context — /critical-review runs standalone too.
- Backlog creation with body content is a two-step choreography (CLI + body Write), not a single-shot API.
- No existing transcript archive of historical /critical-review outputs exists (checked `retros/`, `lifecycle/*/events.log`, everywhere). AC4 Kotlin recovery path is unavailable in-repo; synthetic analog is the realistic path.
- Preserve "Do not soften or editorialize" and the distinct-angle rule (flagged by backlog items 082 and 085 as load-bearing against Opus warmth training).

## Web Research

### Taxonomy shape — ternary vs. binary + axis

Prior-art evidence is **strongly consistent with binary blocking + metadata/axis encoding**, not a native ternary:

- **Conventional Comments**: two-layer grammar — `<label> [decorations]: <subject>`. Label enumerates intent (9 labels); blocking axis is expressed via decorations — `(blocking)`, `(non-blocking)`, `(if-minor)`. Decorations multi-apply (`(blocking, security)`). Labels and decorations are orthogonal. Blocking is binary, with `if-minor` as conditional. Source: https://conventionalcomments.org/
- **Google eng-practices**: three severity prefixes (`Nit:`, `Optional:`/`Consider:`, `FYI:`) but all are flavors of *non-blocking* below an unlabeled blocking default — closer to ternary but semantically still binary + sub-grades. Source: https://google.github.io/eng-practices/review/reviewer/comments.html
- **Netlify Feedback Ladders**: 5-tier single-axis severity (Mountain/Boulder/Pebble/Sand/Dust), explicitly motivated against 2-tier nit/blocking dilution. Source: https://www.netlify.com/blog/2020/03/05/feedback-ladders-how-we-encode-code-reviews-at-netlify/
- **Cloudflare production LLM reviewer**: ternary severity (`critical` / `warning` / `suggestion`) with dispatch rules. Closest to proposed A/B/C shape, but semantics differ — Cloudflare's classes are severity-of-harm, not fix-invalidating/adjacent/framing. The ternary shape matches; the semantics do not transfer. Source: https://blog.cloudflare.com/ai-code-review/
- **CVSS v4.0**: **not orthogonal severity × scope as previously asserted** — produces a single composed scalar from eight base metrics; scope is handled via *Vulnerable* vs *Subsequent System Impact* (impact separation, not a scope axis). Does not support A/B/C (fix-invalidating vs adjacent vs framing). **This directly contradicts the epic research's citation of CVSS as prior art for "orthogonal severity × scope axes" — see `## Open Questions` below.** Source: https://www.first.org/cvss/v4-0/specification-document
- **Academic peer review**: dominant rubric is binary Major/Minor. Cochrane's guidance makes Major escalation path explicit. No widely-adopted academic ternary rubric surfaced. Source: https://documentation.cochrane.org/egr/peer-review-318472358.html
- **Reviewable**: rejected multi-class tagging — single-disposition-per-participant with prefix routing. Source: https://github.com/Reviewable/Reviewable/issues/510

**Shape conclusion**: The A/B/C ternary is defensible (Cloudflare validates ternary severity works) but sits at the outer edge of prior art. The more heavily-evidenced shape is **binary blocking-decoration + an orthogonal kind axis** (fix-invalidating vs adjacent vs framing *as a kind*, independent of whether it blocks).

### LLM classifier accuracy on severity tagging

Empirical numbers from *Benchmarking LLM Code Review* (arXiv 2509.01494):

- Human-LLM **type**-agreement: 69.4%–94.8%; human-human type-agreement: 67.4%–83.6%. **Severity**-agreement is "notably lower" than type-agreement and explicitly flagged as having inherent subjectivity.
- Top LLM reviewer overall precision: **15.39%**; four others <10%.
- Stochastic inconsistency: 5 runs on the same codebase produced only 27 overlapping change-points; cross-model overlap was 36.
- Class imbalance: functional/logic findings F1 ~26%; evolutionary/organizational findings F1 ~16%. Straddle cases systematically migrate toward the more-concrete class.
- Proposed mitigation: Multi-Review — run N times, take high-confidence intersection for precision, union-with-gating for recall.

**Implication**: Single-pass LLM class tagging will have low single-run reliability, especially on the B–C boundary. The synthesizer's refusal to promote B-only → A is defensible *only if* the synthesizer actually re-examines evidence rather than trusting the upstream tag.

### Structured output contracts for reviewers

Production consensus:

- **OpenAI Structured Outputs** (`response_format: {json_schema: ...}` or `strict: true`) — class tag as **enum field** at top level of each finding object, not embedded in prefix or body. https://openai.com/index/introducing-structured-outputs-in-the-api/
- **Anthropic Claude tool use** — same pattern; classification lives in enum-constrained field. https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- **Cloudflare** uses structured XML with severity embedded in tag — LLM reliability trade.
- **LangChain Pydantic**: documented bug (#8156) on array-of-enum patterns. Avoid by using per-finding objects with enum field rather than array of enum values.

**Implication**: Put class tag as separate enum field on each finding object (`{"class": "A|B|C", "finding": "..."}`), not as a `A: ...` prefix. Schema-validatable.

### B-class action-surface mechanisms in practice

- **Auto-ticket-from-comment**: GitHub has manual-only "convert to issue" (community #4330 unresolved). **GitLab's follow-up generation from non-blocking suggestions is the only native B-class auto-surface found**. https://docs.gitlab.com/development/code_review/
- **Disposition tracking** (Reviewable): Working/Informing/Discussing/Blocking creates audit trail, but issue #677 documents difficulty surfacing "discussions requiring attention." https://docs.reviewable.io/discussions.html
- **Gerrit**: +1/-1 opinion vs +2/-2 blocking; no native non-blocking-comment audit trail.
- **Aggregate cap/summary**: "report at most 5 nits, mention rest as count" — dilution-prevention UX, not residue.

**Finding**: No standard B-class action surface exists in mainstream code-review tooling. GitLab's follow-up generation is the only native example. Most production LLM systems (Cloudflare) accept that suggestions get overlooked.

### Straddle-case protocols

- **Conventional Comments**: exactly one label + multiple decorations. Reviewer picks dominant label.
- **Netlify**: reviewer picks one tier.
- **Academic**: picks dominant severity; Cochrane biases upward toward Major.
- **LLM-specific**: straddle cases drive down F1 (2509.01494); AgentAuditor (2602.09341) resolves via evidence-comparison rather than majority vote; Anti-Consensus Preference Optimization trains adjudicators to reward minority selections on majority-failure cases.

**Implication**: Prior art supports single class tag per finding with documented precedence rule, *not* multi-class tagging. The question is which direction straddle cases default — upward (Cochrane, safest for review quality) or downward (Cloudflare, safest for merge velocity).

### Dismissal-dilution empirical evidence

- "Excessive nitpicking causes 20–40% velocity losses" (augmentcode.com — practitioner, not peer-reviewed).
- "Nit fatigue" documented widely in practitioner writing; Netlify's 5-tier exists because 2-tier (blocking/nit) collapsed into dismissal.
- **No rigorous empirical study of labeled-severity dilution** found in academic venues.
- Indirect LLM evidence (2509.01494): evolutionary/stylistic F1 is ~10pp lower than functional F1 because optional/stylistic criteria are inconsistent across reviewers — proxy for the B-class dismissal pressure.

**Implication**: The "strong dismissal pattern" claim is plausible and widely believed in practitioner writing but not rigorously measured. Netlify's 5-tier is the best quasi-evidence that B-class *without* an action surface gets dismissed in practice. Frame ticket 132's premise as a design precaution motivated by practitioner consensus + Netlify case study, not as a "proven" effect.

## Requirements & Constraints

### From requirements/project.md

- **Complexity: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct.** (line 19)
- **Quality bar: Tests pass and the feature works as specced. ROI matters — the system exists to make shipping faster, not to be a project in itself.** (line 21)
- **Graceful partial failure** (line 29): tasks may fail; handoff to fresh agent allowed; fail gracefully if unresolvable.
- **File-based state** (line 25): plain markdown/JSON/YAML; no DB/server.
- **Defense-in-depth for permissions** (line 32): global allows minimal/read-only; overnight bypasses permissions (`--dangerously-skip-permissions`).
- **Context efficiency** (line 33): substring-grep filtering, no model-judgment cost. Class-tagging adds reviewer token count.
- **Conditional loading**: "agent spawning, parallel dispatch, worktrees, or model selection → requirements/multi-agent.md" — /critical-review dispatches parallel reviewer agents, so multi-agent.md applies.

### From requirements/multi-agent.md

- **Agent Spawning** (lines 13–23): scoped to overnight-runner agents; interactive skill-dispatched reviewer agents are not subject to `ConcurrencyManager`.
- **Model selection matrix** (lines 51–62): governs overnight pipeline dispatch, not interactive /critical-review. Ticket 132 is `complex+medium` — not explicitly named in the matrix's `complex+high/critical → opus` rule. Interactive reviewer-agent default is `sonnet` per backlog ticket 046.
- **Parallelism is orchestrator-driven** (line 72): for overnight pipeline agents. /critical-review's reviewer dispatch is an interactive skill exception (same as `/research`, `/pr-review`).

### From requirements/observability.md

- **Read-only subsystems** (line 85): statusline, dashboard, notifications. Any new residue file is read-only to observability; it's created by /critical-review.
- **Statusline latency** (line 22): <500ms per invocation.
- **Graceful degradation** (line 37): missing/malformed files silently ignored.
- **Notifications are stateless** (line 93): no retention/inbox.
- No schema defined for reviewer-findings artifacts — if ticket 132 introduces one, it's new.

### From requirements/pipeline.md

- **Deferral system** (lines 83–91): structured deferral questions written atomically to `lifecycle/deferred/{feature}-q{NNN}.md` with severity (blocking/non-blocking/informational), context, question, options, attempted action, default. **Strongest in-repo precedent for "structured residue artifact for findings the system cannot resolve autonomously."**
- **Atomic writes** (line 121): tempfile + `os.replace()`.
- **Orchestrator rationale convention** (line 127): non-routine events include a `rationale` field.

### From requirements/remote-access.md

Confirmed irrelevant.

### Architectural constraints that apply

1. Complexity must earn its place — ternary taxonomy + new action-surface artifact must be justified against the n=1 Kotlin failure.
2. File-based state only — backlog stub, residue file, and Ask extension all qualify; no DB-backed stores.
3. Read-only observability with <500ms statusline budget and graceful degradation.
4. Defense-in-depth — new CLI tooling stays read-only in global allows; overnight is unsandboxed.
5. Atomic writes for sidecars (tempfile + `os.replace()`).
6. Interactive-dispatch context — reviewer model is `sonnet` per 046, not governed by overnight matrix.
7. Context efficiency — class-tagging inflates per-finding token count; synthesis must fit budget.
8. No regression to Step 4 Apply/Dismiss/Ask — 067 must stay in force.

### Scope boundaries relevant to this topic

- Ticket 132 defers H2, FP5 (per epic DR-6).
- Guards against regressing Step 4 beyond intended C→Ask tightening.
- Plan-later items: action-surface mechanism choice, class-count justification, pilot-vs-flag approach.
- No requirements/skills.md exists; all governance is project-level + the ticket itself.

### Related backlog items

- **067** (complete): Step 4 Dismiss-output suppression. Must not regress.
- **066** (complete): parent epic for 067.
- **053**: synthesis compression — preserves "Do not soften or editorialize" and distinct-angle rules.
- **046**: sonnet default for interactive subagents including critical-review.
- **082 / 085**: 4.7 prompt-delta audits — flag two load-bearing patterns in /critical-review SKILL.md that must be preserved.
- **086**: output-floors applicability block currently excludes /critical-review — noted but unresolved.
- **120 / 121**: plugin packaging decision for /critical-review (cortex-interactive vs cortex-overnight-integration); relevant if action surface adds module-load imports.
- **063**: `skip-review` flag for auto-invoked /critical-review documented but not implemented — runtime gate not in scope here.

## Tradeoffs & Alternatives

### Taxonomy shape (A1–A4)

**A1 — Ternary A/B/C (fix-invalidating / adjacent-gap / framing)** — the ticket's stipulated shape.
- **Pros**: Matches Kotlin failure content 1:1. Synthesizer rule "refuse B→A promotion" directly expressible. C-class → Ask routing is one-line.
- **Cons**: Research OQ2 flags as asserted rather than derived; no prior-art uses exactly three content classes. Risk of C-class becoming a catch-all. Reviewers may bias toward A under "that's what counts" pressure.
- **Fit**: Good fit for Kotlin content; weak derivation from prior art.

**A2 — Binary blocking × orthogonal type axis** (Conventional Comments / Reviewable shape).
- **Pros**: Matches prior-art consensus directly (every cited source collapses to binary blocking commit + type metadata). "Refuse B→A promotion" rephrases as "refuse to synthesize a blocking verdict when no finding is tagged blocking." Straddle cases resolve naturally ("adjacent-gap but blocking" is a legal combination). LLM reviewers handle binary commit + short type label well.
- **Cons**: Two-axis output complicates reviewer prompt and synthesizer rule (two fields to emit, two to aggregate). Blocking axis partially duplicates "fix-invalidating" signal — answerability question ("is blocking + adjacent-gap legal?"). Validation surface doubles.
- **Fit**: Strongest prior-art fit; highest expressive power; highest spec-complexity.

**A3 — Binary blocking only** (drop type axis).
- **Pros**: Simplest rule. Smallest prompt footprint. Straddle cases evaporate.
- **Cons**: Discards type signal entirely. In Kotlin, all four findings might have been tagged blocking, reproducing the failure. Loses C-class → Ask routing.
- **Fit**: Simplicity trades away the exact signal needed.

**A4 — Four/five-class (add convergence, pattern-violation, or nit)**.
- **Pros**: Richer routing.
- **Cons**: Classifier-accuracy risk compounds per added class. Convergence is cross-finding, not a per-finding class — category error. Nit is already Dismiss. Over-engineers.
- **Fit**: Over-engineered for documented failures.

**Recommended**: **A2 (binary + type axis)** as primary, **A1 as fallback** if spec-phase prompt-bloat measurement forces downshift. The prior-art derivation requirement in OQ2 is load-bearing; A2 is the answer prior art actually gives. If A1 is retained, the derivation AC must be satisfied with explicit argument for ternary collapse (e.g., "three content types is the minimum to express B→A non-promotion; finer granularity not required").

### B-class action surface (B1–B5)

**B1 — Auto-emit follow-up backlog ticket stub per B-class finding**.
- **Pros**: Strong backlog tooling integration. Tickets surface in morning reports, dashboard, backlog index. Most robust under operator non-action.
- **Cons**: Spam risk undefended — four B findings across four reviewers produce four tickets for effectively one concern. De-dup logic is a new design. Coupling creates failure cascade if backlog write fails. /critical-review runs ad-hoc outside lifecycles — surprising backlog writes there. May feed "must be shipped soon" anxiety that A2 blocking axis was trying to isolate.
- **Fit**: Highest AC satisfaction; highest blast radius; de-dup must be specified.

**B2 — Structured residue file** (sidecar YAML/JSON or events.log entry).
- **Pros**: Minimal blast radius. Natural fit with clarify-critic.md precedent and pipeline deferral precedent. Inside a lifecycle, writing to `lifecycle/{feature}/events.log` reuses existing infrastructure. Reversible.
- **Cons**: "Observable evidence of silent dismissal" (AC3) requires residue be read somewhere. Without dashboard/morning-report/statusline integration, residue file is silent dismissal with extra steps. Ad-hoc invocation has no obvious residue destination. Spec 067 R8 forbade events.log refs in SKILL.md — rewriting that constraint must be flagged. **Mechanism depends on a consumer this ticket isn't building.**
- **Fit**: Low-cost audit substrate; requires separate surfacing mechanism.

**B3 — Synthesis appendix via Step 4 Ask channel**.
- **Pros**: Reuses existing Ask surface. No new artifact or infrastructure. Works identically in/out of lifecycle. Operator sees B findings inline with other decisions.
- **Cons**: Bloats Ask. Operators may train to skim. No durable audit — operator dismissal leaves no record. Re-introduces a version of H5 Dismiss-rationale leakage that 067 removed. Changes Ask semantics from "consequential decisions" to "mixed bag."
- **Fit**: Cheapest; weakest audit; regression risk for 067.

**B4 — Hybrid (residue file + Ask escalation for defined subset)**.
- **Pros**: Durable audit + operator surface. Full AC3 satisfaction.
- **Cons**: Subset rule ("which B findings escalate vs. reside") is a new unsolved design. Doubles mechanism count.
- **Fit**: Strongest AC satisfaction; highest complexity.

**B5 — Passive (rename sections, no surface)**.
- **Fit**: Excluded. Fails AC3 by definition.

**Recommended**: **B2 (structured residue file) with surfacing as an in-scope Spec decision**, flagged. Residue matches existing events.log / pipeline-deferral conventions, lowest blast radius, forward-compatible with multiple surfacing options. **Spec must name the surfacing consumer** (events.log + morning-report mention, sidecar + dashboard card, etc.); without named surfacing, B2 collapses to B5 and fails AC3. **B1 is the fallback** if Spec finds surfacing heavier than backlog integration, with a documented de-dup rule for multi-reviewer duplicates. B3 rejected due to 067 regression risk + durable-audit gap. B4 rejected due to unsolved subset-rule design.

### Straddle-case protocol (S1–S4)

**S1 — Multi-class tagging** (`[A, B]` simultaneously).
- Natural fit under A2 (blocking + type are orthogonal); awkward under A1 (breaks "refuse B-only → A" rule).

**S2 — Precedence ordering** (A beats B beats C).
- Clean but lossy; loses the adjacent-gap signal whenever A+B collide — exactly the signal the B-surface is for.

**S3 — Reviewer picks one with reasoning**.
- Reviewer bias toward A under "that's what counts" pressure. Reasoning is auditable post-hoc but doesn't prevent emission-time bias.

**S4 — Separate findings per class** (one A on the core, one B on the adjacent pattern).
- Clean atomic classification; de-dup burden on synthesis (already solved — synthesis finds through-lines).

**Recommended** (tied to taxonomy):
- Under **A2**: **S1** (multi-axis resolves by construction — no protocol text needed).
- Under **A1**: **S4** (separate findings) — preserves signal, keeps synthesizer rule simple.

### Classifier validation (V1–V4)

**V1 — Kotlin session recovery**: highest validity if logs exist; logs are unavailable in this repo (confirmed). Ground-truth is operator's post-hoc reconstruction — confirmation-bias risk.

**V2 — Synthetic analog**: deterministic re-runnable fixture; adversarial-to-self if prompt author writes the fixture.

**V3 — Held-out pilot** on next N /critical-review invocations: right instrument for ongoing validation; wrong instrument for pre-ship AC. Overlaps with base-rate instrumentation epic.

**V4 — LLM-judge evaluation**: circular (same model family under test and judging). Not recommended.

**Recommended**: **V1 → V2 combination with V2 as realistic path**. V1 attempts first (probe log availability early); if unrecoverable, fall back to V2 with **at least two fixtures — one pure-B aggregation case (Kotlin pattern) and one straddle**, authored before the prompt is written or by someone other than the prompt author to contain construction-validates-prompt risk. V3 deferred. V4 excluded.

### Overall recommended approach

- **Taxonomy**: A2 primary, A1 fallback.
- **Action surface**: B2 primary with named surfacing consumer; B1 fallback if Spec judges surfacing heavier than backlog integration.
- **Straddle**: S1 under A2; S4 under A1.
- **Validation**: V1 → V2; V2 realistic path with fixture-authorship guard.

## Open Questions

- **CVSS-prior-art citation in epic research is incorrect.** Epic `research/critical-review-scope-expansion-bias/research.md` cites CVSS v4.0 as prior art for "orthogonal severity × scope axes." Web research this round confirms CVSS v4 produces a single composed scalar, not orthogonal axes — the epic's claim is factually wrong and any A2-taxonomy derivation arguments that lean on it must be restated. **Deferred: will be resolved in Spec by citing the actual sources that do support orthogonal binary × type axes (Conventional Comments' label + decoration grammar) and dropping CVSS from that argument.**
- **A1-vs-A2 taxonomy choice requires a prompt-bloat measurement this research cannot perform.** Spec should draft the A2 reviewer prompt, measure token delta against the current template, and downshift to A1 only if delta exceeds a declared budget. **Deferred: will be resolved in Spec with an explicit budget and measurement step.**
- **B2 requires a named surfacing consumer.** A residue file with no reader is silent dismissal. Spec must name the consumer (events.log + morning-report line, sidecar + dashboard card, or similar). **Deferred: will be resolved in Spec as a first-class requirement on the action-surface decision.**
- **Spec 067 R8 forbade events.log references in SKILL.md.** If B2 uses events.log as the residue channel, 067 R8 is being rewritten. **Deferred: Spec must either choose a non-events.log residue destination or explicitly update 067 R8 with rationale.**
- **Straddle protocol is determined by taxonomy choice.** Cannot close straddle until A1/A2 closes. **Deferred: resolved downstream of taxonomy decision in Spec.**
- **V1 (Kotlin recovery) feasibility is unknown.** Session logs not found in-repo; user may have them elsewhere. **Deferred: Spec probes log availability early; if infeasible, V2 fixture-authorship guard is required.**
- **Step 2c fallback prompt shape is silent in the ticket AC.** The single-agent fallback at SKILL.md:113–142 also emits objections/through-lines; Spec must decide whether class tagging propagates to the fallback or is explicitly out of scope. **Deferred: Spec decision; minor scope question.**
- **`output-floors.md` currently excludes /critical-review from applicability** (per backlog 086). If class-tagging affects per-finding output floor, the exclusion may need revisiting. **Deferred: out-of-scope for this ticket; flag as a follow-up if the skill's applicability-block changes.**
- **Dismissal-dilution effect is practitioner-consensus but not rigorously measured.** The ticket's premise rests on n=1 Kotlin + practitioner writing + Netlify's 5-tier evolution. No academic rigor exists to cite. **Deferred: accept as design-precaution motivation; frame value-case accordingly in Spec §4 complexity/value gate.**
- **Should /lifecycle's `clarify-critic.md` adopt the same taxonomy fix?** Shares H1–H4 with /critical-review. Out of scope for this ticket. **Deferred: resolved as a potential follow-up after this ticket lands and V2 fixture validation passes.**
