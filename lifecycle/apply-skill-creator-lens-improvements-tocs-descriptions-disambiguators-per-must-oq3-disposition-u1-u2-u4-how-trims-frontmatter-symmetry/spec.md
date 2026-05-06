# Specification: Apply skill-creator-lens improvements (TOCs, descriptions + when_to_use, per-MUST OQ3 disposition, U1/U2/U4 HOW trims, frontmatter symmetry)

## Problem Statement

The skill-creator-lens audit pass on epic #172 surfaced six classes of skill-design quality concerns the prior content-density audits missed because they focused on "what's redundant" rather than "what's well-formed." This ticket lands the bundled mechanical improvements: TOCs on >300-line files, description-trigger fixes plus a new `when_to_use` frontmatter field for sibling disambiguators (a structural divergence from ticket-178 §2's prescribed in-description mechanism — see R2 for explicit scope-expansion rationale), uniform OQ3 MUST softening across both `review.md` and `clarify-critic.md` with parallel follow-on backlog items for the structural mitigations (parser hardening + schema validator), HOW-prose trims (U1/U2/U4), and frontmatter symmetry on `critical-review`. Net outcome: ~80–100 lines of HOW-prose removal, four navigable >300-line reference files, four canonically-aligned skill descriptions, and structurally-correct OQ3 disposition that respects CLAUDE.md's closed evidence list (no third evidence form invented; no asymmetric reading between the two MUST groups).

## Requirements

### R1. TOCs on four >300-line files

Add a `## Contents` H2 section immediately after frontmatter (and before the first protocol-equivalent heading) on each of these four files, using the cortex template at `skills/discovery/references/research.md:5–15` as the canonical pattern:

- `skills/lifecycle/SKILL.md` (380 lines)
- `skills/lifecycle/references/plan.md` (309 lines)
- `skills/lifecycle/references/implement.md` (301 lines)
- `skills/critical-review/SKILL.md` (365 lines)

