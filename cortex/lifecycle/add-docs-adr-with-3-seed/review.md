# Review: add-docs-adr-with-3-seed

## Stage 1: Spec Compliance

### Requirement 1: cortex/adr/ directory exists
- **Expected**: `cortex/adr/` created at repo root; `test -d cortex/adr` exits 0.
- **Actual**: Directory exists; `test -d cortex/adr` returned 0. Contains `README.md` plus three `000N-*.md` seed files.
- **Verdict**: PASS
- **Notes**: Phase 1 (Mechanism) artifact present.

### Requirement 2: Policy doc at cortex/adr/README.md
- **Expected**: Five sections (Purpose, Three-criteria emission gate, Frontmatter convention, No-content-duplication discipline rule, Consumer-rule prose); Purpose defends prose-only enforcement citing CLAUDE.md:58 with three sub-grounds (i–iii). Acceptance: `grep -c "^## "` ≥ 5 AND `grep -c "CLAUDE.md:58"` ≥ 1.
- **Actual**: `grep -c "^## "` = 5 (Purpose / Three-criteria emission gate / Frontmatter convention / No-content-duplication discipline rule / Consumer-rule prose). `grep -c "CLAUDE.md:58"` = 2. Purpose section enumerates all three sub-grounds verbatim: "Stray ADRs are recoverable via `status: deprecated`", "New ADRs are individually PR-reviewable", and "This README surfaces on PRs touching `cortex/adr/`".
- **Verdict**: PASS
- **Notes**: All required content present.

### Requirement 3: Three seed ADRs ship from day one
- **Expected**: `0001-file-based-state-no-database.md`, `0002-cli-wheel-plus-plugin-distribution.md`, `0003-per-repo-sandbox-registration.md` each carrying `status: accepted` in Pocock-stripped format. Acceptance: file count = 3 AND each contains `status: accepted` line.
- **Actual**: `ls cortex/adr/000[123]-*.md | wc -l` = 3. Each seed contains a `status: accepted` frontmatter line (head -10 confirmation). Bodies fuse context + decision + reasoning in a single paragraph each, with optional "Considered Options" present on 0002 and 0003 (genuine value: documents the rejected symlink-deploy and machine-wide setup alternatives).
- **Verdict**: PASS
- **Notes**: Pocock format honored; optional sections used only where they add value.

### Requirement 4: Source back-pointer edits
- **Expected**: project.md:7 → ADR-0002, :27 → ADR-0001, :28 → ADR-0003 back-pointer replacements. Acceptance: each `→ ADR-000N` substring appears ≥ 1 time.
- **Actual**: Line 7 references `(→ ADR-0002)` for CLI wheel + plugins. Line 27 reads `- **File-based state**: → ADR-0001: File-based state, no database`. Line 28 reads `- **Per-repo sandbox registration**: → ADR-0003: Per-repo sandbox registration`. Line 32 (`CLI/plugin version contract`) also back-points to ADR-0002. Grep counts: ADR-0001 = 1, ADR-0002 = 2, ADR-0003 = 1.
- **Verdict**: PASS
- **Notes**: Paragraph rationale moved to the corresponding ADR; bullet labels preserved.

### Requirement 5: Frontmatter schema (v1)
- **Expected**: Each ADR has `status: <enum>` and no `area:` field. Acceptance: each file has a matching status line AND zero `area:` lines across the three files.
- **Actual**: All three seeds carry `status: accepted`. `grep -cE "^area:" cortex/adr/0*.md` returns 0 for each of the three files. README's Frontmatter convention section documents the enum and explicitly states no `area:` at v1.
- **Verdict**: PASS
- **Notes**: Schema discipline holds at both seed-file and policy-doc level.

### Requirement 6: Promotion gate prose in policy doc
- **Expected**: README specifies proposed → accepted at PR merge. Acceptance: regex `proposed.*accepted.*merge|merge.*proposed.*accepted` matches.
- **Actual**: README contains the sentence: *"An ADR with `status: proposed` is promoted to `status: accepted` at the moment its PR is merged into `main`."* Regex matches.
- **Verdict**: PASS
- **Notes**: Promotion gate explicit.

### Requirement 7: §2 in-the-moment ADR-proposal posture
- **Expected**: specify.md §2 has a posture line citing the three-criteria gate from `cortex/adr/README.md`. Acceptance: `grep -c "three-criteria gate from .cortex/adr/README.md"` ≥ 1.
- **Actual**: Line 32 of `skills/lifecycle/references/specify.md` adds `**ADR posture (in-the-moment)**: When negotiating a requirement decision, if it meets the three-criteria gate from \`cortex/adr/README.md\` (Hard to reverse + Surprising without context + Real trade-off), draft an ADR proposal in the spec's \`## Proposed ADR\` section in the same turn rather than deferring.` Grep returns 1.
- **Verdict**: PASS
- **Notes**: Soft-positive routing language; sits alongside the existing must-have/nice-to-have probe.

