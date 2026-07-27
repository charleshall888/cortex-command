# Clarify Phase

Pre-research ideation gate: confirm the topic is well-aimed, novel, and aligned with requirements. Always ad-hoc — discovery produces backlog items, it does not consume them.

### 1. Load Requirements Context

Run `cortex-load-requirements` (omit `--feature`; discovery has no lifecycle index, so it falls back to project.md + Global Context). Read every listed non-skipped path and inject the printed path list into downstream prompts, relaying any fallback note. No `cortex/requirements/` → note it and continue.

### 3. Check Existing Backlog Coverage

Resolve the active backend once with `cortex-read-backlog-backend` (argless). **Two arms**, not decompose's three — a read path has no external-tracker query to fall to. Any backend other than `cortex-backlog` → skip the scan with a one-line advisory that backlog coverage checking is disabled for this repo, defaulting novelty to "no overlap detected" (the safe, non-blocking direction). Under **`cortex-backlog`** → scan `cortex/backlog/[0-9]*-*.md` titles, tags, and descriptions for overlap; if an item already covers this topic substantially, surface it and ask whether to proceed with discovery or work from the existing ticket.

### 4. Confidence Assessment

Four dimensions: **topic aim** (one problem space vs. vague or conflated), **domain** (belongs to one area vs. spans unrelated ones without a unifying question), **novelty** (no substantial backlog overlap), **requirements alignment** (no conflicts).

All four high → skip to §4. Any low → ask ≤4 targeted questions covering only what's genuinely unclear, and wait for answers.

### 6. Produce Clarify Output

1. **Clarified topic statement** — one sentence on what this will investigate and why.
2. **Domain note** — which area(s) of the project this touches.
3. **Requirements alignment** — aligned (naming the file and relevant constraints), partial, no requirements found, or conflict (resolve with the user before proceeding).
4. **Open questions for research** — what investigation should resolve, not what the user should answer. May be empty.
5. **Research-sizing complexity** — `simple` or `complex`. Sizes the research fan-out only, not the implementation complexity refine or lifecycle assess later. **Skew toward `complex`** for any multi-faceted topic or one seeding a whole epic: an under-sized pass propagates a shallow, wrong direction across every ticket the epic spawns.
6. **Research-sizing criticality** — `low|medium|high|critical`, biased upward for the same reason and **floored at `medium`, never `low`**. Raise to `high`/`critical` when the topic sets direction across multiple tickets.
7. **Scope envelope** (optional) — in-scope/out-of-scope bullets when boundaries are tractable now; otherwise "No envelope needed" with a one-line reason.

State each assessment with brief reasoning.

### 7. Persist the Research-Sizing Assessment

Discovery supports independent phase entry, and conversation memory does not survive a phase resume — persist outputs 5–6 so Research can read them back:

```
cortex-discovery emit-research-sizing --topic <topic> --complexity <simple|complex> --criticality <low|medium|high|critical>
```
