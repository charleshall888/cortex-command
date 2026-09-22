# Clarify Phase

Before research: confirm what is being built and why, check it against requirements, set complexity and criticality. Ask only where intent is unclear.

**Context A** — the input matched a `cortex/backlog/NNN-*.md`; read its frontmatter and body. **Context B** — free text; assess it directly, skip all backlog write-backs.

## 1. Load requirements

`cortex-load-requirements --feature {slug}` — read every listed path that is not skipped, pass the path list to later prompts, and show any fallback note. No `cortex/requirements/` → say so and continue.

## 2. Confidence assessment

| Dimension | High | Low |
|---|---|---|
| **Intent clarity** | one unambiguous outcome | vague, several readings, contradictory |
| **Scope boundedness** | in/out explicit | open-ended, or mixed up with nearby work |
| **Requirements alignment** | aligns, no conflicts | conflicts with, ignores, or has no connection to requirements |

A ticket that says how to build it does not set the scope — its suggestions are ideas for research to test. Context B with no requirements → rate alignment "no requirements files found".

## 3. Critic review

Follow `${CLAUDE_SKILL_DIR}/references/clarify-critic.md`. The orchestrator writes the `clarify_critic` event, not the critic.

## 4. Question threshold

<!-- pause: clarify-question-batch question -->
All three dimensions high after §3 **and** no critic Ask items → skip to §5. Otherwise merge the low-rated gaps and critic Asks into one list of ≤5 choices — critic Asks first, then highest-impact gaps. Ask only about specific gaps, never to be complete or about what is already clear.

## 5. Handoff package

1. **Clarified intent** — one sentence: what and why. It sets the research scope.
2. **Complexity** — `simple` (you know the approach, or one read confirms it; nothing to decide. Size is not the test. Handle directly, no lifecycle), `moderate` (needs some reading, no real design choice — most work), `complex` (a decision that reading code won't settle: competing designs, effects too wide to list, a precedent others will follow). Judge what the work *requires*. When torn, take the lower tier — refine re-checks after research. Say which lower tier you considered and why you rejected it.
3. **Criticality** — `low` (easy to undo, nothing depends on it), `medium` (recoverable, isolated), `high` (hard to reverse, or any change to shared skills / workflow infrastructure / overnight runner / hooks — the default for most agentic-layer changes), `critical` (security, data loss, financial, loss of a core capability). State both with brief reasoning; do not ask the user to confirm.
4. **Requirements alignment** — aligned (name the file and constraints), partial, none found, or conflict (resolve with the user first).
5. **Open questions for research** — ones that reading code can answer, not the user. May be empty.

## 6. Research sufficiency

Applied when Research starts, against an existing `cortex/lifecycle/{slug}/research.md`. Insufficient when any holds: (a) its goal differs materially from the clarified intent; (b) files named in the item's description or acceptance criteria are absent from its codebase findings; (c) its codebase findings are empty or generic; (d) requirements changed significantly since it was written. None → don't re-run. Any → name the signal and re-run.

## 7. Write back

Use refine SKILL.md §2's 3-arm routing (Context B skips). Clarify checks intent, scope, and alignment only. The requirements interview is Specify's job; feasibility is Research's.
