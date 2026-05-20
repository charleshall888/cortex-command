# Body Template

Five-section template for backlog ticket bodies. Sections appear in this order. All sections are required except `## Touch points`, which is optional. Each section must be prose only — no path:line citations, no section-index citations, no fenced code blocks — except inside `## Touch points`, where those forms are the norm.

---

## Why

Capture the problem the ticket addresses in symptom-voice: what is broken, missing, or degraded in observable terms, as a user or operator would describe the symptom. Do not name the solution or mechanism here. One paragraph is sufficient. This section anchors motivation at intake so reviewers can evaluate whether the Role fills the right gap.

**Why-vs-Role disambiguation rule**: Why captures the problem in symptom-voice (what's broken / what's missing in observable terms). Role captures what slot this piece fills in the system after the ticket lands (arc42 Responsibility — what task it fulfills). When the Why collapses to one sentence that restates Role's lead, omit Why entirely — the section is optional in this collapse case, required otherwise.

---

## Role

Name what this piece does by its Responsibility in the system, not by its mechanism. State the task this piece fulfills once the ticket lands — the arc42 Responsibility framing: what job exists in the system after this piece is present that could not be done before. One paragraph. Do not describe how it is built or which files it touches.

---

## Integration

Describe how this piece connects to neighboring pieces and to the existing system, using the Interface surfaces named in the Architecture section. Reference contract surfaces by name (e.g., "the phase-transition contract", "the events-registry schema") without citing file paths or line numbers. One paragraph covering the inbound and outbound Interface connections is sufficient.

---

## Edges

Enumerate structural constraints and Boundary conditions: what breaks if an upstream contract changes shape, what this piece must not do, and what explicit non-goal decisions keep the scope tight. Each bullet names a contract surface or non-goal by name. Bullets do not cite file paths or section indices — those belong in `## Touch points`.

---

## Touch points  (optional)

List implementation locations: specific file paths with line numbers, section indices (§N, RN), or multi-line code excerpts. This is the sole permitted location for path:line citations and section-index references. Use one bullet per distinct location. Omit this section entirely when no implementation locations are known at ticket-authoring time; the section is optional by design so early-stage tickets remain clean.
