# cortex-pr-review Measurement 2: Fan-Out on Large Multi-Author PRs

Date: 2026-06-14

**Verdict: the fan-out did not earn its keep, even on its best case.** On three large multi-author public PRs graded against the real human-review answer key, System A's four-angle fan-out paid off on exactly one PR (cargo #17083), was marginal on a second (cli #13459), and added nothing the answer key rewarded on a third (svelte #18330); System B (the single high-effort pass) won consistency on all three and won quality on the svelte PR while losing it narrowly on the other two to a single A finding that surfaced in only one of three runs. Across both measurements the picture is now consistent: B is more reproducible and far cheaper to maintain, A's only repeatable edge comes from the prev-PR-comments angle (not the bug, history, or compliance critics), and that edge is intermittent and externally re-findable. The combined recommendation is **thin-shell-own**: collapse to one reviewer agent, keep the footer and no-autopost default, and keep a single optional prev-PR-comments fetch as on-demand context rather than a standing fan-out stage.

## Method and fidelity caveats

Three large multi-author PRs from major public repos were selected to stress exactly the case the first measurement could not test: PRs where four critic angles, git-history/blame, and a previous-PR-comments critic are most likely to pay off. Each PR has a human answer key extracted from the real merged review thread (9, 6, and 5 distinct issues respectively). Each PR was reviewed three times by System A (the bespoke five-stage pipeline) and three times by System B (a single high-effort single-pass reviewer), and scored on verdict stability, finding recurrence (in all 3 runs vs in only 1), answer-key recall, unique true positives per system, and false-positive load. Load-bearing answer-key hits were verified against merged code and follow-up PRs where possible (for example, cli #13459 answer-key #7 was confirmed against discovery.go line 400 in the merged tree plus the existence of follow-up PR #13568 "Fix root-level SKILL.md discovery" closing issue #13552).

Honest fidelity caveats, stated up front:

- **Remote repos reviewed via `gh`, not local clone.** Diffs and metadata came through the GitHub API rather than a working tree, so the git-history/blame angle is approximated (it reads what `gh` and the trees API expose, not a full local `git log --follow -p`/`git blame`). This understates the history critic's ceiling somewhat, but the history angle produced no answer-key hits on any PR even so.
- **Human-comment answer key is a proxy for "all real issues."** The answer key is what human reviewers actually raised in the thread, which is itself incomplete and biased toward what reviewers chose to comment on. A finding outside the key is not necessarily noise (A surfaced several real, externally verifiable issues that humans simply never raised), and the key over-weights items a reviewer happened to voice. Recall against this key measures alignment with human reviewers, not absolute correctness.
- **n=3 runs per cell.** Three runs make consistency indicative, not statistically tight. The decisive A finding on cli #13459 appearing in 1 of 3 runs is exactly the kind of signal that n=3 makes directional rather than firm, though it points the same direction as everything else.
- **Compliance critic inactive where no CLAUDE.md.** None of the three target repos ship a CLAUDE.md the compliance critic recognizes, so Agent 1 produced zero surfaced findings in all runs on all three PRs. This is dead cost on these repos by construction; it says nothing about repos that do ship one, but it does confirm the critic contributes nothing on the general open-source case.
- **Single-agent emulation of a multi-call pipeline.** As in measurement 1, A was driven by its protocol rather than a fully independent production deployment. The structural failure modes it self-reported (TMPDIR cross-PR contamination, sandbox TLS x509 failures forcing dangerouslyDisableSandbox, silent grounding drops on line-number drift) are real and traceable to the design; absolute rates are indicative.

## Results

Verdict stability was near-total: B was identical (3/3) on all three PRs; A was identical on cargo and svelte but **split** on cli #13459 (APPROVE / APPROVE / REQUEST_CHANGES). That single split is meaningful: it is the one PR where A's pipeline produced the best single review in the set, and it could not reproduce it.

| PR (answer-key size) | System | Verdict (3 runs) | In all 3 | In only 1 | Answer-key recall | Consistency winner | Quality winner | Fan-out paid off |
|---|---|---|---|---|---|---|---|---|
| cli/cli #13459 (9) | A | split (APP/APP/RC) | 1 | 3 | 1/9 (#7) | B | A (narrow) | marginal |
| cli/cli #13459 (9) | B | APPROVE x3 | 2 | 2 | 1/9 (#8) | | | |
| rust-lang/cargo #17083 (6) | A | APPROVE x3 | 1 | 9 | 3/6 (#2,#3,#5) | B | A (narrow) | yes |
| rust-lang/cargo #17083 (6) | B | APPROVE x3 | 2 | 4 | 2/6 (#2 weak,#5) | | | |
| sveltejs/svelte #18330 (5) | A | APPROVE x3 | 2 | 4 | 2/5 (#2,#3-partial) | B | B | no |
| sveltejs/svelte #18330 (5) | B | APPROVE x3 | 4 | 1 | 2/5 (#2,#3) | | | |

Axis tally: B wins consistency 3 of 3. B wins quality 1 of 3 outright (svelte) and loses 2 of 3 narrowly, where "loses" means A caught one higher-value answer-key item that appeared in a single run. Fan-out paid off cleanly on 1 of 3 (cargo), marginally on 1 (cli), and not at all on 1 (svelte).

A consistent pattern holds across all three: both systems correctly APPROVE the PRs that humans merged (no false blocking verdicts on either side, except A's one stray REQUEST_CHANGES on cli, which was arguably the correct call but unreproducible), and both systems miss the bulk of the human answer key (neither broke 3/6 on its best PR; both whiffed the entire test-hygiene cluster on cli and the central enum-removal design thread on cargo).

## The crux: every real issue one system found that the other missed, by critic angle

This is the decision evidence. The question is not raw recall (a wash or near-wash on every PR) but whether A's extra machinery surfaced **repeatable** true positives B structurally could not reach, often enough to justify its cost and documented failure modes.

### Issues A found that B missed

**cli/cli #13459:**
- **Answer-key #7, bare-SKILL.md / root-level SKILL.md regression** (BUG angle, run 3 only; CORROBORATED by prev-comments angle citing follow-up PR #13568 + issue #13552). This is the single highest-value item on the whole PR and the only finding that should have blocked the merge. B saw the exact code change in all 3 runs and actively dismissed it as "benign, errors either way," which is a real false negative. Verified against merged discovery.go (line 400 matches only `/SKILL.md`, so bare `SKILL.md` routes to full discovery, which lacks a root matcher) and against the existence of the one-day-later upstream fix. **This is A's signature win, but it surfaced in only 1 of 3 runs**, and runs 1 and 2 dropped it because A's own Stage 3.5 grounding silently erased the bug-class findings on line-number drift.
- **External-fix corroboration** (PREV-COMMENTS angle): the regression recurred as a separate fix (PR #13568). A single-pass diff read cannot surface that a change recurred as a one-day-later upstream fix. This is the clearest case in the set of the fan-out reaching something structurally unreachable from the diff.

**rust-lang/cargo #17083:**
- **Answer-key #3, design-direction tension** (PREV-COMMENTS angle, run 3): open PR #17012 (`-Zmin-publish-age`, RFC 3923) and the question of whether the yanked predicate should co-locate with a future publish-age predicate now or defer. B never referenced #17012 or any publish-age direction; structurally unreachable from the diff.
- **Answer-key #2 historical confirmation** (PREV-COMMENTS angle): follow-up PR #17092's maintainer "easy to misuse" discussion (`as_summary` -> `as_summary_unchecked`) validating the error-prone-API concern as a real, maintainer-acknowledged design risk. B touched the same accessor but only as a quality/dedup nit, not as the answer-key design risk.
- **yanked_whitelist removal as an intentional multi-PR series** and the removed-field load-bearing doc invariant (HISTORY angle). Real context, not an answer-key item, non-blocking.

**sveltejs/svelte #18330:**
- **Follow-up PR #18350 trailing-slash infinite-loop hang** in the same `find_matching_bracket` `/` branch (HISTORY + prev-comments). Real and externally verifiable, present in all 3 runs, but **not in the answer key** (humans never raised it; it was a separate PR).
- **Recurring-fix cluster #18282/#18321/#18324** and the **#18321 predecessor review comment** about `{type }` trailing whitespace (HISTORY + prev-comments). Real, verifiable, **off-answer-key context.**

### Issues B found that A missed

**cli/cli #13459:**
- **Answer-key #8, stale `matchHiddenDirConventions` doc comment** (single pass, run 2): B stated the doc-accuracy nit exactly (the code now matches any dot-prefixed segment via `hasHiddenSegment`, not a `.{host}` name). A only brushed the underlying matcher as a design question and never made the staleness point. Verified against merged discovery.go lines 475-486.

**rust-lang/cargo #17083:**
- **Answer-key #5, sharper grounded form**: `should_prefer` broadens yanked-keep to include `[patch]`/`prefer_patch_deps` matches beyond the old whitelist's lock-only set, a precise verified behavior-change observation (run 1) that A only gestured at generically.
- **errors.rs QueryKind discrimination** verified correct against base `RegistrySource::query` (run 3); **`is_yanked` rewrite** verified a literal no-op (run 2). Precise verifications A never performed.

**sveltejs/svelte #18330:**
- **Mechanistic grounding of the comment-reset (answer-key #3)**: B read acorn.js `add_comments` and proved *why* truncating to `initial_comment_count` is correct (local-copy reassignment). A only mentioned the reset existed.
- **Empirical old-vs-new bracket-logic simulation** in Node across division/regex/multiline/unterminated-EOF plus a 1M-iteration loop guard, resolving the exact infinite-loop concern A raised only as an open question.
- **Verified `match_regex` does not advance `parser.index`** and `/type\b/` excludes `typeof`/`typescript`/`types`. Concrete correctness verification A never did.

### What the crux shows

The only critic angle that produced repeatable, answer-key-rewarded true positives B could not reach is **prev-PR-comments**, and it did so on 2 of 3 PRs (cli #7 corroboration, cargo #3 and #2). The **bug critic** produced A's one decisive cli finding but only in 1 of 3 runs and was its weakest contributor on svelte (repeatedly surfacing findings on reverted/dead code that synthesis had to drop). The **history critic** produced real off-answer-key context on every PR but zero answer-key hits and, via `gh`, runs approximated. The **compliance critic** produced zero surfaced findings on all three PRs (no CLAUDE.md). Meanwhile, B repeatedly did something A's fan-out did not: it *resolved* the questions A only *raised*, by cloning the repo, enumerating all 217 call sites, simulating the bracket logic, and reading acorn.js. B's edge is depth of grounding on a single pass; A's edge is breadth of context from one of four angles, intermittently, at roughly 4x the cost plus documented integrity failures.

## Combined decision across both measurements

**Final recommendation: thin-shell-own.** Collapse the orchestration to one high-effort reviewer agent. Keep exactly two things that no external single-pass tool reproduces and that this measurement did not impeach: the observability footer (dropped-findings visibility) and the no-autopost-default terminal-first behavior. Add one optional, on-demand prev-PR-comments / follow-up-PR fetch the single agent can run when a PR is large or multi-author, rather than as a standing fan-out stage. Do not keep the four-way critic fan-out, the Haiku triage, the standing git-history stage, or the compliance critic as standing components.

This stops short of **pure-buy-codereview** for one reason the data supports: the prev-PR-comments angle is the single capability that repeatably surfaced real answer-key issues a single diff pass cannot reach (cli #7's external corroboration, cargo #3), and the footer plus no-autopost default are genuine owner-valued differentiators bundled `/code-review` does not give for free. It stops short of **keep-some-critics** (in the plural, fan-out sense) because the fan-out as a structure did not earn its keep: it paid off cleanly on 1 of 3 best-case PRs, the payoff came from 1 of 4 angles, the other three angles were dead or marginal cost, the pipeline self-reported real integrity failures on the very PR where it produced its best review, and even on its signature win the decisive finding was unreproducible (1 of 3 runs) because A's own grounding stage erased it.

What to build:
- One high-effort single-pass reviewer agent that investigates the codebase to ground each finding (the depth move that won B the svelte PR and the grounded forms of cargo #5).
- The dropped-findings footer as a thin output layer.
- One optional prev-PR-comments / follow-up-PR context fetch, invoked on demand for large or multi-author PRs, feeding the single reviewer. This preserves the one angle with a demonstrated repeatable answer-key edge without paying for a four-way standing fan-out.

What to delete:
- The four-way critic fan-out as a standing structure.
- The Haiku triage stage (identity-work in measurement 1; nothing here changes that).
- The standing git-history `-p` firehose stage (real context, zero answer-key hits, worst cost/value ratio).
- The standing compliance critic (zero surfaced findings on all three open-source PRs; demote to "read CLAUDE.md if present" inside the single agent).
- The bug critic as a separate diff-only critic (its prompt hobbles it; fold defect-hunting into the single full-context reviewer, which on svelte resolved what the isolated bug critic only flailed at).
- Re-evaluate the grounder per measurement 1: it actively dropped A's single best finding on cli #13459 (line-number drift on the bug-class findings in runs 1 and 2), which is direct new evidence for the "delete evidence-ground.sh and ground in-context" branch. Keep it only if a calibration run shows a measured precision edge over in-context grounding AND the visible-drops/slack fixes land.

**Confidence: medium-high.** Both measurements now point the same direction across six PRs (three solo, three large multi-author) and 36 runs: B is more consistent everywhere and at least as good on quality except where A caught one higher-value item in a single run. The best-case test for the fan-out came back marginal-to-negative. It is held below high by the same structural caveats: n=3, the human-comment answer key is an imperfect proxy, the history critic was approximated through `gh` rather than a local clone, and the compliance critic was untestable on repos with no CLAUDE.md.

What would still change the answer:
- A repo that ships a CLAUDE.md plus a thick prev-PR-comment culture, where the compliance and prev-comments critics could both pay off on the same PR, measured with a local clone so the history angle runs at full fidelity.
- Evidence that the prev-PR-comments edge generalizes (more than the 2-of-3 hit rate seen here) and is cheaper to keep as a standing stage than as the proposed on-demand fetch.
- A natural-bug fixture set where A's full fan-out reproducibly (3 of 3, not 1 of 3) catches blocking defects B's single pass misses. The cli #7 result is the closest evidence for this and it failed the reproducibility bar.
- Proof that A's grounding drops and TMPDIR contamination are cheap one-line fixes rather than intrinsic, which would re-open keeping a fixed grounder but not, on this data, the five-stage fan-out structure.
