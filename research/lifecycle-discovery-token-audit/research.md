# Research: Lifecycle & Discovery Token-Munching Audit

Breadth-first audit of cortex-command's lifecycle/discovery/overnight flows for hot-path token waste — context loads, file reads, and sub-agent dispatch payloads that consume substantial token budget relative to their downstream value.

**Scoping**: per user direction — "anything cuttable" threshold; going-forward only (no retroactive archive migration).

**Non-overlap with prior work**:
- Epic #172 (complete) addressed skill-corpus duplication, conditional extraction, plan/spec artifact trims. Did NOT measure events.log, backlog reads, sub-agent dispatch payloads, or always-loaded boot context.
- Ticket #185 (in_progress) addresses `/cortex-core:research` output schema (~3k tok of sub-agent-invented sections). This audit covers the *input* surfaces (orthogonal).

## Research Questions

1. **Events log + pipeline state**: where does `events.log` and pipeline-state JSON land in agent context, and how does it scale? → **Largest single waste: critical-review-residue.json glob loads ALL historical residues into morning report (~700KB). Second: orchestrator-round prompt re-inlines escalations.jsonl every round, unbounded growth. Third: clarify_critic events accumulate to ~46k tok cumulative across archive.**

2. **Backlog reads + lifecycle artifact re-reads**: what re-enters context on resume / phase transition? → **Lifecycle resume is reasonable (progressive per-phase). The real cost is sub-agent prompt inlining: critical-tier plan inlines full spec+research into 2-3 plan-agent prompts AND main context. complete.md reads full plan+review to extract 2 integers (weakest-consumer ratio in corpus).**

3. **Reference-file loading + sub-agent dispatch payloads**: which `references/*.md` load unconditionally with low payoff, and where do parallel-agent dispatches duplicate context? → **Largest per-dispatch waste: `/cortex-core:critical-review` injects FULL artifact into each of N reviewers + synthesizer = N+1 copies per dispatch. Worst case (300-line plan × 4 reviewers): ~12-15k tok. Typical case (150-line plan × 3 reviewers): ~3-5k tok. The "biggest waste" framing depends on artifact size and reviewer count — sensitivity disclosed.**

4. **Always-loaded session context**: what's the steady-state boot cost of CLAUDE.md / MEMORY.md / hooks / statusline / plugin descriptions? → **~2,300 tok always-loaded from SKILL.md description trigger-phrase lists (13 SKILL.md files, avg ~136 words/description, range 31–218; measured directly, not estimated). CLAUDE.md policy blocks (~400 tok) extractable to docs/policies.md now. Dashboard / morning-report back-feed: clean — no agent-context leak. At median-case DR-1, this is the largest single waste in the audit (per-session, every session) — outranks DR-1.**

## Codebase Analysis

### Tier 1: Largest per-dispatch waste

- **`/cortex-core:critical-review` artifact duplication** `[skills/critical-review/SKILL.md:95-152, 209-211]` — the prompt template injects `{artifact content}` into each of 3-4 reviewer agents AND the synthesizer prompt AND the main orchestrator's context. **Worst case (300-line plan × 4 reviewers): ~12-15k tok wasted per critical-review run. Typical case (150-line plan × 3 reviewers): ~3-5k tok. The savings exist; the headline magnitude is artifact-size and reviewer-count dependent.** Fix: pass absolute artifact path resolved from `git rev-parse --show-toplevel` (not cwd-relative); each reviewer reads via path. See DR-1 for mechanism + caveats.

- **Critical-tier plan agent prompts inline full spec+research** `[skills/lifecycle/references/plan.md:43-46]` — at critical tier, 2-3 plan agents each receive full `spec.md + research.md` body inline, AND main orchestrator already has them loaded. ~1.5-3k tok duplicated per critical plan. Same fix mechanism as above.

- **~~`critical-review-residue.json` glob loads all historical residues~~ — RETRACTED**: verification revealed `lifecycle_root.glob("*/critical-review-residue.json")` at `[cortex_command/overnight/report.py:985]` is depth-1 pathlib glob (`*`, not `**`). Archived residues at `lifecycle/archive/{slug}/critical-review-residue.json` (depth-2) are NOT matched. Active matched files: ~10 at ~36 KB total, not ~700 KB. DR-3 ("scope by session") is dropped — the targeted contamination path does not exist. **Residual narrower concern**: active depth-1 residues from features in long-running incomplete states still contaminate every morning report; a future cleanup could prune residues older than N days, but this is "nice cleanup" not Tier-1 waste.