Format: numbered list with explicit markdown links `[text](#anchor)`, anchors lowercase-hyphenated with numeric prefixes. Depth: H2 entries only (no H3 nesting). Threshold confirmed at 300 lines per `skill-creator/SKILL.md` (cortex's adopted threshold); the 100-line variant from `platform.claude.com` is out of scope.

**Acceptance criteria** (binary-checkable):
- `for f in skills/lifecycle/SKILL.md skills/lifecycle/references/plan.md skills/lifecycle/references/implement.md skills/critical-review/SKILL.md; do head -25 "$f" | grep -q '^## Contents$' || echo "MISSING TOC: $f"; done` returns no MISSING lines.
- Each TOC is positioned BEFORE the first protocol-equivalent H2 (visual inspection — no stricter check feasible since H2 ordering varies per file).

### R2. Adopt `when_to_use` frontmatter on all four SKILL.md files; trim descriptions to fit cap

**Scope-expansion acknowledgment**: Ticket-178 §2 prescribes that sibling-disambiguator clauses go in the `description` field. R2 instead adopts the Anthropic-canonical `when_to_use` frontmatter field for that content. This is a structural divergence from ticket-178's prescribed mechanism, justified by: (a) Anthropic-canonical alignment (Claude Code documents `when_to_use` as the dedicated routing/triggering field), (b) FM-9 char-cap relief (lifecycle 901 chars and critical-review 895 chars are within 130 chars of the 1024 description cap; in-description disambiguators would exceed cap), (c) future-disambiguator additions become O(1) (one new field) rather than O(N²) (every existing description re-edited). The trade-off — adding a new frontmatter field × 4 — is accepted; the spec back-amends ticket-178's body to acknowledge the mechanism change (see Changes to Existing Behavior).

Add the `when_to_use` field to all four SKILL.md files. Move sibling-disambiguator content there. Keep `description` focused on (a) what the skill does and (b) explicit trigger phrases ("Use when…"). This resolves OQ-B and the FM-9 char-cap pressure.

For each of the four skills, the `when_to_use` content includes:
- Concrete trigger phrases that ticket-178 §2 flagged as missing (e.g., for `lifecycle`: "start a feature", "build this properly"; for `refine`: "spec this out", "tighten the requirements", "lock in the spec"; for `critical-review`: "poke holes in the plan", "stress test the spec", "is this actually a good idea", "review before I commit").
- A sibling-disambiguator clause: "Different from /cortex-core:{sibling} — {one-line distinction}" for each skill that has a near-sibling. Per ticket-178 §2:
  - lifecycle: "Different from /cortex-core:refine — refine stops at spec.md; lifecycle continues to plan/implement/review."
  - refine: "Different from /cortex-core:lifecycle — refine produces spec only; lifecycle wraps refine and continues to plan/implement."
  - discovery: "Different from /cortex-core:research — research produces a research.md and stops; discovery wraps clarify→research→decompose and ends with backlog tickets." (already present in description; relocate to when_to_use)
  - critical-review: keep the existing "/devils-advocate" differentiator (already present); relocate to when_to_use.

The `description` field should retain its primary "what + when" framing but drop the disambiguator clause that moves to when_to_use, so the field stays under the 1024-char Anthropic skill-creator cap.

**Acceptance criteria**:
- `awk '/^---$/{c++; if(c==2) exit} c==1 && /^when_to_use:/' skills/{lifecycle,refine,critical-review,discovery}/SKILL.md | wc -l` returns 4 (one match per file).
- `grep -c "Different from /cortex-core" skills/{lifecycle,refine,critical-review,discovery}/SKILL.md` returns at least 1 per file (each file has at least one disambiguator clause now living in when_to_use or the existing description).
- Each `description` field is ≤1024 chars when measured (use a small awk/python check at PR review time; not encoded as a hard CI gate in this ticket).

### R3. OQ3 per-MUST disposition (uniform soften per closed-list reading)

**SOFTEN** to positive-routing for ALL 7 in-scope MUSTs:
- 4 MUSTs in `skills/lifecycle/references/review.md` at lines 64, 72, 78, 80 (parser-protective for verdict JSON consumed by `metrics.py:221`).
- 3 MUSTs in `skills/refine/references/clarify-critic.md` at lines 26 (closed-allowlist warning template), 155 (`REQUIRED` field on every post-feature event — events.log schema invariant), 159 (cross-field invariant `MUST`: `origin: alignment` → `parent_epic_loaded: true`).

**Why uniform soften (not split)**: CLAUDE.md OQ3 enumerates a closed evidence list for retaining MUSTs — (a) `events.log` F-row OR (b) commit-linked transcript URL. Empirically (Adversarial FM-1) zero F-rows exist in the 158-feature events.log corpus, so the (a) prong is unfulfillable for ANY MUST in the codebase. No transcript URL evidence has been gathered for any of the 7 in-scope MUSTs. Therefore neither evidence form is satisfied; the OQ3 default ("default to soft positive-routing phrasing for new authoring") applies uniformly. Earlier OQ-A reasoning attempted to retain clarify-critic.md MUSTs by introducing new evidence categories ("security-adjacent," "schema invariant," "cross-field invariant") — but those are not on CLAUDE.md's closed list and adopting them as licenses would replicate the same closed-list violation the spec rejects in the parser-cite framing of ticket-178. Uniform soften is the only OQ3-compliant disposition under the closed evidence list.

**Mitigations** (each filed as a parallel follow-on, analogous structure):
- Review.md verdict-JSON parser-protection: R5 amends `backlog/182` to scope-cover `metrics.py:221` parser hardening (alias lookup or normalized field-name parsing).
- Clarify-critic.md schema invariants: R7 (new requirement) files a follow-on backlog item for the planned schema validator covering the dismissals invariant and the cross-field invariant. CLAUDE.md text itself anticipates this validator: "neither is programmatically validated in this version, but a future ticket may add a validator covering both."
- Clarify-critic.md:26 closed-allowlist (warning-template information-leak): also covered by R7's follow-on, OR if R7's validator scope cannot reach allowlist enforcement, R7 files a second sub-bullet for warning-template runtime validation.

The softened phrasing should be declarative-behavioral (per MindStudio empirical: "Lead with the answer first" beats "MUST be concise" on Claude Opus 4.7). Example rewrite for review.md:64 ("CRITICAL: The Verdict section MUST contain a JSON object with exactly these fields"):

> "The Verdict section is a JSON object with exactly these fields: …"

The strict format-contract emphasis is preserved; the imperative mode is dropped per CLAUDE.md OQ3 default. The same declarative pattern applies to lines 72, 78, 80 in `review.md` and lines 26, 155, 159 in `clarify-critic.md`. For lines 155 and 159 specifically, retain the schema-invariant prose but drop the imperative form ("any post-feature event whose findings[] contains origin: alignment has `parent_epic_loaded: true`" — descriptive rather than imperative).

**Ticket-178 amendments** (captured in Changes to Existing Behavior):
- Drop ticket-178 Verification line 94 ("MUSTs retained with parser-cite at metrics.py:221 documented") — parser-cite is closed-list-incompatible per CLAUDE.md OQ3.
- Drop ticket-178 Verification line 95 ("MUSTs softened to positive-routing OR have documented evidence trail") — the OR-disjunction's "documented evidence trail" branch is structurally vacuous (no F-row form exists in corpus). Replace with a single line: "All 7 MUSTs in review.md and clarify-critic.md softened to positive-routing per OQ3 default."

**Acceptance criteria**:
- `awk 'NR>=60 && NR<=90' skills/lifecycle/references/review.md | grep -cE 'MUST|CRITICAL|REQUIRED'` returns 0.
- `awk 'NR>=20 && NR<=170' skills/refine/references/clarify-critic.md | grep -cE 'MUST|REQUIRED'` returns 0 (all 3 instances softened).
- `grep -c "metrics.py" backlog/182-*.md` returns ≥1 (R5 amendment visible — see R5).
- R7's follow-on backlog item exists at `backlog/NNN-*.md` with parser-validator scope visible.
- `grep -c "MUSTs retained with parser-cite" backlog/178-*.md` returns 0 (line 94 dropped).
- `grep -c "documented evidence trail" backlog/178-*.md` returns 0 (line 95 dropped).
- `grep -c "softened to positive-routing per OQ3" backlog/178-*.md` returns ≥1 (replacement Verification line landed).

### R4. HOW-prose trims (U1, U2, U4)

**U1**: Replace `skills/critical-review/SKILL.md:336–365` (the ~30-line Apply/Dismiss/Ask body) with a ~5-line WHAT/WHY directive:

```
**Apply** when the fix is unambiguous and confidence is high.
**Dismiss** when the artifact already addresses the objection or the objection misreads stated constraints.
**Ask** when the fix involves user preference, scope decision, or genuine uncertainty.
Default ambiguous to Ask. Anchor-checks: dismissals must be pointable to artifact text, not memory; resolutions must rest on new evidence, not prior reasoning.
```

The remaining "After classifying all objections" sequence (re-read artifact, write updates, present compact summary) stays intact. Verbose worked-examples and "Apply bar" prose are absorbed into the brief directive above.

**U2**: Trim Constraints "Thought/Reality" tables across `skills/`. **Canonical named-consumer rule**: a row stays if and only if its Reality column references a **specific identifier** — a function name (e.g., `metrics.py:221`), a file path (e.g., `cortex_command/common.py`), a schema key (e.g., `verdict`, `parent_epic_loaded`), or a named test/validator/contract. Generic category mentions ("the parser", "validators", "downstream tests") without an accompanying specific identifier do NOT satisfy the criterion. This canonical rule supersedes earlier loose framings; it is the single authoritative criterion for retention.

**Implementation artifact requirement**: Implementation produces `lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/u2-decisions.md` enumerating per-row keep/drop decisions for every row in every Constraints table. Format per row: `- [file:line] | KEEP / DROP | <named identifier cited or "no specific identifier — drop">`. PR review verifies the artifact reflects the canonical rule.

**No numeric floor**: the deletion count satisfies the spec when (a) the canonical rule is applied to every row, AND (b) the per-row decisions are recorded in `u2-decisions.md`. If strict application yields fewer than the ticket-178 §4 ~50-row estimate, that is acceptable — the criterion is the authority, not the count.

**Wholesale table removal**: a table may be removed entirely only if `u2-decisions.md` records that ALL its rows lacked a specific identifier (no contract-protective row anywhere). If even one row has a named identifier, that row is retained and the table is preserved.

The 12 tables identified in research (file paths + line numbers below) are the corpus. Per-table row inventory and per-row keep/drop decisions are deferred to Plan/Implementation since they require reading each table:

- `skills/discovery/references/clarify.md:60`
- `skills/discovery/references/auto-scan.md:81`
- `skills/discovery/references/decompose.md` (line TBD)
- `skills/lifecycle/references/clarify.md:119`
- `skills/lifecycle/references/clarify-critic.md:159`
- `skills/lifecycle/references/specify.md:181`
- `skills/lifecycle/references/plan.md:303`
- `skills/lifecycle/references/implement.md:294`
- `skills/lifecycle/references/review.md:212`
- `skills/lifecycle/references/orchestrator-review.md:178`
- `skills/lifecycle/references/complete.md:98`
- `skills/refine/references/clarify-critic.md:207`

**U4**: Replace `skills/lifecycle/SKILL.md:30–36` slugify HOW prose with a one-line reference to the canonical implementation:

> "Use the canonical `slugify()` from `cortex_command.common`."

The canonical function exists at `cortex_command/common.py:110–117` (already verified in research). The example-based explanation in the current prose is redundant given that the function is documented at the source.

**Acceptance criteria** (content-based, robust to line-number drift):
- U1: `grep -c "Default ambiguous" skills/critical-review/SKILL.md` returns ≥1 (new directive present); AND `grep -c "Compliant: R10 strengthened" skills/critical-review/SKILL.md` returns 0 (verbose worked-example block removed).
- U2: `lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/u2-decisions.md` exists and lists a KEEP/DROP decision for every row in the 12 Constraints tables enumerated below; AND every retained row's `u2-decisions.md` entry cites a specific identifier (function name, file path, schema key, or named test/validator/contract); AND every dropped row's entry confirms "no specific identifier"; AND no table is wholesale-removed unless `u2-decisions.md` records that all its rows lacked a specific identifier.
- U4: `grep -c "cortex_command.common" skills/lifecycle/SKILL.md` returns ≥1 (new reference present); AND `grep -c "underscores become hyphens, not stripped" skills/lifecycle/SKILL.md` returns 0 (old verbose example removed).

### R5. Amend backlog/182 to expand scope to metrics.py:221 parser hardening

Per OQ-D, expand `backlog/182-vertical-planning-adoption-outline-and-phases-and-p9-s7-gates-and-parser-test.md`'s scope to include `cortex_command/pipeline/metrics.py:221` parser hardening (alias lookup or normalized field-name parsing).

**Honest framing of what R5 is and isn't**: R5 is a **documentation-only edit** at this ticket's merge gate — it amends backlog/182's body so the parser-hardening work is scope-included, not a code-level change to `metrics.py`. The actual parser-hardening implementation is deferred to backlog/182's own future implementation on an unspecified timeline. R5 does NOT itself protect against R3's FM-7 silent-degradation failure mode at this ticket's merge gate; that protection arrives only when backlog/182's implementation lands.

The amendment is a small edit to backlog/182's body adding a "Parser hardening at metrics.py:221" sub-bullet and updating its `tags` to include `metrics-parser` (or equivalent). No status change; 182's existing refinement state is preserved.

**Acceptance criteria**:
- `grep -c "metrics.py" backlog/182-*.md` returns ≥1 post-amendment.
- `cortex-update-item 182-vertical-planning-...-parser-test "tags=[...,metrics-parser]"` succeeds (or equivalent tag addition).

### R7. File parallel follow-on backlog item for clarify-critic schema validator

Per R3's uniform soften decision, the structural mitigation for `clarify-critic.md`'s schema-invariant MUSTs (lines 155, 159) and warning-template MUST (line 26) is a programmatic validator that enforces what the prose MUSTs currently enforce. CLAUDE.md text itself anticipates this: "neither is programmatically validated in this version, but a future ticket may add a validator covering both."

R7 files a new backlog item (or amends an existing related one) for the planned validator. Scope:
- **Schema validator**: validates `events.log` post-feature events for the `len(dismissals) == dispositions.dismiss` invariant and the `origin: alignment → parent_epic_loaded: true` cross-field invariant.
- **Warning-template runtime validator**: validates that the orchestrator's user-facing warnings on `missing` / `unreadable` parent-epic branches use one of the two allowlist templates and do not echo raw filesystem error text or helper stderr (line 26's information-leak protection).

