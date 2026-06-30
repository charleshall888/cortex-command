# Research: Move overnight-suitability judgment from /refine into /overnight curation

**Ticket:** #323 · **Tier:** complex · **Criticality:** high

Goal: (1) remove `skills/refine/SKILL.md` Step 6 "Overnight-candidate advisory (standalone /refine only)" in full — including its `grep -c '"event": "phase_transition"'` run-mode detection and standalone-vs-lifecycle branching — while keeping the §5 `phase_transition` skip-note; (2) relocate the overnight-suitability judgment into overnight's interactive curation so poor-fit refined specs are set aside with per-item reasons, surfaced at the approval gate, **re-addable** before the run list is frozen, biased toward exclusion, and the unattended harness consumes only the frozen list.

> **Headline:** Research confirmed the ticket's central premise is partly false. The operator's Step 6 curation does **not** reach the executed set today — `launch` re-selects from scratch. Honoring the ticket's own Edges (excluded-by-default *at execution* + re-add that *sticks* + harness consumes a *frozen* list) requires a **new curation→launch handoff** that the ticket's Touch points omit. Shipping the listed touch points alone yields an actively-harmful cosmetic feature (set-aside items run anyway). See Open Questions Q1.

## Codebase Analysis (refine side + skill-layer)

**The advisory to remove — `skills/refine/SKILL.md` lines 195–213 (the SEED, preserve its meaning):**

```markdown
### Overnight-candidate advisory (standalone `/refine` only)

This advisory runs only on the standalone `/refine` path. Detect that path with a concrete
signal: standalone `/refine` never logs `phase_transition` events (it writes only `lifecycle_start`
and `*_override` rows), whereas a run under `/cortex-core:lifecycle` already carries `phase_transition`
rows ... Check:

    grep -c '"event": "phase_transition"' cortex/lifecycle/{lifecycle-slug}/events.log

- `0` → standalone: assess overnight-suitability and surface the advisory below when warranted.
- `≥ 1` → invoked under `/cortex-core:lifecycle`: stay silent ...

When standalone, assess whether the approved `spec.md` is a poor overnight candidate. Anchor on
these mechanical signals, and cite each that is present:
- any acceptance criterion marked `Interactive/session-dependent`, and
- any unresolved item under the spec's `## Open Decisions`.

You may additionally cite judgment reasons when they apply: the work needs network or credentials
the sandbox can't reach, it leans on human-visual or human-judgment verification, or its scope is
exploratory/under-specified.

When one or more reasons apply, surface a brief advisory naming them — e.g., "Heads up — this looks
like a poor overnight candidate because …" — so the operator can choose to run it interactively
instead. When none apply, say nothing; the advisory is silent on a good candidate.
```

**Keep intact — the §5 skip-note (line 158), a separate event-logging boundary, NOT part of the advisory:**

> `§5 (Transition)`: Skip the `phase_transition` event emission — /cortex-core:refine does not log `phase_transition` events; the caller (/cortex-core:lifecycle) owns phase-transition logging ... The `lifecycle_start` sentinel emitted at Step 2 is exempt.

The advisory's `grep -c` heuristic merely *consumed* this fact; the producer-contract in §5 stands on its own. After excision, Step 6 reverts to the plain `## Completion` block (announce + the two summary lists at lines 187–193). The Step 2 cross-reference "skip directly to Step 6 (Completion)" still resolves.

**Files that change / governance:**
- Canonical `skills/refine/SKILL.md` (excise 195–213) and `skills/overnight/SKILL.md` + `skills/overnight/references/new-session-flow.md` (curation surface). Edit canonical only.
- Mirrors regen via `just build-plugin` (justfile:589) + the `.githooks/pre-commit` dual-source drift gate (commit canonical + mirror together). **Mirror locations:** refine → `plugins/cortex-core/skills/refine/`; **overnight → `plugins/cortex-overnight/skills/overnight/` (SKILL.md *and* the `references/` subtree)** — the ticket's "`plugins/cortex-core/skills/overnight/SKILL.md`" Touch point is **stale**; the overnight skill lives in the dedicated `cortex-overnight` plugin.
- **L1 ratchet** measures frontmatter (`description`+`when_to_use`) only — body removal is byte-neutral. `refine`=624B (routing-pressure cluster), `overnight`=314B (non-cluster, hard ≤400B ceiling, ~86B headroom). Risk only if frontmatter/descriptions change.
- **Size cap** 500 lines: refine=222, overnight=132 — far under.

## Web Research (prior art for the curation gate)

