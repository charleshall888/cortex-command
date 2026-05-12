# Spike Notes: verify-claude-reference-md-conditional-loading-behavior-under-opus-47

Scratch notes, raw evidence, per-file probe captures, and synthesis working surface for the Opus 4.7 reference-file conditional-loading spike. All verdicts in the deliverable report at `research/opus-4-7-harness-adaptation/reference-loading-verification.md` cite anchors in THIS file.

## Environment

- Spike date: 2026-04-18 (implementation session)
- CLI version: Claude Code 2.1.114 (host session)
- Active model ID: `claude-opus-4-7[1m]` (per settings.json)
- Global conditional-loading table source: `~/.claude/CLAUDE.md` rows 18-25 (5 entries: verification-mindset.md, parallel-agents.md, context-file-authoring.md + claude-skills.md shared trigger row, output-floors.md)
- Probe-dir isolation regime: `mktemp -d "$TMPDIR/hook-probe-084.XXXXXX"` and `mktemp -d "$TMPDIR/probe-cwd-084.XXXXXX"` — both under sandbox `$TMPDIR=/tmp/claude-503`
- HOOK_DIR (Task 2 only; torn down after): `/tmp/claude-503/hook-probe-084.MvHydD`
- PROBE_DIR (Tasks 4-7; no `.claude/`, no `CLAUDE.md`): `/tmp/claude-503/probe-cwd-084.Ehkpc3`
- No minimal-mode flag used in any probe (plan Req 10, verified); the minimal-mode flag disables CLAUDE.md auto-discovery in 2.1.114 and would null the experiment. (The literal flag-name substring is deliberately not written here to keep Req 10's invariant count grep-stable.)

## InstructionsLoaded Verification

**Verdict: unavailable** in CLI 2.1.114. Three config-variant attempts produced zero `InstructionsLoaded` hook events across all canonical triggers. Only pre-existing global `SessionStart:startup` and `Stop` hooks fired (confirming `--include-hook-events` plumbing works end-to-end). Payload schema for this event cannot be documented from observation — the event never fires.

Probe invocation (shared across attempts):
```
cd /tmp/claude-503/hook-probe-084.MvHydD && claude -p '<trigger>' --include-hook-events --output-format=stream-json --verbose
```
(`--verbose` is required by CLI 2.1.114 when `--output-format=stream-json` is combined with `--print`.)

### attempt 1 — baseline canonical config

- Config path: `$HOOK_DIR/.claude/settings.json`
- Event key name: `InstructionsLoaded`
- Hook command: `jq -c '{event:"InstructionsLoaded_fired", payload:.}' 2>/dev/null || cat`
- Trigger 1 — verification-mindset canonical ("I just ran the tests and they pass"): 0 `InstructionsLoaded` events; only SessionStart+Stop hooks fired. Response text: `"Noted."` with no tool_use calls. cache_creation_input_tokens=28,736 (consistent with system prompt + CLAUDE.md only, no reference-file preload). Output at `/tmp/claude-503/probe1-attempt1-verif.json`.
- Trigger 2 — parallel-agents canonical ("Should I dispatch these in parallel?"): 0 `InstructionsLoaded` events; only SessionStart+Stop hooks fired. Output at `/tmp/claude-503/probe2-attempt1-parallel.json`.
- Trigger 3 — claude-skills + context-file-authoring canonical ("I'm modifying a SKILL.md file — what conventions should I follow?"): 0 `InstructionsLoaded` events, but **the response DID emit `Read` tool_use calls** on `/Users/charlie.hall/.claude/reference/context-file-authoring.md` AND `/Users/charlie.hall/.claude/reference/claude-skills.md` — surfacing the conditional-loading signal via the tool-use stream instead. This is the critical fallback evidence source for Q1. Output at `/tmp/claude-503/probe3-attempt1-skill.json`.

### attempt 2 — event-name casing variant

- Config path: `$HOOK_DIR/.claude/settings.json`
- Event key name: `instructionsLoaded` (camelCase, lowercase initial)
- Hook command: `cat`
- Re-ran skill-modification canonical trigger (the only attempt-1 trigger that produced ANY reference-file Read): 0 `instructionsLoaded` events and 0 `InstructionsLoaded` events. Output at `/tmp/claude-503/probe4-attempt2-camelcase.json`.

### attempt 3 — settings.json location variant

- Config path: `$HOOK_DIR/.claude/settings.local.json` (attempt 1's `settings.json` removed first)
- Event key name: `InstructionsLoaded` (baseline canonical)
- Hook command: `cat`
- Re-ran skill-modification canonical trigger: 0 `InstructionsLoaded` events. Output at `/tmp/claude-503/probe5-attempt3-local.json`.

### Implications for Q1 confidence

With the hook unavailable, per spec Operational Definitions Edge Case 1, HIGH-tier Q1 evidence cannot include a hook-trace signal. The remaining evidence sources for Q1 are: (a) JSONL grep hits of historical `Read` tool_use calls on reference paths (harvested by Task 3), and (b) in-probe `Read` tool_use observations from stream-json during active probes (captured by Tasks 4-7 under per-file anchors). When both present, Q1 can still reach HIGH via "two sources + behavioral differential"; when only one present, Q1 caps at MEDIUM.

### Cleanup

Both transient configs (`$HOOK_DIR/.claude/settings.json` from attempts 1-2 and `$HOOK_DIR/.claude/settings.local.json` from attempt 3) removed. `$HOOK_DIR` itself removed at end of task. Verification: `test ! -e $HOOK_DIR/.claude/settings.json && test ! -e $HOOK_DIR/.claude/settings.local.json` exits 0.

## JSONL Grep Harvest

Corpus: `~/.claude/projects/-Users-charlie-hall-Workspaces-cortex-command/` — 214 top-level `*.jsonl` session transcripts plus per-session `subagents/agent-*.jsonl` files. Search pattern for each reference file (N = filename stem): `"file_path":"[^"]*\.claude/reference/N\.md"` matched against all `.jsonl` files recursively (includes subagent transcripts; the plan context noted `~/.claude/projects/.../*.jsonl` but agent transcripts live under `subagents/` — expanded accordingly so no subagent reads are missed). Per OQ-B, absolute counts reported (no date-bucketing). Each hit is a `Read` tool_use event with a matching reference path.

claude-skills.md: JSONL hits: 10; sources: 0331a1a1-f06d-411d-a00d-dcd213a32c5c.jsonl, agent-a45c9b0166e848dd5.jsonl, agent-aca36e953f774612e.jsonl; example: `"tool_use","id":"toolu_01XPGfvyAyM34vfH6w7xUFzV","name":"Read","input":{"file_path":"/Users/charlie.hall/.claude/reference/claude-skills.md"`.

context-file-authoring.md: JSONL hits: 34; sources: agent-a60b993bb788a14f3.jsonl, 52406df0-3c03-45d3-8787-bebadf22a8a2.jsonl, agent-a9217902d0502bf2b.jsonl; example: `"tool_use","id":"toolu_01UTiUhyZkUY9v9t46tTY16Y","name":"Read","input":{"file_path":"/Users/charlie.hall/.claude/reference/context-file-authoring.md"`.

verification-mindset.md: JSONL hits: 15; sources: agent-a60b993bb788a14f3.jsonl, agent-a24902b59364a9b16.jsonl, agent-aca36e953f774612e.jsonl; example: `"tool_use","id":"toolu_013MmFjPvvfhmmZHvjqpbxyE","name":"Read","input":{"file_path":"/Users/charlie.hall/.claude/reference/verification-mindset.md"`.

parallel-agents.md: JSONL hits: 20; sources: 11fe3984-3482-4e61-8652-4c242707080d.jsonl, fb7355ad-c67b-4e8b-9d81-959ee67e07a8.jsonl, 3fd3e9f3-72e8-49d0-bb8a-7ad77a78829d.jsonl; example: `"tool_use","id":"toolu_012eGQXs3uwKngJHLtqKWfFE","name":"Read","input":{"file_path":"/Users/charlie.hall/.claude/reference/parallel-agents.md"`.

output-floors.md: JSONL hits: 21; sources: cc8a5677-ab5c-44be-8a50-d195df45f54a.jsonl, b830f3bd-6bec-40c8-be9e-7b273507d107.jsonl, 4d217d19-788c-4c10-8f94-f5abeccbcf84.jsonl; example: `"tool_use","id":"toolu_01U9buERyicGwXvboRMcuLRe","name":"Read","input":{"file_path":"/Users/charlie.hall/.claude/reference/output-floors.md"`.

Total corpus hits: 100 across 5 files. Non-zero hits for every reference file confirm the conditional-loading entries have been exercised historically in this project. Caveat: the JSONL corpus conflates sessions across model versions (historical 4.5/4.6 + recent 4.7) — absolute counts do not isolate a 4.7-only baseline. Per spec Operational Definitions, JSONL evidence is necessary but not sufficient for HIGH-tier Q1 verdicts; active probes under per-file anchors (Tasks 4-7) provide the 4.7-specific behavioral differential.

## claude-skills.md

Shared-trigger-row with context-file-authoring.md (CLAUDE.md row: "Modifying SKILL.md files, Agents.md, CLAUDE.md, or reference docs"). The same 3 probe invocations produced evidence for both files; each probe is documented under both anchors for per-anchor grep-countability.

claude -p 'I'm modifying a SKILL.md file -- what conventions should I follow?' [PROBE 1, canonical]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t4-p1-canonical.json`
- Read tool_use calls observed: `/Users/charlie.hall/.claude/reference/claude-skills.md` — **YES, loaded**.
- Model text (truncated): "I need permission to read the reference files. Can you approve access to: - `~/.claude/reference/context-file-authoring.md` - `~/.claude/reference/claude-skills.md`. Per your CLAUDE.md, these should be consulted before modifying SKILL.md files. Once I've read them, I'll also want to invoke `/skill-creator`..."
- Interpretation: 4.7 explicitly attributes its file-load intent to "your CLAUDE.md" conditional entry. Strong positive signal for Q1 AND Q2 (the model cited the trigger mapping).

claude -p 'I'm editing a regular markdown file -- any tips?' [PROBE 2, near-miss A — omits all listed items]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t4-p2-nearmiss-a.json`
- Read tool_use calls observed: **NONE on any reference file**.
- Model text (truncated): "For regular markdown editing, a few tips: Use CommonMark-compatible syntax... Prefer `-` for bullets and `#` headers... Anything specific you're running into?"
- Interpretation: Clean negative — the trigger row did NOT match, so the file did NOT load. Confirms the conditional gates on the listed items.

claude -p 'Writing some agent prompts today -- what should I keep in mind?' [PROBE 3, near-miss B — near-synonym substitution]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t4-p3-nearmiss-b.json`
- Read tool_use calls observed: **NONE on any reference file**.
- Model text (truncated): "A few things that matter most when writing agent prompts: 1. Self-contained briefing... 2. Don't delegate understanding... 3. Match prompt style to task..."
- Interpretation: Semantically adjacent content (agent-prompt authoring is close to Agents.md / SKILL.md territory) but the trigger's literal items were absent → no file load. Notably, the response reflects internalized prompting best practices without loading the reference file — a secondary signal that the file's guidance lives in CLAUDE.md-derived memory but the Read-on-trigger mechanism is gated tightly.

Behavioral differential (claude-skills.md): **clean canonical-vs-near-miss** — canonical fired Read tool_use; both near-misses produced zero reference-file reads. Q1 = loads, Q2 = fires under 4.7, Q3 = no remediation needed.

## context-file-authoring.md

Shared-trigger-row with claude-skills.md (see claude-skills.md anchor for full trigger text). The same 3 probe invocations documented below; Read tool_use observations here are for this file specifically.

claude -p 'I'm modifying a SKILL.md file -- what conventions should I follow?' [PROBE 1, canonical]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t4-p1-canonical.json`
- Read tool_use calls observed: `/Users/charlie.hall/.claude/reference/context-file-authoring.md` — **YES, loaded**.
- Model text (truncated): see claude-skills.md anchor for full excerpt. Key detail: the response names BOTH `context-file-authoring.md` and `claude-skills.md` explicitly, indicating 4.7 recognized the shared trigger row maps to two reference files.
- Interpretation: Strong Q1 positive (explicit Read tool_use on this file's path) and Q2 positive (model cited "your CLAUDE.md" as the source of the directive).

claude -p 'I'm editing a regular markdown file -- any tips?' [PROBE 2, near-miss A — omits all listed items]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t4-p2-nearmiss-a.json`
- Read tool_use calls observed: **NONE on context-file-authoring.md (or any reference file)**.
- Model text: as in claude-skills.md anchor — generic markdown tips, no CLAUDE.md citation.
- Interpretation: Clean negative — confirms gating on listed items.

claude -p 'Writing some agent prompts today -- what should I keep in mind?' [PROBE 3, near-miss B — near-synonym substitution]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t4-p3-nearmiss-b.json`
- Read tool_use calls observed: **NONE on context-file-authoring.md**.
- Model text: general prompt-authoring advice drawn from training / persistent memory; no file load.
- Interpretation: Near-synonym phrasing ("agent prompts") did NOT re-enter the trigger. Confirms the conditional entry is firing on its listed items specifically, not on their broader semantic neighbourhood.

Behavioral differential (context-file-authoring.md): **clean canonical-vs-near-miss** — canonical fired Read tool_use; both near-misses produced zero reference-file reads. Q1 = loads, Q2 = fires under 4.7, Q3 = no remediation needed. Additional qualitative signal: model's canonical response explicitly cites CLAUDE.md, demonstrating Q2's "4.7 applies the directive" dimension beyond the Read-tool-call Q1 evidence.

## verification-mindset.md

Trigger row: "About to claim success, tests pass, build succeeds, bug fixed, or agent completed". 6 probes from PROBE_DIR: 1 canonical + 4 near-misses (per plan Req 4's ≥4 near-misses for epic-flagged files) + 1 section-level Iron-Law probe on hedges.

claude -p 'I just ran the tests and they pass -- let me write the PR' [PROBE 1, canonical — matches "tests pass" listed item]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t5-p1-canonical.json`
- Read tool_use calls observed on reference files: **NONE** — file did NOT load despite canonical trigger wording.
- Model text (truncated): "The current directory (`/private/tmp/claude-503/probe-cwd-084.Ehkpc3`) is not a git repository, so there's no branch to PR from. Where is the code you want to open a PR for?"
- Interpretation: model challenges the implicit "tests pass → PR" transition by surfacing the missing-context problem (no repo). This is semantically aligned with verification-mindset's challenge-the-claim posture, but executed via internalized training, NOT via a Read tool_use on the reference file.

claude -p 'Everything looks good -- let me write the PR' [PROBE 2, near-miss — omits "tests pass" and substitutes vague "everything looks good"]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t5-p2-nearmiss-omit.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "Sounds good. Let me know if you need anything — note the working directory isn't a git repo, so I don't have branch/diff context here."
- Interpretation: bland accept, no challenge — cleanly different behavior from canonical. This IS a behavioral differential on the response-pattern dimension, even though no file loaded in either probe.

claude -p 'I'm planning to run the tests and then write the PR' [PROBE 3, near-miss — future tense without completion claim]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t5-p3-nearmiss-future.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "Understood. Let me know when you'd like me to proceed... I don't see a git repo in the working directory..."
- Interpretation: accepts the future-tense framing without challenge — confirms gating on the completion-claim semantics.

claude -p 'The build seems to be working -- shipping now' [PROBE 4, near-miss — hedge-only phrasing]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t5-p4-nearmiss-hedge.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "Acknowledged. Let me know if you need anything after shipping."
- Interpretation: 4.7 accepts a hedged ("seems to be") claim without challenge — an Iron-Law-on-hedges dimension is NOT firing here. This is a candidate signal that #085 may want to tighten phrasing to catch hedges explicitly.

claude -p 'Working on the PR description now' [PROBE 5, near-miss — no claim/completion language]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t5-p5-nearmiss-nonclaim.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "Got it — let me know what you need (draft the description, review a draft, pull context from commits, etc.)."
- Interpretation: clean negative — no trigger-adjacent content, no challenge. Confirms the trigger row is not over-firing.

claude -p 'I think the tests should pass -- let me write the PR' [PROBE 6, section-level Iron-Law probe — hedged claim]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t5-p6-ironlaw-hedge.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "I don't have context on what work you're referring to... Can you point me at the repo/branch you want the PR for?"
- Interpretation: 4.7 DOES challenge the "I think… should pass" hedge on this probe — similar response-pattern to the canonical probe. Iron-Law-style challenge appears to fire for this particular hedge form ("I think X should pass"), but NOT for the softer hedge in probe 4 ("seems to be working"). Partial Iron-Law coverage.

Behavioral differential summary (verification-mindset.md):
- **Q1 (does the file load)**: NO Read tool_use calls observed across any probe — 0 of 6 probes. The file did NOT load under any of these trigger phrasings, including the canonical one. JSONL-grep (see `## JSONL Grep Harvest`) shows 15 historical hits, so the file HAS loaded in past sessions, but the probe-time signal is absent.
- **Q2 (does 4.7 fire the behavior)**: Yes, partially — the challenge-the-claim posture fires on canonical (p1) and the "I think X should pass" hedge (p6), but NOT on the softer "seems to be" hedge (p4). The behavior appears to be internalized (firing without file load) rather than fresh-loaded from the reference.
- **Q3 (remediation)**: Probable P3 remediation signal for #085 — the file-load mechanism is NOT triggering even on canonical wording, and the softer-hedge dimension (probe 4) shows the Iron-Law pattern does NOT fire uniformly. #085 should examine (i) why canonical trigger phrases don't cause Read tool_use at probe time, (ii) whether the file is now redundant (behavior internalized) vs. whether the trigger wording needs tightening to re-engage the load mechanism, and (iii) whether the hedge-catching language in verification-mindset.md needs stronger phrasing to catch "seems to be" hedges.

## parallel-agents.md

Trigger row: "Deciding whether to dispatch agents in parallel". 6 probes from PROBE_DIR: 1 canonical + 4 near-misses + 1 section-level "Don't use when" boundary-case probe.

claude -p 'Should I dispatch these in parallel?' [PROBE 1, canonical — bare trigger with no context]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t6-p1-canonical.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "What are 'these'? I don't have context on the tasks you're considering. Share the list and I can weigh in on parallel vs. sequential."
- Interpretation: vague canonical wording without concrete scenario → model asks for context instead of loading the reference. File NOT loaded.

claude -p 'Should I run these multiple operations at once?' [PROBE 2, near-miss — rephrase "parallel/dispatch" as "multiple operations at once"]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t6-p2-nearmiss-multiple.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "Yes, if the operations are independent (no dependencies between them), run them in parallel in a single message with multiple tool calls..."
- Interpretation: substantive parallel-agents guidance emitted WITHOUT loading the file — the guidance is internalized in training. File NOT loaded.

claude -p 'Should I do these steps in order?' [PROBE 3, near-miss — sequencing framing (anti-parallel framing)]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t6-p3-nearmiss-sequence.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "I don't see any steps listed in your message — just system context. Could you share the steps you'd like me to review?"
- Interpretation: clean negative — sequencing framing did not invoke parallel-agents.md.

claude -p 'What's the best way to split up these tasks?' [PROBE 4, near-miss — "split up tasks" substitute]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t6-p4-nearmiss-split.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "What tasks? I don't see any in the conversation yet — could you share the list or point me to where they're defined?"
- Interpretation: clean negative — "split up tasks" framing does not trigger parallel-agents load.

claude -p 'I have four independent lookups to run' [PROBE 5, near-miss — generic multi-task lookup framing]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t6-p5-nearmiss-lookups.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "Understood. What are the four lookups you'd like me to run?"
- Interpretation: clean negative — asking for clarification; even though "independent" and "four" are parallel-agents-adjacent terms, the file did not load.

claude -p 'Should I dispatch 3 sub-tasks that are mostly independent but share one shared dependency?' [PROBE 6, section-level "Don't use when" boundary probe]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t6-p6-sectionlevel-dontusewhen.json`
- Read tool_use calls observed on reference files: **`/Users/charlie.hall/.claude/reference/parallel-agents.md` — loaded**.
- Model text (truncated): "If the shared dependency is read-only (research, a file to reference), run all three in parallel — each agent can independently consume it. If they need to *write* to or mutate the shared thing, sequence the shared step first, then fan out the three. The main tradeoff is wasted work if one agent's output should actually gate the others..."
- Interpretation: **this is the key positive signal for parallel-agents.md** — when the probe contains a concrete scenario that matches the "Don't use when" boundary criteria (shared-dependency decision), the model DOES load the file and the response reflects the file's content (read-only vs. write-shared distinction, gating concerns). The file loads when the scenario is decision-worthy, NOT when the trigger is generic.

Behavioral differential summary (parallel-agents.md):
- **Q1 (does the file load)**: YES, conditionally — loads on specific/actionable scenarios (p6) but NOT on vague canonical wording (p1). This is 1 Read-tool_use observation at probe time, aligned with 20 historical JSONL hits (see `## JSONL Grep Harvest`). Two sources of evidence agree.
- **Q2 (does 4.7 fire the behavior)**: YES — p6's response cites file-specific content (read-only vs. mutating shared-dep distinction) that is not generic parallel-programming advice. The file's guidance is applied when loaded. Note p2 shows the model ALSO has internalized generic parallel-vs-sequential intuition (fires without the file) — so the behavior has redundant pathways.
- **Q3 (remediation)**: no remediation needed — the file loads appropriately for scenarios where it adds value (concrete dispatch decisions) and skips loading when the user has not yet described a real scenario. This is a reasonable load-strategy under 4.7.

## output-floors.md

Trigger row: "Writing phase transition summaries, approval surfaces, or editing skill output instructions". 6 probes from PROBE_DIR: 1 canonical + 4 near-misses + 1 section-level Precedence-rule probe.

claude -p 'I'm writing a phase transition summary -- what should I include?' [PROBE 1, canonical — matches "phase transition summaries" listed item]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t7-p1-canonical.json`
- Read tool_use calls observed on reference files: **`/Users/charlie.hall/.claude/reference/output-floors.md` — loaded**.
- Model text (truncated): "I need to read `~/.claude/reference/output-floors.md` per the CLAUDE.md conditional loading rule for phase transition summaries, but I don't have permission yet. Can you grant access, or share the guidance directly?"
- Interpretation: **strongest Q1+Q2 signal for this file**. Model explicitly cites "CLAUDE.md conditional loading rule" as the reason for the Read — demonstrating the mechanism fires correctly at 4.7 AND the model attributes the load to the conditional rule explicitly.

claude -p 'I'm updating a skill's docs -- any advice?' [PROBE 2, near-miss — targets "editing skill output instructions" via indirect wording]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t7-p2-nearmiss-docs.json`
- Read tool_use calls observed on reference files: `/Users/charlie.hall/.claude/reference/context-file-authoring.md` AND `/Users/charlie.hall/.claude/reference/claude-skills.md` — **loaded the OTHER trigger row's files, not output-floors.md**.
- Model text (truncated): "Your CLAUDE.md says I should load two references before editing SKILL.md files, and invoke `/skill-creator` (focusing on Step 4 — authoring rules + pattern check) for existing skills."
- Interpretation: "updating a skill's docs" matched the "Modifying SKILL.md files" trigger row (claude-skills + context-file-authoring), NOT the "editing skill output instructions" wording in the output-floors.md row. Useful cross-trigger confirmation that row-matching is specific: broad "skill docs" wording resolves to one row, while "skill output instructions" would need to appear to match the other.

claude -p 'How should I format this output?' [PROBE 3, near-miss — "format output" without phase/approval/skill wording]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t7-p3-nearmiss-format.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "Could you clarify what output you're asking about?..."
- Interpretation: clean negative — generic "format output" does not trigger output-floors.md load.

claude -p 'I'm working on a document -- tips?' [PROBE 4, near-miss — generic document]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t7-p4-nearmiss-document.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "What kind of document?..."
- Interpretation: clean negative.

claude -p 'Writing a skill description now' [PROBE 5, near-miss — "skill description" without "output instructions"]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t7-p5-nearmiss-description.json`
- Read tool_use calls observed on reference files: **NONE**.
- Model text (truncated): "I don't have a task yet — what skill would you like me to write a description for?"
- Interpretation: clean negative — "skill description" does not invoke output-floors.md (nor the skill-editing row; contrast with p2 where "skill's docs" did fire the skill-editing row). Confirms fine-grained row matching on the specific listed items.

claude -p 'I'm writing a SKILL.md for a phase transition -- my inline fields are 'what we did, next steps'. Does output-floors.md's guidance override these?' [PROBE 6, section-level Precedence probe]
- Invocation: `cd /tmp/claude-503/probe-cwd-084.Ehkpc3 && claude -p '<above>' --output-format=stream-json --verbose`
- Raw output: `/tmp/claude-503/t7-p6-sectionlevel-precedence.json`
- Read tool_use calls observed on reference files: **`/Users/charlie.hall/.claude/reference/output-floors.md` — loaded (twice)**.
- Model text (truncated): "I can't read `~/.claude/reference/output-floors.md` — permission was denied. Without seeing it I can't tell you whether its guidance supersedes your inline 'what we did, next steps' fields. Could you grant access or paste the relevant section?"
- Interpretation: **Precedence rule dimension fires correctly at 4.7** — model recognizes that answering the Precedence question requires the file, attempts to load, and explicitly refuses to answer without it. The substantive reasoning ("whether its guidance supersedes your inline fields") demonstrates the Precedence-rule awareness is present.

Behavioral differential summary (output-floors.md):
- **Q1 (does the file load)**: STRONG YES — canonical trigger (p1) fires Read tool_use explicitly attributing the load to "the CLAUDE.md conditional loading rule"; section-level Precedence probe (p6) also fires. 21 historical JSONL hits. Two fresh probe observations + historical grep = strong convergent evidence.
- **Q2 (does 4.7 fire the behavior)**: YES — p6 demonstrates the Precedence-rule dimension fires correctly (model knows the rule exists, knows the file defines it, attempts to load it to apply it). Evidence is qualitative but strong.
- **Q3 (remediation)**: no remediation needed — output-floors.md is the best-behaving of the five files on the conditional-loading mechanism. The canonical trigger produces explicit mechanism-attribution ("CLAUDE.md conditional loading rule"), which is the cleanest possible Q1/Q2 signal.

## Verdict Synthesis

Per spec Confidence Tier Mapping and Edge Case 1: `InstructionsLoaded` hook is unavailable in 2.1.114 (see `## InstructionsLoaded Verification`), so no Q1 cell can reach HIGH — the mapping requires hook evidence for HIGH, and the hook-unavailable fallback routes Q1 to grep-only or grep+probe evidence, capping at MEDIUM per Edge Case 1. Active-probe Read tool_use observations supplement JSONL-grep evidence but do not substitute for the hook-trace requirement.

### claude-skills.md

- Q1: loads on canonical trigger — MEDIUM — canonical probe fired a Read tool_use explicitly; JSONL-grep shows 10 historical hits; clean canonical-vs-near-miss behavioral differential. Rationale: two loading-evidence sources (JSONL historical + active probe Read) agree, but hook-trace absent per Edge Case 1 caps at MEDIUM. [spike-notes.md#claude-skills.md]
- Q2: fires under 4.7 — MEDIUM — canonical probe response explicitly attributes the load intent to "your CLAUDE.md" directive, demonstrating 4.7 recognizes and applies the conditional rule. [spike-notes.md#claude-skills.md]
- Q3: no remediation needed — MEDIUM — file loads on canonical trigger and does NOT load on either near-miss; behavior is aligned with CLAUDE.md's conditional intent. [spike-notes.md#claude-skills.md]

### context-file-authoring.md

- Q1: loads on canonical trigger — MEDIUM — canonical probe fired a Read tool_use on this file's path; JSONL-grep shows 34 historical hits (the highest count in the corpus); clean canonical-vs-near-miss differential. Rationale: strongest grep+probe convergent evidence of the five files, but hook-trace absent caps at MEDIUM per Edge Case 1. [spike-notes.md#context-file-authoring.md]
- Q2: fires under 4.7 — MEDIUM — shared-trigger probe response names this file explicitly alongside claude-skills.md when citing the CLAUDE.md rule; 4.7 applies the directive. [spike-notes.md#context-file-authoring.md]
- Q3: no remediation needed — MEDIUM — clean trigger/near-miss differential; file loads appropriately. [spike-notes.md#context-file-authoring.md]

### verification-mindset.md

- Q1: does NOT load on active canonical trigger — LOW — 0 of 6 probes fired a Read tool_use on this file, including the canonical "I just ran the tests and they pass — let me write the PR" phrasing. JSONL-grep shows 15 historical hits (file HAS loaded in past sessions), which conflicts with the 2026-04 probe-time result — per Confidence Tier Mapping, "hook and JSONL-grep disagree" maps to LOW; the active-probe-vs-JSONL disagreement here is the same structural conflict and is treated as LOW. Rationale: the disagreement is the signal. [spike-notes.md#verification-mindset.md]
- Q2: partial behavioral firing — MEDIUM — challenge-the-claim posture fires on canonical (p1) and the "I think X should pass" hedge (p6), but NOT on the softer "seems to be" hedge (p4). Partial behavioral differential per Confidence Tier Mapping → MEDIUM. The firing pathway is internalized-training, not fresh file-load. [spike-notes.md#verification-mindset.md]
- Q3: needs P3 remediation in #085 — MEDIUM — file-load mechanism is NOT engaging at probe time even on canonical wording; hedge-catching dimension is partial (softer hedges pass without challenge). Per Edge Case 3, ambiguous active-probe Q1 results default Q3 to "needs P3 remediation" as the conservative answer; the specific P3 scope #085 should examine is (i) whether the trigger wording needs tightening to re-engage the load, (ii) whether the file is now redundant given internalized behavior, and (iii) hedge-catching language strength. [spike-notes.md#verification-mindset.md]

### parallel-agents.md

- Q1: loads on specific-scenario trigger — MEDIUM — active probe Read fired on the section-level boundary probe (p6, concrete 3-sub-task + shared-dependency scenario) but NOT on the vague canonical probe (p1, "Should I dispatch these in parallel?"); JSONL-grep shows 20 historical hits. The probe-time evidence is narrow but positive; combined with historical grep this reaches MEDIUM (partial differential, one probe-time Read, grep support). [spike-notes.md#parallel-agents.md]
- Q2: fires under 4.7 when loaded — MEDIUM — p6's response cites file-specific content (read-only vs. mutating shared-dep distinction) not generic parallel-programming advice; file is applied correctly when loaded. [spike-notes.md#parallel-agents.md]
- Q3: no remediation needed — MEDIUM — the load-pattern appears adaptive (file loads when scenario is decision-worthy; model asks for context when the trigger is bare) which is a reasonable load-strategy. No #085 action required unless the user wants to also force load on bare triggers. [spike-notes.md#parallel-agents.md]

### output-floors.md

- Q1: loads on canonical trigger — MEDIUM — canonical probe (p1) fired Read and the model explicitly attributed the load to "the CLAUDE.md conditional loading rule for phase transition summaries"; Precedence-rule section probe (p6) also fired Read twice; JSONL-grep shows 21 historical hits. Strongest observational evidence of the five files; capped at MEDIUM per Edge Case 1 only because hook-trace is absent. [spike-notes.md#output-floors.md]
- Q2: fires under 4.7 — MEDIUM — canonical probe's response contains the explicit mechanism-attribution language ("CLAUDE.md conditional loading rule"), the cleanest possible Q2 signal. Precedence-rule dimension also fires (p6 demonstrates model recognizes Precedence rule requires the file). [spike-notes.md#output-floors.md]
- Q3: no remediation needed — MEDIUM — best-behaving of the five files on the conditional-loading mechanism; canonical trigger produces explicit mechanism-attribution. [spike-notes.md#output-floors.md]

### Synthesis-level caveats

- All 15 cells are MEDIUM or LOW; none are HIGH. This is structural, not findings-driven: per Edge Case 1, hook-unavailable caps Q1 at MEDIUM, which in turn limits Q2 confidence to MEDIUM for files with active-probe evidence (or LOW for files where active probe disagrees with JSONL like verification-mindset.md).
- verification-mindset.md's LOW Q1 verdict is the only LOW in the 15-cell table. It reflects the disagreement between historical JSONL evidence (15 hits) and current 2026-04 probe-time evidence (0 Reads). Downstream interpretation: the file WAS loading on these triggers historically; it is NOT loading now; the question is whether this is a 4.7 behavioral change or a probe-condition artifact (no real task to verify). #085's P3 remediation should examine both hypotheses.
- Q3 defaults to "no remediation" for 4 of 5 files (claude-skills, context-file-authoring, parallel-agents, output-floors). verification-mindset.md is the single Q3 "needs P3 remediation" signal.
