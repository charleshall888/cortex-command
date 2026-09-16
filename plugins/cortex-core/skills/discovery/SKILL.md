---
name: discovery
description: Investigate a topic, then decompose it into backlog tickets grouped by epic. Ends at tickets, not a spec. Needs a topic argument — without one, use dev.
argument-hint: "<topic>"
---

# Discovery

Topic: $ARGUMENTS — required. Empty → halt with "discovery requires a topic argument; for 'what should I work on' or 'next task' routing, use `/cortex-core:dev` instead." Directory: `cortex/research/{{topic}}/`, lowercase-kebab.

## Step 1: Resolve the phase

Absent directory → **clarify**; `research.md` without `decomposed.md` → **decompose**; `decomposed.md` present → complete (offer re-run or update). Report the phase and offer to continue or restart earlier. Several `cortex/research/*/` lack `decomposed.md` → list them and ask which.

**Re-run from scratch** never overwrites: take slug `{{topic}}-N` (smallest N ≥2 unused), open the new `research.md` with `superseded:` naming the immediately-prior artifact, leave the old directory as an audit trail. Reconciliation (repointing `discovery_source:`, archiving) is the user's call, outside this skill.

## Step 2: Execute the phase

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Clarify | [clarify.md](${CLAUDE_SKILL_DIR}/references/clarify.md) | none (conversation only) |
| Research | [research.md](${CLAUDE_SKILL_DIR}/references/research.md) | `cortex/research/{{topic}}/research.md` |
| Decompose | [decompose.md](${CLAUDE_SKILL_DIR}/references/decompose.md) | Epic + backlog tickets |

Read **only** the current phase's reference. `${CLAUDE_SKILL_DIR}` resolves only here — substitute the absolute path where a reference names a sibling: **fanout** → `${CLAUDE_SKILL_DIR}/../research/references/fanout.md`; **orchestrator-review** → `${CLAUDE_SKILL_DIR}/../build/references/orchestrator-review.md`.

After each phase, commit `cortex/research/{{topic}}/`, summarize, and proceed automatically — except across the gate below.

## Step 3: Research → Decompose gate

One user-blocking question, reached by finishing Research or resuming into Decompose; no decompose work starts until answered.

```
cortex-discovery generate-brief --research-md cortex/research/<topic>/research.md \
    --persist-to cortex/research/<topic>/brief.md
```

Non-zero exit, missing file, or failed validation → show the dense `## Architecture` section with a warning naming the failure (`brief_generation_failed: <reason>`). Over the advisory word cap → show it anyway with a one-line note.

- **`approve`** — proceed to Decompose.
- **`revise`** — free-text revision scoped to Architecture: re-walk it against `references/research.md` §3's template, re-emit `### Pieces` then `### How they connect`, re-present, increment `revision_round`. Loops until `approve` or `drop`.
- **`drop`** — neutral terminus: research sufficient and no tickets warranted, or abandon. Write nothing to `cortex/backlog/`; the artifact stays.
- **`promote-sub-topic`** — the user names a sub-topic; compose a body via `/backlog-author compose` with a `## Promoted from` section reading exactly `## Promoted from\n\nDiscovery: cortex/research/<current-topic>/` (the sole linkage — no frontmatter pointer, no nested discovery). Create one `needs-discovery` ticket per the backend routing below, then return to this gate.

Emit one event per response:

```
cortex-discovery emit-checkpoint-response --topic <topic> --checkpoint research-decompose \
    --response <approve|revise|drop|promote-sub-topic> --revision-round <int>
```

## Backend routing

Wherever a phase creates tickets, resolve first with `cortex-read-backlog-backend` (argless): `cortex-backlog` → create normally; `none` → skip the create, keep the authored titles and bodies in `cortex/research/{topic}/decomposed.md` with a one-line advisory, write nothing to `cortex/backlog/`; anything else → file best-effort per `backlog.instructions`, surfacing bodies inline if filing fails.

Every ticket created carries `discovery_source:` pointing at the research artifact; `/cortex-core:refine` loads it as background.
