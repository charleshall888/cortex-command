# Lifecycle Skill + Artifact Value Audit

Synthesis of four parallel deep audits commissioned 2026-05-06, plus a pressure-test pass and a skill-creator-lens pass commissioned the same day. Companion to `research/vertical-planning/research.md`.

> **Important: post-pressure-test corrections.** The original audit (sections below) was directionally correct but overconfident on several claims. See "Pressure-test corrections" at the bottom of this file before acting on the recommendations.

## Headline numbers

| Surface | Lines | Estimated reducible | % |
|---|---|---|---|
| Skill corpus (lifecycle + refine + critical-review + discovery, 24 files) | **4,214** | **~1,800–2,200** | **43–52%** |
| Of which: cross-skill duplication collapse alone | — | ~700 | — |
| Per-feature artifact text (mean across 138 archived lifecycles) | ~606 lines / ~910 tokens | ~250 lines / ~500 tokens | ~40% |
| `events.log` per feature (one-time bloat from `clarify_critic` + `critical_review*` blocks) | ~80 lines × 95 features = ~7,600 lines / ~30k tokens | most | most |

**Caveat on estimates**: cuts are calibrated by rating (cut all `dead`+`noise`, ~50% of `marginal`, hold all `valuable` and `load-bearing`). The 43–52% range reflects the gap between conservative (just dedupe) and aggressive (dedupe + content cuts + table trims).

## The single most important finding

**`skills/refine/references/` contains four files that are near-byte-identical to their counterparts in `skills/lifecycle/references/`**, totaling ~700 reclaimable lines, ~17% of the entire skill corpus:

| Pair | Lifecycle lines | Refine lines | Diff |
|---|---|---|---|
| `orchestrator-review.md` | 184 | 183 | **1 line** different (lifecycle has the `P8` Architectural Pattern row) |
| `specify.md` | 186 | 163 | refine drops the trailing `### 5. Transition` + `## Hard Gate` table; **body is byte-identical** |
| `clarify-critic.md` | 167 | 215 | refine adds Parent Epic Loading (~48 net new lines); **rest is identical** — refine is a superset |
| `clarify.md` | 124 | 130 | only §1 Resolve Input differs (refine routes through `cortex-resolve-backlog-item`); **§2–§7 identical** |

