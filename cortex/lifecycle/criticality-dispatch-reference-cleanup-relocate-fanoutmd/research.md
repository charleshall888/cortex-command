# Research: cortex-resolve-model verb + criticality/dispatch reference cleanup (#334)

**Clarified intent:** Introduce a `cortex-resolve-model` CLI verb that owns the deterministic *(role, criticality) → model* lookup (the LLM keeps the tier/role judgment and passes it in; the verb returns the model name), migrate the inline model-directive sites to defer to it, relocate the research-shared `fanout.md` out of `skills/lifecycle/references/`, move the staleness-prone rationale prose out of `model-selection.md`, and delete the `criticality-matrix.md` line-24 narration — while preserving the deliberate role-threshold difference and the behavior matrix itself.

**Tier:** complex · **Criticality:** high

> **Headline correction from the adversarial pass:** there is **no inline drift today** — all six live directive sites match the canonical Lifecycle Matrix exactly. The ticket's framing ("two silent variants") describes a *deliberate role difference*, not a bug. This verb is therefore **preventive single-sourcing**, not a corrective fix. That reframes its value (and is honest input to the spec/value gate).

---

## Codebase Analysis

### Verified grounding
- `skills/lifecycle/assets/model-selection.md` holds **two different-axis tables** — **Lifecycle Matrix** (task-type/role × criticality, lines 11–20) and **Pipeline Matrix** (complexity × criticality, lines 22–30) — plus **Model Profiles** (32–54) and **Design Rationale** (56–62). It has **zero live path citations** (confirmed; only sibling-doc prose cross-links reference it). It never functioned as a dedup *source* because nothing dereferences it.
- The **Pipeline Matrix already exists as code**: `resolve_model(complexity, criticality)` at `cortex_command/pipeline/dispatch.py:218` (backed by `_MODEL_MATRIX`, lines 136–149) — public, tested (`cortex_command/pipeline/tests/test_dispatch.py`), raises `ValueError` on bad input, returns short names, imported in-process by `retry.py`/`runner.py`. `docs/internals/sdk.md:60–68` already documents this matrix (so `model-selection.md`'s Pipeline Matrix is a **stale duplicate** of code+sdk.md).
- The **Lifecycle Matrix lives only as prose** (model-selection.md + the inline copies) — it has **no Python home**.

### The inline model-directive sites (canonical paths; each auto-mirrors to `plugins/cortex-core/...`)
| Site | Directive | Role | Class | Matches canon? |
|---|---|---|---|---|
| `skills/lifecycle/references/review.md:18` | sonnet ≤medium, opus high/critical | review | tier-keyed | ✓ (Review row) |
| `skills/lifecycle/references/orchestrator-review.md:46` | sonnet ≤high, opus critical | orchestrator-fix | tier-keyed | ✓ (Orchestrator-fix row) |
| `skills/lifecycle/references/implement.md:224` | sonnet ≤medium, opus high/critical (crit from events.log) | builder | tier-keyed | ✓ (Builder row) |
| `skills/lifecycle/references/plan.md:28` | sonnet (critical-gated) | competing-plan | static (critical-only) | ✓ (Competing-plan row) |
| `skills/lifecycle/references/plan.md:79` | opus | plan-synthesizer | **constant, no matrix row** | n/a |
| `skills/critical-review/SKILL.md:76` | opus | synthesizer | **constant, no matrix row** | n/a |

Non-migration surfaces among the "~9 sites": `critical-review/references/synthesizer-prompt.md:1` is a **document title**, not a directive; `critical-review/references/verification-gates.md:44` (`--model-tier`) is the **existing precedent** (LLM passes a tier *into* a telemetry CLI), not a chooser; `criticality-matrix.md:19–22` is a **4th duplicate** of the routing column; `model-selection.md` is the data source.

### `criticality-matrix.md:24` narration (to delete — pure self-narration, no test pins it)
> "All three tickets (023, 024, 025) are implemented. The Review phase column reflects tier-based skip logic … The Model selection column reflects which models are used at each criticality level."

### New verb landing site & existing resolver-verb patterns
- New pure module + thin CLI (see CLI section for the placement decision). Console-script in `pyproject.toml [project.scripts]`; binstub `bin/cortex-resolve-model` (4-branch dual-channel wrapper; `bin/cortex-resolve-backlog-item` is the exact template). Auto-mirrors to `plugins/cortex-core/bin/` via `just build-plugin`.
- Family precedent: `cortex-read-backlog-backend` (`cortex_command/lifecycle/backlog_backend_cli.py`), `cortex-lifecycle-state` (`state_cli.py`), `cortex-resolve-backlog-item` (`backlog/resolve_item.py`), plus `cortex-lifecycle-dispatch-choice` / `cortex-complexity-escalator` — the "deterministic decision pulled out of prose" family this verb joins.

### Integration & guardrail surfaces
- **Mirrors**: `just build-plugin` rsyncs `skills/` (lifecycle, research, discovery, critical-review) and `bin/cortex-*` into `plugins/cortex-core/`. Moved/deleted files propagate (rsync `--delete`). Commit canonical + mirror **together** (pre-commit drift hook).
- **Tests touched**: `tests/test_research_fanout_matrix.py:22` hardcodes `skills/lifecycle/references/fanout.md` (**must repoint**); `tests/test_dual_source_reference_parity.py` (byte-parity, globs `skills/*/references/*.md` + `assets/*.md`); `tests/test_lifecycle_references_resolve.py` (broken-link checker — flags dangling fanout refs in lifecycle files); per-verb parity-test convention (`test_cortex_*_parity.py`).
- **ADR siting** (if used): next number is **0017**.

---

## Web Research

The design is well-supported prior art on every axis:
- **LiteLLM `model_alias_map` / `model_group_alias`** — logical-name → concrete-model indirection so models swap in one config location. Direct analog to the verb's table.
- **Claude Code subagents** — `model` frontmatter (`sonnet`/`opus`/`haiku`/`inherit`) resolved via a deterministic precedence chain; recommended tier-by-role (opus=reasoning/synthesis, sonnet=implementation, haiku=lookups). A community repo's "all 13 agents use opus despite CONTRIBUTING recommending sonnet" issue is the *scattered-hardcoding drift* failure mode this work pre-empts.
- **CrewAI / LangChain** — per-role model in YAML config / `init_chat_model` + provider profiles; model choice is a declarative config concern separate from the behavioral prompt.
- **LLM routers/gateways** — tier/criticality → model is the dominant production pattern (~40–70% cost savings at <2% quality loss); guidance is to route in one table rather than "hunting hardcoded model names through code." The proposal sits on the simpler, more auditable **deterministic-mapping** end (vs a learned router).
- **Mechanism/policy separation (UNIX "Rule of Separation")** + **single-source-of-truth** map cleanly: LLM's tier/role assessment = policy (stays with agent); (role,criticality)→name lookup = mechanism (centralized, testable).
- **Anti-patterns to heed**: "duplication is cheaper than the wrong abstraction" / AHA / Rule of Three (don't over-parameterize the key space prematurely); indirection cost; god-object risk (keep the resolver a thin lookup, not a criticality-assessor); centralized routing tables drift toward rigidity. Provide a deferred-binding/override path (cf. LiteLLM aliases, Claude env-var precedence).

---

## Requirements & Constraints

- **Model selection is in-scope and split across two requirement docs**: `cortex/requirements/multi-agent.md:54–65` owns the **pipeline** matrix (complexity × criticality; escalation ladder "fixed: haiku → sonnet → opus, no downgrade", :78); `pipeline.md:166` consumes it. The **skill-side Lifecycle Matrix** is what the verb owns.
- **Skill-side vs SDK-side is a documented, owned boundary**: `docs/internals/sdk.md` owns SDK model-selection mechanics (CLAUDE.md). SDK-side (Path B) is **already Python-resolved** (`dispatch.py`). The verb is bounded to the **skill-side Lifecycle Matrix** — it must not absorb the pipeline path.
- **Parity (`bin/cortex-check-parity`)**: a `[project.scripts]` entry counts as a deployed command → an unwired `cortex-resolve-model` trips **W003 orphan** (failing, non-lenient at pre-commit). Wiring = a prose/inline-code/fenced mention in an in-scope file (`skills/**/*.md`, `docs/**/*.md`, `cortex/requirements/**`, `justfile`, `tests/**`). **A flat matrix-table cell does NOT count** (R6 narrowing). The migrated `cortex-resolve-model` mentions in `skills/lifecycle/references/*.md` satisfy it → **no `.parity-exceptions.md` row needed**.
- **Console-script idiom + L201**: the verb must be a `cortex_command/<…>.py` module with a `[project.scripts]` entry; migrated sites invoke the **console script**, never bare-Python `import` (L201 / `cortex-check-bare-python-import`). This is exactly L201's prescribed remediation.
- **ADR-0009 / SP001-SP002**: a console-script call carries no path → no `${CLAUDE_SKILL_DIR}` resolution needed at call sites (clean). ADR-0009 *sanctions* the CLI mechanism for cortex-coupled skills (lifecycle qualifies). The `fanout.md` repoints keep the body-resolve-then-propagate discipline.
- **L1 surface ratchet**: triggered **only if** a SKILL.md `description`/`when_to_use` changes. The work is reference/asset-file body edits → not triggered — **except** touching `critical-review/SKILL.md` body would re-engage it (a scope nuance; the synthesizer site there is in a SKILL.md, not a reference file).
- **Events-registry**: a pure resolver emits no events → **no `bin/.events-registry.md` row**.
- **ADR no-duplication / What-not-How**: rationale prose's home is governed by the 3-criteria ADR gate and the "back-point, don't restate" rule (see Tradeoffs + Adversarial — verdict is **sdk.md, not a new ADR**).
- **Solution-horizon**: the "named multiple sites that duplicate one source" case justifies durable centralization over per-site edits (the user's explicit "trim fat via CLI verbs" framing).
- **Contract checker (E101/E103)**: `cortex-resolve-model` prose mentions must include the required flags (`--role`, `--criticality`; `{placeholder}` values OK) or they fail E101/E103.

---

## Tradeoffs & Alternatives

**Fork 1 — one verb spanning both matrices, or lifecycle-only?** → **Lifecycle-only.** Pipeline callers are in-process Python; routing them through a CLI adds subprocess/interpreter latency for zero prose consumers (a `--matrix=pipeline` mode would have no users). Authority boundary stays clean: code owns pipeline, verb owns lifecycle. (See Adversarial: the two matrices are **structurally unmergeable**, which kills even the "co-locate in one module" option.)

**Fork 2 — RUN the verb vs cite it as canonical reference?** → **RUN it.** The cite-and-keep-inline approach already failed (model-selection.md, zero citations, values stayed correct only by discipline). Only runtime computation enforces single-source for a prose-to-LLM consumer. **But** the adversarial pass surfaced a real counter (run-discipline "double-pointer") — see Open Questions; this is the central design decision for spec.

**Fork 3 — rationale-prose destination?** Two content kinds are tangled: (1) **durable design rationale** (why parallel→sonnet, exploration→haiku, complex+low/med→sonnet, reviews-follow-criticality) — version-agnostic; (2) **version-pinned facts** (SWE-bench/GPQA %, $/MTok, "Sonnet 4.6") — already stale and unmaintained. Recommendation: durable rationale → `docs/internals/sdk.md` (the declared owner) + a load-bearing comment in the verb module; **delete** the version-pinned numbers (preserved in `cortex/research/opus-4-7-harness-adaptation/`); collapse sdk.md's duplicated Pipeline Matrix to a code back-pointer. (Adversarial overrode the Tradeoffs agent's "new ADR" idea — see below.)

**Fork 4 — output/error contract?** → Bare short model name on stdout, exit 0; **no safe default** (a default silently masks a typo'd role — the exact silent-wrong-value class this verb exists to kill); exit 2 + stderr naming valid values on unknown role/criticality (matches `resolve_model`'s `ValueError` + the repo's fail-loud posture). Optional `--json`. (Adversarial: the "distinct exit for `—` cells" is dead code — those cells are unreachable behind an upstream gate; and hard-fail needs a prose handler — see Open Questions.)

**Rejected alternative re-check (no verb; fix-in-place + parity test):** genuinely cheaper for the *drift symptom alone* — and since **there's no drift today**, a parity test asserting inline==canonical would lock correctness at commit time with zero runtime cost (the repo already uses this device, `tests/test_lifecycle_kept_pauses_parity.py`). The verb still wins **only on the larger goals** (runtime single-source + completing the resolver-verb family + removing the literals entirely), not on fixing a present bug. This honest framing belongs in the spec value gate.

---

## Migration & Call-Site Semantics

- **Caller-resolves invariant holds at every live site**: the orchestrator/main agent reads the directive while composing the `Agent()`/Task call; the model is an argument to that call. No sub-agent picks its own model (proof: `synthesizer-prompt.md` names no model — the caller picks opus at `SKILL.md:76` and dispatches the prompt *to* that agent).
- **At resolve-time there is almost no live judgment**: *role* is positional (fixed by which file/site the orchestrator is in), *criticality* is a deterministic state read (`cortex-lifecycle-state --field criticality`, assessed back in Clarify). So the verb owns essentially the whole **dispatch-time** decision; the genuine judgment lives upstream at Clarify.
- **The load-bearing discriminator**: `review@high → opus` vs `orchestrator-fix@high → sonnet` — same criticality, different model because the role differs. This proves `--role` is **mandatory** and is the one cell where two roles disagree at the same criticality. **Lock it with a regression test.**
- **Canonical replacement pattern** (lint-clean — L201/SP001-SP002/E101 all satisfied): the prose instructs the orchestrator to read criticality then `cortex-resolve-model --role review --criticality {criticality}` and pass the returned name as the sub-task model; **inline the command, never a model literal** (a literal recreates the drift surface).
- **Scope of genuinely-migratable sites = the 4 criticality-varying role rows**: review, builder, orchestrator-fix, competing-plan. (See Adversarial for why synthesizers and orphan rows are excluded.)

---

## CLI-Verb Construction & Guardrails

- **Module shape**: a **pure, stdlib-only lifecycle-matrix module** + thin CLI (`main(argv)` + `_build_parser()`), mirroring `backlog_backend_cli.py` / `state_cli.py`. **Do not import from `dispatch.py`** (it drags in `claude_agent_sdk`) and **do not extract/co-locate the pipeline matrix** (adversarial: unmergeable + touching `dispatch.py` risks the retry escalation ladder and triggers the editable-install caveat). Build the lifecycle matrix fresh; leave `dispatch.py` untouched.
- **argparse**: `--role` (choices from a module-level tuple) + `--criticality {low,medium,high,critical}`, both `required=True`. stdout = bare model name + newline. Exit 0 success / 2 unknown-or-missing.
- **Wiring**: `pyproject.toml [project.scripts]` line + `bin/cortex-resolve-model` (copy `bin/cortex-resolve-backlog-item` template; swap module path; `chmod +x`; `cortex-log-invocation` header). Parity satisfied by the in-prose verb mentions at the migrated sites. No events-registry row.
- **Tests** (pattern: `test_dispatch.py::test_effort_matrix_policy` + `test_backlog_backend_cli.py`): (a) **table-coverage** — every (role,criticality) cell returns the documented model; (b) **markdown↔Python source-of-truth** test — parse the surviving canonical table (in sdk.md) and assert == the Python matrix so prose and verb can't drift; (c) **negative** — unknown role/criticality → exit 2 + stderr; (d) **regression** — `review@high→opus` AND `orchestrator-fix@high→sonnet`. Invoke in-process via `main([...])` (the PATH command isn't live until the editable wheel reinstalls).
- **Mirror/wheel ordering**: edit canonical → `just build-plugin` → stage canonical + regenerated mirror together → commit (explicit pathspec if a concurrent session is live). Editing `cortex_command/` means **sequential dispatch, not worktree** (`just test` runs the editable install). Use `python3 -m` / `CORTEX_COMMAND_FORCE_SOURCE=1` for same-session verb invocation before reinstall.

---

## fanout.md Relocation & Coupling

- **Home: `skills/research/references/fanout.md`** (the ticket's choice, validated). It cuts the *operative* cross-skill Read paths from 4 (research ×3 + discovery ×1) → 1 (discovery ×1): research becomes own-dir, zero cross-skill reach — and research is the heaviest, only operative-Read consumer. The residual is cheap (discovery's reach merely flips lifecycle→research; lifecycle's two pointers are non-operative "see" citations). No neutral/shared home exists by design (ADR-0009 rejected a standalone shared dir). #328 is the concrete repoint template.
  - *Honest caveat (adversarial):* this **shifts** cross-skill burden onto lifecycle's prose pointers rather than eliminating it globally — but it moves the expensive (operative) coupling off the owner.
- **Citers to repoint (7 files + 1 test)**: `research/SKILL.md` (L49/67/184 → `${CLAUDE_SKILL_DIR}/references/fanout.md`; L71/227 bare nouns unchanged); `discovery/SKILL.md:75` → `${CLAUDE_SKILL_DIR}/../research/references/fanout.md`; `discovery/references/clarify.md:61` (+:65 prose unchanged); `discovery/references/research.md:41` (+:43/:53 bare unchanged); `lifecycle/references/criticality-matrix.md:26` → bare noun "see fanout.md" (#328 form); `lifecycle/assets/model-selection.md:58` (**gated on the deletion decision** — disappears if deleted); `docs/agentic-layer.md:121`; and `tests/test_research_fanout_matrix.py:22` (hardcoded path const — **must update**). All repoints verified lint-clean per SP001/SP002; current tree is `cortex-check-skill-path --audit` clean (any regression would be newly introduced).

---

## Adversarial Review

- **Drift-contradiction verdict — the Tradeoffs agent was WRONG.** File evidence: `review.md:18` exactly matches the canonical Review row (`sonnet|sonnet|opus|opus`); `orchestrator-review.md:46` exactly matches the Orchestrator-fix row (`sonnet|sonnet|sonnet|opus`). The Tradeoffs agent conflated the two rows. Its proposed "fix" (review opus@high → sonnet) would inject a behavior regression and destroy the very role-threshold difference the ticket says to preserve. **The migration must NOT touch `review.md:18`. No real inline drift exists among the live sites.**
- **Synthesizer-as-matrix-row is actively harmful.** A criticality-independent constant can't drift, so a verb call buys zero single-source value; encoding `synthesizer→opus` as a *row* invites a future editor to "fill in" empty low/medium/high cells with different values — manufacturing the drift it claims to prevent. **Keep synthesizer `opus` inline with a one-line rationale comment.** (This refutes the Migration agent's "missing synthesizer row = gating blocker" — the right remedy is *don't make it a row*.)
- **Two matrices are structurally unmergeable.** Orchestrator-fix's `sonnet|sonnet|sonnet|opus` is unrepresentable in the pipeline matrix's rows. Confirms lifecycle-only scope; confirms leave `dispatch.py` alone.
- **Orphan rows have no call-site.** `research/SKILL.md` dispatches research/exploration agents with **no model pin** today. Wiring "exploration"/"parallel-research" into the verb would **ADD** pins where none exist — a silent behavior change, not a migration. Leave them out unless adding pins is a deliberately-justified decision.
- **Deletion omissions**: `criticality-matrix.md:19–22` is a **4th copy** of the routing policy that must be reconciled in the same change; deleting model-selection.md must, in the same commit, confirm sdk.md holds the pipeline matrix + durable rationale and regenerate the mirror.
- **ADR does NOT clear the 3-criteria gate** — the refactor is mechanically reversible (fails "hard to reverse"). Home is `docs/internals/sdk.md` + a verb comment, not a new ADR (over-producing ADRs is its own anti-pattern).
- **Mitigations**: drop the review.md "fix"; add the role-threshold regression test; scope the verb to the 4 criticality-varying rows; give the prose a hard-fail handler (or a documented default); fresh lifecycle-only module (sequential dispatch); reconcile all 4 routing copies + mirror in one commit; rationale → sdk.md.

---

## Open Questions

These are genuine design decisions, **deferred to the Spec phase** (resolved in the structured interview + value gate with the user). Each carries written rationale, per the research exit gate.

1. **Run-discipline vs single-source (the central decision).** RUN-the-verb (Fork 2a) enforces single-source only if the orchestrator actually runs it every dispatch; deleting all inline literals removes the correct-by-construction fallback the system has *today* (where there is no drift). Options: (a) RUN-verb + delete literals (max single-source, no fallback); (b) RUN-verb but keep a brief inline value + a parity test asserting inline==verb-table (belt-and-suspenders, reintroduces a literal); (c) structural gating per CLAUDE.md where skill control-flow allows. *Deferred to Spec: this is a value/robustness tradeoff the user should weigh, especially given there's no present drift to fix.*
2. **Hard-fail handling for a prose consumer.** If the verb exits nonzero (unknown role), the skill prose currently defines no handler — the agent would improvise. Decide: documented "on nonzero, halt and escalate" handler vs a safe default vs structural pre-validation. *Deferred to Spec: needs a concrete prose contract.*
3. **Synthesizer sites: inline-constant vs verb-row.** Adversarial recommends keeping `opus` inline (+comment); Migration recommended a verb row. *Deferred to Spec — leaning inline-constant, but confirm with the user since it bounds the verb's role set.*
4. **Does the verb earn its place given no present drift?** The honest value case is preventive single-sourcing + resolver-verb-family consistency + "trim fat" (the user's framing), not a bug fix. The cheaper alternative (fix-nothing + parity test) is viable. *Deferred to the Spec value gate — the user already chose to build the verb; this records the tradeoff for explicit confirmation.*
5. **Rationale-prose: confirm sdk.md (not ADR) and the delete-vs-snapshot call for version-pinned numbers.** *Deferred to Spec.*
6. **Scope of migratable sites: confirm 4 criticality-varying roles** (review, builder, orchestrator-fix, competing-plan); exploration/parallel-research excluded (no call-site); synthesizers inline. *Deferred to Spec for the final in/out list.*
