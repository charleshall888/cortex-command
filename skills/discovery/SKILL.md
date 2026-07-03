---
name: discovery
description: Ideation research for topics not ready for implementation — checks aim, investigates the problem space, then decomposes findings into backlog tickets grouped by epic. Use when user says "/cortex-core:discovery", "discover this", "break this down into tickets", "decompose into backlog", or wants to understand a topic before committing to build. Requires a topic argument; for "what should I work on" or "next task" routing without a specific topic, use /cortex-core:dev instead.
when_to_use: "Use when investigating a topic deeply before committing to build it. Different from /cortex-core:research — research produces a research.md and stops; discovery wraps clarify→research→decompose and ends with backlog tickets. Different from /cortex-core:lifecycle — discovery stops at backlog tickets rather than proceeding to plan/implement."
argument-hint: "<topic>"
inputs:
  - "topic: string (required) — the topic or feature area to research and decompose into backlog tickets"
  - "phase: string (optional) — explicit phase to enter: clarify|research|decompose"
outputs:
  - "cortex/backlog/NNN-{{topic}}.md — decomposed backlog tickets grouped by epic"
  - "cortex/research/{{topic}}/ — durable research artifact"
preconditions:
  - "Run from project root"
  - "cortex/backlog/ directory exists"
---

# Discovery

## Step 1: Identify the Topic

Topic: $ARGUMENTS (required — non-empty topic).

Determine the `{{topic}}` from invocation. Use lowercase-kebab-case for directory naming (e.g., `cortex/research/plugin-system/`).

**If `$ARGUMENTS` is empty**: halt with the message "discovery requires a topic argument; for 'what should I work on' or 'next task' routing, use `/cortex-core:dev` instead." Do not proceed to Step 2.

## Step 2: Check for Existing State

Scan for `cortex/research/{{topic}}/` at the project root:

```
if no cortex/research/{{topic}}/ directory exists:
    phase = clarify
elif research.md exists and no decomposed.md:
    phase = decompose
elif decomposed.md exists:
    phase = complete (offer to re-run or update)
```

If resuming, report the detected phase and offer to continue or restart from an earlier phase.

### Re-run slug-collision semantics (spec R13)

When the user invokes `/cortex-core:discovery` on a topic whose `cortex/research/{{topic}}/` directory already exists AND the user elects to re-run from scratch (rather than resume or update in place), the agent does NOT overwrite the prior artifact. Instead:

(a) **Fresh slug**: compute a new slug of the form `{{topic}}-N` where N is the smallest integer ≥ 2 making the resulting slug unique on disk. For example, if `cortex/research/plugin-system/` already exists, the first re-run produces `cortex/research/plugin-system-2/`; a second re-run produces `cortex/research/plugin-system-3/`; and so on. The collision check considers every entry directly under `cortex/research/` so prior re-runs are honored.
(b) **`superseded:` frontmatter on the new artifact**: the newly created `cortex/research/{{topic}}-N/research.md` begins with a YAML frontmatter block that includes a `superseded:` key whose value is the relative path of the prior artifact it supersedes (e.g. `superseded: cortex/research/plugin-system/research.md`). When the re-run itself supersedes an existing `-N` artifact, the `superseded:` value points at that immediately-prior `-N` artifact, not the original.
(c) **Prior artifact untouched**: the existing `cortex/research/{{topic}}/` (or prior `-N`) directory is read-only for this re-run. No files in it are renamed, moved, or deleted; the decomposed.md (if any) remains in place as a durable audit trail.
(d) **Reconciliation is manual**: the agent does NOT automatically reconcile the new architecture with the prior one. Surfacing differences, choosing which slug downstream `discovery_source:` fields should point at, and any archival of the prior artifact are explicit user decisions made outside the discovery skill.

Events for re-runs route to `cortex/research/{{topic}}-N/events.log` via the helper module's `resolve-events-log-path` subcommand (see Step 2's `cortex-discovery` invocations below), which inspects the slug for a `-N` suffix and returns the correctly-suffixed path. Skill prose should resolve event-log paths through the helper rather than hardcoding `cortex/research/{topic}/events.log`, so re-runs do not bleed events into the superseded artifact's log.

## Step 3: Execute Current Phase

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Clarify | [clarify.md](${CLAUDE_SKILL_DIR}/references/clarify.md) | none (conversation output only) |
| Research | [research.md](${CLAUDE_SKILL_DIR}/references/research.md) | `cortex/research/{{topic}}/research.md` |
| Decompose | [decompose.md](${CLAUDE_SKILL_DIR}/references/decompose.md) | Epic + backlog tickets |

Read **only** the reference for the current phase.

**Sibling-path propagation (load-bearing).** Both `clarify.md` and `research.md` need to load two files that live in the **lifecycle sibling** skill, not in discovery's own `references/` directory: the shared requirements-loading protocol and the fan-out sizing matrix. Resolve them here in the body (where `${CLAUDE_SKILL_DIR}/../lifecycle/…` resolves) and carry the absolute paths into the phase. When you read the current-phase reference, substitute these body-resolved absolute paths wherever it directs you to the lifecycle sibling:

- **load-requirements** → `${CLAUDE_SKILL_DIR}/../lifecycle/references/load-requirements.md`
- **fanout** (research-sizing matrix) → `${CLAUDE_SKILL_DIR}/../research/references/fanout.md`
- **orchestrator-review** (canonical protocol) → `${CLAUDE_SKILL_DIR}/../lifecycle/references/orchestrator-review.md`
- **fix-agent-prompt-template** → `${CLAUDE_SKILL_DIR}/../lifecycle/references/fix-agent-prompt-template.md`

