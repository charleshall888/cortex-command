# Research: A rework re-review re-reads the whole spec with no way to scope it

Ticket #455 · tier `complex` · criticality `high` · lifecycle `a-rework-re-review-re-reads`

**Clarified intent.** Make a rework re-review a supported mode that reads the rework diff against the
previous cycle's issue list instead of re-reading the whole spec — across *both* review specifications
(the interactive skill reference and the overnight prompt/dispatcher) — without letting the scoping
shrink what the reviewer is allowed to conclude.

**Scope decisions taken at Clarify** (operator): both surfaces in scope; restructure rather than append;
the missing-artifact robustness gap split out to **#457**. The ticket body's Edges bullet 5 ("adjacent
robustness gap worth folding in") is therefore **superseded** — it is out of scope here.

---

## Codebase

### The ticket's central premise is false, and the correct discriminant already exists

`cortex_command/common.py:355` computes `cycle = review_verdict_count if review_verdict_count > 0 else 1`
— the count of **completed** `review_verdict` events. At entry to review cycle 1 that is 1 (zero verdicts);
at entry to review cycle 2 it is **also 1** (one verdict). The served `cycle` collapses the two cases at
exactly the moment a review mode must be chosen. The ticket's touch point — "`cortex-lifecycle-next`
already serves `cycle` in its `evidence_trace`, so the discriminant exists" — does not hold at dispatch
time.

It is also **display-only**. The rework cap's real authority is the reviewer's *self-reported* cycle,
threaded as `cortex-lifecycle-advance review-verdict --cycle` → `_route_target` (`review_verdict.py:161`)
→ transition-table guards (`transition_table.py:356-358` cycle==1 → rework, `:369-371` cycle>=2 →
escalated). Nothing routes on `common.py:355`.

**The correct discriminant is already built and CLI-exposed**: `count_rework_cycles`
(`cortex_command/lifecycle/counters.py:53`) counts `CHANGES_REQUESTED` verdicts only. `rework_cycles >= 1`
is a correct binary "this is a rework re-review" test with no off-by-one, served by
`cortex-lifecycle-counters`.

**Do not touch `common.py:355`.** It has five golden-pinned display consumers (`state_cli.py`,
`claude/statusline.sh`, `dashboard/data.py`, `scan_lifecycle.py:970`, `generate_index.py`) and
`tests/test_lifecycle_auto_advance.py:126-145` (`test_cycle_2_changes_requested_escalates`) pins the
count semantics explicitly — it seeds two CHANGES_REQUESTED events and asserts `cycle == 2`. Redefining
:355 to "the cycle about to run" flips that assertion to 3 for zero routing benefit.

Note a **stale docstring** at `common.py:462-463`, which still claims `cycle` is "the count of `verdict`
regex matches in review.md" — the implementation counts events (the migration is explained at :308-309).
Worth correcting opportunistically; nothing depends on the stale reading.

### Overnight needs no new discriminant at all

`dispatch_review()` already branches in Python: cycle-1 dispatch at `review_dispatch.py:378-388`, cycle-2
at `:625-636`. The cycle-2 branch at `:596-609` reloads the **identical** cycle-1 template and appends one
sentence ("Focus on whether the flagged issues were resolved") **without passing the `issues` array** —
even though `issues` is a local in scope at that point (populated at `:401`) and is already injected into
the *fix* agent's prompt at `:499`. `prompts/review.md:96`'s worked example also hardcodes `{"cycle": 1}`,
so a cycle-2 reviewer copying the example self-reports the wrong cycle.

### The prior cycle's issues have no durable store, on either path

- The `review_verdict` events.log row carries only `verdict` / `cycle` / `requirements_drift`
  (`advance.py:436`, `review_verdict.py:207-219`). **No `issues` field, ever.**
- `review.md` is one unversioned path the next cycle overwrites (`review_dispatch.py:324`).
- `orchestrator-note.md` is overnight-only, `write_text` not append (`review_dispatch.py:481-486`), and
  shares its path with an unrelated deferral-Q&A flow that deletes it
  (`overnight/prompts/orchestrator-round.md:62,88,109`) — a latent collision.
