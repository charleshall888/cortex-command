# Research: backlog-optional-plugin

> Topic: make the backlog an optional `cortex-backlog` plugin with a config-selected backend (local engine / external LLM-best-effort / none).
> Authoritative spec: `cortex/requirements/backlog.md` (gathered 2026-06-23). This research decomposes that spec into an epic + tickets; it does not re-open its locked decisions.

## Research Questions

1. Where should the config-resolution seam live, and how do consumers read `lifecycle.config.md` today? → **`cortex_command/lifecycle_config.py`** is the canonical parser (`read_branch_mode`, `read_commit_artifacts`, shared `_extract_frontmatter_text`) `[cortex_command/lifecycle_config.py:22,29-46,49-88,91-140]`. A new `resolve_backlog_backend(repo_root)` belongs there, reusing `_extract_frontmatter_text`, exposed via a **new CLI module** (mirroring `cortex_command/lifecycle/branch_mode_cli.py` `[pyproject.toml:52]`) — NOT a reuse of `lifecycle_config:_main`, which is hardcoded to commit-artifacts `[cortex_command/lifecycle_config.py:143-156]`. Overnight has its own inline parser `read_synthesizer_gate` `[cortex_command/overnight/cli_handler.py:74-114]` and should call the shared helper rather than grow a third.

2. Exact per-consumer backend-branch edit points? → Mostly **skill-prose**: lifecycle `[skills/lifecycle/references/backlog-writeback.md:45,53,60-62]`, discovery `[skills/discovery/references/decompose.md:138,183]` + `[skills/discovery/SKILL.md:93]`, morning-review `[skills/morning-review/references/walkthrough.md:538]` + `[skills/morning-review/SKILL.md:91,101-111]`, dev `[skills/dev/SKILL.md:137,141,147,155,161-166]`. Two **Python** points: refine `[cortex_command/refine.py:35-85,157,231]` and the overnight selection guard `[cortex_command/overnight/cli_handler.py:2005,2013,2078,2087]`.

3. Build/distribution mechanics for a new plugin? → justfile `BUILD_OUTPUT_PLUGINS` + per-plugin `case` array `[justfile:575,596-609]`; build-plugin **skips** unmaterialized plugins `[justfile:592-593]`; pre-commit Phase-1 **fails closed** on unclassified plugin dirs `[.githooks/pre-commit:31-69]`; drift loop `git diff --quiet` `[.githooks/pre-commit:641-664]`. A skills-only plugin needs only `.claude-plugin/plugin.json` hand-authored; `skills/` is build-generated. Marketplace registration in `.claude-plugin/marketplace.json` `[.claude-plugin/marketplace.json:12-49]`.

4. Which gates must each ticket satisfy? → dual-source/drift co-land `[.githooks/pre-commit:31-69,641-664]`; `plugin-list-matches-justfile` self-test asserts `PLUGIN_NAMES == justfile lists` `[cortex_command/parity_check.py:1607-1638]`; marketplace set vs PLUGIN_NAMES `[cortex_command/parity_check.py:1635-1637]`; SKILL.md 500-line cap `[tests/test_skill_size_budget.py:59]`; MUST-escalation policy forbids MUST in routing prose `[CLAUDE.md]`; events-registry dual-gate if any event added `[bin/.events-registry.md]` + `[cortex_command/overnight/events.py:93-154]`; backlog grep-targets must resolve `[tests/test_backlog_grep_targets_resolve.py:49,72-118]`; ADR three-criteria gate `[cortex/adr/README.md:19-27]`.

5. External-tracker LLM-best-effort failure modes? → GitHub search is fuzzy + eventually-consistent → duplicate-on-retry; `gh auth status` exit codes unreliable; human title edits orphan the no-ID-map round-trip; `complexity`/`criticality` absent from `index.json`. See Web & Domain sections.

6. Correct sequencing? → `P4` (resolver) is the long pole; `P4 → P5 → P6 → {P7,P8,P9}`. Extraction `P1` changes the slash namespace, so it precedes the `P6` rename. See Architecture.

## Codebase Analysis

