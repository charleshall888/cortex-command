# Research: Artifact template cleanups (Architectural Pattern optional in §3, index.md body-trim with frontmatter preserved, ## Open Decisions optional gated on #183)

Scope anchor (from clarify): Apply three independent template/artifact changes (and one cross-ticket-gated change) to reduce per-feature lifecycle artifact bloat without touching skill instruction docs:
1. Keep `**Architectural Pattern**` in the default plan §3 template as optional — exact rendering deferred to spec Open Decision.
2. Defer `## Scope Boundaries` deletion to #182's Outline replacement — no-op in #180.
3. Compress `lifecycle/{feature}/index.md` body — drop intro+wikilinks while keeping full frontmatter — H1 keep/remove deferred to spec Open Decision.
4. Make `## Open Decisions` optional in spec.md template — D4 gated on #183 (Gate 2 removal) via `blocked-by:[183]`.

## Codebase Analysis

### Files that will change (with line numbers verified against current state — note ticket #180's cited line numbers are drifted)

| Touch point | Current line range | Ticket-cited (stale) | Change behavior |
|---|---|---|---|
| `skills/lifecycle/references/plan.md` §3 canonical template | L137–173 | (n/a) | D1: insert `**Architectural Pattern**` line as optional. Field is NOT currently in §3 — D1 is additive, not "keep". |
| `skills/lifecycle/references/plan.md` §1b critical-tier prompt | L26–123 (closed enum at L32, L52–53, L73) | (n/a) | Unchanged (already requires field with closed enum on critical path). |
| `skills/lifecycle/references/orchestrator-review.md` P8 row | L165 | (n/a) | Verify-only: already gated on `criticality = critical`; explicitly N/A for non-critical. No edit needed for D1. |
| `skills/lifecycle/SKILL.md` "Create index.md" section | L123–157 | L108–143 | D3: drop body emission (H1+intro+wikilinks). Keep all seven frontmatter fields. |
| `skills/lifecycle/references/plan.md` index.md update step | L237–243 | L258–264 | D3: stop appending `- Plan: [[…]]` wikilink to body. Keep `artifacts` array append. |
| `skills/lifecycle/references/review.md` index.md update step | L147–153 | L147–153 | D3: stop appending `- Review: [[…]]` wikilink to body. Keep `artifacts` array append. |
| `skills/refine/SKILL.md` index.md update step (research) | L139–145 | L187–193 | D3: stop appending `- Research: [[…]]` wikilink to body. Keep `artifacts` array append. |
| `skills/refine/SKILL.md` index.md update step (spec) | L168–174 | L187–193 | D3: stop appending `- Spec: [[…]]` wikilink to body. Keep `artifacts` array append. |
| `skills/lifecycle/references/specify.md` §3 spec template | L139–140 (the `## Open Decisions` line) | (n/a) | D4: mark `## Open Decisions` optional; "## Open Decisions: None" remains valid. Gated on #183. |
| `skills/lifecycle/references/specify.md` §2b "Open Decision Resolution" | L91–97 | (n/a) | Retain as anti-bloat affordance; only heading-presence requirement relaxes. |
| `skills/lifecycle/SKILL.md` Step 6 Gate 2 prose | L270–274 | (n/a) | NOT edited by #180; deleted by #183. D4's blocked-by:[183] ensures #183 lands first. |

**Line-number drift note**: #180's ticket body cites `lifecycle/SKILL.md` L108–143, `plan.md` L258–264, `refine/SKILL.md` L187–193. Current state is L123–157, L237–243, L168–174 (and L139–145 for the research site). Recent compressions (e.g., #177) have shifted line numbers. Behavior described matches at the new locations; spec author should re-verify before edit.

### Relevant existing patterns

**Architectural Pattern field**: §1b critical-tier dispatch (`plan.md:32`): *"for critical tier only, they also populate the `**Architectural Pattern**` field in the Overview per the closed enum `{event-driven, pipeline, layered, shared-state, plug-in}`."* P8 row (`orchestrator-review.md:165`): *"Architectural Pattern field present and in taxonomy ... Gated on `criticality = critical` (when §1b ran); explicitly N/A for non-critical plans. Semantic fit is not checked here — that domain belongs to the synthesizer."* The default §3 template at `plan.md:137-173` does NOT currently render the field — D1's "keep optional in default §3" framing is misleading because there is no field to "keep"; D1 is an additive insertion.

**index.md template** (`lifecycle/SKILL.md:131-157`): writes seven frontmatter fields (`feature`, `parent_backlog_uuid`, `parent_backlog_id`, `artifacts`, `tags`, `created`, `updated`) plus a body of H1 wikilink + "Feature lifecycle for [[…]]." intro line. Per-artifact wikilinks (`- Research: [[…]]`, etc.) are appended at the 4 sites listed above. `artifacts: []` is mandated inline-array notation (`lifecycle/SKILL.md:157`).

