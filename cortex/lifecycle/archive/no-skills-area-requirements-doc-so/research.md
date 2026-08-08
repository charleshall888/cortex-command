# Research: Make area requirements reach the phases that author code

**Scope anchor (clarified intent):** Make area requirements reach the phases that author code, so a
builder is planned and reviewed against the constraints governing the files it edits — and establish by
measurement whether the spec→plan flow-through is in fact lossy before adding any load.

**Provenance note.** This lifecycle was filed as #476 ("No skills area requirements doc, so 45 lifecycles
editing skills review against project.md only"). The clarify critic found its Why did not survive
verification, and Clarify retargeted the lifecycle to the question above. The ticket body still describes
the original scope. See `## Open Questions` Q1 for the disposition.

---

## Codebase

Produced by the orchestrator after the dispatched agent idled twice without reporting.

### The load path exists at four callsites, none of them authoring phases

`grep -rn "cortex-load-requirements" skills/` returns exactly four prose callsites:

- `skills/refine/references/clarify.md:9`
- `skills/discovery/references/clarify.md:7`
- `skills/discovery/references/research.md:9`
- `skills/build/references/review.md:9`

`grep -c -i requirements skills/build/references/plan.md` → **0**. Same for `implement.md`. The two phases
that author code never load requirements.

`skills/build/references/plan.md:7` (§1 Load context) reads `research.md`, `spec.md`, and
`cortex/lifecycle.config.md` — nothing else.

### The builder has exactly one context channel

`skills/build/references/implement.md`, `### Builder brief`:

> Each builder gets the task's full block from plan.md, 2–3 sentences of architectural context from the
> plan's Overview, and these standing instructions:

and among those standing instructions:

> Read `cortex/lifecycle/{feature}/spec.md` **only if the task references it**.

This is decisive for one candidate shape: **spec-carries-forward cannot reach the builder**, because the
builder is explicitly instructed not to open the spec. It can reach the plan author only.

The narrowness is deliberate, not an oversight — `plan.md:56`, Authoring rules:

> **Task sizing** — a self-contained unit an implementer with no prior context can complete from the task
> text and its referenced files alone.

The harness has committed to builders having no prior context. That makes the plan task block the only
place a governing constraint can live, and the task template already has the slot — `plan.md:39`:

```
- **Context**: {paths, signatures, type defs, pattern references}
```

This is exactly where #472's plan author hand-wrote the ratchet and mirror constraints. The mechanism the
original ticket described was real; it misidentified the fix as a missing *document* rather than a missing
*load at plan*.

### Nothing derives areas from touched paths

`grep -rn "area_for_path\|infer_area\|AREA_MAP\|areas_from" cortex_command/ bin/` → no matches. Every
`areas` consumer (`cortex_command/lifecycle/create_index.py`, `backfill_index_areas.py`, `spec_approve.py`,
`load_requirements_cli.py`, plus the dashboard) reads an author-declared value and copies it forward. A
file-identity trigger (the Cursor/Copilot/Windsurf pattern, see `## Web`) would be new machinery here, not
a configuration change.

### Authoring cost of any prose-based fix

`skills/build/references/` sits at its ratchet ceiling — `size-pin.txt` = 57267, measured content = 57267,
zero headroom. `skills/refine/references/` (20568) and `skills/discovery/references/` (12916) are likewise
at pin exactly; this is what a down-only ratchet produces by construction, not a fact about any one area.
Adding prose to `plan.md` or `implement.md` therefore requires a hand-raised `# raised:` exception with a
lifecycle-id, per `docs/policies.md:15`.

Combined with the no-tests-pinning-skill-prose rule, the testable form of any fix here is a CLI verb, not
a paragraph.

---

## Empirical Measurement

**Angle warning:** the dispatched measurement agent idled three times without reporting. Every figure below
was produced by the orchestrator. Scripts are in the session scratchpad (`cov.py`, `m2.py`, `m2b.py`).

### Baseline coverage — reproduces the ticket, slightly conservative

196 active lifecycle `index.md` files, exact kebab-normalized area lookup against `project.md`'s
`## Conditional Loading` map:

| | ADR-0037 (2026-08-07) | ticket #476 | this run (2026-08-08) |
|---|---|---|---|
| `loaded` / `unmapped` / `no-area` | 86 / 61 / 44 | — | **89 / 63 / 44** |
| declare `areas: [skills]` | — | 57 | **59** |
| already covered by another area | — | 12 | **12** |
| would newly gain coverage | 45 | 45 | **47** |

Raw declaration tail (all areas, active): `skills` 59, `lifecycle` 50, `overnight-runner` 26, `backlog` 13,
`hooks` 9, `tests` 8, `docs` 4. Note the ticket's tail figures counted raw declarations while an
unmapped-only count gives `skills` 47, `hooks` 7, `tests` 5, `docs` 3 — two different denominators that are
easy to conflate.

### M1 — does the load correlate with constraints reaching the artifact?

Proxy: does an artifact cite a requirements doc at all?

| artifact | n | cites **any** `cortex/requirements/` doc | cites an **area** doc | cites `project.md` |
|---|---|---|---|---|
| `plan.md` (never loads) | 187 | 47 (25%) | 23 (**12%**) | 23 (12%) |
| `spec.md` | 188 | 63 (34%) | 28 (**15%**) | 37 (20%) |
| `review.md` (does load) | 166 | 68 (41%) | 29 (**17%**) | 54 (33%) |

Commands:

```bash
grep -l "cortex/requirements/" cortex/lifecycle/*/plan.md | wc -l
grep -lE "cortex/requirements/(lifecycle|backlog|pipeline|observability|multi-agent|remote-access|training)\.md" \
  cortex/lifecycle/*/plan.md | wc -l
```

