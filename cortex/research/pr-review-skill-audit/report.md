# cortex-pr-review Skill Audit: Build vs Buy

Date: 2026-06-14

## Executive recommendation

**Hybrid: gut the pipeline, keep the skill as a thin shell around its two real differentiators.** Retire the five-stage multi-agent orchestration and route `/pr-review` to a single high-effort reviewer agent (or the bundled `/code-review` engine), keeping only the two capabilities no external tool reproduces: provable quoted-text evidence grounding and the auditable dropped-findings footer. The lever this turns on is shape, not vendor: the live trial showed the review's value came from ordinary codebase investigation any single capable agent does, while the four-critic fan-out, Haiku triage, git-history firehose, and prev-PR-comments critic measurably hurt by manufacturing redundancy and dead weight. The bet is that less pipeline plus a fixed grounder produces more consistent findings than either the current machine or a black-box external bot. The main risk is that the grounding script's defects (silent near-miss drops, exact-substring matching) are intrinsic enough that the honest endgame is deleting it too and grounding in-context, which would collapse the hybrid toward near-pure adopt-external.

This is not a clean keep: the skill is an admitted fork of Anthropic's first-party `plugins/code-review`, and two of its four homegrown additions (the JSON evidence schema and the three-axis rubric) are net-negative as built. It is not a clean buy either: no external tool both defaults to terminal-only AND reproduces the grounder plus footer that are the owner's trust-building edge.

## How the skill works today

`/pr-review [number]` runs a five-stage multi-agent pipeline the main agent orchestrates by reading 821 lines of prose protocol:

- **Stage 0**: Bash preflight (jq, python3, writable cache dir).
- **Stage 1**: `gh pr view` (metadata) + `gh pr diff` (full diff cached to disk).
- **Stage 2**: a Haiku triage subagent labels each changed file deep-review or skim-ignore.
- **Stage 3**: four parallel Sonnet critics (CLAUDE.md compliance, bug scan, git history/blame, previous PR comments), each emitting a strict JSON evidence schema.
- **Stage 3.5**: a 553-line bash/awk/python3 script (`evidence-ground.sh`) verifies each finding's `quoted_text` appears on the correct diff side, dropping unverifiable findings.
- **Stage 4**: an Opus 4.7 synthesizer applies a three-axis rubric (severity x solidness x signal), gate thresholds, per-label caps, a matched_side demotion rule, and emits a Verdict plus Conventional-Comments-labeled findings and an observability footer.
- **Stage 5**: the main agent presents the synthesis.

The hard constraint (terminal-local review, opt-in posting only) is honored at SKILL.md:73 and survives any rewrite.

## Internal audit findings

Six of seven dimensions rate broken or weak. Highest-severity problems, grounded in file:line:

### flow-ux (broken)
- **No deterministic driver.** The entire pipeline is orchestrated by the main agent reading 821 lines of prose; the only executable artifact is `evidence-ground.sh`. Six model calls plus temp-file/jq/JSON plumbing driven by a model interpreting prose is non-reproducible by construction. This is the direct mechanism behind "findings not consistently good" and "the flow is not great."
- **Maximal latency, zero progressive disclosure.** Serial Haiku to 4x Sonnet to bash to Opus, with SKILL.md:76 mandating "no conversational text during execution." The user blocks on the slowest path and sees nothing until the end.
- **Main agent is a hand-marshaled JSON message bus** between subagents through heredocs and jq (protocol.md:507-538). Each hop can drop a finding or emit invalid JSON that the script rejects as critic-malformed-json.