**`## Open Decisions` template** (`specify.md:139-140`):
```
## Open Decisions
- [Only when implementation-level context is required and unavailable at spec time — include a one-sentence reason why. Resolution at spec time is strongly preferred; ask the user if uncertain.]
```
The §2b Pre-Write Check "Open Decision Resolution" (L91-97) attempts resolution before defer. Section is structurally treated as required by the canonical template; D4 marks it optional.

**Gate 2** (`lifecycle/SKILL.md:270-274`): MODEL-executed protocol step (not a hook/script). Scans `spec.md` for `## Open Decisions`, counts bullets, escalates tier to Complex when count ≥ 3. **Already skips silently** when section absent OR count < 3 — so D4's "optional" framing does NOT break Gate 2's fire-path; it only creates a doc-inconsistency where Step 6 prose still references a now-optional section. The doc-inconsistency dissolves when #183 deletes Gate 2 entirely.

### Integration points and dependencies

- **Dual-source enforcement**: all touch points are canonical sources under `skills/`. Mirrors at `plugins/cortex-core/skills/*` auto-regenerate via `just build-plugin` and the pre-commit hook (`.githooks/pre-commit` Phase 3, L168-174). The hook re-runs `just build-plugin` with stderr surfaced AND exits 1 on failure — no silent build failures.
- **No body-content consumer of index.md**: verified via grep across `bin/`, `hooks/`, `claude/hooks/`, `skills/`, `cortex_command/`, `docs/`, `requirements/`. Only `bin/cortex-archive-sample-select` (L251-266) touches index.md, and only via directory-contents membership check (`contents.issubset({"events.log", "index.md"})`) — not body content. Dashboard and statusline do not read index.md at all. The `tags:` frontmatter field is the only field with an explicit programmatic consumer (`review.md:14` for tag-based area-doc loading).
- **Existing archive index.md files**: NOT retroactively compressed (`lifecycle/SKILL.md:124` guard "if index.md exists, skip — do not overwrite"). Only new lifecycles get the trimmed body; ~138 existing archive index.md files retain their bodies. Mixed-format coexistence is benign because no consumer reads index.md body content.
- **Gate 2 dependency**: D4 is gated on #183 via `blocked-by:[183]`. Once #183 deletes Gate 2 from `lifecycle/SKILL.md`, `## Open Decisions` has no programmatic consumer and D4 is safe to land.
- **refine/SKILL.md duplication fix** (#173, complete): the index.md update region in `refine/SKILL.md` (L139-145, L168-174) does NOT intersect the now-fixed duplication region. #180 D3's refine/SKILL.md edits proceed independently of #173.

### Conventions to follow

- Edit canonical sources under `skills/` only; never touch `plugins/cortex-core/skills/*` mirrors directly.
- Use inline YAML array notation for `artifacts: [...]` per `lifecycle/SKILL.md:157`.
- Do not touch the §1b critical-tier Architectural Pattern emission (keep enum-required for critical) or the P8 orchestrator-review row (already correctly gated).
- For D4, retain `specify.md §2b` Pre-Write Open Decision Resolution as anti-bloat affordance; only the heading-presence requirement relaxes.
- No MUST/CRITICAL/REQUIRED language is added — all #180 changes are de-escalations (required→optional). MUST-escalation policy (CLAUDE.md §53-55) is not applicable.

### Per-sub-item findings summary

| Sub-item | Action | Files | Risk |
|---|---|---|---|
| #1 Architectural Pattern | Additive insertion in §3 as optional (D1) OR no-insertion (A2) — deferred to spec Open Decision | `plan.md` §3 | Decorative-when-populated drift for non-critical authors absent enum guidance |
| #2 Scope Boundaries | NO-OP in #180; #182 owns the delete via Outline replacement | (none) | None |
| #3 index.md compression | Drop wikilinks at 4 append sites + drop body emission in SKILL.md template. H1 keep/remove deferred to spec Open Decision | `lifecycle/SKILL.md`, `plan.md`, `review.md`, `refine/SKILL.md` (2 sites) | **Obsidian graph regression — see Adversarial Review** |
| #4 Open Decisions optional | Mark §3 section optional in specify.md template; "## Open Decisions: None" remains valid | `specify.md` §3 | Gate-2-doc-inconsistency until #183 lands — mitigated by `blocked-by:[183]` |

## Web Research

### 1. Optional-field policy in template-driven workflows

- **RFC 2119 (BCP 14)**: *"An implementation which does not include a particular option MUST be prepared to interoperate with another implementation which does include the option, though perhaps with reduced functionality, and vice versa."* Directly applicable: optional Architectural Pattern means consumers (P8, dispatch prompts) MUST tolerate both populated and absent cases. ([RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119))
- **MADR v4.0 minimal variant + ADR ecosystem consensus**: optional fields with inline guidance is the preferred pattern; tier-gating optional fields to a specific decision-type is *not* a documented pattern in mature ADR templates. AWS Architecture Blog and joelparkerhenderson/ADR repo both recommend "limit template to the most basic format possible, reducing fields to fill to a minimum." ([MADR Primer](https://www.ozimmer.ch/practices/2022/11/22/MADRTemplatePrimer.html), [adr.github.io](https://adr.github.io/adr-templates/), [AWS ADR Best Practices](https://aws.amazon.com/blogs/architecture/master-architecture-decision-records-adrs-best-practices-for-effective-decision-making/))

**Takeaway for D1**: keep-optional aligns with ADR/RFC convention. Author-discretion population (with optional marker) is well-precedented.

### 2. Obsidian wikilink navigation patterns — STRONGEST EXTERNAL RISK SIGNAL

- **Frontmatter wikilinks are NOT first-class in Obsidian's native graph view and backlinks**: *"Tags used in frontmatter are not used in the graph view"* and *"Links to other notes that were in the front matter are not shown in the graph view nor in the backlinks."* ([Obsidian Forum: Tags in frontmatter](https://forum.obsidian.md/t/tags-in-frontmatter-do-not-seem-to-be-used-in-the-graph-view/36881), [Wikilinks in YAML frontmatter](https://forum.obsidian.md/t/wikilinks-in-yaml-front-matter/10052))
- **Concrete regression risk**: compressing index.md body removes the wikilinks that currently power Obsidian graph + backlink navigation between index.md and its sibling artifacts (plan/spec/research/review) AND between backlog→index.md.
- **Mitigation options**:
  - **Dataview plugin auto-MOCs** ([Dataview README](https://github.com/blacksmithgu/obsidian-dataview)): replace static wikilinks with a Dataview query that auto-lists sibling files. Requires plugin install.
  - **obsidian-frontmatter-links plugin** ([Trikzon/obsidian-frontmatter-links](https://github.com/Trikzon/obsidian-frontmatter-links)): makes frontmatter wikilinks first-class. Requires plugin install.
  - **Retain minimal wikilink list under H2** (e.g., `## Files`): preserves graph + backlinks at ~5-line cost.
  - **Folder-tree navigation only**: Obsidian's left sidebar works without index.md body, but folders are not graph-view nodes — graph view loses the index.md→artifact edges.
- **Hugo `_index.md` direct prior art** for frontmatter-only index files ([Hugo Issue #3008](https://github.com/gohugoio/hugo/issues/3008)) — but it works *because Hugo's build system reads the frontmatter*. Cortex must identify whether its index.md consumer is Obsidian native UI (regression risk) or Cortex-internal parser (safe).

**Takeaway for D3**: Obsidian regression is well-documented and the strongest single risk signal in the research pass. Adversarial Review (below) confirms via vault inspection that this regression is REAL for the cortex-command vault (Obsidian core plugins are installed).

### 3. Frontmatter vs body trade-offs

- **Hugo `_index.md`, GitHub Docs `children:`, Jekyll, MkDocs**: all support frontmatter-driven navigation, but each works *because the build system reads frontmatter*. ([Hugo front matter](https://gohugo.io/content-management/front-matter/), [GitHub Docs frontmatter](https://docs.github.com/en/contributing/writing-for-github-docs/using-yaml-frontmatter))
- **When body is safe to drop**: (a) consumer reads structured metadata not prose; (b) prose is redundant restatement of frontmatter. The H1 wikilink + intro line in current index.md largely restate `feature:` and `parent_backlog_id` fields, so they're redundant for machine consumers — but they provide affordances Obsidian's native UI needs (per focus area 2).

### 4. Required → optional schema-evolution patterns — direct precedent for D4

- **Confluent Schema Registry / Avro / Protobuf**: ([Confluent Schema Evolution](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html), [INNOQ Schema Evolution](https://www.innoq.com/en/blog/2023/11/schema-evolution-avro/))
  > *"To enable forward compatibility when you need to change a required field to optional, you must first make that field optional by providing a default value... The safest strategy is a two-step migration: (1) First, make the required field optional with a default value (backward compatible). (2) Then, remove the field in a subsequent schema version (forward compatible)."*
  > *"It's advisable to separate addition and removal of mandatory fields, as this makes your schema evolution process easier."*
- **Cortex maps onto this pattern inverted**: #183 removes the *consumer* (Gate 2) first; #180 D4 makes the *producer* (spec.md template) optional after. Either order works in schema-evolution literature; the choice is consumer-tolerance vs producer-tolerance. Cortex chose consumer-first (#183 before #180 D4) — this is structurally sound.
- **Protobuf "field presence" debate**: distinguishing "section omitted" from "section present but empty" is well-studied. Cortex's parsers (if any) should tolerate both states.

### 5. Cross-ticket sequencing patterns

- **Jira, Linear, GitHub Issues**: `blocked-by` is **advisory metadata, not runtime enforcement**. ([Atlassian Community](https://community.atlassian.com/forums/App-Central-articles/Jira-Issue-Links-and-dependencies-management/ba-p/2050756), [Linear project dependencies](https://linear.app/docs/project-dependencies), [GitHub Issues dependencies](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies))
- **Trunk-based dev / feature flags**: industry direction is *away* from strict blocked-by sequencing and *toward* merging incomplete work with runtime guards. ([trunkbaseddevelopment.com](https://trunkbaseddevelopment.com/feature-flags/))
- **Cortex's choice (S1 strict blocked-by)**: structurally simpler than S2's conditional-prose guardrail, which is itself the anti-pattern epic-172 densification is removing. S1 is the right choice for *this* densification ticket precisely because the alternative (S2) re-introduces what the epic is trying to eliminate.

### 6. Required→optional migration patterns (cross-ref to focus area 4)

- **Two-step migration** is the documented norm: relax the producer-side requirement first, then optionally remove the consumer enforcement (or vice versa). Both orderings work if consumer tolerates absence and producer can omit. Cortex's `blocked-by:[183]` ensures the consumer enforcement (Gate 2) is gone before the producer relaxation (D4) takes effect — no transient inconsistency.

### Key URLs

- [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119)
- [MADR Template Primer](https://www.ozimmer.ch/practices/2022/11/22/MADRTemplatePrimer.html)
- [adr.github.io templates](https://adr.github.io/adr-templates/)
- [AWS ADR Best Practices](https://aws.amazon.com/blogs/architecture/master-architecture-decision-records-adrs-best-practices-for-effective-decision-making/)
- [Obsidian Forum — Wikilinks in YAML frontmatter](https://forum.obsidian.md/t/wikilinks-in-yaml-front-matter/10052)
- [Obsidian Forum — Tags in frontmatter not in graph view](https://forum.obsidian.md/t/tags-in-frontmatter-do-not-seem-to-be-used-in-the-graph-view/36881)
- [blacksmithgu/obsidian-dataview](https://github.com/blacksmithgu/obsidian-dataview)
- [Trikzon/obsidian-frontmatter-links](https://github.com/Trikzon/obsidian-frontmatter-links)
- [Hugo Issue #3008 — `_index.md` frontmatter only](https://github.com/gohugoio/hugo/issues/3008)
- [Confluent Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- [INNOQ — Schema Evolution (Avro)](https://www.innoq.com/en/blog/2023/11/schema-evolution-avro/)
- [Atlassian Community — Jira Issue Links](https://community.atlassian.com/forums/App-Central-articles/Jira-Issue-Links-and-dependencies-management/ba-p/2050756)
- [Linear Docs — Project dependencies](https://linear.app/docs/project-dependencies)
- [trunkbaseddevelopment.com — Feature flags](https://trunkbaseddevelopment.com/feature-flags/)

## Requirements & Constraints

### Relevant requirements (with source paths)

**`requirements/project.md`**:
- L13 — *"Handoff readiness: A feature isn't ready for overnight until the spec has no open questions, success criteria are verifiable by an agent with zero prior context, and all lifecycle artifacts are fully self-contained. The spec is the entire communication channel."* — spec.md content density is load-bearing; nothing removed from spec.md should break agent-with-zero-context handoff.
- L19 — *"Complexity: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."*
- L21 — *"Quality bar: Tests pass and the feature works as specced. ROI matters — the system exists to make shipping faster, not to be a project in itself."*
- L23 — *"Workflow trimming: Workflows that have not earned their place are removed wholesale rather than deprecated in stages. Hard-deletion is preferred over deprecation notices, tombstone skills, or env-var soft-deletes when the surface has zero downstream consumers (verified per-PR)."*
- L27 — *"File-based state: Lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files (markdown, JSON, YAML frontmatter)."*
- L30 — *"SKILL.md size cap: SKILL.md files are capped at 500 lines."* (lifecycle/SKILL.md = 374; refine/SKILL.md = 214 — both well under cap.)

**`requirements/observability.md`**: does NOT name `index.md` as an observability surface. Statusline/dashboard inputs are `overnight-state.json`, `events.log`, `active-session.json`. The `tags:` frontmatter field is the only index.md field with an explicit programmatic consumer (`review.md:14` tag-based area-doc routing). `created`/`updated`/`parent_backlog_uuid` are observability primitives the audit itself depended on (preserved per C2 correction).

**`requirements/multi-agent.md`, `requirements/pipeline.md`, `requirements/remote-access.md`**: no constraints specifically on plan.md / spec.md / index.md template content.

### Architectural constraints

**CLAUDE.md**:
- Dual-source enforcement: edits to `skills/lifecycle/*`, `skills/refine/SKILL.md` are canonical-source edits; `plugins/cortex-core/skills/*` mirrors auto-regenerate via pre-commit hook.
- `cortex-core:lifecycle` skill is required before editing any file in `skills/`, `hooks/`, `claude/hooks/`, `bin/cortex-*`, etc. — #180's touch points are all under `skills/`.
- MUST-escalation policy (L53-55): no MUST escalations added by #180 — all changes are de-escalations.

### Scope boundaries

**Explicitly in scope (per #180 body)**:
- D1: keep `**Architectural Pattern**` field in default plan.md §3 template as optional
- D3: compress `lifecycle/{feature}/index.md` body — drop H1 + intro prose + wikilink list; keep full frontmatter
- D4: make `## Open Decisions` optional in spec.md template (gated on #183)

**Explicitly out of scope / deferred**:
- D2 (Scope Boundaries deletion) — moved to #182
- Vertical-planning `## Outline`/`## Phases` adoption — owned by #182
- Gate 2 hook code / SKILL.md gate-prose collapse — owned by #183

### Parent epic context (#172)

- Confirms three artifact bloat findings: Open Decisions ~88% ceremony, Scope Boundaries no programmatic consumer, Architectural Pattern field 1.4% populated.
- Lists `refine/SKILL.md` 21-line copy-paste bug (owned by #173, complete — does NOT intersect #180's edit region).
- Epic L41 line listing still uses pre-correction framing ("critical-only", "frontmatter-only") — stale relative to #180's corrected body. Update of parent epic listing is out of scope for #180.
- Epic L56 records the original Hold-1 "Open Decisions blocked" framing; #183's DR-2 reversal is what unblocks D4.

### Sibling-ticket commitments

**#182** (`status: backlog`, not blocked-by anything):
- Outline absorbs Scope Boundaries + Verification Strategy.
- ## Risks preserves Veto Surface (rename).
- Tier-conditional `## Acceptance` section for complex-tier only.
- P9 + S7 gates fire per existing skip rules; P10 critical-only.

**#183** (`status: backlog`, not blocked-by anything):
- Migrate Gate 1 (research→specify Open-Questions escalation) to Python hook.
- Remove Gate 2 entirely — no hook, no skill prose.
- "Removing Gate 2 unblocks #180 D4 (Open Decisions optional) immediately."
- Empirical claim: "Gate 2: 0 fires across 153 lifecycles" — admitted methodologically thin (timing-pattern heuristics; #183 L26).

### MUST-escalation policy applicability

Not applicable. All #180 changes are de-escalations:
- D1 softens "field implicitly absent from §3 → field explicitly optional in §3" (or "field absent / present with optional marker")
- D3 drops body content (no modal verbs)
- D4 softens "section required by canonical template → section optional"

Per CLAUDE.md §53-55, the MUST-escalation policy applies only to *adding* or *restoring* MUST language. No effort=high dispatch evidence is required.

## Tradeoffs & Alternatives

### Sub-item #1 (Architectural Pattern in §3 template)

| Alt | Description | Complexity | Maintainability | Token cost | Alignment |
|---|---|---|---|---|---|
| **A1** | Add field to §3 as optional with note "optional; populate when load-bearing" | Low | Slight uptick (third state to reason about) | ~2 lines per default template; ~0 if author leaves blank | Best — honors prior research's "evaluated, not decorative" intent |
| **A2** | Do not insert in §3 (status quo); critical-tier §1b only | Trivial (no-op) | Cleanest — one field, one consumer | Best — zero overhead | Contradicts C3 correction; silently demotes field to "invisible" for non-critical |
| **A3** | Remove entirely from all templates | Higher — touches §1b + P8 + synthesizer | Looks cleanest superficially | Best raw savings (~3 lines per critical plan × 5 plans) | Worst — reverses prior research; removes working consumer |
| **A4** | Add to §3 with no optional-marker prose | Low | Worst — authors will read as required | ~2 lines per default | Worse than A1 (creates low-value populated values) |

**Recommendation: defer to spec Open Decision (user's choice). Within the deferred surface, prefer A1 with enum guidance (see Adversarial mitigation #2) over A2.**

The adversarial review found that A1's "populate when load-bearing" phrasing risks soft-MUST drift under post-Opus-4.7 tone semantics — recommend explicit conditional + enum: *"Include only when the implementation commits to one of: event-driven, pipeline, layered, shared-state, plug-in. Omit otherwise."* This doubles as the missing enum guidance for non-critical authors and prevents free-form drift.

### Sub-item #3 (index.md compression)

| Alt | Description | Lines saved per file | Obsidian risk | Audit-trail risk |
|---|---|---|---|---|
| **B1** | Drop intro+wikilinks, keep H1 | ~7–8 | Partial (loses intra-lifecycle wikilinks; preserves H1 as graph-view title) | None (frontmatter preserved) |
| **B2** | Drop H1+intro+wikilinks (max compression) | ~9–10 | Highest (loses all graph-view edges from index.md) | None |
| **B3** | Drop intro+wikilinks, keep H1 + "Generated YYYY-MM-DD" line | ~6 | Same as B1 | Worse — date duplicates frontmatter `created` |
| **B4** | Replace wikilink list with Dataview query block | ~3 | Mitigated (if user has Dataview plugin) | Worst — third-party plugin lock-in |
| **B5** | Status quo (no compression) | 0 | None | None |
| **B1+** | Keep H1 + intro line (the load-bearing backlog↔index edge), drop only per-artifact wikilinks | ~5 | Lowest of compression alternatives | None |

**Recommendation: defer H1 keep/remove to spec Open Decision (user's choice). Within the deferred surface, prefer B1+ (adversarial-recommended) — keep H1 wikilink AND `Feature lifecycle for [[…]]` intro line; drop only per-artifact wikilink list at the 4 append sites. Effect: ~5 lines saved per index.md instead of B2's ~10; preserves the load-bearing backlog→index.md and index.md→backlog graph edges that Obsidian's native graph view needs.**

Reject B3 (date duplicates frontmatter), B4 (third-party plugin lock-in), B5 (forfeits savings).

### Sub-item #4 (## Open Decisions optional in spec.md)

| Alt | Description | Audit-trail | Transient-window risk |
|---|---|---|---|
| **C1** | Mark optional; omit when empty OR emit "## Open Decisions: None" | Preserved when author chooses to emit | Mitigated by `blocked-by:[183]` |
| **C2** | Drop section entirely from template | Lost — deferral semantics merge into Non-Requirements | None (no producer = no consumer mismatch) |
| **C3** | Status quo (required, permissive "None" fallback) | Preserved | None |
| **C4** | Defer change; wait for #183 + re-evaluate | Preserved | None (most conservative) |

**Recommendation: C1, sequenced via `blocked-by:[183]`** (user's choice S1).

C1 is the right end state: prescribed by the audit, preserves "None" affordance for explicit-empty audit trails, aligns with epic-172 densification. Transient-window risk eliminated by gating on #183.

### Sequencing decision (`blocked-by:[183]`)

| Alt | Risk | Coordination cost | Anti-pattern surface |
|---|---|---|---|
| **S1** | None (structural — Gate 2 deleted before D4 lands) | Low (one ticket edge) | None |
| **S2** | Higher (transient-window guardrail relies on author behavior) | Higher (must remove guardrail prose later) | Yes — reintroduces conditional template prose epic-172 is removing |
| **S3** | None (split D4 into its own ticket) | Highest (three tickets in chain) | None |

**Recommendation: S1 (user's choice).** S2 is rejected because conditional-prose guardrails are the anti-pattern epic-172 densification is eliminating. S3 over-fragments without materially reducing risk.

## Adversarial Review

### Failure modes and edge cases

- **Obsidian graph-view regression is REAL, not theoretical.** `.obsidian/` exists at repo root with `graph`, `backlink`, `outgoing-link`, `properties` core plugins enabled (per `.obsidian/core-plugins.json`) and NO community plugins (no `plugins/` subdir; Dataview and `obsidian-frontmatter-links` are NOT installed). Obsidian's native graph and backlink panes do NOT index frontmatter wikilinks — they only index body-content `[[…]]`. Dropping H1+intro+wikilink list breaks graph-view connectivity from index.md to plan/spec/research/review AND breaks the backlog→index.md wikilink edge. **B2 (drop H1) + body-trim is a real navigation regression for this specific repo.**

- **Scope Boundaries audit number is INVERTED in #180 body.** Direct grep of `lifecycle/archive/*/plan.md` shows 65 of 138 plans (47.1%) OMIT Scope Boundaries; 73 (52.9%) INCLUDE it. The ticket's "53% omit" figure refers to INCLUDE, not omit. The deferral procedurally still works (Outline absorbs Scope Boundaries regardless of ratio), but the framing in #180 and the parent audit is empirically wrong.

- **§3 Architectural Pattern field will lack enum guidance for non-critical authors.** All five closed-enum mentions (`event-driven, pipeline, layered, shared-state, plug-in`) live in `plan.md` L32, L52, L73 — all gated on `criticality = critical`. The §3 template at L137-173 contains zero enum guidance. If D1 inserts the field as "optional; populate when load-bearing," a non-critical author has no closed-set constraint visible — silent free-form drift ("microservices", "Pipeline", "event_driven") will neither be caught nor surfaced (P8 is N/A for non-critical).

- **Gate 2 "0 fires" claim is empirically supported but methodologically partial.** Scanned all `complexity_override` events in `lifecycle/archive/*/events.log`: 13 of 16 fall in Gate 1 window (research→specify), 3 are post-plan-transition manual overrides, 0 fall cleanly in Gate 2 window (specify→plan) with auto-firing semantics. **However**, the events.log payload has no `gate` field (per #183 L45, adding one is part of #183's scope), so attribution is heuristic. D4's `blocked-by:[183]` is the right structural mitigation — once #183 deletes Gate 2 entirely, the empirical-vs-heuristic distinction becomes moot.

- **Open Decisions empty-rate validates C1 at corpus scale.** Of 108 archive spec.md files with `## Open Decisions`, 71 (65.7%) have zero items beneath the heading. C1 trims ~71 sections. Larger than the Scope Boundaries split (47/53) and the Architectural Pattern population rate (1.4%).

- **Soft-MUST drift in proposed prose** (D1 specifically). The phrase "optional; populate when load-bearing" introduces normative judgment ("load-bearing") that under post-Opus-4.7 tone semantics a model could read as "you should always assess whether the field is load-bearing → therefore always emit some value to demonstrate you assessed it." Compare existing template-side optional patterns: `critical-review/SKILL.md:147` uses `"<optional: rationale when splitting per Straddle Protocol>"` — explicit conditional trigger, no normative judgment. Safer phrasing: *"Include only when the implementation commits to one of: event-driven, pipeline, layered, shared-state, plug-in. Omit otherwise."*

- **Mixed-format index.md hazard is bounded.** `cortex-archive-sample-select` (only program that touches index.md) checks dir-contents membership not body content. Dashboard, statusline, tests do not walk index.md body. Old (body-rich) and new (frontmatter-only) index.md files coexist without runtime breakage. The 138 existing archive index.md files retain their bodies (no migration).

- **Self-referential hazard in #180's own spec.md is small.** #180 is the ticket making `## Open Decisions` optional in spec.md. Its own spec.md will USE `## Open Decisions` (for the deferred Q1 + Q2). Since C1's semantics are "omit when empty, populate when items exist," and #180's spec has items, no contradiction arises. Recommend inline note in the post-change template: *"omit only when empty; include with items when uncertain at spec time"* to prevent reverse drift.

- **Audit's missed-consumer track record is mixed.** Prior research flagged the audit method "demonstrably missed implicit consumers in 4 reference files." Direct verification: 1.4% Architectural Pattern is correct (2/138); 53% Scope Boundaries is INVERTED. So the audit method has both a confirmed inversion error and missed-consumer issues — corpus statistics need direct grep verification before being cited downstream.

### Security concerns or anti-patterns

- None substantive. No credential, sandbox-permission, or filesystem-trust concerns. Changes are purely template-section optionality.

### Assumptions that may not hold (with verification result)

| Assumption | Verification |
|---|---|
| "No body-content consumer of index.md" | VERIFIED (only `cortex-archive-sample-select` touches index.md and only via dir-membership) |
| "Obsidian graph regression is theoretical" | **REFUTED** — `.obsidian/` exists with graph/backlink core plugins enabled; community plugins NOT installed |
| "Gate 2: 0 fires" | STRUCTURALLY VERIFIED with heuristic caveat (#183 L26 admits) |
| "Architectural Pattern population 1.4%" | VERIFIED (2/138) |
| "Scope Boundaries 53% omit" | **REFUTED** — actual is 47.1% omit, 52.9% include (inverted) |
| "Open Decisions ~88% ceremony" | Partial: 65.7% empty-rate verified on 108 specs with the section |
| "Pre-commit hook reliable on build-plugin failure" | VERIFIED (`.githooks/pre-commit:168-174`) |
| "No plan-template Task references Open Decisions" | VERIFIED via grep |
| "refine/SKILL.md duplication fix (#173) complete and non-intersecting" | Relied on Agent 1's claim; spec should re-confirm |

### Recommended mitigations

- **For D3 (Obsidian regression)**: prefer **B1+** within the deferred Open Decision — keep H1 wikilink AND `Feature lifecycle for [[…]]` intro line; drop only the per-artifact wikilink list at the 4 append sites. Preserves load-bearing backlog↔index.md graph edges; ~5 lines saved per file instead of ~10. Update the 4 wikilink-append sites (`plan.md:237-243`, `review.md:147-153`, `refine/SKILL.md:139-145` + `:168-174`) to NOT append per-artifact wikilinks — otherwise body regenerates after the first phase write.

- **For D1 (enum drift)**: in the §3 template, replace "optional; populate when load-bearing" with explicit conditional + enum: *"Include only when the implementation commits to one of: event-driven, pipeline, layered, shared-state, plug-in. Omit otherwise."* This (a) prevents free-form values, (b) makes the field deterministically present-or-absent, (c) doubles as missing enum guidance for non-critical authors. **Alternative**: keep D1 as A2 (do not insert in §3 at all) — A2 is structurally cleaner since the ticket's "keep" framing is misleading (the field isn't currently in §3).

- **For audit-number errors**: correct the Scope Boundaries 53%/47% inversion in any downstream artifact that cites the figure. The deferral itself is procedurally fine (Outline absorbs regardless). Spot-check other audit-derived counts in the spec phase before citing.

- **For D4 sequencing**: keep `blocked-by:[183]` strict (S1). Do not relax to advisory or weaken to "after #183" — the structural mitigation is what makes the empirical-vs-heuristic Gate-2 attribution gap moot.

- **For self-referential drift in #180's own spec.md**: when writing #180's spec, populate `## Open Decisions` with the deferred Q1 + Q2 items. After the template change lands, an inline note in the post-change template should clarify: *"omit only when empty; include with items when uncertain at spec time."*

- **For soft-MUST drift in template prose**: avoid normative judgment phrases like "when load-bearing" in template optional-field guidance; prefer explicit conditional triggers ("Include only when X. Omit otherwise.").

## Open Questions

All four substantive open questions are explicitly deferred to the Spec phase as Open Decisions (per user's clarify-phase choices and per the adversarial recommendations above). Recording here for traceability — each will be re-surfaced during the §4 spec interview.

- **OQ1**: Should D1 insert `**Architectural Pattern**` into §3 (and if so, with what exact prose — adversarial-recommended explicit conditional + enum vs ticket's "optional; populate when load-bearing"), or should D1 land as A2 (no insertion in §3, status quo)? **Deferred to spec Open Decision per user clarify-phase choice.**

- **OQ2**: Should D3 keep the H1 wikilink + intro line (adversarial-recommended B1+ to preserve Obsidian graph edges) or drop them (B2, max compression)? **Deferred to spec Open Decision per user clarify-phase choice.**

- **OQ3**: Should the ticket's inverted Scope Boundaries audit number (53% vs 47%) be corrected in any downstream artifact (e.g., the parent epic listing at #172 L41), or left alone since #180 D2 is a no-op and #182 owns the actual delete? **Deferred to Spec — likely out of scope for #180 but worth pinning explicitly.**

- **OQ4**: For the post-change `specify.md` template, should the inline note ("omit only when empty; include with items when uncertain at spec time") be added to the §3 template body to prevent reverse drift, or is the §2b "Open Decision Resolution" prose sufficient? **Deferred to Spec.**

## Considerations Addressed

- **"Validate prior research's evaluated-not-decorative evidence at `lifecycle/archive/tighten-1b-plan-agent-prompt-to-require-strategy-level-distinction/research.md:54,194` is still current"**: Addressed by Agent 1 + Agent 3. The prior research's reasoning still holds for the critical-tier path (P8 is the evaluating consumer; gated `criticality = critical`). For non-critical tier, D1's "optional in §3" framing re-introduces a "decorative-when-populated" condition — accepted by the ticket as the cost of author-discretion. Adversarial mitigation #2 (explicit conditional + enum, OR A2 no-insertion) is the cleaner end state.

- **"Verify refine/SKILL.md edit region (L187-193) intersects parent epic's flagged duplication/copy-paste-bug region"**: Addressed. #173 (Z) is complete and fixed the 21-line copy-paste bug. #180 D3's index.md update region in refine/SKILL.md (actual lines L139-145 + L168-174, not the stale L187-193) does NOT intersect the now-fixed duplication. Edits proceed independently.

- **"Verify orchestrator-review P8 wording consistency with 'keep optional in default template' framing"**: Addressed. P8 (orchestrator-review.md:165) is already correctly gated on `criticality = critical` and explicitly N/A for non-critical. No P8 wording change is required for D1 because the field's absence on non-critical plans was already a P8-pass condition. No other reviewer/dispatch prompt reads the field outside §1b (plan.md L32, L52-53, L73) and P8.

- **"Confirm four artifacts: [...] append sites and exact frontmatter fields to keep vs drop"**: Addressed. Verified 4 append sites: `plan.md:237-243`, `review.md:147-153`, `refine/SKILL.md:139-145` (research), `refine/SKILL.md:168-174` (spec). All seven frontmatter fields kept per C2 (`feature`, `parent_backlog_uuid`, `parent_backlog_id`, `artifacts`, `tags`, `created`, `updated`); body content (H1+intro+wikilinks) drops per D3 (with H1 keep/remove deferred to spec Open Decision). Ticket's cited line numbers (108-143, 258-264, 187-193) are stale — current state is 123-157, 237-243, 168-174.

- **"For D4: characterize Gate 2's current enforcement consumer and the safe sequencing contract"**: Addressed. Gate 2 is a model-executed protocol step at `lifecycle/SKILL.md:270-274` — it scans spec.md for `## Open Decisions`, counts bullets, escalates to Complex when count ≥ 3. Already skips silently when section absent OR count < 3. D4's "optional" framing does NOT break Gate 2's fire-path — it only creates a doc-inconsistency in the gate prose. The safe sequencing contract is `blocked-by:[183]` (S1, user's choice): once #183 deletes Gate 2 entirely, there is no consumer to mis-signal. If D4 landed before #183, the failure mode is **silent escalation skip** for specs that legitimately had ≥3 latent open decisions but chose to omit the heading — empirically vanishingly rare (Gate 2: 0 confirmed auto-firings) but structurally avoidable via the strict sequencing.

- **"Surface alternative approaches to index.md compression that preserve Obsidian wikilink-navigation affordances"**: Addressed. Adversarial review confirmed via `.obsidian/` inspection that the vault HAS Obsidian core plugins (graph, backlink, outgoing-link, properties) enabled and NO community plugins installed. The graph-view regression is real, not theoretical. Three mitigation alternatives surfaced: (a) **B1+ (recommended)**: keep H1 wikilink + intro line, drop only per-artifact wikilinks (~5 lines saved per file; preserves load-bearing backlog↔index edges); (b) Dataview query block (requires Dataview plugin install — currently not installed); (c) retain minimal wikilink list under H2 (~5-line cost, preserves all edges). The recommended mitigation (B1+) is the smallest concession to Obsidian UX while still capturing meaningful compression savings.
