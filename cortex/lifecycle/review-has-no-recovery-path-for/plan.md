# Plan: review-has-no-recovery-path-for

## Overview

Add an exists-and-non-empty precondition to `register_artifact` so it refuses to record an artifact that
was never written, reusing the existing `error` state so no new state value enters the payload (which
would bump `PROTOCOL_VERSION` and strand out-of-repo consumers). Enforcement is the withheld `index.md`
write, not a returned value — none of the five skill-prose call sites branch on state, so a signal alone
would be inert.

## Outline

### Phase 1: Verb gate (tasks: 1, 2)
**Goal**: `register_artifact` stops recording artifacts that do not exist.
**Checkpoint**: registering `review` with no `review.md` present returns `"state":"error"` and leaves
`index.md` byte-identical; the full `test_register_artifact.py` suite is green.

### Phase 2: Review-phase response (tasks: 3)
**Goal**: the review phase has a defined, coherent response to a reviewer that wrote nothing.
**Checkpoint**: `review.md` §2 admits resumption as a way the artifact comes to exist, §3 no longer
instructs reading a file that was never written, and both size pins are green and identical.

## Tasks

### Task 1: Add the exists-and-non-empty precondition to register_artifact
- **Files**: `cortex_command/lifecycle/register_artifact.py`
- **Callers**: `skills/build/references/review.md:35`, `skills/build/references/plan.md:76`,
  `skills/build/references/backlog-writeback.md:19`, `skills/refine/SKILL.md:76`,
  `skills/refine/references/research-phase.md:23` (all invoke `--artifact <name>` at the CLI), plus
  `cortex_command/lifecycle/tests/test_register_artifact.py` (direct function calls, updated by Task 2)
  and `tests/test_lifecycle_verb_deployment.py:33-35` (asserts CLI deployment only). None of these branch
  on the returned `state` today, so none breaks. `plan.md`, `backlog-writeback.md`, `refine/SKILL.md`, and
  `research-phase.md` are listed for awareness only — this plan deliberately does not edit them, even
  though they inherit the new refusal.
- **What**: Before the `artifacts:` regex rewrite, stat the artifact file; when it is absent or zero-byte,
  return the existing `error` state with a `message` naming the resolved path, writing nothing. Satisfies
  spec R1, R2, R3, R5, R8.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `register_artifact()` at `:81-136`. The `index.md` read is at `:103-106` and returns
  `no-index` on `FileNotFoundError` — the new check must sit **after** that so a missing index still wins
  (R8 precedence), and **before** the `_ARTIFACTS_RE` match at `:109`. Resolve the artifact as
  `path.parent / f"{artifact}.md"` where `path` is the already-resolved index path — this makes the check
  follow whichever root resolved `index.md` and keeps the `index_path=` test injection working (R3).
  `KNOWN_STATES` at `:61` is unchanged; `error` is already a member. `main()` at `:178-190` must keep
  `return 0` (R5). Existing `error` returns carry `message` (see the docstring at `:28-33`), so match that
  shape. **Root-resolution note**: `_resolve_user_project_root_from_cwd` at `:100` is the same resolver
  `review_brief.py:607` uses to build the reviewer's absolute `review_path` (`:618`), so writer and
  checker agree when both run from one cwd; deriving from `path.parent` rather than re-resolving the root
  is what preserves that.
- **Verification**: `python3 -m cortex_command.lifecycle.register_artifact --feature f --artifact review
  --project-root <fixture>` in a fixture holding `cortex/lifecycle/f/index.md` with `artifacts: []` and no
  `review.md` prints JSON containing `"state":"error"`, exits 0, and leaves `index.md` byte-identical
  (`cmp` exits 0). Repeat with `review.md` created by `touch` — same result. Repeat with `review.md`
  holding one line — prints `"state":"registered"` and `index.md` gains `[review]`. Invoke via `python3
  -m`, never the `cortex-*` binstub, which runs the installed wheel rather than the working tree.
- **Status**: [x] done (c6dca432 2026-08-07T17:16:23-04:00)