The design shape — **soft-mandatory / default-deny + reviewable, per-item override** — is well-precedented:
- **GitHub Actions environment protection** (pause-until-human-approves before the irreversible phase; *prevents self-review*). **Terraform `plan`→`apply`** with a **saved plan file** fed verbatim to apply — the canonical "freeze the reviewed set, execute exactly that." **OPA/Sentinel three-level taxonomy:** advisory / soft-mandatory (block + override) / hard-mandatory. Set-aside-with-re-add = soft-mandatory.
- **HITL escalation design:** "gate by consequence, not confidence"; model self-confidence is miscalibrated, so suitability should be **structural/surfaced, not the agent's self-assessment**; gating belongs at the execution layer, not negotiated at runtime.
- **Last Responsible Moment** supports moving the *binding* decision to curation time (richest context) — but capture cheap signals early; don't procrastinate everything.

**Reconciliation of the fail-open/fail-closed tension (decisive here):** fail-**closed on whether an item RUNS** (unattended execution is Tier-4/irreversible → bias to exclude) + fail-**loud on VISIBILITY of what was set aside** (never silent). K8s "fail-open and validate" protects *availability*, which is not the risk here.

**Anti-patterns to engineer against:**
- **Silent drops** ("every set-aside is real work that didn't happen — surfacing is non-negotiable").
- **Over-flagging → rubber-stamping**: long exclusion lists get reflex-approved. Mitigate with **consequence-calibrated triggers, batched single-gate review, terse plain-language reasons** — not per-item prompts.
- **Lossy re-add**: quarantine/false-positive items that return on the next pass force re-work. The operator's re-add must be **either persistent (suppress next time) or explicitly one-shot** — and the system must say which.

## Requirements & Constraints

- **Suitability is anchored** in `project.md` "Handoff readiness: a feature isn't overnight-ready until the spec has no open questions, criteria are agent-verifiable from zero context, artifacts self-contained." That *is* the judgment being relocated.
- **Affordance-preservation guideline (CLAUDE.md):** removing refine's heads-up obligates explicitly documenting that the protection (operator can redirect/reject before the lifecycle advances) is **preserved at overnight curation**. This is a hard authoring obligation for this ticket, not optional.
- **Kept-pauses claim REFUTED:** `tests/test_lifecycle_kept_pauses_parity.py:96` scans only `skills/lifecycle` + `skills/refine` for `AskUserQuestion` sites. The advisory is **prose, not an AskUserQuestion**, so removing it touches neither the inventory nor the parity test, and the overnight gate is out of that inventory's scope. (An earlier alignment note that invoked kept-pauses for the overnight gate was wrong.)
- **Backend-blindness resolved upstream:** overnight is **fail-closed gated to the `cortex-backlog` backend before any selection** (`_refuse_unsupported_backlog_backend`, cli_handler.py:1949/2131). So the relocated logic needs **no backend-awareness** and must **not** route through the fail-open `cortex-read-backlog-backend` reader (the asymmetry is deliberate and regression-pinned).
- **MUST-escalation:** any new curation gate prose stays **soft positive-routing**; a MUST requires the evidence-artifact + effort-first ritual.
- **bin parity:** direction is bin→reference; removing advisory prose drops no script's last wiring. A *new* `cortex-*` binstub (if introduced) would need its own wiring reference.

## Selection Pipeline Internals

- `select_overnight_batch` (`backlog.py:1020`, signature `(backlog_dir, batch_size_cap)`) = pure deterministic `load → filter_ready → score → group`. **`filter_ready` (backlog.py:448–632) reads no spec/research *content* — only `research_path.exists()` / `spec_path.exists()`**, status enum, blocker BFS, `type != epic`, branch-not-merged. Reasons are free-form strings built inline.
- **No `## Open Decisions` / `Interactive` / `session-dependent` parser exists anywhere in `cortex_command/`.** The closest content-section reader is `report.py:_read_acceptance` (a `^## …\n(.*?)(?=\n## |\Z)` regex over `plan.md`, at report time — never in selection). `complexity_escalator.py` parses `## Open Decisions` (with `- None.`/`- (none)`/placeholder exclusions) but does **not** key on `Interactive/session-dependent`.
- **Data shapes:** `IneligibleItem = namedtuple('item','reason')` (free-form reason, **no category enum**); `SelectionResult(batches, ineligible, summary, intra_session_deps)` (note: **no `eligible_count` field**). Envelope `_selection_summary_payload` (cli_handler.py:1992) emits `{summary, batch_count, selected_count, batches:[…], ineligible:[{id,title,reason}], intra_session_deps}`. The `ineligible` list is today's **only** per-item set-aside channel; a soft "poor-fit (overridable)" category would either ride it with a reason-prefix (cheap, conflates) or add a sibling `set_aside` field (cleaner separation — recommended given re-addability differs).
- **Mechanical drops** (interactive AC / unresolved Open Decisions) = **net-new spec-body parsing**, feasible in Python. **Soft drops** (network/credentials, human-visual, exploratory) = **impossible in the deterministic verb** (no LLM); only keyword heuristics, which are brittle.

