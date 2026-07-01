# Research: Extract the critical-only competing-plans block to a lazy reference (#341)

> All `<path>:<line>` citations in this document are wrapped in inline code spans on purpose: `tests/test_lifecycle_references_resolve.py` scans `cortex/lifecycle/**` artifacts and marks any **bare** `path:line` token "stale" when the line exceeds the target file's length. After this extraction `plan.md` shrinks to ~212 lines, so a bare `plan.md:302` would fail the test. Backticking keeps every citation inert. **The implementer must keep this convention in spec.md and plan.md too.**

## Summary / Recommendation

Validate the ticket's approach: physically extract the §1b "Competing Plans (Critical Only)" **body** from `skills/lifecycle/references/plan.md` into a new sibling `skills/lifecycle/references/competing-plans.md`, leaving the **verbatim heading stub** `### 1b. Competing Plans (Critical Only)` plus a body-resolved pointer in plan.md. Wire the sibling through a **new SKILL.md "Reference-path propagation" manifest bullet** (plan.md cannot resolve `${CLAUDE_SKILL_DIR}` itself — ADR-0009), mirroring how `orchestrator-review` and `critical-review-gate` are already wired. This is the no-architectural-risk hot-path reduction the discovery research (R3) and epic #340 pre-committed to.

The win is real and requires physical extraction: §1b is ≈10,915 B of plan.md's 25,471 B (≈43%), loaded on **every** plan read but used only on the ≈2% critical path. Reordering within plan.md saves nothing — the Plan phase issues one whole-file `Read`, so every byte in the file becomes resident regardless of section order. Only moving the bytes into a file Read solely on the critical arm removes them from the hot path.

## Codebase Analysis

**Files that change**
- `skills/lifecycle/references/plan.md` — cut §1b body, leave heading stub + pointer; file-qualify 4 dangling cross-refs.
- `skills/lifecycle/references/competing-plans.md` — **new** sibling holding the extracted body.
- `skills/lifecycle/SKILL.md` — add one bullet to the Reference-path propagation manifest (`SKILL.md:146`–`159`).
- `skills/lifecycle/references/kept-pauses.md` — re-anchor the plan-approval entry (line `18`).
- `cortex_command/overnight/prompts/orchestrator-round.md` — doc-accuracy repoint of the §1b cite (line `302`); optional.
- `cortex_command/overnight/tests/test_orchestrator_round.py` — docstring repoint (line `85`); optional, not an assertion.
- `plugins/cortex-core/skills/lifecycle/references/{plan.md,competing-plans.md}` + mirror SKILL.md — **auto-regenerated** by `just build-plugin`; never hand-edited; committed in the same commit.

**plan.md section map** (315 lines / 25,471 B): `# Plan Phase` 1–3 · `## Protocol` 5 · `### 1. Load Context` 7–12 · `### 1a. Check Criticality` 14–19 · **`### 1b. Competing Plans (Critical Only)` 21–126** · `### 2. Design the Approach` 128–134 · `### 3. Write Plan Artifact` 136–256 · `### 3a. Orchestrator Review` 258–260 · `### 3b. Critical Review` 262–269 · `### 4. User Approval` 271–298 (AskUserQuestion site ≈287) · `### 5. Transition` 300–308 · `## Hard Gate` 310–315.

