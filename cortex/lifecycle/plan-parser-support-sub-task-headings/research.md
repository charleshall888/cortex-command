# Research: Plan parser — first-class `### Task Na` sub-task headings (#297)

**Goal:** Make `### Task Na` letter-suffixed sub-task headings parse into first-class, independently-dispatchable units whose intra-parent ordering and cross-task dependencies survive batching and dispatch — replacing the #293 fail-loud guard (commit 87239c4b) — without changing how integer-only plans parse or dispatch.

**Tier:** complex · **Criticality:** high · Parent: #293 (`bug`, complete).

> Synthesis note: a parallel adversarial pass **overturned** the core wave's headline claim that "ordering is irrelevant, batching is type-agnostic." See `## Adversarial Review` and OQ-1 — the shared-worktree overnight concurrency model makes same-batch sub-task parallelism a genuine correctness decision, not a display nicety.

---

## Codebase Analysis

The change is parser/data-model-centric, landing in three code files plus doc/template surfaces.

**`cortex_command/pipeline/parser.py`**
- `FeatureTask` dataclass (lines 54–63): `number: int` (58), `description: str` (59), `files: list[str]` (60), `depends_on: list[int]` (61), `complexity` (62), `status` (63).
- Integer-only task-heading regex (314–316): `r"^###\s+Task\s+(\d+)\s*[:—–-]\s*(.+)$"`.
- `_normalize_task_separators` (284–296): rewrites em/en-dash/hyphen → colon, **but only for integer-only headings** (regex at 292), intentionally leaving a letter suffix intact so the guard fires.
- The 87239c4b fail-loud guard (319–336): detection regex `^###\s+Task\s+\d+[A-Za-z]` (328), raises `ValueError` (329–336). Inline comment states this is a placeholder pending the data-model change.
- `_parse_tasks` assigns `number=int(match.group(1))` (342, 370–377).
- `_parse_field_depends_on` (490–551): token grammar `_DEPENDS_ON_TASK_ID = r"\d+[a-z]?"` (473) *accepts* `3a` syntactically, then **collapses to integers** via `re.findall(r"\d+", stripped)` (545) → `[int(n) for n in numbers]` (551). `[1, 3a, 3b]` → `[1, 3, 3]` (note duplicate `3`, not deduped).

**`cortex_command/common.py`**
- `compute_dependency_batches` (672–708): `done_numbers: set[int]` (692), `assigned: set[int]` (694), batch = pending tasks whose `depends_on` ⊆ `assigned` (697), cycle → raise (698–702), `assigned.add(t.number)` (705), drop assigned from pending (706). **Pure set membership — no arithmetic on `.number`.** Within-batch order = input order (no sort).
- `mark_task_done_in_plan(plan_path, task_number: int)` (715–737): regex `rf"(### Task {task_number}:.*?-\s+\*\*Status\*\*:\s*)\[ \]"` with `re.DOTALL` (731–734). Call sites: `feature_executor.py:278, 780, 852`.

**`cortex_command/overnight/feature_executor.py` — every `task.number` consumer:**
- `247` `has_dependents = any(task.number in t.depends_on for t in all_tasks)` — membership test (feeds brain-triage SKIP/DEFER).
- `278, 780, 852` `mark_task_done_in_plan(..., task.number)`.
- `283, 288, 297, 776` deferral/error f-strings.
- `626` `"task_number": str(task.number)` (IMPLEMENT_TEMPLATE var).
- `637` `_make_idempotency_token(feature, task.number, plan_hash)` → key `f"{feature}:{task_number}:{plan_hash}"` (329).
- `643, 690, 721, 811, 836, 845` JSON event payloads `"task_number": task.number`.
- `685` `_write_completion_token(..., task.number, token)`.
- `785, 829` exit-report filename input → `f"{task_number}.json"` (194, 197).
- `596` `compute_dependency_batches(feature_plan.tasks)` call site.
- `611` renders `- **Depends on**: {task.depends_on}` into the worker prompt.

**Other consumers:** `cortex_command/dashboard/data.py:1349–1361` derives `_task_number` from exit-report `path.stem`, sorting `int(p.stem) if p.stem.isdigit() else 1<<30` — a hidden numeric-only consumer (string stems bucket to the sort floor). `skills/lifecycle/references/plan.md` (template `### Task N:`) and `implement.md` §2 (batch dispatch, `### Task N:`) are doc-authority surfaces.

