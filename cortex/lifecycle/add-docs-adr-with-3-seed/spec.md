# Specification: Add cortex/adr/ with policy doc, 3 seeds, and §2b emission rule

> Epic context: parent backlog [[221-adopt-grill-with-docs-progressive-disclosure-system]]. Discovery research at `cortex/research/grill-me-with-docs-learnings/research.md` arbitrated the ADR mechanism's shape (DR-1 through DR-6). This spec scopes Tier-1 layer 3 of the four-layer progressive-disclosure stack: project.md (rule) / glossary (vocabulary) / **ADRs (why)** / area docs (how). Sibling tickets ship glossary (#223) and cadence/posture uplift (#222).

## Problem Statement

`cortex/requirements/project.md` stays terse so it loads cheaply on every dispatch — but terseness compresses out the *why* behind each architectural constraint. Today the why scatters across commit messages, archived `cortex/lifecycle/*/spec.md` files, and informal CLAUDE.md prose. None is grep-able as a project-wide decision log. An author or reviewer asking "why does cortex use file-based state instead of a database?" has no single durable artifact to consult. Build a sequentially-numbered architectural decision log under `cortex/adr/` with three seeds whose rationale already exists in prose form, plus an emission rule in the specify phase so new decisions matching a three-criteria gate land in the log instead of dissipating.

## Phases

- **Phase 1: Mechanism** — create `cortex/adr/` directory, `cortex/adr/README.md` policy doc, three seed ADRs synthesized from existing prose, and back-pointer edits to source one-liners in `cortex/requirements/project.md`. Ships a self-contained, browsable ADR log on day one with the no-duplication rule satisfied at introduction.
- **Phase 2: Integration** — modify `skills/lifecycle/references/specify.md` §2 and §4 so that ADR proposal happens in-the-moment during the structured interview (when the author recognizes a requirement decision meets the three-criteria gate), and the `## Proposed ADR` section + `Proposed ADRs` consent bullet always render in spec.md / §4 (with "None considered" when empty) so a silently-skipped gate is observable.

## Requirements

1. **cortex/adr/ directory exists**: `cortex/adr/` is created at the repo root. **Phase**: Mechanism. Acceptance: `test -d cortex/adr` exits 0.

2. **Policy doc at cortex/adr/README.md**: Contains five sections — (a) Purpose, (b) Three-criteria emission gate (verbatim Pocock criteria: Hard to reverse + Surprising without context + Result of a real trade-off; all three required), (c) Frontmatter convention (status enum + superseded_by; explicitly no `area:` field at v1), (d) No-content-duplication discipline rule applying prospectively to ADRs created via this mechanism, (e) Consumer-rule prose specifying MUST automatic / MUST NOT automatic / SHOULD surface behaviors. The Purpose section explicitly defends the prose-only enforcement choice by citing CLAUDE.md:58 and arguing that the cost of occasional deviation is low here because (i) stray ADRs are recoverable via `status: deprecated`, which is the canonical supersede mechanism; (ii) new ADRs are individually PR-reviewable in a small directory; (iii) the policy doc itself surfaces in any PR that touches `cortex/adr/`. **Phase**: Mechanism. Acceptance: `grep -c "^## " cortex/adr/README.md` ≥ 5 AND `grep -c "CLAUDE.md:58" cortex/adr/README.md` ≥ 1.

3. **Three seed ADRs ship from day one**: `cortex/adr/0001-file-based-state-no-database.md`, `cortex/adr/0002-cli-wheel-plus-plugin-distribution.md`, `cortex/adr/0003-per-repo-sandbox-registration.md`. Each is 1-3 sentences fusing context + decision + reasoning per Pocock's stripped format; each carries `status: accepted`. Optional structure (Considered Options, Consequences) is included only when adding genuine value per Pocock's format. **Phase**: Mechanism. Acceptance: `ls cortex/adr/000[123]-*.md | wc -l` = 3 AND for each seed, `head -10 <file> | grep -c "^status: accepted$"` = 1.

