# Trim Anchor Audit — `cortex/requirements/project.md`

Pre-trim enumeration of every reference to `cortex/requirements/project.md` (anchor refs `project.md#<anchor>` and named-section refs) across active source. Each row records the cited handle, source location, snippet, and preserve/relocate decision for Task 15's trim. Generated 2026-05-12 before Task 15's trim iteration begins.

## Scope of search

Active-source roots: `skills/`, `hooks/`, `bin/`, `cortex_command/`, `docs/`, `claude/`, `CLAUDE.md`, `justfile`, `tests/`, `plugins/` (auto-mirrored — informational only, the canonical source under `skills/` etc. is what is enforced).

Excluded: `.git/`, `cortex/lifecycle/requirements-skill-v2/` (this lifecycle's own working set), `cortex/lifecycle/archive/`, `cortex/research/`, `cortex/backlog/` (historical artifacts; per spec edge case for R10, the trim must preserve sections referenced by *active* skill/hook prose; archived lifecycles are not load-bearing).

## Findings

### A. Anchor references (`project.md#<anchor>`)

**None found.** No file in active source uses URL-style anchor links into `project.md`. The audit therefore reduces to named-section references.

### B. Named-section references

The following H2 sections are referenced by name (or by stable conceptual handle) in active source. These MUST remain reachable in the trimmed `project.md` — either as required H2 sections per spec, or because a downstream consumer cites them by name.

| Section / handle | Cited by | Snippet | Decision |
| --- | --- | --- | --- |
| `Overview` | `skills/critical-review/SKILL.md:37` | "extract the **Overview** section (or the first top-level summary section if none is labeled 'Overview') — up to ~250 words." | Preserve as H2 (required by spec; critical-review reads this section by name). |
| `Overview` | `skills/critical-review/SKILL.md:41` | "narrows its context to the parent `cortex/requirements/project.md` Overview only (~250 words)" | Preserve as H2 (same as above; design-choice anchor). |
| `Philosophy of Work` | `CLAUDE.md:66` | "The canonical statement of this principle [Solution horizon], and its reconciliation with the simplicity defaults, lives in `cortex/requirements/project.md` under Philosophy of Work." | Preserve as H2 AND preserve the **Solution horizon** sub-statement and its reconciliation with simplicity defaults within this section. |
| `Architectural Constraints` | spec R10 required-sections list; `cortex/lifecycle/requirements-skill-v2/spec.md:37` | "Preserve all required sections (Overview, Philosophy of Work, **Architectural Constraints**, Quality Attributes, Project Boundaries, Conditional Loading)." | Preserve as H2 (required by spec). |
| `Quality Attributes` | spec R10; also cited by example in `skills/lifecycle/references/review.md:81` ("existing section heading where the content belongs, e.g. \"## Quality Attributes\"") | "**Section**: (existing section heading where the content belongs, e.g. \"## Quality Attributes\")" | Preserve as H2 (required by spec; reviewer template uses this section name as the canonical example heading). |
| `Project Boundaries` | spec R10; spec R14 references the In Scope subsection | "In `cortex/requirements/project.md` Project Boundaries (In Scope), explicitly clarify that discovery and backlog subsystems are documented inline" | Preserve as H2 with `### In Scope` subsection (required by spec; R14/Task 20 will add the discovery/backlog inline clarification). |
| `Conditional Loading` | spec R10, R12; `skills/lifecycle/references/load-requirements.md:13` ("**Read the Conditional Loading section of `cortex/requirements/project.md`.**"); `skills/requirements/references/gather.md:45` ("populates the `## Conditional Loading` trigger table") | "Read the Conditional Loading section of `cortex/requirements/project.md`. For each tag word in the `tags:` array, check **case-insensitively** whether any Conditional Loading phrase contains that word." | Preserve as H2; this is the load-bearing section the tag-based loader reads at runtime. Phrases must remain matchable to area-doc stems (multi-agent, observability, pipeline, remote-access) per R12. |
| `skill-helper module` (Architectural Constraints sub-bullet) | `cortex_command/discovery.py:12` | "project.md L33 \"skill-helper module\" paraphrase-vulnerability threshold" | Preserve the **Skill-helper modules** bullet inside Architectural Constraints (the line number will shift after the trim but the conceptual handle "skill-helper module" must remain greppable and the bullet's intent — fusing load-bearing operations into atomic CLI subcommands — must be retained). |
| **Solution horizon** (paragraph inside Philosophy of Work) | `CLAUDE.md:66`; also referenced in spec.md:110 ("Solution Horizon compliance: v2 is grounded in evidence") | "Before suggesting a fix, ask whether you already know it will need to be redone…" | Preserve the Solution horizon paragraph inside Philosophy of Work as the canonical statement. CLAUDE.md explicitly points readers here. |
| **Workflow trimming** (paragraph inside Philosophy of Work) | No active-source cross-reference found; mentions hard-deletion preference | (internal to project.md) | Relocate to `## Optional` — no external consumer references this paragraph by name; the principle is operational guidance, not a load-bearing requirement. |
| **SKILL.md size cap / size-budget-exception** (sub-bullet of Architectural Constraints) | `tests/test_skill_size_budget.py:108` ("size-budget-exception marker is present") — enforces the rule but does not cite project.md by anchor. Spec.md:107 cites "`cortex/requirements/project.md:32`" for the 500-line cap. | "(≤500 lines per `cortex/requirements/project.md:32`)" | Preserve the size-cap bullet inside Architectural Constraints (line number will shift, but the rule's stated location in project.md must remain present). |
| **Sandbox preflight gate** (sub-bullet of Architectural Constraints) | No external cross-reference by name. Referenced indirectly via `bin/cortex-check-parity` behavior and `cortex_command/overnight/sandbox_settings.py` exists. | (internal to project.md) | Preserve the bullet inside Architectural Constraints — it's the canonical statement of the sandbox-source pre-commit gate, even though no skill/hook prose cites it by section name. |
| **Two-mode gate pattern** (sub-bullet of Architectural Constraints) | No external cross-reference by name. | (internal to project.md) | Preserve the bullet inside Architectural Constraints — same rationale: canonical statement of a structural pattern documented elsewhere only by example (`bin/cortex-check-events-registry`). |
| **Per-repo sandbox registration** (sub-bullet of Architectural Constraints) | `cortex/lifecycle/requirements-skill-v2/research.md:48` cites "Per-repo sandbox registration via fcntl.flock serialization" verbatim from project.md:30 as a spot-check. | "Per-repo sandbox registration: `cortex init` additively registers the repo's `cortex/` umbrella in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array." | Preserve the bullet — research spot-check confirms current accuracy and the CLI invocation contract (`cortex init`) is documented here. |
| **SKILL.md-to-bin parity enforcement** (sub-bullet of Architectural Constraints) | `bin/cortex-check-parity:2` ("SKILL.md-to-bin parity linter") implements the rule. | "SKILL.md-to-bin parity enforcement: `bin/cortex-*` scripts must be wired through an in-scope SKILL.md / requirements / docs / hooks / justfile / tests reference" | Preserve the bullet inside Architectural Constraints. |
| **File-based state** (sub-bullet of Architectural Constraints) | No external cross-reference by name. | (internal to project.md) | Preserve as the foundational architectural commitment; canonical statement of the no-database constraint. |
| **Graceful partial failure**, **Defense-in-depth for permissions**, **Maintainability through simplicity**, **Iterative improvement**, **Destructive operations preserve uncommitted state** (Quality Attributes sub-bullets) | No external cross-reference by name. Section header `Quality Attributes` is cited as an example reviewer-template heading (see above). | (internal to project.md) | Preserve all five bullets inside Quality Attributes — these are the canonical quality commitments. None can be safely moved to Optional without breaking the section's purpose. Tighten prose where possible but keep the bullet set intact. |
| **In Scope / Out of Scope / Deferred** (Project Boundaries subsections) | spec R14 references In Scope; research §1.2 references Out of Scope (`Published packages or reusable modules for others — out of scope`); `docs/internals/mcp-contract.md:177` quotes the Out-of-Scope line. | "Per `cortex/requirements/project.md`, cortex-command is personal tooling — \"Published packages or reusable modules for others — out of scope.\"" | Preserve all three subsections. Out-of-Scope quote in mcp-contract.md is verbatim and load-bearing. |

### C. Other plain references to `project.md` (no specific section cited)

These references mention `project.md` as a file path but do not depend on a specific section staying named. Listed for completeness:

- `skills/critical-review/SKILL.md:39` — checks for file existence, no section dependency.
- `skills/lifecycle/references/load-requirements.md:9,13,15,17,27` — references the file path and the `## Conditional Loading` section (already captured above).
- `skills/lifecycle/references/review.md:12,31,80` — references the file path for drift-update destinations.
- `skills/requirements/references/gather.md:32,77,146,200` — references file path; this file is being retired in Task 25.
- `skills/requirements/SKILL.md:9,32,51,80` — references file path; orchestrator being rewritten in Task 24.
- `cortex_command/init/tests/test_settings_merge.py`, `test_scaffold.py` — file-existence assertions on the scaffolded template; no section dependency.
- `cortex_command/init/templates/cortex/requirements/project.md` — this is the *template* shipped to new repos via `cortex init`. Out of scope for this trim; template is intentionally minimal and does not need to mirror the dev repo's `project.md` content.
- `docs/setup.md:149`, `docs/agentic-layer.md:35,129,256` — narrative references to the file path; no section dependency.
- `docs/internals/mcp-contract.md:177` — quotes the Out-of-Scope bullet verbatim (captured in named-section table above).
- `bin/cortex-requirements-parity-audit:85` — path-normalization comment; no section dependency.

## Exemption list (sections that MUST NOT move to `## Optional`)

The following sections / sub-bullets are exempted from relocation to `## Optional` because they are either spec-required H2 sections or referenced by name in active source:

1. `## Overview` (spec-required; critical-review reads it).
2. `## Philosophy of Work` (spec-required; CLAUDE.md anchors Solution horizon here).
3. **Solution horizon** paragraph inside Philosophy of Work (CLAUDE.md cites it explicitly).
4. `## Architectural Constraints` (spec-required) — **with** all current sub-bullets preserved: File-based state, Per-repo sandbox registration, SKILL.md-to-bin parity enforcement, SKILL.md size cap, Sandbox preflight gate, Two-mode gate pattern, Skill-helper modules.
5. `## Quality Attributes` (spec-required) — with all five sub-bullets preserved.
6. `## Project Boundaries` (spec-required) — with In Scope / Out of Scope / Deferred subsections. The "Published packages…out of scope" line is quoted verbatim by `docs/internals/mcp-contract.md`.
7. `## Conditional Loading` (spec-required; runtime-load-bearing for the tag-based loader).

## Sections eligible for relocation to `## Optional`

Items NOT cited by name in active source (and therefore eligible for relocation to `## Optional` as content under that H2, rather than left under their original H2):

- **Workflow trimming** paragraph (originally in Philosophy of Work).
- **Two-mode gate pattern** bullet (originally in Architectural Constraints) — no external cross-reference by name; the pattern is documented elsewhere only by example (`bin/cortex-check-events-registry`).
- **Sandbox preflight gate** bullet (originally in Architectural Constraints) — no external cross-reference by name; behavior is implemented in `bin/cortex-check-parity` and the implementation is canonical without prose duplication.

When relocated, each kept item retains its bold-prefixed name so post-trim greps for these handles still resolve against the file (just under a different H2). This is acceptable because the audit's post-trim anchor check tests handle-presence in the file, not section-association.

Remaining reductions to hit the ≤1,200 token cap come from prose tightening (collapsing redundancy, removing tutorial framing, terser bullet phrasing) — the spec-required H2 sections and externally-cited bullets remain under their original H2.

## Post-trim anchor check

After the trim, the following greps MUST each return ≥1 against the trimmed `project.md`:

- `^## Overview$`
- `^## Philosophy of Work$`
- `Solution horizon` (anywhere in the Philosophy of Work section)
- `^## Architectural Constraints$`
- `skill-helper` (Skill-helper modules bullet — case-insensitive ok)
- `size cap` OR `500 lines` (SKILL.md size-cap bullet)
- `Per-repo sandbox registration`
- `SKILL.md-to-bin parity`
- `File-based state`
- `Sandbox preflight gate`
- `Two-mode gate pattern`
- `^## Quality Attributes$`
- `Graceful partial failure`
- `Defense-in-depth`
- `Maintainability through simplicity`
- `Iterative improvement`
- `Destructive operations`
- `^## Project Boundaries$`
- `### In Scope`
- `### Out of Scope`
- `### Deferred`
- `Published packages` (verbatim Out-of-Scope quote)
- `^## Conditional Loading$`
- `multi-agent` AND `observability` AND `pipeline` AND `remote-access` (all four area-doc stems in Conditional Loading)
- `^## Optional$`

These are the load-bearing handles. Task 15's post-trim verification runs each grep against the trimmed file before declaring R10 satisfied.

A reproducible verification script is at `cortex/lifecycle/requirements-skill-v2/scripts/post-trim-anchor-check.sh` — run via `bash cortex/lifecycle/requirements-skill-v2/scripts/post-trim-anchor-check.sh` from the repo root. Exits 0 on all-pass, non-zero with a list of FAIL anchors if any handle is unresolved.
