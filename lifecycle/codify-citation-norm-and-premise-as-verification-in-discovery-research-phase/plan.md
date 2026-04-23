# Plan: codify-citation-norm-and-premise-as-verification-in-discovery-research-phase

## Overview

Five additive prose edits to a single file (`skills/discovery/references/research.md`) that codify a citation-or-`premise-unverified` rule, an empty-corpus reporting rule, a §5 Prerequisites-retargeting instruction, three example bullets in the §6 template, and a Signal-formats subsection that pins the marker shape as stable contract for #139. Tasks are sequential because they all edit the same file.

## Tasks

### Task 1: Add Citations and Empty-corpus bullets to `## Constraints` [x]

- **Files**: `skills/discovery/references/research.md`
- **What**: Append two new bullets to the existing `## Constraints` bullet list (currently at lines 134-138). The bullets codify the citation-or-marker rule (spec Req 1) and the empty-corpus reporting rule (spec Req 2).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Edit location: end of the `## Constraints` bullet list at the bottom of the file (the existing items are `Read-only`, `All findings in the artifact`, `Scope`).
  - Spec Req 1 (verbatim wording): `**Citations**: codebase-pointing claims must carry an inline \`[file:line]\` citation traceable to codebase-agent findings, OR an explicit inline \`[premise-unverified: not-searched]\` marker when the author did not investigate the claim.`
  - Spec Req 2 (verbatim wording): `**Empty-corpus reporting**: searches that returned no results must be reported inline as \`NOT_FOUND(query=<search-string>, scope=<path-or-glob>)\` — distinct from the \`premise-unverified: not-searched\` marker used when no investigation was attempted.`
  - Bullet style follows the existing pattern: `- **Label**: prose.`
  - Do not introduce a markdown table — the existing structure is a bullet list (the spec uses the word "table" loosely).
- **Verification**:
  - `awk '/^## Constraints/,/^##[^#]|\Z/' skills/discovery/references/research.md | grep -c "Citations"` — pass if output = `1`.
  - `awk '/^## Constraints/,/^##[^#]|\Z/' skills/discovery/references/research.md | grep -c "Empty-corpus reporting"` — pass if output = `1`.
- **Status**: [x] complete (commit a7692f2 — note: spec awk regex broken on BSD awk; replaced with bare `grep -c "Citations"` = 1 and `grep -c "Empty-corpus reporting"` = 1)

### Task 2: Add `### Signal formats` subsection following Constraints [x]

