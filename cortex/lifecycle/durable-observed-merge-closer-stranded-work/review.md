# Review: durable-observed-merge-closer-stranded-work (cycle 2)

## Verification baseline (re-run at HEAD)

Suites run separately with `.venv/bin/python -m pytest`:

- `cortex_command/` → **1791 passed**, 0 failed (matches the stated baseline; +2 from
  the resolver fix's tests)
- `tests/` → **2504 passed**, 2 failed — both the known pre-existing
  `test_model_resolution_wiring.py` reds. Not counted against this lifecycle.
- `just check-parity` → exit 0. Mirror byte-identical to canonical source.

Spec greps re-run: R3 `_MAX_NON_ALLOWLIST`=0 · R5 `candidates[0]`=0 · R7 `--state`=1 ·
R12 false claims=0. Backlog id integrity: no duplicate numeric prefixes anywhere;
`395-*` matches one tracked `.md` plus its gitignored events sidecar.

## Stage 1 — Spec Compliance

| # | Requirement | Cycle 1 | Cycle 2 |
|---|---|---|---|
| 1 | Repair `sync-allowlist.conf` patterns + per-pattern coverage test | PASS | PASS |
| 2 | Cover `sync_rebase`'s conflict-resolution path | PASS | PASS |
| 3 | Resolve the unreachable `_MAX_NON_ALLOWLIST` threshold | PASS | PASS |
| 4 | Stop `_behind_count` reporting "up to date" on failure | **PARTIAL** | **PASS** |
| 5 | Remove the blind first-match from the write-back's item lookup | PASS | PASS |
| 6 | Thread the ticket `uuid` to close time | PASS | PASS |
| 7 | Make the merged/closed PR exits reachable | PASS | PASS |
| 8 | Make the merged/closed exits honest, and report-only | PASS | PASS |
| 9 | Correct the stale advisory text at the merged exit | PASS | PASS |
| 10 | Commit and push §6b's ticket closures | PASS | PASS |
| 11 | Never report a close as durable without a verified push | PASS | PASS |
| 12 | Correct #346's false premise in the ticket body | PASS | PASS |
| 13 | Regenerate the dual-source mirror in the same commit | PASS | PASS |

No FAIL → Stage 2 assessed. Cycle-1 PASSes were spot-checked (greps, parity, the
report-only merged exit, the `pushed` derivation), not re-derived; all hold.

## The four cycle-1 issues

### 1. Exit-3 gap — fixed (Requirement 4 now PASS)

`walkthrough.md` §6a step 2 now carries both the **3** arm and an **any other code**
catch-all, in canonical and mirror alike (`check-parity` exit 0). The catch-all is the
right call: it closes the class rather than today's instance, and `sync_rebase` returns
only 0/1/2/3 today, so it is pure future-proofing rather than dead prose.

**On the gate-consistency claim I was asked to check: you are wrong, and it matters
less than it looks.** My cycle-1 report did not paraphrase §6b's gate — it quoted the
file verbatim. "Run immediately after a *successful* post-merge sync in Section 6a" was
the real wording, unchanged since `f06c0ad8`, and `28d4e19f` is what changed it (the
diff shows the deletion of "successful"). So the fix did not align itself with existing
wording; it **edited the gate**, under a commit framed as mapping exit codes.

That said, the edit is sound, and I would not reverse it:

- §6b's skip conditions were always merge-based only — "declined, skipped, or the PR
  was already merged/closed before this review". None of them is a sync condition, so
  "successful post-merge sync" implied a skip that no listed condition supported. The
  qualifier was internally contradictory before the edit; removing it resolves that.
- `test_morning_review_status_close_ordering.py::test_section_6b_is_gated_on_successful_merge`
  gates on the **merge**, confirming merge-authorization is the design intent. The new
  sentence ("ticket closure is authorized by the confirmed merge in Section 6, not by
  the sync result") restates the test's own premise.
- Proceeding on a failed sync degrades honestly rather than dangerously. I traced the
  worst case: exit 1 leaves local `main` diverged; §6b closes locally; `push_closures`
  commits and pushes; the push is rejected non-fast-forward → `state: push-failed`,
  `pushed: false`, `unpushed_tickets` named. No force push exists in the verb, and
  `pushed: true` requires both `rc == 0` **and** an observed `ahead == 0`. Requirement
  11 anticipated exactly this state and ruled it acceptable when reported honestly.

The correction worth carrying forward is procedural, not technical: cycle 1's bound on
the harm ("§6b's gate probably causes an agent to skip") was removed by this commit,
which is a real semantic change and was described to review as a consistency
alignment. Rating unaffected.

### 2. Side-ruling exit ticket — fixed

`cortex/backlog/395-rule-on-which-side-wins-...md` is substantive (55 lines), tracked,
and carries the evidence rather than a pointer to it: both rationales (the original
"the merged PR version is authoritative" intent vs. the later lifecycle's dependence on
local commits surviving), both data-loss directions, the provenance of the "remote
wins" claim as a single unexamined parenthetical, and the append-only case where
neither side is correct. Touch points are accurate.

**It does not rule.** "Decide which side should win" is stated as the work, not the
answer; the Edges section explicitly forbids ruling from the documents and notes the
conflict tests deliberately pin no side. It also records the meta-lesson — that this is
the second filing failure of the same ticket — which is the point of filing it.

### 3. `pipeline.md` `>3` threshold — fixed

The replacement matches the code exactly: `sync_rebase.py:281-289` aborts on ≥1
non-allowlist conflict and returns 1 ("exits non-zero" is more durable than the "exit
1" I suggested — good call), `git rebase --abort` leaves no partial resolution behind,
and L286-287 names every unresolved path in a loop. The surrounding block's `--theirs`
description is correct post-Task-11.

**One other stale claim does survive in that block** — see Follow-ups below. Cycle 1
missed it too; it is pre-existing rather than introduced.

### 4. Resolver fallthrough — fixed, sound, additive, non-vacuously tested

The guard readmits exactly what the resolver's numeric step itself matched
(`_numeric_prefix(found) == backlog_id`). That is the right shape: the numeric step
compares ids as ints, so a legitimate numeric match always satisfies the guard, and
anything a later step in the chain reached is discarded. The fall-through to the
feature attempt is preserved rather than aborting the lookup.

I verified non-vacuity by probing the primitives directly on the tests' own fixture
rather than by mutating source:

- Unguarded `resolve("500")` → `291-harden-the-cli-against-dependency-drift.md`, whose
  `_numeric_prefix` is 291 ≠ 500 → guarded lookup returns `None`. The fixture genuinely
  reproduces the live-backlog bug, so the guard is what makes the test pass.
- `test_stale_id_leaves_the_feature_slug_free_to_resolve` passes under the old code too
  — but that is correct by design: it kills the *over-constraint* mutation (discard →
  return `None`), which is the fix's own risk, not the bug. It is the additivity guard.
- Padded/unpadded regression holds (`id=42` → `042-alpha-feature.md`).

## Stage 2 — Code Quality

Cycle 1's assessment stands; I re-confirmed the load-bearing parts rather than
re-deriving them. The rework itself is clean:

- **`_numeric_prefix` is well-placed and documented.** It sits beside its only caller,
  states why zero-padding is insignificant, and cites `resolve_item._resolve_numeric`'s
  int comparison as the reason — the same rationale-at-the-boundary habit the rest of
  this work shows.
- **Comment density is proportionate.** The docstring says what changed and why with a
  concrete instance (id 500 → item 291), and the inline comment explains the readmit
  logic rather than restating it. "An id means a filename number and nothing else" is
  the durable statement of the rule.
- **No new error paths.** The change narrows a return; nothing raises where it did not.
- **#393's widening is honest about its own miss** ("that was measured too early and is
  wrong") and names the structural rule rather than the second instance, plus the test
  gap that hid both. That is the right shape for a ticket that has now been wrong once.

## Follow-ups (not blocking — recommend tickets)

Both are pre-existing, outside this spec's requirements, and untouched by the rework. I
raise them because they are the same defect class this lifecycle was convened to
repair — a documented contract that no longer matches the code — and because they are
cheap to lose once this lifecycle archives.

1. **`pipeline.md`'s success criterion is false on the `behind == 0` path.** "After sync
   completes successfully, `git rev-list HEAD..origin/main --count` = 0 and `git
   rev-list origin/main..HEAD --count` = 0 (local and remote identical)" does not hold:
   `sync_rebase.py:219-221` returns 0 roughly 95 lines before the push at L313-321, so
   exit 0 routinely leaves local ahead of remote with nothing pushed. This is not a
   claim Task 4 made stale — it was never true. The spec's own Requirement 10 documents
   the behavior accurately (it is the reason the push is not delegated), so the code and
   the requirement agree and only this doc line dissents. I did not fold it into issue 3
   because that issue was scoped to a claim *this lifecycle* invalidated.

2. **Exit 1 is overloaded, and the walkthrough's arm misreports one of its causes.**
   `sync_rebase` returns 1 from three places: a failed `git fetch` (L207-209), a
   non-allowlist conflict (L289), and exhausted passes (L311). The module header and
   §6a's exit-1 arm both describe only the conflict case — the arm tells the operator
   "Sync encountered unresolvable conflicts. Local main is diverged — resolve manually
   with `git pull --rebase origin main`", which is false after a fetch failure (nothing
   conflicted, main is not diverged, and the suggested command fails identically).
   Notably, Requirement 4's own text lists "an auth failure, or network loss" among the
   modes to surface honestly — it fixed them at the behind-count step while the sibling
   failure one step earlier still renders as a conflict. Requirement 4's acceptance is
   explicitly narrow (a stubbed `rev-list`, a code ≠ 1 or 2, a diagnostic naming the
   behind-count step), all of which is met, so this is not an R4 miss — it is the next
   instance of the class.

## Requirements Drift

**State**: none

**Findings**: None. The rework adds no behavior the project requirements fail to
capture. `55d7ec87` narrows an existing lookup rather than adding a surface; `28d4e19f`
touches walkthrough prose only; `4f5d5fee` and `ae301a4e` are backlog and area-doc
content. Cycle 1's drift assessment against `cortex/requirements/project.md` is
unchanged and re-confirmed: the `cortex-morning-review-push-closures` console script
still matches the "Skill-helper modules" constraint, emits no new events, and honors
"Destructive operations preserve uncommitted state" (pathspec-limited commit, never a
forced push).

`cortex/requirements/pipeline.md` remains outside this drift check's declared scope
(the loader matched no area docs for this feature's tags). Follow-up 1 above is a stale
doc claim the implementation should arguably have corrected, not requirements the
implementation outran — so it is filed as a follow-up, consistent with cycle 1's
treatment of the same file.

**Update needed**: None

## Verdict

All four cycle-1 issues are genuinely fixed. The fixes introduced no new defects: the
resolver change is sound and additive with non-vacuous tests, the exit-3 arm and
catch-all are correct and mirrored, #395 carries its evidence without ruling, and the
`pipeline.md` correction matches the code. Suites and parity are green at the stated
baseline. The two items I found are pre-existing, out of scope, and belong in tickets
rather than in a human interrupt — nothing here must be fixed before this ships.

The one thing to carry forward is not a code issue: `28d4e19f` changed §6b's gate
semantics while presenting the change as an alignment with wording that never existed.
The edit is right, but it was a decision, and decisions should arrive labeled.

{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "none"}
