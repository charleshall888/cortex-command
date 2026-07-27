---
name: discovery
description: Ideation research for topics not ready for implementation — checks aim, investigates the problem space, then decomposes findings into backlog tickets grouped by epic. Use when user says "/cortex-core:discovery", "discover this", "break this down into tickets", "decompose into backlog", or wants to understand a topic before committing to build. Requires a topic argument; for "what should I work on" or "next task" routing without a specific topic, use /cortex-core:dev instead.
when_to_use: "Use when investigating a topic deeply before committing to build it. Different from /cortex-core:research — research produces a research.md and stops; discovery wraps clarify→research→decompose and ends with backlog tickets. Different from /cortex-core:refine and /cortex-core:build — discovery stops at backlog tickets rather than speccing or building one."
argument-hint: "<topic>"
---

# Discovery

Topic: $ARGUMENTS — required. Empty → halt with "discovery requires a topic argument; for 'what should I work on' or 'next task' routing, use `/cortex-core:dev` instead." Lowercase-kebab-case for the directory name (`cortex/research/plugin-system/`).

## Step 1: Resolve the phase

Scan `cortex/research/{{topic}}/`: absent → **clarify**; `research.md` without `decomposed.md` → **decompose**; `decomposed.md` present → complete (offer to re-run or update). Report the detected phase and offer to continue or restart earlier. One active discovery at a time — if several `cortex/research/*/` directories lack `decomposed.md`, list them and ask which to resume.

**Re-run from scratch** (not resume, not update-in-place) never overwrites the prior artifact. Take a fresh slug `{{topic}}-N`, N the smallest integer ≥2 unique under `cortex/research/`; open the new `research.md` with `superseded:` frontmatter naming the artifact it supersedes (the immediately-prior `-N`, not the original); leave the existing directory untouched as a durable audit trail. Reconciliation — surfacing differences, repointing `discovery_source:`, archiving the old artifact — is an explicit user decision outside this skill.

## Step 2: Execute the phase

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Clarify | [clarify.md](${CLAUDE_SKILL_DIR}/references/clarify.md) | none (conversation only) |
| Research | [research.md](${CLAUDE_SKILL_DIR}/references/research.md) | `cortex/research/{{topic}}/research.md` |
| Decompose | [decompose.md](${CLAUDE_SKILL_DIR}/references/decompose.md) | Epic + backlog tickets |

Read **only** the current phase's reference.

**Sibling-path propagation (load-bearing).** `${CLAUDE_SKILL_DIR}` resolves only in this body. Where a phase reference points at a sibling skill, substitute the absolute path resolved here:

- **fanout** → `${CLAUDE_SKILL_DIR}/../research/references/fanout.md`
- **orchestrator-review** → `${CLAUDE_SKILL_DIR}/../lifecycle/references/orchestrator-review.md`

After each phase, commit `cortex/research/{{topic}}/`, summarize, and proceed automatically — except across the Research → Decompose gate below.

## Step 3: Research → Decompose gate

A single-question user-blocking gate, reached by finishing Research or by resuming into Decompose. No decompose work starts until the user answers it.

```
cortex-discovery generate-brief --research-md cortex/research/<topic>/research.md \
    --persist-to cortex/research/<topic>/brief.md
```

Non-zero exit, missing file, or failed decision-content validation → fall back to displaying the dense `## Architecture` section with a warning naming the failure (`brief_generation_failed: <reason>`). Valid but over the advisory word cap → display it anyway, followed by a one-line note.

Four options:

- **`approve`** — proceed to Decompose.
- **`revise`** — free-text revision scoped to the Architecture section: re-walk it against the live template in `references/research.md` §3, re-emitting `### Pieces` then `### How they connect`, re-present the gate, increment `revision_round`. Loops until `approve` or `drop`.
- **`drop`** — neutral terminus, motive-agnostic: close discovery when research is sufficient and no tickets are warranted, OR abandon outright. Exit without writing to `cortex/backlog/`; the research artifact stays as the audit trail.
- **`promote-sub-topic`** — the user supplies a sub-topic; compose a body via `/backlog-author compose` including a `## Promoted from` section reading exactly `## Promoted from\n\nDiscovery: cortex/research/<current-topic>/` (the body section is the sole linkage — no frontmatter pointer, no nested discovery). Create one `needs-discovery` ticket under the backend routing below, then return to this gate.

Emit one event per response — never hardcode the log path:

```
cortex-discovery emit-checkpoint-response --topic <topic> --checkpoint research-decompose \
    --response <approve|revise|drop|promote-sub-topic> --revision-round <int>
```

## Backend routing

Wherever a phase creates tickets, resolve the backend first with `cortex-read-backlog-backend` (argless): **`cortex-backlog`** → create normally; **`none`** → skip the create CLI, preserve the authored titles and bodies in `cortex/research/{topic}/decomposed.md` with a one-line advisory, and write nothing to `cortex/backlog/`; **anything else** → file the equivalent best-effort per `backlog.instructions`, surfacing bodies inline if filing fails.

## Relationship to /cortex-core:refine

Every ticket discovery creates carries `discovery_source:` pointing at the research artifact. When `/cortex-core:refine` starts on that ticket it auto-loads the prior research as background, summarizes it, and asks whether to skip re-investigation (default skip; pipeline and overnight contexts skip automatically).
