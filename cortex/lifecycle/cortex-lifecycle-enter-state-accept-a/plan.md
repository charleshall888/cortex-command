# Plan: cortex-lifecycle-enter-state-accept-a

## Overview

Harden the one lifecycle writer that materializes a directory (`enter.py`) with three fail-loud guards, then fix the producer (`resolve.py`'s `new` branch) so it emits the backlog item's canonical `lifecycle_slug` instead of the raw caller token. The guards land first because Phase 2 removes the `is_dir()` conjunct that currently holds the path-traversal vector inert.

**Architectural Pattern**: layered
<!-- Producer (resolve) normalizes identity once at the boundary; the writer (enter) validates its own args + filesystem preconditions before any side effect. "Parse, don't validate" applied across two layers. -->

## Outline

### Phase 1: Writer guards (tasks: 1, 2)
**Goal**: `enter` refuses to materialize a lifecycle dir it cannot account for, failing loud via stderr + exit 3 with zero skill-prose edits.
**Checkpoint**: `uv run pytest cortex_command/lifecycle/tests/test_enter.py -q` green, including a new guard-trip test per guard and the preserved `test_cli_exits_0_with_error_state_on_unexpected_exception`.

### Phase 2: Producer normalization (tasks: 3, 4)
**Goal**: `resolve_invocation`'s `new` branch emits `feature = lifecycle_slug` + `resolved_from`, with `state: new` and the pinned-slug corpus unaffected.
**Checkpoint**: `just test` green; the corpus drift check emits zero rows.

## Tasks

### Task 1: Add the fail-loud guard scaffolding + unsafe-slug and existence/phase guards to `enter`
- **Files**: `cortex_command/lifecycle/enter.py`, `cortex_command/lifecycle/tests/test_enter.py`
- **What**: Introduces the purpose-built exception, its `main()` catch arm returning exit 3, and the two guards that need no backlog read: the unsafe-slug rejection (R3) and the resume-of-a-non-existent-lifecycle rejection (R1/R2/R4/R7). Closes the reported shadow-dir incident on its own.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Guard site: `enter.py:158` — both guards must precede `create_index(feature, backlog_file, root)` at `:169`, and precede the `backlog_status == "already_complete"` short-circuit at `:160-167` only if an unsafe/absent-dir invocation should fail loud rather than return `needs-decision`; place them at the top of `enter()` before `_backlog_status` so no filesystem read happens on an unsafe token (R3: "before any filesystem op").
  - Exception must **not** subclass `OSError` — `main()`'s `except OSError` arm at `:261-267` is exit 1 and would swallow it. Add the new `except` arm between `except _Exit2` (`:268`) and the broad `except Exception` (`:270`), which returns exit 0 with `state: "error"`.
  - Unsafe-slug idiom to adopt: `describe.py:55-63` `_reject_unsafe_slug` (rejects empty, `/`, `\`, `..`). It returns an error *envelope*; here the same predicate must instead raise, because R6 requires exit 3 not `state: "error"`. The whitelist alternative is `wontfix_cli.py:46` `_SLUG_RE = ^[a-z0-9]+(-[a-z0-9]+)*$` — pick one existing idiom, do not invent a third. Note the whitelist rejects `374` (`^[a-z0-9]+` matches digits, so `374` passes) but would reject any uppercase or underscore token; the blacklist is the lower-risk choice against the grandfathered corpus (R4).
  - Existence guard predicate: `--phase != "none"` AND `not (root / "cortex" / "lifecycle" / feature).is_dir()`. This is the fourth application of the shipped pattern at `critical_review/__init__.py:484-494` (`_lifecycle_dir_exists(lifecycle_root, feature) -> bool`); read its docstring — it records why the guard lives in callers, never in the write primitive.
  - R7: the message must name the feature and distinguish "dir vanished mid-flight" (TOCTOU) from "caller mis-threaded the identity", and point at the served-slug remedy. One message with both causes named is acceptable; the wording is reviewed at implement time.
  - Stderr line format: `cortex-lifecycle-enter: …` (the file's own idiom at `:249`, `:262-266`).
  - Module docstring at `:59-68` enumerates exits 1 and 2 — add exit 3 there. `KNOWN_STATES` at `:99` is unchanged (exit 3 emits no envelope).
  - Docstring-only documentation of the provisional-until-pinned window belongs in Task 3 (`resolve.py`), not here. No file under `skills/` or `plugins/*/skills/` is touched (R6a).
  - Existing test that will break: `test_sync_receives_caller_passed_discriminants` (`tests/test_enter.py:152-169`) calls `en.enter(feature="feat", phase="plan", root=tmp_path)` with no lifecycle dir under `tmp_path` — the R1 guard trips it. Repair by creating `tmp_path / "cortex" / "lifecycle" / "feat"` before the call; do not weaken the guard to accommodate it. `test_all_known_states_reachable` (`:135`) passes `--phase p` but monkeypatches `en.enter` to `_boom`, so the guard never runs — leave it alone.
  - Test-suite seam: `_patch_primitives` (`tests/test_enter.py:24-45`) patches `create_index`/`sync`/`init_ensure` on the verb's module namespace; the guards run in `enter()` *before* those, so guard tests need no patching. `_cli_args` (`:304-311`) passes `--phase none --feature feat`, so the CLI-contract tests are unaffected.
- **Verification**: two checks, both required.
  (1) `uv run pytest cortex_command/lifecycle/tests/test_enter.py -q` → exit 0, all pass, including new tests asserting (a) `main()` returns `3` and stderr matches `no such lifecycle` for `--feature no-such-thing --phase research`, with the dir still absent; (b) `main()` returns `3` for `--feature '../../../tmp/evil' --phase none` and nothing is written outside the lifecycle root; (c) `--feature brand-new-slug --phase none` still returns `state == "ready"` (R2); (d) a feature whose dir exists passes with `--phase specify` (R4); (e) `test_cli_exits_0_with_error_state_on_unexpected_exception` passes **unmodified**.
  (2) R1 demands the command's OWN exit code, not a downstream check — from an empty scratch root: `CORTEX_REPO_ROOT=$(mktemp -d) uv run python -m cortex_command.lifecycle.enter --feature no-such-thing --phase research --session-id X --backend cortex-backlog --backlog-file ""; echo $?` → prints `3`, stderr matches `no such lifecycle`, and `test -d "$CORTEX_REPO_ROOT/cortex/lifecycle/no-such-thing"` → exit 1. Pass = all three; any other exit code fails. (`enter.py:277-278` already has the `__main__` block, so `-m` exercises the same `main()` the console script calls.)
- **Status**: [x] done — `d2d1bac1`; blacklist idiom chosen; guards at top of `enter()` before `_backlog_status`. Correction: `_lifecycle_dir_exists` lives at `cortex_command/critical_review/__init__.py:484`, not under `cortex_command/lifecycle/` as the spec and Task 2 below cite.

### Task 2: Add the same-item-uuid guard to `enter`
- **Files**: `cortex_command/lifecycle/enter.py`, `cortex_command/lifecycle/tests/test_enter.py`
- **What**: Blocks the silent cross-ticket merge (R5) that Phase 2's derived-slug identity makes reachable: when the target dir exists and its `index.md` names a *different* backlog item than `--backlog-file`, fail via the Task-1 exception + exit 3, leaving the dir byte-identical.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Predicate: target `index.md` exists AND its frontmatter `parent_backlog_uuid` is non-null AND `--backlog-file` is non-empty AND that item's `uuid` differs → raise. Compare the **uuid**, not the filename — it is immutable across renames/renumbering.
  - **Inert by design when `--backlog-file` is `""`** (Context B / `no_match`): there is no item to collide on, so the check is skipped. This is a stated coverage limit, not a hole to close here.
  - Frontmatter reader: `_parse_frontmatter` is already imported into `create_index.py:50` from `cortex_command.backlog.resolve_item`; it parses both a backlog item and an `index.md`. Reuse it rather than adding a parser.
  - The merge mechanism this closes is `create_index.py:164-165` (`if target.exists(): return {"signal": "skipped"}`). `create_index.py:99-131` `_render` is what emits `parent_backlog_uuid`/`parent_backlog_id` into index.md frontmatter, with the literal string `null` when there is no uuid (`:112`) — so the reader must treat `"null"` as absent, not as a uuid to compare.
  - Guard ordering: this one needs a filesystem read, so it sits after Task 1's unsafe-slug guard (which must stay first) and can sit beside the existence guard. It must still precede `create_index` at `:169`.
  - Live reference for the frontmatter shape: `cortex/lifecycle/cortex-lifecycle-enter-state-accept-a/index.md`.
- **Verification**: `uv run pytest cortex_command/lifecycle/tests/test_enter.py -q` → exit 0, including a new test that creates a lifecycle for item A, invokes `enter` with A's slug and B's `--backlog-file`, asserts the return code is `3` and A's `index.md` sha256 is unchanged before/after; plus a test that a `parent_backlog_uuid: null` index.md with `--backlog-file ""` passes the guard (inert-by-design arm).
- **Status**: [x] done — `f7291f98`; reuses Task 1's `_GuardRejected`. Known trade: `_parent_uuid` returns `None` on a malformed `index.md`, so a corrupt index silently disables the check for that dir (keeps the guard from stealing `create_index`'s exit-1 contract).

### Task 3: Emit the canonical slug from `resolve_invocation`'s `new` branch
- **Files**: `cortex_command/lifecycle/resolve.py`, `cortex_command/lifecycle/tests/test_resolve.py`
- **What**: Applies the rule already live at `resolve.py:188` to the one branch that skips it — when a backlog item resolved and `slug != feature`, the `new` envelope carries `feature = lifecycle_slug` and `resolved_from = <raw token>` (R8), with `state: new` preserved (R9), Context B untouched (R10), and the pinned corpus unaffected (R11).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Fix site: `resolve.py:204-211` — the `if not dir_exists:` block. The resolved backlog dict is already in scope at `:208`.
  - The existing remap at `:180-192` fires only when `slug and slug != feature and (lifecycle_base / slug).is_dir()`. That `is_dir()` conjunct is **#370's deliberate bound, not a bug** — the `new` branch needs its own normalization; do not simply delete the conjunct from `:188`, which would flip existing `new` results to `resume` and violate R9.
  - Coercion idiom to reuse: `:182-187` (`if slug is not None: slug = str(slug)`) — #378's defensive reader coercion. It **MUST be retained**; the hand-typed `enter --feature 999` path keeps producing the values it defends against (Proposed ADR-0029, "Consequence").
  - `resolved_from` already exists and is served on the `resume` arm (`:231-233`, `next_verb.py:459-460`). Same field, no new shape, no protocol bump.
  - Zero `next_verb.py` changes: `new` is in `_ROUTING_PASSTHROUGH` (`:88-96`, `:421-424`) and flows through verbatim. Note this also means `next_verb.py`'s sanitizer (`:433`) is scoped to `resume` and does **not** cover this branch — that is why Task 1's guard is the sequenced predecessor, and why the `lifecycle_slug: ../../../../tmp/evil` frontmatter scenario stays open on the `refine` path (Non-Requirements).
  - Pinned test to update deliberately (R12): `tests/test_resolve.py:194-202` `test_numeric_id_without_slug_dir_stays_new` — `assert "resolved_from" not in r` flips to assert its presence and the normalized `feature`; `assert r["state"] == "new"` **must remain unchanged in the diff**.
  - Docstring home for the accepted title-drift window (research OQ3): document "first-entry identity is provisional until `enter` pins it — one skill turn" in `resolve.py`'s docstring. Code docstrings and `spec.md` only — zero skill-prose edits.
  - No file under `skills/` or `plugins/*/skills/` is touched. `PROTOCOL_VERSION` is not bumped (`protocol.py:24-27` — value semantics, not envelope shape).
- **Verification**: `uv run pytest cortex_command/lifecycle/tests/test_resolve.py -q` → exit 0, including (a) the updated pinned test asserting `state == "new"`, `feature == "core-skill-efficiency-survivors-of-the"`-shaped normalization and `resolved_from == <raw token>`; (b) a Context-B test asserting `feature` is the caller token and `resolved_from` is absent when no item matches.
- **Status**: [x] done — `2195762b`; split the `:188` predicate into a `canonical_slug` local rather than deleting the `is_dir()` conjunct, so #370's resume bound stays intact. R12's `state` assertion verified unchanged as diff context.

### Task 4: Run the corpus drift acceptance check and the full suite
- **Files**: none (verification-only; no source edits)
- **What**: Proves R11's corpus claim empirically against the live 372-item tree — every existing lifecycle dir still resolves to its own name — and confirms the whole change is green.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - R11 acceptance (a): `cortex-lifecycle-next 374` → `feature == "374"`, `resume`, `resolved_from` absent — byte-identical to pre-fix (the dir exists, so the branch never fires).
  - R11 acceptance (b): for every `d` in `cortex/lifecycle/*/`, `cortex-lifecycle-next "$(basename $d)"` returns `feature == basename $d`; the count of rows where they differ must be `0`. Research §Adversarial 6 recommends exactly this to rule out in-flight dirs created via the `refine.py:212`/`:289` mkdir bypass.
  - The installed `cortex-lifecycle-next` console script resolves to the uv-tool venv, not the working tree — run the check against the working-tree module (`uv run python -m …`) or reinstall first, or the check silently validates the old code.
  - R6 acceptance (a): `git diff --stat` for the whole change lists zero files under `skills/` or `plugins/*/skills/`.
- **Verification**: three checks, all required.
  (1) Baseline-then-compare, because `just test` has two known-red pre-existing failures (refine writeback, mcp DNS) and will not exit 0: capture the failing-test node-id set on `HEAD` before the change, run `just test` after, and diff the two sets. Pass = the after-set is a subset of the before-set (no new failures); fail = any node id present after but not before.
  (2) Corpus drift loop: for every `d` in `cortex/lifecycle/*/`, compare `basename $d` against the `feature` field returned for that basename. Pass = the count of rows where they differ is exactly `0`; any nonzero count fails. Additionally `374` → `feature == "374"`, `state == "resume"`, `resolved_from` absent.
  (3) `git diff --stat` → grep for `^ *skills/` and `^ *plugins/.*/skills/` returns zero matches (R6a).
- **Status**: [x] done — all three pass. (1) Baseline `09a11815` vs `2195762b`, both run in identical detached worktrees so only code differs: 42 failures before, the same 42 after, **zero new**. **Correction (review cycle 1):** that 42 was detached-worktree environment noise, not the real baseline. `just test` on the working tree gives **3** failures, none from this change: the known-red `test_writeback_*` pair (`tests/test_model_resolution_wiring.py`), plus `test_dual_source_byte_parity[cortex-core::skills/refine/references/specify.md]` caused by a **concurrent session's uncommitted edit** to that file. This change touches zero refine files, so all three are pre-existing by construction — a stronger result than the worktree diff. (2) Corpus drift: **177 dirs checked, 0 drift rows**; `374` → `feature=374`, `state=resume`, no `resolved_from`. (3) Zero `skills/` or `plugins/*/skills/` files across `09a11815..HEAD` — the whole change is 4 files, all under `cortex_command/lifecycle/`.

## Risks

- **Guard placement vs. the `needs-decision` short-circuit** — Task 1 places the guards before `_backlog_status`, so an already-complete item invoked with an unsafe slug now fails exit 3 instead of returning `needs-decision`. That is the intended precedence (fail loud beats a decision prompt on a token that must never touch the filesystem), but it is a behavior ordering the spec does not name explicitly.
- **Blacklist vs. whitelist idiom** — the spec permits either; the plan recommends the `_reject_unsafe_slug` blacklist because the `_SLUG_RE` whitelist would reject any uppercase/underscore token and the grandfathered corpus was never audited for those. The deferred security ticket must pick one for the other seven writers regardless.
- **Task 4's console-script trap** — the corpus check is the only acceptance that exercises the *installed* CLI. Run against the uv-tool venv and it validates the pre-fix code and passes vacuously.
- **Coverage limits are by design, not oversight** — R5 is inert when `--backlog-file` is `""`; the traversal guard closes the `next` → `enter` chain only, and `/cortex-core:refine` still reaches the unguarded CWD-relative mkdir at `refine.py:211-212`/`:288-289` without ever invoking `enter`. Both are recorded Non-Requirements deferred to a security ticket; the plan does not widen them.

## Acceptance

Entering a not-yet-pinned backlog item by ticket number through `/cortex-core:lifecycle` creates a **slug-keyed** lifecycle dir (matching what `/cortex-core:refine` and `overnight/backlog.py`'s `resolve_slug()` already assume), while `cortex-lifecycle-enter` handed a resume phase for a non-existent dir, a path-traversal token, or another item's dir writes a `cortex-lifecycle-enter: …` line to stderr, exits 3, and creates nothing. `374`/`378` resolve byte-identically to pre-fix, and the diff touches zero files under `skills/`.