- **Config parser & pattern.** `cortex_command/lifecycle_config.py` is the home for config readers; each ships as an importable function + a console-script binstub consumers shell from prose (precedent: `cortex-read-commit-artifacts` shelled at `[skills/lifecycle/references/complete.md:19]`, `[skills/lifecycle/references/plan.md:302]`, branching on `true`/`false` stdout). The resolver mirrors `branch_mode_cli.py` `[pyproject.toml:52]` as its own CLI module `[cortex_command/lifecycle/branch_mode_cli.py:21]`.
- **Config scaffold.** `cortex_command/init/templates/cortex/lifecycle.config.md` holds the current keys (`skip-specify`, `skip-review`, `commit-artifacts`, `synthesizer_overnight_enabled`); it is hash-tracked in `_HASH_INPUT_TEMPLATES` `[cortex_command/init/scaffold.py:69]`, so adding a `backlog:` block requires bumping the init-artifacts hash. `NOT_FOUND(query="backlog:/backend: keys", scope="cortex_command/init/templates/cortex/lifecycle.config.md")` — net-new.
- **Consumer edit points** are enumerated per Research Question 2. Corrections to initial assumptions: discovery's create is **skill-prose** (`decompose.md` → `backlog/SKILL.md:54,62`), not in `cortex_command/discovery.py` (`NOT_FOUND(query="cortex-create-backlog-item", scope="cortex_command/discovery.py")`); dev picks via index files + `cortex-build-epic-map` `[skills/dev/SKILL.md:155]`, **not** `cortex-backlog-ready` (`NOT_FOUND(query="cortex-backlog-ready", scope="skills/dev/")`).
- **Plugin template.** `cortex-overnight` is the analog `[plugins/cortex-overnight/.claude-plugin/plugin.json:1-8]`; cortex-backlog is simpler (no MCP, no hooks, no bin, no vendored Python).
- **Parity placeholder already in place.** `cortex-backlog` sits in `RESERVED_NON_BIN_NAMES` `[cortex_command/parity_check.py:62-66]` (committed this session) and migrates to `PLUGIN_NAMES` `[cortex_command/parity_check.py:34-43]` when the plugin is built.
- **Engine stays in the wheel.** `cortex_command/backlog/*` (create_item/update_item/ready/resolve_item/generate_index/readiness) and `cortex_command/overnight/backlog.py` selection are unchanged and remain cortex-backlog-only; backend branching is at the skill/consumer layer per spec `[cortex/requirements/backlog.md:100]`.
- **Structural (non-skill-routed) consumers.** `dev` reads `cortex/backlog/index.{md,json}` directly `[skills/dev/SKILL.md:147,155]`; `refine.py:_read_backlog_frontmatter` reads `cortex/backlog/{slug}.md` for tier/criticality `[cortex_command/refine.py:35-60]`; `refine` parent-epic alignment reads `cortex/backlog/NNN-*.md` `[skills/refine/references/clarify-critic.md:23-25]`. These have no local index under an external backend — they need an explicit degrade decision.

## Web & Documentation Research

