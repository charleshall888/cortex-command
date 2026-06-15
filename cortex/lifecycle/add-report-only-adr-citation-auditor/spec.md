# Specification: add-report-only-adr-citation-auditor

## Problem Statement

ADR references rot silently: nothing checks that an `ADR-NNNN` citation resolves to a real decision record. The proven friction is in **consumer repos** that build on cortex — a consumer game project ("Wild Light") accumulated dozens of files pointing at ADRs that were never created, **plus a duplicate number**, and it surfaced only when a human happened to look. cortex's own lifecycle machinery emits 4-digit ADR references (`→ ADR-NNNN`, `### Proposed ADR: <NNNN-slug>`) into generated artifacts, so a cortex-consumer that doesn't keep its ADR corpus in sync accumulates dangling 4-digit references by construction. The value is a **report-only auditor, shipped as a CLI console-script** (so `uv tool install` puts it on a consumer's PATH alongside the plugin) that a consumer runs on their own repo and that cortex-command dogfoods — the detection/observability layer the ADR README's ratified prose-only posture explicitly calls for ("SHOULD surface"), since a blocking prevention gate is out of bounds by that same posture. It detects both defects the incident exhibited: dangling references and duplicate ADR numbers.

## Phases

- **Phase 1: Auditor core** — a `cortex_command/` module (token grammar, reference resolution, duplicate-number + gap detection, missing-corpus handling, JSON-with-`kind`-taxonomy output, exit-0-always) plus its test suite.
- **Phase 2: Integration & fold-in** — `[project.scripts]` console-script entry, a thin `bin/` wrapper, plugin-mirror regeneration, justfile recipe, `--help` smoke-test inventory, and the `cortex/adr/README.md` area-tagging reword.

## Requirements

1. **Auditor shipped as a console-script module.** New `cortex_command/adr_citation_audit.py` with a `main()` entry, registered in `pyproject.toml` `[project.scripts]` as `cortex-adr-citation-audit`, plus a thin dual-channel `bin/cortex-adr-citation-audit` wrapper (structure modeled on `bin/cortex-check-parity` → `cortex_command/parity_check.py`). Report-only: exit 0 on every path. **Acceptance:** `cortex-adr-citation-audit --help` exits 0; run against a fixture tree containing an unresolved reference → exits 0. **Phase**: Auditor core

2. **Canonical 4-digit reference resolution.** Recognizes prefix `ADR-NNNN`, bracketed `[ADR-NNNN]`, space `ADR NNNN`, and path `adr/NNNN[-slug]` (`NNNN` = exactly four digits), resolving each against the target repo's filed ADRs (`<root>/cortex/adr/NNNN-*.md`, matched by `^[0-9]{4}-[a-z0-9-]+\.md$`, `README.md` excluded). Slug-less forms resolve by numeric prefix; path-with-slug resolves by exact `NNNN-slug` filename match. Right-boundary is `(?![0-9A-Za-z])`. **Acceptance:** a fixture with `ADR-0001` (filed) → no finding; `ADR-9999` (unfiled) → a finding with `kind: "unresolved"`; `adr/0001-wrong-slug` where `0001`'s real slug differs → a finding with `kind: "slug_mismatch"`. **Phase**: Auditor core

3. **Document-local labels and placeholders are not flagged.** Non-4-digit `ADR-N` (1–3 digit document-local proposal labels, e.g. `ADR-1`/`ADR-2`/`ADR-3` as used in `cortex_command/init/settings_merge.py`), `ADR-000N`, and `NNNN-` template placeholders are never reported. **Acceptance:** a fixture containing `ADR-2`, `ADR-000N`, and `NNNN-slug` produces zero findings for those tokens. **Phase**: Auditor core

4. **Repo-agnostic within the cortex convention.** Defaults to the current working directory, accepts `--root <dir>` to target any repo, and resolves references against `<root>/cortex/adr/`. The auditor targets repos following cortex's ADR convention (4-digit zero-padded `NNNN-slug.md` under `cortex/adr/`) — which every cortex-consumer is, since cortex's own machinery emits 4-digit references. **Acceptance:** run with `--root <synthetic cortex-convention tmp tree>` (no `plugins/`, no cortex-command layout) containing `cortex/adr/0001-foo.md` and a doc citing `ADR-0001` and `ADR-0002` → exits 0, `ADR-0002` reported `kind: "unresolved"`, `ADR-0001` not reported. **Phase**: Auditor core

5. **Missing-corpus handling.** When `<root>/cortex/adr/` is absent or empty while ADR references exist, the JSON output carries top-level `corpus_present: false` and every reference is reported as `kind: "unresolved"` — this is the actual consumer-repo (Wild Light) scenario. **Acceptance:** run against a tmp tree with ADR references but no `cortex/adr/` dir → exits 0; output JSON has `corpus_present` = `false` and the references appear in the findings as `kind: "unresolved"`. **Phase**: Auditor core

6. **Duplicate-number detection.** Two or more filed ADR files sharing the same `NNNN` prefix are reported as a finding with `kind: "duplicate_number"` naming the colliding files. This rides the number→files index the resolution step already builds. **Acceptance:** a fixture with `cortex/adr/0001-a.md` and `cortex/adr/0001-b.md` → a finding with `kind: "duplicate_number"` naming both files. **Phase**: Auditor core

7. **Gap detection.** A missing number in the `1..max(filed)` sequence is reported with `kind: "gap"`, framed as an "unaccounted" gap (report-only — a deliberately deleted/superseded-and-removed ADR is a legitimate gap a human adjudicates, not an error). A superseded-but-present ADR file is NOT a gap. **Acceptance:** a fixture with `0001`, `0002`, `0004` filed (`0003` absent) → a finding with `kind: "gap"` for `0003`; a fixture where `0002` is present with `status: superseded` → no gap finding for `0002`. **Phase**: Auditor core

8. **JSON report contract with finding taxonomy.** Output is a single JSON object on stdout, documented in a `# Contract` docblock in the module. Each finding carries a `kind` ∈ {`unresolved`, `slug_mismatch`, `duplicate_number`, `gap`}; the top level carries `corpus_present`. Exit code is 0 on every path. **Acceptance:** `cortex-adr-citation-audit --root <fixture> | python3 -m json.tool` exits 0; the module source contains a `# Contract` block enumerating the four `kind` values. **Phase**: Auditor core

9. **Test suite.** `tests/test_adr_citation_audit.py` exercises requirements 2–7 via subprocess + `--root <tmp tree>` (model: `tests/test_requirements_parity_audit.py`), with fixtures under `tests/fixtures/cortex-adr-citation-audit/` — a path the auditor's default/dogfood scan excludes. **Acceptance:** the test file's tests pass under `just test`. **Phase**: Auditor core

10. **Console-script wiring + parity + plugin mirror.** The `[project.scripts]` entry is added; the `bin/` wrapper is wired through a `justfile` recipe (satisfies W003) and added to the `--help` smoke-test inventory at `tests/test_phase1_sibling_rewrite_smoke.py:45`; `plugins/cortex-core/bin/cortex-adr-citation-audit` is regenerated via `just build-plugin` and committed with the canonical. **Acceptance:** `bin/cortex-check-parity` reports no W003 orphan for the wrapper; `tests/test_plugin_mirror_parity.py` passes; `cortex_command/dashboard/tests/test_routes_smoke.py` / the fresh-resolve install path still resolves the new console-script. **Phase**: Integration & fold-in

11. **README:45 area-tagging reword.** Reword the `cortex/adr/README.md:45` note to drop the broken "deferred to a backfill ticket" promise (the backfill was deliberately not filed per epic 303; `area:` has no consumer) while keeping the still-live "do not invent one ad hoc" guardrail — e.g. *"No `area:` field is defined. Area tagging was considered and deliberately not adopted (no consumer); do not invent one ad hoc."* This is an operator-approved, intentional narrowing of the ticket's literal "delete the note" wording (the guardrail clause is independently useful). **Acceptance:** `grep -c 'backfill ticket' cortex/adr/README.md` = 0 AND `grep -c 'do not invent' cortex/adr/README.md` ≥ 1. **Phase**: Integration & fold-in

## Non-Requirements

- **No proposals sub-mode (cut from v1, deferrable).** Reconciling `### Proposed ADR:` spec entries is cut. In cortex-command the only non-resolving entries are renumbered-during-review proposals correctly filed under other numbers, living in immutable archived specs → permanent un-clearable noise. In a *consumer* repo a never-filed proposal could be genuine signal, so this is a candidate for a future iteration scoped to active (non-archived) lifecycles — not a permanent rejection.
- **No next-free-number allocator** (the ticket's explicit non-goal); the read-side gap/duplicate detectors cover the real risk.
- **No blocking gate.** Report-only only; never fails a commit. A blocking ADR gate contradicts the ADR README's ratified prose-only posture and is out of scope unless a maintainer overturns that rationale.
- **No ADR content, status-transition, or supersession-chain validation** — those remain human-reviewed.
- **No `--adr-dir` override.** The corpus path defaults to `<root>/cortex/adr/` (cortex convention); a non-standard location override is YAGNI until a consumer needs one.
- **Not numbering-convention-agnostic.** The 4-digit grammar assumes cortex's zero-padded `NNNN` convention (correct for cortex-consumers, whose references are cortex-generated). A repo using a different ADR convention (e.g. adr-tools 1–3-digit numbering) is out of scope.
- **No emission-side prevention** (e.g. blocking lifecycle-complete on an unfiled proposed ADR, or scaffolding a consumer ADR corpus on `cortex init`). That deeper prevention root fix is a separate, larger concern likely conflicting with the prose-only posture.

## Edge Cases

- **Document-local proposal labels in shipped code**: `ADR-1`/`ADR-2`/`ADR-3` in `cortex_command/init/{settings_merge.py,handler.py}` and archived specs → not flagged (4-digit discriminator; no directory carve-out needed).
- **Reference to a superseded-but-present ADR** (`ADR-0006`, superseded_by 0008, file present): resolves cleanly (supersession validation out of scope) and is NOT a gap.
- **Gap from a deliberately deleted/superseded-and-removed ADR**: reported `kind: "gap"` as "unaccounted" — report-only, a human adjudicates; not an error.
- **Self-reference / fixtures**: the auditor's own deliberately-dangling fixtures live under `tests/fixtures/cortex-adr-citation-audit/`, excluded from the default/dogfood scan, so cortex-command's own run does not flag them.
- **Generated mirror (cortex-command only)**: the default scan excludes generated mirror trees where present (`plugins/cortex-core/**` in cortex-command); consumer repos have no such tree.
- **`.py` string-literal example tokens**: a 4-digit `ADR-NNNN` inside an illustrative Python string could be matched; accepted as a minor false-positive surface for a report-only tool (word-boundary anchoring keeps it rare).

## Changes to Existing Behavior

- **ADDED**: a new CLI console-script `cortex-adr-citation-audit` (reaches consumers via `uv tool install`; the SessionStart PATH bootstrap already exposes `~/.local/bin`), dogfooded in cortex-command via a justfile recipe.
- **ADDED**: a new `[project.scripts]` entry, a `bin/` wrapper, and its plugin-`bin/` mirror.
- **MODIFIED**: `cortex/adr/README.md` area-tagging note reworded (broken backfill-ticket promise removed; guardrail kept).

## Technical Constraints

- Structure modeled on `cortex-check-parity` (thin dual-channel `bin/cortex-check-parity` wrapper → `cortex_command/parity_check.py` module + `[project.scripts]` entry). Report-only output discipline (JSON-to-stdout, `# Contract` docblock, **exit 0 on every path**, `cortex-log-invocation` shim in the wrapper) modeled on `bin/cortex-requirements-parity-audit`.
- **Distribution to consumers is via the `[project.scripts]` console-script** (`uv tool install` lands it on PATH; the SessionStart bootstrap prepends `~/.local/bin`). The `bin/` wrapper additionally mirrors to `plugins/cortex-core/bin/` — commit canonical + mirror together (drift pre-commit hook + `tests/test_plugin_mirror_parity.py` enforce byte-parity).
- Token grammar (from research): prefix/space/bracketed `(?<![0-9A-Za-z])\[?ADR[- ](?P<num>[0-9]{4})\]?(?![0-9A-Za-z])`; path `(?<![0-9A-Za-z])adr/(?P<num>[0-9]{4})(?:-(?P<slug>[a-z0-9-]+?))?(?=\.md|[^a-z0-9-]|$)`.
- Scan scope: source text files under `<root>` (at minimum `.md` and `.py`, where references demonstrably appear per the discovery), excluding `.git/`, `tests/fixtures/cortex-adr-citation-audit/`, and generated mirror trees (`plugins/cortex-core/**`) where present. Exact extension set is a thin implementation detail for the plan.
- ADR corpus assumption: `<root>/cortex/adr/`, 4-digit zero-padded `NNNN-slug.md`, `README.md` excluded. This is cortex's convention — honest scoping, not a repo-universal claim.
- No events-registry entry (emits no event; the ticket's "any event it emits registers" is satisfied vacuously).
- Tests should invoke the working tree (`python3 -m cortex_command.adr_citation_audit`); the editable install also points the `cortex-adr-citation-audit` console-script at the working tree (per the wheel-binstub vs working-tree constraint in `project.md`).
- Editing `cortex_command/`, `bin/cortex-*`, `pyproject.toml`, and `cortex/adr/README.md` requires the lifecycle (this work); the justfile/test/mirror edits ride along.

## Open Decisions

None — all open questions are resolved: structural home (console-script), numbering checks (restore duplicate + gap), and the README:45 reword were decided by the operator; token grammar, scan scope, supersession semantics, finding taxonomy, and naming were resolved in research and critical review.

## Proposed ADR

None considered.
