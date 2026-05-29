# Plan: rescope-cortex-init-ensure-to-never

## Overview
Restrict in-session `cortex init --ensure` (`_run_ensure`) to repo-scope writes
only: remove the three `~/.claude/`-touching calls so the sandbox no longer
forces a `dangerouslyDisableSandbox` retry, and convert the marker-absent
clean-repo case from bootstrap to a refuse-with-directive (exit 2) that points
the user to terminal `cortex init`. The handler change and its directly-coupled
tests land together (one green commit); the dependent auto-apply spec and the
first-contact docs are then reconciled to the new contract. Terminal
`cortex init` and the R19 foreign-content refusal are untouched.

## Outline

### Phase 1: Rescope `--ensure` (behavior + tests) (tasks: 1, 2)
**Goal**: `_run_ensure` performs no `~/.claude/` write; clean-repo case refuses
with exit 2 + a directive distinct from R19; the test suite stays green at every
commit and the R1 spy / byte-identity coverage is added.
**Checkpoint**: `just test` exits 0 with `_run_ensure` containing zero
`settings_merge.register` / `validate_settings` / `unregister_matching_in_place`
calls, case (iii) raising `ScaffoldError` → exit 2, and a spy test asserting the
post-dispatch calls (`register`, `unregister_matching_in_place`) fire zero times across
cases (ii)/(iii)/(v) and the pre-flight `validate_settings` fires zero times across cases
(i)/(ii)/(iii)/(iv)/(v).

### Phase 2: Reconcile dependents (tasks: 3, 4)
**Goal**: the completed `auto-apply-cortex-init-at-lifecycle` spec is amended at
all three clean-repo-bootstrap sites (+ superseding pointer), and the
first-contact docs (README, landing page) lead adopters to terminal
`cortex init` before `/lifecycle`.
**Checkpoint**: all three clean-repo-bootstrap sites in the auto-apply spec are revised to
the exit-2 contract — the Problem-Statement clause (line 5) and R4 acceptance #1 (line 28)
"exits 0 and writes"/"bootstrap automatically" phrasings removed, AND the case-(iii)
dispatch-table row's "dispatch through clean first-init … write the marker" behavior phrase
revised — with R5's preserved "bootstrap a clean one" untouched; `273` is referenced there;
README's `cortex init` step is no longer OPTIONAL; and `cortex init` appears in the landing
page's cortex-core start-here block.

## Tasks