## Approval-Gate UX & Re-Add Design

- Gate = Step 6 "Unified Plan + Spec Review." Menu (`new-session-flow.md:93`): **`[A]pprove / [R]emove / [T]ime-limit / [Q]uit`**. `[R]emove` only subtracts an *already-selected* feature and re-renders; ineligible / "Not Ready" items are **display-only — no re-add affordance exists** (grep across `skills/overnight/` for re-add/include/restore = zero).
- **Three pools needed (not two):** (1) **hard-ineligible** (missing research/spec, epic, blocked, branch-merged) — display-only, **never re-addable** (forcing one in crashes `bootstrap`/`extract_batch_specs`); (2) **suitability set-aside** — mechanical *and* soft, **always re-addable** (an unresolved Open Decision is a judgment the operator may legitimately override; treating mechanical drops as non-re-addable would violate the ticket); (3) **active**.
- **Smallest UX:** a numbered set-aside block (excluded-by-default → bias-to-exclude is structural) + **one conditional new verb `[I] Include a set-aside item`** (symmetric inverse of `[R]`; rendered only when the set-aside pool is non-empty) + reuse of the existing re-render/re-prompt loop. One genuinely new *direction* of mutation, but additive prose only — no control-flow restructuring.

## Tradeoffs & Alternatives (judgment locus)

The drop signals split into MECHANICAL (interactive AC; unresolved `## Open Decisions` — deterministically detectable *if* something reads the spec body) and SOFT (network/credentials, human-visual, exploratory — require LLM judgment).