**Existing tests:** `test_parser.py::TestSubTaskHeadingFailLoud` (885–927) asserts `### Task 2a:` and `### Task 2b —` *raise*; `test_subtask_letter_suffix_tolerated` (748–757) asserts `[1,3a,3b]`→`[1,3,3]`; `test_common.py::TestComputeDependencyBatches` (128–171) is entirely int-based.

**Lockstep invariant:** lifting the heading guard and stopping the `depends_on` collapse must move *together* — `compute_dependency_batches` keys `done_numbers`/`assigned` on the same identity that `depends_on` names. Diverge and batching references ids that don't exist.

---

## Web Research

The `3 < 3a < 3b < 4` problem is structurally "release vs release-with-suffix" — the closest authoritative prior art is **PEP 440 / `packaging.version`**, not generic natural-sort.

- **Composite-key idiom (recommended):** parse to a fixed-shape tuple and compare element-wise, keeping each slot type-homogeneous so int is never compared against str:
  ```python
  m = re.fullmatch(r'(\d+)([a-z]*)', token)
  key = (int(m.group(1)), m.group(2))   # (3,"") < (3,"a") < (3,"b") < (4,"")
  ```
  Empty suffix sorts first automatically (`"" < "a"`). This is exactly `packaging.version._cmpkey`'s trick. **Do NOT import `packaging`** — `parser.py` is documented stdlib-only; hand-roll the tuple.
- **Structured vs stringly-typed IDs:** prefer a parsed `(number, suffix)` structure for logic + one canonical `str` round-trip for I/O (filenames/tokens). Avoid "primitive obsession" (scattered re-parsing) but don't over-wrap.
- **Grouped topological sort:** Kahn level-by-level (emit indegree-0 as a batch) matches `compute_dependency_batches`. Build-system precedent (Bazel `depset`): a "group" is its own node — "depends on group 3" = edge to the group node; "depends on 3a" = edge to the member. Decide up front which a bare `[3]` means.
- **Migration hazards (the real risk, not the ordering math):** lexical-vs-numeric sort regressions (`"10" < "2"`) and regex prefix-collisions. Mitigation: anchor every id regex (`re.fullmatch`/explicit terminator); sort only via the parsed composite key, never raw string order.

---

## Requirements & Constraints

**`cortex/requirements/pipeline.md` line 42 (must-have, Feature Execution):**
> "Intra-feature task ordering is preserved: the runner derives batch ordering via `compute_dependency_batches` from per-task `Depends on` metadata, so a task never dispatches before its declared prerequisites. Unparseable ordering metadata fails the feature loudly (`parse_error`) rather than degrading silently — the fail-forward model governs whole-feature units, not silent mis-dispatch of tasks within a feature"

This criterion needs a **targeted amendment** (not a rewrite), and `pipeline.md` is **NOT in the ticket's named touch-points** — a scope gap:
1. The invariant survives — #297 *extends* "never dispatches before prerequisites" to sub-tasks.
2. The mechanism clause becomes inaccurate: ordering "derives via `compute_dependency_batches`... from `Depends on`" must reflect the richer identity type (and, per adversarial OQ-1, possibly an explicit intra-batch concurrency carve-out).
3. The "fails loudly (`parse_error`)" clause currently implies sub-task headings are unparseable; after #297 they parse, so the text must be narrowed so it doesn't read as forbidding the now-supported pattern (the fail-loud net still applies to *genuinely* unparseable metadata).

