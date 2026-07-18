# Review: cortex-lifecycle-enter-state-accept-a (#379) — Cycle 1

**Scope reviewed**: `09a11815..HEAD`, four files, all under `cortex_command/lifecycle/` (`enter.py`, `resolve.py`, `tests/test_enter.py`, `tests/test_resolve.py`).
**Method**: read the three implementation diffs (`d2d1bac1`, `f7291f98`, `2195762b`) and the resulting sources; re-ran every literal acceptance criterion that is non-destructive; independently re-ran the two claimed-substituted acceptances (R4, R12) and the R11 corpus check rather than taking the plan's recorded outcomes on trust. No source file was modified.

---

## Stage 1 — Spec Compliance

| Req | Rating | Evidence |
|---|---|---|
| R1 — fail loud on resume of non-existent lifecycle | **PASS** | Literal acceptance run: `CORTEX_REPO_ROOT=$SCRATCH python -m cortex_command.lifecycle.enter --feature no-such-thing --phase research …` → own exit code `3`; stderr `cortex-lifecycle-enter: no such lifecycle 'no-such-thing': …`; `test -d $SCRATCH/cortex/lifecycle/no-such-thing` → exit 1. All three clauses met. |
| R2 — legitimately-new lifecycle still created | **PASS** | Both halves verified. `test_brand_new_lifecycle_with_phase_none_still_creates` pins `state == "ready"`. The acceptance's second half (`index.md` exists) is **not** pinned by that test (it patches `create_index`), so I ran it unpatched against a scratch root: `--feature brand-new-slug --phase none --backlog-file ""` → exit 0 and `cortex/lifecycle/brand-new-slug/index.md` materialized with correct frontmatter. See issue 4. |
| R3 — reject unsafe feature token | **PASS** | Literal acceptance run: `--feature '../../../tmp/evil' --phase none` → exit `3`, stderr `unsafe feature slug`, `test -e /tmp/evil` → exit 1. `_reject_unsafe_slug` adopts the `describe.py` blacklist verbatim (empty, `/`, `\`, `..`) — one existing idiom, not a third. Parametrized over 5 hostile tokens; a separate test asserts nothing is written outside the lifecycle root. |
| R4 — grandfathered numeric lifecycles keep working | **PASS** (deviation accepted — see below) | |
| R5 — refuse a dir belonging to a different item | **PASS** | Verified against the **live** tree read-only: `_parent_uuid(cortex/lifecycle/374/index.md)` == `_parent_uuid(cortex/backlog/374-*.md)` == `84506324-…` → guard does not fire on the same item; `_reject_cross_item_merge('374', '379-*.md', root)` → fires. Comparison is on the uuid, not the filename. `test_entering_a_dir_owned_by_a_different_item_exits_3_and_changes_nothing` asserts rc 3 **and** sha256 of A's `index.md` unchanged, with all three primitives monkeypatched to `AssertionError` — so the test proves no side effect ran, not merely that the return code was 3. The fixture index is written by the **real** `create_index`, so it cannot drift from the producer whose frontmatter the guard reads. Inert-by-design arm pinned by `test_null_parent_uuid_with_empty_backlog_file_passes_the_guard`. |
| R6 — fail loud without touching skill prose | **PASS** | (a) `git diff --stat 09a11815..HEAD` → zero files under `skills/` or `plugins/*/skills/`; the whole change is 4 files under `cortex_command/lifecycle/`. (b) `test_cli_exits_0_with_error_state_on_unexpected_exception` has **zero** hits in the test diff (unmodified) and passes. Guards route through `_GuardRejected` → stderr + exit 3, never through `state: "error"`. See issue 3 for a prose-vocabulary hazard the spec's R6 rationale overlooked. |
| R7 — message distinguishes its two causes | **PASS** | Live stderr names the feature (`'no-such-thing'`), the phase, **both** causes verbatim ("the dir vanished mid-flight (deleted between the resolver and this call — recover the dir, then re-run)" vs "the caller mis-threaded the identity"), the served-slug remedy ("re-run cortex-lifecycle-next and thread its resolved --feature verbatim"), and the no-op guarantee ("Creating nothing."). Pinned by `test_guard_message_names_feature_and_both_causes`, which asserts each of the four elements separately — not a substring smoke test. |
| R8 — `new` branch emits the canonical slug | **PASS** | Literal acceptance run live: `resolve_invocation("340")` → `feature == "core-skill-efficiency-survivors-of-the"`, `resolved_from == "340"`. Confirmed end-to-end through `next` (`python -m cortex_command.lifecycle.next_verb 340` returns the same, since `new` is in `_ROUTING_PASSTHROUGH` and `next` returns `dict(resolved)` verbatim — `resolved_from` is not dropped by a key whitelist). Also confirmed on three fresh unpinned tickets (381/382/383). |
| R9 — `state: new` preserved | **PASS** | `resolve_invocation("340")` → `state == "new"` (not `resume`). The implementation split the `:188` predicate into a `canonical_slug` local rather than deleting the `is_dir()` conjunct, so #370's resume bound is structurally intact — the conjunct still gates `dir_exists = True`, and only `feature`/`resolved_from` change on the `new` arm. |
| R10 — Context B untouched | **PASS** | Literal acceptance run live: `resolve_invocation("some-adhoc-slug-with-no-item")` → `feature` == the caller token, `backlog is None`, `"resolved_from" not in r`. Pinned by `test_new_branch_without_backlog_match_keeps_caller_token`. |
| R11 — pinned-slug corpus unaffected | **PASS** | Both halves re-run independently, not taken on trust. (a) `resolve_invocation("374")` → `feature == "374"`, `state == "resume"`, `resolved_from` absent. (b) Corpus loop over the live tree against the **working-tree module** (avoiding the plan's console-script trap): **177 dirs checked, 0 drift rows**. Matches the plan's recorded outcome exactly. |
| R12 — pinned test updated deliberately | **PASS** (deviation accepted — see below) | `assert r["state"] == "new"` appears as unchanged **context** in the diff (space-prefixed, no `+`/`-`); `assert "resolved_from" not in r` correctly inverted to assert presence and the normalized `feature`. |

**No FAIL. Stage 2 proceeds.**

### R4 — deviation assessed, PASS

The literal acceptance (`cortex-lifecycle-enter --feature 374 --phase specify` against the live repo) was **not** run, and the orchestrator's reasoning is sound: that command would drive `create_index`/`sync`/`init-ensure` and mutate the real `374` lifecycle — `sync` writes `in_progress` back to the backlog item and `.session` would be overwritten — in order to test a **read-only guard**. The literal acceptance exercises three composed primitives that R4 makes no claim about.

I verified R4's actual claim ("a feature whose dir exists passes every guard regardless of token shape") directly and read-only, running all three guard predicates against the live tree:

- `374` + `--phase specify` → all three guards pass
- `378` + `--phase plan` → all three guards pass
- `cortex-lifecycle-enter-state-accept-a` + `--phase implement` → all three guards pass

Combined with `test_grandfathered_numeric_lifecycle_passes_guards` (full `enter()` against a real dir named `374`, `--phase specify` → `state == "ready"`), R4 is genuinely satisfied. The substitute evidence covers R4's claim **more** precisely than the literal command would, and the blacklist-over-whitelist choice — the specific decision R4 exists to protect — is pinned by the numeric-token test. **Not PARTIAL.**

### R12 — deviation assessed, PASS (and the plan's recorded number is wrong)

R12's acceptance names `just test` green. It is not green — but the shortfall is in the **acceptance criterion**, not the implementation: the plan itself records the suite as known-red before the change, so the criterion was unmeetable at the baseline too and no change to `resolve.py` could have made it green.

I re-ran `just test` on the working tree rather than trusting the recorded outcome, and it materially corrects the plan:

```
2 failed, 2504 passed, 23 skipped, 1 xfailed in 122.92s
FAILED tests/test_model_resolution_wiring.py::test_writeback_routing_defined_once_and_referenced
FAILED tests/test_model_resolution_wiring.py::test_writeback_preserves_empty_areas_clearing_quirk
```

**Two** failures, not 42. Both are the known-red "refine writeback" pair, both assert on `skills/refine/SKILL.md` prose, and this change touches **zero** skill files — so they are pre-existing by construction, not merely by comparison. The plan's Task-4 note ("42 failures before, the same 42 after… the pre-existing set is far larger than the 'refine writeback + mcp DNS' pair on record") measured detached worktrees, where environment-dependent tests (seatbelt, init-ensure, PR-gating) fail for reasons unrelated to the code. The orchestrator's **conclusion** (zero new failures) holds and is confirmed; its **number** is worktree noise and the original record of two known-red failures was right. See issue 5 — this matters only so a future reader does not inherit a false picture of suite health.

R12's intent — the change breaks nothing, the `state` assertion survives — is satisfied on stronger evidence than the plan claimed. Additionally, `uv run pytest cortex_command/lifecycle/tests/test_enter.py cortex_command/lifecycle/tests/test_resolve.py -q` → **54 passed**.

### Non-Requirements — verified, all respected

- **Zero `skills/` or `plugins/*/skills/` files touched** (R6a) — confirmed via `git diff --stat`.
- **`PROTOCOL_VERSION` not bumped** — `git diff --stat -- cortex_command/lifecycle/protocol.py` returns zero lines. Correct per `protocol.py:24-27`: value semantics changed, envelope shape did not.
- **#378 defensive coercions retained** (Proposed ADR-0029 "Consequence" clause) — **both** sites confirmed present and unmodified: `resolve.py` (`if slug is not None: slug = str(slug)`, with its `#378 req-3` comment intact) and `resolve_item.py:135-141` (`return str(slug)`, untouched — not in the diff). The implementation went further than retention: `test_new_branch_normalizes_numeric_lifecycle_slug` newly pins that an unquoted numeric `lifecycle_slug` read as `int` is str-coerced **before it reaches `feature` on the new branch** — a regression pin the coercion previously lacked on this path. This is exactly the right response to the ADR's "not dead code" clause.
- Numeric-keyed dirs remain producible by hand-typed `enter` (ADR-0029 §Scope) — confirmed: `--phase none` bypasses the existence guard and the blacklist accepts `374`.
- `_lifecycle_dir_exists` location: the spec/plan cite `critical_review/__init__.py:484-494`; it is at `cortex_command/critical_review/__init__.py:484`. A path-prefix typo in the artifacts, already corrected in the Task-1 Status note. No code impact.

---

## Stage 2 — Code Quality

**Guard ordering — correct.** `enter()` runs `_reject_unsafe_slug` → `_reject_missing_lifecycle` → `_reject_cross_item_merge`, all three before `_backlog_status`, before the `needs-decision` short-circuit, and before `create_index`. `_reject_unsafe_slug` is strictly first, which is load-bearing: the two guards behind it build paths from `feature`, so the token must be proven safe before either touches the filesystem — R3's "before any filesystem op" is met literally, including before the `--backlog-file` read. `test_guards_raise_before_any_composed_primitive` pins this structurally by monkeypatching `create_index`/`sync`/`init_ensure.main` to raise `AssertionError` and seeding an `already_complete` item that would otherwise short-circuit to `needs-decision` — so it proves both the primitive ordering **and** the precedence over the short-circuit. That precedence is the one behavior the plan's Risks section flagged as unnamed by the spec; it is now the tested behavior, and it is the right call (a token that must never touch the filesystem should not produce a routine Close/Continue prompt).

**`_GuardRejected` cannot be swallowed — verified, not assumed.** MRO is `['_GuardRejected', 'Exception', 'BaseException', 'object']`; `issubclass(_GuardRejected, OSError)` is `False` and `issubclass(_GuardRejected, _Exit2)` is `False`. `main()`'s arms are ordered `OSError` (exit 1) → `_Exit2` (exit 2) → `_GuardRejected` (exit 3) → broad `Exception` (exit 0 + `state: "error"`). Since `_GuardRejected` matches neither earlier arm, its own arm catches it before the broad one. Both swallow paths named in the review brief are closed. `test_guard_exception_is_not_an_oserror` pins the OSError half as an explicit regression assertion — the correct place for it, since the hazard is invisible at the call site.

**Tests are load-bearing, not vacuous.** The plan's verification steps were executed and I reproduced them independently. The guard tests need no `_patch_primitives` seam (reaching a primitive at all would be the bug) and several actively **forbid** primitives from running. The R5 test pins a sha256, not just a return code. The Task-1 test-repair was done correctly — `test_sync_receives_caller_passed_discriminants` creates the dir the R1 guard now requires rather than weakening the guard, exactly as the plan directed; `test_all_known_states_reachable` was correctly left alone.

**Pattern consistency — good.** Stderr uses the file's own `cortex-lifecycle-enter: …` idiom; the module docstring, argparse description, and `enter()` docstring were all updated to enumerate exit 3 and its rationale; the `# gate-class: hygiene` markers match the house convention. `_reject_unsafe_slug` shares a name with `describe.py`/`next_verb.py` while raising instead of returning an envelope — a divergence the plan explicitly directed ("the same predicate must instead raise"), documented in the docstring. Correct, not a finding.

### Issues (minor — noted per the project's compounding constraint; none blocking)

1. **`_parent_uuid` is one helper serving two different frontmatter schemas via a key-preference heuristic.** `fm.get("uuid", fm.get("parent_backlog_uuid"))` reads a backlog item's own `uuid` **and** an index's `parent_backlog_uuid`. It is correct today — `create_index._render` emits no `uuid` key into `index.md` — but the correctness rests on an absence, not an invariant. If `index.md` ever gains its own `uuid` field, the guard would compare a lifecycle uuid against a backlog uuid and reject **every** legitimate entry. An explicit key argument (or two thin named wrappers) would make the two call sites self-describing. The name is also a slight misnomer at the backlog-item call site, where the uuid read is the item's own, not a parent's.

2. **A malformed or unreadable `index.md` silently disables the R5 guard for that dir.** `_parent_uuid` returns `None` on any parse/read failure, so `_reject_cross_item_merge` returns early and `create_index`'s skip-if-exists reopens the silent-merge path for that directory. **The spec permits this** — R5's predicate is literally "`parent_backlog_uuid` is non-null AND differs", and a corrupt index cannot establish a difference — and the trade is documented in both the code docstring and the Task-2 Status note. It is nonetheless a narrow gap in a fix whose thesis is "fail loud instead of inventing a lifecycle": the one input shape that cannot be reasoned about is the one that gets the silent pass. Recording it so the follow-up security ticket inherits it rather than rediscovering it.

3. **`skills/lifecycle/SKILL.md:56` already assigns a meaning to "exit-3", and R6's rationale missed it.** The spec argued exit 3 costs zero prose because "`SKILL.md:56` enumerates only exit 2". That line in fact reads: *"pass `""` on resume and **on an exit-3 no-match**. Exit 2 (ambiguous slug) → …"* — the exit-3 there is the upstream resolver's no-match (`resolve_item.py:599`), sitting one sentence before enter's exit-2 arm. Enter's new exit 3 therefore introduces a second meaning for "exit 3" inside the same paragraph. The concrete hazard: an agent that reads enter's exit 3 as "the exit-3 no-match" would re-run with `--backlog-file ""` — which **disables** the R5 guard (inert by design when the backlog file is empty) and proceeds to the silent merge R5 exists to prevent. The implementation had no latitude here (the operator constraint forbids skill-prose edits) and R6's stated acceptance criteria both pass, so this is not an implementation defect — it is a spec-level gap worth carrying into whatever ticket next opens that prose.

4. **R2's acceptance is only half-pinned by an automated test.** `test_brand_new_lifecycle_with_phase_none_still_creates` patches `create_index`, so it asserts `state == "ready"` but never that `cortex/lifecycle/brand-new-slug/index.md` exists — the second clause of R2's acceptance. I verified it manually end-to-end (it does), and `create_index` has its own tests, so the risk is low; but no test in this change proves the post-guard brand-new path actually materializes an index. A one-line existence assertion in the unpatched scratch-root flow would close it.

5. **The plan's Task-4 record ("42 pre-existing failures") is worktree-environment noise and should not be inherited as fact.** The working tree shows 2, both pre-existing and both provably unrelated (they assert on `skills/refine/SKILL.md`, which this change never touches). The zero-new-failures conclusion is sound and confirmed; only the number is wrong. Flagged because a future reader treating "42 known-red" as the baseline would lose the ability to notice a real regression.

---

## Requirements Drift

**State**: detected

**Findings**:
- The change ships a **lifecycle-identity rule** — "a lifecycle's identity is the backlog item's canonical `lifecycle_slug`; a ticket number or other alias is input normalization" (Proposed ADR-0029) — that `cortex/requirements/project.md` does not capture anywhere. The spec's own ADR text concedes "Nothing in the repo governs lifecycle directory naming", and that is still true after the change: `project.md`'s Architectural Constraints has no identity/naming entry.
- The rule's most consequential property is a **split**: the served `next` → `enter` loop normalizes identity, but a hand-typed `cortex-lifecycle-enter --feature <number> --phase none` still creates a numeric-keyed dir and remains permitted. So "identity is the canonical slug" is a property of the *path*, not an invariant of the *system* — a future contributor reading only `project.md` would have no way to learn that, and the natural wrong assumption (every lifecycle dir on disk is slug-keyed) is exactly what ADR-0029 warns against.
- That split carries a live **MUST-retain** consequence on unrelated code: the #378 defensive coercions at `resolve_item.py:137-141` and `resolve.py:184-187` are not dead code, because the hand-typed path keeps producing the values they defend against. The implementation honors it, but nothing outside the spec records it — and `project.md` is where the comparable ADR-0027 frontmatter-quoter constraint records precisely this kind of "leave this in place or the hazard returns" rule.
- `cortex/adr/0029-lifecycle-identity-is-the-canonical-slug.md` does not exist (`cortex/adr/` ends at 0028); the ADR is still only spec prose. The house pattern (most recently ADR-0027, per the memory record) is an ADR file **plus** a `project.md` back-pointer bullet. Neither has landed.

Noting for completeness: `cortex-load-requirements` emitted its no-match fallback for tags `[lifecycle, cli, slug-resolution]`, so this drift check covers `project.md` only. Exit code 3, the writer guards, and the `resolved_from` field are ordinary verb-contract work (`project.md:35` — "arg+filesystem validation is normal verb work") and are **not** drift.

**Update needed**: cortex/requirements/project.md

---

## Suggested Requirements Update

**File**: cortex/requirements/project.md

**Section**: `## Architectural Constraints`

**Content**:

```markdown
- **Lifecycle identity is the canonical slug**: a lifecycle's identity is the backlog item's canonical `lifecycle_slug` (`resolve_item.py`'s chain: frontmatter → spec/research dirname → capped `slugify(title)`); ticket numbers, uuid prefixes, and filename stems are input normalization — accepted everywhere, stored nowhere *by the served loop*. The rule governs the `resolve_invocation`-mediated path (`next` → `enter`) only: a hand-typed `cortex-lifecycle-enter --feature <number> --phase none` still creates a numeric-keyed dir and stays permitted (`374/`, `378/`), so not every lifecycle dir on disk is slug-keyed. Consequence: the #378 defensive str-coercions (`resolve.py`, `resolve_item.py:137-141`) MUST be retained — the hand-typed path keeps producing the values they defend. `enter` is the enforcement point (unsafe-slug, missing-lifecycle, and cross-item-uuid guards → stderr + exit 3, no side effect). → ADR-0029.
```

---

## Verdict

All twelve requirements PASS on independently re-run evidence, including both flagged deviations — R4's substitute verification covers its actual claim more precisely than the destructive literal command would have, and R12's literal criterion was unmeetable at the baseline, with the change proven to add zero failures on a cleaner measurement than the plan recorded. The Non-Requirements hold: zero skill-prose edits, no protocol bump, and the ADR-0029 "Consequence" retention clause honored at both sites and newly regression-pinned. Guard ordering is correct and structurally tested; `_GuardRejected` provably escapes both swallow paths. The five issues are minor and none blocks: two are spec-permitted trades recorded for the already-planned follow-up security ticket, one is a spec-level prose gap the operator constraint forbade fixing here, and two are hygiene notes on test pinning and a misleading recorded number.

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["_parent_uuid serves two frontmatter schemas via a key-preference heuristic (fm.get(\"uuid\", fm.get(\"parent_backlog_uuid\"))); correct only because create_index._render happens to emit no uuid key into index.md — an explicit key argument would make both call sites self-describing", "A malformed or unreadable index.md makes _parent_uuid return None, silently disabling the R5 cross-item guard for that dir and reopening the silent-merge path; spec-permitted (R5's predicate requires proving a difference) and documented, but recorded so the follow-up security ticket inherits it", "skills/lifecycle/SKILL.md:56 already uses \"exit-3\" for the upstream resolver's no-match, one sentence before enter's exit-2 arm; R6's rationale claimed that line \"enumerates only exit 2\" and missed it. An agent misreading enter's new exit 3 as the resolver's exit-3 no-match would re-run with --backlog-file \"\", which disables the R5 guard. Not fixable here (no-skill-prose constraint) — carry to the next ticket touching that prose", "R2's acceptance is half-pinned: test_brand_new_lifecycle_with_phase_none_still_creates patches create_index, so it asserts state == \"ready\" but never that index.md exists. Verified manually end-to-end; a one-line existence assertion would close it", "The plan's Task-4 record of \"42 pre-existing failures\" is detached-worktree environment noise — the working tree shows 2, both asserting on skills/refine/SKILL.md, which this change never touches. The zero-new-failures conclusion holds; the number would mislead a future reader about suite health"], "requirements_drift": "detected"}
```