**This is the dominant lever.** Every other systemic pattern is smaller. Promoting these to single canonical files (lifecycle owns three, refine owns clarify-critic since it's the superset) saves ~560 lines with zero behavior change.

## The smoking-gun bug

**`skills/refine/SKILL.md` lines 117–136 and 138–157 are the same Alignment-Considerations Propagation block, copy-pasted twice consecutively with one bogus header.** The text *"After clarify-critic returns and dispositions are applied (see Step 3), collect every finding with `origin: 'alignment'`"* appears verbatim, twice. This is a literal copy-paste bug, not design — 21 lines of pure duplication that should just be deleted.

## Top systemic patterns (cross-cutting)

Ranked by line savings × confidence.

| # | Pattern | Lines saved | Risk |
|---|---|---|---|
| 1 | Cross-skill duplication: 4 files in `refine/references/` near-clones of `lifecycle/references/` | ~700 | low (refine SKILL.md already enumerates the deltas) |
| 2 | Inline JSON event schemas duplicating `cortex_command/overnight/events.py` (≥11 instances of `phase_transition` alone) | ~120 | low (canonical schemas already exist in code) |
| 3 | "Hard Gate / Thought vs Reality" Constraints tables — 10+ across corpus, most ceremony | ~75–100 | medium (some rows encode genuine policy; cut selectively) |
| 4 | Conceptual duplication: "binary-checkable acceptance criteria" rubric defined 4× | ~30 | low |
| 5 | "After writing X, update index.md" boilerplate copy-pasted ≥4× | ~24 | low |
| 6 | "Read criticality from events.log" stanza copy-pasted 6× | ~20 | low |
| 7 | The literal duplicated-block bug in `refine/SKILL.md` | 21 | none |
| 8 | Backlog-index sync fallback chain duplicated in `complete.md §2` and `§3` | 9 | low |
| 9 | Loop-back / Sufficiency Check bypass described 3× | ~15 | low |
| 10 | Self-narrative section bodies that just introduce the next section | ~30 | low |

**Total systemic patterns: ~1,050–1,150 lines reclaimable** before touching individual file content.

## Top per-file content cuts

The biggest single in-file targets, ordered by line savings:

| # | File:section | Lines saved | Risk | Justification |
|---|---|---|---|---|
| 1 | `lifecycle/references/implement.md §1a` (Daytime Dispatch, 49–166) | **~95** | low | Reproduces logic that lives in `cortex_command/overnight/daytime_pipeline.py` and `daytime_result_reader.py`. The atomic-write recipe (82–101), tier-1/3 routing (135–148), `dispatch_complete` outcome map (156–164) — all duplicate the module. Collapse to: *"Run the daytime pipeline module; surface its JSON output to user."* |
| 2 | `lifecycle/references/plan.md §1b.b` (Plan Agent Prompt + embedded Plan Format, 22–95) | **~60** | low | Plan Format inside the prompt template (lines 70–95) duplicates §3's canonical template (156–194). Collapse to a 5-line wrapper that says "produce a plan in §3's format." |
| 3 | ~~`critical-review/SKILL.md` worked examples (8 → 2, lines 212–260)~~ **SUPERSEDED — see skill-creator-lens S2 below.** Same line range double-booked between this in-place cut (~30 lines) and S2 extraction (~49 lines). **Recommended path: extract to `references/a-b-downgrade-rubric.md` (S2 wins).** Drop this row from the per-file cuts. | — | — | — |
| 4 | `lifecycle/SKILL.md` Step 3 §6 + Complexity Override (253–260, 294–312) | ~25 | low | Triplet-duplication of the same complexity-override logic. Keep one block. |
| 5 | `critical-review/SKILL.md` Step 2e residue write (294–330) | ~25 | low | Inline bash + python heredoc. Move to `bin/cortex-write-critical-review-residue`; SKILL.md keeps schema + invocation. |
| 6 | `critical-review/SKILL.md` fallback prompt (137–174) | ~25 | medium | Total-failure path rare; restates parallel template. Replace with 4-line directive. |
| 7 | `lifecycle/references/specify.md §2a` Research Confidence Check (38–77) | ~22 | medium | C1/C2/C3 + dual-cycle handling can collapse to 18 lines without behavior loss. |
| 8 | `lifecycle/SKILL.md` Backlog Status Check (76–106) | ~20 | low | Dense conditional tree for a rare path. |
| 9 | `lifecycle/SKILL.md` Create index.md (108–143) | ~18 | low | Drop worked example, keep schema. |
| 10 | `lifecycle/references/research.md §0` Log Lifecycle Start (8–13) | 6 | none | Duplicates SKILL.md Step 3 §4 logging. Already documented as lifecycle-owned. |

**Plus** ~30 more lines from `complete.md §3` (duplicate write-back), ~10 from `plan.md §1b.f` legacy fallback table, ~10 from `lifecycle/SKILL.md` Worktree Inspection Invariant. Total per-file content cuts: **~360 lines.**

## Top artifact-side cuts (per-feature, applied retroactively + going forward)

| # | Section | Population rate | Consumer | Action | Per-feature cost |
|---|---|---|---|---|---|
| 1 | `## Open Decisions` (spec.md) | 77% present, **88% ceremony** ("None — all resolved") | spec §2b push-resolution-upstream check | **Make optional**; default omitted | ~75 tokens × 95 features = ~7,200 tokens |
| 2 | `events.log` `clarify_critic` blocks | 95 emissions, ~80 lines each | None outside same-session | **Move to `events-detail.log`** or drop; spine events stay | ~30,000 tokens cumulative |
| 3 | `## Scope Boundaries` (plan.md) | 53% present, often duplicates spec's `## Non-Requirements` | NO programmatic consumer | **Delete from template**; optional pointer to spec Non-Requirements | ~5,500 tokens cumulative |
| 4 | `## Edge Cases` (spec.md) — bullet bloat | 99% present, **73% have 6+ bullets** | reviewer (verbatim); orch-review S2 (presence-only) | **Cap at 6 bullets**; overflow → backlog ticket | ~81,000 chars (~20k tokens) cumulative |
| 5 | `index.md` body wikilinks | 100% written | **Only `tags:` frontmatter is read** | **Compress to frontmatter-only** | ~7,000 tokens cumulative |
| 6 | `**Architectural Pattern**` field | 1.4% (2/138 plans) | synthesizer (critical-only); P8 presence-only | **Gate to critical-tier in template**; remove from default plan format | ~tiny per-feature, but stops "presence ceremony" leak into all plans |
| 7 | `## Stage 2: Code Quality` (review.md) | conditional — when Stage 1 passes, devolves to ~4 generic bullets | NO programmatic consumer | **Compress to single line "OK / concerns: …"** | ~3,500 tokens cumulative |
| 8 | End-of-plan `## Verification Strategy` | 99% present | `overnight/report.py:725` reads as "How to try" | **Compress to ≤5 lines** (consumer is happy with one user-runnable end-to-end command) | ~3,000 tokens cumulative |
| 9 | `## Veto Surface` (plan.md) | 53% present, mean 4.9 bullets | NO programmatic consumer | **Make optional** (status quo allows this; document explicitly) | ~minor |

**Net per-feature artifact reduction**: 250–350 lines / 500–700 tokens going forward. Retroactively across 146 archived features: ~70k–100k tokens of stored bloat.

## Dead `events.log` event types (emitted but never consumed)

Confirmed consumers (across `metrics.py`, `report.py`, `dashboard/data.py`, `overnight/status.py`):
**Consumed (alive)**: `dispatch_start`, `dispatch_complete`, `dispatch_error`, `feature_complete`, `lifecycle_start`, `phase_transition`, `review_verdict`, `batch_dispatch`, `circuit_breaker`, `feature_merged`, `merge_conflict_classified`, `retry_attempt`, `round_complete`, `round_start`, `task_output`, `session_start`, `session_complete`, `turn_complete`, `feature_start`, `worker_no_exit_report`, `worker_malformed_exit_report`, `sandbox_soft_fail_active`. About 22 consumers.

**Emitted-but-unconsumed (dead)**: `clarify_critic`, `orchestrator_review`, `critical_review`, `critical_review_apply`, `critical_review_complete`, `critical_review_dispositions`, `critical_review_applied`, `critical_review_apply_round2`, `discovery_reference`, `orchestrator_dispatch_fix`, `complexity_override`, `criticality_override`, `plan_approved`, `spec_approved`, `lifecycle_paused`, `lifecycle_resumed`, `dispatch_progress`, `backlog_write_failed`, `task_partial`, `spec_amendment`, `spec_revision`, `confidence_check`, `drift_auto_apply_skipped`, `scope_expansion`, `feature_failed`, `brain_decision`, `feature_paused`, `feature_deferred`, `ask_items_resolved`, `atomic_commit`, `scheduling_escalate`, `candidates_refresh`, `r18_probe_complete`, `r18_verdict_resolved`, `task_cancelled`, `lifecycle_abort`, `runner_sandbox_fix`, `test_portability_fix`, `feature_reverted`, `req1_verified`, `scope_followup`, `non-prescriptive-tickets-and-refine`, `plan_amendment`, `brain_unavailable`, `batch_gate_closure`, `implement_complete`, `scope_amendment`, `spec_reopened`, `requirements_updated`. **About 49 dead event types.**

Many serve as same-session breadcrumbs for the agent emitting them; some (e.g., `requirements_updated`) are written then never read by anything. **Recommendation**: 2-tier scheme — "spine" events stay in `events.log`, large session-internal blocks (`clarify_critic`, `critical_review*`) move to `events-detail.log` or are inlined into the artifact they affected.

## Stale references found

| # | Reference | Location | Reality |
|---|---|---|---|
| 1 | `claude/common.py` | `lifecycle/SKILL.md:3, :35` | File is at `cortex_command/common.py` |
| 2 | `cortex-worktree-create.sh` (unqualified) | `lifecycle/SKILL.md:378`, `implement.md:206` | Lives at `claude/hooks/cortex-worktree-create.sh` |
| 3 | `bin/overnight-status` | `implement.md:68` | Not present anywhere |
| 4 | `backlog/generate_index.py` | `complete.md:42, :65` | Lives at `cortex_command/backlog/generate_index.py` |
| 5 | `update_item.py` | `lifecycle/clarify.md:113`, `refine/clarify.md:119`, `refine/SKILL.md:231` | Renamed to `cortex-update-item` CLI |

## Per-file rankings (ratings summary)

| File | Lines | Reducible | Notes |
|---|---|---|---|
| `lifecycle/SKILL.md` | 380 | ~150 (~40%) | Triplet-duplication of complexity-override logic; verbose Backlog Status Check; stale `claude/common.py` reference |
| `lifecycle/references/clarify.md` | 124 | ~15 (~12%) | Confidence assessment is load-bearing; Constraints table is noise |
| `lifecycle/references/clarify-critic.md` | 167 | **delete entirely** (167) | Refine's version is a superset; promote refine to canonical |
| `lifecycle/references/research.md` | 204 | ~50 (~25%) | §0 duplicates SKILL.md; §1a synthesis template duplicates §3 artifact template |
| `lifecycle/references/specify.md` | 186 | ~35 (~19%) | §2a Research Confidence Check + §2b Pre-Write Checks are valuable; Hard Gate is noise |
| `lifecycle/references/plan.md` | 309 | **~110 (~36%)** | §1b.b Plan Format duplicates §3 (60 lines saved); per-task templates 1+2 redundant; Code Budget duplicate |
| `lifecycle/references/orchestrator-review.md` | 184 | ~15 (~8%) | All checklist rows are real gates; Constraints table trim |
| `lifecycle/references/implement.md` | 301 | **~115 (~38%)** | §1a Daytime Dispatch is the largest single bloat target in the audit |
| `lifecycle/references/review.md` | 219 | ~30 (~14%) | Reviewer prompt + verdict JSON are load-bearing; Stage 2 collapse |
| `lifecycle/references/complete.md` | 102 | ~30 (~29%) | §3 duplicates §2's index-sync fallback chain |
| `refine/SKILL.md` | 233 | ~34 (~15%) | **Includes 21 lines of literal copy-paste bug**; Constraints noise |
| `refine/references/clarify.md` | 130 | **delete (130)** | Lifecycle adopts `cortex-resolve-backlog-item` and points |
| `refine/references/clarify-critic.md` | 215 | keep — promote canonical | Becomes the single source; lifecycle deletes its 167-line copy |
| `refine/references/orchestrator-review.md` | 183 | **delete (183)** | Refine reads lifecycle copy |
| `refine/references/specify.md` | 163 | **delete (163)** | Refine reads lifecycle copy |
| `critical-review/SKILL.md` | 365 | ~92 (~25%) | Worked-examples 8→2 (30); residue-write extraction (25); fallback prompt (25); domain examples (12) |
| `discovery/SKILL.md` | 71 | 0–3 | Tight |
| `discovery/references/clarify.md` | 65 | ~5 | Constraints noise |
| `discovery/references/research.md` | 154 | ~10 in-file, ~70 via shared base extraction with lifecycle | Signal-format contract is load-bearing |
| `discovery/references/decompose.md` | 149 | ~15 | Surface-pattern helper list noise |
| `discovery/references/auto-scan.md` | 87 | 0 | Tight |
| `discovery/references/orchestrator-review.md` | 133 | ~5 | Path differences make cross-skill collapse risky |

## Sections that look bloated but are load-bearing — DO NOT CUT

1. **`SKILL.md` Phase Detection table (lines 41–66)** — directly consumed by `cortex_command/common.py:_cli_detect_phase`. Phase value vocabulary is routing primary key.
2. **`orchestrator-review.md` Checklists (R1–R5, S1–S6, P1–P8)** — consumed verbatim by Fix Agent Prompt Template at line 92. Removing rows breaks fix-agent.
3. **`plan.md §1b.f` route on verdict+confidence** — mirrored in `cortex_command/overnight/runner.py:954` and `pipeline/dispatch.py:620`. Schema_version=2 envelope is real contract.
4. **`review.md §2` Reviewer Prompt verdict JSON shape** — fields parsed for `review_verdict` event by `metrics.py:221`. The strict "do NOT use alternative field names" wording is parser-protective.
5. **`implement.md §2.d` Checkpoint** — `git log HEAD..worktree/{name}` invariant directly references `cortex-worktree-create.sh:30` branch naming and the SKILL.md security-check workaround. Removing re-introduces the compound-cd-git security prompt.
6. **`refine/clarify-critic.md` Parent Epic Loading branching** — five status branches each with distinct observable behavior (warnings vs silence vs section-omit), enforced by `bin/cortex-load-parent-epic`.
7. **`discovery/decompose.md` R2(b) research-side premise check + R5 flag propagation** — every clause maps to a real failure mode (vendor-citation Value claims, consolidation flagging behavior).
8. **`specify.md §2a` Research Confidence Check + §2b Pre-Write Checks** — concrete failure-mode rules (git two-dot vs three-dot, function-behavior verification, file-path existence) prevent specific spec-quality regressions.
9. **Per-task `Files` and `Depends on` fields** — the only plan fields the parser consumes (`pipeline/parser.py:332-374`). Drives batch dispatch graph + worktree merge.
10. **`spec.md ## Non-Requirements`** — 100% present, 100% substantive, read verbatim by reviewer + S4 gate.

## "If you only do three things"

1. **Collapse the four duplicated `refine/references/` files** + delete the duplicated-block bug in `refine/SKILL.md` lines 117–157. **~720 lines reclaimed (17% of corpus). Zero behavior change.**
2. **Cut `implement.md §1a` (Daytime Dispatch) to a 25-line summary** + dedupe `plan.md §1b.b` Plan Format against `§3` canonical. **~155 lines reclaimed (4% of corpus). Single-largest non-dedupe cuts.**
3. **Make `## Open Decisions` optional + delete `## Scope Boundaries` from plan template + compress `index.md` to frontmatter-only + cut event-log `clarify_critic` block events to a detail file.** **~30k tokens of cumulative artifact bloat reclaimed; ~250 lines saved per future feature.**

Combined: ~875 lines off the skill corpus + ~250 lines × every future feature in artifacts. Roughly 21% of the corpus + a permanent per-feature reduction.

## How this changes the proposed decomposition

The original epic 171 had 9 children. The audit reveals:

- **Original ticket 176 (audit) is DONE** — this document is the deliverable.
- **Original tickets 177/178/179 (restructure each ref file)** become much more concrete and have specific cuts identified, but they're now substantially smaller because of the cross-skill collapse work below.
- **New tickets emerge that weren't in the original decomposition**:
  - Cross-skill duplication collapse (the highest-leverage move, completely missed by the original framing)
  - The literal duplicated-block bug fix
  - Stale-reference fixes (5 references)
  - `events.log` 2-tier scheme
  - `index.md` frontmatter-only compression
  - Architectural Pattern field gating to critical-only
  - Open Decisions / Scope Boundaries / Edge Cases / Stage 2 / Verification Strategy compression
- **Original artifact-side tickets (172/173 outline + phases sections)** still apply but their integration changes: they should land AFTER the cross-skill collapse so the new sections live in a single canonical home, not get added to two duplicated copies.

---

# Pressure-test corrections + skill-creator-lens additions

A pressure-test pass and a skill-creator-lens pass were commissioned after the original four-agent audit. The pressure-test materially weakens several original claims; the skill-creator-lens surfaces a class of issues the prior audit missed entirely. This section is the corrected, action-ready synthesis.

## Pressure-test corrections to the original audit

### Verified safely (proceed as audit recommended)

| Claim | Verification |
|---|---|
| `orchestrator-review.md` lifecycle/refine differs by 1 line (P8 row only) | **Verified by diff.** Lifecycle 184, refine 183. Body byte-identical. |
| `specify.md` lifecycle/refine body byte-identical except trailing 23 lines | **Verified by diff.** Refine drops `### 5. Transition` + `## Hard Gate`. |
| `refine/SKILL.md` lines 117–157 contain 21 lines of literal copy-paste duplication | **Verified by byte-diff.** Two `### Alignment-Considerations Propagation` headings with identical bodies. Pure bug. |
| `Architectural Pattern` field 1.4% population | **Verified.** 2 of 141 plans contain it. |
| `## Open Decisions` 88% ceremony rate | **Verified.** All 5 sampled archive specs are "None" / boilerplate. |
| `## Scope Boundaries` no programmatic consumer | **Verified by grep.** Zero matches in `cortex_command/`, `hooks/`, `.py`, `.sh` files. |
| Parity tests handle deletion correctly | **Verified.** `tests/test_dual_source_reference_parity.py` discovers pairs via glob; `justfile build-plugin` uses `rsync -a --delete` which prunes. |

### Falsified or weakened (revise before acting — ordered by severity, not by claim text)

| Severity | Claim | Correction |
|---|---|---|
| 🔴 **NEAR-MISS RUNTIME RISK** | **49 dead `events.log` event types** | **OVERCONFIDENT.** The audit grepped Python consumers but missed skill-`.md` reads, which are the dominant consumer family. Verified counter-examples: `complexity_override` is read by `lifecycle/SKILL.md:64,66, :256, :305` and 5+ phase ref docs (drives complexity-tier routing); `criticality_override` same (drives criticality-tier routing); `confidence_check` is read by `specify.md §2a` (cycle counting at line 57) and §2a-residue callout at line 103; `requirements_updated` is read by `morning-review/walkthrough.md:303,305`. **Three of these four are routing primitives — moving them to a "detail" log would have stripped Claude's tier-routing signal.** **The 49-event "dead" list is starting hypothesis, not verified truth — DO NOT use as basis for a 2-tier scheme without a complete consumer audit including skill-md reads, tests, hooks, and bin/ scripts.** Note: 4-of-49 sample bounds nothing; remaining 45 events have no per-event verdict. Stream G's deferral is currently a punt unless G-pre is sized as a concrete deliverable with a per-event-classification table as its acceptance criterion. |
| **`## Open Decisions` is pure ceremony — make optional** | **HIDDEN CONSUMER.** `lifecycle/SKILL.md:256, :305` reads the Open Decisions **bullet count** for the Specify→Plan complexity escalation gate (≥3 bullets auto-escalates to Complex tier). Making the section optional silently disables this escalation. **This is a behavior change, not a ceremony cut.** Mitigations: re-anchor escalation on a different signal, OR make the optionality apply only to specs where the section would otherwise be "None." |
| **`plan.md §1b.b` saves 60 lines via dedupe with §3** | **OVERSTATED.** §1b.b template includes `**Architectural Pattern**: {category} — {1-sentence differentiation}` (line 75) and the closed-enum directive (line 47). §3 canonical does NOT include Architectural Pattern but DOES include Veto Surface and Scope Boundaries. They are **structurally different on purpose** — §1b.b is the critical-tier dual-plan format. Realistic dedupe: **~20 lines of overlap, not 60.** |
| **`implement.md §1a` cuttable to 25 lines** | **OVERSTATED.** §1a contains genuine skill-side logic the pipeline module does NOT implement: uncommitted-changes guard with demote-and-warn logic, runtime probe with explicit fail-open (lines 19–38), double-dispatch guard via PID liveness, overnight-concurrent guard, polling loop with user-pause-at-30-iterations, `dispatch_complete` event log writing. These are harness-level concerns requiring AskUserQuestion / sandbox controls / in-conversation memory — they cannot move to the pipeline module. **Realistic cut: ~30–40 lines (atomic-write recipe at 82–101 + verbatim outcome map at 156–164), not 95.** |
| **`clarify-critic.md` lifecycle ↔ refine — refine is a clean superset** | **NOT CLEAN.** Refine's version: (i) interleaves Parent Epic Loading via 7+ splice points across the body (not append-only), (ii) **changes schema** — `findings` becomes `array of {text, origin}` objects, not strings, (iii) adds REQUIRED `parent_epic_loaded: <bool>` field, (iv) changes Constraints table row at line 164. Promoting refine's version to canonical means lifecycle starts emitting the new schema; legacy lifecycle-side `clarify_critic` events lack `parent_epic_loaded` and use bare-string findings. **Risk:** archived events break consumers expecting the new schema unconditionally. Mitigation: audit all `clarify_critic` consumers for legacy-tolerant fallback before adoption. |
| **`clarify.md` adoption of `cortex-resolve-backlog-item` is a no-op** | **NOT NO-OP.** Lifecycle's current §1 does ad-hoc Python scanning (numeric ID + kebab slug + title fuzzy match). Refine's helper has its own predicate (set-theoretic union of raw substring AND slugified substring). These match different sets, particularly for inputs with uppercase or punctuation. **Adopting refine's flow changes which backlog items resolve unambiguously vs as ambiguous.** Test before deletion. |

### Realistic reduction estimate (revised)

Original headline: **~43–52% reducible.** Pressure-test correction: **~25–30%, ~1,050–1,250 lines** is the realistic conservative cut. The high end of the original estimate assumed events.log work that requires substantially more analysis than the audit performed.

## Skill-creator-lens additions (new findings)

The prior audit measured content density. The skill-creator-lens pass measures skill-design quality. These are mostly orthogonal to the prior audit's findings.

### Description-trigger gaps across all four skills

The SKILL.md `description` field is the primary trigger mechanism. All four descriptions have measurable gaps in trigger comprehensiveness or sibling disambiguation:

- **lifecycle**: missing casual phrasings ("start a feature", "build this properly", "implement <feature>"). Path-required clause ("Required before editing any file in `skills/`...") is a pushy MUST in disguise that violates OQ3 spirit. No "Different from /cortex-core:refine" disambiguator. Will under-trigger on natural phrasings + over-trigger on trivial edits in the named paths.
- **refine**: missing intent phrasings ("spec this out", "tighten the requirements", "lock in the spec"). No "Different from /cortex-core:lifecycle" disambiguator (creates routing ambiguity since both produce research.md + spec.md). Description is short relative to siblings.
- **critical-review**: best-written of the four. Missing some natural phrasings ("poke holes in the plan", "stress test the spec", "is this actually a good idea", "review before I commit"). Has the model `/devils-advocate` differentiator (exemplary).
- **discovery**: most comprehensive trigger list. Has "Different from /cortex-core:lifecycle" but missing "Different from /cortex-core:research" (research and discovery share "investigate this feature" / "research this topic" triggers).

### Progressive disclosure: TOCs missing on every >300-line file

| File | Lines | Has TOC? |
|---|---|---|
| `lifecycle/SKILL.md` | 380 | **No** |
| `lifecycle/references/plan.md` | 309 | **No** |
| `lifecycle/references/implement.md` | 301 | **No** |
| `critical-review/SKILL.md` | 365 | **No** |
| `discovery/references/research.md` | 154 | Yes — only file with one |

Skill-creator framework requires TOCs on >300-line reference files. All four offenders need them. Discovery's research.md is the template to follow.

### Content-locality mistakes (high leverage)

These are conditional content blocks loaded on every invocation — strong candidates for extraction to references/, NOT visible from the prior audit's content-density lens:

| File:section | Lines | Currently | Should be |
|---|---|---|---|
| `lifecycle/SKILL.md` Step 2 (Backlog Status Check + Create index.md + Backlog Write-Back + Discovery Bootstrap, lines 76–208) | ~133 | Loaded every lifecycle invocation | **Split**: first-invocation logic (Discovery Bootstrap, initial Create index.md) → `references/state-init.md`; **re-entrant logic (Backlog Write-Back, Open Decisions bullet-count read for Specify→Plan escalation gate) STAYS in SKILL.md** — Backlog Write-Back fires every phase transition, escalation read is re-entrant. ⚠ Original recommendation incorrectly bundled re-entrant with one-time. |
| `lifecycle/SKILL.md` Parallel Execution + Worktree Inspection (lines 350–380) | ~30 | Loaded every invocation | `references/parallel-execution.md` (fires only when running concurrent lifecycles) |
| `lifecycle/references/plan.md` §1b Competing Plans (22–144) | ~122 | Loaded every Plan invocation | `references/plan-competing.md` (critical-tier only) |
| `lifecycle/references/research.md` §1a Parallel Research (45–140) | ~95 | Loaded every Research invocation | `references/research-parallel.md` (critical-tier only) |
| `lifecycle/references/implement.md` §1a Daytime Dispatch (49–166, **after Stream B trim to ~75 lines**) | ~75 (NOT 115) | Loaded every Implement invocation | `references/implement-daytime.md` (daytime-dispatch path only). ⚠ Extraction target is ~75 lines after pressure-test-corrected Stream B trim, not the original 115. |
| `critical-review/SKILL.md` 8 worked examples (212–260) | ~49 | Loaded every critical-review invocation | `references/a-b-downgrade-rubric.md` (only relevant mid-rubric). **Note: this row supersedes per-file cut #3 above (same line range, can't double-book).** |

**Net SKILL.md sizes after extraction:** lifecycle 380→~280 (state-init split keeps re-entrant logic resident), critical-review 365→~250, plan.md 309→~190, research.md 204→~110, implement.md 301→~225 (post-Stream-B trim retained ~75 §1a lines stay). Most comfortably under the 300-line TOC threshold.

> **⚠ Critical-review correction: extraction requires explicit trigger prose in parent SKILL.md.** Cortex's progressive-disclosure model has no runtime mechanism for Claude to detect "first invocation per feature" / "critical-tier only" / "daytime path only" conditions. Each extracted file's parent SKILL.md must add explicit "if X, read references/Y.md" prose, OR the extracted file is loaded every time anyway (no savings) OR skipped when needed (correctness regression). This adds ~3-5 lines per extracted file × 6 files = ~25 lines of trigger prose back into parent SKILL.md surfaces — not free.

> **⚠ Net savings revised: ~300 lines (NOT 440).** Original ~440 figure was unsourced arithmetic; the table sums to ~544 extracted, but after (a) keeping re-entrant state-init logic resident, (b) accounting for Stream B's pressure-test-corrected §1a trim (~75 not 115), (c) subtracting trigger-prose overhead in parent files, and (d) reconciling the worked-examples double-book, realistic net is **~300 lines off hot-path context**.

This is still a class of cuts the prior audit missed — it focused on what's redundant rather than what's conditional. **Stream B trims and Stream C2 extraction overlap arithmetically on §1a, §1b.b, and worked-examples line ranges; savings are partial-stack, not full-stack.**

### Cross-skill triggering reliability

Four issues found in the skill-to-skill handoff protocols (post-critical-review correction; #5 dropped):

1. **lifecycle → refine** uses "**Read `skills/refine/SKILL.md` verbatim**" instruction at SKILL.md:220. Fragile — no fallback if file unreadable. **Failure mode**: lifecycle silently completes Clarify with a paraphrase. Fix: add "if the file is unreadable, halt and surface the error" sentence. **Halt-on-fail is the canonical policy across all cross-skill invocations** — soft-skip silently degrades quality on the load-bearing gates that justified the invocation.
2. **lifecycle → critical-review** auto-trigger lives in `references/plan.md:270` ("Run when tier = complex"), not in SKILL.md. **Failure mode**: a model that reads only SKILL.md misses the trigger. Fix: lifecycle SKILL.md's Criticality Behavior Matrix should explicitly call out critical-review fires after plan approval for complex tier.
3. **refine → lifecycle** handoff is implicit, not declared. Refine ends with "ready for overnight execution" but doesn't tell user how to start. Fix: refine Step 6 should append "Next: invoke `/cortex-core:lifecycle <slug>` to plan and build."
4. **discovery → backlog → refine** chain has no integration test. A refactor renaming `discovery_source` → `research_source` would silently break.

> **DROPPED via critical-review (2026-05-06)**: a fifth issue had recommended runtime fallbacks for "skill failed to load." That failure mode does not exist at runtime in cortex's plugin-only deployment — cortex-core is a single plugin containing all four skills, and "skill not installed" is an install-time precondition with no in-conversation API for sibling SKILL.md to detect. The runtime concern is dominated by Stream E's E3 (reference-file path resolution test) at CI time, plus issue #1's halt-on-fail policy at runtime. Adding fallback ceremony would have introduced ~30 lines of dead branching that biases Claude toward soft-skip.

### OQ3 violations (caps-MUST instances)

Sampled 10 instruction blocks. **4 of 10 violate OQ3** (cortex's own anti-MUST policy post-Opus-4.7):

- `lifecycle/references/review.md:64,72,78,80` — 4 MUST/CRITICAL instances on the verdict JSON format. Defensible escalation candidate IF the OQ3 evidence trail (events.log F-row + effort=high failure) is added; otherwise should be softened.
- `refine/references/clarify-critic.md:26,155,159` — 3 MUST instances. Marginal; should be softened with WHY explanation instead.

### Frontmatter asymmetry

| Field | lifecycle | refine | critical-review | discovery |
|---|---|---|---|---|
| `argument-hint` | ✓ | ✓ | **missing** | ✓ |
| `inputs`/`outputs` | ✓ | ✓ | **missing** | ✓ |
| `preconditions` | ✓ | ✓ | **missing** | ✓ |
| `precondition_checks` | ✓ | missing | missing | missing |

`critical-review` is invoked with `<artifact-path>` argument per `plan.md:330` but declares no input. Add the missing fields.

### Test gaps (new class)

Prior audit didn't surface these because they're test-design issues, not content-density issues:

1. **No description-triggering snapshot tests.** A casual edit dropping "prepare for overnight" from refine's description silently breaks routing. Need `tests/test_skill_descriptions.py` asserting each description contains a curated set of trigger phrases.
2. **No cross-skill handoff integration tests.** lifecycle→refine, refine→lifecycle, lifecycle→critical-review handoffs aren't exercised end-to-end.
3. **No description false-positive tests.** No test asserting "given input X, skill Y should NOT trigger."
4. **No reference-file-cited path tests.** `plan.md:107` references `plugins/cortex-core/skills/critical-review/SKILL.md:176-182` — line numbers are extremely brittle. Need a CI test that all `<file>:<line>` references in skills/ resolve.
5. **No skill-size budget test.** Skill-creator says SKILL.md ≤500 lines; nothing enforces it. lifecycle (380) and critical-review (365) are close to the cap.

### Five additional concerns missed by prior audit (priority order)

- **P0**: refine SKILL.md duplicated block (already known; reconfirmed).
- **P1**: critical-review's 8 worked examples (lines 212–260) are conditional content — extract to references/.
- **P2**: lifecycle SKILL.md path-required clause is a hidden MUST violating OQ3. Convert to soft routing.
- **P3**: No "what I am NOT for" / sibling disambiguator on lifecycle and refine descriptions.
- **P4**: Line-number pointers (`plugins/cortex-core/skills/critical-review/SKILL.md:176-182`) are brittle. Replace with stable section anchors and add CI test.

## Recommended phased sequencing (pressure-test-aware)

The original "if you only do three things" recommendation was over-aggressive. The pressure-test recommends 7 phases, hardest moves last:

| Phase | Move | Lines | Risk | Notes |
|---|---|---|---|---|
| 1 | Stale-ref fixes (5 paths) + duplicated-block bug fix | ~26 | None | Zero-risk; do today |
| 2 | Collapse `orchestrator-review.md` + `specify.md` (refine reads lifecycle) | ~346 | Low | Verified safe by diff + parity tests |
| 3 | Promote refine's `clarify-critic.md` to canonical AFTER auditing all `clarify_critic` consumers for legacy-tolerant fallback | ~167 | Medium | Schema-aware adoption required |
| 4 | Switch lifecycle's `clarify.md §1` to use `cortex-resolve-backlog-item` THEN delete refine's copy | ~124 | Low-medium | Predicate-equivalence test required first |
| 5 | Trim `implement.md §1a` (~30–40 lines, NOT 95) + `plan.md §1b.b` overlap with §3 (~20 lines, NOT 60) | ~50 | Medium | Preserve skill-side guards |
| 6a | Architectural Pattern → critical-tier-only in template | minor | Low | Template gate change only |
| 6b | Scope Boundaries → delete | minor | Low | Verified no consumer |
| 6c | index.md → frontmatter-only | minor | Medium | Confirm no Obsidian-vault breakage |
| 6d | **DO NOT make Open Decisions optional** until escalation gate is re-anchored on a different signal | — | High | Blocked on re-anchor work |
| 7 | events.log 2-tier scheme | high | High | Blocked on a complete consumer table including all skill-md reads. Treat the 49-event "dead" list as starting hypothesis, not truth. Explicitly preserve `complexity_override`, `criticality_override`, `confidence_check`, `requirements_updated` in the spine. |
| **Skill-creator-lens additions (run in parallel with phases 5–6)** | | | | |
| S1 | Add TOCs to plan.md, implement.md, lifecycle/SKILL.md, critical-review/SKILL.md | minor | None | Pure documentation |
| S2 | Extract conditional content (5 blocks) to references/ | **~300 lines reducible** (revised down from 440 — see Critical-Review corrections at the bottom of this file: state-init.md is partly re-entrant, ~75 of the original ~115 implement.md §1a stays after Stream B trim, savings stack arithmetic was over-counted) | **Medium** (revised up from Low-medium — accounts for: 6 new dual-sourced files × parity tests, mirror sync, edit coordination, and the requirement that parent SKILL.md add explicit trigger prose for each extracted reference since cortex's progressive-disclosure model has no runtime gate Claude can self-detect for "first invocation" / "critical-tier" / "daytime" conditions) | Stacks partially with cross-skill collapse — savings are ~300 net, not 440 |
| S3 | Description trigger improvements (4 skills) + sibling disambiguators | minor | None | Pure description edits |
| S4 | Soften OQ3 violations in `review.md:64-80` + `clarify-critic.md:26,155,159` OR document escalation evidence | minor | None | Policy compliance |
| S5 | Add 5 missing test classes | new tests | None | Net positive — catches regressions |
| S6 | Frontmatter symmetry (add missing fields to critical-review) | minor | None | |
| S7 | Replace line-number pointers with section anchors | minor | None | Brittleness fix |

### Realistic total reduction (post-pressure-test, post-critical-review)

| Source | Lines |
|---|---|
| Cross-skill collapse (phases 1–4) | ~663 |
| Skill-side trims (phase 5) | ~50 |
| Conditional extraction (skill-creator S2) | **~300** (revised down from 440 — net of trigger-prose overhead, re-entrant state-init logic that stays resident, Stream B arithmetic dependency, worked-examples double-book reconciliation) |
| Bug fix (phase 1) | 21 |
| Stale refs (phase 1) | ~5 (rewrites, not deletions) |
| Artifact cuts (6a–6c) | ~minor per template + accumulated artifact savings |
| **Phase 7 events.log** | **deferred** until consumer table built (G-pre delivers per-event verdict table as acceptance criterion — see Critical-Review corrections) |

**Total skill-corpus reduction: ~1,000–1,050 lines** (~24–25% of corpus), with another ~300 lines of context-budget reduction from conditional extraction (S2, **partial stack**). Conservative estimate after critical review.

> **Critical-Review corrections (2026-05-06)**: this audit was reviewed by parallel adversarial reviewers + Opus synthesizer. **Five A-class corrections were applied inline above**: (1) the worked-examples double-book between per-file cut #3 and S2 was resolved in favor of S2 extraction; (2) cross-skill issue #5 (skill-failed-to-load fallback) was DROPPED — targeted a runtime failure mode that doesn't exist in cortex's plugin-only deployment; (3) S2 risk re-rated from Low-medium to Medium (6-file maintenance burden + trigger-prose requirement); (4) state-init.md extraction split — re-entrant logic stays resident, only first-invocation logic extracts; (5) events.log overconfidence elevated to NEAR-MISS RUNTIME RISK severity in the falsified-claims table (stripping routing primitives would have broken tier detection). **Two scope decisions are held for the user — see "Held for user" at the very bottom.**

## How this changes the proposed decomposition (revised)

The revised epic 171 needs 14–16 children, not 9, and the order is now constrained:

**Stream Z (zero-risk, do today)**:
- Z1: Fix duplicated-block bug in `refine/SKILL.md`
- Z2: Fix 5 stale references

**Stream A (cross-skill collapse, phased by safety)**:
- A1: Collapse `refine/references/orchestrator-review.md` (low-risk; lifecycle canonical)
- A2: Collapse `refine/references/specify.md` (low-risk; lifecycle canonical with §5 skip enumerated)
- A3: Promote refine's `clarify-critic.md` to canonical + audit consumers (medium-risk; schema-aware)
- A4: Lifecycle adopts `cortex-resolve-backlog-item` + delete refine's `clarify.md` (low-medium-risk; predicate test)

**Stream B (skill-side content trims)**:
- B1: Trim `implement.md §1a` (~30–40 lines) preserving skill-side guards
- B2: Trim `plan.md §1b.b` overlap with §3 (~20 lines)
- B3: Cut critical-review fallback prompt + extract residue write to bin/
- B4: Cut critical-review worked examples to 2

**Stream C (skill-design improvements — skill-creator-lens)**:
- C1: Add TOCs to 4 files (plan.md, implement.md, lifecycle SKILL.md, critical-review SKILL.md)
- C2: Extract conditional content (5 blocks) to references/
- C3: Description-trigger fixes + sibling disambiguators across all 4 SKILL.md
- C4: Soften OQ3 violations OR document evidence trail per cortex policy
- C5: Frontmatter symmetry (add `argument-hint`, `inputs`, `outputs`, `preconditions`, `precondition_checks` to critical-review)

**Stream D (artifact-side cuts, gated)**:
- D1: Architectural Pattern → critical-tier-only (low-risk)
- D2: Scope Boundaries → delete (low-risk)
- D3: index.md → frontmatter-only (medium-risk)
- D4: **BLOCKED**: Open Decisions optional — depends on D-pre (re-anchor Specify→Plan escalation on different signal)
- D-pre: Re-anchor escalation gate before D4 can proceed

**Stream E (test infrastructure)**:
- E1: `tests/test_skill_descriptions.py` (snapshot trigger phrases)
- E2: Cross-skill handoff integration tests
- E3: Reference-file path resolution test (catches stale `<file>:<line>` pointers)
- E4: Skill-size budget test

**Stream F (vertical-planning adoption — original goal)**:
- F1: Add `## Outline` section to plan.md template (lands AFTER A1–A2 collapse so single canonical home)
- F2: Add `## Phases` section to spec.md template (lands AFTER A2 collapse)
- F3: New P9 + S7 orchestrator-review gates
- F4: Plan parser regression test
- F5 (optional): `cortex plan-outline` topological renderer

**Stream G (DEFERRED until ready)**:
- G1: events.log 2-tier scheme — requires complete consumer table including skill-md reads. Blocked on G-pre.
- G-pre: Build consumer table for every events.log event type (Python + skill-md + dashboard + report).

That's 14–16 children depending on whether F5, D4/D-pre, and G/G-pre are scoped in.

---

## Resolved holds (2026-05-06)

**Hold 1 — Specify→Plan and Research→Specify escalation gates.** Resolution: **keep both gates**. Inspecting the actual gate code (`lifecycle/SKILL.md:244-260, 294-312`), both auto-escalate `simple` → `complex` (≥3 Open Decisions bullets in spec, or ≥2 Open Questions bullets in research). Complex tier triggers `/cortex-core:critical-review`, runs orchestrator-review (which `low+simple` skips), and may shift model selection downstream. Both gates are kept; D4 (make Open Decisions optional) remains BLOCKED in the decomposition because making the section optional would silently disable D-gate escalation.

The compression direction: **Tier 1 in-skill compression** (deduplicate the gate description that currently appears twice in SKILL.md, collapse two-gate prose into one unified paragraph, replace inlined `complexity_override` JSON with a schema pointer) — **~40 lines off SKILL.md, zero behavior change.** Goes into Stream B as a new ticket. Plus **Tier 3 hook migration** — move both gates to a deterministic Python hook (`cortex-complexity-escalator`) on research→specify and specify→plan transitions, removing gate logic from SKILL.md entirely. **Additional ~25 lines off SKILL.md, gate execution moves out of model context entirely** (no token spend at gate-evaluation time, deterministic behavior). New Stream H.

**Hold 2 — Stream C scope.** Resolution: **accept Stream C as currently scoped**. The critical-review's "imported heuristics may not transfer" concern was specific to issue #5 (runtime fallback for skill-unavailable), which was already dropped. The remaining Stream C items have local cortex justification: C1 (TOCs) addresses the stated readability goal; C2 (conditional extraction) was already pressure-tested and corrected; C3 (description triggers + sibling disambiguators) fixes a real refine ↔ lifecycle routing ambiguity; C4 (OQ3 softening) aligns with cortex's own CLAUDE.md policy; C5 (frontmatter symmetry) fixes a local cortex inconsistency.

## Updated decomposition (post-hold-resolution)

The original 14–16 children grow to **17–19 children** with the gate-compression additions:

- **Stream B** gets one additional ticket: B5 — "Compress complexity-escalation gate descriptions in lifecycle/SKILL.md (Tier 1 dedup + unified prose + JSON schema pointer)"
- **Stream H** is new: H1 — "Migrate complexity-escalation gates to deterministic Python hook (Tier 3)"

Stream H sequencing: lands AFTER Stream A (cross-skill collapse) so the canonical SKILL.md exists in one place to receive the migration. Independent of Stream F (vertical planning).