### findings-rubric (weak)
- **Never calibrated.** rubric.md:85 and :116 both literally state "Calibration data not yet recorded." The 9-run Krippendorff's-alpha stability protocol with ship/block thresholds was never run. Every consistency claim is aspirational; the rubric shipped against its own ship gate with no data.
- **Non-deterministic by construction.** Three subjective LLM axes with no anchoring examples, multiplied through conjunctive gates, so a one-bucket wobble flips a finding between surfaced and dropped (rubric.md:13-36, protocol.md:646-664).
- **Logic bugs.** The praise gate is structurally unreachable (praise carries no concrete next action, but solid requires one, rubric.md:26 vs :46). `linter-class` is a drop reason no axis produces, the synthesizer is told to use it (protocol.md:673), and output-format.md:71-78 bans inventing it. `issue (non-blocking)` and `suggestion (blocking)` both bypass the verdict gate (protocol.md:690 vs output-format.md:25), so a must-fix can surface while the PR shows APPROVE.

### evidence-grounding (broken)
- **Exact-substring matching silently drops real bugs.** `if q in ct` (evidence-ground.sh:337) means a lightly-edited or paraphrased quote of a real bug is dropped as `evidence-not-found`, which is a SILENT drop not shown in the footer (rubric.md:64).
- **Simultaneously too lenient and too strict.** `slack=10` (line 216) accepts findings whose line_range is off by up to 10 lines, while a 1-character quote typo vanishes with zero trace.
- **matched_side can be mis-attributed** via substring overlap (a removed-line concern reported as `+`), corrupting the synthesizer's demotion rule.
- **The multi-line consecutive-hunk machinery is defeated by its own fallback** (lines 356-361 re-admit any quote where any single line appears anywhere). The most complex code in the file does almost no filtering.

### critic-angles (weak)
- **Only one of four critics hunts defects, and its prompt hobbles it** ("shallow, skeptical scan," diff-only, no repo context, protocol.md:256, :265).
- **Git-history and prev-PR-comments critics structurally conflict with grounding.** Their findings are about code NOT in the current diff, so grounding drops them as `evidence-not-found`. Half the panel is set up to have its output discarded.
- **No security, test-coverage, or API-contract critic** despite the repo shipping a dedicated `/security-review` skill and the rubric's own must-fix definition referencing security (rubric.md:17).

### output-format (mixed)
- **GitHub-markdown wire format for a terminal-first skill.** `<details>`/`<summary>` HTML and a markdown table (protocol.md:729-736) render as literal noise in a terminal and the "collapsed" drop table is always expanded.
- **The footer often outweighs the findings.** An aggressive-drop pipeline surfaces a few findings above a longer drop table.
- **No severity ordering** in the flat finding list, so a blocking `issue:` can appear below a `praise:`.

### architecture-distribution (broken)
- **The tiered-model design is admitted-unwired.** protocol.md:573-580 says model/effort params are set "once the Task tool exposes it... no runtime fallback required." If the Task tool ignores model pins, all stages run on the session default and the user pays five-stage complexity for single-model quality.
- **Hard pin to claude-opus-4-7** (protocol.md:572, 727), a generation behind the Opus 4.8 this repo runs. The footer template asserts a model that may not even be the one that ran.
- **Runtime artifacts written into the read-only plugin dir and hardcoded /tmp** (SKILL.md:16, protocol.md:531) against the repo's own $TMPDIR convention; concurrent reviews collide.

### robustness-failure (broken)
- **Fail-open default: every degradation path collapses to a silent empty APPROVE** (protocol.md:556, :784). All-critics-malformed, grounding error, or legitimate zero-grounded all route to Verdict=APPROVE. A code reviewer's worst failure is approving a defective PR, and this design does it silently.
- **Fatal-error branches emit success-shaped JSON.** Verified at evidence-ground.sh:75-116: each fatal branch `printf`s a full object containing `.grounded` then `exit 1`. Whether the agent routes to synthesis-failure or to "ran, zero findings, APPROVE" depends on whether it checks the exit code before parsing, a prose-only contract.
- **~30 prose-only failure branches** the main agent must arbitrate with no structural enforcement, violating the repo's own "prefer structural separation over prose-only enforcement" principle.

## Live-trial evidence

