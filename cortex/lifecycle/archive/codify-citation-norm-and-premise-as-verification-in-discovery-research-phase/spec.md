# Specification: codify-citation-norm-and-premise-as-verification-in-discovery-research-phase

> Epic reference: `research/audit-and-improve-discovery-skill-rigor/research.md` DR-1(c) Work Item #1 (Approach A). #139 is the C-half and consumes this ticket's marker format. See `lifecycle/archive/codify-citation-norm-and-premise-as-verification-in-discovery-research-phase/research.md` for investigation and cross-agent findings.

## Problem Statement

The `/discovery` research protocol does not require that codebase-pointing claims carry file:line citations, nor does it require that empty-corpus searches be reported as distinct outcomes. In the #092 incident, the synthesis author wrote "Remove 'After every 3 tool calls…' scaffolding from lifecycle/implement prompts" as an inferred locator; the ticket was decomposed, approved, and dispatched before the lifecycle research phase discovered an empty corpus. Orchestrator-review and critical-review both passed — R2's "cites specific codebase patterns" criterion is satisfied by any file-path-string appearing, not by the pattern actually occurring there. This ticket codifies synthesis-time rules requiring authors to either cite file:line evidence for codebase-pointing claims or explicitly mark them `premise-unverified`, closing the syntactic gap that let #092's inferred locator enter the artifact without challenge. The rule does not — and cannot, at the prose-only level — bind an author who mistakes an inference for grounded evidence and emits a well-formed but fabricated citation; that failure class is named explicitly in Technical Constraints as an acknowledged residual whose escalation path is a separate ticket invoking Approach F (mechanical grounding probe).

## Requirements

1. **Citation-or-marker rule added to `## Constraints` table at file bottom**. A new row is added to the existing Constraints table at `skills/discovery/references/research.md:134-138` stating: "Citations: codebase-pointing claims must carry an inline `[file:line]` citation traceable to codebase-agent findings, OR an explicit inline `[premise-unverified: not-searched]` marker when the author did not investigate the claim."
   - **Acceptance**: `awk '/^## Constraints$/{p=1; next} p && /^## /{exit} p' skills/discovery/references/research.md | grep -c "Citations"` = 1.

2. **Empty-corpus reporting rule added to `## Constraints` table**. A second new row is added stating: "Empty-corpus reporting: searches that returned no results must be reported inline as `NOT_FOUND(query=<search-string>, scope=<path-or-glob>)` — distinct from the `premise-unverified: not-searched` marker used when no investigation was attempted."
   - **Acceptance**: `awk '/^## Constraints$/{p=1; next} p && /^## /{exit} p' skills/discovery/references/research.md | grep -c "Empty-corpus reporting"` = 1.

3. **Prerequisites-retargeting instruction added to §5**. The §5 Feasibility Assessment narrative (between lines 66-73) adds an author instruction: "Prerequisites entries describing codebase-state checks (e.g., 'Identify pattern X in {file}') must be resolved during §2 Codebase Analysis — findings move to §2 with citations, or are reported as `NOT_FOUND(query, scope)`. Entries remaining in the §5 Prerequisites column are implementation-sequencing only (work to be done after the approach is committed)." The Prerequisites column structure in the template (research.md:104-107) is unchanged.
   - **Acceptance**: `grep -cF "implementation-sequencing only" skills/discovery/references/research.md` = 1.