- `stage_artifacts.py` uses an **explicit allowlist, never a directory glob** (module docstring :4-6, :31),
  staging `{research,spec,plan,review,index}.md`, and there is **no `--phase review`** — review artifacts
  stage at `--phase complete`. So cycle-1's `review.md` is already overwritten before it is ever committed:
  **cycle-1 reviews are not in git history at all today.**

Confirmed on the real artifact: the provenance run's events.log contains two `review_verdict` rows with no
issues, and the on-disk `review.md` is the cycle-2 file.

### Byte budget — zero headroom

Measured with the enforcement code itself (`scripts/ratchet_refs.py`):

```
skills/build/references/  measured=57964  pin=57964  headroom=0
```

`measure()` counts **all regular files**, not just `.md` — including `kept-pauses-data.toml` (7584),
`protocol-expectation.txt` (1334), `_interactive_overnight_check.sh` (2235). Any added byte fails
`tests/test_reference_size_ratchet.py`. A brand-new situational reference file in that directory is
equally rejected — there is no free byte by any reference-file route.

`review.md` is 5374 bytes; its §2 (dispatch) is 2099 of them, mostly **output-shape prescription** (drift
section format, Verdict JSON schema, stage definitions) that is re-read on 100% of reviews.

`cortex_command/pipeline/prompts/` has **no** `size-pin.txt` — the overnight template is unmeasured.

### Prior art for mode-switching

`plan.md:13` + `competing-plans.md` is the existing pattern: a separate reference read conditionally on an
arm. **Not usable here** — a new file costs its full size against a zero budget. In
`cortex_command/pipeline/prompts/` there is no template-variation prior art at all: two files, pure
`{placeholder}` `.replace()` substitution (`review_dispatch.py:219-251`).

---

## Web

Two directly usable precedents, and one honest gap.

- **CodeRabbit** ships this as a named two-mode split: `@coderabbitai review` = incremental, new changes
  only; `@coderabbitai full review` = from scratch. Validates making the mode explicit and nameable rather
  than implicit. Thread-resolution state is its carry-forward mechanism.
- **Cloudflare's internal AI reviewer** ([blog](https://blog.cloudflare.com/ai-code-review/)) is the closest
  match to the hard part. On re-review the coordinator is fed **its own prior review text plus every prior
  finding with its resolution status**. Fixed issues are silently omitted and auto-resolved; unfixed ones
  re-emitted verbatim to preserve continuity; user-resolved ones respected *unless materially worsened*.
  This is a working answer to the ticket's "keep their rating by reference" requirement — and note it feeds
  the **whole prior review**, not a bare issue list, which is what structurally permits noticing things
  outside scope.
- **Gerrit `copyCondition`** is the structural precedent worth stealing: a prior vote carries forward only
  while a **declared** condition holds, and when it breaks the vote is explicitly marked *outdated* rather
  than going quietly stale. Maps directly onto "unchanged since cycle 1, not re-read".
- **Reviewable.io** tracks (reviewer × file × revision) seen-state independent of git history shape, and
  hides rebase/whitespace-only deltas — the delta model to imitate if this ever needs to survive rebases.
