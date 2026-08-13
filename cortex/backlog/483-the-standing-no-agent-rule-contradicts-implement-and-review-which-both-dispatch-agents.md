---
schema_version: "1"
uuid: 61989ba3-426b-4034-bd12-6bdd86ae629d
title: The standing no-agent rule contradicts Implement and Review, which both dispatch agents
status: complete
priority: medium
type: bug
created: 2026-08-12
updated: 2026-08-12
tags: ['lifecycle', 'skills', 'agents', 'prompt']
areas: ['lifecycle']
---
Filed from wild-light, 2026-08-12, during `/cortex-core:build` on ticket #520 (`mount-structures-as-real-meshes-and`). The operator's words: remove the clause "so it isn't causing confusion (it has happened several times)."

## Why

Sessions driving this plugin's lifecycle are started with two lines in their system prompt:

```
Do not call the AgentTool unless the user requested it
Do not use workflows or deep-research unless the user requested it
```

Those lines **directly contradict two phases of this plugin's own skills**, and the contradiction fires every time a `high`/`critical` or `complex` ticket reaches Review:

- `skills/build/references/implement.md` §2 opens "Dispatch a fresh sub-task per task — a clean context prevents stale assumptions," and its §2b says to dispatch every batch task concurrently using the builder template.
- `skills/build/references/review.md` §2 says "Dispatch one read-only reviewer," and §3's **single-writer rule** states that only the reviewer role writes `review.md`.

An agent honouring the standing rule literally must implement inline and then **self-review** — the same context that wrote the code judging it, which is the weakest possible configuration for the one phase whose entire value is independence. On #520 this surfaced as a blocking question to the operator mid-lifecycle, which is exactly the friction the trailing clause creates.

## The clause is the problem, not the rule

"Unless the user requested it" is ambiguous about **what counts as a request**. Invoking `/cortex-core:build` *is* a request for a workflow whose documented steps dispatch agents — so one reading says the invocation already authorised it, and another says only an explicit "spawn an agent" does. Both readings are defensible, which is why it has repeatedly cost a turn: the agent either over-asks (blocking on a decision the skill already made) or silently degrades the phase without saying so. The second failure is worse and is invisible in the artifacts.

Deleting the clause resolves it in the direction the skills already assume. Keeping a bare "do not call the AgentTool" would be coherent too — but then Implement and Review need rewriting to match, and Review needs an honest self-review mode that labels itself.

## The part that needs investigating first

**The source of those two lines was not found.** Searched, all negative:

- this repo — `grep -rn "unless the user requested"` and `grep -rn "AgentTool"` across the whole tree: **0 hits**
- `~/.claude/settings.json`, `~/.claude/settings.local.json`, `~/.claude/CLAUDE.md` (a 0-byte file)
- the consuming repo's `CLAUDE.md`, `.claude/settings.json`, `.claude/settings.local.json`
- `~/.claude/plugins/` including the plugin cache

The only matches anywhere under `~/.claude` were inside session transcript JSONL — i.e. the text as it arrived in a prompt, not its definition. So it is injected at session start by something outside both repos: a launcher, a runner, a Claude Code app-level setting, or whatever starts these sessions. **Find that first** — the fix is one line once located, and the search above is recorded so it is not repeated.

If it turns out to live outside anything this repo controls, the actionable half is still real: the skills should state explicitly that invoking a lifecycle skill authorises the agent dispatches its own references prescribe, so an agent reading a conflicting standing rule has something concrete to resolve against.

## Edges

- Do **not** "fix" this by weakening `review.md`'s single-writer rule to let the orchestrator write `review.md`. That rule exists so the verdict is not authored by the implementer, and the contradiction above is an argument for keeping it, not relaxing it.
- Whatever is decided should be consistent for **both** lines. Workflows and deep-research have the same shape of problem — `skills/build/references/parallel-execution.md` describes `Agent(isolation: "worktree")` fan-out as a sanctioned path.
- Worth checking whether the standing rule was added deliberately after a bad experience. In the consuming repo the operator's memory carries roughly eight separately-learned entries about subagent failure modes — agents freezing on rejection prompts, named agents going silent, reports routing to the wrong session, worktree-blocked capture tasks. If the rule was a considered response to those, the right answer may be a **narrower** rule (e.g. no *unattended* fan-out) rather than deletion.

## Touch-points

- `skills/build/references/implement.md` — §2 dispatch contract
- `skills/build/references/review.md` — §2 dispatch, §3 single-writer rule
- `skills/build/references/parallel-execution.md` — the worktree fan-out path
- wherever the session-start system prompt is assembled (**unlocated — see above**)

## Resolution (2026-08-12) — source located as out-of-repo; skill-side half landed

**The two lines are not in any file this repo or the operator controls.** Extending the ticket's search:

- `/Applications/Claude.app/Contents/Resources/` including `app.asar` (via `strings`) — 0 hits for
  `Do not call the AgentTool` and for `unless the user requested`
- `~/.claude/{settings.json,settings.local.json,CLAUDE.md,plugins/,cache/}` and
  `~/Library/Application Support/Claude` — 0 hits
- the only matches anywhere under `~/.claude` are 5 session transcript JSONL files, and every one is this
  ticket's own body being read by an agent — i.e. the text as it *arrived* in a prompt, never its definition

They are injected into the session system prompt by the Claude Code session assembly, above both repos.
Confirmed from primary evidence rather than inference: they are present verbatim in this session's own system
prompt while being absent from every file above. **There is no line to delete**, so the operator's requested
fix ("remove the clause") is not available here and the ticket's fallback half is the whole actionable scope.

**Landed:** one clause in `skills/build/SKILL.md` §Step 3, which the orchestrator reads on every run before
any phase reference — so it covers Implement and Review from one site rather than duplicating into both. It
states that invoking the skill *is* the request for the dispatches its references prescribe, that the
standing rule does not reach them, and that this is not a question to put to the operator; and it forbids the
worse failure — degrading to inline work silently — by requiring the substitution be named in the phase
summary and the result labelled a self-review. It covers the workflow/fan-out line too, by naming
`parallel-execution.md`.

`skills/build/SKILL.md` was chosen over the two references because the reference byte pin
(`skills/build/references/size-pin.txt`) sits at exactly its measured floor with zero headroom, while
SKILL.md is 89 lines against a 500-line cap — so the one-site placement is also the one that needs no pin
raise. `review.md`'s single-writer rule is untouched, per this ticket's first edge.

**Not done, deliberately:** the "narrower rule" option the last edge raises (e.g. banning only *unattended*
fan-out) is unavailable for the same reason the deletion is — the rule is not ours to narrow. If the session
assembly ever becomes configurable, that option is still the better one and this note is where to start.