### Research → Decompose approval gate (spec R4)

Between the Research and Decompose phases a single-question user-blocking gate fires. The gate's first content section is the contents of `cortex/research/<topic>/brief.md`, generated via:

```
cortex-discovery generate-brief \
    --research-md cortex/research/<topic>/research.md \
    --persist-to cortex/research/<topic>/brief.md
```

If brief generation exits non-zero, OR `brief.md` is missing after the command runs, OR `brief.md` fails decision-content validation, the gate falls back to displaying the dense `## Architecture` section (sub-sections `### Pieces` and `### How they connect`) and surfaces a warning naming the failure condition (`brief_generation_failed: <reason>`). When `brief.md` is present, the generator exited 0, and the decision-content anchors pass — but the brief's word count exceeds the advisory cap — the gate still displays the brief (the cap is advisory, not a posting gate), followed by a one-line overage note such as "(summary ran N words over the 275-word advisory cap)". No decompose work begins until the user answers. Four options:

- **`approve`** — continue to the Decompose phase. The agent emits one `approval_checkpoint_responded` event with `checkpoint: research-decompose`, `response: approve`, and the current `revision_round` integer, then proceeds.
- **`revise`** — open a free-text revision prompt scoped to the Architecture section. The agent re-walks the Architecture section against the live template in `references/research.md` §6, re-emitting `### Pieces` (named by role, per the role-naming convention) then `### How they connect`, and applying the template's soft "consider merging" guidance when the piece count grows large. It re-presents the gate and increments `revision_round`. Emits one `approval_checkpoint_responded` event with `response: revise` per loop iteration. Loop continues until `approve` or `drop`.
- **`drop`** — neutral terminus: close discovery when research is sufficient and no tickets are warranted, OR abandon outright. Both uses are legitimate; the user selects `drop` whenever they want to exit without filing tickets, regardless of motive. The agent emits one `approval_checkpoint_responded` event with `response: drop` and exits without writing to `cortex/backlog/`. The research artifact stays in place as a durable audit trail.
- **`promote-sub-topic`** — minimal-surface affordance per spec R4 + Non-Requirements: the user supplies a sub-topic description, and the agent invokes `/backlog-author compose` with the sub-topic description as the context block (including a pre-resolved `## Promoted from` section reading exactly `## Promoted from\n\nDiscovery: cortex/research/<current-topic>/`), captures the returned body. Resolve the active backend once with `` `cortex-read-backlog-backend` `` (argless; it prints the resolved backend and exits 0) and route the create: on **`cortex-backlog`** (the default arm) proceed exactly as today, calling `cortex-create-backlog-item --title "investigate ..." --status needs-discovery --type discovery --body "<composed-body>"` to create a single `needs-discovery` backlog ticket; on **`none`** do not call the create CLI — instead surface the composed title and body inline in `cortex/research/<current-topic>/` so no authored work is lost, with a one-line advisory that ticket creation is disabled for this repo; on **any other value** (an external tracker) create the equivalent `needs-discovery` item best-effort on the configured tracker using the config `backlog.instructions` and your own judgment (e.g. `gh issue create`), surfacing the composed body inline if it cannot be filed. No frontmatter linkage field is introduced — the body-section reference is the sole linkage (no consumer reads a frontmatter pointer). No nested `/cortex-core:discovery` invocation. After the create routing resolves, the agent emits one `approval_checkpoint_responded` event with `response: promote-sub-topic` and returns to this gate so the user can still `approve`, `revise`, or `drop` the current Architecture section.

All emissions go through the helper module — never hardcode the events.log path. Invoke via:

```
cortex-discovery emit-checkpoint-response \
    --topic <topic> --checkpoint research-decompose \
    --response <approve|revise|drop|promote-sub-topic> \
    --revision-round <int>
```

The helper resolves the correct events.log target (lifecycle-attached, R13 re-run `-N` slug, or standalone `cortex/research/<topic>/events.log`) via its `resolve-events-log-path` subcommand. See `cortex_command/discovery.py` for the full subcommand surface.

### Decompose-commit batch-review gate

Within the Decompose phase, a user-blocking post-decompose batch-review gate (`checkpoint: decompose-commit`) fires after all ticket bodies are authored and the prescriptive-prose scanner has passed, BEFORE any tickets commit to `cortex/backlog/`. The gate offers `approve-all`, `revise-piece <N>`, `drop-piece <N>`, `consolidate-pieces <N,M,...>`, and `split-piece <N>` options and emits an `approval_checkpoint_responded` event per response. See decompose.md §5 for the gate semantics.

## Phase Transition

After completing a phase artifact, commit the `cortex/research/{{topic}}/` directory, summarize findings, and proceed to the next phase automatically.

## Multiple Discoveries

One active discovery at a time. If multiple incomplete `cortex/research/*/` directories exist (those without `decomposed.md`), list them and ask which to resume.

## Relationship to /cortex-core:lifecycle

When `/cortex-core:discovery` creates backlog tickets, each ticket receives a `discovery_source:` field pointing to the research artifact. When `/cortex-core:lifecycle` starts on that ticket, it automatically loads the prior research, presents a summary, and asks whether to skip re-investigation (default: skip). In pipeline or overnight contexts the skip is applied automatically. To re-investigate from scratch, choose N at the prompt.