**Honest framing**: R7 is also a **documentation-only edit** at this ticket's merge gate — it files a new backlog item (or amends an existing one) describing the validator scope. It does NOT itself protect against the FM-4/FM-5 silent-failure modes at this ticket's merge gate. Per OQ-D's pattern (no co-landing constraint), R7 is structurally analogous to R5 — both file follow-on work without gating this ticket on its arrival.

**Acceptance criteria**:
- A backlog item describing the schema validator + warning-template validator exists at `backlog/NNN-*.md` post-this-ticket.
- The backlog item references `clarify-critic.md` lines 26, 155, 159 as the prose MUSTs the validator replaces.
- The backlog item's `parent` field links to backlog/178 (this ticket) or epic 172.

### R6. Frontmatter symmetry on critical-review

Add four canonical fields to `skills/critical-review/SKILL.md` frontmatter: `argument-hint`, `inputs`, `outputs`, `preconditions`. Per OQ resolution, do NOT add `precondition_checks` (only `lifecycle/SKILL.md` has it; refine and discovery do not, so it's not a symmetry baseline).

The `argument-hint` value should be quoted per Issue #22161 to avoid TUI bracket-syntax hangs (e.g., `argument-hint: "[<artifact-path>]"`).

The `inputs` / `outputs` / `preconditions` content reflects critical-review's actual invocation contract per `plan.md:330` (artifact-path argument) and the synthesis-output behavior:

```
argument-hint: "[<artifact-path>]"
inputs:
  - "artifact-path: string (optional) — path to plan.md, spec.md, or research.md to review; if omitted, auto-detect from current lifecycle"
outputs:
  - "Synthesis prose presented in conversation"
  - "Optional residue write at lifecycle/{feature}/critical-review-{phase}.md"
preconditions:
  - "Run from project root"
  - "Artifact path resolves to an existing markdown file"
```

**Acceptance criteria**:
- `awk '/^---$/{c++; if(c==2) exit} c==1' skills/critical-review/SKILL.md | grep -cE '^(argument-hint|inputs|outputs|preconditions):'` returns 4.
- `awk '/^---$/{c++; if(c==2) exit} c==1' skills/critical-review/SKILL.md | grep -c '^precondition_checks:'` returns 0.

## Non-Requirements

- **Parser hardening implementation at `cortex_command/pipeline/metrics.py:221` is OUT of scope for this ticket.** R5 amends backlog/182's scope to include the work; the actual code change is deferred to 182's own implementation.
- **Schema validator implementation for clarify-critic.md invariants is OUT of scope for this ticket.** R7 files a follow-on; the actual validator is deferred to its own implementation.
- **Adopting the 100-line TOC threshold from `platform.claude.com` is OUT of scope.** Held at 300 per OQ-E. The 100-line variant would pull 11+ additional reference files into scope; file separately if desired.
- **Restructuring the bundled approach into 5 separate per-class tickets is OUT of scope.** Tradeoffs/Alternatives Alt B was explicitly rejected as gratuitous decomposition.
- **Co-landing gate between this ticket and the R5/R7 follow-ons is NOT used.** Per OQ-D, the user chose scope-amendment over reverse-link blocking. This accepts the risk that this ticket may land before the structural mitigations arrive (parser hardening or schema validator). The risk is monitored via the new Edge Case below ("cross-ticket sequencing").
- **Plain-bullet TOC variant (Anthropic example) is NOT used.** Cortex's existing template uses markdown-anchor links; this ticket adopts that variant for cross-corpus consistency.
- **Output-style or `--system-prompt` adoption to provide structural tone control is OUT of scope.** Per OQ6 / support.tools analysis, this is the structurally-strongest behavioral lever but cortex does not currently ship it. Tracked separately.
- **Restoring the precondition_checks field on discovery/refine for global symmetry is OUT of scope.** Only critical-review gets symmetry edits per ticket-178; discovery/refine remain on their current frontmatter.

## Edge Cases

- **TOC anchor format collisions**: If two H2 headings within a single file share the same slugified anchor (e.g., two `## Tasks` sections in plan.md), the markdown anchor will only target the first occurrence. Per Agent 1's heading inventory, plan.md has duplicate `## Overview` and `## Tasks` headings (lines 72,77 vs 161,164). The TOC must use disambiguated anchors (e.g., `#tasks-1`, `#tasks-2`) per GitHub-flavored markdown convention, OR the duplicate H2 headings must be renamed during this ticket. Implementation should choose disambiguation; renaming H2s expands scope.
- **Description char-cap regression**: If post-edit `description` field exceeds 1024 chars on any of the 4 SKILL.md files, the implementation must net-trim the description (move more content to `when_to_use`) before commit. PR review verifies char count.
- **Mirror regeneration vs canonical edit ordering**: Edits must be made to canonical sources (`skills/`); mirrors at `plugins/cortex-core/skills/` regenerate on pre-commit hook via `just build-plugin`. If the implementer edits a mirror file by accident, dual-source drift fires at pre-commit and the canonical edit is preserved.
- **Ticket 176 sequencing**: Backlog 176 (`status: refined`) deletes `skills/refine/references/clarify.md` (NOT clarify-critic.md). If 176 lands first via overnight, its deletion does not conflict with this ticket's clarify-critic.md edits. If this ticket lands first, the clarify.md deletion has no overlap. No ordering constraint.
- **U2 named-consumer ambiguity**: For Constraints rows whose Reality column is borderline (e.g., references "the parser" generically without naming the file), the implementer applies the named-consumer test conservatively — a row stays only if a specific identifier (function name, file path, schema key) appears in the Reality text. Generic "the parser" without further specification → drop.
- **U1 line-range drift**: If upstream edits to `critical-review/SKILL.md` shift the `336–365` block before this ticket lands, the implementer locates the Apply/Dismiss/Ask body by content (`grep -n "^**Apply**" skills/critical-review/SKILL.md`) rather than fixed line number.
- **Cross-ticket sequencing (FM-7 silent observability degradation)**: This ticket's R3 soften lands without a co-landing gate on R5's parser hardening (in backlog/182) or R7's schema validator (new follow-on). If R3 ships first, the structural mitigations are absent and the FM-7 failure mode is live: morning-review may show `review_verdicts: None` for case-drifted features and clarify-critic schema invariants are unenforced. **Detection mechanism**: a daily morning-report sanity check (existing or to-be-added) that flags `review_verdicts: None` on completed-this-cycle features. **Rollback trigger**: if morning-report flags `review_verdicts: None` more than once in a 14-day window AND backlog/182's parser hardening has not yet landed, revert R3's soften (restore the 4 review.md MUSTs) until parser hardening lands. **Acceptance window**: this ticket's R3 soften is acceptable for up to 90 days without R5/R7 mitigations landing; beyond 90 days, file a backlog item to either (a) revert R3 or (b) escalate R5/R7 prioritization. The 14-day flag and 90-day acceptance window are conservative defaults; tune based on actual review_verdict frequency observed post-merge.

## Changes to Existing Behavior

- **MODIFIED**: `skills/lifecycle/references/review.md:64,72,78,80` — 4 MUST/CRITICAL imperatives softened to declarative-behavioral phrasing per OQ3 default.
- **MODIFIED**: `skills/refine/references/clarify-critic.md:26,155,159` — 3 MUST/REQUIRED imperatives softened to declarative-behavioral phrasing per OQ3 default (uniform with review.md per R3).
- **MODIFIED**: `skills/critical-review/SKILL.md:336–365` — Apply/Dismiss/Ask body trimmed from ~30 lines to ~5 lines (U1).
- **MODIFIED**: `skills/lifecycle/SKILL.md:30–36` — slugify HOW-prose replaced with one-line reference (U4).
- **MODIFIED**: Constraints "Thought/Reality" tables across 12 files in `skills/` — rows trimmed per canonical named-consumer rule (U2). Per-row decisions recorded in `lifecycle/.../u2-decisions.md`.
- **ADDED**: `## Contents` H2 TOC sections on 4 large files (R1).
- **ADDED**: `when_to_use` frontmatter field on all 4 SKILL.md files (R2). New canonical-aligned routing field. **This is a structural divergence from ticket-178 §2's prescribed in-description disambiguator mechanism**; R2's body provides the scope-expansion rationale.
- **ADDED**: 4 frontmatter fields (`argument-hint`, `inputs`, `outputs`, `preconditions`) on `skills/critical-review/SKILL.md` (R6).
- **ADDED**: `lifecycle/.../u2-decisions.md` artifact — per-row keep/drop decisions for U2 (R4 acceptance requirement).
- **MODIFIED**: `backlog/178-apply-skill-creator-lens-improvements-tocs-descriptions-oq3-frontmatter.md` body:
  - Drop Verification line 94 ("MUSTs retained with parser-cite at metrics.py:221 documented") — parser-cite is closed-list-incompatible.
  - Drop Verification line 95 ("MUSTs softened to positive-routing OR have documented evidence trail") — OR-disjunction's evidence-trail branch is structurally vacuous (no F-row form exists in corpus).
  - Add replacement Verification line: "All 7 MUSTs in review.md and clarify-critic.md softened to positive-routing per OQ3 default."
  - Add ticket-body acknowledgment: R2's `when_to_use` adoption is a mechanism change from §2's in-description prescription.
- **MODIFIED**: `backlog/182-vertical-planning-adoption-outline-and-phases-and-p9-s7-gates-and-parser-test.md` body — add metrics.py:221 parser hardening sub-bullet to scope (R5). Documentation-only at this ticket's merge gate; actual code change deferred to 182's implementation.
- **ADDED**: A new follow-on backlog item for the clarify-critic schema validator + warning-template runtime validator (R7). Documentation-only at this ticket's merge gate; actual validator code deferred to the new ticket's implementation.
- **REMOVED**: ~80–100 lines of HOW-prose across `skills/` (net delta after TOC additions). Per `requirements/project.md` "Workflow trimming" philosophy.

## Technical Constraints

- **CLAUDE.md OQ3 closed evidence list** (CLAUDE.md:51–55): MUST escalations require (a) events.log F-row OR (b) commit-linked transcript URL. Parser-cite, "security-adjacent," "schema invariant," and similar non-listed categories are NOT additional evidence forms — adopting any would replicate the closed-list violation the spec rejects in ticket-178's parser-cite framing. R3's uniform SOFTEN decision applies the OQ3 default uniformly to both MUST groups; the structural mitigations (R5 parser hardening, R7 schema validator) are filed as parallel follow-ons.
- **F-row schema does not exist in events.log corpus** (Adversarial FM-1): zero F-rows across 158 features. Any retention criterion that relies on grep'ing events.log for F-rows fails closed. R4's U2 criterion uses canonical named-consumer rule (specific identifier — function name, file path, schema key) instead, with per-row decisions recorded in `u2-decisions.md`.
- **Pre-commit dual-source drift hook** validates byte-identical mirror sync; does NOT validate verdict-JSON shape downstream (Adversarial FM-7). R5 amends backlog/182 to scope-cover the parser-hardening fix; the actual code change is deferred to 182's implementation. R5 is **documentation-only at this ticket's merge gate** — see Edge Cases "cross-ticket sequencing" for detection mechanism, rollback trigger, and bounded acceptance window.
- **SKILL.md-to-bin parity enforcement** (`requirements/project.md:29`): canonical `skills/` files must remain wired through SKILL.md / requirements / docs / hooks / justfile / tests references. This ticket modifies skill prose only; no parity-relevant additions.
- **Lifecycle gating** applies to all 4 target SKILL.md files. This active lifecycle is the gating mechanism; implementation runs inside it.
- **Anthropic skill-creator description cap** = 1024 chars. lifecycle (901) and critical-review (895) have ~130 chars headroom (Adversarial FM-9). R2's `when_to_use` adoption relieves this pressure.
- **Anthropic argument-hint TUI hang** (Issue #22161): bracket syntax in YAML frontmatter must be quoted. R6's `argument-hint: "[<artifact-path>]"` value uses quoted bracket syntax.
- **Mirror regen via `just build-plugin`**: rsync from canonical to `plugins/cortex-core/skills/`. All canonical edits propagate automatically; do not edit mirrors directly.

## Open Decisions

- **Per-table row count enumeration for U2** is genuine Plan-phase implementation work — requires reading each of the 12 Constraints "Thought/Reality" tables to apply the named-consumer criterion row-by-row. **Why deferred**: the named-consumer criterion can only be applied by reading each row's Reality column; this is implementation-level inspection, not spec-level decision. Plan/Implementation will record per-table inventory.
