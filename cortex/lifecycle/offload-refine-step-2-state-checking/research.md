# Research: Offload /cortex-core:refine Step 2 state-checking and backend routing into the cortex-refine CLI (backlog #322)

**Clarified intent:** Reduce the deterministic, paraphrase-prone surface of the high-traffic `/cortex-core:refine` skill via two related workstreams — (a) offload Step 2's resume-point determination and backend-aware seeding plus the parallel Step 5 `reconcile-clarify` backend routing into the `cortex-refine` CLI, leaving the skill only behavioral guards a CLI cannot encode; and (b) harden the refine→research `research-considerations` arg-interface so neither skill carries character-escaping prose. Preserve byte-identical local `cortex-backlog` behavior and the seed→reconcile→gate ordering invariant.

**Tier/criticality:** complex / high. Research ran an 8-agent fan-out (3 core + 4 design + adversarial). **Headline:** the adversarial pass refuted or weakened several of the ticket's premises — the offload is smaller-value and more architecturally fraught than the ticket implies. The four threads do **not** stand or fall together; see Open Questions for the decisions Spec must take.

---

## Codebase Analysis

**`cortex_command/refine.py` (381 lines)** — primary mutation target.
- Existing verbs: `_cmd_emit_lifecycle_start` (lines 213-288) and `_cmd_reconcile_clarify` (lines 130-210). Idiom: resolve `events_log = Path("cortex/lifecycle")/slug/"events.log"` (bare cwd-relative), `mkdir(parents=True, exist_ok=True)`, read state, append JSONL, return exit 0 / 64 (invalid frontmatter) / 70 (write/IO error). `emit-lifecycle-start` does a read-after-write verify (256-287) and carries the canonical `cortex init` sandbox-write remediation message (246-254).
- Argparse (`_build_parser`, 291-370): subparsers via `sub.add_subparsers(dest="command")`, `sub.required=True`, each `sub.add_parser(...).set_defaults(func=...)`; `main()` dispatches `args.func(args)`. A new subcommand follows this exactly.
- **The CLI is currently backend-blind.** refine.py does **not** call `resolve_backlog_backend`. Backend routing is encoded entirely by the SKILL omitting `--backlog-slug` on non-local backends → `_read_backlog_frontmatter(None)` (52-53) returns seed defaults `("simple","medium")` without reading a local file.
- events.log row shapes: `lifecycle_start` = `{schema_version:1, ts, event, feature, tier, criticality, entry_point:"refine"}` (233-241); override rows = `{ts, event:"complexity_override"|"criticality_override", feature, from, to, gate:"clarify_reconcile"}` (168-190). Written `json.dumps(row)+"\n"` append.
- **Reconcile precedence (156-161): explicit flags win over frontmatter** — `desired = args.complexity if args.complexity is not None else base_tier`. (Load-bearing for the byte-identity question below.)
- Distribution: `cortex-refine = "cortex_command.refine:main"` (pyproject.toml:65), a **wheel-only `[project.scripts]` console-script with NO `bin/` wrapper**. A new subcommand needs no new console-script, no new parity-allowlist row, and is **not** rsynced into `plugins/cortex-core/bin/` (only `cortex_command/refine.py` ships via the wheel). Only `skills/refine/SKILL.md` edits require `just build-plugin` mirror regen.

**`skills/refine/SKILL.md` (~222 lines total, ~207 body)** — WELL under the 500-line `test_skill_size_budget.py` cap. The L1-surface budget (refine = 624 B, `test_l1_surface_ratchet.py:66`) governs frontmatter only and is untouched by body trims. Blocks to condense: Step 2 resume tree (lines 41-53), backend resolve-once (57), emit two-arm bullets (59-64), Step 5 reconcile branch (145-150), Alignment-Considerations Propagation (120-133; escaping caveat at 129, pass at 131).

**`skills/research/SKILL.md` (~244 lines)** — Step 1 arg-parse (28-45); escaping caveat at line 45; per-angle injection at 61-63; `## Considerations Addressed` (lifecycle-mode only) at 229-238.

**Resume-point is NOT a fold-in.** `cortex_command/common.py:detect_lifecycle_phase` (395-436) and `cortex-lifecycle-state` (`lifecycle/state_cli.py`) are **events.log reducers** (project `{tier, criticality}` via `reduce_lifecycle_state`, common.py:762). Resume-point is **filesystem artifact-stat** — different input/output/consumer. `detect_lifecycle_phase` also lacks refine's branches (both-exist→complete, spec-without-research, clarify). → a new `cortex-refine` subcommand is the idiomatic home, not a `--field` on the shared reducer.

