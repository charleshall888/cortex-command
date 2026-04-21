# Specification: collect-47-baseline-rounds-and-snapshot-the-aggregated-data

> Epic context: Child of [#082 Adapt harness to Opus 4.7](../../backlog/082-adapt-harness-to-opus-47-prompt-delta-capability-adoption.md). DR-4 in [`research/opus-4-7-harness-adaptation/research.md`](../../research/opus-4-7-harness-adaptation/research.md) is the motivating decision record.

## Problem Statement

DR-4 requires a clean 4.7 baseline snapshot of `num_turns` and `cost_usd` distributions — captured with prompts frozen and committed as a versioned artifact — before #092 (scaffolding removal) or #090 (xhigh adoption) can ship. Without this comparison anchor, downstream measurement has no statistical reference for the buckets they measure. #087 built the aggregator (`compute_model_tier_dispatch_aggregates()` in `claude/pipeline/metrics.py`); this ticket consumes that aggregator output and commits a markdown snapshot at the exact path `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` that #092 and #090 read.

A research-phase adversarial review surfaced a structural gap: `dispatch_complete` events emit the bare family name (`"opus"`/`"sonnet"`/`"haiku"`) and do not record the resolved model version ID. Without model-version evidence in the events, #092's post-change measurement has no way to confirm it ran on the same resolved model as #088's baseline — cross-version drift would be undetectable. This spec therefore bundles a small pipeline instrumentation change (capture `AssistantMessage.model` and persist it on `dispatch_complete`) that is committed in a **separate, pre-window commit** so the baseline rounds themselves run on the post-R1 codebase and capture `model_resolved` evidence. This ordering (R1 commits first, measurement window opens, snapshot commits later) resolves the otherwise-unsatisfiable "frozen prompts + capture model evidence" constraint.

**Why `AssistantMessage.model`, not `ResultMessage.model`**: the installed `claude_agent_sdk` (`claude_agent_sdk==0.1.41`) defines `ResultMessage` without a `model` attribute — it carries only `subtype`, `duration_ms`, `duration_api_ms`, `is_error`, `num_turns`, `session_id`, `total_cost_usd`, `usage`, `result`, `structured_output` (see `.venv/lib/python3.13/site-packages/claude_agent_sdk/types.py`). `AssistantMessage` is the only stream-member carrying the resolved `model: str`. Research-phase text that referenced `ResultMessage.model` was incorrect; this spec corrects that.

**Scope of what this baseline guarantees**: the snapshot is a comparison anchor for per-`(model, tier)` buckets that received ≥1 dispatch across the clean rounds. It does **not** guarantee per-tier n≥30, does not guarantee every tier is populated, and does not guarantee any particular downstream ticket has a usable comparison in its bucket of interest. #092 and #090 scope their own comparisons to the buckets this snapshot actually populated; an empty bucket in this snapshot is itself evidence (not an error) and downstream tickets handle that case in their own specs.

## Requirements

1. **Capture resolved model ID in `dispatch_complete`**: In `claude/pipeline/dispatch.py` around lines 461–516, capture `getattr(message, 'model', None)` from the first `AssistantMessage` observed during the async iteration into a local `resolved_model: str | None` (initially `None`; set on first occurrence and never re-assigned). When emitting the `dispatch_complete` event at lines 509–516, include a new field `"model_resolved": <resolved_model>` (value is `None` when no `AssistantMessage` was seen — e.g., synchronous error before any completion — or when a future SDK renames the `.model` attribute). "First-observed" is the chosen semantic even for dispatches with up to `max_turns=30` AssistantMessages per stream; a future ticket may refine if mid-stream model changes become empirically observable.
   - Acceptance: `grep -n '"model_resolved"' claude/pipeline/dispatch.py` returns at least one match inside the `log_event(... "event": "dispatch_complete" ...)` block. `pytest claude/pipeline/tests/` exits 0 with the new test from R2.

2. **Add a test that verifies `model_resolved` emission**: Add a test (in an existing `claude/pipeline/tests/test_dispatch*.py` file or a new file) that patches `claude_agent_sdk.query` to yield an `AssistantMessage(content=[], model="claude-opus-4-7-test")` followed by a `ResultMessage(...)` and asserts that the resulting `dispatch_complete` JSON line in the log contains the key `model_resolved` with value `"claude-opus-4-7-test"`. Additionally, verify by inspection that any existing test in `claude/pipeline/tests/` that constructs or asserts on `dispatch_complete` event fixtures (e.g., `test_metrics.py:80, 217-230` and `claude/pipeline/tests/fixtures/dispatch_since_boundary.jsonl`, `dispatch_over_cap.jsonl`) still passes after the new field is introduced — if any of those fixtures or assertions pin to a precise-field-set check, update them to accept the new field.
   - Acceptance: `pytest claude/pipeline/tests/` exits 0. `grep -rn 'model_resolved.*claude-opus-4-7-test' claude/pipeline/tests/` returns at least one match.

3. **`#087`'s aggregator runs unchanged**: No changes to `claude/pipeline/metrics.py`. The aggregator already groups by the `model` field from `dispatch_start` (unchanged, still bare family name). The new `model_resolved` field on `dispatch_complete` is persisted for downstream evidence only — not used as an aggregation key in this ticket. A future ticket may add version-aware aggregation.
   - Acceptance: `git diff claude/pipeline/metrics.py` is empty across this ticket's commits.

4. **Baseline window definition**: The baseline window starts at `2026-04-20T00:00:00Z`. Only dispatches with `ts >= 2026-04-20` are included in the aggregation. The user invokes `python3 -m claude.pipeline.metrics --since 2026-04-20 --report tier-dispatch` once ≥ 2 clean rounds have completed.
   - Acceptance: The snapshot's YAML frontmatter records `window_start: 2026-04-20` and `since_flag: "2026-04-20"`. The `model_tier_dispatch_aggregates_window` field in `lifecycle/metrics.json` records the same bound at generation time.

5. **Prompts are held frozen during the measurement window**: No edits during the measurement window to any file under any of these prompt-surfacing paths:
   - `skills/**/*.md`
   - `claude/reference/**/*.md`
   - `claude/pipeline/prompts/**/*.md` (e.g. `implement.md`, `review.md`)
   - `claude/overnight/prompts/**/*.md` (e.g. `batch-brain.md`, `orchestrator-round.md`, `repair-agent.md`)
   - `CLAUDE.md` (repo root)
   - `claude/Agents.md` (symlinked to `~/.claude/CLAUDE.md` per the project CLAUDE.md symlink table)
   
   Enforcement is by voluntary discipline — no hash mechanism is added. The snapshot's YAML frontmatter records `git_sha_window_start` and `git_sha_window_end` so reviewers can diff the prompt surface over the window using the full path list above.
   - Acceptance: The snapshot's frontmatter contains both `git_sha_window_start` and `git_sha_window_end`. `git log --oneline <start_sha>..<end_sha> -- skills/ claude/reference/ claude/pipeline/prompts/ claude/overnight/prompts/ CLAUDE.md claude/Agents.md` is expected to return zero commits; if non-zero, the snapshot body's rounds table flags the affected rounds and the user decides whether to include or re-run them.
   - **Residual risk (Technical Constraints)**: inline string-literal system prompts in Python source (e.g. `claude/pipeline/review_dispatch.py:246` constructs `system_prompt = "You are a code reviewer. …"` as a literal) are NOT covered by this grep. Voluntary discipline is the only mitigation; deliberate pipeline-code edits during the measurement window should be limited to none (after R1's pre-window commit lands).

6. **Clean-round rule (pre-committed, mechanically checked)**: A round is considered "clean" and included in the baseline if and only if both conditions hold:
   - (a) The round's `pipeline-events.log` contains zero `dispatch_error` events with `error_type == "api_rate_limit"`.
   - (b) The round terminated normally: `lifecycle/sessions/{session_id}/overnight-events.log` contains a `SESSION_COMPLETE` event AND the session was not killed by the watchdog (no `.runner.lock` PID mismatch at session end).
   
   A round failing either condition is labeled "discarded" in the snapshot's rounds table and the user runs an additional round (per ticket contingency).
   - Acceptance: The snapshot body contains a table of all rounds considered in the window with per-round columns `session_id | round | clean | reason_if_discarded`. At least two rows have `clean = true`. For each row, both (a) and (b) are checkable by grep/jq of the cited log files — no subjective judgment.

7. **Close rule**: #088 closes `complete` when ≥ 2 clean rounds have completed within the window and the snapshot file is committed at the exact path `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md`. No per-tier minimum-n threshold is enforced at ticket closure; the snapshot documents per-bucket `n_completes` and labels low-n buckets per #087's existing `p95_suppressed:true` convention. Empty buckets are documented as such in the rounds table and `## Limitations`; downstream tickets (#092, #090) that find their target bucket empty must open follow-up tickets to extend the baseline — they do not re-open #088.
   - Acceptance: `ls research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` exits 0; the file contains ≥ 2 entries in the clean-rounds table (Requirement 6); `update-item 088-collect-47-baseline-rounds-then-remove-progress-update-scaffolding status=complete` succeeds.

8. **Snapshot schema — per-(model, tier) primary**: The snapshot preserves #087's native `"<model>,<tier>"` bucket keys as the primary view. No separate tier-only collapsed view is produced.
   - Acceptance: The snapshot contains the fenced code block described in Requirement 9, which contains rows whose first column is the `"<model>,<tier>"` bucket key from #087's aggregator output.

9. **Snapshot Aggregates section — literal verbatim capture of the CLI report**: The snapshot's `## Aggregates` section contains a fenced code block (```) whose contents are the **literal stdout** of `python3 -m claude.pipeline.metrics --since 2026-04-20 --report tier-dispatch`, captured verbatim and pasted without reformatting. This eliminates hand-transcription of a wide numeric table.
   - Acceptance: Regenerate the report into a temp file: `python3 -m claude.pipeline.metrics --since 2026-04-20 --report tier-dispatch > /tmp/report.txt`. Extract the fenced block from the snapshot (the first fenced block after the `## Aggregates` heading) into `/tmp/block.txt`. `diff -u /tmp/report.txt /tmp/block.txt` exits 0 (they match byte-for-byte modulo trailing whitespace).

10. **Snapshot schema — embedded JSON fence identical to metrics.json**: Immediately after `## Raw data`, the snapshot embeds a fenced `json` code block containing the raw `model_tier_dispatch_aggregates` dict and its `model_tier_dispatch_aggregates_window` metadata — these two keys lifted verbatim from `lifecycle/metrics.json`. No separate JSON sidecar file is committed.
   - Acceptance: `python3 -c "import json, re; md = open('research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md').read(); m = re.search(r'\`\`\`json\n(.*?)\n\`\`\`', md, re.DOTALL); d = json.loads(m.group(1)); src = json.loads(open('lifecycle/metrics.json').read()); assert d['model_tier_dispatch_aggregates'] == src['model_tier_dispatch_aggregates']; assert d.get('model_tier_dispatch_aggregates_window') == src.get('model_tier_dispatch_aggregates_window')"` exits 0.

11. **Snapshot YAML frontmatter (provenance, typed)**: The snapshot begins with a YAML frontmatter block containing these exact fields with the listed value-types:
    ```yaml
    ---
    snapshot: 4-7-baseline                              # literal string
    ticket: 088                                         # integer
    epic: 082                                           # integer
    generated_at: <ISO 8601 UTC>                        # e.g. 2026-04-25T15:30:00Z
    window_start: 2026-04-20                            # ISO date (YYYY-MM-DD)
    window_end: <ISO 8601 date>                         # YYYY-MM-DD of last included round
    since_flag: "2026-04-20"                            # quoted string
    rounds_included: <integer ≥ 2>                     # integer
    git_sha_window_start: <12-char lowercase hex>       # matches /^[0-9a-f]{12}$/
    git_sha_window_end: <12-char lowercase hex>         # matches /^[0-9a-f]{12}$/
    aggregator_invocation: "python3 -m claude.pipeline.metrics --since 2026-04-20 --report tier-dispatch"
    cost_caveat: "All cost values are SDK client-side estimates (ResultMessage.total_cost_usd), not authoritative billing data"
    sample_size_caveat: "At n<30 per bucket this baseline is directional only, not conclusive evidence for prompt-change attribution"
    ---
    ```
    - Acceptance: The following Python one-liner exits 0 — it checks both key-set AND value-types:
      ```python
      python3 -c "
      import yaml, re, datetime
      md = open('research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md').read()
      fm = md.split('---', 2)[1]
      d = yaml.safe_load(fm)
      required = {'snapshot','ticket','epic','generated_at','window_start','window_end','since_flag','rounds_included','git_sha_window_start','git_sha_window_end','aggregator_invocation','cost_caveat','sample_size_caveat'}
      assert required <= set(d.keys()), f'missing keys: {required - set(d.keys())}'
      assert d['snapshot'] == '4-7-baseline'
      assert isinstance(d['ticket'], int) and d['ticket'] == 88
      assert isinstance(d['epic'], int) and d['epic'] == 82
      assert isinstance(d['window_start'], datetime.date) and d['window_start'].isoformat() == '2026-04-20'
      assert isinstance(d['window_end'], datetime.date)
      assert isinstance(d['since_flag'], str) and d['since_flag'] == '2026-04-20'
      assert isinstance(d['rounds_included'], int) and d['rounds_included'] >= 2
      assert isinstance(d['git_sha_window_start'], str) and re.match(r'^[0-9a-f]{12}\$', d['git_sha_window_start'])
      assert isinstance(d['git_sha_window_end'], str) and re.match(r'^[0-9a-f]{12}\$', d['git_sha_window_end'])
      assert isinstance(d['aggregator_invocation'], str) and '--since 2026-04-20' in d['aggregator_invocation']
      "
      ```

12. **Snapshot body sections**: The snapshot body (after the frontmatter) contains these sections in order:
    (a) `## Overview` — 1-paragraph context and what this snapshot is for (1-sentence DR-4 reference, 1-sentence what's measured, 1-sentence scope limitation);
    (b) `## Clean rounds included` — the per-round table from Requirement 6;
    (c) `## Aggregates` — the literal CLI-report fenced block from Requirement 9;
    (d) `## Raw data` — the embedded JSON fence from Requirement 10;
    (e) `## Limitations` — bulleted list explicitly noting:
       - Cost values are SDK client-side estimates (not authoritative billing).
       - Small-n per-bucket makes this directional only; not conclusive for prompt-change attribution.
       - `dispatch_start` `model` field is bare family name; `dispatch_complete`'s new `model_resolved` field captures resolved version for downstream comparison, but this snapshot does not aggregate on it.
       - Cross-model-version comparisons are invalid (4.6↔4.7 tokenizer differs 1.0–1.35×; 4.7 has "fewer tool calls by default").
       - **This baseline captures dispatches made while R1's `model_resolved` instrumentation is active (landed in commit `<sha>` prior to window_start). #092's post-change measurement MUST run on the same or a later instrumentation (do not revert R1 before #092 ships).**
       - **Frozen-prompts check excludes inline string-literal system prompts in Python source (e.g., `claude/pipeline/review_dispatch.py`). Voluntary discipline is the only mitigation; the check in Requirement 5 does not detect such edits.**
    - Acceptance: `grep -E "^## (Overview|Clean rounds included|Aggregates|Raw data|Limitations)" research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md | wc -l` returns `5`. `## Limitations` section contains exactly ≥ 6 bullets.

13. **Speculative round-start SHA capture (operational)**: At the start of each overnight round attempted within the window — before any dispatch fires — the operator records `git rev-parse HEAD` to a file at `lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/sha-round-{session_id}.txt`. When the snapshot is composed, `git_sha_window_start` is the SHA from the file corresponding to the first clean round; `git_sha_window_end` is the SHA from the file corresponding to the last included clean round. This gives a fixation moment for retrospective "first clean round" attribution and also records SHAs for discarded rounds (the files remain, but the snapshot frontmatter does not reference them).
    - Acceptance: `ls lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/sha-round-*.txt` returns ≥ 2 files. The values in the snapshot's `git_sha_window_start` and `git_sha_window_end` frontmatter fields match (truncated to 12 chars) the contents of two of those files.

14. **Commit sequence** — this ticket produces **two separate commits** in order:
    - **Commit A (pre-window)**: Pipeline instrumentation. Contains only: `claude/pipeline/dispatch.py` (R1's change) + any test updates from R2 + `lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/{events.log, research.md, spec.md, index.md}` (lifecycle artifacts). Commit message references `#088 (pipeline instrumentation, pre-window)`. This commit MUST land and be on `main` before the first round of the measurement window runs — its SHA (truncated to 12 chars) is what gets recorded as `git_sha_window_start` for the first clean round.
    - **Commit B (snapshot)**: Contains only the new file `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` plus the `lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/sha-round-*.txt` files from R13. Commit message references `#088 (baseline snapshot)`. This commit lands after ≥ 2 clean rounds are in the bag and the snapshot has been composed per R9–R12.
    - **Rationale for splitting**: keeps the R1 instrumentation change revertable independently of the snapshot (so #092/#090 do not lose their comparison anchor if R1 is ever rolled back), and ensures the snapshotted dispatches all run on the post-R1 codebase (so `model_resolved` is captured in the data the snapshot covers).
    - Acceptance: `git log --oneline main -- claude/pipeline/dispatch.py | head -1` returns a commit whose message matches `/088.*pipeline instrumentation/i`; `git log --oneline main -- research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md | head -1` returns a distinct commit whose message matches `/088.*(baseline )?snapshot/i`; the snapshot commit's parent chain is a descendant of the pipeline instrumentation commit.

## Non-Requirements

- **No new `bin/` script** for snapshot generation. The existing `python3 -m claude.pipeline.metrics --since YYYY-MM-DD --report tier-dispatch` CLI, combined with Requirement 9's verbatim-capture rule, is sufficient to avoid hand-transcription. The snapshot's `aggregator_invocation` frontmatter records the exact command.
- **No JSON sidecar file.** Raw data lives in the embedded fenced JSON block inside the markdown. One file, one source of truth.
- **No tier-only collapsed view.** The per-(model, tier) schema from #087 is the primary and only view; readers can aggregate from the embedded JSON if they need a tier-only summary.
- **No manifest hashing of prompt-surfacing paths** at round-start. Enforcement of frozen-prompts discipline is voluntary. Git SHA at window start/end (captured speculatively per R13) plus the full path list in R5 is the evidence; reviewers diff manually if needed.
- **No version-aware aggregation in #087.** The new `model_resolved` field on `dispatch_complete` is persisted for downstream evidence but is not used as an aggregation bucket key in this ticket. A future ticket may add that.
- **No rate-limit-incidents field in the snapshot.** #087 Non-Requirement #2 explicitly excluded throttle_backoff aggregation; zero such events exist in the corpus. The `## Limitations` section notes the absence.
- **No hypothesis block** in the snapshot.
- **No extended measurement window** beyond the 2–3 rounds DR-4 specifies. If one round is discarded per Requirement 6, an additional round is run to reach ≥ 2 clean rounds, but the window is not extended to chase n≥30 per bucket.
- **No per-tier minimum-n enforcement at ticket closure.** `p95_suppressed:true` from #087's existing logic labels low-n buckets; the snapshot inherits that. Downstream tickets handle empty/sparse buckets in their own specs (open a follow-up ticket to extend the baseline; do not re-open #088).
- **No mid-stream model-resolution handling in R1.** "First-observed AssistantMessage" is the semantic; if dispatches ever produce mixed resolved models within a single stream, a future ticket addresses it.
- **No automated prompt-surface manifest check.** R5 is a `git log` command the reviewer runs manually.

## Edge Cases

- **A round emits `api_rate_limit` errors** → round is discarded per Requirement 6; user runs an additional round. Rounds table lists it with `clean = false, reason = "api_rate_limit errors: N"`.
- **Session watchdog kills a round mid-session** → `SESSION_COMPLETE` event is absent; round is discarded per Requirement 6(b). Listed with `clean = false, reason = "abnormal termination: no SESSION_COMPLETE event"`.
- **A round completes normally but contains zero complex+high dispatches** → included as a clean round; `(opus, complex)` bucket may be absent or low-n. Snapshot's `## Limitations` notes the gap; downstream tickets open follow-ups per R7. #088 does not re-open.
- **A prompt-surface file was edited mid-window** (git-SHA diff between window_start and window_end over the R5 path list is non-empty) → the snapshot body's rounds table flags which rounds occurred post-edit; the user decides whether to include, re-run, or partition the window.
- **`AssistantMessage` never arrives** before an error (synchronous crash before any completion) → `model_resolved` is `None` on that `dispatch_complete` event. Emitted normally; aggregator handles as it does for any null field.
- **Future SDK renames `AssistantMessage.model`** → `getattr(message, 'model', None)` per R1 returns `None` silently; no crash. `model_resolved` will be `None` on new dispatches, but the aggregator and snapshot still work. The SDK version mismatch would be visible via the snapshot's `generated_at` timestamp vs. the installed SDK version.
- **SDK returns a resolved model string the harness doesn't recognize** (e.g., a point-release ID) → logged verbatim. No normalization, no allowlist enforcement.
- **The aggregator is re-run later with a different `--since`** → produces a different `metrics.json`; as long as the committed snapshot is unchanged, #092/#090 continue to read the committed baseline. Re-running the aggregator does NOT regenerate or overwrite the committed snapshot file.
- **A round dispatches a subagent (nested AssistantMessage with `parent_tool_use_id`)** → first-observed semantic captures whichever AssistantMessage the SDK yields first in the async stream. If this produces unstable or confusing model_resolved values across rounds, a future ticket refines.
- **Operator forgets to run `git rev-parse HEAD > sha-round-*.txt` at round start** → the R13 file does not exist; snapshot composition detects this and the operator reconstructs from `git log --oneline --before=<round_start_ts>` as a fallback. Fallback is documented in the snapshot's `## Limitations` if used.
- **Dispatch events generated from rounds _before_ the R14 Commit A SHA are excluded by the `--since 2026-04-20` filter** → but the filter is date-based, not SHA-based. If the operator accidentally commits Commit A on 2026-04-19 and runs rounds on 2026-04-20, the window captures those rounds on the post-R1 code as intended.

## Changes to Existing Behavior

- **ADDED**: `claude/pipeline/dispatch.py` — `dispatch_complete` events now include a `model_resolved: str | None` field carrying the resolved model version from the first `AssistantMessage` observed during the dispatch. Lands in Commit A (R14).
- **ADDED**: `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` — a new committed snapshot artifact following the typed frontmatter + five-section body structure in Requirements 11–12. Lands in Commit B (R14).
- **ADDED**: `lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/sha-round-{session_id}.txt` — per-round HEAD SHA files captured speculatively at each round start (R13). Land in Commit B.
- **ADDED**: at least one test in `claude/pipeline/tests/` that verifies `model_resolved` emission (R2). Lands in Commit A.
- **UNCHANGED**: `claude/pipeline/metrics.py` — `#087`'s aggregator reads the same fields it always did; `model_resolved` is persisted but not bucketed on in this ticket.

## Technical Constraints

- **Only R1 code change**. The spec's only pipeline code change is ~5 lines in `claude/pipeline/dispatch.py` plus tests from R2.
- **`AssistantMessage.model` — correct target per installed SDK**. `claude_agent_sdk==0.1.41` defines `ResultMessage` without a `model` attribute; `AssistantMessage` is the only stream-member carrying resolved `model: str`. Research-phase text mentioned `ResultMessage.model` — that was incorrect. The spec uses `getattr(message, 'model', None)` defensively so future SDK renames fall through to `None` rather than raise.
- **Cost labels are SDK client-side estimates**. Per Anthropic docs: "Do not bill end users or trigger financial decisions from these fields." The snapshot's frontmatter `cost_caveat` field and `## Limitations` bullet make this explicit.
- **Small-sample caveat**. At 2–3 overnight rounds × ~5–10 features each, most buckets will have n<30 and #087's existing `p95_suppressed:true` flag applies. The snapshot's frontmatter `sample_size_caveat` field makes the directional-only nature explicit.
- **Inline string-literal system prompts in Python source are a residual frozen-prompts risk.** R5's grep scope excludes them. Example: `claude/pipeline/review_dispatch.py` constructs system prompts inline. Mitigated by voluntary discipline only — once R1's Commit A lands, the operator commits no further pipeline edits during the window.
- **Bare model-family names remain the `dispatch_start` aggregation key.** The new `model_resolved` on `dispatch_complete` is persisted for downstream evidence only.
- **Git SHA is the attribution anchor for frozen-prompts discipline**, captured speculatively per R13 at each round's start.
- **Atomic snapshot write.** If a script is used to compose the snapshot (not required — R9's verbatim-capture and R13's file-based SHA capture keep manual composition tractable), it uses the standard tempfile + `os.replace()` pattern.
- **Python 3.11+** for `datetime.fromisoformat` handling (already a project-wide assertion in `metrics.py`).
- **Commit ordering is load-bearing.** R14 specifies R1 lands in Commit A BEFORE any round runs; snapshot lands in Commit B AFTER ≥ 2 clean rounds. Violating this ordering produces either a contaminated baseline (R1 landed mid-window) or a snapshot without `model_resolved` evidence (R1 landed post-snapshot).

## Open Decisions

(None. All decisions resolved during Clarify, Research, Spec interview, and critical review.)
