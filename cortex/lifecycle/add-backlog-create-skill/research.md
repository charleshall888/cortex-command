# Research: /backlog-create authoring-discipline layer

Topic anchor (from Clarify): a discipline layer wired into every harness location that instructs creating a backlog ticket, that interviews the author for Why and What, prevents prescriptive How language, coexists with the existing `/cortex-core:backlog add`, and covers non-discovery creation paths.

## Codebase Analysis

### Existing creation surfaces (rewire candidates)

| Surface | File | Lines | Behavior today |
|---|---|---|---|
| `/cortex-core:backlog add <title>` | `skills/backlog/SKILL.md` | 49–54 | Calls `cortex-create-backlog-item --title ...`; opens file for user edit. |
| `/cortex-core:discovery` decompose | `skills/discovery/references/decompose.md` | 137–148 | Authors body with `## Role / ## Integration / ## Edges / ## Touch points` template; calls `cortex-create-backlog-item` per piece. |
| `/cortex-core:lifecycle` Clarify Context B | `skills/lifecycle/references/clarify.md` | 19 | "Offer to create a backlog item before continuing — if impractical, note it and proceed without." |
| `/cortex-core:discovery` promote-sub-topic | `skills/discovery/SKILL.md` | 87 | Creates a `needs-discovery` ticket with minimal body. |
| `skills/dev/SKILL.md` | `skills/dev/SKILL.md` | 149, 231 | Suggests creating backlog items in dev-hub flow. |
| `skills/morning-review/SKILL.md` | `skills/morning-review/SKILL.md` | 91 | "create a backlog investigation item" prose. |
| `/cortex-core:refine` Context B | `skills/refine/SKILL.md` | 37–41 | Falls through to Clarify Context B. |

### Reusable patterns already in the repo

- **Discovery's body-template discipline** (`skills/discovery/references/decompose.md` §2, lines 15–38; "No implementation planning" constraint line 196). Proven four-header structure (`## Role`, `## Integration`, `## Edges`, `## Touch points`) that separates intent from mechanism by structural section.
- **LEX-1 prescriptive-prose scanner** (`bin/cortex-check-prescriptive-prose`; invoked from `decompose.md:100–121` and from pre-commit). Catches **structural** prescriptive signals only: path:line citations, `§N` references, and multi-line code blocks appearing outside `## Touch points`. Does NOT catch prescriptive English ("we should use X", "the fix is to add Y").
- **Orchestrator + sub-skill pattern** (`skills/requirements/SKILL.md` → `skills/requirements-gather/SKILL.md` + `skills/requirements-write/SKILL.md`). Canonical shape in this repo for "thin orchestrator + interview sub-skill". The user-facing slash command is the orchestrator; the interview lives in a named sub-skill that is also invocable on its own.
- **Skill helper module pattern** (`cortex_command/discovery.py`, `cortex_command/backlog/create_item.py`). When a SKILL.md dispatch ceremony invites paraphrase, collapse it into atomic `cortex_command/<skill>.py` subcommands with a `[project.scripts]` console-script entry.
- **`AskUserQuestion`-driven interview UX**, used throughout the harness for structured multi-question pauses.

### Integration anchors for a new skill

- `cortex_command/backlog/create_item.py::create_item()` (lines 84–139) accepts `title/status/type/priority/parent` — no `body` parameter today. A `--body` CLI flag would let the interview write structured body content.
- `pyproject.toml [project.scripts]` (after the `cortex-discovery` entry at line 18) is the registration point for any new console-script.
- Dual-source mirror (`plugins/cortex-core/skills/...`) regenerates from canonical `skills/` via `just build-plugin`; no extra step needed beyond editing canonical sources.
- `tests/test_dual_source_reference_parity.py` and `tests/test_skill_contracts.py` validate new skill files.

## Web Research

### Prior art for the "Why/What not How" discipline

