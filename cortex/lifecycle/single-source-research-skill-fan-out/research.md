# Research: Single-source research skill fan-out prose into fanout reference (#350)

Fold `skills/research/SKILL.md`'s duplicated fan-out prose into `skills/research/references/fanout.md` references and single-source the considerations hand-off contract, executing the epic-#347 audit verdicts s3, s4, s6, s7, s13, s17, s18 — **deferring the unverified s15** (see Open Questions). fanout.md is the canonical owner; the ticket cuts duplication **out of** SKILL.md, it does not add anything to fanout.md. Baseline: 100 research-adjacent tests pass; SKILL.md is 251 lines; the cortex-core mirror is byte-identical today.

## Codebase Analysis

**Files that change**
- `skills/research/SKILL.md` — canonical, all 7 applied verdicts land here.
- `plugins/cortex-core/skills/research/SKILL.md` — mirror; regenerates via `just build-plugin` (rsync `skills/research/` → mirror) and is enforced by the `.githooks/pre-commit` drift loop. The hook detects drift but **does not auto-stage**: workflow is edit canonical → `just build-plugin` → `git add` both trees → commit together.
- `skills/research/references/fanout.md` — **not edited.** Every cut target already lives here (see below); touching it would re-duplicate and produce a spurious mirror diff.
- Frontmatter (L1–19, `description`) — **not touched** (L1 surface 502B, #302-restored). None of the verdicts reach it.

**Every cut target already resides in fanout.md** (so the trims are pure deletion from SKILL.md): s4 → floor 3 / corner 10 / monotonic / upper-bound (fanout.md L14, L41); s7 → mandatory core (L18), adversarial-always-last (L24), no-keyword-router (L28); s13 → judgment-inherit contract (L33), "no second wave" (L35).

**Pattern to mirror for s4**: `skills/discovery/references/research.md:41-43` is the condensed sibling that already made the "fanout.md pointer + one retained rider" reduction, keeping exactly *"an upper bound on investigation breadth, not a quota — dispatch fewer…"* with **no inline floor/corner numbers**.

**Prior precedent (bears on s15)**: `cortex/lifecycle/adversarially-verified-trim-of-research-skillmd/` (APPROVED, 11/11 requirements PASS, independent auditor/verifier/oracle + 9-item behavioral-equivalence battery) already trimmed this file once and classified the Empty/failed-agent region (L203–211) as `content_class: load-bearing-gate`, `consumption_mode: verbatim-shipped`, `verdict: keep`.

### Per-verdict plan (current line numbers)

- **s3 — Step 1 Parse Arguments (L27–46)**: cut the two example-invocation bullets (derivable from `argument-hint` L18); merge L45's reader-contract paragraph with Step 3's `### Considerations injection` (L61–64) into ONE canonical statement. **Execute jointly with s6.** Keep mode-detection rule/bullets (L35–38), Defaults (L40–43).
- **s4 — Step 2 Determine Agent Count (L47–52)**: cut inline floor(3)/corner(10)/monotonic restatement; keep the fanout.md pointer + exactly one "upper bound, not a quota — dispatch fewer" rider. Removing inline 3/10 makes the Step-2 fanout.md Read **unconditional** (today a simple+low run reads `3` inline and can skip fanout.md).
- **s6 — Considerations injection (L61–64)**: keep the per-angle applicability arms + why (core-only; not Tradeoffs — orthogonal/unnarrowed; not Adversarial — works on summaries); cut the content-not-path/empty-file clauses (dup of Step 1) and the h3-nesting/placement How (structurally demonstrated by the three `### Considerations to investigate…` headings physically present in the core fenced templates at L87–88 / L111–112 / L131–132).
- **s7 — Angle selection (L65–74)**: cut the restated core-roster / adversarial-last / no-keyword-router rules; keep the count arithmetic, template index, the fanout.md pointer ("the authority… is fanout.md. Apply it."), and the `(core)` / `(always last for high/critical)` h4 tags (they structurally re-encode roster + ordering).
- **s13 — Dispatch protocol (L182–196)**: keep ALL ADR-0023 mechanism — the runnable `model=$(cortex-resolve-model --role searcher)` line, core-wave bind, read-only/no-worktree note, wave ordering, full degrade-loud fallback; cut ONLY the trailing "error-correction layer / judgment-inherit contract" rationale and the "no second wave" closer (both in fanout.md L33–35). Realized saving ~50–70 tokens (far below the scorer's 368 estimate; "breadth-first gather" language it cites is not in this section).
- **s17 — Output structure (L216–238)**: keep the skeleton and the `## Considerations Addressed` definition (the sole repo definition); strip the bracketed annotations (angle-roster re-explanation dup of Step 4 opening L199; verbatim re-quote of the empty-agent warning L207; escalator-parse restatement). **Must retain** the one-line `## Open Questions` semantics note including *"omit if no open questions exist"* — sole occurrence repo-wide (L233).
- **s18 — Step 5 Route Output (L239–251)**: fold INTO Step 1's mode-detection block; cut the mkdir/write/announce narration. Removing the terminal Step 5 leaves Steps 1–4 contiguous — **no renumbering** and no orphaned "see Step 5" citation exists anywhere in the repo.

## Web Research

External prior art converges on the ticket's direction:
- **Anthropic, "Effective context engineering for AI agents"** (Sept 2025) endorses the just-in-time pattern — keep lightweight references, load canonical data at runtime — which is structurally this ticket (SKILL.md keeps a pointer; fanout.md is force-read at Step 2). The safety condition it implies: the reference must be *reliably dereferenced*, not a dangling pointer. It also warns that "overly aggressive compaction can result in the loss of subtle but critical context whose importance only becomes apparent later" — argues for preserving literal/operative strings (warning text, enum values, machine-parsed headings) while cutting explanatory prose. And "specialized sub-agents… clean context windows" supports keeping fan-out prompts lean.
- **Token multiplication in fan-out**: n workers consume n× the broadcast tokens — the concrete mechanism behind the ticket's "duplicated prose rides into searcher prompts" premise. (Note: this multiplier applies only to prose that actually enters the per-angle prompts — s3/s6 considerations content — not to orchestrator-body prose like s13/s17/s18, whose saving is plain body reduction.)
- **Context-rot research** (Chroma / Liu et al.) gives a secondary justification: redundant mid-prompt prose plausibly dilutes attention on the material around it, so the trim is not only cheaper.
- **DITA single-sourcing / conref** is the decades-old technical-writing analogue: fragment lives in one file, consumers point to it.
- **Anti-pattern**: collapsing inline content to a bare pointer when the reference is *not* guaranteed resolved before the consuming step. This is exactly the residency condition s7/s13's safety leans on (fanout.md resident via the Step-2 Read).

## Requirements & Constraints

- **L1 surface ratchet (`cortex/requirements/project.md`)**: governs the **frontmatter** `description`+`when_to_use` byte sum only (measured by `bin/cortex-measure-l1-surface`; `research` has budget row `379` in `tests/test_l1_surface_ratchet.py` as a routing-pressure-cluster member). **Body-only trims do not engage the ratchet** — non-blocker for this ticket, provided the frontmatter stays untouched.
- **CLAUDE.md — "prescribe What/Why not How"**: directly licenses s7 (drop procedural rule-restatement) and s13 (cut restated rationale, keep the runnable mechanism). CLAUDE.md's "back-point to ADRs rather than restating rationale" convention licenses s13's citation-not-restatement.
- **CLAUDE.md — resolve `${CLAUDE_SKILL_DIR}` in body then propagate (ADR-0009)**: SKILL.md already uses the compliant markdown-link form for the fanout.md pointers (L49/L67/L184). These links must survive the dedup edits **with the `${CLAUDE_SKILL_DIR}/` prefix intact**.
- **ADR-0022 (considerations file-channel)** mandates what the s3/s6 merged statement must preserve: refine writes/overwrites `research-considerations.md`; the write and the `research-considerations-file=<path>` argument are coupled; research's body reads the file and injects **content, never the path** into the three core-angle placeholders; reader contract = absent/missing/empty/whitespace → no injection, no halt.
- **ADR-0023 (searcher tier / judgment-inherit)** requires each consuming orchestrator body to carry its own runnable resolve+bind — so **s13 cannot fold the mechanism into a pure fanout.md pointer**; it may cut only the restated rationale.
- **Test gates**: `test_research_handoff.py` (file-wide phrasing regexes; governs s3/s6/s18), `test_research_fanout_matrix.py` (parses fanout.md only — zero SKILL.md surface, so s4/s7 are unpinned), `test_l1_surface_ratchet.py` (frontmatter only), `cortex-check-skill-path` (SP001/SP002), `test_dual_source_reference_parity.py` (canonical↔mirror byte parity — same-commit regen).
- **Epic #347 boundary**: "verified trims and offloads." s15 is the one `unverified` id → its inclusion is conditional; the epic's designated home for provisional candidates is sibling ticket **#353**.

## Test-Pin Verification

Green baseline: **100 passed** (`test_research_handoff` 15, `test_research_fanout_matrix` 8, plus escalator/parity/discovery-sizing/resolve-model/adr-citation). Per-verdict pins:

- **s3** → must preserve *somewhere file-wide*: the `read\w*…(that|the) file and substitut\w+ its literal content` phrase, the `(absent|missing|empty|whitespace)…no…injection` clause, the do-not-halt phrase, and `research-considerations-file` never truncated to a bare token. **Only L45's exact wording matches** two of these regexes (see Adversarial — L63's "injects its content" / "inject nothing" does **not** match). Keep L45 essentially verbatim.
- **s4** → no SKILL.md-side pin (`test_research_fanout_matrix.py` targets fanout.md only). Free.
- **s6** → same file-wide regexes as s3; joint execution ensures ≥1 surviving occurrence. `test_three_placeholders_retained` requires exactly 3 `{research_considerations_bullets}` (in the core templates, untouched).
- **s7** → no pin (`pins: []`; whole-tree grep for the roster/router rules is empty). Free.
- **s13** → no pytest string pin (`test_resolve_model.py` tests the CLI, not SKILL.md); preservation is ADR-0023 fidelity, not a test assertion.
- **s15** → **no test pin anywhere** (`"returned no findings"` appears in zero test/source files). Test-unconstrained.
- **s17** → keep `## Open Questions` heading + "omit if no open questions exist" note (sole occurrence); `## Considerations Addressed` sole definition; escalator pins the heading in produced research.md, not SKILL.md prose.
- **s18** → preserve exactly one capital-S `**Standalone mode**` anchor placed **after** L45's considerations paragraph; `test_standalone_reads_nothing` slices anchor → next `\n## ` (H2 only) and asserts no `research-considerations-file` / `read (that|the) file` in the span.

## Adversarial Review

Three traps where the **green suite gives false confidence** — these require human verification at review (they are the verification-vacuity through-line of these trim tickets):

1. **The `do not halt` assertion is non-discriminating.** `test_reader_contract_empty_no_injection`'s `do\s+not\s+halt` regex matches file-wide and has **two** hits: L45 (reader contract) *and* L192 (s13-kept degrade-loud fallback). Since s13 keeps L192, the test stays green **even if the s3+s6 merge drops the reader-contract halt clause entirely**. The reader-contract halt semantics are effectively unpinned — eyeball them manually. (The `(absent|missing|empty|whitespace)…no…injection` half *is* discriminating, so the whole contract can't vanish silently — only the halt half.)

