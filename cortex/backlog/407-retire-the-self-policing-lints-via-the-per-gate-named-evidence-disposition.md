---
schema_version: "1"
uuid: 7d3061f2-5b08-4d23-921d-3a3f2c98b8cb
title: Retire the self-policing lints via the per-gate named-evidence disposition
status: backlog
priority: medium
type: chore
created: 2026-07-21
updated: 2026-07-21
tags: ['lint', 'token-efficiency', 'cleanup']
areas: ['cli', 'skills']
---
## Why

The Architectural Constraints bullet 'Enforcement gates carry named evidence' states that a pre-commit/CI gate survives only by naming the specific, evidenced failure it prevents, and that prose-scanners, parity/citation audits, and similar self-policing lints retire, with per-gate disposition landing via a lifecycle. That disposition was never ticketed, so every named retiree is still alive and still firing — on 2026-07-21 the prescriptive-prose check blocked a backlog-ticket commit over a section-glyph citation, a live datum for the friction these gates add without a named shipped failure behind them.

## Role

One lifecycle that walks the self-policing inventory and lands a disposition per gate: retire (delete the lint, its recipe wiring, pre-commit phase, allowlist/registry files, and tests) or survive by naming the specific evidenced failure it prevents. Deletion-biased per the standing 2026-07-16 mandate: a keep must clear the same evidence bar as a new feature.

## Inventory (dispositions decided in-lifecycle, not here)

- prescriptive-prose check (pre-commit wired)
- SKILL.md-to-bin parity linter with its orphan-warning machinery and exceptions allowlist (pre-commit wired)
- events-registry staged check and its stale-deprecation audit (pre-commit wired)
- contract lint and its audit
- clarify-critic events check
- bare-python-import lint and bare-python-callsites audit
- path-hardcoding lint and audit
- ADR citation audit (report-only)
- requirements parity audit
- skill section-citations test
- skill-path lint — carries an ADR-0009 rationale and a CLAUDE.md citation; likely survivor, but it takes the same named-evidence test as the rest

## Edges

- The four named survivors in the requirements bullet (commit-message validation, worktree containment, sandbox preflight, shipped-bug regressions) are out of scope — they already carry named evidence.
- A retirement must remove the gate's full surface in one change (recipe, pre-commit phase, allowlist/registry file, tests) so nothing half-fires; the parity linter's exceptions allowlist and first-run-green test go with it if it goes.
- Gated surfaces are touched (bin scripts, hooks wiring) and the requirements clause itself mandates a lifecycle — route via /cortex-core:lifecycle.
- Some gates guard other repos' authoring flows through the plugin mirrors; confirm consumer impact per gate before deleting.

## Touch points

- cortex/requirements/project.md (Architectural Constraints, 'Enforcement gates carry named evidence')
- cortex_command/lint/{prescriptive_prose,skill_path,contract,bare_python_import,clarify_critic_events}.py, cortex_command/parity_check.py
- bin/cortex-check-* wrappers, bin/cortex-adr-citation-audit, bin/.parity-exceptions.md, bin/.events-registry.md
- justfile check-* recipes and the audit recipes (adr-citation-audit, requirements-parity-audit)
- .githooks/pre-commit Phases 1.5 (parity), 1.8 (events-registry), and the prescriptive-prose phase
- tests/test_check_*.py, tests/test_adr_citation_audit.py, tests/test_requirements_parity_audit.py, tests/test_skill_section_citations.py, tests/test_parity_contract.py