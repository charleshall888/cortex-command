# Review: reframe-discovery-to-principal-architect-posture

## Stage 1: Spec Compliance

### R1 — Add `## Architecture` section to research-phase output template
- **Expected**: `grep -c "^## Architecture$" skills/discovery/references/research.md` ≥ 1 AND `grep -c "^### Pieces$|^### Integration shape$|^### Seam-level edges$|^### Why N pieces$" ...` = 4 AND walk-back rule documented inline.
- **Actual**: `## Architecture` heading present at line 115; the four sub-headings (`### Pieces`, `### Integration shape`, `### Seam-level edges`, `### Why N pieces`) all present (count = 4). Walk-back rule documented inline at lines 152-157 ("If the gate above instructs a merge, re-emit `### Pieces` and re-walk `### Integration shape` and `### Seam-level edges`..."). Non-constructive-shape permissive paragraph present at lines 121-124.
- **Verdict**: PASS

### R2 — Optional scope-envelope output in clarify phase
- **Expected**: `grep -c "Scope envelope" skills/discovery/references/clarify.md` ≥ 1 AND optional with both fire and skip cases.
- **Actual**: `Scope envelope` appears at clarify.md:58 as the fifth output, documented as `(optional)`. Fire case ("when boundaries are tractable") and skip case ("No envelope needed" with one-line reason) both documented at lines 58-62. The "agent decides per topic" framing is honored verbatim.
- **Verdict**: PASS

### R3 — Falsification-framed "Why N pieces" gate
- **Expected**: `grep -c "named contract surface|one Role/Integration/Edges paragraph|distinguishing detail" skills/discovery/references/research.md` ≥ 2 AND `piece_count > 5` threshold named.
- **Actual**: Grep returns 5 (well above ≥ 2). The structural-coherence rule is captured at research.md:142-144 verbatim from spec ("Merge if the two pieces share ≥1 named contract surface AND can be described in one Role/Integration/Edges paragraph without losing distinguishing detail"). The `piece_count > 5` threshold is named at line 138 and 149.
- **Verdict**: PASS

### R4 — Phase-boundary approval gate between research and decompose
- **Expected**: `grep -c "approval_checkpoint_responded|approve|revise|drop|promote-sub-topic" skills/discovery/SKILL.md skills/discovery/references/*.md` ≥ 4 AND four options documented with explicit semantics AND no `parent_discovery:` frontmatter field appears AND body-section reference format shown inline.
- **Actual**: Grep counts: SKILL.md = 7, decompose.md = 10, orchestrator-review.md = 3 (total 20, well above ≥ 4). Four options documented at SKILL.md:76-79 with explicit semantics (`approve`, `revise`, `drop`, `promote-sub-topic`). The body-section reference format `## Promoted from\n\nDiscovery: research/<current-topic>/` appears verbatim at SKILL.md:79. No `parent_discovery:` frontmatter field in any skill prose — the term only appears in spec/plan as the prohibition record.
- **Verdict**: PASS

### R5 — Uniform piece-shaped ticket body template
- **Expected**: `grep -c "^## Role$|^## Integration$|^## Edges$|^## Touch points$" skills/discovery/references/decompose.md` ≥ 4 AND Edge-vs-Touch-point distinction documented inline with at least one worked example.
- **Actual**: All four headers present (Role:18, Integration:22, Edges:27 and :47 [the worked example], Touch points:52). Edge-vs-Touch-point semantic distinction documented at decompose.md:42 verbatim from spec. Worked example at lines 44-59 shows Edges naming contracts by name and Touch points carrying `bin/cortex-lifecycle-state:42-58` path:line citation.
- **Verdict**: PASS

### R6 — Section-partitioned prescriptive-prose check with LEX-1 regex baked into spec
- **Expected**: `grep -c "section-partitioned|path:line|section-index|quoted-prose-patch" skills/discovery/references/decompose.md` ≥ 3 AND three regex patterns + section-boundary rule + worked examples + 2 anti-patterns documented inline (`grep -c "PASSES|FLAGS|NOT flagged" ...` ≥ 4).
- **Actual**: First grep returns 11 (≥ 3). Second grep returns 6 (≥ 4). The three patterns are spelled out at decompose.md:104-106; section-boundary rule at :110; worked examples at :112-119 (2 PASSES + 2 FLAGS + 2 NOT flagged anti-patterns).
- **Verdict**: PASS

