---
name: discovery
description: Investigate a topic, then decompose it into backlog tickets grouped by epic. Ends at tickets, not a spec. Needs a topic argument — without one, use dev.
argument-hint: "<topic>"
---

# Discovery

Topic: $ARGUMENTS — required. Empty → stop with "discovery requires a topic argument; for 'what should I work on' or 'next task' routing, use `/cortex-core:dev` instead." Directory: `cortex/research/{{topic}}/`, lowercase-kebab.

## Step 1: Resolve the phase

- No directory → **clarify**.
- `research.md` without `decomposed.md` → **decompose**.
- `decomposed.md` present → complete. Offer a re-run or an update.

Report the phase and offer to continue or restart earlier. If several `cortex/research/*/` lack `decomposed.md`, list them and ask which.

**A re-run from scratch** never overwrites. Use slug `{{topic}}-N` (smallest unused N ≥2). Open the new `research.md` with `superseded:` naming the artifact just before it. Leave the old directory as a record. Repointing `discovery_source:` or archiving is the user's call.

## Step 2: Execute the phase

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Clarify | [clarify.md](${CLAUDE_SKILL_DIR}/references/clarify.md) | none (conversation only) |
| Research | [research.md](${CLAUDE_SKILL_DIR}/references/research.md) | `cortex/research/{{topic}}/research.md` |
| Decompose | [decompose.md](${CLAUDE_SKILL_DIR}/references/decompose.md) | Epic + backlog tickets |

Read **only** the current phase's reference. `${CLAUDE_SKILL_DIR}` resolves only here. Where a reference names a sibling, use the absolute path: **fanout** → `${CLAUDE_SKILL_DIR}/../research/references/fanout.md`; **orchestrator-review** → `${CLAUDE_SKILL_DIR}/../build/references/orchestrator-review.md`.

After each phase, commit `cortex/research/{{topic}}/`, summarize, and go on without asking — except at the gate below.

## Step 3: Research → Decompose gate

One question the user must answer, reached by finishing Research or resuming into Decompose. No decompose work starts until it is answered.

```
cortex-discovery generate-brief --research-md cortex/research/<topic>/research.md \
    --persist-to cortex/research/<topic>/brief.md
```

Non-zero exit, missing file, or failed validation → show the full `## Architecture` section with a warning that names the failure (`brief_generation_failed: <reason>`). Over the advisory word cap → show the brief anyway with a one-line note.

- **`approve`** — go to Decompose.
- **`revise`** — free-text changes to Architecture only. Rework it against the template in `references/research.md` §3, rewrite `### Pieces` then `### How they connect`, show it again, and add one to `revision_round`. Repeat until `approve` or `drop`.
- **`drop`** — a neutral end: the research is enough and needs no tickets, or the user abandons it. Write nothing to `cortex/backlog/`. The artifact stays.
- **`promote-sub-topic`** — the user names a sub-topic. Compose a body via `/backlog-author compose` with a `## Promoted from` section reading exactly `## Promoted from\n\nDiscovery: cortex/research/<current-topic>/`. That section is the only link — no frontmatter pointer, no nested discovery. Create one `needs-discovery` ticket per the backend routing below, then return to this gate.

Log one event per response:

```
cortex-discovery emit-checkpoint-response --topic <topic> --checkpoint research-decompose \
    --response <approve|revise|drop|promote-sub-topic> --revision-round <int>
```

## Backend routing

Before a phase creates tickets, run `cortex-read-backlog-backend` (no arguments):

- `cortex-backlog` → create normally.
- `none` → create nothing. Keep the titles and bodies in `cortex/research/{topic}/decomposed.md` with a one-line note. Write nothing to `cortex/backlog/`.
- Anything else → file as best you can per `backlog.instructions`. If filing fails, show the bodies inline.

Every ticket created carries `discovery_source:` pointing at the research artifact; `/cortex-core:refine` loads it as background.
