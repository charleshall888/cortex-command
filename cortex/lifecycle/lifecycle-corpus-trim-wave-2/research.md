# Research: Reduce per-invocation loaded tokens of /cortex-core:lifecycle runs by ~50% on common paths

Topic: progressive disclosure, wrapper-verb combining (`cortex-lifecycle-enter`, `cortex-lifecycle-finalize`, `cortex-lifecycle-register-artifact`), reference merging/pruning, and word-level compression across the lifecycle skill, with refine/critical-review/commit/pr held at audited floors (safe cuts only) and skills/research taking its first content audit. Target metric (operator-confirmed): **per-run loaded tokens**, not corpus bytes.

## Codebase Analysis

**Load-path map** (bytes actually read per route, `wc -c`-measured, lifecycle+refine files only):

| Route | Files | Bytes |
|---|---|---|
| A: new feature, full run, trunk | 18 | 99,449 |
| B: new feature, full run, worktree | 19 | 100,469 |
| C: resume at plan | 5 | 28,372 |
| D: resume at implement | 4 | 25,295 |
| E: complete first-run | 3 | 19,492 |
| F: complete finalize re-invocation | 3 | 19,492 |
| G: simple tier, gate-skip | 18 | 94,931 |

**Always-on set** (every route): `SKILL.md` (8,475B) + `backlog-writeback.md` (3,452B) = 11,927B — the highest-leverage surface; SKILL.md alone is 71% of the floor and taxes even cheap resumes.

**Measured split candidates:**
- `complete.md` (7,565B): first-run Steps 1–6 = 2,541B; Step 7 + finalize = 4,916B. **Not route-exclusive** — see Adversarial #2; on_main reads Step 2 plus Steps 9–12, bypassing Step 7 by design.
- `orchestrator-review.md`: shared protocol 2,776B + Post-Specify checklist 1,034B + Post-Plan checklist 1,516B. Each invocation wastes the other phase's checklist; fires twice per full run — phase-split compounds.
- `criticality-matrix.md` (1,897B): only its "Reading lifecycle state" third is load-bearing on straight-line runs.