4. **Source back-pointer edits**: After seed ADR creation, the one-liner in `cortex/requirements/project.md:27` (File-based state) is replaced with `→ ADR-0001: File-based state, no database` back-pointer. Similar back-pointer replacement for `cortex/requirements/project.md:7` (CLI wheel) → ADR-0002 and `cortex/requirements/project.md:28` (Per-repo sandbox registration) → ADR-0003. The back-pointer line is the single sentence remaining in source — the paragraph rationale moves to the ADR. **Phase**: Mechanism. Acceptance: `grep -c "→ ADR-0001" cortex/requirements/project.md` ≥ 1 AND `grep -c "→ ADR-0002" cortex/requirements/project.md` ≥ 1 AND `grep -c "→ ADR-0003" cortex/requirements/project.md` ≥ 1.

5. **Frontmatter schema (v1)**: ADR frontmatter uses `status: <proposed | accepted | deprecated | superseded>` (single enum value, not value-with-data) plus optional `superseded_by: NNNN` field for the back-reference. No `area:` field at v1 — deferred to a backfill ticket when ADR count crosses ~20 and area-filtering actually saves consumer effort. **Phase**: Mechanism. Acceptance: For each `cortex/adr/0*.md`, `grep -E '^status: (proposed|accepted|deprecated|superseded)$' <file>` exits 0 AND `grep -cE "^area:" cortex/adr/0*.md` returns 0 for all three.

6. **Promotion gate prose in policy doc**: README.md specifies that `proposed → accepted` transition happens at PR merge (i.e., a proposed ADR landing on the main branch is implicitly accepted unless explicitly held back via PR review). **Phase**: Mechanism. Acceptance: `grep -iE "proposed.*accepted.*merge|merge.*proposed.*accepted" cortex/adr/README.md` exits 0.

7. **§2 in-the-moment ADR-proposal posture**: `skills/lifecycle/references/specify.md` §2 (Structured Interview) gains a new soft-positive-routing posture line under the existing interview-area enumeration, stating: "When negotiating a requirement decision, if it meets the three-criteria gate from `cortex/adr/README.md` (Hard to reverse + Surprising without context + Real trade-off), draft an ADR proposal in the spec's `## Proposed ADR` section in the same turn rather than deferring." This is posture, not a control-flow gate — it sits alongside the existing "probe for must-have vs nice-to-have" guidance. **Phase**: Integration. Acceptance: `grep -c "three-criteria gate from .cortex/adr/README.md" skills/lifecycle/references/specify.md` ≥ 1.

8. **Spec.md template gains always-rendered ## Proposed ADR section**: The specify.md §3 spec template gains a required `## Proposed ADR` section between `## Open Decisions` and the end of the template. The section always appears; when no ADRs were drafted during §2, its body is the literal line "None considered." (with the trailing period). When ADRs were drafted, the body contains one `### Proposed ADR: <NNNN-slug>` sub-entry per draft, each containing the 1-3 sentence ADR body. **Phase**: Integration. Acceptance: `grep -c "^## Proposed ADR$" skills/lifecycle/references/specify.md` ≥ 1 AND `grep -c "None considered\." skills/lifecycle/references/specify.md` ≥ 1.

9. **§4 approval surface always renders Proposed ADRs consent line**: The §4 approval-surface bullet list (`Produced`, `Value`, `Trade-offs`) gains a required fourth bullet `Proposed ADRs` that always appears. Its value is "None" when the spec's `## Proposed ADR` section body is "None considered."; otherwise a comma-separated list of proposed ADR slugs. This makes a silently-skipped gate observable: the user sees "Proposed ADRs: None" and can ask "are you sure?" if any requirement decision smelled three-criteria-shaped. **Phase**: Integration. Acceptance: `grep -c "Proposed ADRs" skills/lifecycle/references/specify.md` ≥ 1 AND `awk '/^### 4. User Approval/{u=NR} /Proposed ADRs/ && NR>u{p=NR} END{exit (p)?0:1}' skills/lifecycle/references/specify.md` exits 0.

