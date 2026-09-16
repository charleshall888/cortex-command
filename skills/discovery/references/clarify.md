# Clarify Phase

Ideation gate before research: the topic is well-aimed, novel, and aligned with requirements. Always ad-hoc — discovery produces backlog items, it does not consume them.

### 1. Requirements

`cortex-load-requirements` (no `--feature`; falls back to project.md + Global Context). Read every listed non-skipped path, carry the path list into downstream prompts, relay any fallback note. None → note it and continue.

### 2. Backlog coverage

`cortex-read-backlog-backend` (argless). Any backend other than `cortex-backlog` → skip the scan with a one-line advisory, defaulting novelty to "no overlap detected". Under `cortex-backlog` → scan `cortex/backlog/[0-9]*-*.md` titles, tags, and descriptions; substantial overlap → surface it and ask whether to proceed or work from the existing ticket.

### 3. Confidence

Four dimensions: **topic aim** (one problem space vs. vague or conflated), **domain** (one area vs. unrelated ones with no unifying question), **novelty** (no substantial backlog overlap), **requirements alignment** (no conflicts). All high → §4. Any low → ask targeted questions covering only what is unclear, and wait.

### 4. Output

1. **Clarified topic statement** — one sentence: what this investigates and why.
2. **Domain note** — the area(s) touched.
3. **Requirements alignment** — aligned (file and constraints), partial, none found, or conflict (resolve with the user first).
4. **Open questions for research** — what investigation should resolve, not what the user should answer. May be empty.
5. **Research-sizing complexity** — `simple` or `complex`; sizes the fan-out only, not implementation complexity. Skew toward `complex` for any multi-faceted or epic-seeding topic: an under-sized pass propagates a shallow direction across every ticket the epic spawns.
6. **Research-sizing criticality** — `low|medium|high|critical`, biased upward for the same reason and floored at `medium`. `high`/`critical` when the topic sets direction across multiple tickets.
7. **Scope envelope** (optional) — in/out bullets when boundaries are tractable now; else "No envelope needed" with a reason.

State each with brief reasoning.

### 5. Persist the sizing

Conversation memory does not survive a phase resume:

```
cortex-discovery emit-research-sizing --topic <topic> --complexity <simple|complex> --criticality <low|medium|high|critical>
```