The protocol was run by hand against PRs #20 and #18 and executed successfully. What actually happened:

- **The review was genuinely useful** but the value traced to codebase investigation any single capable agent does (reading common.py, `git log -2`, spotting that the inline tier fold duplicates the canonical reducer and was replaced one commit later), NOT to the five-stage structure.
- **The structure measurably hurt.** The four-critic split manufactured 3 near-duplicate findings about one underlying fact that the synthesizer only half-deduped. Haiku triage was identity-work: 4/4 files labeled deep-review, a wasted model round-trip a 5-line bash glob could do for free. Git-history's `git log --follow -p` firehose returned full patch history when `git log --oneline -2` had the one relevant fact. Prev-PR-comments returned nothing actionable on a solo repo and its one synthesized finding was dropped as low-signal.
- **The grounding script ran correctly on every branch exercised.** It passed all 7 real findings, correctly set `matched_side='+'` on quoted findings and left it null on the null-quote question/cross-cutting findings, matched a 2-line consecutive multi-line quote within one hunk, correctly returned `matched_side='-'` on an injected removed-line probe, and DROPPED the 1 deliberately-hallucinated finding as `evidence-not-found`. So the grounder works as a hallucination filter. But this success depended on the trial author authoring byte-exact quotes and recovering POST-IMAGE line numbers via `git show`. The confirmed latent danger: `evidence-not-found` is a silent drop excluded from the footer, matching is exact-substring after normalization, so a real finding with a 1-char quote typo vanishes with zero trace while `slack=10` accepts findings 10 lines off-target. Robust against gross hallucination, brittle against near-miss quotes, and the brittleness is invisible by design.