### R7 — Ship `bin/cortex-check-prescriptive-prose` as Python script (Unit B)
- **Expected**: `test -x bin/cortex-check-prescriptive-prose` exits 0 AND `--help` exits 0 AND `grep -c "check-prescriptive-prose" justfile` ≥ 1 AND `grep -c "check-prescriptive-prose" .githooks/pre-commit` ≥ 1 AND parity gate passes. Test acceptance: ≥ 7 functions covering 7 named cases.
- **Actual**: Script is executable; `--help` exits 0. justfile:352-353 has the recipe; `.githooks/pre-commit` invokes it as Phase 1.85 at line 194 (correctly ordered AFTER Phase 1.5 parity and Phase 1.8 events-registry, matching the spec's "AFTER cortex-check-parity AND AFTER cortex-check-events-registry" requirement). `bin/cortex-check-parity --staged` exits 0. Test file has 8 functions (≥ 7). The seven case-coverage axes (a-g) from spec acceptance are exercised: clean section / path:line in Role / §N in Edges / fenced block ≥2 lines in Integration / Touch points exempt / bare path not flagged / inline backtick not flagged. Pre-commit insertion is gated by staged-path matching `skills/*|backlog/*.md|bin/cortex-check-prescriptive-prose` per spec.
- **Verdict**: PASS

### R8a — Extend events-registry checker to support dual-target syntax (Unit A)
- **Expected**: `grep -c "research-topic-events-log" bin/cortex-check-events-registry` ≥ 1 AND staged gate exits 0 AND unit test validates pipe-split parsing.
- **Actual**: `research-topic-events-log` present in `ALLOWED_TARGETS` frozenset at line 73. Pipe-split parsing in the target-cell validator at lines 232-253 — splits on `|`, validates each part independently against `ALLOWED_TARGETS`, accepts empty/invalid parts as `INVALID_ROW`. `_split_table_row` helper at lines 99-125 recognizes `\|` as a literal escape so dual-target syntax round-trips through the cell-splitter. `bin/cortex-check-events-registry --staged --root .` exits 0 against the current registry.
- **Verdict**: PASS

### R8b — Three new events with dual target (Unit A)
- **Expected**: `grep -c "^| \`architecture_section_written\`|^| \`approval_checkpoint_responded\`|^| \`prescriptive_check_run\`" bin/.events-registry.md` = 3 AND events-registry staged gate exits 0.
- **Actual**: All three rows present at lines 109-111 of `.events-registry.md`. Each declares dual target `per-feature-events-log \| research-topic-events-log` (pipe-escaped), category `audit-affordance`, consumer `tests/test_discovery_events.py (tests-only)`, owner `charliemhall@gmail.com`, ≥ 30-char rationale citing EVT-3. The R12 re-walk re-use of `architecture_section_written` with `re_walk_attempt` field is documented in the rationale column. Events-registry gate exits 0.
- **Verdict**: PASS

### R9 — Helper module `cortex_command/discovery.py` for events emission (Unit F)
- **Expected**: `python3 -m cortex_command.discovery --help` exits 0 AND four subcommands addressable AND `tests/test_discovery_module.py` ≥ 7 test functions covering (i) each emit-* subcommand validation+emission, (ii) `-N` slug suffix honored, (iii) active-lifecycle env override honored, (iv) emit-* invokes `resolve-events-log-path` (not hardcoded).
- **Actual**: Module imports clean; four subcommands wired (`emit-architecture-written`, `emit-checkpoint-response`, `emit-prescriptive-check`, `resolve-events-log-path`). Path-resolution implementation at lines 151-195 honors active-lifecycle env via `_active_lifecycle_slug` (lines 86-122 — reads `LIFECYCLE_SESSION_ID` and matches `.session`/`.session-owner` files). The `-N` suffix is honored because the agent passes `{topic}-N` as the topic argument and the resolver returns `research/{slug}/events.log` (slug already includes the suffix). The three emit-* functions internally call `resolve_events_log_path` (lines 384, 411, 438) — never hardcoded. `tests/test_discovery_module.py` has 14 functions covering all four axes.
- **Verdict**: PASS

### R10 — Trim decompose protocol (Unit C)
- **Expected**: `grep -c "premise-unverified|canonical pattern|all items flagged|Return to research|propagation|originating|invariant" decompose.md` = 0 AND `grep -c "## Architecture|single-piece|zero-piece" ...` ≥ 3.
- **Actual**: First grep returns 0 (removals verified). Second grep returns 3 hits (`## Architecture` referenced at :9, `single-piece` at :81 and :173, `zero-piece` at :83/:88/:173/:187). The §2 rewrite consumes the Architecture section. §4 has single-piece branch (line 81) and zero-piece branch (lines 83-88, with `decomposition_verdict: zero-piece` frontmatter). R3 per-item-ack is replaced by R15 batch-review gate at §5 (lines 123-135).
- **Verdict**: PASS

### R11 — Update `tests/test_decompose_rules.py` for trimmed protocol (Unit C)
- **Expected**: `just test tests/test_decompose_rules.py` exits 0 AND ≥ 14 test functions partitioned as 3 architecture-consumption + 2 single-piece + 2 zero-piece + 3 uniform-template + 2 batch-review + 2 prescriptive-prose.
- **Actual**: 14 test functions exactly. Partition (by function name):
  - 3 architecture-consumption (lines 105, 114, 126)
  - 2 single-piece branch (lines 140, 152)
  - 2 zero-piece branch (lines 162, 176)
  - 3 uniform-template body sections (lines 191, 204, 220)
  - 2 R15 batch-review gate (lines 242, 259)
  - 2 prescriptive-prose-check integration (lines 272, 284)

  All 14 pass (`uv run pytest tests/test_decompose_rules.py -q` reports 14 passed). Removed tests for R2(a)/(b)/E9, R3 per-item-ack, R4 cap, R5 flag propagation, R7 flag events, E10 invariant — verified via the R10 grep returning 0.
- **Verdict**: PASS

### R12 — Pre-implementation spec-phase re-walk
- **Expected**: `test -f lifecycle/reframe-discovery-to-principal-architect-posture/re-walk.md` exits 0 AND both corpora walks documented with explicit pass/fail verdicts against (i)/(ii-a)/(iii) AND (ii-b) post-R7 deferral noted.
- **Actual**: re-walk.md present (802 lines). Both corpora walked: vertical-planning (Corpus 1) and repo-spring-cleaning (Corpus 2). Final summary table (lines 779-787) records: criterion (i) PASS on both corpora (vertical-planning produced 8 pieces, in range 8-10; repo-spring-cleaning produced 3, in range 2-4); criterion (ii-a) PASS on both (zero expected violations across 24+9 forbidden sections); criterion (ii-b) agreed; criterion (iii) PASS on both (every Edges section names a specific contract surface). The (ii-b) scanner-pass deferral is documented at lines 17-18 and revisited at 687/755-765 with the post-R7 re-execution noted. The re-walk landed in commit f313fc3 (third commit in the ledger), BEFORE Tasks 3/5/6/7/8 — implementation order respected.
- **Verdict**: PASS

### R13 — Define re-run discovery slug-collision behavior
- **Expected**: `grep -c "superseded:|-2|slug.*collision|topic-N" skills/discovery/SKILL.md` ≥ 2 AND four sub-rules (a)/(b)/(c)/(d) documented AND `tests/test_superseded_frontmatter_tolerance.py` exists and passes.
- **Actual**: Grep returns 4 (≥ 2). The four sub-rules (a) Fresh slug, (b) `superseded:` frontmatter, (c) Prior artifact untouched, (d) Reconciliation manual — all documented at SKILL.md:54-58. Events-log resolution under `-N` re-runs is documented at SKILL.md:60 (routes via helper's `resolve-events-log-path` honoring the `-N` suffix). `tests/test_superseded_frontmatter_tolerance.py` exists with 6 test functions exercising the backlog index generator, clarify-critic loader, lifecycle discovery-bootstrap loader, and the YAML round-trip. All 6 pass.
- **Verdict**: PASS

### R14 — Rewrite ticket #195 body to comply with prescriptive-prose check (Unit D)
- **Expected**: `bin/cortex-check-prescriptive-prose --root . backlog/195-reframe-discovery-to-principal-architect-posture.md` exits 0.
- **Actual**: Scanner exits 0 on the ticket. Body structure at lines 26-67: `## Role`, `## Integration`, `## Edges`, `## Touch points`. All path:line citations and section-index citations (`§5`, `§6`, `:147`, `:24-27`, `:35`, `:37-42`, `:46-52`, `:70`) live exclusively in `## Touch points`. Edges names contracts by name (e.g., "phase-transition contract", "events-registry schema") without file paths.
- **Verdict**: PASS

### R15 — Post-decompose batch-review gate
- **Expected**: `grep -c "approve-all|revise-piece|drop-piece|decompose-commit" skills/discovery/references/decompose.md skills/discovery/SKILL.md` ≥ 4 AND gate documented with all three options + user-blocking semantics.
- **Actual**: Grep across the two files returns 15+ matches (well above ≥ 4). Gate documented at decompose.md:123-135 with all three options (`approve-all`, `revise-piece <N>`, `drop-piece <N>`). User-blocking semantics explicit at :133 ("The gate is user-blocking: no tickets commit to `backlog/` until `approve-all` fires"). The `approval_checkpoint_responded` event with `checkpoint: decompose-commit` is emitted via the helper module per :135. SKILL.md:92-94 cross-references back to decompose.md §5.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent. The `cortex_command/discovery.py` module mirrors `cortex_command/critical_review.py` per the spec's "skill-helper modules" pattern (project.md L33). Subcommand verbs (`emit-architecture-written`, `emit-checkpoint-response`, `emit-prescriptive-check`, `resolve-events-log-path`) follow the verb-noun shape used elsewhere. Event names use the `<thing>_<verb>ed` snake_case shape already in the registry. Commit messages follow the project's imperative-mood, ≤72-char-subject convention.

- **Error handling**: The helper module validates payloads via `_validate_architecture_payload` / `_validate_checkpoint_payload` / `_validate_prescriptive_payload` before append; raises `ValueError` with a slug-naming message on bad input; the CLI wrappers convert to exit-code 2 with stderr message. The `append_event` function uses tempfile + `os.replace` for atomic append, matching critical_review.py's precedent. `_default_repo_root` raises `RuntimeError` with an actionable message when git is unavailable. The prescriptive-prose scanner's `_read_staged_blob` swallows non-text staged blobs (UnicodeDecodeError → None) so binary file diffs don't crash the gate — reasonable for a markdown-targeted scanner. The events-registry `_split_table_row` correctly distinguishes `\|` (literal) from `|` (cell boundary), preventing dual-target syntax from accidentally validating as a malformed extra cell.

- **Test coverage**: 42 new tests across the four new test files; all 42 pass. Full suite (793 passed, 12 skipped, 1 xfailed) is green. R11's partition is exact (3+2+2+3+2+2 = 14). R9's path-resolution tests cover the `-N` suffix axis AND the active-lifecycle env override axis (both spec-required). The R7 scanner tests cover all seven case axes from the spec acceptance (clean / path:line in Role / §N in Edges / fenced ≥2 lines / Touch points exempt / bare path narrative / inline-backtick narrative). The R12 re-walk artifact is binary-evaluable (the summary table records explicit PASS verdicts against the four spec criteria) and stayed within the "produce hypothetical Architecture sections + ticket bodies" scope per spec.

- **Pattern consistency**: All implementation Units (A, B, C, D, E, F) landed as atomic commits per the spec's Implementation Topology section. Unit A (ecc6366) bundled parser update + registry rows + extended target enum together — Phase 1.8 of pre-commit would have blocked partial commits. Unit B (a1cf28e) bundled scanner + justfile recipe + pre-commit insertion + decompose.md prose reference — Unit B's parity gate is satisfied (parity scan finds the `check-prescriptive-prose` reference in justfile + decompose.md). The R12 re-walk landed before Tasks 3/5/6/7/8 per the spec's "Unit A → Unit B → (C/E/F parallel) → Unit D → R12" order — actually a slight order deviation: the re-walk commit f313fc3 landed AFTER Unit A and Unit B but BEFORE Units C/D/E/F, which matches the spec's "land Units A and B, then R12 gates Tasks 3/5/6/7/8" pre-implementation-gate framing. Plugin-tree mirrors regenerate via `just build-plugin` from canonical sources per the established dual-source mirror discipline.

- **Caveat (non-blocking)**: Running `bin/cortex-check-prescriptive-prose --staged --root .` against the full repo surfaces one violation in `backlog/197-independently-sourced-phrase-corpus-for-skill-routing.md:18` (an `R2` section-index in a `## Role` section). Ticket #197 pre-existed before the LEX-1 scanner was added (commit 0c5fe5d landed 2026-05-11 17:25, the scanner landed 2026-05-11 20:22). The pre-commit hook's staged-path filter (`skills/*|backlog/*.md|bin/cortex-check-prescriptive-prose`) means the violation is not currently blocking commits since #197 is unmodified; it will surface the next time #197 is staged. This is a pre-existing baseline issue surfaced by the new scanner, not a defect introduced by this implementation. Recommend filing a follow-up ticket to retroactively bring #197 into compliance, or accept as a known-and-tolerated pre-existing surface that will self-correct when the ticket is next touched.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
