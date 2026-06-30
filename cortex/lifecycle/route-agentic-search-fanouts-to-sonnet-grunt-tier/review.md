# Review: route-agentic-search-fanouts-to-sonnet-grunt-tier

## Stage 1: Spec Compliance

### Requirement 1: `searcher` role resolves to `sonnet`, criticality-independent
- **Expected**: `cortex-resolve-model --role searcher` prints `sonnet` exit 0; same with `--criticality low`.
- **Actual**: Verified via working-tree source (`PYTHONPATH=... CORTEX_COMMAND_FORCE_SOURCE=1 bin/cortex-resolve-model --role searcher` → `sonnet`, exit 0; `--role searcher --criticality low` → `sonnet`, exit 0). `resolve_model_cli.py:130-132` emits the pinned model for any key in `_CRITICALITY_INDEPENDENT` regardless of whether `--criticality` was supplied.
- **Verdict**: PASS

### Requirement 2: Modeled as `_CRITICALITY_INDEPENDENT` constant, not a tier-keyed row
- **Expected**: `"searcher": "sonnet"` inside `_CRITICALITY_INDEPENDENT`; golden matrix set assertion unchanged (`{review, builder, orchestrator-fix, competing-plan}`).
- **Actual**: `cortex_command/lifecycle/resolve_model_cli.py:78` — `_CRITICALITY_INDEPENDENT: dict[str, str] = {"synthesizer": "opus", "searcher": "sonnet"}`. `grep -c '"searcher": "sonnet"'` = 1. `tests/test_resolve_model.py:188-193` set assertion still reads exactly `{"review", "builder", "orchestrator-fix", "competing-plan"}`, untouched.
- **Verdict**: PASS

### Requirement 3: Golden-anchor test extended for the new constant
- **Expected**: `test_searcher_is_constant_sonnet` mirroring `test_synthesizer_is_constant_opus`; `"searcher"` added to `_ALL_ROLES`; full suite exits 0.
- **Actual**: `tests/test_resolve_model.py:92-101` adds `test_searcher_is_constant_sonnet` (no-criticality, low, critical — all assert `sonnet\n`). `_ALL_ROLES` (`:33`) includes `"searcher"`. `.venv/bin/python -m pytest tests/test_resolve_model.py` → 25 passed.
- **Verdict**: PASS

### Requirement 4: The entire core wave routes to the resolved `searcher` model
- **Expected**: `skills/research/SKILL.md` Step 3 resolves `cortex-resolve-model --role searcher` in the orchestrator body and binds it as `model:` on the core-wave dispatch batch.
- **Actual**: SKILL.md:188-190 resolves `model=$(cortex-resolve-model --role searcher)` in the Step-3 body (outside any fenced agent-prompt block). §1 (`:192`) explicitly states "bind the resolved `searcher` model" and "passing the captured `$model` (sonnet) as each core-wave Agent's `model:` parameter." `grep -c 'cortex-resolve-model --role searcher' skills/research/SKILL.md` = 1.
- **Verdict**: PASS

### Requirement 5: Only the always-last adversarial wave inherits the parent — both sides witnessed
- **Expected**: §1 binds; §2 omits `model:`/inherits — both observable.
- **Actual**: §1 (`SKILL.md:192`) binds `$model`. §2 (`:193`) reads "The adversarial agent **omits** `model:` and inherits the parent — it is the error-correction layer, deliberately not routed to `searcher` (the judgment-inherit contract)." Both sides hold in both research SKILL.md and discovery's research.md (`:59`/`:60` — core binds, adversarial "**omits** `model:` and inherits the parent").
- **Verdict**: PASS

### Requirement 6: Degrade-loud-to-inherit on resolver failure — do not halt
- **Expected**: nonzero resolve → fall back to no `model:` (inherit) + one-line warning; no halt; no `MUST`/`CRITICAL`/`REQUIRED` introduced.
- **Actual**: SKILL.md:192 — "If the resolve above exited nonzero, fall back to dispatching the core wave with **no** `model:` (inherit the parent, as before) and surface a one-line warning that the gather wave is running on the inherited model because role resolution failed — do not halt." Same pattern in fanout.md:32 and discovery research.md:59. `git show 8b65e414 -- skills/research/SKILL.md | grep -E '^\+' | grep -iE 'MUST|CRITICAL|REQUIRED'` → no matches (same checked clean for the fanout.md and discovery commits). Environment fact confirmed: the installed `~/.local/bin/cortex-resolve-model` wheel rejects `--role searcher` (`invalid choice... choose from builder, competing-plan, orchestrator-fix, review, synthesizer`, exit 2) while the working-tree source resolves it — exactly the wheel-vs-mirror skew R6 is designed to degrade through. `.venv/bin/python -m pytest tests/test_resolve_model.py` exits 0 from source.
- **Verdict**: PASS

### Requirement 7: Routing lives in the shared fan-out protocol so research and discovery cannot drift
- **Expected**: rule authored in `fanout.md`; discovery's `research.md` carries a runnable resolve+bind (not a passive pointer) that doesn't contradict it.
- **Actual**: `fanout.md` `## Dispatch protocol` (`:30-37`) authors the canonical rule (§1 binds `searcher`, §2 inherits) and explicitly states "each consuming entry point ... carries its own runnable resolve + `model:` bind that follows it, because each dispatches from its own orchestrator body rather than by executing this file." Discovery's `research.md:53-60` independently resolves `model=$(cortex-resolve-model --role searcher)` in its own executed body (not inside `**Dispatch it.**`'s fenced prompts) and binds `$model` to the core wave, citing "per fanout.md's dispatch-protocol routing rule" — this is a real runnable bind, not a bare "see fanout.md" reference. `grep -c 'searcher' skills/research/references/fanout.md` = 2.
- **Verdict**: PASS

