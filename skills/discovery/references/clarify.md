# Clarify Phase

Check the idea before research: the topic is well-aimed, new, and fits the requirements. Discovery never starts from a backlog item — it produces them.

### 1. Requirements

Run `cortex-load-requirements` (no `--feature`; it falls back to project.md + Global Context). Read every listed path that is not skipped, pass the path list to later prompts, and tell the user about any fallback note. None found → say so and continue.

### 2. Backlog coverage

Run `cortex-read-backlog-backend` (no arguments). Any backend other than `cortex-backlog` → skip the scan with a one-line note and set novelty to "no overlap detected". Under `cortex-backlog` → scan the titles, tags, and descriptions in `cortex/backlog/[0-9]*-*.md`. Large overlap → show it and ask whether to proceed or work from the existing ticket.

### 3. Confidence

Rate four things:

- **Topic aim** — one problem space, not vague or mixed.
- **Domain** — one area, not unrelated areas with no shared question.
- **Novelty** — no large backlog overlap.
- **Requirements alignment** — no conflicts.

All high → §4. Any low → ask only about what is unclear, and wait.

### 4. Output

1. **Clarified topic statement** — one sentence: what this investigates and why.
2. **Domain note** — the area(s) touched.
3. **Requirements alignment** — aligned (file and constraints), partial, none found, or conflict (resolve with the user first).
4. **Open questions for research** — what the research should answer, not what the user should answer. May be empty.
5. **Research-sizing complexity** — `simple` or `complex`. It sets how many research agents run, not how hard the build is. Lean toward `complex` for any many-sided topic or one that starts an epic: research that is too small sends every ticket in the epic in a shallow direction.
6. **Research-sizing criticality** — `low|medium|high|critical`. Lean high for the same reason; never below `medium`. `high`/`critical` when the topic sets direction across several tickets.
7. **Scope envelope** (optional) — in/out bullets when the boundaries are clear now; else "No envelope needed" with a reason.

Give a short reason for each.

### 5. Persist the sizing

Conversation memory does not survive a phase resume:

```
cortex-discovery emit-research-sizing --topic <topic> --complexity <simple|complex> --criticality <low|medium|high|critical>
```