### Tier 2: Large waste (1-10k tok per occurrence)

- **Aggregate SKILL.md description bloat** `[plugins/cortex-core/skills/*/SKILL.md frontmatter]` — 13 enabled SKILL.md files; measured average description ~136 words (range 31–218; sum ~1,770 words ≈ **~2,300 tok always-loaded at every session start**). Several embed trigger-phrase lists and structural prose (e.g., `lifecycle/SKILL.md` lists canonical source paths inside its description field). **Bigger boot-context hit than CLAUDE.md, and at typical-case DR-1 this is the largest single waste in the audit.**

- **Ticket #179 extractions never landed** `[backlog/179-...md:67-68]` — closed as `status: complete` but `skills/critical-review/references/a-b-downgrade-rubric.md` and `skills/lifecycle/references/implement-daytime.md` **do not exist**. `skills/critical-review/SKILL.md:229-278` still contains 8 worked examples inline (~49 lines). `skills/lifecycle/references/implement.md` is 283 lines (target was ~210). **Process gap**: status field is wrong, OR the spec was never executed. Net: ~120 lines remain on hot path.

- **`escalations.jsonl` unbounded growth in orchestrator-round prompt** `[cortex_command/overnight/orchestrator_context.py:23,62-75]` and `[cortex_command/overnight/prompts/orchestrator-round.md:33-37]` — `aggregate_round_context()` fully concatenates `escalations.jsonl` into `ctx["all_entries"]` with no cap. Token cost grows linearly per round with session history. Fix: cap to current+previous round, or unresolved + N most recent resolutions.