### Requirement 8: Rationale AND judgment-inherit contract recorded in sdk.md, citing ADR-0023
- **Expected**: `searcher → sonnet` rationale extending the "Parallel agents → sonnet" bullet; judgment-inherit note naming critical-review reviewers + clarify-critic; ADR-0023 cited.
- **Actual**: `docs/internals/sdk.md:149` extends "Parallel agents → sonnet" with the `searcher` rationale and cites `ADR-0023 adr/0023-route-core-research-fanout-to-sonnet-searcher-tier`. `:150` — "Judgment dispatches inherit the parent, deliberately. The research **adversarial** wave, **critical-review**'s parallel reviewers, and the **clarify-critic** are intentionally left inheriting the parent model..." `grep -c 'searcher' docs/internals/sdk.md` = 2; ADR stem cite present.
- **Verdict**: PASS

### Requirement 9: Plugin mirror regenerated in the same commit
- **Expected**: `just build-plugin` produces no diff; mirror committed alongside canonical edit.
- **Actual**: `just build-plugin` exits 0; `git status --porcelain plugins/` is empty (no residual diff). Direct diff of canonical vs. mirror for all three changed files (`fanout.md`, `skills/research/SKILL.md`, `skills/discovery/references/research.md`) against their `plugins/cortex-core/...` counterparts is byte-identical (empty `diff` output). `.venv/bin/python -m pytest tests/test_dual_source_reference_parity.py` passes (included in the 78-passed combined run below).
- **Verdict**: PASS

### Requirement 10: Research frontmatter untouched (L1 budget)
- **Expected**: `skills/research/SKILL.md` lines 1-15 byte-unchanged; `test_l1_surface_ratchet.py` exits 0.
- **Actual**: `git show 8b65e414 -- skills/research/SKILL.md` shows the only hunk touching lines 183+ (Step 3 dispatch protocol); no hunk touches lines 1-15. `.venv/bin/python -m pytest tests/test_l1_surface_ratchet.py` passes (in the combined 78-passed run).
- **Verdict**: PASS

All 10 requirements PASS. Proceeding to Stage 2.

## Stage 2: Code Quality

- **Naming conventions**: `searcher` follows the existing `synthesizer` pattern exactly — same dict, same resolution branch, same test shape (`test_searcher_is_constant_sonnet` mirrors `test_synthesizer_is_constant_opus`). Docstring `Roles:` block and argparse `help=` strings both updated to name `synthesizer, searcher` as the two criticality-independent roles. Consistent with existing module conventions.
- **Error handling**: The degrade-loud-to-inherit branch is present in all three consumer sites (`fanout.md`, research `SKILL.md`, discovery `research.md`) with consistent wording ("fall back ... no `model:` ... surface a one-line warning ... do not halt"). Confirmed soft — no `MUST`/`CRITICAL`/`REQUIRED` token introduced in any of the three feature commits touching these files (`8b65e414`, `25db4da9`). Matches the MUST-escalation policy (post-4.7 soft positive-routing default) without needing an escalation evidence artifact, since none was added.
- **Test coverage**: `.venv/bin/python -m pytest tests/test_resolve_model.py tests/test_l1_surface_ratchet.py tests/test_dual_source_reference_parity.py` → 103 passed, 0 failed. Additional lints run clean from source: `CORTEX_COMMAND_FORCE_SOURCE=1 cortex-check-skill-path --root .` exit 0; `cortex-check-contract` exit 0; `cortex-check-parity` exit 0; `cortex-adr-citation-audit` reports zero findings for ADR 23 (no `unresolved`/`slug_mismatch`/`duplicate_number`/`gap`). A full-repo `pytest -q` run shows 28 pre-existing failures, all confined to `cortex_command/dashboard/tests/test_templates.py` (template-rendering tests unrelated to model routing/research/discovery — none reference `resolve_model`, `searcher`, or `fanout`, and the changed-files list never touches the dashboard); out of scope for this feature.
- **Pattern consistency**: Single-matrix-owner held — `cortex-resolve-model` is the sole source of the `sonnet` literal; no skill hardcodes a model name. ADR-0009 body-resolution honored — the `cortex-resolve-model` calls sit in orchestrator bodies (SKILL.md:188-190, discovery research.md:55-57), never inside fenced agent-prompt blocks, and the verb is a PATH binary so `${CLAUDE_SKILL_DIR}` resolution doesn't apply. Soft phrasing maintained throughout. The wave-not-angle routing decision (R4/R5), the constant-not-row modeling (R2), and the degrade-vs-halt choice (R6) all match the spec's stated rationale and ADR-0023's trade-offs section verbatim in spirit.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

The feature adds a new model-routing surface (`searcher` role) entirely within the existing "Multi-agent: parallel dispatch, worktrees, Haiku/Sonnet/Opus selection" in-scope boundary already stated in `cortex/requirements/project.md` (Project Boundaries → In Scope), and the new architectural constraint it introduces (single-matrix-owner extension, ADR-0009 body-resolution, soft-phrasing) is governed by constraints already present in project.md (`SKILL.md L1 surface ratchet`, `Skill-dir path-resolution invariant`, `Architectural Decision Records`). No new behavior outside what's already reflected in stated requirements.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