Sample real output (PR #20):

```
Verdict: APPROVE

suggestion: cortex_command/pipeline/metrics.py:244-245
The inline tier-supersession fold re-implements the canonical rule instead of
calling common.reduce_lifecycle_events... The follow-up commit 66ef32d7 did exactly this.

suggestion: cortex_command/pipeline/metrics.py:244-245
The inline fold accepts any non-None tier/to value, but common.reduce_lifecycle_events
gates each value against TIER_VOCABULARY... Gate the assignment or delegate to the shared reducer.

question: cortex_command/pipeline/metrics.py:240-256
The fold lets the last complexity_override in iteration order win... Is every writer
of events.log guaranteed to append chronologically?

cross-cutting: cortex_command/pipeline/metrics.py:240-256
The duplicated supersession logic was superseded one commit later by 66ef32d7...
this is context rather than a defect.

---
_Reviewed by claude-opus-4-7 with 4 critics. 4 findings posted, 4 dropped._

<details>
<summary>Dropped findings (3)</summary>
| # | Category | Label (would have been) | Reason dropped |
...
</details>
```

The output is useful but redundant (three findings orbiting one fact), the footer is the best part, the verdict is brittle (APPROVE vs REQUEST_CHANGES hinges on one subjective should-fix-vs-must-fix call), and the model footer asserts claude-opus-4-7.

Trial verdict: KEEP-BUT-SIMPLIFY, leaning hard toward a major cut.

## External landscape

| Tool | Category | No-autopost? | Fit (1-5) | Verdict | Notes |
|------|----------|--------------|-----------|---------|-------|
| Claude Code `/code-review` (bundled local) | anthropic-native | Yes (default; --comment opt-in) | 5 | adopt | Same agent lineage, Anthropic-maintained, free, already installed. The single strongest comparator. |
| Claude Code `/review [PR]` (bundled) | anthropic-native | Yes (local, no post flag) | 4 | borrow-ideas | Single-pass PR review; shallower; overlaps /code-review. |
| Claude Code `/security-review` (bundled) | anthropic-native | Yes (local) | 3 | borrow-ideas | Security-scoped companion, not a general reviewer. |
| Claude Code ultrareview (`/code-review ultra`, `claude ultrareview`) | anthropic-native | Yes (prints to session/stdout) | 4 | adopt | Deep multi-agent, independent reproduce-and-verify; premium/metered ~$5-20/review after 3 free; cloud. |
| Anthropic GitHub Action / managed Code Review | anthropic-native | No (auto-posts) | 1 | ignore | Commenting bot; Team/Enterprise; fails the constraint. |
| Anthropic `plugins/code-review` (marketplace ancestor) | anthropic-native | Auto-posts (gh pr comment in allowed-tools) | 4 | borrow-ideas | The fork-parent. Verified: it CAN post. Free no-autopost path is the bundled skill, not this plugin. |
| CodeRabbit GitHub app | saas-bot | No (auto-posts) | 2 | ignore | Best catch-rate reputation but noisy (~80% signal); commenting bot. |
| CodeRabbit CLI | saas-bot | Yes (no post capability) | 4 | borrow-ideas | Native /coderabbit:review plugin; cloud inference; inherits noise reputation. |
| Greptile | saas-bot | Partial (CLI yes, bot no) | 3 | borrow-ideas | 82% catch rate but noisiest (~11 FP/run); whole-repo indexing is the idea to borrow. |
| GitHub Copilot code review | saas-bot | Partial (IDE-only non-post) | 2 | borrow-ideas | gh/web surfaces auto-post; no terminal PR-by-number non-posting flow. |
| Cursor Bugbot (/review) | ide-integrated | Partial (editor-bound; CLI "coming soon") | 2 | borrow-ideas | Posting-first; non-post is editor-bound. |
| GitHub Copilot CLI /review | other | Yes (prints to terminal) | 3 | borrow-ideas | Cleanest external no-autopost CLI fit; single-pass, no grounding/rubric. |
| Qodo PR-Agent (OSS) | oss-skill | Yes (publish_output=false) | 4 | borrow-ideas | Documented terminal mode but posting-by-default; lives outside Claude Code skill model. |
| Bito CLI (bitoreview) | saas-bot | Yes (CLI prints to terminal) | 3 | borrow-ideas | Good CLI ergonomics; cloud inference; mid-pack quality. |
| tag1consulting/claude-comprehensive-review | oss-skill | Yes (--post-* opt-in) | 4 | borrow-ideas | Integrates semgrep/shellcheck (deterministic ground truth); 3-star bus factor. |
| awesome-skills/code-review-skill | oss-skill | Yes (no posting) | 3 | borrow-ideas | 1000+ star guideline knowledge layer; not a pipeline. |
| Graphite Agent, Sourcery, Codacy, Ellipsis, Korbit, Sweep, Trag, Baz, Codeball | saas-bot | No / partial | 1-2 | ignore | Commenting/CI bots; fail the constraint or wrong category. |

The few that matter:

- **Bundled `/code-review`** is the decisive comparator. It satisfies no-autopost out of the box ("--comment to post... or --fix to apply"; no flag prints to terminal), is Anthropic-maintained so it tracks model upgrades, is already installed, and accepts a `REVIEW.md` for repo-specific tuning. Its weakness against cortex is no quoted-text evidence grounding and a black-box rubric.
- **ultrareview** is the strongest first-party quality option: many parallel agents that independently reproduce findings, which is a stronger false-positive filter than text-matching `evidence-ground.sh`. Cost (~$5-20/review, metered) and Claude.ai-auth constraints make it an on-demand deep-pass tier, not the default.
- **The naming trap**: "Code Review" splits into the auto-posting managed/marketplace product (fails the constraint) and the bundled local `/code-review` command (meets it). Verified the marketplace ancestor lists `gh pr comment` in allowed-tools, so it can post; the free no-autopost path is the bundled slash skill.
- **tag1's deterministic-tool integration** (semgrep, shellcheck, dependency scan) is the single most promising idea to import: ground-truth checks would directly improve "findings not consistently good" and cortex has none.

## Build vs buy

Three symmetric positions were argued. Hybrid wins.

**Keep-and-improve** is right that no-autopost is best satisfied by our own skill (default-and-only, not a vendor's secondary surface), that evidence grounding and the footer are genuine differentiators no external tool reproduces, and that the diagnosis is unanimous the problems are fixable by simplification. Its fatal weakness: the skill's net value over a free first-party ancestor reduces to a grounding script plus a footer, because the JSON schema and rubric are net-negative as built. And the grounder's central guarantee is partly illusory (silent near-miss drops), so the flagship differentiator currently works against the owner's complaint.

**Adopt-external** is right that we are maintaining a fork of upstream, that the tiered design is admitted-unwired so the complexity buys nothing, that the rubric is unvalidated and internally broken, and that the fail-open default is dangerous. Its fatal weakness: no external option reproduces provable quoted-text grounding plus the auditable drop table end-to-end, so full retirement loses real value the owner specifically wants. Several no-autopost externals also carry the same noise problem the owner is trying to escape.

**Hybrid** wins because the decisive factor is shape, not vendor. The live trial proved the value came from investigation any single capable agent does, not from the five-stage structure, and that the structure measurably hurt while exactly two components (grounder, footer) earned their place. Pure keep over-maintains a 553-line script plus 821-line protocol the owner is already unhappy with. Pure buy discards the one provably-unique capability and inherits a noise problem. Hybrid keeps the earners and cuts the non-earners. The honest caveat that holds confidence at medium: the single most decisive number, whether the pipeline is actually less consistent than a single pass, was never measured by anyone including this audit.

## Recommendation & plan

**Decision: hybrid.** Collapse the orchestration to a single high-effort reviewer agent (one prompt: diff + discovered CLAUDE.md + "investigate the codebase to ground each finding") that emits the same evidence schema. Keep the evidence-grounding step and the observability footer. Drop triage, the four-way fan-out, git-history, and prev-PR-comments as standing stages. If the single-agent rewrite plus the calibration run (below) shows no consistency edge over bundled `/code-review` with a tuned `REVIEW.md`, fall back to wrapping `/code-review` and bolting the footer on as a thin output layer. The no-autopost requirement is preserved trivially in either case: it is a presentation choice orthogonal to pipeline shape.

Prioritized improvement plan (highest impact / lowest effort first):

| Change | Effort | Impact | Rationale |
|--------|--------|--------|-----------|
| Make `evidence-not-found` drops VISIBLE in the footer (or a count line) | small | high | The system's worst failure mode (real-bug near-miss quotes vanishing) is invisible by design. One line fixes observability of the lossiest path. |
| Stop line_range as a hard filter; search whole-diff for the quote, use line_range only as tie-breaker; drop the arbitrary slack=10 | small | high | Fixes the off-by-window silent drops without touching the matcher's anti-hallucination core. |
| Invert fail-open to fail-loud: zero surfaced findings + any degradation signal (failed_critics, grounding error, missing diff) yields REVIEW_INCONCLUSIVE, not APPROVE | small | high | A reviewer that cannot verify must not approve. Direct correctness fix. |
| Make grounding fatal-error branches structurally distinct: emit `{"status":"error"}` with NO `.grounded` key | small | high | Removes the exit-code-vs-parse ambiguity (script:75-116) that lets a setup error masquerade as a clean review. |
| Replace claude-opus-4-7 pin with session-default/highest-available; footer reports the model that actually ran | small | high | Kills the rot source and the lying footer. |
| Collapse the three-axis rubric to a single severity scale + hard grounding requirement; emit all grounded findings; delete per-label caps and the alphabetical tie-break | medium | high | Removes the unreachable-praise bug, the linter-class contradiction, the issue/suggestion verdict leak, and most run-to-run variance. Caps and alphabetical tie-break suppress real signal by arbitrary count and sort order. |
| Reconcile label/verdict vocabulary across all three files; key the verdict off severity, not an exact label string; decide whether COMMENT is a third verdict | small | high | A must-fix can currently surface while the PR shows APPROVE. Correctness fix. |
| Collapse four critics into one agent (or one synthesizer) emitting findings directly | medium | high | Removes the redundancy the live trial measured, the strict cross-stage JSON contract, and the "one malformed critic drops its findings" failure. |
| Make output mode-aware: plain terminal text by default, GitHub-markdown only when posting; sort findings blocking-first | medium | medium | Aligns format with the terminal-first hard requirement; makes blockers scannable. |
| Add deterministic linters (semgrep, shellcheck) as a ground-truth input the reviewer anchors on | medium | medium | Borrowed from tag1; ground-truth checks directly improve consistency. cortex has none today. |
| Run the rubric's own 9-run stability protocol on 3 fixed PRs to baseline Krippendorff's-alpha before/after the rewrite | medium | medium | The owner's "inconsistent" complaint is currently unfalsifiable. This is the cheapest decision-maker and gives a ship/block gate that exists today only on paper. |
| Add a golden-fixture test suite for whatever grounding survives (paraphrase, line-range drift, both-sides overlap, multi-line, CRLF, NFC) | medium | medium | Zero behavioral tests on the lossiest component is the root maintenance risk. |

What to delete / stop doing:

- **Delete Stage 2 Haiku triage.** It was identity-work in the trial; a static skim-ignore bash glob (lockfiles, *.snap, generated) does it deterministically and free.
- **Delete the four-way critic fan-out.** Fold compliance + bug + security + test-coverage + contract into one agent's checklist.
- **Delete the git-history and prev-PR-comments critics as standing stages.** Demote to optional on-demand context the single agent can fetch when a PR warrants it. The git-history `-p` full-patch firehose in particular is the worst cost/value ratio in the pipeline.
- **Stop hand-marshaling JSON between subagents through heredocs and jq.** With one agent there is nothing to marshal.
- **Stop inlining rubric.md + output-format.md into a freshly composed prompt every run.** Ship the synthesizer as code that reads the files.
- **Consider deleting `evidence-ground.sh` entirely** if the calibration run shows in-context grounding by the single reviewer agent (which already has the full diff) matches or beats it. The 553-line bash/awk/python3 script with no tests is a maintenance liability whose central guarantee is partly illusory; the audit's own top idea is to fold "verify the quote appears on the + side, else demote/drop" into the reviewer prompt as a decision criterion. Keep it only if the calibration run shows it provides a measured precision edge AND the silent-drop/slack fixes above land.

## Open questions / where evidence is thin

- **The decisive measurement was never taken.** Whether the bespoke pipeline (or a simplified single-agent version) is actually more consistent than bundled `/code-review` on the same PRs is unmeasured. Running the rubric's own stability protocol on 3 fixed PRs resolves keep-vs-buy toward one pole and should gate the rewrite.
- **Whether the Task tool honors per-dispatch model pins is unconfirmed.** If it does not, the tiered design buys nothing and the case for any multi-stage structure weakens further. If it does, a cost/quality argument for tiering reappears.
- **The live trial is a single small solo-repo PR (#20/#18).** The redundancy and dead-weight findings may not fully generalize to large multi-author PRs where the four-angle split or prev-PR-comments critic could pay off. The trial author flags prev-PR-comments as dead "on a normal/solo repo," implicitly conceding it may matter elsewhere.
- **Whether the grounder's silent-drop and slack defects are cheaply fixable or intrinsic to substring matching.** If cheaply fixable (visible evidence-weak drops + line_range as tie-breaker), keeping a fixed grounder is justified. If intrinsic, deleting it for in-context grounding is the honest call and the hybrid collapses toward adopt-external.
- **External tools are moving targets.** `/code-review` command shape changed across recent versions and ultrareview is a research preview with metered pricing and Claude.ai-auth constraints. Any adopt decision should re-confirm current behavior before committing.