**Backend resolver:** `cortex_command/lifecycle_config.py:resolve_backlog_backend(repo_root)->str` (97-154) never raises, fails open to `"cortex-backlog"`. Import is cycle-safe. The argless reader `cortex-read-backlog-backend` (`lifecycle/backlog_backend_cli.py:76`) resolves root via `_resolve_user_project_root()` (honors `CORTEX_REPO_ROOT`, walks up to nearest `cortex/` ancestor; common.py:84-99) and fails OPEN. The overnight guard (`overnight/cli_handler.py:1955-1977`) fails CLOSED — **these two must NOT be DRY-merged.**

**No new tracked surface (VERIFIED by adversarial):** `bin/.events-registry.md` already lists `cortex_command/refine.py` as emitter for `lifecycle_start` / `criticality_override` / `complexity_override` (lines 13/19/103); Python emission sites are out-of-scan for the events-registry gate. Parity is name-based on `bin/cortex-*` + `[project.scripts]` keys; internal changes that keep the `cortex-refine <verb>` literals wired trip nothing.

**Test surface (must stay green / extend):**
- `tests/test_refine_module.py` — full `emit`/`reconcile` coverage; the model for a new-subcommand test. Note `test_reconcile_clarify_flags_take_precedence_over_backlog` (line 396) pins flags-win on the default backend.
- `tests/test_refine_reconcile_clarify.py::test_refine_non_local_reconcile_branch_is_value_aware` (250-275) **statically pins the TWO-ARM SKILL.md structure** → must be rewritten if the two-arm prose collapses.
- `tests/test_refine_lifecycle_start_wiring.py` (asserts literal `cortex-refine emit-lifecycle-start`), `tests/test_refine_reconcile_wiring.py` (asserts `cortex-refine reconcile-clarify` present AND before the `specify.md`-delegation anchor at SKILL.md:152), `tests/test_refine_skill.py` (the §4 "Complexity/value gate" anchor at SKILL.md:157) — preserve these anchors or update tests.

---

## Web Research

Direct prior art for "offload LLM-skill prose into a CLI" is essentially nonexistent (internal concern); the transferable engineering practice is strong and consistent.

1. **resume-point as a JSON verb** — converge on: single JSON object to **stdout**, human/log noise to **stderr**, **exit 0** on success, a `schema_version` field, and an explicit stability promise (`git status --porcelain` lesson; `terraform show -json`). `terraform plan -detailed-exitcode` (0/1/2) shows reserved non-zero codes for distinct non-error states — usable but must be documented and not conflated with "error." The closest analog is **git rebase/status**: the CLI owns the resume state on disk and exposes both a *read* (status) and *order-enforcing advance* verbs (`--continue/--skip/--abort`).
2. **Passing arbitrary text between tools (ranked least→most brittle):** (1) **file path passed as an arg** / structured file read whole ("pass a filename, not the data"); (2) **stdin**; (3) `key="value"` arg — this is the **CWE-88 argument-injection** surface, brittle exactly on `=`/`"`/whitespace/newlines; (4) **env vars** (worst — leak via `ps`/`/proc`, inherited by children). Bottom line: for arbitrary multi-line quoted text, write a file and pass/derive the path; never put the payload in a `key="value"` arg.
3. **Ordering gates:** encode as **fail-closed guard clauses + runtime invariant checks** in code, not comments. Matches the repo's own "prefer structural separation over prose-only enforcement."

Sources: git-scm porcelain/rebase docs; terraform machine-readable-ui + detailed-exitcode; clig.dev; CWE-88; nodejs-security/smallstep "don't put secrets in env/args"; fail-closed + guard-clause references.

---

## Requirements & Constraints