4. **Template examples updated in §6 — demonstrate classification judgment, not just syntax**. The `## Codebase Analysis` block inside the §6 Write Research Artifact template (`skills/discovery/references/research.md:79-120`) includes at least three example bullets demonstrating: (a) a grounded claim with a `[file:line]` citation; (b) an empty-corpus finding reported as `NOT_FOUND(query=..., scope=...)`; (c) a claim that could be inferred from external endorsement without codebase evidence (the #092 pattern: a web-endorsed locator not verified in the codebase), correctly flagged with `[premise-unverified: not-searched]` rather than a fabricated citation. The third example teaches the classification heuristic the rule depends on, not merely the marker syntax.
   - **Acceptance**: `awk '/^## Codebase Analysis$/{p=1; next} p && /^## /{exit} p' skills/discovery/references/research.md | grep -cE "\[[^]]+:[0-9]+\]|NOT_FOUND\(|premise-unverified"` ≥ 3.

5. **Signal-format contract section added**. A concise format-definition section is added immediately following the two new Constraints rows (or immediately adjacent to the Constraints table), titled `### Signal formats` or inlined into the Constraints rows, defining three literal markers and their allowed values:
   - `[file:line]` — inline citation, e.g., `[skills/discovery/references/research.md:42]`
   - `[premise-unverified: not-searched]` — marker indicating the author did not attempt investigation
   - `NOT_FOUND(query=<string>, scope=<path-or-glob>)` — marker indicating a search was performed and returned no results
   This section is the stable contract #139 reads when implementing vendor-endorsement gating.
   - **Acceptance**: All three literal markers appear in research.md: `grep -c "\[file:line\]" skills/discovery/references/research.md` ≥ 1 AND `grep -c "premise-unverified: not-searched" skills/discovery/references/research.md` ≥ 1 AND `grep -c "NOT_FOUND(query" skills/discovery/references/research.md` ≥ 1.

6. **Prospective applicability — no retroactive language**. The rule text contains no retroactive-audit, migration, or backfill language. The rule applies to research artifacts produced after this edit merges.
   - **Acceptance**: `grep -cE "retroactive|retroactively|backfill|audit pass" skills/discovery/references/research.md` referring to this new rule = 0.

7. **Orchestrator-review.md unchanged**. No edits to `skills/discovery/references/orchestrator-review.md` (the ticket's synthesis-time enforcement decision means no post-hoc checklist changes).
   - **Acceptance**: `git diff main -- skills/discovery/references/orchestrator-review.md` is empty after implementation.

8. **Decompose.md unchanged**. No edits to `skills/discovery/references/decompose.md`. #139 owns the consumer-side wiring.
   - **Acceptance**: `git diff main -- skills/discovery/references/decompose.md` is empty.

9. **skills/research/SKILL.md unchanged; codebase-agent contract unchanged**. Empty-corpus reporting is enforced synthesis-side; no upstream contract changes.
   - **Acceptance**: `git diff main -- skills/research/SKILL.md` is empty; `git diff main -- skills/research/` is empty.

## Non-Requirements

- Not changing `orchestrator-review.md` R1-R5 (enforcement at synthesis surface, not post-hoc).
- Not changing `decompose.md` Value field or user-approval gate (that's #139's scope).
- Not changing `skills/research/SKILL.md` or the codebase-agent return-format contract.
- Not adding a mechanical grounding-probe tool (Approach F — deferred by epic DR-1; future recurrence triggers a new ticket).
- Not adding a new `### Research Rules` subsection under §2 (rule lives in existing `## Constraints` table per OQ4).
- Not adding a Status column to the §5 Feasibility table (markers are prose-inline per OQ1).
- Not removing the §5 Prerequisites column (retargeting is rule-level per OQ3, not structural).
- Not splitting §5 Prerequisites into multiple columns.
- No retroactive audit, migration, or backfill of the 27+ existing research artifacts.
- No tooling, lint, pre-commit hook, or CI check validating the markers — enforcement is author-side + grep-side + future-reviewer-side.
- Not defining `premise-unverified` variants beyond `not-searched` (the only variant is structural to distinguish from `NOT_FOUND`; no other categories).

## Edge Cases

- **Approach rows with no codebase premise** (e.g., "Add a new R6 post-hoc check"): §5 Prerequisites may be empty or sequencing-only. The retargeting rule is conditional on "Prerequisites describing codebase state"; no action when no such prerequisites exist.
- **Prose claim that spans multiple files**: citations may stack — `[a.py:10, b.py:42]` or separate citations per referenced file. Format remains `[file:line]`; multiplicity is author's choice.
- **Multi-agent research artifacts** (e.g., 5-agent dispatch via `/research`): each agent's output carries its own citations; synthesis author is responsible for preserving citations when composing the final artifact. The rule applies to the final synthesized artifact, not individual agent outputs.
- **Author encounters an inferred claim they genuinely believe is grounded**: residual risk (adversarial FM2/AS1, epic H3 empirical). No technical mitigation in this ticket. Future recurrence opens a new ticket for Approach F.
- **Pre-rule existing artifact, or post-rule artifact with missing markers**: downstream consumers (e.g., #139) treat absent markers as "no signal" — neither "premise-verified" nor "premise-unverified". Post-rule non-compliance (markers absent where the rule requires them) is detected by future reviewers during PR review or spot-check, not by consumers at runtime. This is the intended enforcement model given the Non-Requirement against tooling.
- **Author investigated but the result was inconclusive** (e.g., an ambiguous search hit): cite the partial evidence as `[file:line (partial)]` with a parenthetical note describing the ambiguity. The `[premise-unverified: not-searched]` marker is reserved for cases where no investigation was attempted — using it after an inconclusive search would falsify the marker's literal semantics and corrupt the signal #139 consumes. Spec deliberately avoids proliferating marker categories by routing inconclusive results back to the citation form with a caveat.
- **Claim in the Feasibility Prerequisites column that cannot be resolved during research** (e.g., depends on third-party API availability not yet checked): author resolves during §2 if possible, or records the unresolved state inline using the markers. Author is not permitted to silently leave codebase-state claims unresolved in §5.

## Changes to Existing Behavior

- **MODIFIED**: `skills/discovery/references/research.md` §2 Codebase Analysis findings now require inline `[file:line]` citations OR `[premise-unverified: not-searched]` / `NOT_FOUND(query, scope)` markers for every codebase-pointing claim. Previously: free-form prose with no content rule.
- **MODIFIED**: `skills/discovery/references/research.md` §5 Feasibility Prerequisites semantics — codebase-state checks must be resolved during §2; remaining §5 entries are implementation-sequencing only. Column structure preserved; semantics retargeted.
- **ADDED**: Two new rows in the existing `## Constraints` table at `research.md:134-138` (one for citations, one for empty-corpus reporting).
- **ADDED**: Signal-format definitions section (or inline rows) documenting three literal marker tokens — `[file:line]`, `[premise-unverified: not-searched]`, `NOT_FOUND(query, scope)` — as stable contract for #139.
- **ADDED**: Example bullets in the §6 template demonstrating marker usage.
- **ADDED**: New artifact-content vocabulary that all future /discovery research artifacts must use for codebase-pointing claims. This is a new persistent authoring obligation on research synthesizers.

## Technical Constraints

- **File-based state** (`requirements/project.md:25-26`): no schema validator; rule enforcement is author-discipline + grep-based review.
- **Symlink architecture** (project CLAUDE.md): the repo copy of `skills/discovery/references/research.md` is source of truth; symlink to `~/.claude/skills/...` updates automatically.
- **Self-enforcement residual risk** (epic H3, adversarial FM2/AS1): the synthesis author is the same agent whose inferences created #092's failure. Synthesis-time enforcement depends on the author recognizing their own inferences as inferences. Acknowledged residual; escalation path is a new ticket invoking Approach F (mechanical grounding probe).
- **Signal format is a stable contract**: after #138 merges, the three marker tokens (`[file:line]`, `[premise-unverified: not-searched]`, `NOT_FOUND(query, scope)`) are read by #139. Changing the format after merge requires coordinated updates to both tickets.
- **Lexical vs. epistemic citation density** (epic research §2 Q6): a `[file:line]` tag appearing does not mean the pattern actually exists at that location. The rule closes the specific hole where no citation appears at all; it does not mechanically verify that citations are accurate. Future reviewers may spot-check; no tooling is added here.

## Open Decisions

- None. All design questions resolved in the §2 interview (OQ1–OQ5, OQ7 via the 6-question AskUserQuestion batch; OQ6 resolved pre-interview via user confirmation to ship rule-edit at ticket scope).