- **`gh issue create` has no idempotency key**; real scripts created duplicates on re-run until adding search-before-create ([github.com/vamseeachanta/workspace-hub#1710]). GitHub issue search is **fuzzy/partial-match** even with quoted `in:title` ([community#17956], [cli/cli#1011]) and **eventually consistent** — a just-created issue may not appear in search for ~minutes ([community#13516], [GitHub April 2026 availability report]), so create-then-immediately-search races and can duplicate on retry.
- **`gh` auth**: reads `GH_TOKEN`/`GITHUB_TOKEN` for headless use ([cli.github.com auth manual]); has a **silent unauthenticated fallback** that surfaces as confusing rate-limit errors ([cli/cli#13317]); `gh auth status` **exit codes have been buggy** ([cli/cli#8845], [PR#9240]) — prefer a positive functional probe (e.g. `gh api user`).
- **`gh` v2.94.0 (2026-06-10)** now exposes `--type/--parent/--blocked-by/--blocking` on create/edit and parent/sub-issue/type/dependency JSON fields on view/list ([github.blog changelog 2026-06-10]); issue dependencies + sub-issues + types are GA ([changelog 2025-08-21], [InfoQ 2025]). This **softens** the spec's "limited dependency support" framing — the example `instructions` snippet should recommend the v2.94+ flags. Caveat: issue **types are org-level** (absent in personal repos → label fallback).
- **Jira has no single canonical CLI** (`ankitpokhrel/jira-cli`, `go-jira/jira`, `andygrunwald/go-jira`, npm wrappers), each with different auth — the structural reason Jira can't reach `gh`-parity and stays best-effort/unverified.

## Domain & Prior Art

- **LLM-as-adapter via CLI** is exactly how Claude Code already drives `gh` — reusing the agent as the integration layer instead of a typed client is sound for GitHub and well-trodden.
- **Calibrated autonomy / human-in-the-loop**: industry guidance routes irreversible, outward-facing, high-blast-radius writes through human approval and warns against confirmation fatigue ([OpenAI guardrails & approvals], [Truto], [StackAI]). Outward issue create/close is precisely that category — reinforcing the spec's rule that external writes stay on interactive paths and overnight refuses external backends.
- **Durable cross-reference**: embedding the cortex slug/UUID in the issue **body** (survives human title edits) is the cheap middle ground for the spec's "persist the external ref?" open question — lighter than a persisted ID map, more robust than title-only re-resolution.

## Feasibility Assessment

| Approach (piece) | Effort | Risks | Prerequisites |
|---|---|---|---|
| Extract `backlog` mgmt skill to optional plugin | M | atomic blast radius; drift/parity/marketplace co-land | parity placeholder (done) |
| Config-backend resolver + binstub | S | second config parser divergence | none (long pole) |
| Config scaffold `backlog:` block | S | init-artifacts hash bump | resolver field shape |
| Interactive consumer routing + slash-rename | L | double-edit vs rename; cross-plugin refs; MUST-escalation | resolver |
| External best-effort create + round-trip | M | dup-on-retry; fuzzy search; auth probe; fidelity loss | resolver; routing |
| Overnight refusal guard | S | `backend` name collision; bypass paths | resolver |
| none-backend + structural-consumer degrade | S | dev/refine have no index under external | routing |
| ADR-0015 | S | back-point discipline | decision recorded |

## Architecture

### Pieces

- **P1 — Extract the `backlog` management skill into an optional `cortex-backlog` plugin (atomic).** Move ONLY `backlog` (add/list/pick/ready/archive/reindex against the local engine); **keep `backlog-author` in cortex-core** (it is a backend-agnostic body composer that discovery and morning-review need on the external path). Co-land set: justfile `BUILD_OUTPUT_PLUGINS` + new `case(SKILLS=backlog)`, remove `backlog` from cortex-core's array, delete `plugins/cortex-core/skills/backlog/`, scaffold `plugins/cortex-backlog/.claude-plugin/plugin.json`, migrate `cortex-backlog` `RESERVED_NON_BIN_NAMES`→`PLUGIN_NAMES`, `.claude-plugin/marketplace.json` entry, `tests/test_dual_source_reference_parity.py` PLUGINS dict entry, a parity regression test that `cortex-backlog-ready`/`cortex-resolve-backlog-item` stay classified as bin scripts, then `just build-plugin`. (All forced together by Phase-1 fail-closed + the two self-tests + the drift gate.)
- **P2 — Install-topology dependency contract.** Define which plugins may be installed independently and what each consumer does when `cortex-backlog` is absent. Establishes that `backlog-author` stays in cortex-core (guaranteed dependency of discovery and of morning-review, which ships in cortex-overnight). Small; may fold into P1 or pair with the ADR.
- **P3 — Human-facing docs registration.** `docs/setup.md` table ("six"→"seven" + OPTIONAL row + prereq note + install snippet), `CLAUDE.md` architecture prose, `cortex/requirements/project.md` prose, `docs/backlog.md`. (marketplace.json itself lives in P1 because it is gated.)
- **P4 — Config-backend resolver (long pole).** `resolve_backlog_backend(repo_root) -> "cortex-backlog" | <external> | "none"` (default `cortex-backlog`) in `lifecycle_config.py` reusing `_extract_frontmatter_text`; a new CLI module mirroring `branch_mode_cli.py`; binstub `cortex-read-backlog-backend` with the dual-channel wheel/source wrapper. Overnight calls this helper rather than adding a parser.
- **P5 — Config scaffold.** Add the `backlog:` block (`backend:` default `cortex-backlog` + commented alternatives, freeform `instructions:`) to the init template; bump the init-artifacts hash in `scaffold.py`.
- **P6 — Interactive consumer routing + slash-rename (single pass per file).** For lifecycle, discovery, refine, dev, morning-review: branch on `cortex-read-backlog-backend` (soft positive-routing prose, no MUST) AND rename `/cortex-core:backlog`→`/cortex-backlog:backlog` in the same edit — **live files only** (skills/docs/tests fixtures), explicitly excluding historical `cortex/lifecycle/**` and `cortex/research/**`. Includes the refine.py read-point branch and morning-review's cortex-overnight-resident backend-awareness. (L1 ratchet is unaffected — budgets key on canonical skill dir name.)
- **P7 — External best-effort create + round-trip.** Compose body via `backlog-author`, then create in the tracker via the `instructions` hint; search-before-create on a cortex-controlled label+slug; embed slug/UUID in the issue **body**; auth via functional probe; round-trip by listing+disambiguating (not create-then-immediately-search); on any failure surface the composed body inline rather than dropping work; example `instructions` uses `gh` v2.94+ flags with the org-level issue-types caveat noted.
- **P8 — Overnight refusal guard.** A shared helper called as the FIRST check in `handle_prepare`/`handle_launch` (verify `handle_schedule`/`handle_start` can't reach `select_overnight_batch` unguarded); resolved value named `backlog_backend` to avoid the launchd `backend` collision; refuses any non-`cortex-backlog` backend; a test asserts overnight performs zero `gh` issue writes.
- **P9 — `none`-backend behavior + structural-consumer degrade.** Incidental consumers skip with a one-line advisory; discovery surfaces composed bodies inline; explicit decision for `dev` epic-map and `refine` parent-epic alignment under external/`none` (recommend: scope those reads to cortex-backlog-only with a clear advisory, since the local index won't exist).
- **P10 — ADR-0015: configurable backlog backend + LLM-as-adapter.** Records context/decision/rejected-alternatives (per-tool code adapters, rejected for zero-maintenance)/consequences; consumers and `backlog.md` back-point by number, no rationale duplication.

### How they connect

`P4` (resolver) is the spine: `P6`, `P7`, `P8`, `P9` all consume its output, so it lands first and `P5` (scaffold) follows to make the field real for end-to-end testing. `P1` (extraction) is largely independent of the config seam but changes the slash namespace, so it precedes `P6`'s rename. `P2` (topology contract) is the guardrail that keeps `P1` from breaking the external path — it is the reason `backlog-author` is excluded from the move. `P3` is human-facing docs trailing `P1`. `P10` (ADR) records the decision and should land early (with `P4`) so later pieces back-point to it. The hard safety boundary is `P8`: overnight structurally refuses external backends so unattended outward writes are impossible — enforced in control flow, not prose. The deliberate scope wall (spec): **no concrete Jira/GitHub code adapters** — `P7` is prose-and-`gh` only.

## Decision Records

- **Keep `backlog-author` in cortex-core; move only the `backlog` management skill.** The external-backend create path (discovery, morning-review) composes ticket bodies through `backlog-author` `[skills/discovery/references/decompose.md:17]`, `[skills/morning-review/SKILL.md:91]`. Moving it into the optional plugin would mean a github-issues user (cortex-core, no cortex-backlog) loses the body composer — gutting the feature the area exists to ship. Alternative (move both) rejected.
- **Config is the source of truth, default `cortex-backlog`; the backlog "engine" stays in the wheel.** What becomes optional is the interactive `/backlog` management surface and the active-backend selection — not the backlog system itself (overnight still requires it). This is coherent with the spec's explicit scope-out of removing the engine `[cortex/requirements/backlog.md:13]`; P1's framing is "extract the management surface," not "make the backlog optional."
- **Round-trip via body-embedded slug + list-and-disambiguate, not a persisted ID map.** Cheapest design that survives human title edits and GitHub's eventual-consistency, staying in the best-effort spirit. Heavy ID-map persistence rejected for v1 (revisit if flaky).
- **Overnight refuses external backends (structural, not prose).** Outward issue writes are irreversible/high-blast-radius and unsafe unattended; deterministic selection also can't reconstruct the rich local fields. Best-effort overnight-on-external rejected.

## Open Questions

- **`dev` epic-map and `refine` parent-epic alignment under external/`none`**: scope to cortex-backlog-only with an advisory, or define a best-effort degrade? (Recommend cortex-backlog-only + advisory; `complexity`/`criticality` aren't even in `index.json`, so external read-back is lossy.)
- **Event vs prose for backend resolution / overnight refusal**: if implemented as a logged event (e.g. `backend_resolved`), it must register in the events-registry dual-gate; if prose-only advisory, no gate fires. Decide per piece.
- **Should a starter `instructions` snippet ship for Jira** (and which CLI), or stay deferred until a real Jira user drives it? (Spec defers; recommend keep deferred.)
- **P2 granularity**: standalone ticket vs folded into P1/P10.
- **Whether any concrete external adapter is ever warranted** — explicitly deferred to a future area decision (spec boundary).
