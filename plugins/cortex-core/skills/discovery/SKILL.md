---
name: discovery
description: Ideation research for topics not ready for implementation — checks aim, investigates the problem space, then decomposes findings into backlog tickets grouped by epic. Use when user says "/cortex-core:discovery", "discover this", "research and ticket", "break this down into tickets", "decompose into backlog", "create an epic for", "investigate before building", "what should I discover", or wants to understand a topic before committing to build. Requires a topic argument; for "what should I work on" or "next task" routing without a specific topic, use /cortex-core:dev instead.
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

## Invocation

- `/cortex-core:discovery {{topic}}` — start new or resume existing discovery
- `/cortex-core:discovery {{phase}}` — jump to a specific phase (clarify, research, decompose)

## Step 1: Identify the Topic

Topic: $ARGUMENTS (required — non-empty topic).

Determine the `{{topic}}` from invocation. Use lowercase-kebab-case for directory naming (e.g., `cortex/research/plugin-system/`).

**If `$ARGUMENTS` is empty**: halt with the message "discovery requires a topic argument; for 'what should I work on' or 'next task' routing, use `/cortex-core:dev` instead." Do not proceed to Step 2.

**If a topic was provided**: proceed to Step 2 directly.

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

Backward compat: existing discoveries that have `spec.md` but no `decomposed.md` will also have `research.md` present and correctly resume at `phase = decompose`.

If resuming, report the detected phase and offer to continue or restart from an earlier phase.

### Re-run slug-collision semantics (spec R13)

When the user invokes `/cortex-core:discovery` on a topic whose `cortex/research/{{topic}}/` directory already exists AND the user elects to re-run from scratch (rather than resume or update in place), the agent does NOT overwrite the prior artifact. Instead:

(a) **Fresh slug**: compute a new slug of the form `{{topic}}-N` where N is the smallest integer ≥ 2 making the resulting slug unique on disk. For example, if `cortex/research/plugin-system/` already exists, the first re-run produces `cortex/research/plugin-system-2/`; a second re-run produces `cortex/research/plugin-system-3/`; and so on. The collision check considers every entry directly under `cortex/research/` so prior re-runs are honored.
(b) **`superseded:` frontmatter on the new artifact**: the newly created `cortex/research/{{topic}}-N/research.md` begins with a YAML frontmatter block that includes a `superseded:` key whose value is the relative path of the prior artifact it supersedes (e.g. `superseded: cortex/research/plugin-system/research.md`). When the re-run itself supersedes an existing `-N` artifact, the `superseded:` value points at that immediately-prior `-N` artifact, not the original.
(c) **Prior artifact untouched**: the existing `cortex/research/{{topic}}/` (or prior `-N`) directory is read-only for this re-run. No files in it are renamed, moved, or deleted; the decomposed.md (if any) remains in place as a durable audit trail.
(d) **Reconciliation is manual**: the agent does NOT automatically reconcile the new architecture with the prior one. Surfacing differences, choosing which slug downstream `discovery_source:` fields should point at, and any archival of the prior artifact are explicit user decisions made outside the discovery skill.

Events for re-runs route to `cortex/research/{{topic}}-N/events.log` via the helper module's `resolve-events-log-path` subcommand (see Step 2's `python3 -m cortex_command.discovery` invocations below), which inspects the slug for a `-N` suffix and returns the correctly-suffixed path. Skill prose should resolve event-log paths through the helper rather than hardcoding `cortex/research/{topic}/events.log`, so re-runs do not bleed events into the superseded artifact's log.

## Step 3: Execute Current Phase

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Clarify | [clarify.md](${CLAUDE_SKILL_DIR}/references/clarify.md) | none (conversation output only) |
| Research | [research.md](${CLAUDE_SKILL_DIR}/references/research.md) | `cortex/research/{{topic}}/research.md` |
| Decompose | [decompose.md](${CLAUDE_SKILL_DIR}/references/decompose.md) | Epic + backlog tickets |

Read **only** the reference for the current phase.

### Research → Decompose approval gate (spec R4)

Between the Research and Decompose phases a single-question user-blocking gate fires, presenting the approved `## Architecture` section (sub-sections `### Pieces`, `### Integration shape`, `### Seam-level edges`, optionally `### Why N pieces`). No decompose work begins until the user answers. Four options:

- **`approve`** — continue to the Decompose phase. The agent emits one `approval_checkpoint_responded` event with `checkpoint: research-decompose`, `response: approve`, and the current `revision_round` integer, then proceeds.
- **`revise`** — open a free-text revision prompt scoped to the Architecture section. The agent re-walks the Architecture write protocol per spec R4 GATE-2 (iii) (re-emit `### Pieces`, re-run `### Integration shape` and `### Seam-level edges`, re-run the `### Why N pieces` falsification gate if piece_count > 5), re-presents the gate, and increments `revision_round`. Emits one `approval_checkpoint_responded` event with `response: revise` per loop iteration. Loop continues until `approve` or `drop`.
- **`drop`** — abandon this discovery. The agent emits one `approval_checkpoint_responded` event with `response: drop` and exits without writing to `cortex/backlog/`. The research artifact stays in place as a durable audit trail.
- **`promote-sub-topic`** — minimal-surface affordance per spec R4 + Non-Requirements: the user supplies a sub-topic description, and the agent creates a single `needs-discovery` backlog ticket whose body includes a `## Promoted from` section reading exactly `## Promoted from\n\nDiscovery: cortex/research/<current-topic>/`. No frontmatter linkage field is introduced — the body-section reference is the sole linkage (no consumer reads a frontmatter pointer). No nested `/cortex-core:discovery` invocation. After ticket creation the agent emits one `approval_checkpoint_responded` event with `response: promote-sub-topic` and returns to this gate so the user can still `approve`, `revise`, or `drop` the current Architecture section.

All emissions go through the helper module — never hardcode the events.log path. Invoke via:

```
python3 -m cortex_command.discovery emit-checkpoint-response \
    --topic <topic> --checkpoint research-decompose \
    --response <approve|revise|drop|promote-sub-topic> \
    --revision-round <int>
```

The helper resolves the correct events.log target (lifecycle-attached, R13 re-run `-N` slug, or standalone `cortex/research/<topic>/events.log`) via its `resolve-events-log-path` subcommand. See `cortex_command/discovery.py` for the full subcommand surface.

### Decompose-commit batch-review gate

Within the Decompose phase, a user-blocking post-decompose batch-review gate (`checkpoint: decompose-commit`) fires after all ticket bodies are authored and the prescriptive-prose scanner has passed, BEFORE any tickets commit to `cortex/backlog/`. The gate offers `approve-all`, `revise-piece <N>`, and `drop-piece <N>` options and emits an `approval_checkpoint_responded` event per response. See decompose.md §5 for the gate semantics.

## Phase Transition

After completing a phase artifact, commit the `cortex/research/{{topic}}/` directory, summarize findings, and proceed to the next phase automatically.

## Multiple Discoveries

One active discovery at a time. If multiple incomplete `cortex/research/*/` directories exist (those without `decomposed.md`), list them and ask which to resume.

## Relationship to /cortex-core:lifecycle

When `/cortex-core:discovery` creates backlog tickets, each ticket receives a `discovery_source:` field pointing to the research artifact. When `/cortex-core:lifecycle` starts on that ticket, it automatically loads the prior research, presents a summary, and asks whether to skip re-investigation (default: skip). In pipeline or overnight contexts the skip is applied automatically. To re-investigate from scratch, choose N at the prompt.
