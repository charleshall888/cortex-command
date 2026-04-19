# Reference-Loading Verification under Opus 4.7 (spike deliverable)

Spike resolving **OQ5** from the epic [research/opus-4-7-harness-adaptation/research.md](./research.md): whether Opus 4.7's stricter instruction-following changes the conditional-loading behavior of the five reference files that `~/.claude/CLAUDE.md` maps via its natural-language conditional table (`verification-mindset.md`, `parallel-agents.md`, `claude-skills.md`, `context-file-authoring.md`, `output-floors.md`). Per-file verdicts gate ticket #085's remediation scope and DR-1's firmness. Raw evidence captured in `lifecycle/verify-claude-reference-md-conditional-loading-behavior-under-opus-47/spike-notes.md` (anchors referenced throughout).

## Verdicts

| File | Q1: Loads on trigger? | Q2: Fires under 4.7? | Q3: Needs P3 remediation in #085? | Confidence | Evidence summary |
|------|-----------------------|----------------------|-----------------------------------|-----------|-------------------|
| `claude-skills.md` | Yes — canonical probe fired a Read tool_use; clean near-miss differential [spike-notes.md#claude-skills.md] | Yes — model response explicitly attributes load to "your CLAUDE.md" directive [spike-notes.md#claude-skills.md] | No, no remediation needed [spike-notes.md#claude-skills.md] | Q1:MEDIUM / Q2:MEDIUM / Q3:MEDIUM | 10 JSONL historical hits + 1 probe-time Read; canonical/near-miss differential clean [spike-notes.md#claude-skills.md] |
| `context-file-authoring.md` | Yes — canonical probe fired a Read tool_use; 34 historical JSONL hits (highest in corpus) [spike-notes.md#context-file-authoring.md] | Yes — shared-trigger-row response names both files explicitly when citing the CLAUDE.md rule [spike-notes.md#context-file-authoring.md] | No, no remediation needed [spike-notes.md#context-file-authoring.md] | Q1:MEDIUM / Q2:MEDIUM / Q3:MEDIUM | 34 JSONL hits + 1 probe-time Read; both near-misses produced zero reference loads [spike-notes.md#context-file-authoring.md] |
| `verification-mindset.md` | Inconsistent — 15 historical JSONL hits but 0 probe-time Reads across 6 probes (canonical + 4 near-miss + 1 Iron-Law) [spike-notes.md#verification-mindset.md] | Partial — challenge-the-claim posture fires on canonical (p1) and "I think X should pass" hedge (p6) but NOT on softer "seems to be" hedge (p4); behavior internalized, not fresh-loaded [spike-notes.md#verification-mindset.md] | Yes, needs P3 remediation in #085 [spike-notes.md#verification-mindset.md] | Q1:LOW / Q2:MEDIUM / Q3:MEDIUM | JSONL-vs-probe disagreement triggers LOW Q1 per Confidence Tier Mapping; Edge Case 3 routes Q3 to "needs P3" when probe-time evidence is ambiguous [spike-notes.md#verification-mindset.md] |
| `parallel-agents.md` | Yes, conditionally — loads on concrete-scenario "Don't use when" probe (p6) but NOT on the vague canonical trigger (p1) [spike-notes.md#parallel-agents.md] | Yes when loaded — p6 response cites file-specific content (read-only vs. mutating shared-dep distinction), not generic parallelism advice [spike-notes.md#parallel-agents.md] | No, no remediation needed [spike-notes.md#parallel-agents.md] | Q1:MEDIUM / Q2:MEDIUM / Q3:MEDIUM | 20 JSONL hits + 1 probe-time Read on concrete scenario; load-strategy appears adaptive (loads when decision-worthy) [spike-notes.md#parallel-agents.md] |
| `output-floors.md` | Yes — canonical probe fired Read AND the Precedence-rule section probe fired Read twice; model explicitly attributed the load to "the CLAUDE.md conditional loading rule for phase transition summaries" [spike-notes.md#output-floors.md] | Yes — canonical response contains the cleanest possible mechanism-attribution language in the five-file corpus [spike-notes.md#output-floors.md] | No, no remediation needed [spike-notes.md#output-floors.md] | Q1:MEDIUM / Q2:MEDIUM / Q3:MEDIUM | 21 JSONL hits + 2 probe-time Reads; best-behaving of the five files [spike-notes.md#output-floors.md] |

### Summary of findings

Four of five files (`claude-skills.md`, `context-file-authoring.md`, `parallel-agents.md`, `output-floors.md`) show the conditional-loading mechanism firing under Opus 4.7 — via active Read tool_use observations + historical JSONL convergent evidence. The one exception is `verification-mindset.md`, whose canonical trigger "I just ran the tests and they pass — let me write the PR" did NOT fire a Read tool_use in any of 6 probe attempts despite 15 historical JSONL hits. Its challenge-the-claim *behavior* still fires (on canonical and on the "I think X should pass" hedge) but appears to be internalized from training rather than freshly loaded. Ticket #085's P3 remediation scope should focus on `verification-mindset.md` specifically; the other four files need no P3 work based on this spike's evidence. DR-1's contracted scope stands for the four passing files; a narrow caveat for `verification-mindset.md` should be surfaced in #085's plan.

No cell in the verdict table reaches HIGH confidence — this is a structural consequence of the `InstructionsLoaded` hook being unavailable in CLI 2.1.114 (three config-variant attempts produced 0 hook events for any trigger), which per spec Confidence Tier Mapping caps Q1 at MEDIUM for all files regardless of how strong the grep + probe evidence is.

## Methodology

### Q1 evidence sources

Three candidate evidence sources were considered per file; hook availability was not in the spike's control and fell through to the fallback:

1. **`InstructionsLoaded` hook** (positive control): attempted in three config variants in `$HOOK_DIR/.claude/settings.json` (project-local canonical name, camelCase event name, settings.local.json location). All three produced zero hook events across canonical-trigger probes [spike-notes.md#InstructionsLoaded Verification]. Hook declared **unavailable** in CLI 2.1.114. Per spec Edge Case 1, this caps every Q1 cell at MEDIUM.
2. **JSONL grep against the corpus** `~/.claude/projects/-Users-charlie-hall-Workspaces-cortex-command/*.jsonl` (214 top-level transcripts + `subagents/agent-*.jsonl`): per-file hit counts computed by matching `Read` tool_use `file_path` entries against both `~/.claude/reference/<name>.md` and `/Users/charlie.hall/.claude/reference/<name>.md` forms [spike-notes.md#JSONL Grep Harvest]. Results: claude-skills.md=10, context-file-authoring.md=34, verification-mindset.md=15, parallel-agents.md=20, output-floors.md=21 (total: 100).
3. **Active `claude -p` probes from the probe-isolation regime**: per-file paired probes documented below under "Probe wordings". This is the probe-time Q1 signal — a Read tool_use on the reference file during the probe session is direct evidence the conditional entry fired under 4.7.

### Probe-isolation regime (`claude -p` invocation)

All active probes run from `/tmp/claude-503/probe-cwd-084.Ehkpc3` — a `mktemp -d` directory containing no `.claude/` subdirectory and no project-local `CLAUDE.md`, so user-global `~/.claude/CLAUDE.md` auto-discovery applies in its canonical form. The invocation shape is:

```
cd $PROBE_DIR && claude -p '<probe text>' --output-format=stream-json --verbose
```

`--verbose` is required by CLI 2.1.114 when `--print` is combined with `--output-format=stream-json`. No minimal-mode flag is used (the minimal-mode flag disables CLAUDE.md auto-discovery, which would null the experiment). Hook verification (Task 2 only) used a separate `$HOOK_DIR` that was torn down after.

### Canonical and near-miss probe wordings per file

- `claude-skills.md` + `context-file-authoring.md` (shared trigger row "Modifying SKILL.md files, Agents.md, CLAUDE.md, or reference docs"):
  - Canonical: "I'm modifying a SKILL.md file -- what conventions should I follow?"
  - Near-miss A (omit all listed items): "I'm editing a regular markdown file -- any tips?"
  - Near-miss B (near-synonym substitution): "Writing some agent prompts today -- what should I keep in mind?"

- `verification-mindset.md` (trigger row "About to claim success, tests pass, build succeeds, bug fixed, or agent completed"; epic-flagged → ≥4 near-misses):
  - Canonical: "I just ran the tests and they pass -- let me write the PR"
  - Near-miss 1 (omit "tests pass"): "Everything looks good -- let me write the PR"
  - Near-miss 2 (future tense, no completion claim): "I'm planning to run the tests and then write the PR"
  - Near-miss 3 (hedge-only phrasing): "The build seems to be working -- shipping now"
  - Near-miss 4 (no claim/completion language): "Working on the PR description now"
  - Section-level Iron-Law-on-hedges probe: "I think the tests should pass -- let me write the PR"

- `parallel-agents.md` (trigger row "Deciding whether to dispatch agents in parallel"; epic-flagged → ≥4 near-misses):
  - Canonical: "Should I dispatch these in parallel?"
  - Near-miss 1 (rephrase "parallel/dispatch"): "Should I run these multiple operations at once?"
  - Near-miss 2 (sequence framing): "Should I do these steps in order?"
  - Near-miss 3 ("split up tasks" substitute): "What's the best way to split up these tasks?"
  - Near-miss 4 (generic multi-task framing): "I have four independent lookups to run"
  - Section-level "Don't use when" boundary probe: "Should I dispatch 3 sub-tasks that are mostly independent but share one shared dependency?"

- `output-floors.md` (trigger row "Writing phase transition summaries, approval surfaces, or editing skill output instructions"; epic-flagged → ≥4 near-misses):
  - Canonical: "I'm writing a phase transition summary -- what should I include?"
  - Near-miss 1 ("skill docs" indirect): "I'm updating a skill's docs -- any advice?"
  - Near-miss 2 (generic "format output"): "How should I format this output?"
  - Near-miss 3 (generic document): "I'm working on a document -- tips?"
  - Near-miss 4 ("skill description" only): "Writing a skill description now"
  - Section-level Precedence-rule probe: "I'm writing a SKILL.md for a phase transition -- my inline fields are 'what we did, next steps'. Does output-floors.md's guidance override these?"

### Per-file evidence tie-breaker

Per spec Confidence Tier Mapping and Edge Case 1: with `InstructionsLoaded` unavailable, Q1 confidence tier ceiling is MEDIUM regardless of how many convergent non-hook sources agree. When JSONL-grep and active probe disagree (JSONL says the file loaded historically; active probe shows no Read at probe time), the cell is LOW — this is the `verification-mindset.md` case. When both non-hook sources agree (grep + probe both show loading) and the behavioral differential is clean, the cell is MEDIUM — four of five files.

## Limitations

1. **Absolute current-state framing, no 4.6-vs-4.7 delta**: per OQ-B resolution, verdicts are framed as absolute current-state under CLI 2.1.114 + `claude-opus-4-7[1m]`. No historical comparison to 4.6 is claimed; the question "did this regress from 4.6" is explicitly out of scope. Ticket #085 receives current-state evidence only.

2. **Mechanism-wide proxy**: the same natural-language conditional-loading pattern is also used in `requirements/project.md` (and potentially other rule documents). This 5-file verdict is a proxy for mechanism-wide behavior; a sixth conditional-loading entry (if added) is out of scope per spec Non-Requirements, and this spike's verdicts do NOT generalize to conditional entries that use different trigger-row phrasing conventions.

3. **Sample size**: n=24 active probes total across 5 files (3 shared-trigger + 6 per epic-flagged × 3 files = 24 with a shared set of 3 counted once; effectively 24 distinct invocations across 4 anchors' probe coverage, documented as 24 `claude -p` lines in spike-notes.md). Per-file-anchor n ranges from 3 (claude-skills.md, context-file-authoring.md — shared trigger) to 6 (verification-mindset.md, parallel-agents.md, output-floors.md — epic-flagged). Historical JSONL n=100 hits across the 214-transcript corpus. These counts are modest — statistically unremarkable — and MEDIUM-tier confidence on most cells reflects that.

4. **Hook availability caveat**: `InstructionsLoaded` hook was verified unavailable in CLI 2.1.114 via three config-variant attempts [spike-notes.md#InstructionsLoaded Verification]. Even when hooks are available in a future CLI release, a hook event only tells you whether a file was *loaded but not whether* the model actually applied the guidance — the behavioral-differential probe evidence remains the Q2 signal, not the hook alone.

5. **Probe-dir context may suppress legitimate loads**: the probe-isolation regime strips project-level `.claude/` and CLAUDE.md so that only user-global CLAUDE.md's conditional table applies. This is the spec's canonical regime, but it also removes the "real task in progress" context that may be part of the trigger conditions. For verification-mindset.md specifically, the probes ran from a non-git-repo directory with no actual test output to verify — it is possible that 4.7's load decision depends on "is there an actionable task" rather than "is the trigger phrase present". This is one hypothesis for the Q1 LOW verdict on verification-mindset.md and should be evaluated by #085 before any reference-file rewrite.

## Reopener clause

If execution of #085's remediation surface surfaces evidence of over-firing (files loading when they should not) or additional non-loading (files failing to load for triggers this spike marked as "loads") not covered by this spike's 5-file scope or probe-phrasing set, **#085 must expand** its scope to investigate the new evidence rather than deferring to this spike's verdicts. Specifically, `verification-mindset.md`'s Q1 LOW verdict should be validated by #085 via at least one probe run that includes an actionable task context (e.g., an actual git repo + recent commit claiming "tests pass") before any mitigation is designed.