- **Skill-helper modules** (project.md): the affirmative warrant — collapse paraphrase-prone SKILL.md dispatch ceremonies into atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry; new events register in `bin/.events-registry.md`.
- **SKILL.md-to-bin parity** (`bin/cortex-check-parity`, name-based), **500-line body cap**, **L1 ratchet = frontmatter only** (refine/research are routing-pressure-cluster skills with higher budgets), **bare-Python prohibition L201** (use `cortex-<skill>` console-script invocations), **SP001/SP002 skill-path invariant** (`${CLAUDE_SKILL_DIR}` resolves only in body, propagate the absolute path; ADR-0009) — directly governs thread 4 if any file path is composed into a subagent prompt: **inject content, not a bare path**.
- **Wheel-binstub vs working-tree** — `cortex-refine` binstub reads the installed wheel; `python3 -m cortex_command.refine` / `CORTEX_COMMAND_FORCE_SOURCE=1` runs the working tree. (Per memory: editing this package → sequential dispatch, not worktree.)
- **Seed→reconcile→gate ordering** (`criticality-matrix.md`, quoted): fixed order **seed `lifecycle_start` → `reconcile-clarify` → §3b tier read**. On non-local backends the seed writes `simple`/`medium` defaults (no `--backlog-slug`); the gate stays alive only because `reconcile-clarify` ratchets up from **Clarify's computed** values (explicit flags, never literals/seed-defaults, monotonic-up-only) *before* the §3b read. The local arm is immune (its `reconcile --backlog-slug` re-sources from frontmatter).
- **CLAUDE.md principles:** "prescribe What/Why not How"; "**prefer structural separation over prose-only enforcement for sequential gates**" (the warrant for the offload *and* a caution to encode the ordering structurally); MUST-escalation soft-phrasing default (retained guards should be soft-phrased).
- **⚠️ ARCHITECTURAL CONFLICT — `cortex/requirements/backlog.md` + ADR-0016 (capability SHIPPED in v2.29.0 / #317; ADR frontmatter may still read "proposed"):** "Backend branching lives in the **consumer skills, NOT in the CLI tools**" (backlog.md:50); "the `cortex-*` CLI tools remain cortex-backlog-only local engine" (:100); "the `cortex-*` backlog CLIs **gain no backend awareness**" (ADR-0016:21). These are stated **without qualification**, and the configurable-backend capability they govern is **released**, not hypothetical — so this is a conflict with a live architectural decision. `cortex-refine` is a `cortex-*` CLI. Threads 2-3 propose putting `resolve_backlog_backend()` *into* it. The "skill-helper ≠ backlog-engine CLI" carve-out that would permit this **appears in neither doc** — it is a research-time rationalization. See Adversarial + Open Questions.
- **Hard regression boundary:** the local `cortex-backlog` arm must stay byte-identical (events.log rows), preserving the idempotent read-after-write verify and the sandbox-write remediation message. Backward-compat NFR: existing local repos see zero behavior change.
- ADRs: 0002 (CLI wheel + plugin distribution), 0009 (skill-path resolution), 0016 (configurable backlog backend — *proposed*, most directly in tension).

---

## Thread 1 — Resume-Point Design

**Home module (decisive): a new `cortex-refine resume-point --lifecycle-slug {slug}` subcommand**, not a `cortex-lifecycle-state --field`. Rationale: data-source mismatch (artifact-stat vs events.log reduction), output-contract mismatch (resume is always determinable; reducer returns `{}` when no events), blast-radius (state_cli is parity-locked and consumed by the §3b gate), and cohesion (refine.py already owns refine's lifecycle verbs over the same dir). Lifecycle's own staleness concern is the separate ticket #325 — no conflation.

**Proposed JSON contract** (house style `separators=(",",":")`):
`{"resume":"clarify|research|spec|complete","spec_exists":bool,"research_exists":bool}`
- `resume` is the load-bearing field; booleans are redundant-but-cheap (data-driven warn + test surface).
- Determination: `spec∧research`→complete; `spec∧¬research`→research; `research∧¬spec`→spec; else (incl. missing dir)→clarify.
- **exit 0 for all four states** (all successful determinations); exit 2 for usage errors (argparse `required`); **no 64/70** (read-only, no write/sandbox path).

**Four-state guard-retention table** (answers the Clarify Obj-3 gap):

| State | CLI returns | Guard the skill RETAINS & why |
|---|---|---|
| complete | `resume:"complete"` | Response policy stays in skill: announce, skip to Step 6, **no prompt/menu**, re-run only on explicit user request (CLI can't read conversational intent). |
| spec-without-research | `resume:"research"` | **Warn announcement** stays (human transparency); the skip-Clarify routing is itself carried by `resume=research`. |
| research-only | `resume:"spec"` | **Research Sufficiency Check** (clarify.md §6 signals a–d) stays — semantic judgment comparing research *content* vs clarified intent; CLI can't judge. Path-guard (only the canonical `research.md`) honored by construction. |
| else | `resume:"clarify"` | None — fully CLI-encoded. |

**Behavioral-parity edges:** existence-only via **`is_file()`** (NOT `exists()`, NOT a non-empty check — the non-empty check is a *separate* post-research Step-4 gate; conflating them changes behavior for an empty `spec.md`); exact canonical paths only; missing dir → `clarify` (never an exception); `complete` stays stateless (the explicit-re-run override sits above the CLI in the skill).

---

## Threads 2-3 — Backend Internalization & Ordering Invariant

**Mechanism (if pursued):** import `resolve_backlog_backend` (cycle-safe) into both verbs; immediately before `_read_backlog_frontmatter`, `if backend != "cortex-backlog": backlog_slug = None`. Argparse surface unchanged (all flags stay optional). This converts "don't read a local file on a non-local backend" from a model-obeyed prose rule into a structural one.

**Repo-root nuance (load-bearing & contested):** the Threads-2-3 agent recommended `Path.cwd()` (consistent with the bare-cwd-relative events.log write). The Adversarial agent refuted this — see below — because the canonical reader uses `_resolve_user_project_root()` (honors `CORTEX_REPO_ROOT`, walks up), so `Path.cwd()` would resolve the backend from a *different* root than the rest of the system under a subdir/worktree/`CORTEX_REPO_ROOT` run. **Open question.**

**"One unconditional call" is only partial.** Internalizing backend removes the *backend* sub-branch but NOT (a) the item-existence branch (omit `--backlog-slug` when no backlog item exists, even on cortex-backlog) nor (b) the Clarify-ran-vs-skipped branch (on `resume=spec`, no freshly-computed tier to pass). The skill's call shape stays context-dependent; net prose removed ≈ 4-6 lines per verb, not the whole branch.

**Ordering invariant is ALREADY structurally backstopped.** `specify.md §3b` carries a "Non-local seed-tier fail-safe": runs critical-review whenever `backend≠cortex-backlog ∧ tier=simple ∧ research.md exists`, **independent of whether reconcile ran**. So a silent critical-review skip cannot occur on a non-local backend even if ordering is violated. Internalizing backend resolution does not change the temporal sequence — it neither helps nor hurts this backstop. Optional upgrades (only if a precise signal is wanted): a non-local-only `clarify_reconciled` sentinel keyed by §3b (needs a registry row + a `_TELEMETRY_ONLY_EVENT_TYPES` phantom-set update); a fail-closed reconcile (loud, but regresses the graceful resume-to-spec path). Recommendation from the design agent: keep the §3b backstop as-is (sufficient, zero cost).

**§3b's backend read STAYS regardless.** Internalizing emit+reconcile removes only the *slug-routing* use of the backend read; the skill still resolves the backend to (1) gate the `cortex-update-item` write-backs in Steps 3/5 and (2) make the §3b gate decision. So the "resolve backend once" line in Step 2 narrows in role — it does not disappear.

---

## Thread 4 — Considerations Hand-off Channel

**The real constraint:** the hand-off is **not** a shell invocation — Skill-tool invocations run **inline** (same model, same conversation). refine substitutes the considerations into research's `$ARGUMENTS` string; research **parses key="value" pairs from free text by prose**. The fragility is that *a model parsing `key="value"` from free text can't reliably tell where a value ends once `=`/`"` appear* — not shell quoting. Therefore **stdin and env vars do not exist** across the boundary (no subprocess, no inherited shell). Any channel that keeps the payload *inside* `$ARGUMENTS` inherits the fragility; any channel that moves it *out* dissolves it.

**Candidate channels:** (b) stdin and (c) env — eliminated (no subprocess). (d) new CLI read/write verbs — rejected as gratuitous ceremony (Write/Read carry no deterministic logic, unlike threads 1-3). Live options: **(e)** implicit `cortex/lifecycle/{slug}/considerations.md` read by slug (research already derives `research.md` from the same slug; zero new arg) vs **(a)** explicit `research-considerations-file=<path>` arg (greppable contract; +1 arg key). Both delete the escaping caveat from both skills.

**Separability: YES, cleanly.** Under any file channel, thread 4 touches **no `refine.py`** and **none of Step 2/Step 5** — only refine **Step 4** (considerations block) + research **Step 1** (a file threads 1-3 never touch), adds **no Python**, near-zero test surface. Zero code/ordering dependency on threads 1-3. The reason to split is *kind-mismatch* (interface redesign vs CLI offload), not size.

---

## Tradeoffs & Alternatives

- **Verb proliferation vs consolidation.** Option A = separate `resume-point` verb. Option B (Tradeoffs agent's "do more with fewer verbs") = one `cortex-refine begin` that stats artifacts + resolves backend + idempotently seeds in one call, returning `{resume_phase, backend}` — folds threads 1+2 into one Step-2 command. **Option C contradicts Thread 1's "keep resume-point read-only & separate"** (see Open Questions / Adversarial #7).
- **Packaging.** Threads 1/2/3 are cohesive (same two files, shared backend mechanism, same test files); threads 2+3 in particular are the same branch in two places and must ship together. **Thread 4 should split out** (different files, different shape, broadest blast radius — it edits `research/SKILL.md`, also invoked standalone — and smallest payoff). Strong consensus across Tradeoffs + Thread-4 + Adversarial.
- **Per-thread "earns its place":** Thread 2 (backend seed) = strongest, no new tracked surface. Thread 3 = ship with 2, *only if* the skill always passes the args and the verb routes by backend (else the prose win evaporates). Thread 1 = marginal as a standalone verb; rides in for free only if consolidated (but consolidation is itself challenged). Thread 4 = weakest payoff (~2 sentences), new untracked cross-skill contract.
- **Web validation:** Microsoft Conductor / Praetorian deterministic-orchestration pieces endorse "LLM nodes do narrow judgment; deterministic nodes do routing" — supports the *direction* but warns against pushing genuine judgment (the kept guards) into rigid code.

---

## Adversarial Review

The adversarial pass verified claims against the code and materially weakened several premises:

1. **Byte-identity is FALSE for `reconcile-clarify` under "always pass flags."** With flags-win precedence (refine.py:156-161), passing `--complexity/--criticality` unconditionally makes the override `to` value come from **flags, not frontmatter** — diverging from today's Context A (which passes no flags → frontmatter wins) whenever the Step-3 write-back failed/was-overridden, frontmatter was hand-edited, or Clarify was skipped on resume. Byte-identity holds only if the CLI additionally **drops the flags when backend resolves `cortex-backlog`** (new, undescribed logic) — or the skill keeps branching (defeating the offload).
2. **"One unconditional call" is leaky** — backend is not the only branch dimension (item-existence; Clarify-ran). Confirmed above.
3. **`Path.cwd()` introduces a third, divergent backend-resolution semantics** vs the canonical `_resolve_user_project_root()` (CORTEX_REPO_ROOT + walk-up). Breaks the run-from-subdirectory and interactive-worktree cases; latent footgun, not a clean choice.
4. **Thread 4 file channel adds a stale-state bug the arg channel lacks.** The arg channel represents "no findings this run" by **absence**; a persisted file survives across runs, so on a refine re-run or `specify.md §2a` loop-back a stale `considerations.md` (prior findings) would be injected when this run Dismissed everything. Implicit-by-slug (e) is worse than explicit (a) — a hidden channel that exists only in lifecycle mode and is invisible to research's standalone path. Mitigation: writer must **always** write the file (empty on no-findings) to preserve absence-as-signal; prefer explicit `--research-considerations-file`; **inject file content, not the path** (SP001/SP002).
5. **§3b fail-safe holds for the non-local silent-skip case (CONCEDED true)** but over-fires (every genuinely-simple non-local feature gets review on each resume — acceptable) and the local "seed always trustworthy" framing has a pre-existing crash-window hole (write-back never landed → resume reads simple/medium → §3b excludes cortex-backlog → skip). **Not introduced or worsened by #322.**
6. **The ADR-0016 conflict is real; the skill-helper carve-out is an undocumented rationalization.** The CLI is **already backend-blind and ADR-compliant today** (it only sees `--backlog-slug` presence; the skill routes by omitting it). Internalizing `resolve_backlog_backend()` **regresses** a clean compliant separation to buy ~4-6 lines of prose, and sets a precedent the next person can cite to add backend logic to `cortex-update-item`. **Cleaner alternative:** pass `--backend {resolved}` as an explicit flag so the CLI stays a dumb arg-actor (no config read, no resolver import) — removes the two-arm prose *without* giving the CLI backend awareness.
7. **School B (`begin`) couples a pure read to a failing write** — a call made just to learn the resume point now also writes `lifecycle_start` and can exit 64/70; if seeding fails the skill can't even learn where to resume. **School A (separate read-only `resume-point`) is the safer split.**
8. **Thread 1 fails the simplicity bar.** The resume tree is pure `is_file()` stat — **there is no judgment to remove**; the actual judgment (Research Sufficiency) stays in the skill, and all four guards get re-encoded as prose anyway. Net: a verb + ~50 LOC + tests + mirror obligation against ~8 lines of the *least-fragile* prose in the file, with no cited misfire. By "complexity must earn its place," Thread 1 is net-negative as a standalone verb.
9. **Verified-clean:** "no new events-registry / parity rows" — TRUE. `is_file()` over `exists()` — marginally better, concede.

---

## Open Questions

These are the decisions Spec must resolve. The first two are **consequential forks raised at the Research Exit Gate** (they reshape scope/architecture and are the user's call); the rest are **deferred to the Spec interview / critical-review** with the stated leaning.

1. **[RESOLVED at Exit Gate — user delegated with guiding principle "CLI handles deterministic behavior; LLM handles judgment"] Keep Thread 1 as a standalone read-only `resume-point` verb (School A).** The resume tree is *deterministic* (`is_file()`→phase), so under the user's principle it belongs in the CLI — the line-count/"earns its place" argument used the wrong yardstick. The three judgment guards (complete→no-prompt/re-run-on-explicit-request; spec-without-research→warn; research-only→Research Sufficiency Check) stay in the skill. School A, not B: do not merge with seed (a `begin` verb couples a pure read to a write that can exit 64/70).

2. **[RESOLVED at Exit Gate — same delegation/principle] Threads 2-3 use a `--backend {resolved}` explicit flag.** The skill resolves the backend via the existing `cortex-read-backlog-backend` CLI and passes the value; the verbs do the deterministic routing on the flag *without resolving backend themselves*. This satisfies "CLI handles deterministic behavior" (the two-arm routing branch leaves the model; all deterministic logic lives in CLIs — resolver + verb) while keeping the consumer verbs backend-blind per shipped ADR-0016 (they never read config). Full internalization is dominated (breaks the ADR + `Path.cwd()` resolver-divergence footgun).

3. **[RESOLVED — follows from Q2] Byte-identity policy for `reconcile-clarify`.** The `--backend` flag governs *only* the `--backlog-slug` handling (whether the verb reads the local frontmatter file). The `--complexity`/`--criticality` flags keep today's exact semantics and the skill passes them exactly as today (Context B / non-local only; Context A on `cortex-backlog` passes none and re-sources frontmatter). So the local-arm override-`to` source stays frontmatter and the rows stay byte-identical — the divergence window the adversarial raised never opens.

4. **[RESOLVED at Exit Gate — packaging] Thread 4 split into its own follow-up ticket.** It aligns with the principle (the `=`/`"` escaping is deterministic string-work the model shouldn't carry → move considerations to a file), so it is *not dropped*. But it is a separable interface redesign (touches the standalone-invoked `research/SKILL.md`, zero dependency on 1-3) with its own stale-state correctness trap (a persisted file must replicate the arg channel's absence=no-findings via always-write-empty; prefer explicit `--research-considerations-file`; inject content not path per SP001/SP002). Channel choice + stale-state handling are deferred to that ticket's own spec/critical-review.

5. **[Deferred to Spec] Ordering-invariant structural upgrade depth.** *Leaning:* keep the existing §3b fail-safe (sufficient, zero cost); invest in the `clarify_reconciled` sentinel only if a precise signal is wanted (registry + phantom-set cost); avoid fail-closed reconcile (regresses resume UX). The `--backend` approach (Q2) doesn't change the temporal sequence, so the existing backstop is unaffected.

6. **[RESOLVED — School A, per Q1] resume-point stays read-only and separate from seed**, not a merged `begin` verb.

7. **[Deferred to implementation] Test churn.** Rewrite `test_refine_non_local_reconcile_branch_is_value_aware` (pins the two-arm structure); preserve the `emit`/`reconcile` wiring-literal anchors, the `specify.md`-delegation ordering anchor, and the §4 "Complexity/value gate" anchor; add a new-subcommand test + a config-present non-local arm test + a config-absent byte-unchanged regression.
