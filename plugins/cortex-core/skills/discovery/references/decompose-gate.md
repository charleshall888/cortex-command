# Research → Decompose Approval Gate (spec R4)

Between Research and Decompose a single-question user-blocking gate fires. Its first content section is `cortex/research/<topic>/brief.md`, generated via:

```
cortex-discovery generate-brief \
    --research-md cortex/research/<topic>/research.md \
    --persist-to cortex/research/<topic>/brief.md
```

If brief generation exits non-zero, `brief.md` is missing, or it fails decision-content validation, the gate falls back to the dense `## Architecture` section (`### Pieces` and `### How they connect`) with a warning naming the failure (`brief_generation_failed: <reason>`). When `brief.md` is present, valid, and anchor-passing but over the advisory word cap, the gate still displays it, followed by a one-line note such as "(summary ran N words over the 275-word advisory cap)". No decompose work begins until the user answers. Four options:

- **`approve`** — continue to the Decompose phase. The agent emits one `approval_checkpoint_responded` event with `checkpoint: research-decompose`, `response: approve`, and the current `revision_round` integer, then proceeds.
- **`revise`** — free-text revision scoped to the Architecture section: the agent re-walks it against the live template in `references/research.md` §6, re-emitting `### Pieces` (named by role) then `### How they connect`, re-presents the gate, and increments `revision_round`. Emits one `approval_checkpoint_responded` event with `response: revise` per iteration. Loops until `approve` or `drop`.
- **`drop`** — neutral terminus: close discovery when research is sufficient and no tickets are warranted, OR abandon outright — both legitimate, motive-agnostic. The agent emits one `approval_checkpoint_responded` event with `response: drop` and exits without writing to `cortex/backlog/`; the research artifact stays in place as a durable audit trail.
- **`promote-sub-topic`** — the user supplies a sub-topic description; invoke `/backlog-author compose` with it as context, including a `## Promoted from` section reading exactly `## Promoted from\n\nDiscovery: cortex/research/<current-topic>/`. Resolve the backend once with `cortex-read-backlog-backend` and route creation of a single `needs-discovery` ticket: **`cortex-backlog`** (default) → `cortex-create-backlog-item --title "investigate ..." --status needs-discovery --type discovery --body "<composed-body>"`; **`none`** → surface the title and body inline in `cortex/research/<current-topic>/` with a one-line advisory that ticket creation is disabled for this repo; **any other value** (external tracker) → create the equivalent item best-effort per `backlog.instructions`, surfacing the body inline if it can't be filed.

  The body-section reference is the sole linkage (no frontmatter pointer, no nested `/cortex-core:discovery`). Emit one `approval_checkpoint_responded` event with `response: promote-sub-topic` and return to this gate (the user can still `approve`, `revise`, or `drop`).

All emissions go through the helper module — never hardcode the events.log path. Invoke via:

```
cortex-discovery emit-checkpoint-response \
    --topic <topic> --checkpoint research-decompose \
    --response <approve|revise|drop|promote-sub-topic> \
    --revision-round <int>
```

The helper resolves the correct events.log target (lifecycle-attached, R13 re-run `-N` slug, or standalone `cortex/research/<topic>/events.log`) via its `resolve-events-log-path` subcommand.