- **Shape Up** (Basecamp/Ryan Singer) — https://basecamp.com/shapeup/1.5-chapter-06 — pitch ingredients: Problem, Appetite, Solution, Rabbit Holes, No-gos. Problem section requires *"a single specific story that shows why the status quo doesn't work."* Structurally separates intent from mechanism.
- **Toyota A3 / 5 Whys** — https://www.learnleansigma.com/guides/a3-problem-solving/ — *"When writing a problem statement, you should not mention solutions yet."* Left side = problem analysis; right side = countermeasures. Explicit structural separation.
- **Jobs-To-Be-Done** — https://strategyn.com/customer-needs-through-a-jobs-to-be-done-lens/ — *"A job to be done is neither a product nor a solution itself."* / *"Desired outcomes are devoid of solutions."* Useful operational test: "devoid of solutions".
- **Specification by Example / BDD** (Adzic, Cucumber) — *"The HOW should be kept separate from the WHAT."* Cucumber anti-pattern: *"writing step definitions that are too implementation-specific."*
- **XY Problem** — https://xyproblem.info/ — canonical industry term for "asking about your attempted solution rather than your actual problem." Spec should cite by name — Schelling point.
- **Simon Tatham, "How to Report Bugs Effectively"** — https://www.chiark.greenend.org.uk/~sgtatham/bugs.html — *"Providing your own diagnosis might be helpful sometimes, but always state the symptoms."* Symptom-voice vs theory-voice distinction.
- **Mike Cohn user stories** — https://www.mountaingoatsoftware.com/agile/user-stories — baseline "As a... I want... so that..." template. Does NOT explicitly forbid How.
- **Sherif Mansour, "How we've destroyed user stories"** — https://sherifmansour.medium.com/how-weve-destroyed-user-stories-8b36120645c6 — *"We got fixated on the format without understanding the intent."* / *"We fell back to writing a list of functional, solution-oriented requirements."* Direct evidence that prose-only template discipline degrades in practice.

### Structured-intake mechanisms