**Reading.** The area-doc gradient is nearly flat: the phase that loads area docs cites them 5 points more
than the phase that never sees them. The `project.md` column is the control that exposes the confound —
`project.md` is always resident at every phase, yet its citation rate climbs 12% → 20% → 33% across the
same artifacts. The gradient therefore tracks **what a phase is for** (review's job is drift-checking), not
what it loads.

**Limitation, stated plainly.** Citation is a weak proxy in both directions. A plan can obey a constraint
without naming its source document, so 12% is a floor on adherence rather than a measure of it. This
evidence is weak *for* the fix and weak *against* it; it is reported because the repo's bar puts the burden
of proof on the addition.

### M2 — do lifecycles under-declare `areas:`? **Not reliably measurable by the method available.**

Attribution by "commits touching `cortex/lifecycle/<slug>/`" is structurally blind to the commits that
matter. Verified: commit `5aca8df8` ("Retire tag-matching prose and read the COVERAGE marker in review"),
which edited `skills/build/references/review.md` for #472, touches **zero** files under
`cortex/lifecycle/requirements-loader-matches-index-tags-against/`.

A first pass reported "38 lifecycles touched `skills/**` without declaring `skills`". Spot-checking killed
it — `fix-api-key-helper-reference`'s only attributable commit is a **1638-file** umbrella relocation
(#202), and `cortex-lifecycle-enter-state-accept-a` drew its `skills/` hits from a 147-file `areas:`
backfill and a 36-file cross-cutting change.

Excluding commits over 40 files (165 sweep commits dropped), over the 131 lifecycles with declared areas
and attributable non-sweep commits:

- touched an undeclared area: **23 / 131** — a lower bound only
- touched `skills/**` without declaring `skills`: **7** — lower bound
- declared an untouched area: 110 / 131 — **discarded as an artifact** of the blind-spot above

**Conclusion: M2 is unmeasured.** The correct attribution is by backlog-number reference in commit
messages, which was not run. Do not cite the 23/131 or the 7 as a rate.

### M3 — load cost

`cortex/requirements/` sizes: `lifecycle.md` 19,172 B, `pipeline.md` 25,105 B, `backlog.md` 12,157 B,
`observability.md` 11,855 B, plus `project.md` (~27 KB) and `glossary.md` always resident.

The repo has already measured this class directly — `cortex/requirements/lifecycle.md:94`: a
lifecycle-tagged feature loads `project.md` + `glossary.md` + `lifecycle.md` = 45,487 B against 31,094 B
before that doc existed, **+14,393 B**, "well above the 33,400–36,400 B projected". A second load at plan
repeats that per session, and `lifecycle.md:98` establishes that plan runs in a *fresh session*.

---

## Requirements & Constraints

### `cortex/requirements/project.md`

- **`:99-111` Conditional Loading** — the many-to-one area→doc map; exact kebab-normalized key lookup,
  never substring. Prose in the section must not contain the separator character.
- **`:23` Deletion bias / front-door bar** — "Keeps, safeguards, and measurement tooling must clear the
  same evidence bar as new features — named, specific evidence, not hypotheticals; when a trim is proposed,
  the burden of proof sits on keeping, not deleting." The bar is conjunctive: a ticket adding harness
  machinery names its evidence, **and** an efficiency-framed ticket states its net effect.
- **`:41` Enforcement gates** — "A new gate enters only with its named failure stated here." A drift check
  landing as an enforced gate must be added to that list with named evidence, in `project.md` itself.
- **`:41`, `:62` Reference-size ratchet** — verb-first direction, per-directory `size-pin.txt`, down-only.
  Scope extends past `references/` to `cortex_command/pipeline/prompts/`.
- **`:7`, `:21` Token economy** — "measured runtime cost is turns × context… the levers are session length,
  turn count, and fan-out width — not resident-prose micro-trims."

### `cortex/requirements/lifecycle.md`

- **`:98` Phase boundaries are session boundaries** — "a fresh session after refine (spec approval) runs
  plan+implement, and a plan that consumed heavy context hands implement to another fresh session."
  Rationale: session carry is superlinear in turns, measured 37–61% of orchestrator spend. **This means a
  clarify-time load cannot reach plan through session context at all** — only through an artifact.
- **`:105`** — "Every run of the loader emits one `COVERAGE:` line on stderr, **which the Review phase
  reads**." Review is named; Plan and Implement are not. No text anywhere assigns requirements-propagation
  responsibility to plan or implement — this is an unfilled slot, not a contradiction.
- **`:94`** — the measured +14,393 B area-doc load cost (see M3).
- **`:120`** — ad-hoc lifecycles carry `areas: []` and report `COVERAGE:no-area`. 44 active lifecycles are
  in this state; no load-timing change helps them.
- **`:122-126` Open Questions** — does *not* list plan/implement loading. The one adjacent open question is
  scoped to Review's warning contract.

### ADRs

- **ADR-0037** (accepted, 2026-08-07) — establishes the area→doc map as the requirements vocabulary. Its
  "Measured outcome" states: "`unmapped` is the expected steady state for 61 lifecycles (`skills` alone
  45), not a defect — no doc is planned for those areas." **This is the sentence the original #476 scope
  contradicted.** The ADR is scoped to *selection* (which doc), not to *timing* (which phase loads) — so
  extending phase coverage is orthogonal to it rather than a reversal.
- **ADR-0009** — body-propagation for `${CLAUDE_SKILL_DIR}`; any propagation of a resolved requirements
  path list into a composed builder prompt must follow it, enforced by `cortex-check-skill-path`.
- **ADR-0036** — "Ceremony relief is not taken on the criticality axis". Establishes the precedent that a
  predicate/gate change requires recorded per-clause justification plus a measured rate for the affected
  class, stated against the corpus baseline. A plan-phase drift check would inherit that bar.
- Surveyed all 37 ADRs; none besides 0037 govern requirements loading or phase context assembly.

### `CLAUDE.md` and `docs/policies.md`

- Editing `skills/` is lifecycle-gated; canonical sources only, mirrors rebuilt from staged blobs.
- **No tests pinning skill prose** — so "plan now loads requirements" cannot be pinned by asserting the
  sentence exists in `plan.md`. To pin the behavior it must move into a CLI verb, per the ADR-0035 worked
  example (`cortex-lifecycle-review-brief`).
- **`docs/policies.md:11`** — structural separation over prose-only enforcement for sequential gates;
  prose-only is appropriate "only for guidelines where the cost of occasional deviation is low." Which
  side of that line this falls on is an evidence question M1 did not settle.
- **`docs/policies.md:53-61` MUST-escalation** — any MUST-strength imperative added to `plan.md` needs a
  linked evidence artifact showing the soft form was skipped.
- **Shipped surfaces carry no repo governance** — rationale text belongs in `CLAUDE.md`,
  `docs/policies.md`, or `cortex/requirements/`, never inline in the phase reference.

### Divergence flagged, not reconciled

`glossary.md:9` cites "→ ADR-0036" for the short-road predicate; ADR-0036's own Context (`:11`) states the
predicate "carries no ADR back-pointer and no ticket number."

---

## Web

### How comparable systems propagate rules to the code-writing step

- **Claude Code** — `CLAUDE.md` always-resident and merged across scopes; `.claude/rules/*.md` load
  automatically *unless* they declare a `paths` glob, which makes them file-triggered. Skills use
  progressive disclosure explicitly for cost: frontmatter at session start, body on fire, references on
  demand. Recommended memory-file ceiling ~40,000 characters.
- **Cursor** — four per-rule activation modes in frontmatter: Always Apply, Auto Attached (`globs`), Agent
  Requested (model reads the description and decides), Manual (`@rule-name`). Mode is an authoring decision
  per rule, not a system-wide choice. *(Third-party corroboration only; no canonical vendor page surfaced.)*
- **GitHub Copilot** — `.github/instructions/*.instructions.md` with an `applyTo` glob; purely
  file-triggered, alongside a repo-wide always-resident file. Extended to PR review in Sept 2025.
- **Windsurf** — same four modes as Cursor, with hard caps (6,000 chars global, 12,000 per workspace rule)
  — the only vendor found putting a number on corpus size.
- **Aider** — `CONVENTIONS.md`, always resident, marked read-only and cache-eligible: its answer to cost is
  caching, not exclusion.
- **AGENTS.md** — single flat always-resident file, "radical simplicity", no globs or modes.

### The trigger distinction that matters here

Cursor, Copilot, and Windsurf all trigger on **file identity** (you touched `src/api/foo.ts`), whereas this
repo triggers on **declared topic** (`areas:` in `index.md`). No published source was found comparing the
two mechanisms' reliability — the agent flagged this as a genuine gap rather than filling it.

### Position vs. length evidence — unresolved, and it cuts both ways

- **Lost in the Middle** (Liu et al., 2023) — U-shaped accuracy curve; 30%+ degradation for material in
  mid-context. Argues *for* restating near the point of use.
- **Context Rot** (Chroma Research, July 2025; 18 SOTA models) — accuracy drops 30–50% non-uniformly with
  length, well before documented context limits. Argues *against* adding length.
- No study measures spec-mediated carry-forward against a fresh reload for this design question.

### Closest structural analog

**GitHub Spec-Kit** runs the same spec→plan→implement pipeline. Its `memory/constitution.md` is loaded at
every phase, **and** `/speckit.plan` runs an explicit constitutional check over requirements + draft plan +
constitution together, with a separate `/speckit.analyze` cross-artifact consistency pass before
implementation. So the nearest prior art adopts load-at-every-phase *plus* an explicit check, and
specifically does not treat spec-carries-forward as sufficient.

### Anti-patterns

Rule bloat is the repeatedly-documented failure of `.cursorrules`: a monolith loaded regardless of
relevance, where the earliest/most important rules are the first compressed out under context pressure.
Consensus mitigations: scope files so they glob-load, prune regularly, and push anything a linter can
enforce deterministically out of the rules corpus entirely. *(Practitioner consensus, blog-level; no
measured adherence-vs-corpus-size curve found.)*

---

## Adversarial

**Angle warning:** the dispatched adversarial agent idled twice without reporting, including after a chase.
The counter-case below was produced by the orchestrator against its own conclusion. Treat it as
self-adversarial — weaker than an independent challenge, and a known limitation of this research.

### Attack 1 — citation is blind to adherence (valid, and it forced a correction)

A plan that *obeys* the ratchet never cites `lifecycle.md`. Citation measures whether an author named a
document, not whether a constraint governed the work. The proxy cannot distinguish "constraints arrive and
are silently obeyed" from "constraints never arrive."

This attack also exposed a real denominator error in the first M1 pass, which used all plan/review files
including the 63 `unmapped` and 44 `no-area` lifecycles that cannot cite an area doc. Corrected, over
lifecycles that actually resolve an area doc, citing **their own** resolved doc:

| artifact | cites its own area doc |
|---|---|
| `plan.md` (never loads) | 11/83 — **13%** |
| `spec.md` | 14/84 — **17%** |
| `review.md` (does load) | 16/75 — **21%** |

The gap widens from 5 to 8 points but the levels stay low. **79% of reviews that successfully load an area
doc never reference it** — the phase whose job includes a drift check, holding the doc in context.

Fair counter-read, recorded: 13% → 21% is a **1.6× relative lift**, so loading plausibly does something.

### Attack 2 — is `project.md` a valid control?

Partly not. `project.md` is both always-resident and the doc a reviewer is most likely to name, so the
12% → 20% → 33% gradient conflates two effects. The corrected M1 above does not depend on it — it compares
the same doc across phases within the same population.

### Attack 3 — a discriminating test, run and rejected

Proposed: if the review phase's requirements drift check rarely *finds* anything, constraints are not being
violated. Measured over 166 `review.md` files by parsing the `## Requirements Drift` section:

- `none` — **131**
- `detected` — **34** (one in five)
- no section — 1

One in five is not rare, and initially read as support for a real problem. **It does not survive
inspection.** `skills/build/references/review.md:39-41` defines drift's direction: when detected, §3a parses
`## Suggested Requirements Update` and *appends the content into the named requirements file*. Confirmed in
the findings themselves — lifecycle `378`: "`cortex/requirements/project.md` has no reference to this
contract"; `add-docs-adr-with-3-seed`: "`project.md` does not list this new artifact class."

Drift means **the docs are stale relative to what was built** (code → doc), not that code violated a
constraint (doc → code). The 34 detections are evidence about documentation currency and say nothing about
whether constraints reach builders. Test rejected.

Incidental finding: the repo already has a closed feedback loop writing newly-established constraints back
into requirements docs. That is the opposite of the original ticket's "nowhere to land" framing.

### Attack 4 — the 79% could indict consumption, not timing

If four in five loaded area docs go unused at the one phase that loads them, the defect may be in how the
reviewer *consumes* requirements, not in when they load. If so, adding a load at plan adds a second unused
load. This reframe is not resolved here and is the most promising direction if anyone revisits this — it
would need a different measurement than any run above.

### What the evidence actually supports

Three independent attempts to measure the theorized failure came up empty: citation rate (flat gradient,
weak proxy in both directions), `areas:` under-declaration (unmeasurable with available attribution), and
drift detections (measures the reverse direction). The structural findings are real and verified — the
builder's only context channel is the plan task block, and it is explicitly told not to read the spec — but
"the channel is narrow" is not the same claim as "constraints are being lost through it." No measured
failure rate exists for any candidate shape to move, which is the same bar the original ticket failed.

---

---

## Open Questions

1. **Disposition of #476 itself.** The ticket body still describes the original scope (write
   `cortex/requirements/skills.md` + a map row), which the clarify critic refuted and which contradicts
   ADR-0037's stated steady state. Resolve at Spec: either retarget the body to the researched question, or
   cancel the ticket. **Not deferrable — a spec cannot be written against a body this research contradicts.**