10. **Consumer-rule prose specifies three behaviors**: README.md consumer-rule section states three behaviors: (a) MUST automatic — when a skill is about to modify behavior described in any ADR, read the relevant ADRs in `cortex/adr/` first (the v1 mechanism: read the directory; without `area:` frontmatter, filtering is by title/body relevance, which a small corpus supports); (b) MUST NOT automatic — create or mutate ADRs (creation is operator- or specify-phase-mediated); (c) SHOULD surface — when a candidate change contradicts an existing ADR's decision, flag it explicitly with `contradicts ADR-NNNN — [reason worth revisiting]` rather than silently overriding. **Phase**: Mechanism. Acceptance: `grep -cE "MUST automatic|MUST NOT automatic|SHOULD surface" cortex/adr/README.md` ≥ 3.

## Non-Requirements

- **`area:` frontmatter on ADRs at v1**: explicitly out of scope. Pocock's seed ADR carries no frontmatter; the lazy-schema posture defers `area:` until ADR count + cross-cutting clustering make filtering worthwhile (~20 ADRs, per discovery DR-3's deferred-INDEX.md trigger logic).
- **Grandfathered acknowledgment + sweep ticket for existing decision-shaped content**: explicitly out of scope. Existing decision-shaped content in `docs/internals/mcp-contract.md` is intentionally co-located with the contract (extraction would harm contract readers); existing `Rationale:` clauses in area requirements docs are small enough to stay where they are. The no-duplication rule applies prospectively to new ADRs created via this mechanism.
- **MUST-escalation policy as a seed ADR**: explicitly out of scope. The policy is shape-mismatched against Pocock's decision-record format (four paragraphs of operational rules + triggers + cross-refs, not 1-3 sentences of decision + reasoning). It remains in CLAUDE.md unchanged; an ADR for it can be authored later if the policy is genuinely being changed.
- **Per-area "Related ADRs" indices in area requirements docs**: explicitly out of scope. Per discovery DR-6 and epic #221 Out-of-Scope.
- **Per-area subdirectories (`cortex/adr/{area}/`)**: out of scope. Flat-with-frontmatter per discovery DR-3; the deferred INDEX.md trigger is at ~50 ADRs.
- **Generated `cortex/adr/INDEX.md`**: out of scope at v1 (three ADRs). Deferred per DR-3 to ~50 ADRs.
- **Cadence/posture uplift in `/cortex-core:requirements` or specify.md §2 interview body**: out of scope; sibling ticket #222.
- **Project glossary at `cortex/requirements/glossary.md`**: out of scope; sibling ticket #223.
- **Pre-commit gate enforcing the three-criteria block on new ADRs**: out of scope. Prose-only enforcement with the policy doc's CLAUDE.md:58 carve-out is the v1 posture. Deferred trigger: events.log F-row evidence that authors are skirting the gate.
- **Auto-update of any backlog/lifecycle frontmatter from ADR changes**: out of scope. ADRs are append-only authorial artifacts.
- **Stating a token cap on project.md as an architectural constraint**: out of scope. The implicit budget is observable from the current project.md being terse; the ADR mechanism is justified by the cap-existence without naming a specific number.
- **Skill-side enforcement that consumers actually load `cortex/adr/README.md`**: out of scope. Trust is on PR review and on the discoverability of the policy doc when authors touch `cortex/adr/`. A later structural check (e.g., a `cortex-check-adr-consumer-rule` parity gate) is a follow-up if drift is observed.

## Edge Cases