- **`clarify_critic` events.log accumulation** — **~500 tok per future feature** (the going-forward number; cumulative-historical figure was cited in earlier draft but is irrelevant under DR-2's "cut, don't migrate" remediation). Row count across archive is ~169 (not 94 as initial Agent A measurement; re-verified during critical-review). Fix: move payloads to sibling `events-detail.log` not glob'd by `metrics.parse_events`. (Was identified by #172 audit as deferred future work — still deferred.)

- **`orchestrator_review` events: write-only ceremony** — 304 emissions, 76 KB, **zero non-test Python consumers** verified across `cortex_command/`, `bin/`, `hooks/`. Highest-volume dead emitter. Fix: stop emitting.

### Tier 3: Notable (persistent, smaller per-occurrence)

- **CLAUDE.md policy blocks at 67/100 lines** `[CLAUDE.md:51-67]` — MUST-escalation + Tone-voice sections consume ~45% of file (~400 tok). Tone section is ~6 sentences documenting *why nothing ships* (history, not instruction). Policy itself says extract to `docs/policies.md` "on first crossing of 100 lines" — but extracting now is cheaper than waiting for the threshold trip.

- **Lifecycle SKILL.md Step 2: 4× redundant backlog globs** `[skills/lifecycle/SKILL.md:95, 129, 164, 191]` — same `backlog/[0-9]*-*{feature}*.md` glob walked 4 times for one slug in one step. `cortex-resolve-backlog-item`'s already-resolved JSON `filename` sits unused.

- **5+ duplicated "read events.log for criticality" stanzas** `[plan.md:21, specify.md:154, orchestrator-review.md:7, implement.md:169,257, refine/SKILL.md:159, dev/SKILL.md:126]` (also formerly in the lifecycle research-phase reference at `skills/lifecycle/references/research.md` line 17, deleted 2026-05-11 per backlog/185; canonical at `skills/research/SKILL.md` Step 4) — each phase ref re-reads full events.log to extract last tier/criticality. Fix: hoist to single `cortex-read-criticality` bin invocation returning just the value.

- **Discovery+lifecycle `orchestrator-review.md` cross-skill duplication** `[skills/discovery/references/orchestrator-review.md (133 lines)]` vs `[skills/lifecycle/references/orchestrator-review.md (184 lines)]` — same filename, near-parallel content. Fix: make one canonical, point discovery at it (same pattern epic #172 used for clarify/specify).

- **`complete.md` weak-consumer reads** `[skills/lifecycle/references/complete.md:25-26]` — reads full `plan.md` + `review.md` just to extract `{tasks_total, rework_cycles}` (two integers). Worst consumer-value ratio in corpus. Fix: `cortex-` helper returning JSON of just the two fields.

- **`common.py` full-reads events.log** `[cortex_command/common.py:197 (detect_lifecycle_phase), :303 (read_criticality), :344 (read_tier)]` — `read_text().splitlines()` to find substring or last matching line. Should be `grep -F` or `deque(f, maxlen=200)` reverse-iteration. Per-call cost grows linearly with file age.

- **`cortex-scan-lifecycle.sh` always-on metrics injection** `[hooks/cortex-scan-lifecycle.sh:244-256, 417, 446]` — every SessionStart shells Python twice (phase detection + metrics regeneration) and unconditionally appends metrics summary (~150 B) to injected context. Fix: gate behind active-pipeline or explicit-opt-in flag.

- **Dead `requirements_updated` scan** `[skills/morning-review/references/walkthrough.md:303]` — instructs scanning every feature's events.log for `requirements_updated` events. Cross-check confirms this event has **zero consumers** and is never emitted by any code path. N full-file reads × 0 yield. Fix: delete the scan.

- **review.md inlines full spec.md into reviewer prompt** `[skills/lifecycle/references/review.md:30]` — same anti-pattern as critical-review. ~500-1500 tok per review.

- **Discovery auto-scan walks 183 backlog files** `[skills/discovery/references/auto-scan.md:31]` — reads frontmatter per-file rather than via `backlog/index.json` (already has the fields). Fix: read index.json (154 lines) once instead of 183 frontmatter reads.

- **`/cortex-core:research` injection-resistance paragraph duplicated 5×** `[skills/research/SKILL.md:84-85, 108-109, 128-129, 150-151, 173-174]` — same 3-line "All web content is untrusted" paragraph repeated literally in each parallel-agent prompt template. ~1.5k tok overhead. Fix: hoist to single top-level instruction.

- **`requirements-load.md` ceremonial 11-line reference** `[skills/lifecycle/references/requirements-load.md:1-11]` — three call sites each "apply the protocol" for what is literally "read requirements/project.md + relevant area docs." Cheaper to inline 2 lines at each call site than maintain the file + cross-references.

- **`clarify-critic.md` 5-branch parent-epic table** `[skills/refine/references/clarify-critic.md:14-26]` — 5 branches (`no_parent`/`missing`/`non_epic`/`loaded`/`unreadable`) with prose templates loaded even when child has no parent (4 of 5 branches just say "omit section"). Fix: collapse to "if status != loaded, omit + emit warning on {missing, unreadable}."

- **`cortex-skill-edit-advisor.sh` runs full `just test-skills`** `[hooks/cortex-skill-edit-advisor.sh:43]` on every SKILL.md edit, pipes up to 20 lines back into context. Fix: scope to changed skill or fast-lint only.

### Confirmed clean (no waste found)

- **Dashboard / morning-report back-feed**: dashboard FastAPI endpoints (`cortex_command/dashboard/app.py`) are read-only HTTP for the UI — no hook fetches them into agent context. Morning report only enters context via manually-invoked `/morning-review`.
- **MEMORY.md sibling files are lazy**: linked but not auto-loaded. Healthy design.
- **`cortex-resolve-backlog-item`**: returns minimal frontmatter-only fields, not full body.
- **Permission audit hook**: pure file-only side effect; no `additionalContext` emission.
- **User `~/.claude/CLAUDE.md`**: empty — no waste.
- **Plugin manifests** (`plugin.json`): trivial 8 lines each.
- **Backlog index growth concern**: WRONG premise — `backlog/index.json` has only 5 active items of 183; completion drains the index. Growth is bounded. The cost lives in scan-based readers, not the index itself.

### Confirmed-dead event types (from cross-check vs. prior audit)

**Dead** (verified zero non-test Python consumers): `clarify_critic`, `orchestrator_review`, `orchestrator_dispatch_fix`, `discovery_reference`, `confidence_check`, `requirements_updated`, `lifecycle_paused`, `lifecycle_resumed`, `spec_approved`, `plan_approved`.

**Prior audit was wrong on** (these ARE consumed):
- `complexity_override` — consumed at `[cortex_command/overnight/report.py:772]` and `[bin/cortex-complexity-escalator:71]`
- `dispatch_progress` — emitted at `[cortex_command/pipeline/dispatch.py:686]`, consumed at `[cortex_command/pipeline/metrics.py:354]`

### Premise-unverified items (carry into spec)

- `[premise-unverified: not-searched]` whether `bin-invocations.jsonl` per-session telemetry has any consumer. Worth a follow-up grep.
- `[premise-unverified: not-searched]` whether `tool-failures/` directory contents are aggregated into agent-visible morning report.
- `[premise-unverified: not-searched]` for Claude Code's progressive-disclosure behavior on SKILL.md descriptions vs bodies — whether body is loaded eagerly or only on trigger. Matters for sizing the "always-on" cost of skill descriptions vs SKILL.md bodies.

## Feasibility Assessment

**Sequencing legend**: `→ N` means must land before item N. `↔ N` means bundle with item N (single ticket). Hotspot files: **plan.md** (items 2, 10, 20), **critical-review/SKILL.md** (items 1, 4 — bundled), **orchestrator-review.md** (items 10, 11, 17), **event emitters** (items 6, 7). Decomposition must respect sequencing or parallel-overnight execution will collide on hotspots.

| # | Tier | Cut | Effort | Risk | Sequencing | Token impact |
|---|------|-----|--------|------|------------|--------------|
| 1+4 | 1 | **BUNDLED**: Critical-review path-not-content dispatch + Land #179 extractions (both touch critical-review/SKILL.md) | M | LOW–MED — see DR-1 caveats | Independent | **Worst-case: 12-15k tok / typical: 3-5k tok per critical-review** + ~120 lines off hot-path |
| 2 | 1 | Critical-tier plan path-not-content dispatch | S | LOW | After 1+4 (same mechanism) | 1.5-3k tok × every critical plan |
| ~~3~~ | — | ~~Session-scope `report.py` residue glob~~ — **DROPPED** (glob is already depth-1; archived residues excluded by construction) | — | — | — | — |
| 5 | 2 | Cap `escalations.jsonl` history in orchestrator_context | S | MED — must preserve unresolved | Independent | Linear growth eliminated |
| 6 | 2 | Move `clarify_critic` to events-detail.log | M | LOW if metrics.parse_events glob is filterable | After 7 (delete dead emitters before relocating live) | ~500 tok/feature going forward |
| 7 | 2 | Stop emitting `orchestrator_review` + 9 other dead events | S | LOW — no consumers verified | → 6 | ~76 KB write-only ceremony removed (orchestrator_review alone) |
| 8 | 3 | Extract CLAUDE.md policies to docs/policies.md now | S | LOW | Independent | ~400 tok off boot context |
| 9 | 2 | Compress SKILL.md descriptions (drop trigger lists, keep canonical phrases) | M | MED — could hurt skill-trigger accuracy; needs test | Independent | **~2,300 tok off boot context** (largest persistent waste at typical-case DR-1) |
| 10 | 3 | Hoist criticality reads to `cortex-read-criticality` bin | M | LOW | After 11 (canonical orchestrator-review.md must settle first) | N events.log full-reads → 1 per lifecycle |
| 11 | 3 | Cross-skill canonical orchestrator-review.md (discovery→lifecycle) | S | LOW — same pattern as #174 | **→ 10, 17** (cross-skill collapse first per #172 precedent) | ~130 lines duplication |
| 12 | 3 | Reuse `cortex-resolve-backlog-item` filename in lifecycle Step 2 | S | LOW | Independent | 4 globs → 0 per lifecycle entry |
| 13 | 3 | `complete.md` JSON helper for 2 integers | S | LOW | Independent | ~200-400 lines per complete |
| 14 | 3 | `common.py` tail-read replacements | S | LOW | Independent | per-call linear growth removed |
| 15 | 3 | Gate scan-lifecycle metrics injection | S | LOW | Independent | ~150 B per SessionStart |
| 16 | 3 | Delete dead `requirements_updated` scan | S | LOW — zero emitters | Independent | N full-file reads × 0 yield |
| 17 | 2 | Review.md path-not-content dispatch | S | LOW (same caveats as DR-1) | After 11; uses same mechanism as 1+4 | ~500-1500 tok per review |
| 18 | 3 | Discovery auto-scan via index.json | S | LOW | Independent | 183 frontmatter reads → 1 JSON read |
| 19 | 3 | Hoist research.md injection-resistance to top | S | LOW | Independent | ~1.5k tok per research invocation |
| 20 | 3 | Inline + delete requirements-load.md | S | LOW | After 11 (orchestrator-review.md is one of the 4 references touched) | ~30 lines of meta-text |
| 21 | 3 | Collapse clarify-critic.md 5-branch table | S | LOW | Independent | ~10 lines |
| 22 | 3 | `cortex-skill-edit-advisor.sh` scope tests | S | LOW | Independent | ~700 B per matching edit |

## Decision Records

### DR-1: Sub-agent dispatch — pass paths, not content

- **Context**: `/cortex-core:critical-review` injects full artifact content into N reviewer + 1 synthesizer + main-context = N+2 copies. Per-dispatch impact ranges 3-15k tok depending on artifact size × reviewer count. Same anti-pattern in `lifecycle/references/plan.md` (critical-tier plan agents), `review.md` (reviewer prompt), and similar dispatch sites.
- **Options considered**:
  - (a) Status quo (inline content) — atomic snapshot at dispatch; high token cost.
  - (b) Pass absolute artifact path (resolved from `git rev-parse --show-toplevel`); reviewers Read.
  - (c) Pass a content hash + path; reviewers verify hash on Read (snapshot guarantee).
- **Recommendation**: (b), with three explicit caveats — **not** the "structurally identical to orchestrator/main session" framing (that justification was wrong: orchestrator writes use in-process Write/Edit tools that bypass sandbox per Anthropic #26616, a different code path than reviewer Reads).
  - **Caveat 1 (path resolution)**: pass an absolute path resolved from `git rev-parse --show-toplevel`, NOT a relative path. Worktree-dispatched reviewers inherit worktree cwd per `docs/overnight-operations.md:601`; a cwd-relative read resolves to the worktree-local copy, not the authoritative one. The dispatch payload must absolute-ify the path before injection.
  - **Caveat 2 (snapshot semantics)**: this trades atomic dispatch-time snapshots for a TOCTOU window between dispatch and reviewer Read. If concurrent writers modify the artifact during the parallel fan-out, reviewers see post-edit content and the synthesizer's `evidence_quote` re-read may not match what reviewers saw. **Pin behavior**: critical-review SKILL.md must add "no edits to artifact between dispatch and synthesis" as a hard constraint; orchestrator must hold writes until synthesis returns.
  - **Caveat 3 (path-arg invocation)**: `/cortex-core:critical-review <path>` is a supported mode where the artifact may live outside `lifecycle/<feature>/`. The "absolute path" rule still applies; resolve the user-supplied path before injection.
- **Trade-offs**: Each reviewer pays one extra Read tool call. Net per-dispatch reduction: ~3-5k tok at typical case, ~12-15k tok at worst case. At small artifact sizes (<2k tok), tool-call overhead may eat most of the gain — disclose this in the implementation spec rather than claim "1-2 orders of magnitude" universally.

### DR-2: Events log — cut, don't migrate

- **Context**: `clarify_critic` (~46k tok cumulative, ~500 tok/feature going forward) and `orchestrator_review` (76 KB write-only ceremony, zero consumers) are the two biggest events.log line items. Plus 8 other dead event types verified.
- **Options considered**:
  - (a) Migrate `clarify_critic` payloads to sibling `events-detail.log`; keep emitting all others.
  - (b) Stop emitting dead events entirely; migrate only `clarify_critic` (the one with arguable diagnostic value).
  - (c) 2-tier split per #172's deferred work — full spine + detail file.
- **Recommendation**: (b). The 9 verified-dead events have no consumers; emit-and-then-store is pure waste. `clarify_critic` is the one with diagnostic value (debugging clarify-critic behavior), so it goes to detail. Defer full 2-tier scheme (#172 deferred work) until per-event consumer audit covers all ~71 event types.
- **Trade-offs**: Loses cumulative emission history for dead events. Acceptable — no consumer would notice. Going-forward only per user scoping.

### DR-3: ~~Critical-review-residue glob — scope by session~~ — **WITHDRAWN**

- **Context**: original draft asserted the residue glob walks the entire `lifecycle/` tree, contaminating morning reports with ~700 KB of archived residues.
- **Verification result**: `lifecycle_root.glob("*/critical-review-residue.json")` at `[cortex_command/overnight/report.py:985]` is depth-1 pathlib glob (`*` is non-recursive; `**` would be). Archived residues at `lifecycle/archive/{slug}/...` (depth-2) are not matched. Actual matched files: ~10 active depth-1 residues at ~36 KB total — not ~700 KB. The premised contamination path does not exist.
- **Disposition**: withdrawn. A narrower follow-up could prune long-lingering active depth-1 residues from features in incomplete states, but at ~36 KB total this is "nice cleanup," not Tier-1 waste.

### DR-4: SKILL.md description compression — test-gated

- **Context**: ~1000 tok of always-on description content, several embedding trigger-phrase lists in prose. Compression conflicts with skill-trigger accuracy (the trigger phrases ARE the routing signal).
- **Options considered**:
  - (a) Aggressive compression — drop all trigger-phrase lists, keep one canonical phrase per skill.
  - (b) Move trigger-phrase enumeration to a separate field (`when_to_use`) — requires Claude Code support.
  - (c) Conservative — compress only descriptions that embed *structural prose* (e.g., lifecycle's canonical-source path enumeration), keep trigger lists.
- **Recommendation**: (c). The audit's most damning finding here is structural prose inside descriptions, not the trigger lists themselves. Trigger lists earn their tokens by routing; structural prose does not.
- **Trade-offs**: Saves ~200-400 tok instead of ~600. Lower risk of trigger-accuracy regression.

### DR-5: Process — investigate #179, then decide on a gate

- **Context**: Ticket #179 was marked `status: complete` 2026-05-11 but the deliverable files (`a-b-downgrade-rubric.md`, `implement-daytime.md`) do not exist; target file sizes (210 lines for implement.md) are not met (actual: 283). No completion-check enforced extraction-landed-on-disk verification. **#179 was also confounded by mid-flight scope-trim** (original 6 extractions halved to 2 per epic-172-audit C7) — a known acceptance-criteria-drift failure mode.
- **Three-step recommendation** (revised from original "extract + add gate"):
  - **(a) Execute #179's extractions.** Spec is sound; value is real. Bundle into Tier-1 item 1+4. *Independent of (b)/(c).*
  - **(b) Sample 2-3 sibling tickets from epic #172 (#173-178, #180-183) for closure-inaccuracy.** Cheap NOW while context is fresh; expensive later. Either confirms or falsifies the "systemic phenomenon" hypothesis. Without this step, the project-wide gate rests on N=1.
  - **(c) Only AFTER (b)**: decide whether the failure is (i) closure-discipline (reviewers skipping `ls`-level verification), (ii) scope-change drift (acceptance criteria not re-aligned after trim), or (iii) general closure-inaccuracy. Each diagnosis demands a different intervention:
    - (i) → process/culture change, not tooling. A filesystem-touchable gate would be ceremony for reviewers who already skip verification.
    - (ii) → scope-change re-acceptance prompt at trim time, not a closure-time gate. This is where #179 likely lives.
    - (iii) → mechanical completion gate as originally proposed.
- **Rationale for the revision**: original DR-5 recommended a project-wide gate from N=1 evidence and prescribed filesystem-touchable checks (file-exists, line-count) — but #179's failure was the most trivially detectable kind (one `ls`), suggesting the failure layer is discipline, not tooling. A gate addressing the easy 10% of acceptance criteria gives false confidence on the hard 90% (semantic correctness, doc accuracy, behavior change).
- **Trade-offs**: Sampling adds one chore-ticket of effort before any gate work. Defensible because the audit's own DR-5 standard ("acceptance verification must touch reality before closure") is one the audit itself does not meet — both `[premise-unverified]` open questions are unsearched.

## Open Questions

- What's the actual mechanism of Claude Code's progressive disclosure for SKILL.md? Is the body loaded eagerly at session start or on first trigger? This sizes whether the SKILL.md *bodies* (not just descriptions) belong in the boot-context audit.
- Is `bin-invocations.jsonl` consumed anywhere? `[premise-unverified: not-searched-exhaustively]` per agent A.
- Does `tool-failures/` directory content feed into morning report agent context? `[premise-unverified: not-searched]` per agent D.
- Should this audit's findings be one epic with ~22 child tickets, or split into 2-3 thematic epics (dispatch-dedup / events-log-cleanup / boot-context-trim)? Decompose phase will decide.