2. **Does the front-door bar clear for any candidate shape?** M1's area-doc gradient (12% → 15% → 17%) with
   the always-resident `project.md` control (12% → 20% → 33%) is consistent with "phase purpose drives
   citation, not loading". No candidate shape currently has a named, measured failure it would move.
   `project.md:23` and `:41` both put the burden on the addition. **Resolve at Spec.**

3. **M2 is unmeasured and the method is known.** Re-run attribution by backlog-number reference in commit
   messages rather than by lifecycle-directory path. Until then, no claim about `areas:` accuracy is
   supportable in either direction — including the claim that declarations are fine. **Deferred with
   rationale:** it does not gate the disposition in Q1, because under-declaration argues against every
   candidate shape equally (a wrongly-declared area loads the wrong doc at any callsite).

4. **Is citation a usable proxy at all?** A plan can obey a constraint without naming its source. A
   discriminating measurement would compare plans against constraints they violated, not constraints they
   cited. No such measurement was designed. **Deferred with rationale:** designing it is a larger exercise
   than the change it would justify, which is itself evidence about proportionality.

5. **The `no-area` population is untouched by every candidate.** 44 active lifecycles declare no areas at
   all (`lifecycle.md:120`), and Context-B ad-hoc lifecycles never get an `index.md`. Any fix framed as
   "load area docs earlier" leaves roughly a quarter of the corpus exactly where it is. **Deferred with
   rationale:** it bounds the ceiling of any fix rather than choosing between fixes.