### Requirement 8: Spec.md template gains always-rendered ## Proposed ADR section
- **Expected**: §3 template has `## Proposed ADR` with `None considered.` default body. Acceptance: `grep -c "^## Proposed ADR$"` ≥ 1 AND `grep -c "None considered\."` ≥ 1.
- **Actual**: Template at lines 152–158 contains `## Proposed ADR\nNone considered.` followed by an HTML comment template for per-proposal `### Proposed ADR: <NNNN-slug>` sub-entries. `grep -c "^## Proposed ADR$"` = 1; `grep -c "None considered\."` = 2 (template plus the `Proposed ADRs` bullet description that references the literal default string).
- **Verdict**: PASS
- **Notes**: Always-render observability anchor in place.

### Requirement 9: §4 approval surface always renders Proposed ADRs consent line
- **Expected**: §4 lists `Proposed ADRs` as a fourth bullet alongside `Produced`, `Value`, `Trade-offs`; defaults to `None` when empty. Acceptance: `grep -c "Proposed ADRs"` ≥ 1 AND awk verifies `Proposed ADRs` appears after `### 4. User Approval`.
- **Actual**: Line 187 reads `- **Proposed ADRs** (comma-separated `<NNNN-slug>` list from the spec's `## Proposed ADR` section; value is `None` when that section's body is `None considered.`)`. Awk exits 0 (matches after §4). Grep count = 1.
- **Verdict**: PASS
- **Notes**: Bullet is the fourth in the approval surface and correctly defaults to `None` when the spec's section reads `None considered.`.

### Requirement 10: Consumer-rule prose specifies three behaviors
- **Expected**: README enumerates MUST automatic / MUST NOT automatic / SHOULD surface. Acceptance: `grep -cE "MUST automatic|MUST NOT automatic|SHOULD surface"` ≥ 3.
- **Actual**: README §Consumer-rule prose lists all three behaviors as bold bullet labels with accompanying narrative. Grep count = 3.
- **Verdict**: PASS
- **Notes**: Behaviors mapped to accepted/proposed-or-deprecated/surfacing semantics.

## Requirements Drift
**State**: detected
**Findings**:
- A new project-level decision-recording mechanism (`cortex/adr/`) is now a peer to `cortex/requirements/`, `cortex/research/`, `cortex/backlog/`, and `cortex/lifecycle/`, with binding consumer-rule semantics (MUST automatic / MUST NOT automatic / SHOULD surface) for skills and hooks. `cortex/requirements/project.md` does not list this new artifact class or its consumer contract under Architectural Constraints, even though the spec's own `Changes to Existing Behavior` section calls out the directory as a new peer under the cortex umbrella. The repo structure section of CLAUDE.md likewise still enumerates only the older four directories under the cortex umbrella.
**Update needed**: `cortex/requirements/project.md`

## Suggested Requirements Update
**File**: `cortex/requirements/project.md`
**Section**: Architectural Constraints
**Content**:
- **Architectural Decision Records**: `cortex/adr/` holds load-bearing decisions per `cortex/adr/README.md` (three-criteria gate, prose-only enforcement, MUST/MUST NOT/SHOULD consumer rules). Skills back-point to ADRs rather than restating rationale.

## Stage 2: Code Quality

- **Naming conventions**: ADR filenames follow the `NNNN-slug.md` 4-digit-prefix pattern (`0001-file-based-state-no-database.md`, `0002-cli-wheel-plus-plugin-distribution.md`, `0003-per-repo-sandbox-registration.md`). Back-pointer bullets in `cortex/requirements/project.md` preserve their original labels (`**File-based state**`, `**Per-repo sandbox registration**`, `**CLI/plugin version contract**`) and append the `→ ADR-000N` link plus title.
- **Error handling**: N/A — docs-only changes.
- **Test coverage**: Re-ran representative acceptance commands from the spec (R1, R2, R3, R5, R6, R7, R8, R9, R10). All exit conditions match the spec's expectations. No automated test suite covers ADR shape at v1, which is consistent with the spec's Non-Requirements (no pre-commit gate on three-criteria block).
- **Pattern consistency**: Seed ADRs follow Pocock-stripped format — single paragraph fusing context + decision + reasoning. Optional `## Considered Options` appears on 0002 and 0003 where a rejected alternative carries non-trivial weight (symlink deploy, machine-wide setup script), and is intentionally omitted from 0001 where the only credible rejected alternative is "use a database", which the body covers inline. The `specify.md` edits adopt the file's existing bold-label posture-line voice (`**ADR posture (in-the-moment)**:` mirrors `**File-path citation**:`, `**Verification posture**:`, `**Edge-case invention**:` siblings) and integrate cleanly with §2/§3/§4 without disrupting the surrounding structure. The plugin mirror at `plugins/cortex-core/skills/lifecycle/references/specify.md` matches the canonical file byte-for-byte (diff empty).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
