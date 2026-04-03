# Orchestrator Patterns

Reference for skills that classify, route, or pipeline work to other skills rather than executing tasks directly. Three distinct patterns — choose the one that matches the structure of the work.

## Pattern 1: Intent Classifier

**When to use**: The user can ask for several different things, each requiring a different downstream skill. The skill's job is to read the request, identify which case applies, and delegate.

**Structure**:

```
## Step 1: Classify Intent

Read the request and match against these cases (first match wins):

- **Case A** [trigger signals]: → delegate to /skill-a
- **Case B** [trigger signals]: → delegate to /skill-b
- **Case C** [trigger signals]: → delegate to /skill-c
- **Default**: [what to do if no case matches — ask the user, or pick the closest match]

## Step 2: Delegate

Invoke the matched skill. Pass relevant context from the original request.
```

**Handling ambiguity**: When the request matches two cases equally, surface the ambiguity to the user with a direct question ("Did you mean X or Y?"). Do not silently pick one.

**Handling no match**: If no case matches and a reasonable default exists, use it and explain. If there is no reasonable default, ask rather than guess.

**Example**: `dev` — classifies user intent into research, lifecycle, backlog, discovery, or direct implementation, then routes to the matching skill.

---

## Pattern 2: Sequential Processor

**When to use**: The work has multiple phases that must run in order. Each phase builds on the previous one. The skill must be resumable — if interrupted, the next invocation should pick up from where it left off.

**Structure**:

```
## Step 1: Detect Phase

Read the state file (or event log) to determine the current phase:

if no state file exists:
    phase = start
elif state.phase == "research":
    phase = specify
elif state.phase == "specify":
    phase = plan
...

## Step 2: Execute Current Phase

Based on the detected phase, run the corresponding work. Each phase ends by
updating the state file to record completion and advance to the next phase.

## Step 3: Transition (or Complete)

If more phases remain, update state and announce the next phase.
If all phases are complete, clean up ephemeral state and summarize.
```

**State file conventions**: Use a mutable JSON file for current-phase tracking (overwritten at each checkpoint). Use a JSONL append-only log for audit history. See `~/.claude/skills/skill-creator/references/state-patterns.md` for the canonical idioms.

**Approval gates**: Some phases require user approval before the next phase begins. Make these explicit — announce the completed phase, present the output, and wait for confirmation before advancing.

**Handling restart**: If the user explicitly requests starting over, delete or reset the state file and begin from phase 1.

**Example**: `evolve` — reads `.evolve-state.json` at invocation, determines which trend-processing phase to resume, runs that phase, updates state.

---

## Pattern 3: Layered Pipeline

**When to use**: The work consists of fixed, ordered layers where each layer produces a result artifact. Later layers can be skipped based on earlier results (e.g., skip if a prerequisite isn't met, or short-circuit on failure).

**Structure**:

```
## Step 1: Run Layer 0 — [prerequisite/setup check]

[Execute layer 0 work]
Write result to: results/layer0.json

If layer 0 fails with a blocking error: stop and report. Do not proceed.
If layer 0 produces warnings only: continue to Layer 1.

## Step 2: Run Layer 1 — [primary check]

[Execute layer 1 work]
Write result to: results/layer1.json

If layer 1 fails: stop. Report layer 1 errors. Do not proceed to Layer 2.

## Step 3: Run Layer 2 — [secondary/conditional check]

[Execute layer 2 work, which may depend on Layer 1 output]
Write result to: results/layer2.json

## Step 4: Summarize

Merge results from all layers into results/summary.json.
Present a compact report: layers run, pass/fail per layer, total issues found.
```

**Skip conditions**: When a layer has a precondition (e.g., a dev server must be running), check before running and skip gracefully if not met. Always report that the layer was skipped and why — do not silently omit it.

**Result artifacts**: Each layer writes its own result file. The final step merges them. This lets callers read individual layer results without re-running the pipeline.

**Exit behavior**: The pipeline always exits cleanly (no non-zero exits that block callers). Failures are represented in the result artifacts, not as process exits.

**Example**: `ui-check` — runs design validation (Layer 0), lint (Layer 1), and accessibility checks (Layer 2) in fixed order, writing `ui-check-results/*.json` at each layer.

---

## Choosing Between Patterns

| Signal | Pattern |
|--------|---------|
| User can ask for N different things | Intent Classifier |
| Work has ordered phases, must be resumable | Sequential Processor |
| Work has fixed layers, later layers depend on earlier ones | Layered Pipeline |
| Phases need approval gates between them | Sequential Processor |
| Layers run unconditionally (unless precondition fails) | Layered Pipeline |
| Each path through the skill is completely different | Intent Classifier |
