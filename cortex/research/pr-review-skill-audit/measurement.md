# cortex-pr-review Measurement: Bespoke Pipeline (A) vs Single-Pass Reviewer (B)

Date: 2026-06-14

**Verdict: A is not better than B.** Across 3 PRs run 3 times each, the 5-stage pipeline (System A) never beat a single high-effort reviewer (System B) on either consistency or quality, won zero of the six per-PR axis comparisons, and on two of three PRs was strictly worse. Applying the rubric's own ship/block gate to this head-to-head, the result is **block**: A is no better than B on consistency AND quality, and a tie there breaks toward B because B is far less to maintain. This firms up the prior HYBRID recommendation and pushes it harder toward the simple end of the spectrum: the measurement that was missing now exists, it says the bespoke machinery buys variance rather than reliability, and the honest next step is to collapse to a single reviewer and treat the grounder/footer as the only candidates for keeping.

## Method and fidelity caveats

Three fixture PRs were selected to exercise distinct review modes: a nits PR (#16, a bare-relative skill path plus L1-surface overage), a bug PR (#20 with an injected inverted-guard defect), and a refactor PR (#17, a clean pure-deletion subsystem retirement). Each PR was reviewed three times by System A (the current bespoke pipeline) and three times by System B (a single high-effort single-pass reviewer), for 18 runs total. For each run I recorded the Verdict, the full finding set, ground-truth recall, and false positives. Per-PR consistency was scored on how many findings recurred in all 3 runs versus appeared in only 1 run; quality was scored on ground-truth capture, signal-to-noise, and restraint (not manufacturing blocking issues on clean diffs). Load-bearing claims were verified against repo state where possible: the PR-16 ground-truth nit was confirmed against history (shipped in commit 87a72635 at SKILL.md line 14, fixed in 8a891967), and the project's own lint (`cortex_command.lint.skill_path.scan_text`) was run against the exact fixture content and returns exactly one violation, SP002 at 14:7.

Honest fidelity caveats, stated up front so the conclusion is not over-read:

- **Single-agent emulation of a multi-call pipeline.** System A was exercised by driving its protocol rather than through a fully independent production deployment of all five stages. The structural failure modes it exhibited (grounding drops, temp-file collisions, rubric label drift) are real and traceable to the design, but the absolute drop rates are indicative, not a production telemetry sample.
- **Small, solo repo.** All three fixtures are single-author cortex-command PRs. A's four-angle critic split and prev-PR-comments critic are exactly the components most likely to pay off on large multi-author PRs, and none of these fixtures stress that case. This measurement does not refute the possibility that A's fan-out earns its keep on a different repo shape; it only shows it does not earn it here.
- **One injected bug, not a natural one.** The bug PR uses a deliberately injected inverted-guard defect. Injected bugs are cleaner and more locatable than wild ones, which flatters both systems' recall and compresses the gap between them.
- **n=3 runs per cell.** Three runs make consistency indicative, not statistically tight. A single anomalous run moves the in-all-3 / in-only-1 counts materially. The verdict-stability signal (3/3 on every PR for both systems) is robust at this n; the finding-recurrence signal should be read as directional.

## Results

Verdict stability was 3/3 identical for both systems on all three PRs. No drift on either side. With verdict tied everywhere, the decision rests entirely on findings.

| PR (category) | System | Verdict (3 runs) | Findings in all 3 | Findings in only 1 | Ground-truth recall | Consistency winner | Quality winner |
|---|---|---|---|---|---|---|---|
| #16 (nits) | A | REQUEST_CHANGES x3 | 1 | 4 | partial | B | B |
| #16 (nits) | B | REQUEST_CHANGES x3 | 4 | 0 | yes | | |
| #20 (bug) | A | REQUEST_CHANGES x3 | 3 | 0 | yes | tie | B |
| #20 (bug) | B | REQUEST_CHANGES x3 | 3 | 0 | yes | | |
| #17 (refactor) | A | APPROVE x3 | 0 | 4 | n/a | B | B |
| #17 (refactor) | B | APPROVE x3 | 2 | 3 | n/a | | |

Axis tally: B wins consistency on 2 of 3 PRs and ties the third; B wins quality on 3 of 3 PRs. A wins zero axes outright.

## What the numbers say

**Consistency: B wins or ties, never loses.** On the bug PR both systems were rock-solid: same 3 findings in all 3 runs, 0 one-run-only findings, bug caught every time. That is the case the bespoke pipeline should win, and it only managed a tie. On the other two PRs B was clearly more stable. For the nits PR, B surfaced 4 findings in all 3 runs (canonical bare path, mirror bare path, the 758B L1-surface overage, and the specify.md single-sourcing praise) with only one minor artifact nit varying; A surfaced just 1 finding in all 3 runs and scattered its other 4 across single runs. For the refactor PR the gap is starkest: A surfaced **zero** findings in all 3 runs and every one of its 4 distinct findings was one-run-only, while B held 2 findings stable across all runs with only well-disclaimed context notes varying.

**Quality and recall: B wins all three.** B caught the ground-truth defect on the nits PR in every run with correct SP002 grounding (14:7) and correctly distinguished legitimate prose cross-references from bare Read directives. On the bug PR, B traced the inverted guard to the specific named tests it breaks (including a `compute_aggregates` cross-check that A never mentioned) and validated the correct half of the diff as a true-positive praise, showing discriminating judgment rather than noise. On the refactor PR, B actually ran the targeted test suite (`uv run pytest`) and `--help` to ground its APPROVE, and disclaimed every peripheral note as not attributable to the diff. A's recall was weaker exactly where it mattered most: on the nits PR it caught the ground-truth defect in only 2 of 3 runs, and in one of those it demoted the real nit to a low-confidence "question" on a verifiably false premise that the lint does not flag the path. A live lint run disproves that premise.

**Standout observation: A's own machinery was the liability.** This is the load-bearing finding for the keep-vs-buy call. A's extra stages did not buy reliability; they introduced documented, machinery-driven failure:

- On the refactor PR, A's grounding layer non-deterministically dropped correctly-quoted findings because of a diff-line-vs-post-image coordinate ambiguity on a deletion-heavy diff (dropped_count varied 5/5/2), and a shared-`$TMPDIR` fixed-filename collision cross-contaminated runs so one run ingested another PR's findings. The most valuable refactor finding (the registry repoint, which B caught every time) survived in only 1 of 3 A runs.
- On the bug PR, A's run 1 reported a self-described line-anchoring error that silently dropped a true finding (dropped_count=1) while runs 2-3 dropped nothing.
- On the nits PR, A's grounding/routing logic is what demoted the real ground-truth nit to a question on a false "lint doesn't fire" premise, and another run dropped the defect entirely.

So the components meant to make findings more consistent and better-grounded are the components observed manufacturing variance and one outright false premise.

**Where A did add real signal.** The measurement is not one-sided. A's git-history critic surfaced genuine context B never produced: on the bug PR it noted the inline fold re-implements logic that commit 66ef32d7 had already delegated to shared core, and on the nits PR it caught a missing `_BASELINES` row and a fixture-replay-against-merged-main observation. A's secondary claims that were checkable (758B L1 surface, 361B baseline, the missing baseline row) all verified accurate, and A honestly disclosed its own concurrency footgun and grounding drops in its execution notes. The problem is not that A produces nothing unique; it is that the unique payoff is one git-history finding per PR, offset by redundancy (findings orbiting one fact), silent true-positive drops, and execution notes dominated by harness-friction meta-commentary rather than PR signal. B matched or beat A on every primary axis with a fraction of the machinery and none of the documented failure modes.

## Decision update

This measurement confirms and strengthens the prior HYBRID recommendation, and it removes the single caveat that was holding the prior call at MEDIUM confidence. The prior audit explicitly leaned hybrid "leaning hard toward a major cut" but conceded that the decisive number, whether the bespoke pipeline is actually less consistent than a single pass, had never been measured. It now has been. The answer is that the bespoke pipeline is not more consistent and not higher quality than a single pass on this repo; on two of three PRs it is worse, and its extra stages are the proximate cause of the inconsistency.

Applying the rubric's own ship/block gate, interpreted for this head-to-head, the call is **block** (collapse toward single-pass): A is no better than B on consistency AND quality, and the tie on the bug PR breaks toward B on maintenance cost. The rubric's underlying ship condition (the rewrite must be more consistent than the status quo) cannot be claimed for A, and its block condition (no better than the simpler comparator) is met.

Recommended next step: proceed with the hybrid rewrite as specified, but bias every open design choice toward the simple pole. Collapse the orchestration to one high-effort reviewer agent now rather than treating that as a fallback. Carry forward only the two candidate differentiators (provable evidence grounding and the dropped-findings footer), and treat even the grounder as on-probation: this measurement showed its grounding stage actively dropping real findings and contaminating runs, which is direct evidence for the prior audit's "consider deleting evidence-ground.sh entirely and ground in-context" branch. Before keeping the grounder, require a measured precision edge over in-context grounding plus the visible-drops and coordinate fixes the prior audit named.

**Confidence: medium-high**, up from the prior medium. The verdict-stability signal is robust at this n, the quality and recall gap favoring B is consistent across all three PRs and all run triplets, and the ground-truth and lint claims were verified against repo state. It is held back from high by the three fidelity caveats: n=3, a single solo repo, and an injected bug.

What would still change the answer: a re-run on large multi-author PRs where A's four-angle fan-out or prev-PR-comments critic could pay off (the one repo shape these fixtures do not test); a natural-bug fixture set showing A's critics catch defects B's single pass misses; or evidence that A's grounding drops and temp-file collisions are cheap one-line fixes rather than intrinsic, which would re-open keeping a fixed grounder but would not, on this data, re-open keeping the five-stage structure.
