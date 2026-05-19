---
schema_version: "1"
uuid: f5b675af-6e35-4cd5-9260-b0cc7b897e47
title: "Remove daytime autonomous pipeline and cancel #228/#230"
status: refined
priority: high
type: chore
created: 2026-05-18
updated: 2026-05-19
parent: "237"
blocked-by: []
tags: [lifecycle, worktree-interactive, daytime-swap, removal]
areas: [overnight-runner]
discovery_source: cortex/research/swap-daytime-autonomous-for-worktree-interactive/research.md
session_id: null
lifecycle_phase: null
lifecycle_slug: null
complexity: complex
criticality: high
spec: cortex/lifecycle/remove-daytime-autonomous-pipeline-and-cancel/spec.md
---

## Role

Remove the daytime autonomous pipeline implementation in full. Deletes the three daytime modules, the `readiness.py` module (dead code post-removal per the corrected blast-radius analysis), six daytime test files plus the dispatch-parity test, the three console-script registrations, the daytime alternate-path block in the implement skill prose, daytime fixture/template surfaces in the dashboard, the dispatch-parity launchd justfile recipe, and references in docs, registries, `.gitignore`, `auth.py` docstrings, the `cli_handler.py` Sphinx xref, and the `pipeline/metrics.py` daytime-schema filter. Cancels tickets `#228` and `#230` with status updates pointing at this discovery as the supersedence record.

## Integration

Lands as a single atomic sweep after the new worktree-interactive option is functional and the menu has been updated (per the dependency on `#238` and `#240`). The cancellation of `#228` and `#230` happens via the backlog frontmatter helper, updating their status to `superseded` and adding a body section referencing this discovery and the parent epic.

## Edges

- Bound by the daytime-blast-radius inventory: every consumer named in the research artifact must be touched in this sweep; missing one leaves dangling references.
- Bound by the overnight-untouched contract: behavioral overnight runtime stays intact; only code-hygiene touchpoints in shared overnight modules (`auth.py` docstrings, `cli_handler.py` Sphinx xref, `pipeline/metrics.py` filter) get edited.
- Bound by the backlog frontmatter schema for the `#228` and `#230` cancellation: status update plus supersedence-record body section.
- Bound by the test-coverage-gap-avoidance constraint: the daytime tests must not be deleted until a new worktree-interactive smoke test is in place.

## Touch points

- `cortex_command/overnight/daytime_pipeline.py` — delete.
- `cortex_command/overnight/daytime_dispatch_writer.py` — delete.
- `cortex_command/overnight/daytime_result_reader.py` — delete.
- `cortex_command/overnight/readiness.py` — delete (dead code post-removal).
- `cortex_command/overnight/tests/test_daytime_pipeline.py` — delete.
- `cortex_command/overnight/tests/test_daytime_auth.py` — delete.
- `cortex_command/overnight/tests/test_daytime_result_reader.py` — delete.
- `tests/test_daytime_preflight.py` — delete.
- `tests/test_daytime_dispatch_writer.py` — delete.
- `tests/test_dispatch_parity.py` — delete.
- `cortex_command/overnight/tests/test_dispatch_readiness.py:207-301` — delete daytime-coupled integration section.
- `cortex_command/overnight/state.py` — drop `DaytimeResult` and `save_daytime_result`.
- `cortex_command/overnight/auth.py` — module/function docstrings and argparse description; daytime references.
- `cortex_command/overnight/cli_handler.py:61` — drop Sphinx xref to `daytime_pipeline._read_test_command`.
- `cortex_command/pipeline/metrics.py:324-414` — drop `_DAYTIME_DISPATCH_FIELDS` filter.
- `cortex_command/pipeline/tests/test_metrics.py:216-246` — drop corresponding test.
- `cortex_command/dashboard/data.py` — drop `parse_daytime_state`, `parse_daytime_result`.
- `cortex_command/dashboard/poller.py` — drop daytime fields and parsing.
- `cortex_command/dashboard/seed.py` — drop `write_daytime_artifacts`.
- `cortex_command/dashboard/templates/feature_cards.html` — drop daytime state/result rendering.
- `pyproject.toml:32-34` — unregister three console-scripts.
- `justfile` — drop `test-dispatch-parity-launchd-real` recipe.
- `.gitignore:31-33` — drop daytime tempfile patterns.
- `bin/.audit-bare-python-m-allowlist.md` — drop four daytime entries.
- `bin/.events-registry.md:16,118` — update producer/consumer rows.
- `docs/setup.md:121` — drop comment.
- `docs/overnight-operations.md` — drop daytime auth-resolution prose.
- `cortex/requirements/observability.md:144` — drop two daytime module references.
- `skills/lifecycle/references/implement.md` §1 (menu) and §1a (alternate path, 107 lines).
- `plugins/cortex-core/skills/lifecycle/references/implement.md` — auto-regenerated mirror.
- `cortex/backlog/228-*.md` and `cortex/backlog/230-*.md` — cancellation status updates.