- **Two ADRs proposed in one spec phase**: The `## Proposed ADR` section accommodates multiple proposals as sequential `### Proposed ADR: <slug>` sub-entries. The §4 `Proposed ADRs` bullet lists all slugs comma-separated.
- **Proposed ADR collides with existing ADR**: The §2 in-the-moment posture (R7) instructs the author: before drafting a new ADR, glob `cortex/adr/*.md` for titles or bodies addressing the same decision. If found, the consumer-rule "SHOULD surface" behavior fires instead (flag the proposed change as `contradicts ADR-NNNN — [reason worth revisiting]`) and no new ADR is drafted.
- **Sequential-numbering merge race**: At draft time, the §2 posture reads `cortex/adr/` directory listing, finds the highest 4-digit numeric prefix, increments by one. Two concurrent specify phases racing on `0004` is acceptable — the second to merge needs a number bump. Because the §4 consent bullet shows the slug, the user sees the number; a post-merge slug bump is treated as cosmetic and does not invalidate the spec approval (the ADR's content is what was approved, not its specific number).
- **Author skipped the three-criteria gate during §2**: The §4 `Proposed ADRs: None` line is the visible signal. The user can ask "any decision in here smell ADR-shaped?" and the author either confirms (re-runs §2 for that requirement) or affirms the empty result. This is the central non-bypass mechanism.
- **Source back-pointer line gets stale after ADR rename**: If an ADR is renamed (slug changes via supersede), the back-pointer in `cortex/requirements/project.md` goes stale. The dual-source-style enforcement is out of scope at v1; relies on PR review of the rename PR to catch back-pointer sites with a grep for `→ ADR-<old-number>`.
- **Deprecated ADR remains in the directory**: Consumer-rule prose (R10.a) instructs consumers to filter on `status: accepted` for live constraints; deprecated ADRs are history but are not deleted. The grep filter is the consumer's responsibility.

## Changes to Existing Behavior

- **ADDED**: A new top-level directory `cortex/adr/` joins `cortex/requirements/`, `cortex/research/`, `cortex/backlog/`, `cortex/lifecycle/` as a peer under the cortex umbrella.
- **MODIFIED**: `cortex/requirements/project.md:7` (CLI wheel + plugins), `:27` (File-based state), and `:28` (Per-repo sandbox registration) one-liners replaced with `→ ADR-000N` back-pointers — the paragraph rationale moves to the corresponding ADR.
- **MODIFIED**: `skills/lifecycle/references/specify.md` §2 (Structured Interview) gains a soft-positive-routing posture line for in-the-moment ADR-proposal recognition.
- **MODIFIED**: `skills/lifecycle/references/specify.md` §3 spec template gains a required `## Proposed ADR` section with "None considered." default.
- **MODIFIED**: `skills/lifecycle/references/specify.md` §4 approval surface gains a required `Proposed ADRs` bullet alongside the existing `Produced` / `Value` / `Trade-offs` bullets.

## Technical Constraints

- **File-based state only**: ADRs are plain markdown with YAML frontmatter (status only at v1). No database, no generated index at v1.
- **Pocock-stripped format**: 1-3 sentences fusing context + decision + reasoning. Optional sections (Considered Options, Consequences) included only when adding genuine value.
- **Sequential numbering**: 4-digit prefix, monotonic, never reused. Highest existing number + 1 at draft time.
- **Append-only history**: Status changes (`accepted → deprecated`, `accepted → superseded`) are the supersede mechanism. ADRs are not deleted or renumbered.
- **Sandbox allowWrite**: `cortex/` umbrella is already registered by `cortex init`; no additional sandbox config needed for `cortex/adr/`.
- **Standalone frontmatter parsing**: If any helper script reads ADR frontmatter, it uses the self-contained `_parse_frontmatter()` helper pattern from `bin/cortex-resolve-backlog-item` (no `cortex_command` package import, per install-guard discipline).
- **Consumer-rule prose discipline**: All instructions to skills about how to use the ADR log live in `cortex/adr/README.md`. No instructions duplicated into individual skill SKILL.md files. The discipline is enforced by PR review of changes to consuming skills.
- **Always-render observability**: R8 and R9 jointly mean the `## Proposed ADR` section and the `Proposed ADRs` approval bullet ALWAYS appear in every spec — "None considered." / "None" is the explicit empty state. This is the structural anchor that makes the otherwise prose-only three-criteria gate observable at the approval surface.

## Open Decisions

None at spec time.

## Proposed ADR

None considered. This spec describes the ADR mechanism itself; it does not exercise the in-the-moment posture against its own requirement decisions because the mechanism is being built, not consumed. The three seed ADRs are pre-authored synthesis from existing prose, not emitted via R7.
