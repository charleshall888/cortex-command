# Research: Give the lifecycle area a real `cortex/requirements/lifecycle.md` and make the `project.md` Conditional Loading row actually resolve to it

Feature: `no-lifecycle-area-requirements-doc-so` (backlog #469). Tier `moderate`, criticality `high`.

Angles dispatched: Codebase, Requirements & Constraints, Adversarial. No Web angle — the work is entirely internal repo governance with no external dependency, protocol, or library question.

**Every load-bearing claim below was re-verified by running or reading the code directly, not accepted on agent report.** Where the ticket body and the corpus disagree, the corpus wins and the divergence is recorded.

## Codebase

### Loader mechanics (`cortex_command/lifecycle/load_requirements_cli.py`)

- `_parse_conditional_loading` splits each `## Conditional Loading` bullet on the **first** U+2192 and treats **all** text right of the arrow as the path, `exists()`-checking it verbatim (`resolve`, `emit`).
- The current row's path is the literal string `cortex/requirements/lifecycle.md (NOT YET WRITTEN — …)`. **Verified executably**: with a real `cortex/requirements/lifecycle.md` present in a scratch fixture, the loader still printed `(skipped: file absent)`. Writing the doc alone does not close the gap — the row must become a bare path in the same change.
- Tag matching is ASCII-casefold substring, `tag.lower() in trigger.lower()`, against the text **left** of the arrow. Current trigger: `lifecycle state machine/phase vocabulary/served verbs (next, advance, enter)/escalation`.
- The loader reads `cortex/lifecycle/{slug}/index.md` `tags:`. It **never** reads the backlog item's `areas:` field. The ticket body conflates the two; no `index.md` in the corpus carries an `areas:` key.
- The ticket's guessed touch-point `cortex_command/requirements/` does not exist.

### The warning channel is already silenced

`resolve()` sets `fallback_note` only `if not matched`. The row #454 landed makes the `lifecycle` tag match the trigger **whether or not the file exists**. Verified at HEAD: `cortex-load-requirements --feature escalated-is-terminal-so-operator-direction` writes **0 bytes to stderr**.

The `no area docs matched` line quoted in the ticket's Why therefore **cannot fire any more**. #454's "partial mitigation" did not make the gap visible — it converted a firing warning into a silent skip. `skills/build/references/review.md:9` keys its warning solely on that note and otherwise instructs reading every "non-skipped" path, so a `(skipped: file absent)` entry is dropped with no signal at all.

### Reach under the current matcher

64 of 351 `cortex/lifecycle/*/index.md` files carry a bare `lifecycle` or `escalation` tag. Features tagged `[cli-served-lifecycle-state-machine]` — `374/`, `378/`, `build-the-verb-completion-composition-wrapper/`, the three most lifecycle-central lifecycles in the repo — **miss**, because matching is tag-in-trigger and that tag is not a substring of the trigger.

### Relocation inventory (measured)

`project.md` is 121 lines / 29,918 bytes. Twelve lifecycle-only items total **8,031 bytes = 26.8%** of the file:

| Line | Bytes | Item | Normative? |
|---|---|---|---|
| 29 | 467 | Multi-step lifecycle phases (ADR-0004) | |
| 31 | 1,333 | Kept user pauses taxonomy (ADR-0024) | |
| 37 | 492 | Phase boundaries are session boundaries | |
| 38 | 282 | Critical-review gates at spec only | |
| 40 | 670 | The short road (ADR-0036) | "Corrupted reductions always take the long road" |
| 49 | 726 | Served lifecycle verb class (ADR-0024/0025) | route/phase machine contract |
| 50 | 308 | Consumer `EnterWorktree` authorization (ADR-0008) | |
| 59 | 1,063 | Lifecycle identity is the canonical slug | **MUST** — "#378 defensive str-coercions MUST be retained"; no ADR carries this rule |
| 61 | 954 | Phase vocabulary — `phase` vs `route` | **may not** — pins every machine equality test |
| 63 | 365 | Reviewer brief is a served surface (ADR-0035) | |
| 64 | 679 | Override-reason clause vocabulary (ADR-0036) | |
| 65 | 692 | Events corpus is mixed-format | **Never** suppress such a reader's stderr (#452) |

With ~100-byte pointer stubs, `project.md` → roughly 23,000 bytes, a **~22% net shrink**. Sibling sizes for calibration: remote-access 3.1 KB, multi-agent 9.0 KB, training 9.6 KB, observability 11.9 KB, backlog 12.2 KB, pipeline 25.1 KB.

### Seven ratified lifecycle ADRs are recorded nowhere

`0010` (task_id is plan-task identity), `0012` (merged plan-approval + dispatch selection), `0017` (reconcile lifecycle.config.md sources), `0018` (structural invocation grammar), `0020` (event emission contract), `0022` (explicit-path considerations handoff), `0030` (mode-agnostic interactive dispatch) all exist in `cortex/adr/` and have **zero** citations in `project.md` (verified by grep, 0 hits each).

This is the ticket's strongest justification and it is not the one the ticket makes. The doc is **not** pure relocation — it closes a genuine coverage gap.

### Consumers

- `cortex-load-requirements` call sites: `skills/build/references/review.md:9`, `skills/refine/references/clarify.md:9`, `skills/discovery/references/clarify.md:7`, `skills/discovery/references/research.md:9`. Specify and orchestrator-review inherit the list from Clarify rather than re-loading.
- `cortex-validate-requirements-doc` has a single call site (`skills/requirements/SKILL.md`) and is **not wired into any hook, justfile recipe, or CI workflow** — model-invoked only.
- No existing test asserts on `project.md`'s Conditional Loading content or on `lifecycle.md`'s existence. Writing the doc breaks nothing and is covered by nothing.
- `cortex/requirements/` is **not** covered by the reference-size ratchet — verified by enumerating `scripts/ratchet_refs.py:enumerate_reference_dirs`, which returns only `skills/*/references`, plugin references, and `cortex_command/pipeline/prompts`.

## Requirements & Constraints

### The bar this ticket must clear

- **Front-door evidence bar** (`project.md:23`, restated in `CLAUDE.md` Conventions): "an efficiency-framed ticket states its expected net effect on the surface it claims to shrink." The ticket currently says only a hedged "should shrink project.md" with no figure. The measured figure is above: 8,031 bytes out, ~1,200 back, ~22% net.
- **Token economy** (`project.md:7,21`): conditional loading is the structural device that keeps new prose off the default-load path.
- **Solution horizon** (`project.md:25`): the row at `project.md:107` already names this doc as the pre-planned durable fix, so this closes a named gap rather than inventing scope.

### Area-doc template contract (`skills/requirements/SKILL.md:55-67`)

Seven H2s in order, verbatim: `## Overview`, `## Functional Requirements` (one H3 per capability with `**Description**`, `**Inputs**`, `**Outputs**`, `**Acceptance criteria**`, `**Priority**`), `## Non-Functional Requirements`, `## Architectural Constraints`, `## Dependencies`, `## Edge Cases` (`**Condition**: behavior`), `## Open Questions` (`- None` when nothing is open). Header: `# Requirements: {area}`, `> Last gathered:`, and verbatim `**Parent doc**: [requirements/project.md](project.md)`.

**No token budget applies to area docs** — `validate_requirements_doc_cli.py` returns `{"name": "optional-token-budget", "applicable": False}` for area scope; the 1,200-token cap is `project.md`'s `## Optional` only.

`## Architectural Constraints` is specified as **"strategic constraints only; operational detail lives in CLAUDE.md"** — so relocation has three destinations, not two: the area doc, `CLAUDE.md`, or stay put.

### `## Global Context` is a third routing option

Defined as "bare paths … that every consumer loads on every invocation **regardless of tag matches**," and "listing one before its file exists is valid." `glossary.md` is the sole occupant.

### Boundary map — surface → owning doc

| Surface | Owner |
|---|---|
| Statusline / dashboard narration of lifecycle phase | `observability.md` (stated explicitly at `project.md:107`) |
| Session-level state machine (`planning → executing → complete`) and feature status (`pending → running → merged`) | `pipeline.md:13-29` |
| Post-merge review dispatch, gating matrix, rework loop | `pipeline.md:75-88` |
| Agent spawning, worktrees, model selection | `multi-agent.md` |
| Feature-phase vocabulary, transition table, served verbs, kept-pause taxonomy | **proposed `lifecycle.md`** |

### Review consumption contract

`skills/build/references/review.md:39-43`: on `requirements_drift: "detected"`, §3a parses `## Suggested Requirements Update` (`File`/`Section`/`Content`) and **appends** `Content` at the end of the named `Section` in the target file, cap 2 retries, then `--breach` without blocking. The new doc must therefore be section-addressable, and it is an unbounded append target.

### No stated principle for when an area earns a doc

Searched requirements, ADRs, and policies: **no stated requirement found**. `backlog.md:13` records its own promotion retrospectively but names no reusable threshold. `project.md:80` records "Discovery is documented inline (no area doc)" with no rationale. Meanwhile `skills` (133 tickets), `hooks`, `docs`, `tests`, `install`, and `requirements` have no doc — so the ticket's claim that "every other area in the repo has both a doc and a row" is false.

## Adversarial

### The Global Context alternative — rejected, with one carve-out

Loading `lifecycle.md` unconditionally would fix both the 72%-miss and MUST-goes-dark problems outright and make the pointer-stub ruling redundant. It is nonetheless disproportionate: it taxes every dashboard, remote-access, and backlog ticket forever, contradicting the loader's stated purpose (`load_requirements_cli.py:8-10`, "avoiding both under-loading … and over-loading") and `project.md:7,21`. `glossary.md` earns its slot by being ~9 lines of universal vocabulary; a 10–14 KB governance doc does not. **Keep Conditional Loading.**

### The relocation half has zero or negative value — the central finding

Today a lifecycle-tagged feature's reviewer **already reads all 12 lines**, because `project.md` loads unconditionally on line 1 of every load. So:

- For the **correctly-tagged** case, relocation nets no content gain — the same material arrives by a different route, plus new template boilerplate.
- For the **wrong-tag / incidentally-lifecycle-adjacent** case, relocation makes things **strictly worse**: content that used to arrive unconditionally now never arrives.

This inverts the ticket's premise. The *net-new* half (seven uncited ADRs, genuine area requirements) carries the value; the *relocation* half is where the risk sits.

### Specific misclassifications in the inventory

- **Line 40 (short road)** duplicates `glossary.md:9`, which is in Global Context and therefore already loads unconditionally. Relocating it creates a third copy and is strictly worse than the status quo. `lifecycle.md` should point at the glossary, not restate it.
- **Line 59 (the MUST)** is the most dangerous move: a future ticket tagged only `slug-resolution` editing `resolve.py` would silently stop seeing a MUST it gets unconditionally today.
- **Line 61 (`route` vs `phase`)** is cross-owned with `observability.md` — statusline narration renders through `phase_labels.phase_label`, and an `observability`-tagged ticket would lose the rule.
- **Line 65 (mixed-format events corpus)** is load-bearing for the dashboard, which reads per-feature `events.log` (`observability.md:16`); a dashboard ticket could reproduce the #452 failure from the other side.
- **Lines 37/38** read partly as multi-agent dispatch policy ("reviewer width is 1–2") wearing a lifecycle label.
- **Line 49** smuggles a runbook pointer (`docs/rollforward-exit.md`) into what the template reserves for strategic constraints.

Uncontested lifecycle-only: **29, 31, 49, 63**, plus 59's content modulo the reachability regression.

### Unbounded growth with no brake

Area docs have no token budget, `cortex/requirements/` is outside the reference-size ratchet, the validator is not wired into CI, and §3a auto-appends on every detected drift. That is the exact shape that let `project.md` reach 29,918 bytes despite its own deletion-bias governance. Nothing in this ticket prevents a future reviewer from auto-appending lifecycle content back into `project.md` — the relocation clears today's backlog and adds no mechanism against line 13 landing next month. Stub/detail sync is prose-only: nothing validates that a `project.md` pointer still resolves to a section that exists in `lifecycle.md`.

### The new silent failure

`review.md:9`'s warning is boolean — it fires only when **zero** area docs match, never when the *relevant* one is missing. A ticket tagged `observability` that touches `resolve.py` or an events.log parser matches `observability.md`, so the warning stays silent while the lifecycle content it needs never loads. This is the same shape as #454's anti-pattern (a present-but-wrong match silencing a warning that should fire), relocated from the loader layer to the content layer — a **new** failure mode this ticket introduces rather than one it inherits.

### Template fit

A state machine's requirements are transition rules and invariants, not Description/Inputs/Outputs capability records. The relocated content is already prose-shaped for `project.md`'s constraint style, so force-fitting it under `## Functional Requirements` headers is a likely, not hypothetical, outcome. The lifecycle functional surface is large (~15 subsystems versus remote-access's 2), which pushes toward `pipeline.md`'s 194-line scale unless thin sections are kept genuinely thin.

## Open Questions

- **How much of the 12-bullet inventory should actually relocate?** The Codebase angle classified 12 items as lifecycle-only; the Adversarial angle contests 5 of them (40, 59, 61, 65, and 37/38 partially) and endorses only 29, 31, 49, 63 outright. These are directly contradictory and Spec must resolve the split rather than average it. The measured ~22% shrink figure assumes the full 12 and drops to roughly 8–10% at the contested-minus set.
- **Does the pointer-stub ruling survive the Adversarial finding?** If relocation nets zero for correctly-tagged features and negative for wrong-tag ones, the stub compromise may not be sufficient for the normative items (59, 61, 65). Options for Spec: leave those three in `project.md` in full and relocate only the non-normative remainder; or relocate everything and accept the regression; or duplicate the normative clauses into `observability.md` where they are genuinely cross-owned.
- **Should the trigger text be widened, and to what?** `state-machine` is safe in the current corpus (matched only by already-lifecycle-tagged features). `review`, `plan`, and `build` carry substring false-positive risk with no word-boundary protection. **Deferred to Spec** with a recommendation: widen to `state-machine` only if at all, since broader terms reuse the substring machinery #472 identifies as the root defect and would need re-doing when #472 lands.
- **Is there a size or growth brake for the new doc?** No budget, no ratchet, no CI gate, and §3a auto-appends. Spec should decide whether to state an explicit size direction in the doc itself, extend the ratchet to `cortex/requirements/`, or accept unbounded growth. Extending the ratchet is arguably its own ticket.
- **Should a regression test pin the row?** No test references `lifecycle.md` or the `NOT YET WRITTEN` marker, so the specific #454 defect (a routing row whose path can never resolve) has no guard. A test asserting every `## Conditional Loading` path resolves to an existing file — or is explicitly marked absent — would catch the whole class. Deferred decision: whether that is in scope here or a separate gate ticket, noting `project.md:41`'s rule that a new gate enters only with its named failure stated.
- **Where is the `lifecycle.md` / `pipeline.md` seam stated?** `pipeline.md` owns the session-level state machine and feature-status vocabulary; the proposed doc owns feature-phase vocabulary. The two use confusingly adjacent language and no disambiguation currently exists in either doc. Deferred to the doc's own `## Open Questions` unless Spec chooses to state it.
