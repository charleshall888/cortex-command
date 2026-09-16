# Clarify Phase

Intent gate before research: confirm what is being built and why, align with requirements, set complexity and criticality, ask only where intent is unclear.

**Context A** — input resolved to a `cortex/backlog/NNN-*.md`; read its frontmatter and body. **Context B** — ad-hoc text; assess directly, skip all backlog write-backs.

## 1. Load requirements

`cortex-load-requirements --feature {slug}` — read every listed non-skipped path, carry the path list into downstream prompts, relay any fallback note. No `cortex/requirements/` → note it and proceed.

## 2. Confidence assessment

| Dimension | High | Low |
|---|---|---|
| **Intent clarity** | one unambiguous outcome | vague, multi-interpretable, contradictory |
| **Scope boundedness** | in/out explicit | open-ended, or conflated with adjacent work |
| **Requirements alignment** | aligns, no conflicts | conflicts with, ignores, or has no connection to requirements |

A prescriptive ticket body does not bound scope — implementation suggestions are hypotheses for research, not constraints. Context B with no requirements → rate alignment "no requirements files found".

## 3. Critic review

Follow `${CLAUDE_SKILL_DIR}/references/clarify-critic.md`. The orchestrator writes the `clarify_critic` event, not the critic.

## 4. Question threshold

<!-- pause: clarify-question-batch question -->
All three dimensions high after §3 **and** no critic Ask items → skip to §5. Otherwise merge the low-confidence gaps and critic Asks into one list of ≤5 choices — critic Asks first, then highest-impact gaps. Ask only about specific gaps, never for completeness or about what is already clear.

## 5. Handoff package

1. **Clarified intent** — one sentence: what and why. Anchors research scope.
2. **Complexity** — `simple` (you know the approach, or one read confirms it; nothing to decide — size is not the test; handle directly, no lifecycle), `moderate` (needs orientation, no real design fork — most work), `complex` (a decision code-reading won't settle: competing designs, unenumerable blast radius, a precedent others follow). Judge what the work *requires*. When torn, take the lower tier — §3 of research re-checks. Say which lower tier was considered and why it was rejected.
3. **Criticality** — `low` (trivially reversible, no downstream deps), `medium` (recoverable, isolated), `high` (hard to reverse, or any change to shared skills / workflow infrastructure / overnight runner / hooks — the default for most agentic-layer changes), `critical` (security, data loss, financial, loss of a core capability). State both with brief reasoning; do not confirm.
4. **Requirements alignment** — aligned (name the file and constraints), partial, none found, or conflict (resolve with the user first).
5. **Open questions for research** — resolvable by reading code, not by asking. May be empty.

## 6. Research sufficiency

Applied at Research entry against an existing `cortex/lifecycle/{slug}/research.md`. Insufficient when any holds: (a) its goal differs materially from the clarified intent; (b) files named in the item's description or acceptance criteria are absent from its codebase findings; (c) its codebase findings are empty or generic; (d) requirements changed significantly since it was written. None → skip re-running. Any → name the signal and re-run.

## 7. Write back

Per refine SKILL.md §2's 3-arm routing (Context B skips). Clarify checks intent, scope, and alignment only — the requirements interview is Specify's, feasibility is Research's.
