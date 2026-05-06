# Research: Lifecycle adopts cortex-resolve-backlog-item, delete refine clarify.md

Topic anchor: switch lifecycle's `clarify.md §1` from ad-hoc Python scanning to invoke `cortex-resolve-backlog-item` (the helper refine already uses), then delete refine's near-identical `clarify.md` so both skills reference one canonical file. Phase 1 establishes a predicate-equivalence test against curated inputs; per-case judgment governs each divergence (bug-shaped → accept refine's helper; legitimate-feature → justify helper enhancement).

## Codebase Analysis

### Files that will change

Canonical sources (edit / delete):
- `skills/lifecycle/references/clarify.md` (124 lines) — rewrite §1 from ad-hoc Python scanning to `cortex-resolve-backlog-item` invocation with explicit exit-code branches (0/2/3/64/70). Keep §2–§7 unchanged (already byte-identical with refine's copy).
- `skills/refine/references/clarify.md` (130 lines) — delete entirely after lifecycle's clarify.md becomes the canonical source.
- `skills/refine/SKILL.md` — three call sites must be retargeted to lifecycle's clarify.md:
  - line 38 (`Switch to Context B per references/clarify.md §1` — exit-3 fallback)
  - line 65 (`Read references/clarify.md and follow its full protocol §2–§7`)
  - line 86 (`apply the Research Sufficiency Criteria defined in references/clarify.md §6`)

Plugin mirror (auto-pruned by `just build-plugin` via `rsync -a --delete`):
- `plugins/cortex-core/skills/refine/references/clarify.md` — removed by mirror sync after canonical deletion.
- `plugins/cortex-core/skills/lifecycle/references/clarify.md` — regenerated from canonical update.

Tests:
- `tests/test_resolve_backlog_item.py` (existing, 626 lines, 30+ axis-level cases) — extend with the Phase 1 curated input corpus.
- `tests/test_dual_source_reference_parity.py` — collected pairs decrement by one (refine clarify canonical/mirror pair).
- `tests/test_lifecycle_references_resolve.py` — expected to continue passing without modification.

### Predicate semantics — `bin/cortex-resolve-backlog-item`

Resolution order (deterministic; first match wins):
1. **Numeric dispatch** (`re.fullmatch(r'\d+', input)`): match the parsed leading `NNN-` prefix as integer (handles zero-padding).
2. **Kebab dispatch** (non-numeric input only): match `path.stem` after stripping `^\d+-` prefix verbatim.
3. **Title-phrase dispatch** (fallback): union of two predicates against frontmatter `title:`:
   - **Predicate A (raw)**: `lower(input) ⊆ lower(title)` — case-folded substring; preserves internal whitespace.
   - **Predicate B (slugified)**: `slugify(input) ⊆ slugify(title)` — both sides normalized via `[_/]→space`, `[^a-z0-9\s-]→""`, `[\s-]+→hyphen`, strip leading/trailing hyphens.
   - Candidate set = union, deduplicated by filename. Either predicate firing includes the item.

Exit codes: 0 (unique match), 2 (ambiguous), 3 (no match), 64 (usage error), 70 (IO/parse failure). Stdout JSON on exit 0 has exactly four fields: `filename`, `backlog_filename_slug`, `title`, `lifecycle_slug`.

### §1 text comparison — full quotes

Lifecycle's current `references/clarify.md` §1 (skills/lifecycle/references/clarify.md) instructs Claude to scan `backlog/[0-9]*-*.md` files inline and resolve via numeric ID + kebab slug + "title/phrase fuzzy match" (the fuzzy predicate is not specified). It does not invoke any external binary. Refine's `references/clarify.md` §1 (skills/refine/references/clarify.md L7–L29) invokes `cortex-resolve-backlog-item` with the five-exit-code branch table and a final paragraph documenting the title-phrase Predicate-A/Predicate-B union semantics. The two §1 sections diverge by approximately 10 lines; §2–§7 are byte-identical.

### Cross-skill reference convention — verified

`${CLAUDE_SKILL_DIR}` is a widely-used substitution for **same-skill** reference paths (skills/morning-review/SKILL.md, skills/backlog/SKILL.md, skills/discovery/SKILL.md, skills/lifecycle/SKILL.md, skills/requirements/SKILL.md, plus several plugin-internal usages). A grep across `skills/` and `plugins/` returns **zero matches** for the cross-skill form `${CLAUDE_SKILL_DIR}/..`. Refine's `SKILL.md` does not currently use the substitution at all — it uses bare `references/clarify.md` (lines 38, 65, 86). The proposed cross-skill reference would invent a new path syntax not present in the repo.

### Live-trigger-path observation — lifecycle delegates Clarify to refine

`skills/lifecycle/SKILL.md` lines 210–262 delegate the Clarify, Research, and Spec phases entirely to `/cortex-core:refine`. Line 220 explicitly instructs: "Read `skills/refine/SKILL.md` verbatim. Do not paraphrase or reconstruct `/cortex-core:refine`'s protocol from training context." The phase table at L264 contains only Plan/Implement/Review/Complete — Clarify is not a row. Therefore, lifecycle's `references/clarify.md` is consulted by humans skimming docs, not by the lifecycle skill's runtime resolution path. The runtime path uses refine's `references/clarify.md` (which already invokes `cortex-resolve-backlog-item`). This reframes the predicate-divergence risk: it is a documentation-vs-runtime asymmetry, not a behavior-divergence-in-production claim.

### Likely predicate divergence shapes (against current backlog/ items)

- Items with backticks in title (e.g. `006-make-just-setup-additive`, title `Make \`just setup\` additive by default`) — Predicate B strips backticks via slugify.
- Items with parentheses (e.g. `190-define-rubric-(spike)` style) — Predicate B strips parentheses.
- Items with slashes or underscores in titles — slugify normalizes to hyphens.
- Numeric/version-like patterns in titles (e.g. `v4.7`) — dots stripped; `47` becomes substring-matchable inside a slugified `470`.
- Multi-space inputs — Predicate A preserves whitespace, Predicate B normalizes (so `create  skill` matches `create skill` only via B).

### Helper-churn risk assessment

Most plausible divergences are *more lenient* in refine's helper than in lifecycle's loose prose ("fuzzy match against title:"). The common case requires no helper enhancement; lifecycle simply gains a precise, tested predicate. A divergence that would require helper enhancement is either (a) a class lifecycle's prose specifically excluded but the helper allows (extremely unlikely given the prose's looseness) or (b) a class the prose effectively included via Claude's interpretation but the helper rejects. Either case warrants an OQ3-style evidence record in the spec (per CLAUDE.md MUST-escalation policy applied to behavior-correctness changes), not a default-on enhancement.

## Web Research

The topic is highly cortex-internal. No direct prior art exists for "two Claude Code skills' clarify.md scanning ad-hoc Python vs invoking a CLI helper." The most adjacent applicable practices:

### Predicate-equivalence migration: characterization tests, golden inputs

- **Characterization testing (Feathers)**: when refactoring two implementations onto one canonical helper, write tests that pin current observable behavior of each implementation, then drive the merge against those pins. The Phase 1 "predicate-equivalence test against curated inputs" framing maps onto this idiom directly. Reference: https://michaelfeathers.silvrback.com/characterization-testing
- **Equivalence-class enumeration (ECP)**: partition the input domain into classes the predicate is supposed to treat identically, plus boundary cases. References: https://en.wikipedia.org/wiki/Equivalence_partitioning and https://www.baeldung.com/cs/software-testing-equivalence-partitioning
- **Golden-set / golden-input regression**: a small, version-controlled fixture of inputs + expected outputs, run as a gate before any change ships. Reference: https://ubos.tech/news/golden-set-a-comprehensive-guide-for-ai-regression-testing/
- **Validating test-case migration via mutation analysis (Coker et al., ICSE 2020)**: equivalence is well-defined only when both verify the same behavior. Useful for a one-sentence definition of equivalence in the spec. Reference: https://dl.acm.org/doi/pdf/10.1145/3387903.3389319
- **Adversarial caveat**: a migration test that pins both predicates' current outputs can hide a real bug if the buggy output is pinned. Mitigation: classify each divergence at curation time as "bug-shaped" vs "feature-shaped" rather than auto-pinning — exactly the approach #176 already specifies.

### Cross-skill reference paths after canonical-file consolidation

- **Anthropic skill authoring guidance**: SKILL.md should contain process steps; reference files are separate single-purpose markdown files. The official skills repo (https://github.com/anthropics/skills) co-locates reference files with the skill that owns them; sibling skills link in. References: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices, https://code.claude.com/docs/en/skills
- **Cursor `@path/to/file` mention syntax**: a related "include, don't duplicate" idiom. References: https://github.com/sanjeed5/awesome-cursor-rules-mdc/blob/main/cursor-rules-reference.md, https://forum.cursor.com/t/mention-files-folders-in-markdown-files/24385
- **Anti-pattern**: nested duplicate rules across a monorepo break consistency. Reference: https://forum.cursor.com/t/monorepo-correct-support-and-rules-deduplication/148752

### Slugify-substring UNION case-folded-substring as fuzzy-ID idiom

The exact union pattern is **not** a recognized public idiom. Closest matches:
- `partial_ratio` + lowercase preprocessing in TheFuzz / RapidFuzz — case-fold both sides, then run a substring-style match. References: https://github.com/rapidfuzz/RapidFuzz, https://github.com/seatgeek/thefuzz, https://www.datacamp.com/tutorial/fuzzy-string-python
- Slugify-then-compare (sindresorhus/slugify, python-slugify) is widely used for URL/ID normalization but rarely *unioned* with a separate case-fold pass; slugification is itself a case-folding superset. References: https://github.com/sindresorhus/slugify, https://www.30secondsofcode.org/python/s/slugify/

**Implication**: public practice would prefer slugify-only over the union form. This biases per-case judgment toward "bug-shaped, accept refine's helper" rather than "legitimate feature, enhance the helper." Evidence in this repo: `tests/test_resolve_backlog_item.py` has an ~80-line block of comments where the test author tried to construct a clean Predicate-A-only case and could not — every attempted construction collapsed to "B fires too." This is direct in-repo evidence that Predicate A is rarely-if-ever the only firing predicate.

### Delete-duplicate-keep-reference-stable: edit-the-referrer is the lowest-risk option

For two markdown reference docs in the same repo, monorepo-deduplication guides converge on three options: symlink, edit-the-referrer, or build-time mirror. Symlinks add fragility (IDE indexing duplicates, plugin-packaging quirks); build-time mirrors are heavyweight (cortex already uses one for canonical→plugin); edit-the-referrer is the natural fit when the only consumer is one sibling skill. References: https://embeddedartistry.com/blog/2023/04/07/dealing-with-duplicated-files-in-a-monorepo/, https://mykeels.medium.com/symlinks-in-monorepos-cfc917260520, https://intellij-support.jetbrains.com/hc/en-us/community/posts/115000508810-Duplicate-entries-when-project-is-in-a-symlink-ed-directory

## Requirements & Constraints

### Project-level constraints (requirements/project.md)

> "Maintainability through simplicity: Complexity is managed by iteratively trimming skills and workflows."

> "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."

> "SKILL.md-to-bin parity enforcement: `bin/cortex-*` scripts must be wired through an in-scope SKILL.md / requirements / docs / hooks / justfile / tests reference. Drift between deployed scripts and references is a pre-commit-blocking failure mode."

Per the Conditional Loading section, no area-level requirements file applies to skills/lifecycle/backlog tooling work.

### CLAUDE.md OQ3 escalation policy (the cited "MUST-escalation" rule)

> "To add a new MUST/CRITICAL/REQUIRED escalation, you must include in the commit body OR PR description a link to one evidence artifact: (a) `lifecycle/<feature>/events.log` path + line of an F-row showing Claude skipped the soft form, OR (b) a commit-linked transcript URL or quoted excerpt."

> "Before adding or restoring a MUST, run a dispatch with `effort=high` (and `effort=xhigh` if effort=high also fails) on a representative case and record the result."

OQ3's "all observed-failure types" clause covers correctness, control-flow, routing, latency, format-conformance, tool-selection, hallucination, and any other behavior-correctness failure mode. A helper enhancement that changes which inputs resolve is a routing/correctness change and would trigger OQ3 evidence requirements unless the change is removing complexity rather than adding behavior.

### Parent epic 172 constraints

> "Stream A (low-risk cross-skill collapse): 174 (clarify-critic.md / orchestrator-review.md / specify.md byte-identical collapses), 175 (promote refine clarify-critic.md to canonical), **176 (lifecycle adopts cortex-resolve-backlog-item, delete refine/references/clarify.md)**."

> "The original goal — adopt vertical-planning patterns from CRISPY into plan.md and spec.md templates — remains, but lands AFTER the cross-skill duplication collapses so the new sections live in one canonical home rather than getting added to duplicated copies."

Stream A's canonical direction is **lifecycle** (174 collapses to lifecycle, 175 elevates lifecycle's clarify-critic, 176 places the helper-based §1 in lifecycle's clarify.md).

### Audit pressure-test correction (research/vertical-planning/audit.md)

> "**`clarify.md` adoption of `cortex-resolve-backlog-item` is a no-op | NOT NO-OP.** Lifecycle's current §1 does ad-hoc Python scanning. Refine's helper has its own predicate (set-theoretic union of raw substring AND slugified substring). These match different sets, particularly for inputs with uppercase or punctuation. Adopting refine's flow changes which backlog items resolve unambiguously vs as ambiguous. **Test before deletion.**"

This is the load-bearing constraint that makes Phase 1 (predicate equivalence test) a precondition, not an option.

### Vertical-planning research budget constraint

> "Cortex's instruction-budget surface (2,148 lines) is already 43% over Horthy's threshold — adopting outlines pushes further into the regime he warns against."

This sets a hard ceiling on adding lines to clarify.md. Helper enhancements that add prose to §1 compound the budget problem; deletions reduce it.

### Stream-A coordination with siblings 174 and 175

Ticket 175 ("Promote refine clarify-critic to canonical with schema-aware migration") will edit `skills/lifecycle/references/clarify.md` §3a Critic Review section to point at refine's clarify-critic.md, and will delete `skills/lifecycle/references/clarify-critic.md`. 175's edits land on the same file 176 modifies, but in disjoint sections (§1 vs §3a). Merge conflict risk is low if both land in close succession; coordination must be explicit in 176's spec.

### Scope-overlap risk: ticket 184

Ticket 184 ("Merge clarify and research lifecycle phases into single investigate phase") proposes to merge Clarify and Research into a single "Investigate" phase, creating `skills/lifecycle/references/investigate.md` and folding clarify.md content into it. If 184 lands after 176, the §1 helper-adoption work persists in the merged file (184 explicitly preserves Clarify's load-bearing What). If 184 lands first, 176's edit target moves from `clarify.md` to `investigate.md`. Sequencing must be addressed in 176's spec.

## Tradeoffs & Alternatives

Five alternatives weighed. Below is each alternative, refined per the codebase analysis above (the "${CLAUDE_SKILL_DIR}/.." precedent claim has been removed because verification found zero matches in the repo).

**Alternative A — Lifecycle adopts refine's helper-based §1; delete refine's clarify.md.** Rewrite `skills/lifecycle/references/clarify.md` §1 to invoke `cortex-resolve-backlog-item` with the five exit-code branches and the title-phrase predicate explainer. Delete `skills/refine/references/clarify.md`. Update three call sites in `skills/refine/SKILL.md` (lines 38, 65, 86) to point at the canonical lifecycle path using a relative or substituted form (the exact syntax must be specified in spec — no precedent in repo). The `build-plugin` recipe auto-prunes the mirror via `rsync --delete`. Phase 1 contract test slots into `tests/test_resolve_backlog_item.py`.
- Pros: Aligns with Stream A's lifecycle-canonical direction. Replaces loose prose with a precisely-defined helper that has 30+ existing tests. Smallest blast radius — three files touched canonical, one mirror auto-pruned.
- Cons: Couples refine to lifecycle (refine breaks if lifecycle's clarify.md is renamed). The cross-skill reference syntax must be invented (no in-repo precedent). Lifecycle's clarify.md `Constraints` table and §6 Sufficiency Criteria are now read by refine's flow, mildly bloating refine's read budget.

**Alternative B — Refine remains canonical; delete lifecycle's clarify.md instead.** Inverse direction. Lifecycle's runtime path already delegates to refine, so the live behavior contract is unchanged. Lifecycle's clarify.md is deleted; lifecycle's SKILL.md (and any prose that references `references/clarify.md`) updates to point at refine's path.
- Pros: Fewer text edits to clarify.md itself (refine's already has the helper-based §1).
- Cons: Reverses the established Stream A direction (174 and 175 both collapse to lifecycle). Inverts the natural ownership hierarchy (lifecycle is the broader skill with 12+ reference files). Breaks symmetry with siblings.

**Alternative C — Move clarify.md to a neutral shared location (`skills/_shared/clarify.md`).** Extract clarify.md to a new shared directory; both SKILL.md files reference the shared path.
- Pros: Eliminates skill-to-skill coupling; symmetric ownership.
- Cons: Introduces a new sharing convention with no precedent. Would require updates to `justfile` `build-plugin` recipe (which globs per-skill SKILLS arrays), `tests/test_dual_source_reference_parity.py` (path-routes by second-path-component skill name), `validate-skill.py`, `validate-callgraph.py`, and the dual-source mirror pre-commit hook. Stream A's other tickets (174, 175) reject this approach implicitly. High implementation cost, misaligned with current conventions.

**Alternative D — Symlink or build-time copy enforcement.** Keep two physical files; enforce identity via a pre-commit hook or filesystem symlink.
- Pros: No skill-to-skill cross-reference at runtime.
- Cons: Symlinks survive local rsync but distribute unpredictably across plugin-install paths; `git` tracks the link but plugin packaging on the receiving machine may materialize as regular files. Adds a new dual-source axis the repo doesn't currently maintain. Doesn't address the §1 predicate divergence — the goal is to adopt the helper-based contract, not freeze two divergent prose blocks. Highest maintenance cost, lowest clarity gain.

**Alternative E — Helper enhancement to preserve lifecycle semantics, then adopt as in A.** Run Phase 1's predicate-equivalence test. Where lifecycle's prose-implied resolution and the helper diverge, per-case judgment: bug-shaped → accept the helper; legitimate-feature → enhance `bin/cortex-resolve-backlog-item` (e.g., a new regex predicate or relaxed slugify rule) before adopting.
- Pros: Single canonical file (same end-state as A) without losing match coverage. Phase 1 forces explicit per-case decisions rather than hand-waving.
- Cons: Speculative absent Phase 1 evidence; helper-churn risk (every added predicate enlarges the global match-set, potentially turning previously-disambiguous resolutions into ambiguous ones). OQ3 evidence-record applies to behavior-correctness changes. Likely enhancement (if any divergence is bug-shaped) is small (≤20 lines, one predicate) — but the test author's documented inability to construct a Predicate-A-only case suggests no enhancement will actually be needed.

**Recommended approach**: **Alternative A**, with Alternative E as a contingent sub-step inside A's Phase 2 if Phase 1 surfaces a legitimate-feature divergence (and even then, only after an OQ3 evidence record). Reasoning grounded in the four dimensions:
- *Implementation complexity*: A is the minimum-blast-radius option (three canonical files, one auto-pruned mirror). Phase 1 contract test extends an existing 626-line test file.
- *Maintainability*: One canonical file vs two; eliminates the byte-identical-except-§1 drift hazard the audit explicitly flagged. Matches 174/175 direction.
- *Performance*: Negligible difference at prompt-evaluation time.
- *Alignment with existing patterns*: A is consistent with Stream A's lifecycle-canonical direction and with the `build-plugin` rsync-based mirror generation. The cross-skill reference syntax must be invented but is a one-line decision (relative path vs `${CLAUDE_SKILL_DIR}/../...`).

## Adversarial Review

Verification confirms three of the adversarial findings as correct in fact (independently checked during synthesis):

**Confirmed F1 — Lifecycle's clarify.md is dead code in the live trigger path.** `skills/lifecycle/SKILL.md` lines 210–262 explicitly delegate Clarify (and Research and Spec) to `/cortex-core:refine`. Line 220: "Read `skills/refine/SKILL.md` verbatim." The phase table at L264 contains only Plan/Implement/Review/Complete — Clarify is not a row. Refine's `references/clarify.md` is what runs; lifecycle's is consulted only by humans skimming docs. This reframes the predicate-divergence risk as a documentation-vs-runtime asymmetry rather than a behavior change in production. The "predicate equivalence test" still has value (it validates that the documented prose matches the live runtime), but the urgency is documentation-coherence, not regression-prevention.

**Confirmed F2 — `${CLAUDE_SKILL_DIR}/..` cross-skill form has zero matches.** Every existing usage is same-skill `${CLAUDE_SKILL_DIR}/references/...`. The cross-skill reference syntax must be invented; spec must specify it explicitly (relative path `../lifecycle/references/clarify.md`, or substituted `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md`, or a different convention entirely).

**Confirmed F3 — Three call sites in refine/SKILL.md, not two.** Lines 38, 65, 86 all reference `references/clarify.md`. Line 38 (Context B branch description) is the exit-3 fallback path — must not be missed.

**Confirmed F11 — Discovery's clarify.md exists as a third file.** `skills/discovery/references/clarify.md` (65 lines) has its own §1 that says "There is no backlog item to resolve — that is what discovery will create." Per the audit, it is ~5 lines reducible but not collapsible with the lifecycle/refine pair. Post-176 the repo has TWO clarify.md files (lifecycle + discovery), not one.

**Confirmed F13 / scope-overlap with 175 and 184.** 175 modifies the same file (`skills/lifecycle/references/clarify.md` §3a Critic Review section, disjoint from §1) and deletes `skills/lifecycle/references/clarify-critic.md`. 184 proposes to merge Clarify and Research into an Investigate phase, which would relocate the §1 content into a different file. Sequencing must be addressed.

Other adversarial findings worth carrying into the spec:

**F5 — Phase 1 contract test framing**: characterization testing pins observable behavior, but lifecycle's "current behavior" was Claude's prose interpretation, which is non-deterministic. The test cannot be a true two-way equivalence; it is a one-sided pin of helper behavior plus a per-case judgment record on each documented divergence. Reframe Phase 1 in spec as "helper-behavior pin + judgment record on documented divergences," not "two-way predicate equivalence."

**F6 — Helper's union design is on shaky ground**: `tests/test_resolve_backlog_item.py:300-389` contains ~80 lines of comments where the test author tried and failed to construct a clean Predicate-A-only case. Web research corroborates: the union form is not a recognized public idiom. Adopting the helper as canonical via 176 entrenches a design that may need simplification later. This is not a blocker for 176, but it argues for a separate ticket to evaluate whether Predicate A should be removed entirely (slugify-only).

**F7 — Helper has had two real post-deployment bugs in 5 months** (`091e2c4` numeric-padded-ID match; `5949691` plugin-mirror path resolution). Once lifecycle adopts the helper as the sole resolution path, lifecycle inherits the helper's bug surface. Not a blocker — the helper is now well-tested — but worth noting for the spec's risk section.

**F9 — Atomicity of the change.** Recommended mitigation: collapse Phase 2 (lifecycle adoption) and Phase 3 (refine deletion + path rewrite) into a single commit. Phase 1 contract test can ship in the same commit or as the gating prior commit.

**S1 — Helper invocation log surface.** `bin/cortex-resolve-backlog-item:16` calls `cortex-log-invocation` on every run. Adopting the helper increases the size of `lifecycle/sessions/{id}/bin-invocations.jsonl`. Side effect, not a blocker.

**S2 — `CORTEX_BACKLOG_DIR` env override.** The helper honors this env var; lifecycle's prose did not. Adoption changes the resolution context. Low risk; worth a one-line note in spec.

**A4 — Plugin-build pruning verification.** The `justfile build-plugin` recipe should be confirmed to use `rsync --delete` (or equivalent deletion-aware sync) before relying on auto-pruning. If the recipe uses `cp -r`, deletion is not propagated and parity tests would fail for orphaned mirrors.

## Open Questions

The questions below are flagged for resolution during the Spec phase. Each is annotated with disposition.

- **Cross-skill reference syntax**: which form should refine's SKILL.md use to reference lifecycle's clarify.md? Options: relative path (`../lifecycle/references/clarify.md`), substituted form (`${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md`), or a different convention. **Deferred — will be resolved in Spec by asking the user.**

- **Sequencing with sibling tickets 175 and 184**: should 176 land before 175 (which edits the same file's §3a) and before 184 (which may relocate §1 content into investigate.md)? **Deferred — will be resolved in Spec by asking the user.**

- **Phase 1 contract-test framing**: should Phase 1 be framed as "helper-behavior pin + per-case judgment record" rather than "two-way predicate equivalence" (per F5)? **Deferred — will be resolved in Spec by asking the user, with the F5 finding presented for context.**

- **Helper-union simplification (F6)**: should adopting the helper as canonical via 176 be coupled with a follow-up ticket to evaluate whether Predicate A should be removed (slugify-only)? **Deferred — will be resolved in Spec or carried as a separate backlog item.**

- **Atomicity of the rollout (F9)**: should Phase 2 (lifecycle adoption) and Phase 3 (refine deletion + path rewrite) land in a single commit, or separately? **Deferred — will be resolved in Spec.**

- **Plugin-build pruning (A4)**: confirm during Spec that `justfile build-plugin` uses `rsync --delete` before relying on auto-pruning. **Resolved during Spec by reading the justfile recipe (small mechanical check).**

## Considerations Addressed

- Evaluate whether the helper-enhancement option in Phase 1 risks adding back complexity that parent epic 172's broader skill-corpus deduplication intent is trying to trim, and whether per-case judgment can be biased toward minimal helper churn — **addressed**: web research finds the helper's Predicate-A/Predicate-B union is not a recognized public idiom and `tests/test_resolve_backlog_item.py:300-389` contains 80 lines of comments where the test author could not construct a Predicate-A-only case, which biases per-case judgment toward "bug-shaped, accept refine's helper" rather than "legitimate feature, enhance the helper." Adversarial review further argues for a separate follow-up ticket to evaluate removing Predicate A entirely. Per-case judgment can and should be biased toward minimal helper churn; OQ3 evidence requirements apply to any behavior-correctness change.