- **GitHub Issue Forms** — https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms — supports `required: true`, dropdowns, textareas. No regex validation on text (open feature request: https://github.com/orgs/community/discussions/10227). Guidance: *"not so burdensome that contributors give up halfway through."*
- **Linear**: spec template explicitly *includes* How — different discipline at spec-time vs intake-time. Informative.

### Prescriptive-language signal patterns (distilled from sources)

- **Modal verbs of prescription**: "should use", "should be implemented with", "the fix is to", "we should add", "implement using", "use library X".
- **Named technologies/libraries/functions in Why/What sections**: any concrete library, file path, function name, framework, or design pattern.
- **"Just" + verb**: "just add X", "just refactor Y".
- **Code blocks in problem statements**: near-100% precision signal of How leakage.
- **Theory-voice**: "is caused by", "because of the way X does Y" (vs symptom-voice: "happens when I do X and I see Y").
- **XY-problem signature**: ticket leads with "Add ability to do Y" without ever stating the underlying X.

### AI-coding-agent prior art

Thin. No published skill/slash-command specifically for interviewing humans to author tickets for downstream AI consumption with anti-prescriptive guardrails. The closest published guidance: *"unclear prompts lead to inconsistent results."* This is genuinely novel territory — the spec can lean on general industry prior art (XY problem, Shape Up, A3, BDD) without conflicting with an established AI-specific convention.

### Known failure modes for structured intake

- **Burden / drop-off** — too many required fields → authors bail or stuff everything into one field.
- **Format-over-intent drift** — enforcing shape without enforcing depth produces empty templates filled with prose-as-ritual.
- **"So that" degeneration** — Why fields restate the What.
- **Workflow abandonment when surprise-introduced** — coexistence with `add` is well-motivated.
- **Solutions masquerading as problems** — even well-meaning authors do this routinely.

## Requirements & Constraints

### Load-bearing project rules

- **CLAUDE.md "Design principle: prescribe What and Why, not How"** (lines 64–70): *"describe decisions to be made, gates to enforce, output shapes required, and the intent behind each (the What and Why). Resist prescribing step-by-step method (the How). The reasoning: capable models (Opus 4.7 and later) determine method themselves given clear decision criteria and intent."* — load-bearing principle for the new skill's own prose AND for the discipline it enforces.
- **CLAUDE.md "MUST-escalation policy"** (lines 72–74): soft positive-routing phrasing for new authoring. Interview prompts should not escalate to imperative MUST unless an effort=high failure has been demonstrated.
- **CLAUDE.md "Skill / phase authoring guidelines"** (lines 52–58): *"Prefer structural separation over prose-only enforcement for sequential gates. A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction. Prose-only enforcement is appropriate only for guidelines where the cost of occasional deviation is low."* — directly relevant; suggests the interview SHOULD be a structural gate, not prose-only.
- **schema.md:62–71** already encodes exploratory-framing as prose-only. The user's request is for stronger enforcement than prose alone delivers.
- **Solution horizon** (project.md): *"Before suggesting a fix, ask: do I already know this needs redoing... If yes, propose the durable version."* — extracting shared discipline once vs. duplicating between `/discovery` and `/backlog` is a Solution-horizon-relevant choice.

### Architectural constraints

- **File-based state** (ADR-0001) — output must be markdown files with YAML frontmatter; no DB.
- **CLI wheel + plugin distribution** (ADR-0002) — CLI surface must register via `[project.scripts]`.
- **SKILL.md-to-bin parity** (`bin/cortex-check-parity`) — any new `cortex-*` script must be wired through a skill/requirements/docs/hooks/justfile/tests reference or added to `bin/.parity-exceptions.md`.
- **Dual-source enforcement** — edit canonical `skills/` only; mirror auto-regenerated.
- **Backlog schema** (`skills/backlog/references/schema.md`) — frontmatter is fixed; new skill authors body content into the markdown after the frontmatter.

### No-go boundary

- Out of scope per project.md: dotfiles, app code, published packages. The new skill stays within the agentic-layer surface (`skills/`, `cortex_command/`, harness prose).

## Tradeoffs & Alternatives

Six shapes considered. Brief summaries; see Open Questions for the spec-phase decision points.

- **A — Top-level `/backlog-create` slash command (peer of `/backlog`)**: full coverage IF every callsite is rewired. Collides with the `/backlog` namespace; introduces a third surface touching the same data; alignment with the existing orchestrator+sub-skill pattern is poor.
- **B — New subcommand `/cortex-core:backlog new` (interview path) alongside `add` (stub path)**: matches existing `add|list|pick|ready|archive|reindex` shape; respects "keep `add` valuable" constraint. One file changes plus rewire of harness prose. Risk: two co-equal entry points means stale references to `add` skip the discipline (mitigable with a one-line `add` → `new` nudge).
- **C — Script-level interview (`cortex-create-backlog-item --interview`)**: enforcement at the data layer. Fights `AskUserQuestion` UX, splits non-interactive callers (overnight runner, morning-review), can check non-empty but not semantic quality. Not recommended.
- **D — Shared sub-skill (`/backlog-author` or `references/ticket-authoring.md`) extracted from `/discovery`'s template, invoked by a new `/backlog new` subcommand (i.e., D layered on B)**: physically shares the discipline source between `/backlog new` and `/discovery decompose`. Mirrors the `/requirements` → `/requirements-gather` + `/requirements-write` canonical shape. Highest maintainability; durable per Solution-horizon. Caveat: user said "possibly sharing pattern" — D goes further (physical extraction), which is a stronger claim than the user made.
- **E — Validator-only (extend LEX-1 with prescriptive-English patterns)**: lowest complexity, fully misses the user's stated "interview-driven" preference. Friction lands at commit time after the author has already framed thinking the wrong way. False-positive rate on English patterns will erode trust.
- **F — Prose-only stronger template in schema.md + backlog/SKILL.md**: lightest touch, best-aligned with "prescribe What and Why, not How" in the abstract. But (1) the user explicitly asked for an interview — a soft escalation signal that prose alone is failing today, and (2) schema.md:64–70 already has prose-only guidance and the user is asking for more.

**Research-recommended approach**: **D layered on B** — new `/cortex-core:backlog new` subcommand that delegates body authoring to a shared sub-skill (`/backlog-author` or equivalent) which both `/backlog new` and `/discovery decompose` invoke. Optional follow-up: extend LEX-1 with English prescriptive patterns. Rationale: matches the repo's canonical thin-orchestrator + interview-sub-skill pattern (`/requirements`); single source of truth for ticket-body discipline; full coverage at user-facing surfaces; honors "keep `add` valuable" by leaving `add` as the raw-stub path; the durable shape matches Solution-horizon ("propose the durable version" when a follow-up to deduplicate is already foreseeable).

## Open Questions

These need spec-phase resolution before plan/implement. Each is a decision the spec author must make explicitly.

- **OQ1 — Skill shape**: Confirm Alternative D (subcommand + shared sub-skill physically extracted from discovery) vs Alternative B (subcommand only; discovery's template stays in `decompose.md`). The research recommendation is D, but B is a defensible smaller step. Deferred: will be resolved in Spec by asking the user.
- **OQ2 — Interview body shape**: Resolved after symmetric secondary research (defense-of-current + failure-of-alternative + neutral-comparator). Convergent finding: every long-running RFC/ADR/design-doc tradition (IETF, PEP, Rust RFC, KEP, Nygard ADR, Google design doc, Shape Up, Amazon PR/FAQ) places **intent before mechanism** in named separate sections; modern templates (post-2010) add an **explicit scope-exclusion field** (Non-Goals, No-gos, Boundaries). Discovery's existing `Role / Integration / Edges / Touch points` template maps directly to arc42's Building Block View (Responsibility / Interface / Boundary), C4 model component-level, and DDD Context Mapping — and survived 19 commits of editorial pressure inside cortex-command, including the May 11 `9cc14898` reframe that explicitly ablated competing structures while leaving R/I/E/T untouched. Why/What/Acceptance-style templates have documented multi-year failure modes (Mansour: "fixated on format without understanding intent"; Evans: "Why section degenerates into restatement of What"; Linear's explicit anti-user-story stance). Spec recommendation: **adopt R/I/E/T verbatim** for the shared sub-skill, **with an optional prepended `## Why` section** to mirror the convergent intent-before-mechanism pattern across durable templates (the prepended Why anchors the intake stage; the existing R/I/E/T carries the architectural slot for downstream AI-planner consumption). LEX-1 scanner needs a config update to add `Why` to the forbidden-for-prescription set. Resolved in Spec.

  Secondary-research sources: arc42 §5 Building Block View (https://docs.arc42.org/section-5/), C4 model (https://c4model.com/), Nygard ADR (https://github.com/joelparkerhenderson/architecture-decision-record), Sherif Mansour "How we've destroyed user stories" (https://sherifmansour.medium.com/how-weve-destroyed-user-stories-8b36120645c6), David Evans "As a/I want/So that Considered Harmful" (https://blog.crisp.se/2014/09/25/david-evans/as-a-i-want-so-that-considered-harmful), Linear "Write issues not user stories" (https://linear.app/method/write-issues-not-user-stories), Industrial Empathy "Design Docs at Google" (https://www.industrialempathy.com/posts/design-docs-at-google/), Shape Up (https://basecamp.com/shapeup/1.5-chapter-06), Kubernetes KEP template, O'Reilly "How to Write a Good Spec for AI Agents".
- **OQ3 — Harness rewire scope**: Confirmed list (from codebase agent): `skills/dev/SKILL.md:149,231`, `skills/morning-review/SKILL.md:91`, `skills/lifecycle/references/clarify.md:19`, `skills/discovery/SKILL.md:87` (promote-sub-topic), and any prose inside `skills/backlog/SKILL.md` that mentions `add` as the canonical creation path. Spec must confirm whether the lifecycle's "offer to create a backlog item" Clarify Context B prose changes from optional to a stronger nudge. Deferred: will be resolved in Spec.
- **OQ4 — `add` → `new` relationship**: Should `/cortex-core:backlog add` continue to work unchanged, or display a one-line "consider `new` for non-trivial items" nudge before invoking `cortex-create-backlog-item`? Trade-off: zero friction vs. higher adoption rate of the discipline path. Deferred: will be resolved in Spec.
- **OQ5 — LEX-1 extension scope**: Should this lifecycle extend `bin/cortex-check-prescriptive-prose` to detect English prescriptive patterns (modal verbs, named-technology mentions in Why/What sections), or leave that scanner work to a follow-up ticket? Web research provides a concrete signal list (modal verbs, "just" + verb, code blocks in problem statements, theory-voice). Trade-off: belt-and-suspenders enforcement now vs. shipping the interview discipline first and validating before adding more rails. Deferred: will be resolved in Spec.
- **OQ6 — Programmatic-caller carve-out**: `cortex-create-backlog-item` is called non-interactively by the overnight runner and morning-review programmatic paths. Confirm the script remains usable without the interview (i.e., the interview lives at the SKILL.md layer, not enforced at the script). Codebase research suggests this is the correct factoring; spec must confirm. Deferred: will be resolved in Spec.
- **OQ7 — Discoverability when Claude is the author**: when the harness instructs Claude (not a human user) to "create a backlog item" mid-flow (e.g., morning-review uncovers an investigation item), the interview UX (`AskUserQuestion`) would interrupt an automated flow. Two options: (a) Claude self-answers the interview when no human is in the loop, (b) Claude calls the raw `add`/`cortex-create-backlog-item` path and the discipline applies only to human-initiated creation. Deferred: will be resolved in Spec.