2. **Only L45's exact tokens satisfy two red-green regexes; L63's do not.** L63 says "injects its content" (≠ `substitut\w+`) and "inject nothing" (≠ `no…injection`). If the implementer consolidates into fresh prose or keeps L63's wording as the survivor, two tests flip red. **Mitigation: keep L45 as the canonical Step-1 statement essentially verbatim; trim L63 to per-angle applicability + a "see Step 1" pointer. Do not rewrite L45.** Any surviving mention must be exactly `research-considerations-file` (a space — "research-considerations file" — trips `test_no_stale_bare_value_key`).

3. **s18 slice detail the summary under-stated: `###` does NOT terminate the slice** (the regex needs a space in the 4th char; `### ` has `#`). So the standalone anchor sweeps everything up to `## Step 2`, including any `###` routing sub-block — keep that whole span free of the pinned tokens. Step 4's `## Considerations Addressed` conditional (L236) depends on Step-1-defined "lifecycle mode," **not** on Step 5 — the fold is clean; L244/L250 are Step-5 restatements safe to cut.

Other adversarial confirmations:
- **fanout.md needs zero edits** — the ticket title "single-source *into* fanout.md" must not be read as "add text to fanout.md."
- **s7's `no topic→angle keyword router` removal is the highest-residual, zero-test-coverage behavioral change** — its only backstop is the kept L67 pointer. Acceptable per What/Why-not-How, but name it explicitly in the spec. (Adversarial-last and core-roster removals *are* structurally backstopped by h4 tags + s6-kept roster + s13-kept protocol.)
- **skill-path lint is not a safety net** for the retained pointers: D1/D2 fire only inside subagent-prompt fences or Read/exec contexts; the fanout.md links are body prose, so a dropped `${CLAUDE_SKILL_DIR}/` prefix passes the lint but breaks off-repo runtime resolution. Preserve the full markdown-link form manually.
- **Deferring s15 leaves a *cleaner* state, not worse**: s17 removes the L227–228 re-quote, so after s17 the warning exists only at L207 — de-duplicated.

## Open Questions

- **s15 (Empty/failed agent handling) — Deferred.** Rationale: status `unverified` with empty `pins` (0/0 votes) — there is nothing to "verify pins" against — and a prior adversarially-verified trim (11/11 APPROVED) already classified this exact region `load-bearing-gate` / `verbatim-shipped` / keep. Per the ticket's own instruction ("defer s15 if its pins do not verify, to stay inside epic #347's 'verified trims' boundary"), #350 executes the **7 verified verdicts** and defers s15 to sibling #353 (or a future verified pass). s17 does not transitively require s15, so deferral does not block the plan.

## Considerations Addressed

- *Re-validate s15's pins first; defer if they do not verify* → **Addressed → defer.** s15 has empty pins and an unverified status, and the prior adversarially-verified trim classified the region load-bearing/keep. Recommendation: execute the 7 verified verdicts, defer s15.
- *Confirm s17's keep-list cross-reference to s15 does not transitively force s15's inclusion* → **Addressed → independent.** s17 removes only the duplicate re-quote of the warning (L227–228), treating L207 as the surviving sole instance; it executes correctly whether s15 ships or is deferred. No ordering dependency.