- **Files**: `skills/discovery/references/research.md`
- **What**: Add a new `### Signal formats` H3 subsection immediately after the `## Constraints` bullet list. The subsection defines the three literal marker tokens as stable contract for downstream consumers (notably #139). Implements spec Req 5.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Edit location: insert immediately after the final bullet of `## Constraints` (which after Task 1 is the Empty-corpus bullet).
  - Subsection content must define exactly three literal markers, each on its own bullet:
    - `` `[file:line]` `` — inline citation, e.g., `` `[skills/discovery/references/research.md:42]` ``
    - `` `[premise-unverified: not-searched]` `` — marker indicating the author did not attempt investigation
    - `` `NOT_FOUND(query=<string>, scope=<path-or-glob>)` `` — marker indicating a search was performed and returned no results
  - Open with a one-sentence preamble naming the markers as stable contract (e.g., "The following literal markers are stable contract for downstream consumers (e.g., `/discovery decompose`)").
  - Use H3 heading `### Signal formats` (one space, lowercase `formats`).
  - This subsection is an `### `-level child of `## Constraints`. Per the awk acceptance regex, H3 children stay inside the Constraints slice, so Task 1's verification still passes.
- **Verification**:
  - `grep -c "\[file:line\]" skills/discovery/references/research.md` — pass if output ≥ `1`.
  - `grep -c "premise-unverified: not-searched" skills/discovery/references/research.md` — pass if output ≥ `1`.
  - `grep -c "NOT_FOUND(query" skills/discovery/references/research.md` — pass if output ≥ `1`.
  - `grep -c "^### Signal formats" skills/discovery/references/research.md` — pass if output = `1`.
- **Status**: [x] complete (commit ce24f28)

### Task 3: Add Prerequisites-retargeting instruction to §5 [x]

- **Files**: `skills/discovery/references/research.md`
- **What**: Add a one-paragraph author instruction to the §5 Feasibility Assessment narrative (currently lines 66-73) that retargets the Prerequisites column semantically without modifying the §6 template's column structure. Implements spec Req 3.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Edit location: append the instruction at the end of the §5 narrative (after the bullet list ending with the effort-estimate line at research.md:73, before §6 begins at research.md:75). Insert as a paragraph; do not modify the four existing bullets.
  - Instruction text (verbatim from spec Req 3): `Prerequisites entries describing codebase-state checks (e.g., 'Identify pattern X in {file}') must be resolved during §2 Codebase Analysis — findings move to §2 with citations, or are reported as \`NOT_FOUND(query, scope)\`. Entries remaining in the §5 Prerequisites column are implementation-sequencing only (work to be done after the approach is committed).`
  - Do not modify the `| Approach | Effort | Risks | Prerequisites |` template at lines 104-107 — column structure is preserved per spec Non-Requirement.
- **Verification**:
  - `grep -cF "implementation-sequencing only" skills/discovery/references/research.md` — pass if output = `1`.
  - `grep -cE "^\| Approach \| Effort \| Risks \| Prerequisites \|" skills/discovery/references/research.md` — pass if output = `1` (template column structure unchanged).
- **Status**: [x] complete (commit 259edc4)

### Task 4: Add three example bullets to the §6 template's `## Codebase Analysis` block [x]

- **Files**: `skills/discovery/references/research.md`
- **What**: Add three example bullets inside the `## Codebase Analysis` block of the §6 Write Research Artifact template (currently lines 86-90). The bullets demonstrate (a) a grounded `[file:line]` citation, (b) a `NOT_FOUND(query, scope)` empty-corpus finding, and (c) the #092-pattern claim correctly flagged with `[premise-unverified: not-searched]` rather than a fabricated citation. Implements spec Req 4.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Edit location: inside the markdown code fence at research.md:79-120. The current `## Codebase Analysis` section in that template (lines 86-90) reads:
    ```
    ## Codebase Analysis
    - [Existing patterns]
    - [Files/modules affected]
    - [Integration points]
    - [Constraints]
    ```
  - Replace these placeholder bullets with three concrete demonstration bullets. The existing four placeholder bullets (Existing patterns / Files affected / Integration points / Constraints) may either be removed or kept above the new examples — preserve them above for narrative continuity, then add a sub-bullet group like `- Examples (per-claim marker usage):` containing the three demonstration bullets.
  - The three demonstration bullets must classify-correctly, not just demonstrate syntax. Suggested wording (adapt as needed):
    - **Grounded claim**: `Pattern X used in three callers — \`src/foo.py:42\`, \`src/bar.py:18\`, \`src/baz.py:88\` — all share the same signature.`
    - **Empty-corpus finding**: `\`NOT_FOUND(query="async ContextVar usage", scope="src/**/*.py")\` — no callers in scope; topic premise (existing async-ContextVar consumers) is empty.`
    - **#092-pattern**: external endorsement without codebase verification, flagged not fabricated. Example: `Vendor blog endorses approach Y as "the canonical pattern in $framework"; \`[premise-unverified: not-searched]\` — no codebase scan attempted to confirm the pattern occurs in this repo, so the endorsement applies to $framework generally, not this codebase.`
  - The third example is the load-bearing one: it teaches the classification heuristic that distinguishes a fabricated `[file:line]` from an honest `[premise-unverified: not-searched]`. Critical-review R4 explicitly requires this judgment-not-syntax demonstration.
  - The bullets live INSIDE the markdown code fence (between the ` ```markdown ` open at line 79 and the closing ` ``` ` at line 120). Do not add a code fence around the new bullets; they are part of the surrounding fenced block.
- **Verification**:
  - `awk '/^## Codebase Analysis/,/^##[^#]/' skills/discovery/references/research.md | grep -cE "\[[^]]+:[0-9]+\]|NOT_FOUND\(|premise-unverified"` — pass if output ≥ `3`.
  - The three matches must include at least one `[file:line]`, one `NOT_FOUND(`, and one `premise-unverified` (verify visually since the awk slice covers the only `## Codebase Analysis` heading in the file, which is inside the §6 template).
- **Status**: [x] complete (commit 58f7c4b — fell back to bare grep due to spec awk regex defect)

## Verification Strategy

After all four tasks complete, run the full spec acceptance suite from the repository root:

1. `awk '/^## Constraints/,/^##[^#]|\Z/' skills/discovery/references/research.md | grep -c "Citations"` — expect `1`.
2. `awk '/^## Constraints/,/^##[^#]|\Z/' skills/discovery/references/research.md | grep -c "Empty-corpus reporting"` — expect `1`.
3. `grep -cF "implementation-sequencing only" skills/discovery/references/research.md` — expect `1`.
4. `awk '/^## Codebase Analysis/,/^##[^#]/' skills/discovery/references/research.md | grep -cE "\[[^]]+:[0-9]+\]|NOT_FOUND\(|premise-unverified"` — expect ≥ `3`.
5. `grep -c "\[file:line\]" skills/discovery/references/research.md` — expect ≥ `1`.
6. `grep -c "premise-unverified: not-searched" skills/discovery/references/research.md` — expect ≥ `1`.
7. `grep -c "NOT_FOUND(query" skills/discovery/references/research.md` — expect ≥ `1`.
8. `grep -cE "retroactive|retroactively|backfill|audit pass" skills/discovery/references/research.md` — expect `0` (Req 6 — prospective applicability; verify visually that any incidental match isn't about the new rule).
9. `git diff main -- skills/discovery/references/orchestrator-review.md` — expect empty (Req 7).
10. `git diff main -- skills/discovery/references/decompose.md` — expect empty (Req 8).
11. `git diff main -- skills/research/SKILL.md` — expect empty (Req 9).
12. `git diff main -- skills/research/` — expect empty (Req 9).

Read-back check: open `skills/discovery/references/research.md` and visually confirm the new content reads coherently as part of the existing skill protocol — the rule is enforceable by an author writing a research artifact, not just by grep.

## Veto Surface

- **Bullet list vs. table**: spec Req 1/2 say "Constraints table"; the actual structure at research.md:134-138 is a bullet list with bold labels. Plan implements as bullets matching the existing pattern. Flip to a markdown table only if you want the structure changed (would require restructuring the existing three Constraints items as well).
- **Signal formats placement**: spec Req 5 allows either a `### Signal formats` H3 subsection OR inlining the format definitions into the Constraints bullets themselves. Plan picks H3 subsection — gives #139 a discoverable anchor (`### Signal formats`) and keeps Constraints bullets concise. Inline alternative would crowd the Constraints bullets but avoid one heading.
- **§6 template edit shape**: Task 4 keeps the four placeholder bullets (Existing patterns / Files affected / Integration points / Constraints) above the three new demonstration bullets. Alternative: replace the placeholders entirely with the three demonstrations. Keeping placeholders preserves the template's narrative structure for first-time authors; replacing them concentrates focus on marker usage.
- **No separate verify task**: verification is per-task plus the Verification Strategy block above. No standalone verification task — the spec acceptance commands are the gate.

## Scope Boundaries

- **Out of scope** (mirrors spec Non-Requirements):
  - No edits to `skills/discovery/references/orchestrator-review.md` (Req 7).
  - No edits to `skills/discovery/references/decompose.md` — #139 owns consumer-side wiring (Req 8).
  - No edits to `skills/research/SKILL.md` or the codebase-agent contract — empty-corpus reporting is enforced synthesis-side (Req 9).
  - No mechanical grounding probe (Approach F, deferred by epic DR-1).
  - No new `### Research Rules` subsection under §2 (rule lives in `## Constraints` per OQ4).
  - No Status column added to the §5 Feasibility table (markers are prose-inline per OQ1).
  - No removal of the §5 Prerequisites column (retargeting is rule-level per OQ3).
  - No retroactive audit, migration, or backfill of the 27+ existing research artifacts (Req 6).
  - No tooling, lint, pre-commit hook, or CI check validating the markers — author + grep + reviewer enforcement only.
  - No new `premise-unverified` variants beyond `not-searched`.