### Task 2: Update and extend the register_artifact test suite
- **Files**: `cortex_command/lifecycle/tests/test_register_artifact.py`
- **What**: The 16 existing tests inject `index_path` into a `tmp_path` with no artifact file beside it, so
  they will now all refuse. Create the artifact alongside each injected index, then add refusal coverage.
  Satisfies spec R7, R12, and the discriminating half of R3.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `_write_index` helper at `:38-41` is where most tests build their index — creating the
  sibling artifact there covers the majority in one edit. The closed-set assertion near `:203-204`
  (`seen == {"registered", "already-present", "no-index", "error"}` and `seen <= set(ra.KNOWN_STATES)`)
  must stay **unchanged** and still pass — that is the guard proving no new state was introduced (R4).
  New cases required: (i) missing artifact → `error`; (ii) zero-byte artifact → `error`; (iii) neither
  index nor artifact → `no-index`, not `error` (R8 precedence); (iv) R3's discriminator — with
  `index_path` in a `tmp_path` subdirectory whose name does **not** match the feature name, an artifact
  beside that index yields `registered`, while an artifact placed only under a cwd-derived
  `cortex/lifecycle/{feature}/` path yields `error`.
- **Verification**: `python3 -m pytest cortex_command/lifecycle/tests/test_register_artifact.py -q` exits
  0 with no failures; `grep -c 'error' cortex_command/lifecycle/tests/test_register_artifact.py` ≥ 4.
- **Status**: [x] done (99e593d6 2026-08-07T17:26:00-04:00)

### Task 3: Give the review phase its defined response, and re-sync both size pins
- **Files**: `skills/build/references/review.md`, `skills/build/references/size-pin.txt`,
  `plugins/cortex-core/skills/build/references/size-pin.txt`
- **What**: Amend §2's single-writer rule to admit resuming the original reviewer, and rewrite §3's
  missing-drift sentence so it covers an absent *file* as well as an absent *section*. Then re-sync the
  reference-size ratchet. Satisfies spec R9, R10, R11.
- **Depends on**: none
- **Complexity**: simple
- **Context**: §2's rule is at `review.md:23` ("only the reviewer role writes `review.md`: this sub-task
  plus §3's missing-drift re-dispatch and §3a's cap-2 re-dispatches") — the rule is role-scoped, so
  admitting resumption is a list edit, not a principle change. §3's sentence is at `:33` and currently
  says "read the existing file and append it", incoherent for a file never written. The directory is at
  **zero** ratchet headroom (pin 57175, measured 57175), so prefer a byte-neutral rewrite; if bytes are
  still needed, either trim elsewhere in the directory or add a `# raised:` line matching the two existing
  precedents in `size-pin.txt` (`# raised: <what> because <why>, lifecycle-id=<id>, date=<YYYY-MM-DD>`).
  Sequence matters: `just ratchet-refs` → `just build-plugin` → `just ratchet-refs`. `build-plugin` does
  **not** carry `size-pin.txt`, so the mirrored pin is the one `plugins/` path staged by hand; the mirrored
  `review.md` is rebuilt from staged blobs by the pre-commit hook and must **not** be hand-edited. Per spec
  R9 the resumption response is resume-then-await-the-agent's-return, never resume-then-immediately-recheck
  — a resumed reviewer may be several turns from flushing.
- **Verification**: `python3 -m pytest tests/test_reference_size_ratchet.py -q` exits 0; `cmp
  skills/build/references/size-pin.txt plugins/cortex-core/skills/build/references/size-pin.txt` exits 0;
  `grep -c 'read the existing file' skills/build/references/review.md` = 0.
- **Status**: [x] done (0c79c1a7 2026-08-07T17:18:27-04:00)

## Risks

- **`error` now carries a common precondition miss, not only an unexpected exception.** The docstring at
  `register_artifact.py:28-33` defines `error` as "an unexpected exception". Folding a routine
  "artifact isn't there" into it is a semantic widening. Nothing branches on `error` today, so the cost is
  soft — but the docstring must be updated in Task 1 or the code contradicts its own contract. The
  alternative (a new `artifact-missing` state) was rejected because it bumps `PROTOCOL_VERSION`.
- **Phase 2 may not fit byte-neutral.** If the §2 and §3 edits cannot be absorbed, a `# raised:` exception
  is needed, which is a documented deliberate act rather than a silent drift. Phase 1 ships the
  enforcement regardless, so a Phase 2 stall does not block the fix.
- **All four non-`review` call sites inherit the refusal.** `plan`, `spec`, and `research` registration can
  now fail where they previously could not. The spec records this as intended; if it proves noisy, the
  narrowing is artifact-conditional logic, not a revert.