**TRUE §1b sub-structure (7 parts a–g; the ticket's 4-item list under-counts):**
`a` prepare shared context (25) · `b` dispatch plan agents + `cortex-resolve-model --role competing-plan` (27–34) · plan-agent prompt template (verbatim fenced block 36–79) · `c` collect results / failure routing (81) · `d` synthesizer dispatch + `cortex-resolve-model --role synthesizer` (83–87) · `e` envelope extraction, LAST-occurrence anchor pattern (89–94) · `f` verdict/confidence routing + legacy comparison table (95–110) · `g` log v2 `plan_comparison` event (112–126).

**Exact extraction boundary**
- **STAYS** in plan.md: line 21 heading `### 1b. Competing Plans (Critical Only)` (byte-identical) + a new short pointer paragraph.
- **MOVES** to competing-plans.md: body lines 23–126 (line 22 = blank after heading; line 127 = blank before §2). All 7 sub-parts move intact.

**§1a criticality branch (the gate the relocation rides):**
`### 1a. Check Criticality` reads criticality via `cortex-lifecycle-state --feature {feature} --field criticality`; line 18 = "If criticality is `critical`: proceed to §1b"; line 19 = "Otherwise (low, medium, high): proceed to §2" (the ≈98% path that never enters §1b).

**Dangling forward-refs inside §1b** (point at sections that STAY in plan.md → become cross-file after the move; definitive list confirmed by the adversarial pass):
| plan.md line | substring | target |
|---|---|---|
| 78 | "Use the plan format defined in **§3** Write Plan Artifact below" | §3 — **inside the verbatim subagent prompt template** |
| 81 | "skip §1b.d–f … proceed to **§3a**" + "fall back to the standard single-plan flow **(§2-§3)**" | §3a, §2-§3 |
| 108 | "fall back to the standard single-plan flow **(§2-§3)**" | §2-§3 |
| 126 | "proceed to **§3a** (Orchestrator Review) … or to **§2**" | §3a, §2 |

Internal refs that move with the body and stay self-consistent: `§1b.d–f` (81), `§1b.f` (93), `§1b.g` (110), `§1b` (123) — but their `### 1b.` heading stays in plan.md, so competing-plans.md should restate a top heading to keep them anchored. **Only one reference points INTO §1b**: the §1a branch (line 18) — nothing downstream (§2–§5, Hard Gate) references the block, so the stub only needs to satisfy the §1a entry path.

## Web Research

#341 is an idiomatic instance of Anthropic's own documented patterns, not a hack:
- **"Pattern 3: Conditional details"** and the **conditional-workflow** tip ("push large workflows into separate files; tell Claude to read the appropriate file based on the task") are structurally identical to a critical-tier-only gate. ([best-practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices))
- **Three-level progressive disclosure**: sibling reference files load only when referenced; **"no context penalty for bundled content that isn't used"** — confirms the resident-byte win. ([Anthropic eng](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills), [overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview))

Anti-patterns / risks to honor:
- **Keep references one level deep** from SKILL.md/plan.md — do not link the cold file from another reference, or the model may partially-read it (`head -100`).
- **Files don't auto-load — the pointer must be explicit and load-bearing**; a path mismatch is the most common cause of a reference silently not loading. For a 2% gate, **under-triggering the cold read is the dominant correctness risk** — the pointer must be a prominent imperative at the decision point.
- **Add a short table of contents** if the cold file exceeds ~100 lines (competing-plans.md will be ≈104) so a partial preview still reveals full scope.
- Path-resolution bugs ([#27332](https://github.com/anthropics/claude-code/issues/27332), [#11011](https://github.com/anthropics/claude-code/issues/11011), [#4754](https://github.com/anthropics/claude-code/issues/4754)) independently validate ADR-0009: bare-relative sibling paths resolve against CWD off-repo.
- Behavioral-equivalence check: a **two-arm dispatch** (a critical case that must still load + run the block; a non-critical case that must NOT load it) is the cheapest high-value verification.

## Requirements & Constraints

- **Maintainability through simplicity** (`cortex/requirements/project.md:55`): "Complexity is managed by iteratively trimming skills/workflows" — this is a direct instance.
- **SKILL.md size cap is SKILL.md-only**: `tests/test_skill_size_budget.py` enumerates `SKILL.md` files, NOT reference files. plan.md and competing-plans.md are references → the 500-line cap does **not** gate them. The cap is cited only because the extraction follows its "extract to references/" idiom.
- **L1 surface ratchet unaffected**: governs SKILL.md `description`+`when_to_use` bytes; frontmatter is untouched.
- **SP001/SP002 path-resolution invariant** (`project.md:46`) + **"resolve `${CLAUDE_SKILL_DIR}` in the body, then propagate"** (`CLAUDE.md`) + **ADR-0009** — the central constraint. `${CLAUDE_SKILL_DIR}` resolves only in a SKILL.md body; a reference file cannot. The §1b stub must NOT embed a raw `${CLAUDE_SKILL_DIR}/references/competing-plans.md` token nor a bare relative path; it names a manifest target the body resolves. ADR-0009's canonical failure: a deleted authoring convention let `${CLAUDE_SKILL_DIR:-$TMPDIR}/...` resolve to a nonexistent path and silently skip work on every run.
- **Bare-Python prohibition (L201)**: `cortex-check-bare-python-import` targets bare `cortex_command` imports only; the §1b prose mention of `importlib.resources` (`plan.md:86`) is backticked descriptive prose, not a cortex_command import → neutral on the move. Avoid introducing a literal bare-python `import` form.
- **#332 guardrail** (`cortex/backlog/332-...:28`, closed ticket prose, not an enforced test): preserve `### 1b. Competing Plans` verbatim. The live test pins the longer `### 1b. Competing Plans (Critical Only)`; the shorter string is a prefix substring, so one stub heading satisfies both.
- **Dual-source mirror**: `.githooks/pre-commit` runs `just build-plugin` (`justfile:589`) → `rsync -a --delete skills/<s>/ → plugins/cortex-core/skills/<s>/`, then fails the commit on mirror drift. Edit canonical only; commit canonical + regenerated mirror together.

## Path-Resolution & Sibling-Read Wiring

**Manifest** lives at `skills/lifecycle/SKILL.md:146` (`### Reference-path propagation (load-bearing)`), preamble at `SKILL.md:148`, 10 targets at `SKILL.md:150`–`159` (clarify-critic, overnight-check sidecar, load-requirements, refine SKILL.md, discovery-bootstrap, complexity-escalation, post-refine-commit, criticality-matrix, **orchestrator-review** at `158`, **critical-review-gate** at `159`). The body resolves `${CLAUDE_SKILL_DIR}` and substitutes absolute paths wherever the phase reference names a target.

**Required wiring (mirrors `critical-review-gate` exactly):**
1. Add one manifest bullet to `SKILL.md` (form: `**competing-plans** (read at Plan §1b on the `critical` branch) → ${CLAUDE_SKILL_DIR}/references/competing-plans.md`). This single bullet IS the body resolve+propagate step — no separate line needed. It belongs in the manifest list, NOT the Step 3 phase-execution table (`SKILL.md:137`–`142`, which lists only top-level phase references).
2. The plan.md stub uses the **named-target idiom** verbatim from `plan.md:260` (orchestrator-review) / `plan.md:269` (critical-review-gate): *"read and follow the competing-plans protocol (use the body-resolved absolute path from lifecycle SKILL.md's Reference-path propagation manifest: the **competing-plans** target)."* Never a bare `references/competing-plans.md` in a Read context.

**Lint behavior** (`cortex_command/lint/skill_path.py`): D2 (SP002) fires on a bare-relative `references/…`/`../`/`skills/…` path in a Read/exec context unless prefixed by `${CLAUDE_SKILL_DIR}/`. The named-target idiom contains no path token → D2 never matches; the manifest's `${CLAUDE_SKILL_DIR}/references/…` form is exempt. D1 (SP001) is scoped to `<!-- BEGIN/END SUBAGENT PROMPT -->` fences / `*-prompt.md` files; plan.md and competing-plans.md have neither, so D1 is inactive (keep any sibling pointer OUT of the moved plan-agent prompt template fence — it carries no skill-dir token today).

**Precedent test shape**: `tests/test_post_refine_commit_wired.py` asserts (a) the new reference exists in BOTH canonical and `plugins/cortex-core/` trees, (b) SKILL.md references the name ≥2× (one manifest bullet contains name twice: bold + path), (c) the consumer points at it. A parallel `test_competing_plans_wired.py` would follow that shape.

## Citation & Test-Pin Integrity

- **`tests/test_skill_section_citations.py`** pins three plan.md headings — §1a (assert line `49`), §1b (assert line `64`: exact `### 1b. Competing Plans (Critical Only)`), §5 (assert line `81`). `_read_headings` reads only `#`-prefix lines, so the **stub satisfies §1b with ZERO test edit**. The ticket's "repoint the test to the stub or the new file" instruction is **unnecessary** — and the test must NOT move to competing-plans.md (it documents the plan.md anchor).
- **`cortex_command/overnight/prompts/orchestrator-round.md:302`** cites "the same LAST-occurrence anchor pattern as the canonical `skills/lifecycle/references/plan.md` §1b" — a **documentation anchor only**. The orchestrator carries its OWN complete inline reimplementation (orchestrator-round.md lines 304–324) and never Reads the skills/plan.md at runtime (its runtime plan.md reads are the *feature's* `cortex/lifecycle/{feature}/plan.md`). Nothing breaks; **repoint to competing-plans.md for accuracy** (recommended — the pattern's body now lives there). `cortex_command/overnight/tests/test_orchestrator_round.py:85` is a docstring comment (not an assertion) — optional repoint.
- **`cortex-check-parity`**: no action. The only `cortex-*` tokens in the body — `cortex-resolve-model` (wired in 8 other skill files) and `cortex-lifecycle-state` (11 others) — stay wired moving between two `skills/**` files. No W003 orphan, no E002 drift, no `.parity-exceptions.md` edit.
- **Mirror parity**: `tests/test_dual_source_reference_parity.py` globs `skills/*/references/*.md` and generates a per-file byte-parity case → competing-plans.md **produces a new case that FAILS until the mirror file exists and matches**. This makes "commit canonical + mirror together" a hard requirement, not a nicety. `tests/test_plugin_mirror_parity.py` has hardcoded `MIRRORED_FILENAMES = ("plan.md", "orchestrator-review.md")` — it won't auto-cover competing-plans.md; optionally add it for symmetry (not required, the glob test already covers it).
- Generic, no-change mentions: `criticality-matrix.md:22`, `docs/agentic-layer.md:119` (generic "competing plans" cells, no §-designator).

## Prior-Art Extraction Pattern

- **#334 fanout relocation** (`df02ac4e`) did the whole extraction in **one 14-file commit**: the move, the consuming-SKILL.md propagation repoint, all cross-skill citers, the test (module-constant AND docstring path together), and the mirror — all in one commit (drift hook forces canonical + mirror together). Follow-up `8f16faf5` scrubbed a bare-noun "see fanout.md" that an absence-grep acceptance check caught. **Lesson: scrub ALL token forms, not only path-form links.** (Caveat: #334 used `git mv`; #341 *adds* a new file and edits in place — so the FileNotFoundError-on-move gotcha does NOT apply here.)
- **Lazy-conditional sibling precedent = `critical-review-gate.md`**: manifest bullet (`SKILL.md:159`, "read … on the skip branch") + a branch in plan.md (`plan.md:269`) that reads it only when the condition holds. #341 mirrors this exactly.
- **`tests/test_lifecycle_references_resolve.py`** is add-safe for the new file (competing-plans.md is under `skills/`, outside the `cortex/lifecycle/`·`cortex/research/`·`lifecycle/`·`research/` scan prefixes, so its own citations aren't validated). The exposure is the *opposite* direction — see Adversarial #2.
- **Discovery source pre-commitment**: `cortex/research/skill-efficiency-remaining-work/research.md` (R3) and epic #340 fix the approach (stub heading + pointer, hot-path resident-token justification) and the discipline ("preserve every test-pinned and overnight-cited heading verbatim, leave a pointer stub rather than deleting").

## Tradeoffs & Alternatives

- **A (ticket) — sibling + heading stub + manifest-wired pointer.** Recommended. Low complexity (mechanically identical to shipped orchestrator-review/critical-review-gate wiring), good maintainability (Plan flow stays owned by plan.md), full ≈10.6 KB hot-path saving, strongest ADR-0009 alignment.
- **B — gate the read in the SKILL.md body's criticality branch.** Rejected. Requires bolting a phase-specific special case onto the deliberately generic Step 3 phase table ("Read only the reference for the current phase", `SKILL.md:144`), fractures the §1a→§1b flow across three files, and the gate (*run competing plans iff critical*) is **already** structural in §1a — B relocates content-loading, not the gate, so "structural over prose" gives it no edge. Same hot-path performance as A but a small every-invocation body tax.
- **C — always-in-manifest, conditionally Read.** Collapses into A: under ADR-0009 the only way to get the path into plan.md is the SKILL.md body manifest, so A's "pointer via manifest" and C's "always in manifest" are the same wiring. No decision between them.
- **Ruled out:** reorder-within-plan.md / "stop reading unless critical" marker (zero byte saving — whole file is Read at once); `offset/limit` partial Read (line-number-coupled, prescribes How, used nowhere here); build-time/hook-time include (criticality is per-feature *runtime* state, unknown at mirror-generation time); folding into criticality-matrix.md (loads more often than the critical arm — makes the block resident *more*).

## Adversarial Review

1. **Tolerance is ±35, not ±20.** `tests/test_lifecycle_kept_pauses_parity.py:28` → `LINE_TOLERANCE = 35`. The kept-pauses entry `kept-pauses.md:18` → `plan.md:281` resolves to a real AskUserQuestion (the only one in plan.md, ≈line 287). Removing ~100 lines of §1b ABOVE it shifts the pause to ≈184–186; the anchor delta (≈95–97) still exceeds 35 → **kept-pauses.md:18 MUST be re-anchored** (derive the exact post-edit line, do not hardcode from the wrong ±20/281 math). This is the touch point the ticket omitted.
2. **`tests/test_lifecycle_references_resolve.py` is a third test in the blast radius — for #341's OWN artifacts.** Its `file_line_citation` check returns "stale" (hard fail) when a cited line exceeds the target's length; scan scope includes `cortex/lifecycle/**` and `cortex/research/**`. Live citations like `plan.md:302`, `plan.md:275–282` already point past the future ~212-line file and survive **only because they are backticked** (the resolver scrubs inline-code spans). **Mitigation: backtick every `plan.md:NNN` citation in #341's research.md / spec.md / plan.md** (done in this file).
3. **Line 78's `§3` ref is inside the verbatim plan-agent prompt template** dispatched to a subagent that sees neither plan.md nor competing-plans.md. "§3 … below" is already unresolvable for that subagent today (the field list is inlined, so §3 is decorative); the move makes "below" doubly false. Rephrase to drop "§3 … below" or qualify "plan.md §3".
4. **Internal `§1b.x` refs lose their heading anchor.** Lines 81/93/110/123 reference `§1b`/`§1b.x` but the `### 1b.` heading stays in plan.md. Mitigation: give competing-plans.md its own top heading (restate `### 1b. Competing Plans (Critical Only)` or an H1 + a short TOC) — harmless to `test_skill_section_citations.py` (it reads only plan.md's headings).
5. **Under-triggering the cold read** is the dominant non-test runtime risk. After extraction the critical arm must reliably perform a *separate* Read; if the model skips the pointer the whole critical-tier flow silently no-ops with no test catching it. Put the read instruction as an **imperative control-flow gate in the §1b stub** ("read and follow … before dispatching"), not a soft mention in the §1a branch line.
6. **Confirmed no-breakage** (planner can skip): SKILL.md size budget (202/500, SKILL.md-only); manifest-count (no test pins the number of bullets); D2 skill-path lint (stub reuses the passing `plan.md:260`/`269` idiom); `cortex-check-parity` W003 (tokens stay wired); `importlib.resources` vs L201 (backticked, not a cortex_command import). Fixture `tests/fixtures/discovery-brief/complex-topic/research.md:34` pins `plan.md:112,285` but is out of scan scope and used as generate-brief input only.

## Open Questions

All resolved by research; the items below are spec-time decisions with a recommendation, not open investigations — none block the transition to Spec.

- **Repoint `orchestrator-round.md:302` (and the `test_orchestrator_round.py:85` docstring)?** Recommendation: **yes**, repoint both to competing-plans.md for documentation accuracy (the cited pattern body moves there). Neither breaks if left as-is; this is cosmetic-accuracy, not a gate.
- **Exact kept-pauses re-anchor line.** Recommendation: derive the new AskUserQuestion line number in plan.md *after* the §1b body is cut (≈184–186), then set `kept-pauses.md:18` to it; verify `test_lifecycle_kept_pauses_parity.py` passes (tolerance ±35). Mechanical, deferred to implementation.
- **competing-plans.md top heading + TOC.** Recommendation: restate `### 1b. Competing Plans (Critical Only)` as the new file's top heading plus a one-line TOC (file ≈104 lines > the ~100-line preview threshold), keeping internal `§1b.x` refs anchored and guarding against partial-read previews.