**Zero-context-cost files** (skip in all effort accounting): `_interactive_overnight_check.sh` (piped to bash, never read), `assets/lifecycle.config.md` (copied template). `kept-pauses.md` and `seed-reconcile-gate-ordering.md` are referenced with passive "lives in" phrasing — a well-behaved reader never loads them (Adversarial #6 confirms no overnight path reads them either); make the non-load explicit rather than assumed.

**Conventions:** every reference self-declares its trigger condition in its first line; `${CLAUDE_SKILL_DIR}` propagation is load-bearing (ADR-0009) and must be simplified, not multiplied, by splits/merges.

## Web Research

- Anthropic skill guidance: progressive disclosure is the core design principle; **references exactly one level deep from SKILL.md** (nested chains risk partial reads); TOC for references >100 lines; "concise is key — challenge every paragraph's token cost"; scripts for deterministic steps should solve-don't-punt (handle their own errors).
- GitHub's agentic-workflow token work (−19% to −62% per workflow) validates the verb-offload lever: move deterministic data-gathering out of the agent loop entirely.
- **Compression risk evidence**: format/procedural-constraint compliance degrades *before* semantic task success under compression (arXiv 2512.17920's "Instruction Ambiguity Zone") — post-trim validation must probe constraint compliance (gates, skip conditions, exact literals), not task completion. "Lost in the middle": mid-file placement of critical rules can make a shorter file behave worse — put load-bearing rules at section edges. Prefer structural compression (splits, offload, dedup) over aggressive word-level compression of surviving prose.

## Requirements & Constraints

- **Ledger authority**: the closed trim campaign's ledger (`cortex/research/skill-value-scorecard/README.md`) Rule 4 bars re-audits absent a changed corpus or new lens. This campaign's lens — route-conditional per-invocation load, measured per route — is new (prior campaign measured corpus bytes), and the operator explicitly directed the pass; floors on refine/critical-review were **re-verified, not re-litigated** (fresh audits: ~2.7% and ~4.5% cuttable).
- **L1 frontmatter ratchet is a separate budget** (lifecycle 890B, refine 624B, critical-review 795B, research 379B; shrink-only) — distinct from the per-invocation metric; don't conflate.
- **Verb constraints**: ADR-0019 dumb arg-actors (`--backend`, `--phase` caller-passed, never self-resolved); ADR-0020 uniform event rows via `log_event` — the hand-written `schema_version`-first exemption class is closed at three events; new verbs invent no fourth. Skill-helper-module pattern (project.md): console-script + `python3 -m` fallback; new events register in `bin/.events-registry.md`.
- **Structural gates**: SKILL.md 500-line cap; dual-source mirror parity (regen via pre-commit hook / `just build-plugin`); SP001/SP002 path lint; L201 bare-import lint; contract lint E101 (prose flags must match argparse); parity lint W003 (new `bin/cortex-*` needs a wiring reference; absorbed verbs whose prose call sites vanish need re-wiring or exception rows); kept-pauses parity test updates in the same change as any pause-site move.
- **Testing**: verb CLI tests use `CORTEX_REPO_ROOT` injection (env-var flavor for `_resolve_user_project_root` consumers; chdir flavor for `_from_cwd` consumers). Full-suite runs before declaring done; known order-dependent pollution baseline (test_templates + feature_cards) and sandbox-only mcp_subprocess DNS failure pre-exist.
- Flagged stale references (housekeeping, not blockers): events-registry rows past their 2026-06-10 deprecation grace window; `lifecycle_cancelled` row cites a nonexistent producer path; project.md Global Context names an absent `cortex/requirements/glossary.md`.

## Verb Design

- **`cortex-lifecycle-enter`** composes, in-process: `create_index()` (skip-if-exists idempotent; raises OSError on bad `--backlog-file` → exit 1), `start_sync()` (raises `_Exit2` on ambiguous slug → exit 2; shells to `cortex-update-item` one layer down), `init_ensure` (exit-code-shaped — call `main([])` or replicate its two steps), and the `.session` write (`Path.write_text`, currently raw shell in prose). Returns one envelope with a `backlog_status` discriminant (`already_complete` | `open` | `no_match`) so the skill keeps the close/continue `AskUserQuestion`; the verb never auto-closes. **`--phase`/`--backlog-file`/`--backend`/`--session-id` are caller-passed from the Step-1 resolver output** — the verb must not re-derive new-vs-resume (Adversarial #3).
- **`cortex-lifecycle-finalize`** composes: backend-gated `update_item()` (whose built-in index regen makes complete.md Step 10's two-tier fallback redundant — drop it), `counters` functions (call in-process with resolved paths; its CLI hardcodes a relative default), and `log_event(event="feature_complete", ...)` behind a new small idempotent-guard scan (no reusable helper exists; `complete_route.py` has an inline analog). **Must emit `merge_anchor: "merge"`** — `pipeline/metrics.py` segments interactive vs legacy-overnight regimes on this field, and the nearest code precedent (`overnight/advance_lifecycle.py`, a third `feature_complete` emitter) deliberately omits it; copying that shape silently misclassifies every interactive completion (Adversarial #5). Pin with a dedicated test.
- **`cortex-lifecycle-register-artifact`**: no existing code reads/updates `index.md`'s `artifacts:` array (written once as `[]`; PyYAML can't round-trip the format). Model the regex capture-rewrite on `update_item._remove_uuid_from_blocked_by` + `atomic_write`; replaces backlog-writeback.md's prose recipe consumed by plan/review/refine call sites.
- **Envelope conventions**: single JSON object, `state` discriminant, module-level `KNOWN_STATES` tuple with a reachability test, `prepare_worktree`'s always-emit-JSON-never-crash wrapper for interactive-flow verbs; `complete_route.py`'s docstring route table as documentation shape.
- **Call sites**: `create-index`/`start-sync` have no consumers outside the two Step-2 references (safe to fold, update both docs together); `cortex-update-item`, `cortex-generate-backlog-index`, `cortex-lifecycle-event`, `cortex-lifecycle-counters` are general-purpose and stay standalone. `init-ensure` keeps its binary (used at SKILL.md Step 2; R10a test pins its literal in SKILL.md ≥1 — update the test with the migration).
- **Known pin edits**: delete `FILE_EVENTS["backlog-writeback.md"]["feature_complete"]` when the prose emission moves into Python (test fails loud otherwise); complete.md's Step 11 emission is currently untracked in FILE_EVENTS (pre-existing gap — resolve by replacing with a Python-side test rather than adding a stale entry); update the events-registry `feature_complete` producers row (Python emitters are `scan_coverage: manual`).
- **Pre-existing inconsistencies found** (fix or explicitly ignore, don't propagate): `--session-id null` never clears frontmatter (`_DEST_TO_FRONTMATTER_KEY` has no session_id entry) yet `generate_index.py` reads it from frontmatter; complete.md Step 9 has no backend gate while backlog-writeback.md's write-backs do — the finalize verb should close this by accepting `--backend`.

## Sub-skill Audit (research, commit, pr)

- `skills/research/`: ~600B of safe/probably-safe cross-file dedup (upper-bound restatement, mode-routing forward-reference, conditional-angle descriptions, "Tradeoffs is the common choice" echo, frontmatter parenthetical — the last also buys L1 headroom). The SKILL↔fanout dispatch-protocol near-duplication is **by design and pinned** ("this file authors the rule; each consumer carries its own runnable bind") — leave it. Floor ≈ 12,700B.
- `skills/commit/` and `skills/pr/`: at floor now; zero viable cuts (L1 at exact ceilings, bodies pure gate/format content).

## Adversarial Review

1. **One-level-deep vs. §1a extraction**: plan.md→competing-plans.md is an existing second-level chain, but an untested precedent on rare judgment prose; the §1a extraction moves ordinally-strict, literal-pinned machinery onto the common worktree path. Mitigate: imperative "Read X and follow" linking, self-declared trigger, verbatim-literal preservation, and an empirical check of the nested read during verification.
2. **complete.md halves are NOT route-exclusive** (claim falsified): on_main jumps Step 2 → Steps 9–12, bypassing Step 7 structurally (prior offload ticket's research confirms a naive Step-7 call on-main spuriously fires the orphan probe). Correct shape: the finalize half (Step 7 router + Steps 8–12) is near-universal; Steps 1–6 is the true optional chunk; on_main needs Step 2's artifact-commit behavior plus the finalize half. Redo savings math (finalize re-invocations save ~2.5K; first-runs roughly break even).
3. **Enter-verb resume safety** holds only with caller-passed `--phase` (resolver output), mirroring start_sync — never wrapper-internal phase detection.
4. **Checklist compression is two levers**: the structural phase-split is low-risk (ship); word-level criteria compression specifically endangers conditional gates (S7/P8/P10 skip rules, P7's benign-vs-harmful nuance) per the constraint-compliance finding — verify gate compliance post-compression, not just verdict emission.
5. **Third feature_complete emitter** (`overnight/advance_lifecycle.py`, no `merge_anchor`, deliberate) — do not use as a template; pin `merge_anchor: "merge"` in the finalize verb's test.
6. **kept-pauses.md non-load confirmed** for interactive and overnight modes — safe to mark explicitly non-runtime.
7. **Test blast radius beyond the pin map's list**: `test_lifecycle_step_v_ordering.py`, `test_implement_worktree_interactive_contract.py`, `test_lifecycle_picker_label_pins_worktree.py` all hardcode implement.md and text-anchor-extract §1/§1a blocks — they re-anchor in the same change as the extraction; ~20 test files reference implement.md, audit all before extraction.

## Open Questions

- **Does a second-level reference read land reliably for procedural content?** Resolved for planning purposes: proceed with the extraction using imperative linking + self-declared condition (the pattern merge-back.md already uses successfully on the same path), and add an explicit end-to-end verification step (drive the worktree route, confirm Step v ordering executes) before commit. If verification shows partial reads, fall back to keeping §1a inline and taking the smaller structural wins.
- **Exact complete.md split shape.** Resolved: keep Step 7 + Steps 8–12 (+ a compact on-main artifact-commit note) in complete.md; extract Steps 1–6 PR-flow to a first-run reference. Savings accrue to finalize re-invocations and on_main; first-runs break even.
- **W003 parity wiring for absorbed verbs** (create-index/start-sync binaries lose their prose call sites) and the R10a init-ensure literal pin: deferred to Plan — mechanical resolution (exception rows or doc-reference retention), enumerate exact edits there.
- **Whether `--session-id null` dead-field inconsistency gets fixed in this wave.** Deferred with rationale: pre-existing, orthogonal to token reduction; record as a backlog candidate rather than expanding this wave's blast radius.