### Task 1: Rescope `_run_ensure` and flip the tests the change breaks
- **Files**: `cortex_command/init/handler.py`, `cortex_command/init/tests/test_handler_ensure.py`
- **What**: Remove the three `~/.claude/` writes from `_run_ensure` and convert
  the marker-absent clean-repo case (iii) from bootstrap to a refuse-with-directive
  (exit 2). In the same change, flip every `test_handler_ensure.py` assertion the
  behavior change breaks (the two case-iii tests, plus any `--ensure` test that
  asserts a `~/.claude/` write) so `just test` stays green. (R1 behavior, R2, R3.)
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - `_run_ensure` is at `cortex_command/init/handler.py:129-240`. Remove these three
    `settings_merge` calls, all of which target real `~/.claude/`:
    `validate_settings(home)` (pre-flight, currently :163), `register(repo_root, cortex_target, home=home)`
    (post-dispatch, currently :233), `unregister_matching_in_place("cortex-worktrees", home=home)`
    (post-dispatch, currently :238). Keep the repo-scope post-dispatch writes
    `scaffold.ensure_gitignore(repo_root)` and `scaffold.ensure_claude_md_authorization(repo_root)`.
  - After removal, the `home: Path | None = None` local (currently :140) is unused — remove it.
    The module-level `settings_merge` import stays (still used by the terminal `_run` path at
    :464/:520/:529); do not touch imports.
  - Case (iii) is the `if cortex_absent_or_empty:` branch (currently :219-222) that calls
    `scaffold.scaffold(...)` + `scaffold.write_marker(refresh=False)`. Replace its body with
    `raise ScaffoldError(<directive>)`. `ScaffoldError` is already imported and is caught in
    `main()` (currently :571-573) → exit 2, the user-correctable-refusal path. The `else` branch
    (case iv, `scaffold.check_content_decline(repo_root)`) is unchanged. Raising before scaffold
    guarantees no `cortex/`, `CLAUDE.md`, or `.gitignore` write on the refuse path (R3).
  - Directive constraints (R3, OQ2 — exact prose is implementer's to finalize): single-line
    stderr message; names terminal `cortex init` as the corrective action; contains a unique
    marker substring that does NOT appear in the R19 `check_content_decline` message
    (`cortex_command/init/scaffold.py:199-202`, whose distinctive phrase is "pre-existing content").
    R3's hard gate is R19-distinctness, but the two R8 marker-corruption messages
    (`scaffold.py:525` "Run `cortex init` to reinitialize" and `:545` "Run `cortex init` manually")
    also fire on the `--ensure` path and also say "Run `cortex init`" — the directive's unique
    substring should be absent from those two as well, so the distinctness test asserts the substring
    is absent from all three messages (strengthens the gate against a later reword on this
    load-bearing first-contact surface; spec-additive, not a contract change).
    Candidate phrasing: "`cortex init --ensure`: this repo is not yet initialized for cortex
    (no `cortex/`). Run `cortex init` in your terminal, then re-run /lifecycle." — the substring
    "not yet initialized" is verifiably unique across all three messages.
  - Test flips in `test_handler_ensure.py` (helpers `_make_ensure_args`, `_isolate_home` at
    :58-78): the case-iii tests `test_r4_case_iii_a_clean_scratch_repo` (:209) and
    `test_r4_case_iii_b_empty_cortex_dir` (:231) currently assert `rc == 0` + marker written —
    flip both to assert `rc == 2`, that stderr contains the directive's unique substring, and that
    `git status --porcelain` shows no new/modified files; update their "→ bootstrap" docstrings.
    Run the module first to surface any other `--ensure` test that asserts a `~/.claude/` write and
    flip it too. (The dedicated spy + byte-identity coverage is added in Task 2 — keep this task to
    the minimum flips needed for green.)
  - Sibling `cortex_command/lifecycle/tests/test_init_ensure.py` needs no behavioral change
    (it monkeypatches `handler.main()` and asserts only exit-code pass-through) — re-run it to confirm.
- **Verification**: run `python3 -m pytest cortex_command/init/tests/test_handler_ensure.py cortex_command/lifecycle/tests/test_init_ensure.py -q` — pass if exit 0; run `just test` — pass if exit 0; run `sed -n '/^def _run_ensure/,/^def /p' cortex_command/init/handler.py | grep -c -E 'settings_merge\.(register|validate_settings|unregister_matching_in_place)'` — pass if output is `0`.
- **Status**: [x] complete

### Task 2: Add the R1 no-`~/.claude/`-write spy and byte-identity tests
- **Files**: `cortex_command/init/tests/test_handler_ensure.py`
- **What**: Add the dedicated coverage R1's acceptance requires: a spy asserting
  the three `~/.claude/` calls fire zero times across the cases that previously
  reached the post-dispatch block, and a temp-HOME byte-identity assertion. These
  pass against the handler already changed in Task 1. (R1 acceptance, R8.)
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Add a test that spies on `cortex_command.init.settings_merge` (monkeypatch `register`,
    `validate_settings`, and `unregister_matching_in_place` with call counters). `register` and
    `unregister_matching_in_place` were post-dispatch — assert zero calls across case (ii)
    marker-present + hash-mismatch, case (iii) clean, and case (v) R8 recovery. `validate_settings`
    was a PRE-FLIGHT call reached on every non-early path — so additionally assert it is called zero
    times on case (i) marker-present + hash-match (early-return) and case (iv) marker-absent +
    foreign-content (R19 decline), not only (ii)/(iii)/(v). Cases (ii) and (v) must be exercised (not
    only the early-return case (i)) so the post-dispatch assertion is non-trivial. Reuse
    `_write_marker` (:81) for the marker-present cases and the hash-mismatch monkeypatch pattern from
    the existing case-(ii) test (`monkeypatch.setattr` on the installed-hash helper, see the test
    near :185).
  - Add a temp-HOME assertion: capture `~/.claude/settings.local.json` bytes (or its absence) before
    `--ensure`, run `--ensure` (use a marker-present drifted repo so dispatch reaches post-dispatch),
    and assert the file is byte-identical (or still absent) afterward. ALSO assert the lockfile
    `~/.claude/.settings.local.json.lock` is never created — today `validate_settings`→`_acquire_lock`
    creates it, so its absence is a fixture-independent signal that no `~/.claude/` access occurred
    (the bytes-absent check alone is fixture-dependent: `_isolate_home` pre-creates `~/.claude/`, so
    "still absent" can pass trivially). Use the `_isolate_home` fixture (:58) for the temp HOME.
  - Do not modify `handler.py` in this task — it is test-only, layered on Task 1's behavior.
- **Verification**: run `python3 -m pytest cortex_command/init/tests/test_handler_ensure.py -q` — pass if exit 0; run `grep -c "settings.local.json.lock" cortex_command/init/tests/test_handler_ensure.py` — pass if ≥ 1 (the lockfile-absence assertion is present); run `grep -c "unregister_matching_in_place" cortex_command/init/tests/test_handler_ensure.py` — pass if ≥ 1 (the spy references the call by name); run `just test` — pass if exit 0.
- **Status**: [x] complete

### Task 3: Amend the auto-apply-cortex-init-at-lifecycle spec to the new contract
- **Files**: `cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/spec.md`
- **What**: Revise all three sites that assert clean-repo bootstrap and add a
  top-of-file superseding pointer + per-site rationale referencing #273. (R7.)
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Three sites to revise (line anchors current, will drift). NOTE: the word "bootstrap" does
    NOT appear in the case-(iii) row — its old-behavior marker is the phrase "dispatch through
    clean first-init … write the marker" (the only occurrence in the file). "bootstrap" elsewhere
    is at the Problem Statement (line 5), R5 (line 30 — PRESERVE: "bootstrap a clean one"), and
    R11 (line 42 — unrelated worktree diagnostic). Do not delete those. (a) the R4 dispatch-table
    case-(iii) row (currently :26, "marker absent + `cortex/` absent OR empty: dispatch through
    clean first-init … write the marker") → replace its behavior phrasing with "→ refuse, exit 2
    (no bootstrap)"; (b) R4 acceptance criterion #1 (currently :28,
    "`cortex init --ensure` in a clean scratch repo (no `cortex/`) exits 0 and writes
    `cortex/.cortex-init`") → state the exit-2 refuse; (c) the Problem-Statement clause (currently :5,
    "Brand-new clean repos (no `cortex/` directory) also bootstrap automatically on first
    `/lifecycle` invocation.") → state that clean repos now refuse with exit 2.
  - Add one superseding pointer near the top of the file (e.g.
    "> Partially superseded by #273: clean-repo bootstrap replaced by exit-2 refuse — see R4.")
    and a one-line `#273` rationale note at each revised site.
  - Preserve R5 (marker-absent + `cortex/`-has-content → R19 decline) verbatim. Do NOT rewrite that
    lifecycle's `plan.md` / `review.md` — they are historical records; the superseding pointer is the
    reconciliation signal.
- **Verification**: `grep -c -E "exits 0 and writes|bootstrap automatically" cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/spec.md` — pass if `0` (sites b + c revised); `grep -c "dispatch through clean first-init" cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/spec.md` — pass if `0` (site a, the case-(iii) row's old-behavior phrase, revised); `grep -c "273" cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/spec.md` — pass if ≥ 1; `grep -c "bootstrap a clean one" cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/spec.md` — pass if `1` (R5 statement preserved, not accidentally stripped).
- **Status**: [x] complete

### Task 4: Correct first-contact docs so terminal `cortex init` precedes `/lifecycle`
- **Files**: `README.md`, `docs/index.html`
- **What**: Remove the OPTIONAL framing of `cortex init` in README (leave the
  overnight-plugin OPTIONAL intact), and surface terminal `cortex init` as a
  required step before `/lifecycle` in the landing page's cortex-core start-here
  block. (R9.)
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - `README.md` (~:27): the `cortex init` step is currently introduced by the comment
    "# 3. OPTIONAL - In each project where you want cortex active." Remove the OPTIONAL framing on
    this step (re-word the comment so it reads as a required per-project step). The separate OPTIONAL
    annotation on the overnight-plugin install line (~:25, "OPTIONAL - autonomous overnight runs")
    must remain.
  - `docs/index.html`: the cortex-core start-here block is the `<article class="ship-card required"
    data-surface="skills">` element (~:6653-6660). Currently `cortex init` appears only in the
    overnight `<article data-surface="overnight">` block (~:6671). Add the literal `cortex init` as a
    required step inside the skills article (before/alongside the `/lifecycle` mention), matching the
    existing `<p class="ship-when">` markup style.
- **Verification**: `grep -c "OPTIONAL - In each project" README.md` — pass if `0` (the `cortex init`-step OPTIONAL annotation is removed; this anchors the specific edit, not a brittle total-token count); `grep -c "OPTIONAL - autonomous overnight" README.md` — pass if `1` (overnight-plugin OPTIONAL preserved); extract the `data-surface="skills"` article block and confirm it contains the literal `cortex init`: `awk '/data-surface=\"skills\"/{f=1} f; /<\/article>/{if(f)exit}' docs/index.html | grep -c "cortex init"` — pass if ≥ 1.
- **Status**: [x] complete

## Risks
- **Deviation from the spec's phase labels (deliberate).** The spec assigns R8 (test
  updates) to Phase 2, but this plan places the test work in Phase 1 (Task 1 flips the
  assertions the behavior change breaks; Task 2 adds the R1 spy / byte-identity coverage).
  Rationale: flipping the case-iii assertions in a later task than the behavior change would
  leave a red intermediate commit (`just test` failing between tasks), so behavior + its
  breaking-test flips must land in one green commit (Task 1). The net-new coverage is split
  into Task 2 to keep each task within the 5–15 min sizing bound. No scope change, only sequencing.
- **R3 directive wording is implementer-finalized** (per OQ2 / spec — exact prose is
  implementation-level). The binary distinctness gate (Task 1's test) enforces that the directive's
  unique substring is absent from R19 AND from the two R8 "Run `cortex init`" messages
  (`scaffold.py:525`/`:545`) — broadened beyond the spec's R19-only acceptance because those R8
  messages also fire on the `--ensure` first-contact path, so the gate protects the load-bearing
  surface even if the wording is later changed.
- **Optional SKILL.md / CLAUDE.md clarifying notes are intentionally omitted.** The spec's
  Non-Requirements mark these as permitted-but-not-required; the existing SKILL.md:128
  halt-on-non-zero already routes the new exit-2 correctly, so no SKILL.md control-flow change
  is made (keeps the dual-source mirror untouched).
- **Dropped `cortex-worktrees` migration from `--ensure`** is an accepted consequence (spec
  Non-Requirements): a user whose only path is in-session `/lifecycle` won't have stale
  `cortex-worktrees` entries expunged. They are inert, and terminal `cortex init --update` still
  performs the migration.

## Acceptance
In a Claude Code session on a marker-present cortex repo, `cortex-lifecycle-init-ensure`
(→ `cortex init --ensure`) completes with exit 0 and attempts no `~/.claude/` write (no
`dangerouslyDisableSandbox` retry); on a clean repo it exits 2 with an actionable directive
naming terminal `cortex init` and distinct from the R19 message, writing nothing. Terminal
`cortex init` still writes the `~/.claude/` grant. `just test` exits 0, the auto-apply spec
no longer asserts clean-repo bootstrap (and references #273), and the first-contact docs lead
adopters to terminal `cortex init` before `/lifecycle`.