**Other constraints:**
- `project.md` Solution-horizon / "complexity must earn its place": don't over-engineer a general suffix grammar — the corpus uses only single lowercase `a..e`.
- No ADR governs the plan parser, task identity, or dependency batching (scanned 0001–0009). The data-model change is ADR-unencumbered; a new ADR is likely unwarranted unless the identity representation proves hard-to-reverse.
- No new event type is introduced (`parse_error` is a `FeatureResult` field, not a registered event), so `bin/.events-registry.md` needs no row. `tests/test_backlog_grep_targets_resolve.py` is not tripped (#297 body has no `grep -c` checks).
- Parent #293 established the fail-loud posture (87239c4b applied #293's "raise, don't silently drop" to suffixed headings). #297 must preserve the **no-silent-drop** invariant while replacing hard-fail with correct parsing.
- Editing `cortex_command/common.py` + `skills/` requires the lifecycle; per project memory use **sequential dispatch, not worktree** (just test runs the editable install).

---

## Tradeoffs & Alternatives

Four identity representations evaluated on complexity / maintainability / blast radius / backward-compat. (`compute_dependency_batches` uses **set membership, not `<`** — so dispatch correctness needs only *distinct keys*, ordering is secondary. That shrinks the load-bearing change to "distinct string identity.")

- **A — retype `FeatureTask.number` itself to a suffix type (`str` or custom comparable).** Largest blast radius; subtle bugs in implicit numeric consumers (dashboard `isdigit()` sort, JSON int-serialization, `set[int]` narrowing). A plain `str` breaks `test_idempotency.py` int-equality asserts and changes JSON `task_number` type. Backward-compat: moderate-to-high risk, hardest to hold "dispatch IDENTICALLY."
- **B — keep `number: int`, add `suffix: str=""` + derived `task_id`/`sort_key` (RECOMMENDED).** Integer-only plans byte-identical *by construction* — `.number` stays a real int, so JSON payloads/tokens/int-tests don't churn. Required changes ~6–8 sites; ~11 stay identical. One weakness: the **dual-key collision** (a stray consumer keying on `.number` merges `3a`/`3b`) — exactly the bug #297 exists to kill.
- **C — composite string `task_id` primary, derived `.number` for back-compat.** Single canonical key (avoids B's ambiguity) but `.number` as a *lossy derived* property re-introduces the same collision intrinsically; constructor-signature change churns all ~30 tests.
- **D — encode the suffix into integer space (`3→300, 3a→301`).** Zero change to int consumers, but a leaky encoding that hides identity behind a scaling trick and needs a `display_label` for `mark_task_done_in_plan`; fights the "first-class" intent.

**Recommendation: B, hardened with C's single-canonical-key discipline.** Make `task_id` (str, `f"{number}{suffix}"`, == `str(number)` when unsuffixed) the **sole** identity for `compute_dependency_batches`, `mark_task_done_in_plan`, exit-report filename, **and the idempotency token**; widen `depends_on` to `list[str]` of task_ids; expose `sort_key=(number, suffix)`; demote `.number` to a documented "group ordinal, not unique key" used only by telemetry JSON. Back the not-identity rule with a test asserting `3a`/`3b` produce distinct batches AND distinct filenames AND distinct idempotency tokens.

**Minimal blast radius (B + single-key):** parser (regex + `suffix` field + `task_id`/`sort_key` props + drop guard + stop collapse); `common.py` (`compute_dependency_batches` key→`task_id`, `mark_task_done_in_plan` full-id + anchoring); `feature_executor.py` (exit-report filename, idempotency token, `has_dependents` line 247 → `task_id`); `dashboard/data.py` stem sort → `(numeric-prefix, suffix)`; `implement.md` filename instruction; tests.

---

## Dependency & Ordering Semantics

Grounded in all 12 fixtures (the suffixed plans currently never reach the batcher — the heading guard raises first, so the `3a`→`3` collapse is effectively dead for them today).

**Empirical fixture behavior** (what `[...]` resolves to *today* post-collapse vs intent):
- `critical-review-sentinel.../plan.md`: `3a`(deps none), `3b`(deps `[3a]`), `4`(deps `[1,3a,3b]`); no bare `3`. Today → `4` deps `[1,3,3]` = phantom `3`, never satisfied.
- `harden-autonomous-dispatch.../plan.md`: `13a/13b/13c` all deps `[10]` (parallel siblings); `11` deps `[10,13a,13b,13c]`. Today → `[10,13,13,13]` phantom.
- `investigate-and-standardize.../plan.md`: `5a→5b→5c` serial + `5d`/`5e` parallel; `6b` deps `[1,2,3,4,5a,5b,5c,5d,5e,6a]`. Prose explicitly says `5a/5b/5c` serialize for a *mirror-regen race, not content dependency*.
- `requirements-skill-v2/plan.md`: has BOTH bare `### Task 8:` AND `### Task 8b:` (no `8a`) — `8`/`8b` are sequential peers (`8b` deps `[8]`, `9` deps `[8b]`). Today → `8b` collapses to `8` = self-loop + duplicate-id collision.

**Findings / recommendations:**
- **Fan-out semantics: literal — `[3]` means parent `3` only; do NOT auto-expand to {3,3a,3b}.** But this is *largely moot*: no author ever writes `[3]` meaning the group — they enumerate sub-tasks explicitly (`[3a,3b]`, `[13a,13b,13c]`). Option (b) auto-expand is wrong and dangerous (would break the `requirements-skill-v2` real-`8` case).
- **The real fix is to stop collapsing and resolve `depends_on` ids verbatim against real headings.** The genuine hazard is **dangling references** (a `[3]` left over after the heading became `3a/3b`). Recommend: unresolvable id → **hard parse error** (fail-loud, #293 posture), converting today's silent phantom-stall into a loud, fixable error. Add a self-dependency check.
- **Intra-parent ordering is NOT automatic `a<b<c`** — honor only declared edges. `13a/13b/13c` (all deps `[10]`) co-schedule in one batch; `5a→5b→5c` serialize via explicit edges. **[But see Adversarial OQ-1: "co-schedule in one batch" is unsafe under the shared overnight worktree.]**
- **`compute_dependency_batches` needs no algorithmic change** — only the identity-type update — because its topological pass is already identifier-agnostic and the corpus's ordering intent is fully carried by explicit `Depends on` edges.

---

## Backward-Compatibility & Migration Safety

The most dangerous item is a **pre-existing latent bug**, widened by sub-tasks.

1. **`mark_task_done_in_plan` cross-task `[ ]` bleed — REAL, pre-existing.** Heading-prefix collision is *not* the issue (trailing `:` anchors it; `### Task 3:` won't match `3a:` or `30:`). The real bug: with `re.DOTALL` + lazy `.*?`, when the target task's Status is already `[x]`, the scan runs *past* the next `### ` heading and flips the **next** task's `[ ]` (reproduced: marking already-done `3` flipped `3a`). Sub-tasks make it fire on the immediately-following sibling. **Fix (mandatory, needed regardless of #297):** tempered-dot stopping at next `^###\s` under `re.MULTILINE` + match the full `task_id` string. Current single-task R12 test (`test_common_utils.py:260–300`) misses it — add a multi-task already-done regression.
2. **Filename / token collisions — SAFE** if keyed on `task_id`: `3a.json` is fs-safe and distinct; `f"{feature}:3a:{hash}"` ≠ `f"{feature}:3b:{hash}"`. **But if `.number` (non-unique) is used instead, `3a`/`3b` both → `3.json` and identical idempotency token → silent overwrite + skip-dedup.** (See Adversarial — second landmine.)
3. **Sort/comparison — one display-only site** (`dashboard/data.py:1349`), already guards non-digit stems (cosmetic bunching of `3a` after `10`; no crash). No dispatch-path numeric sort exists.
4. **`_parse_field_depends_on` integer-only parse — byte-identical** (verified: `[1,2,3]`→`[1,2,3]`, `None`→`[]`, etc.). The `[a-z]?` token only *widens* acceptance. **Trap:** keep the collapse-removal and heading-recognition atomic, or `[1,3,3]` won't match `{"3a","3b"}` and ordering silently breaks.
5. **JSON / event round-trip — SAFE.** No non-test consumer does arithmetic on `task_number` (`metrics.py` doesn't read it; `report.py` filters by feature; dashboard uses string stem). `int 3` and `str "3a"` both serialize cleanly. Widen annotations `int`→`int|str` where the full id flows; update `test_idempotency.py:249,268–269` if values become strings.
6. **Idempotency / resume — SAFE for integers** (verified: `sha256("feat:3:hash")` == `sha256` of the same with `task_number=3` int vs `"3"` str — identical token). Integer-only resume re-skips correctly **provided the key shape `{feature}:{task_number}:{plan_hash}` and stringification are preserved exactly.** Do not reformat the key.

---

## Fixture Corpus & Parse-Shape Coverage

**Ticket says 6; real population is 12 files / 35 suffixed heading lines** (6 archive + 6 live). All are `###`-level, literal `Task` keyword, lowercase single-letter suffixes only — no uppercase (`3A`), no multi-letter (`3aa`), no spaced (`3 a`).

**Distinct shapes:**
- **Shape 1 — `### Task <N><letter>:` (32/35, dominant):** e.g. `### Task 4a: Write Architecture...`, `### Task 5e: Class-2 sweep...`. First colon after the identifier delimits the title; em-dash *inside* the title (e.g. `5a: Implement ... — skip/...`) is preserved as description.
- **Shape 2 — `### Task 0<letter> — Q<n>:` (3/35, all in `permissions-audit-round-2`):** `### Task 0a — Q1: Verify...`. Genuine U+2014 em-dash after `0a` (byte-confirmed); the title-delimiting colon sits after the `Q1` label — **two candidate delimiters; must split on the first identifier delimiter only** (greedy `.+` already does this).

**Structural edge cases the corpus mandates:**
- Integer part can be `0` (`0a/0b/0c`) — no `[1-9]` / "parent ≥ 1" assumption.
- **Orphan suffix:** `8b` with no `8a` (`requirements-skill-v2`) — suffix need not start at `a`.
- **Parent coexistence:** 11/12 files delete the bare integer when sub-tasks exist; `requirements-skill-v2` is the lone case with BOTH `### Task 8:` AND `### Task 8b:` — don't assume the parent is absent *or* present.
- Suffix depth reaches `e` (`5a–5e`, 5-deep); no gaps within contiguous groups (except the `8b` orphan).
- Multiple independent suffixed groups per file (`4a 4b … 6a 6b`); identity is `(integer, letter)`, not letter-globally-unique.
- Integer and suffixed tasks interleave in one ordered sequence (`1, 2a, 2b, 3, 4, …`).

**Recommended identity regex:** `^###\s+Task\s+(\d+)([A-Za-z]?)\s*[:—–-]\s*(.+)$` — g1 integer (accept `0`), g2 optional single letter (identity = `(int(g1), g2.lower())`), g3 title after the first delimiter. Extend `_normalize_task_separators` to also match the optional letter so Shape 2's `0a —` normalizes consistently. **Reject multi-letter / spaced suffixes with an explicit fail-loud, not a silent regex miss** (adversarial #4).

**Fixture caveat (adversarial):** `permissions-audit-round-2` uses *prose* `depends_on` ("Tasks 0a, 0b, 0c can run concurrently") that already fails `_DEPENDS_ON_LIST_CONFORMANT` — it can fixture heading-parse only, not end-to-end dependency resolution, without a rewrite.

---

## Adversarial Review

Verified against live source + the 12-file corpus. Several summary claims held; three were overturned or sharpened.

1. **[HIGH] "Ordering is irrelevant / batching is type-agnostic" is FALSE in the overnight path.** `execute_feature` dispatches each batch via `asyncio.gather(*[_run_task(t) for t in batch])` (feature_executor.py:728) into a **single shared per-feature worktree** (390, 672). So `13a/13b/13c` (one batch, all deps `[10]`) run **concurrently in one checkout** — if same-parent sub-tasks touch overlapping files (exactly what decomposing one task invites), they race on the working tree and git index. Making sub-tasks "first-class independently-dispatchable" *increases batch width*, increasing concurrent-write collisions. **Asymmetry the core wave missed:** the **interactive** path (`implement.md` §2) gives each task its OWN `Agent(isolation:"worktree")` merged sequentially — isolated — so the same plan behaves differently across execution surfaces.
2. **[HIGH] The `mark_task_done_in_plan` "the `:` anchors it" dismissal is a category error.** The `:` prevents *heading-match* collision but not the *DOTALL body-scan bleed* into a later task's `[ ]` (reproduced). Fix as in Backward-Compat #1; don't let the summary's reasoning under-scope it.
3. **[HIGH] `(number:int) + depends_on:list[str]` has confirmed silent type-mismatches.** `feature_executor.py:247` `task.number in t.depends_on` becomes `int in list[str]` → **always False** → `has_dependents` signal silently vanishes (feeds brain-triage). And `compute_dependency_batches`' `assigned.add(t.number)` (int) vs a str `depends_on` → dependent batches never form → `ValueError("cycle or unresolvable")` on the first dependent task. **No half-migration works:** every identity-bearing `.number` (247, common.py 692/705/706, idempotency token 329/637, exit-report filename 194/829) must switch to `task_id` atomically.
4. **[MEDIUM] Regex / case hazards.** `(\d+)([A-Za-z]?)` silently drops `3ab` / `3 a` (none in corpus — future-proof with explicit fail-loud). Case asymmetry: heading `[A-Za-z]` vs `depends_on` `re.IGNORECASE` → heading `"3A"` but dep `"3a"` → `"3a" in {"3A"}` False → silent dangling. Mitigation: case-fold `task_id` both sides, or restrict headings to `[a-z]`.
5. **[MEDIUM] Fail-loud on dangling refs is empirically SAFE for the corpus** — **zero** dangling list-conformant `[Na]` refs across all 12 plans; all 6 non-archive suffixed plans are fully complete (0 pending tasks) with no in-flight sessions. So "real plan in flight" risk is nil today. The future `[3]`-when-only-`3a/3b`-exist case must still be specced explicitly (hard error, no auto-expand).
6. **Structurally missed:** the dual execution-surface divergence (#1); the idempotency-token/exit-report silent-merge under non-unique `.number` (#3); the pipeline.md amendment must also carve out the intra-batch concurrency contract; test churn is ~15+ edits (every int-based `compute_dependency_batches`/`depends_on` assertion + invert `test_subtask_letter_suffix_tolerated` + flip `TestSubTaskHeadingFailLoud`), larger than the ticket's "replace TestSubTaskHeadingFailLoud" implies.

---

## Open Questions

The fan-out / collapse / parse-shape questions are **resolved by evidence** (inline below). The remaining design decisions are **deferred to Spec** for the user's call, with rationale — they are genuine scope/preference choices the orchestrator should not make unilaterally.

- **OQ-1 — Same-batch sub-task concurrency contract (the load-bearing decision). DEFERRED to Spec.** Under the overnight shared-worktree model, co-scheduling `13a/13b/13c` (or any same-parent siblings) in one batch races on the working tree. Options for the user: (a) add an implicit serialization edge between same-parent sub-tasks so a decomposition runs sequentially; (b) document that sub-tasks must declare disjoint `Files` and same-batch parallelism is intentional; (c) serialize the overnight shared-worktree to one task at a time when sub-tasks are present. *Rationale for deferral: changes the dispatch contract and the pipeline.md amendment; a correctness/throughput tradeoff the user must choose.*
- **OQ-2 — `depends_on` representation: `list[str]` task_ids vs. a back-compat-preserving alternative. DEFERRED to Spec.** Recommendation is `list[str]`, but it forces the atomic `task_id` migration of all identity-bearing `.number` sites (adversarial #3). *Rationale: determines blast radius; pairs with OQ-1.*
- **OQ-3 — How far to harden the parser beyond the corpus. DEFERRED to Spec.** Reject multi-letter (`3ab`), spaced (`3 a`), uppercase (`3A`) suffixes with explicit fail-loud vs. silently accept? Case-fold `task_id` vs. restrict to `[a-z]`? *Rationale: "complexity must earn its place" — the corpus is single lowercase `a..e`; the user decides how much future-proofing earns its keep.*
- **OQ-4 — pipeline.md amendment scope. DEFERRED to Spec.** The must-have line 42 needs editing (mechanism clause + the now-supported-pattern carve-out + possibly the intra-batch concurrency contract from OQ-1). pipeline.md is an out-of-ticket touch-point. *Rationale: requirements text is a deliberate edit, not an implementation detail.*
- **OQ-5 — Pre-existing `mark_task_done_in_plan` bug: fix in this lifecycle or split out? DEFERRED to Spec.** The DOTALL cross-task bleed is independent of #297 but is widened by it and sits squarely in a touched function. *Rationale: scope decision — bundle the latent-bug fix or file a sibling ticket.*
- **OQ-6 (RESOLVED — fan-out):** `[3]` means the literal parent only; do not auto-expand. Evidence: no author in 12 fixtures uses a bare integer to mean the group; they enumerate sub-tasks explicitly. Stop collapsing, resolve verbatim, hard-error on dangling refs.
- **OQ-7 (RESOLVED — intra-parent ordering):** not automatic `a<b<c`; honor only declared `Depends on` edges (parallel siblings exist: `13a/13b/13c`). The `(number, suffix)` `sort_key` is for *display* ordering only — subject to OQ-1's concurrency contract for actual dispatch.
- **OQ-8 (RESOLVED — identity representation):** `(number:int, suffix:str)` + canonical `task_id` str, `task_id` as sole identity key, `.number` demoted to telemetry-only group ordinal. Evidence: only design that keeps integer-only plans byte-identical by construction while giving `3a`/`3b` distinct keys.
