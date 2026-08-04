# Clarify Phase

Pre-research intent gate: confirm what's being built and why, align with requirements, set complexity/criticality, and surface targeted questions when intent is unclear.

**Context A** — input resolved to a `cortex/backlog/NNN-*.md`; read its frontmatter and body. **Context B** — ad-hoc text, no matching item; assess directly, skip all backlog write-backs.

## 1. Load requirements

`cortex-load-requirements --feature {slug}` — read every listed non-skipped path, inject the printed path list into downstream prompts, relay any fallback note. No `cortex/requirements/` → note it and proceed.

## 2. Confidence assessment

| Dimension | High confidence | Low confidence |
|-----------|-----------------|----------------|
| **Intent clarity** | one clear, unambiguous outcome | vague, multi-interpretable, or contradictory |
| **Scope boundedness** | in/out explicit | open-ended, or conflated with adjacent work |
| **Requirements alignment** | aligns with `cortex/requirements/`, no conflicts | conflicts with, ignores, or has no connection to requirements |

A prescriptive ticket body does NOT make scope more bounded — treat implementation suggestions as unvalidated hypotheses for research, not scope constraints. In Context B with no requirements files, rate alignment as "no requirements files found".

## 3. Critic review

Follow `${CLAUDE_SKILL_DIR}/references/clarify-critic.md`. The orchestrator, not the critic, writes the `clarify_critic` event to `cortex/lifecycle/{feature}/events.log`.

## 4. Question threshold

<!-- pause: clarify-question-batch question -->
All three dimensions high after §3 **and** no critic Ask items → skip questions, proceed to §5. Otherwise merge the low-confidence gaps and critic Asks into one list, present via `AskUserQuestion`, cap ≤5 — critic Asks first, then highest-impact gaps, drop the rest. Ask only about specific gaps, never for completeness, never re-asking what's already clear.

## 5. Produce the handoff package

1. **Clarified intent statement** — one sentence: what's being built and why. The anchor for research scope.
2. **Complexity** — `simple` (you know the approach, or one read confirms it; nothing to decide — **size is not the test**, a wide mechanical change is still simple; handle directly, no lifecycle), `moderate` (needs orientation, but no real design fork — most work lands here), or `complex` (a decision code-reading won't settle: competing designs, a blast radius you can't enumerate, or a precedent others follow). Judge what the work *requires*, not its size. **When torn, take the lower tier** — the escalator re-checks after research. State whether the next tier down was considered, and why it was rejected.
3. **Criticality** — `low` (trivially reversible, no downstream deps), `medium` (recoverable, isolated tooling with no downstream consumers), `high` (significant or hard to reverse, **or any change to shared skills / workflow infrastructure / overnight runner / hooks — the appropriate default for most agentic-layer changes**), `critical` (security, data loss, financial, or loss of a core capability). State both with brief reasoning and proceed without confirming.
4. **Requirements alignment note** — aligned (name the file and its constraints), partial, none found, or conflict (resolve with the user before proceeding).
5. **Open questions for research** — ambiguities best resolved by reading code, not by asking the user. May be empty.

## 6. Research sufficiency criteria

Defined here, **applied at Research entry** against an existing `cortex/lifecycle/{slug}/research.md`. Research is sufficient when none of these hold:

- (a) its goal differs materially from the clarified intent statement;
- (b) files named in the item's description or acceptance criteria don't appear in its codebase findings;
- (c) its codebase findings are empty or generic — no specific paths or patterns;
- (d) requirements context has changed significantly since it was written.

None apply → skip re-running, proceed to Spec. Any apply → name the signal, explain the insufficiency, re-run research.

## 7. Write back

Write complexity and criticality per refine SKILL.md Step 2's canonical routing (Context B skips).

Clarify checks intent, scope, and alignment only — the deep requirements interview belongs to Specify, technical feasibility to Research.