- **A — Python owns all drops:** soft signals infeasible (no LLM); degrades to brittle keyword soup. Rejected.
- **B — Hybrid (Python owns mechanical via new spec-parsing; LLM skill owns soft):** maps to the codebase's mechanics-vs-judgment split and the "structural gate > prose" preference; mechanical drops get unit tests. **But** it creates split-brain ownership across two actors that re-run independently, causes a **determinism flicker** (LLM re-assesses soft drops on every `[R]`/`[T]` re-render while Python is stable; a `[T]` change re-triggers soft re-assessment), and **still needs the handoff anyway** for the soft half — so the Python parsing is *added cost*, not a substitute.
- **C — LLM `/overnight` skill owns ALL suitability drops** (reads each candidate spec it already displays inline at Step 6; applies mechanical + soft criteria as a prose rubric seeded from the advisory); Python `select_overnight_batch` unchanged: **zero net-new Python parsing, no template-heading coupling, all drops computed once by one actor at freeze (no flicker, no split-brain), mechanical drops stay re-addable, robust to spec-phrasing drift.** Cost: mechanical drops are not deterministically unit-testable — acceptable because every drop is surfaced + re-addable at a human gate (the ticket's own "reviewable gate is what makes aggressive dropping safe"). Aligns with CLAUDE.md "prescribe What/Why not How" (the Edges are the contract; none require Python to own parsing).
- **D — Python surfaces structured facts, skill judges:** needless indirection + more envelope schema surface.

**Two agents disagreed on the recommendation** (see Open Questions Q2): the Tradeoffs angle recommended **B**; the Adversarial angle recommended **C** and argued B over-builds. Both agree the **curation→launch handoff is mandatory** under any non-cosmetic design.

## Adversarial Review

- **Plumbing finding CONFIRMED with no escape hatch.** `handle_launch` (cli_handler.py:2143) re-runs `select_overnight_batch` from scratch; `bootstrap_session` consumes *that* fresh selection. argparse (`cli.py:970–1052`) has no `--only/--include/--exclude`. Step 6 writes nothing on disk; `[R]emove` → "repeat Step 5" → re-runs read-only `prepare` → **re-selects everything**, so a removed item can reappear *within the Step 6 loop itself* unless the LLM holds it in working memory. Step 7 calls `cortex overnight launch` with no curated set. The runner consumes bootstrapped state and never re-selects. **No path exists by which curation reaches the executed set.**
- **The handoff is load-bearing, not scope creep.** Implementing only the ticket's Touch points produces an *actively harmful* result: a soft set-aside (e.g. "needs credentials") is re-selected by launch's pure-Python pass and **runs unattended anyway** — exactly what Edge #1 forbids. Re-adds don't stick. If mechanical drops are pushed into Python so they reach launch, they become **non-overridable**, contradicting "re-add any of them." → #323 must **absorb the handoff or be blocked-by a handoff ticket; do not ship the cosmetic half.** This also closes the pre-existing `[R]emove`-doesn't-stick bug.
- **`Interactive/session-dependent` is the weakest possible coupling** — defined only as option (c) inside a *template comment* (`specify.md:128`), not a section, not pinned by any test, explicitly optional phrasing ("manual verification" / "requires a live UI" are equivalent). A Python literal-substring matcher would miss most real cases → strong argument **against** Python owning that signal, **for** semantic LLM reading. `## Open Decisions` is a real header (`specify.md:148`) but also unpinned by any test in either the escalator or a new parser (template rename silently disables the gate).
- **Points in favor / real trades:** relocation **improves self-review separation** (judgment moves from the spec's author to a fresh `/overnight` session) — provided `/overnight` is genuinely separate. **Lost early signal:** the standalone-refine→interactive-build path loses the heads-up; overnight re-derives suitability "cold," possibly days later, across a batch — judgment *quality* per item may drop even as *timing* improves. Acceptable per the ticket's Role, but a genuine trade.
- **Bias-to-exclude × no session-size cap** (`new-session-flow.md:91`) risks a set-aside block rivaling the active list → rubber-stamping; only safe **after** the handoff lands and with terse reasons + batched review.

## Open Questions

1. **[SCOPE — load-bearing; defer to Spec §4 user decision] Does #323 absorb the curation→launch frozen-list handoff, or get blocked-by a dedicated handoff ticket?** Confirmed: the operator's curation does not reach launch today (`handle_launch` re-selects; no selection-set flag; runner consumes bootstrapped state). Any non-cosmetic design — including advisory-only — requires the handoff (a `launch`/`prepare` curated-set input + `handle_launch` bootstrapping that set instead of re-selecting + the skill passing the post-curation set). Shipping the ticket's listed Touch points alone is actively harmful (set-aside items run anyway). The handoff also fixes a pre-existing `[R]emove`-doesn't-stick bug. **Deferred: resolved in Spec — present absorb-vs-block (and the cosmetic-half non-option) to the user at the §4 complexity/value gate; this is the dominant scope lever and should be settled before the §3b critical-review gate fires.**

2. **[DESIGN — agent contradiction] Judgment locus: Alternative C (LLM skill owns all suitability drops, Python unchanged) vs Alternative B (Python owns mechanical drops via new spec-parsing, LLM owns soft).** The Tradeoffs angle recommended B (structural/testable mechanical gate); the Adversarial angle recommended C and showed B over-builds (Python parsing is added cost since the handoff is needed for soft drops regardless; the `Interactive/session-dependent` marker is too weak for substring matching; B introduces flicker + split-brain). **Deferred: resolved in Spec — lean C per the adversarial analysis (one actor at freeze, no template coupling, mechanical drops stay re-addable), explicitly weighing the structural-gate counterargument (CLAUDE.md "prefer structural separation for sequential gates") and the loss of deterministic unit tests for mechanical drops.**

3. **[DESIGN] Re-add persistence semantics.** Web prior art warns of lossy re-add (set-aside items returning next pass forcing re-work). Is the operator's re-add a one-shot override for this session, or does it suppress the same false-exclusion in future curations? **Deferred: resolved in Spec — within a single curation session the re-add must at minimum stick through `[R]`/`[T]` re-renders and into the frozen list; cross-session persistence is a smaller add to decide at spec time.**

4. **[DESIGN] Set-aside channel shape in the envelope:** reuse `ineligible` with a recognizable reason-prefix (zero schema change, conflates cannot-run with poor-fit) vs. a new sibling `set_aside` field (clean separation matching the differing re-addability of the three pools). **Deferred: resolved in Spec — favor a distinct channel because hard-ineligible and suitability-set-aside have opposite re-add semantics; note no test currently pins the envelope `ineligible` field, so a new envelope test is needed either way.**

5. **[CONTRACT] If any drop signal is parsed in Python, pin its spec marker.** Do not key on `Interactive/session-dependent` (comment-only, optional, unpinned). At most reuse the escalator's `## Open Decisions` parser and add a test asserting `specify.md` still emits that exact heading so a template rename fails loudly. **Deferred: resolved in Spec — contingent on Q2; moot if Alternative C (no Python parsing) is chosen.**

6. **[CALIBRATION] Bias-to-exclude vs. rubber-stamping at large batch sizes** (no session-size cap exists). Keep exclusion calibrated to consequence with terse, plain-language reasons and a single batched review. **Deferred: resolved in Spec as an authoring guideline for the curation rubric (What/Why, soft phrasing).**

7. **[OBLIGATION] Affordance-preservation note.** Per CLAUDE.md, the implementation must explicitly document that refine's removed heads-up protection is preserved at overnight curation, and acknowledge the lost early signal on the standalone-refine→interactive-build path. **Resolved: this is a documentation requirement carried into Spec/implementation, not an open design question.**
