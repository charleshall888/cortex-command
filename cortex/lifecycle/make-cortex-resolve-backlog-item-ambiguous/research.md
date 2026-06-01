# Research: Make cortex-resolve-backlog-item ambiguous parity fixture robust to backlog drift

> Goal: stop `tests/test_cortex_resolve_backlog_item_parity.py::test_stderr_parity[title_phrase_ambiguous]` from breaking `just test` whenever a "lifecycle"-titled backlog item is added or removed, while keeping the resolver's ambiguous-match behavior (exit 2 + the `ambiguous: N matches` formatter) genuinely under test — not weakened to a no-op.

## Codebase Analysis

### The drift is live and imminent — not hypothetical
The `title_phrase_ambiguous.stderr` fixture pins `ambiguous: 33 matches` / `... (28 more)`, but a live `resolve("lifecycle", cortex/backlog)` on this working tree now returns **34 candidates** — three new "lifecycle"-titled items landed (#276 committed, #277/#278 untracked). `test_stderr_parity` byte-compares against whatever `cortex/backlog/` currently holds; the test passes *today* only because #277/#278 are untracked. The moment they are committed, `test_stderr_parity[title_phrase_ambiguous]` fails. This is the recurring tax the ticket names (re-captured at `c582a84e`, then `904bb80f` during #274 — this would be the **third** drift). The README is even further behind: case table says `(32 matches)`, snapshot note says `256 items / 001-259`.

### Files that will change
1. **`tests/test_cortex_resolve_backlog_item_parity.py`** (primary). Key mechanics:
   - `_discover_cases()` (L64–69) globs `FIXTURE_DIR.glob("*.argv")` and returns `path.stem` — **parametrization keys off `*.argv` only**. Deleting `title_phrase_ambiguous.stderr`/`.exitcode`/`.stdout` does NOT drop the case, but the byte-readers (`_read_expected_stderr` L87–88, `_read_expected_exitcode` L91–93) would then `FileNotFoundError`. To drop a case entirely you must remove its `.argv`.
   - `test_stderr_parity` (L161–171) is the failing assertion: `assert_byte_identical(actual_stderr, expected_stderr)` for every discovered case. This line pins the count.
   - `test_exitcode_parity` (L150–158) and `test_stdout_parity` (L174–196) iterate the same cases; the ambiguous case's exit (2) and empty stdout are stable — only stderr drifts.
   - `test_stdout_parity` already uses an in-test `if case == "numeric_unambiguous": ... else: ...` branch (L186–196) — the established idiom for handling one case differently.
   - `_DETERMINISM_ENV_OVERRIDES` (L52–56) sets `CORTEX_BACKLOG_DIR` to **`REPO_ROOT/cortex/backlog`** (the live, growing backlog) — this is the drift source. Pointing it at a `tmp_path`/committed fixture corpus is the determinism lever.
   - Module docstring L19–25 ("error-formatter-shape is NOT opted in") must be updated to match the chosen assertion.
2. **`tests/fixtures/cortex-resolve-backlog-item/README.md`** — drifted regardless of approach. Fix L22 (`yes (32 matches)`), L41 (`256 items / 001-259`), L95–98 (the byte-for-byte claim), and the "How to recapture" block (L100–123).
3. **`tests/fixtures/cortex-resolve-backlog-item/title_phrase_ambiguous.{stderr,exitcode,stdout}`** — under a structural assertion the `.stderr` byte-fixture is no longer source of truth (delete or keep as illustrative, keep `.argv` so the case stays discovered); under a frozen-corpus approach, re-capture once against the controlled corpus.
4. **`tests/test_parity_contract.py`** — touched ONLY if the durable-tolerance-category route (a2) is chosen.

### Exact resolver format strings (for a precise structural assertion)
`_format_candidates` in `cortex_command/backlog/resolve_item.py` (≈L282–296):
```
lines = [f"ambiguous: {count} matches"]
for path in matches[:5]:
    lines.append(f"{path.name}\t{title}")     # filename<TAB>title
if count > 5:
    lines.append(f"... ({count - 5} more)")
return "\n".join(lines)
```
- First line is exactly `ambiguous: {N} matches` (no trailing punctuation).
- Candidate lines: `{filename}\t{title}` (literal TAB), at most 5.
- The `... ({N-5} more)` line appears **only when `count > 5`**.
- `main()` prints to stderr (trailing `\n` appended); exit is `2`.
- A robust structural check: assert exit 2; first stderr line matches `^ambiguous: (\d+) matches$`; captured N > 1; ≤5 candidate lines each containing a TAB; the `... (N more)` line present iff N > 5 with `N-5` arithmetic.

### Tolerance contract (durable route, if chosen)
`TOLERANCE_CATEGORIES` (L53–59) is a frozenset of exactly five: `key-reorder`, `unicode-escape`, `number-format`, `trailing-newline`, `error-formatter-shape`. Adding a sixth needs three coordinated edits: (1) frozenset entry; (2) the guard test `test_tolerance_categories_is_closed_set_of_five` (L563–573) — including its `_of_five` name; (3) a handling branch + stream guard in `assert_structurally_equivalent`, plus the both-directions contract tests every category has. **`error-formatter-shape` is NOT reusable** for this case: opted in (L154–179) it compares only `{empty/non-empty} × {zero/non-zero exit}` and never inspects bytes — it would pass for `ambiguous: 0 matches` or a single garbage byte, leaving `_format_candidates` entirely unguarded (the "weaken to a no-op" the ticket forbids).

### Blast radius
**~21 sibling test modules** import from `tests/test_parity_contract.py`. A **local** assertion confined to `test_cortex_resolve_backlog_item_parity.py` touches one file and leaves all siblings untouched. A **new tolerance category** widens the shared closed set every sibling validates against — a contract-level amendment for a single call site.

### Decisive precedent: synthetic-corpus parity tests already exist
- `tests/test_cortex_backlog_ready_parity.py` (≈L53–169) builds a synthetic `tmp_path/cortex/backlog/` from records via `_write_md` and runs byte-exact parity against it.
- `tests/test_cortex_load_parent_epic_parity.py` (≈L121–143) builds a synthetic backlog in `tmp_path` and sets `CORTEX_BACKLOG_DIR` to it for its `broken_parent` case.
- `tests/test_resolve_backlog_item.py` (the unit test for this same module) builds isolated corpora via `make_item(...)` (promoted to `tests/conftest.py`) and asserts `len(matches) == 2` against a hand-built 2-item set.
Both parity siblings retain **full byte-exact comparison against deterministic data**. The resolver parity test's use of the *live* backlog is the outlier that produced the drift.

### Conventions to follow
- In-test branching by case name and per-case tolerance dicts (`test_cortex_lifecycle_state_parity.py` `_CASE_TOLERANCES`) are both established idioms.
- The broader `tests/` suite freely uses `re.search`/`re.match`/`.splitlines()` against captured output (~20 files), so a hand-written structural stderr assertion is consistent with repo conventions — even though the parity tests themselves route through the contract helpers.

## Web Research

Industry guidance treats the three options as a **layered hierarchy**, not equals. For output embedding volatile data (a count + a directory listing), the strongest-supported fixes are **deterministic input control** (when you own the input — "sacrifices nothing") and **normalize/scrub-then-compare or structural assertion** (when you don't). A documented re-capture cadence is the universally-acknowledged *weakest* fallback because it relies on human discipline that erodes.

Authoritative sources (this is **industry-validated practice, not folk practice**):
- **Abseil Tip of the Week #135, "Test the Contract, not the Implementation"** (Google) — *"Tests that depend on unspecified aspects of a component are brittle… should not make assumptions beyond what's guaranteed."* The live count `N` and the specific listing are *incidental*; the contract is "emit `ambiguous: N matches` + a listing in this format." Pinning the literal N is overspecification.
- **Jason Rudolph, "Testing Anti-Patterns: Overspecification"** — names "incidental data" as an overspecification smell.
- **Kent C. Dodds, "Effective Snapshot Testing"** — primary remedy is *shrink the snapshot / convert to an explicit assertion*.
- **Artem Sapegin, "What's wrong with snapshot tests"** — names exactly this symptom: unrelated changes cascade snapshot failures; concedes snapshots are fine for *"very short output… like error messages."*
- **testthat `transform=`** (R), **syrupy `path_type`/`path_value`** (pytest), **Jest property matchers** (`expect.any`), **Verify/ApprovalTests scrubbers**, **Go `testscript` `cmpenv` + regex** — all ship first-class "normalize/match-shape, not literal" mechanisms; testthat explicitly ranks: mock for determinism → `transform` regex-scrub → deterministic inputs.

Anti-patterns named: byte-pinning incidental/volatile data (root cause here); whole-blob snapshots; and **scheduled blind re-capture as the primary strategy** (degrades into "regenerate without reading," eroding trust) — i.e. option (c).

## Requirements & Constraints

- **Quality bar** (`project.md` L23): *"Tests pass; the feature works as specced."* The drift makes `just test` fail on unrelated changes — the direct driver.
- **Complexity / "simpler wins"** (L19): *"Must earn its place… When in doubt, simpler wins."*
- **Solution horizon** (L21, and CLAUDE.md): *"Before suggesting a fix, ask… do I already know this needs redoing… the same patch would apply in multiple known places you can name… If yes, propose the durable version."* **Directly decisive**: the re-capture has already recurred (two known commits, a third imminent) — satisfied by *current knowledge*, not prediction. Option (c) "document the cadence" IS the recurring patch; the durable version is favored.
- **Maintainability through simplicity** (L50).
- **The closed five-category tolerance contract** is governed by `test_parity_contract.py`'s docstring + the `test_tolerance_categories_is_closed_set_of_five` guard (carrying the in-code rule *"a future amendment expanding the set MUST update this test alongside the helper"*) + the call-time `ValueError` on unknown names. **No ADR governs it** (checked `cortex/adr/`, only 0001–0007 exist); it originated as Phase 1 of feature `installation-integrity-layer-bash-to-entry` (#252).
- **Stated constraint the fix must consciously revise**: the fixture README (L95–98) and the parity-test docstring (L23–25) explicitly say `error-formatter-shape` is NOT opted in and the stderr cases "must reproduce byte-for-byte." The chosen fix overrides this for the ambiguous case (the byte it pins is precisely the volatile thing).
- **No `tests/`-subsystem requirements doc exists** — `cortex/requirements/` holds only project.md + four area docs (multi-agent, observability, pipeline, remote-access). Governing artifacts for this change are the two test docstrings, the fixture README, and CLAUDE.md design principles.
- **Design-principle applicability**: "prescribe What not How" and "prefer structural separation over prose-only enforcement for sequential gates" are scoped to *harness authoring / control-flow gates*, not test-assertion granularity — so neither directly governs byte-exact-vs-structural. But both are *consonant* with the durable fix and argue **against** (c): a README cadence note is prose-only enforcement whose cost of deviation is demonstrably not low.
- **Naming collision caution**: the SKILL.md↔bin "parity enforcement" (`bin/cortex-check-parity`) is a *different* subsystem from the test-tier "parity contract" (`tests/test_parity_contract.py`); only the latter is in scope.

## Tradeoffs & Alternatives

- **(a1) LOCAL structural assertion** — special-case the ambiguous stderr (regex: exit 2, `^ambiguous: \d+ matches$`, ≥1 `filename<TAB>title` line, `... (N more)` iff count>5), bypassing the shared helper for that one case against the **live** backlog. *Complexity: low (~15 lines, one file). Maintainability: drift-immune, but forks the resolver test off the shared helper — an unnamed, undeclared tolerance, the exact thing the contract forbids. Alignment: medium-low.* This is the ticket's recommended option.
- **(a2) DURABLE contract extension** — add a sixth named tolerance category, update the guard test (and its `_of_five` name), add a helper branch. *Complexity: medium-high. Maintainability: poor relative to payoff — modifies a contract imported by ~21 siblings to launder one fixture's instability; single-use additions to a closed contract are a smell. Reject* unless a second drift-prone-stderr consumer is named.
- **(a3) Reuse `error-formatter-shape`** — *this is precisely the "weaken to a no-op" the ticket forbids.* It verifies only non-empty + non-zero-exit; the `ambiguous: N matches` formatter would be entirely unguarded. **Reject.**
- **(b) Stable organic query term** — *fundamentally non-viable.* Backlog titles are arbitrary free text and the corpus only grows; any English word that matches >1 today is *popular* and therefore the *most* likely to keep accreting matches. There is no organic substring that stays at a fixed count. **Reject** standalone.
- **(b′) Frozen mini-backlog fixture** — point `CORTEX_BACKLOG_DIR` at a small synthetic backlog (built in `tmp_path` or committed) with a fixed item set, then keep `assert_byte_identical`. *Complexity: low-medium (copy-paste-ready precedent in two siblings). Maintainability: excellent — drift-immune by construction; the count changes only when someone deliberately edits the fixture corpus. Alignment: highest — it CONFORMS to the existing synthetic-corpus parity pattern; the live-backlog resolver test is the outlier.* Keeps byte-exactness (strongest verification — `_format_candidates`' header, the 5 `filename<TAB>title` lines, and the `... (N more)` branch all fully exercised when the corpus is seeded with >5 matches), no contract surgery, no snowflake helper.

### Recommended approach
**(b′) frozen mini-backlog fixture, assertion kept byte-exact** — with **(a1) local structural assertion** as the viable fallback if minimizing churn is preferred over byte-exactness. Rationale: (b′) is the only option that keeps the assertion *byte-exact* (nothing weakened — stronger than today, since the count becomes an asserted invariant rather than an accident of the live corpus), is drift-immune by construction, reuses a proven in-repo pattern, touches no shared contract, and is the durable fix the Solution-horizon principle prescribes for an *observed, recurring* failure. (a1) also keeps behavior under test and is the smaller diff, but leaves the contract-vs-snowflake tension unresolved and continues to read live data. The decision between (b′) and (a1) is the one open design choice for Spec.

Suggested handling of fixture files + README under (b′): seed the synthetic corpus with a fixed set whose titles yield a deliberate >5 match count (so the truncation branch stays covered); re-capture `.stderr`/`.stdout`/`.exitcode` once against it; consider migrating `numeric_unambiguous`/`no_match` onto the same corpus for consistency (replicate #252's `lifecycle_slug` frontmatter in one synthetic item to keep the slug-priority path covered); rewrite the README's "Cases captured" table, "Backlog snapshot," and "How to recapture" sections to describe the committed/synthetic corpus and document *why* the count is pinned (so a future maintainer doesn't re-point it at the live backlog).

## Open Questions

- **Primary design choice — (b′) frozen mini-backlog fixture vs. (a1) local structural assertion.** Deferred: resolved in Spec by asking the user. Research recommends (b′) (keeps byte-exactness + matches sibling precedent + durable); (a1) is the smaller-diff fallback the ticket recommends. Both keep resolver behavior genuinely under test; (a2)/(a3)/(b)/(c) are rejected with rationale above.
- **Scope of corpus migration if (b′) is chosen** — migrate all three cases (`numeric_unambiguous`, `no_match`, `title_phrase_ambiguous`) onto the frozen corpus, or only the ambiguous one? Deferred: resolved in Spec. Research leans toward migrating all three for consistency and to kill any future numeric/no-match drift, but the ticket's Edges note that the siblings are currently stable makes ambiguous-only a defensible minimal scope.
- **README de-volatilization** — Resolved: the README is already drifted (L22 "32 matches", L41 "256 items / 001-259") and must be corrected/de-pinned as part of this work regardless of which option is chosen; under (b′) it is rewritten to describe the frozen corpus, under (a1) the volatile count is removed from the case table.