- **Negative data point**: Qodo/PR-Agent shipped naive re-review and got duplicate-suggestion spam until
  dedup was built ([issue #2184](https://github.com/qodo-ai/pr-agent/issues/2184)). That is the default
  failure mode if carry-forward isn't designed.
- **Test-selection**: Azure DevOps Test Impact Analysis is the canonical shape — dependency map per test,
  select on intersection with changed files, **safety fallback to the full suite on unrecognized input**,
  plus forced periodic full runs to catch map drift. The fallback and the periodic full run are the parts
  worth copying.

**The gap**: no vendor documents a mechanism for escalating on problems *outside* the original issue list.
The ticket's Edge 1 is not solved prior art anywhere — it is something this design has to invent.

---

## Requirements & Constraints

### Binding

- **ADR-0009** (accepted) — skill path resolution; no reference region reaching a subagent may carry a raw
  `${CLAUDE_SKILL_DIR}` token. Binds any `review.md` edit that composes a reviewer prompt.
- **ADR-0015** (accepted) — could-not-run vs dispatch-crash split and the `review_no_artifact` cause class.
  Its `DispatchResult.success` / positive `could_not_run` discriminants are load-bearing for the systemic
  breaker and must not move.
- **`project.md` Deletion bias** — an efficiency-framed ticket must state its expected net effect on the
  surface it claims to shrink. See the measurement below; this is the clause the shape is answering.
- **`project.md` Token economy** — cost is turns × context; levers are session length, turn count, fan-out.
- **CLAUDE.md** — `cortex_command/common.py` is explicitly lifecycle-gated (we are in one).
  `cortex_command/pipeline/**` is *not* named in that clause: a governance asymmetry between the two
  surfaces this ticket spans.

Proposed-status ADRs (**SHOULD surface, not binding**): 0018 (structural over prose-only), 0020 (event
emission contract — a new field must fit the uniform `--set`/`--set-json` shape), 0024 (served directives
gate only on machine-readable state, never judgment), 0025 (`cycle` is explicitly carved out as an
artifact-derived read-side fact, not events-derived state).

### The requirements loader silently skipped the most relevant area doc

`cortex-load-requirements` reported *no area docs matched* for tags `[lifecycle, review, rework, cost]` and
fell back to `project.md` + `glossary.md`. The matcher is correct: it tests the feature's `index.md` tags
against the trigger strings in `project.md`'s `## Conditional Loading` (`:96-101`), and no area doc carries
tag frontmatter at all. But the trigger for `pipeline.md` is `pipeline/overnight runner/conflict
resolution/deferral` — it contains neither "review" nor "rework", so **`cortex/requirements/pipeline.md`
§ Post-Merge Review was skipped**, and that section is squarely this ticket's domain. Read manually; its
content is folded in below. There is also **no `cortex/requirements/lifecycle.md`** despite the ticket
carrying `areas: ['lifecycle']`.

This will silently skip `pipeline.md` for *every* review- or lifecycle-tagged ticket. Filed as a finding,
not fixed here — see Open Questions.

### What pipeline.md § Post-Merge Review actually specifies

- The overnight loop is a **2-cycle** rework loop: CHANGES_REQUESTED cycle 1 → `orchestrator-note.md` →
  fix agent → SHA circuit breaker → re-merge → cycle 2 review.
- **Non-APPROVED after cycle 2 → feature status `deferred`** with a deferral file for morning triage.
  Overnight **defers**; interactive **escalates** (`review_verdict.py:163`). The two paths diverge at
  exactly the outcome this ticket touches, and that divergence is deliberate — do not unify it.

### Enforcement gates this change must clear

`tests/test_reference_size_ratchet.py` (zero headroom), `test_dual_source_reference_parity.py` and
`test_plugin_mirror_parity.py` (mirrors), `test_check_skill_path.py` (SP001/SP002),
`test_lifecycle_kept_pauses_parity.py` (if any `<!-- pause: -->` marker moves),
`test_lifecycle_reverse_golden.py` (any events.log row shape change),
`test_lifecycle_phase_parity.py`, `test_transition_table.py` (closure/completeness — the test that would
have caught #433), `test_transition_table_describe_parity.py` (`docs/lifecycle-transition-table.md` is
generated, never hand-edited).

---

## Tradeoffs & Alternatives

### Measured net effect — the Deletion-bias answer

Rework frequency, counted from `review_verdict` rows across five repos' lifecycle corpora:

| repo | reviewed lifecycles | ran a re-review | rate | max cycle |
|---|---|---|---|---|
| cortex-command | 275 | 19 | 7% | 2 |
| wild-light | 217 | 37 | 17% | 3 |
| gaggimate-barista | 8 | 0 | 0% | 1 |
| pixel-art-generator | 10 | 0 | 0% | 1 |
| Team-Builder-Bot | 1 | 0 | 0% | 1 |
| **total** | **511** | **56** | **11%** | **3** |

**The scoped mode fires on 7–17% of reviewed lifecycles; any prose describing it is read on 100% of
reviews.** That ratio is the decisive argument against a prose branch and for a verb — and it is the net-
effect statement the front-door bar requires.

### The resolved shape

1. **Discriminant** — `rework_cycles >= 1` via the existing `cortex-lifecycle-counters`. Zero new plumbing.
   `common.py:355` untouched. Overnight needs nothing: it already branches structurally.
2. **One verb emits the reviewer brief for *both* modes**, mode-selected on the discriminant; called as a
   bash step from `review.md` §2 and imported in-process by `review_dispatch.py`. One implementation, two
   consumers, no duplicated rule. This is what makes the byte budget work: §2's ~2099 bytes of output-shape
   prescription move out of always-read prose into verb-emitted text, so the swap can go net-negative.
   It also closes a perverse incentive — `cortex_command/pipeline/prompts/` is unratcheted, so an
   implementer under ratchet pressure could otherwise "solve" the interactive side by pushing the branch
   logic into the one place nobody counts bytes.
3. **Durable prior-cycle store — a sidecar file, not an events.log row.** On writing cycle N's review,
   first move the existing `review.md` to `review-cycle-{N-1}.md`; the current cycle stays at `review.md`
   (phase detection requires it — `common.py:390-410` reads `verdict_matches[-1]`, and `_stat_key(review.md)`
   at `:467` is part of the memoization key). Requires extending `stage_artifacts.py`'s allowlist, or the
   archive is never committed. Preserves the *whole* prior review, matching the Cloudflare precedent.
4. **By-reference carry-forward stays in Stage-1 prose**, e.g. `**Verdict**: PASS (unchanged since cycle 1,
   not re-read)`. `review.md` §3 states downstream parsing depends only on the Verdict JSON block; nothing
   reads below verdict granularity, so a schema field would be dead weight. Borrow Gerrit's discipline:
   state the *condition* under which the carry-forward holds, so a broken condition reads as outdated
   rather than stale.
5. **Test-baseline re-run rule** — re-run iff `git diff <before_sha>..<after_sha> --name-only` touches any
   path outside `cortex/lifecycle/**`. The SHA pair already exists at `review_dispatch.py:489-495` for the
   circuit breaker; interactive needs the equivalent capture. Corroborated by the provenance run, where the
   reviewer improvised exactly this rule by hand.
6. **#454 sequencing** — not a hard dependency, but land it before or alongside the interactive-path work.
   Confirmed that #454's dead end is **interactive-only** (overnight defers to morning triage, a separate
   working mechanism). A scoped reviewer told to escalate genuine new problems will hit `escalated` more
   often, i.e. drive traffic straight into #454's gap.

### Two rejected alternatives, and why

- **Add `issues` to the `review_verdict` events.log row** — rejected twice over. (a) Measured: the
  provenance run's issues array is **5,672 bytes** against a whole events.log of **7,056** — ~80% growth in
  one line, and events.log is `json.loads`-parsed per line on every phase detection, statusline render,
  dashboard poll and hook. (b) `overnight/advance_lifecycle.py:140-155` `_has_real_review_verdict` treats
  **any** `review_verdict` row with integer `cycle >= 1` as proof the feature was reviewed, and morning
  crash-recovery synthesizes an APPROVED completion from it. Overnight deliberately writes **no** verdict
  row on CHANGES_REQUESTED for exactly this reason (`review_dispatch.py:458-465`, `FOLD (374)`). Emitting
  one would make a crash mid-rework complete a rejected feature as APPROVED.
- **A separate `review_issues {cycle, issues}` event** — dodges the crash-recovery hazard but not the size
  one. 5,672 bytes costs the same under any event name. Rejected.

---

## Adversarial

The dispatched adversarial agent returned late, in two rounds; round 2 withdrew two of its own round-1
findings after the design was revised to keep the current cycle at `review.md`. Its surviving findings are
folded in below alongside the orchestrator-verified ones.

**From the adversarial pass** (each verified before acceptance):

- **The verb becomes a single point of failure for the safety-critical part of the contract.** Moving §2's
  output-shape prescription out of prose is what funds the byte budget — but the Verdict JSON schema that
  `parse_verdict` requires (`review_dispatch.py:202`) would then exist only behind a subprocess call. The
  wheel and the plugin are versioned separately, so "plugin newer than the installed wheel" is a real state.
  **Resolution: the Verdict JSON block stays in prose as a backstop; only the narrative moves** (spec req 12,
  19).
- **An empty checklist is indistinguishable from "the prior cycle found nothing."** `parse_verdict`'s failure
  sentinel is `{"verdict": "ERROR", "cycle": 0, "issues": []}` (`review_dispatch.py:177`). A verb inheriting
  that pattern hands a reviewer an empty checklist with no signal to widen. **Resolution: fail open to a full
  review, with a degraded return distinguishable from a legitimately empty list** (spec req 19).
- **The test-baseline rule had a proven false negative.** `tests/test_clarify_critic_alignment_integration.py`
  `::test_post_migration_clarify_critic_events_are_jsonl` walks the **real** `cortex/lifecycle/*/events.log`
  tree and asserts format compliance — verified by reading it. So a rework confined to `cortex/lifecycle/**`
  can turn a live test red, and that is exactly the directory this feature adds machinery to. **Resolution:
  narrow the exemption to `cortex/lifecycle/{feature}/*.md`; `events.log` is not exempt** (spec req 11).
- **Rename opens a crash window that does not exist today.** Between move and rewrite, `review.md` is absent
  and phase detection falls through to the plan-based step, reporting `review` instead of `implement-rework`.
  Retry then hits `FileNotFoundError`. **Resolution: copy, never move; no-clobber on an existing archive**
  (spec reqs 1, 2).
- **Carry-forward is prose-only enforcement of a sequential gate**, which CLAUDE.md says to avoid where
  deviation is not cheap — and nothing bounded its depth, so a cycle-3 review could carry a cycle-2
  carry-forward of a cycle-1 rating and never re-read the line item. **Resolution: carry forward once; a
  second consecutive carry must be re-verified** (spec req 10).
- **Overnight does not need the file format at all** — it holds the prior issues in process at
  `review_dispatch.py:401`. Only the interactive path lacks cross-session memory. **Resolution: the archive is
  scoped as an interactive-path need** (spec req 1).
- **The deletion-bias case against building this**, stated at its strongest: a new verb, a new artifact class,
  new carry-forward prose and a new diff heuristic, to save a spec re-read on ~1-in-9 review cycles that
  overnight already caps at two. Surfaced to the operator at approval rather than resolved here.
- **#454 is understated as "not a hard blocker."** Partially accepted: escalation is the interactive path's
  only channel for a genuine out-of-checklist finding, so the ticket's own anti-rubber-stamp precondition
  leans on it. Judged non-blocking because escalation *works* and halts with findings presented — the corpus
  shows two operators resolving it out-of-band — but recorded as a reason to hold Phase 3 if #454 slips.

**Orchestrator-verified:**

- **A frame trap that produced a wrong conclusion mid-research.** One lifecycle appeared to show the
  cycle>=2 rework cap failing to fire (`review->implement` after a cycle-2 CHANGES_REQUESTED). It is from
  **2026-03-19**, pre-schema (`schema_version: None`), using a transition name the current protocol does
  not emit. Different era, not a live bug. Both *modern* cases (2026-07-22, 2026-08-03) routed
  `review->escalated` correctly. **Time-anchor any corpus claim before believing it.**
- **The escalation corner is asserted, not solved.** The shape preserves "scoping governs where it reads,
  never what it may conclude" by *telling* the reviewer so. Nothing enforces it, and no prior art anywhere
  implements it (see Web). The provenance run shows a good reviewer honoring it unprompted — that is
  evidence it is achievable, not that it is reliable. This is the single weakest point in the design.
- **Version skew is a new failure mode this shape introduces.** Today the prose owns the output shape, so a
  stale wheel cannot change what the reviewer is told. Once the brief comes from a verb, a stale wheel emits
  a stale brief. The existing mechanism covers it — `PROTOCOL_VERSION` (`lifecycle/protocol.py`) range-
  checked against `protocol-expectation.txt` (currently `min=3,max=3`) — but the brief's shape must be
  declared protocol-governed, and a shape change is a floor bump. Note `cortex-*` on PATH is the **released
  wheel**, not the working tree; verify wheel-side fixes with `uv run python -m …` or read a false negative.
- **The net-negative byte claim is an assumption, not a result.** The verb absorbs the brief's content, but
  prose still gains control flow (the branch, the verb call, the by-reference convention, the baseline rule).
  Naively that lands ~400–550 bytes positive against a zero budget. The §2 restructure is what pays for it,
  and that must be *measured*, not asserted — see the acceptance criterion in Open Questions.
- **The archive file has a silent-failure mode.** `stage_artifacts.py`'s allowlist is explicit; a
  `review-cycle-N.md` that is not added to it exists locally, never enters git, and is invisible to a fresh
  session or an overnight worktree — the feature would appear to work interactively and silently do nothing
  where it matters most.
- **Idempotency of the archive step.** Raised as unspecified; **resolved** by switching from move to
  copy-with-no-clobber, which converges on retry without needing to distinguish "archive already taken" from
  "cycle-N write never completed". The events.log emission machinery is idempotent by design
  (`_event_exists` cycle-qualified presence checks); a file operation is not, so this needed stating.
- **Trust boundary.** The prior cycle's `issues` array is free text written by a previous agent and fed to
  the next as a checklist. It is same-trust-domain (our own reviewer, our own repo) so this is not an
  injection vector in the usual sense, but it *is* an unbounded-length field being spliced into a prompt —
  the 5,672-byte measurement is the reason to bound it.

---

## Open Questions

1. **Does the §2 restructure actually go net-negative?** *Deferred to Spec as a measured acceptance
   criterion rather than resolved here*: post-edit, `ratchet_refs.measure(skills/build/references/)` must be
   `<= 57964` with no new `# raised:` line. Checkable in one command, so it cannot be hand-waved at review.
2. **How is "the reviewer may still conclude anything" enforced rather than asserted?** Unresolved, and
   named above as the design's weakest point. No prior art exists to copy. *Deferred to Spec* — it needs a
   design decision, and possibly an explicit "out-of-scope findings" section in the output shape so that
   escalating outside the checklist has somewhere to go.
3. **Should the requirements-loader trigger gap be fixed here or separately?** `project.md:97`'s trigger
   vocabulary lacks "review"/"rework", silently skipping `pipeline.md` for every review-tagged ticket.
   *Recommendation: separate ticket* — it is a one-line requirements edit that affects every lifecycle, not
   just this one, and bundling it would confuse this ticket's scope. Not yet filed.
4. **Should the reviewer be handed an authoritative cycle number at dispatch?** Today it self-reports with
   no ground truth (`review.md` §2 states no cycle; `prompts/review.md:96`'s example hardcodes
   `{"cycle": 1}`). The corpus shows it self-reporting correctly 19/19, so this is *fragile-by-design, not
   observed failing*. Adjacent to this feature — the discriminant work hands the dispatch site the right
   answer anyway. *Recommendation: fold the one-line example fix into this ticket; file the broader
   "reviewer has no ground-truth cycle" gap separately if it recurs.*
5. **Does the archive change what `implement.md` §3 reads?** It reads `review.md` for the fix step
   (`implement.md:70-72`), which stays the current-cycle path — so no. Stated for the record because it was
   checked, not because it is open.
