# Research: Make the triage board's Ready block agree with the dev skill's readiness rule and with the epic block

Ticket: `cortex/backlog/425-triage-routes-ready-items-by-ticket-type-so-a-refined-bug-chore-never-reaches-build-and-the-two-blocks-contradict-each-other.md` (type `bug`, complexity `complex`, criticality `high`).

Clarify's entering intent was Option A — delete the `→ workflow` verb from rendered output and render a readiness mark instead, moving routing authority into `skills/dev/SKILL.md`. **Research overturned that direction.** See Tradeoffs, Adversarial, and Open Questions.

## Codebase

`cortex_command/backlog/triage.py`:

- `_ready_set(items)` (`:41-70`) — filters via `_is_deferred` then `is_item_ready(...)` from `readiness.py`, sorts by `_PRIORITY_ORDER` (`:37`). This is block *membership*; every item reaching either block has already passed it.
- `_is_refined(item)` (`:73-75`) — `bool(spec) and spec not in ("null","~","None")`. A pure frontmatter check; no status logic, no filesystem I/O.
- `_workflow(item)` (`:78-84`) — the defect. Returns `"direct implementation"` for `type in ("bug","chore")` *before* consulting `_is_refined()`.
- `_render_epic_block(...)` (`:87-138`) — per child computes `marks = ["[refined]" if _is_refined(child) else "[needs /cortex-core:refine]"]` (`:95`), appends `[blocked]` (`:96-97`). Receives `by_id` (full index records built at `render():148`), **so `type` IS reachable here** without widening the epic-map envelope.
- The epic **footer** (`:103-137`) is a *third* routing voice: "Run `/cortex-core:refine` on each unrefined child" (`:130`) or "Run `/cortex-overnight:overnight`" (`:135`). `/cortex-core:build` never appears in the epic block at all.
- `render()` (`:141-183`) — Ready row at `:174-177`; `_workflow()`'s sole call site is `:176`.
- `main()` (`:270-284`) — the `flat` JSON array already carries `"refined": _is_refined(i)` (`:277`). The readiness signal already exists as structured data; only the markdown lacks it.

`cortex_command/backlog/build_epic_map.py` (`:158-163`) emits child envelopes with exactly `id`, `spec`, `status`, `title` — **no `type`** — but `by_id` supplies it at the call site, so the keyset lock is not an obstacle.

**Two predicates, neither subsuming the other.** `_is_refined()` asks "does a spec exist"; `is_item_ready()` (`readiness.py:89-175`) asks "is status+blockers clear" and never references `spec`. `is_item_ready` is consumed upstream by `_ready_set`, so re-checking it at mark time would be constant-true and carry zero information. `_is_refined()` is the only signal that still varies among visible rows.

Bracket-mark style exists **only** in `_render_epic_block` — no competing convention to reconcile.

## Web

Established precedent supports separating state from prescription, and the current design is the outlier:

- **Separation of mechanism and policy** (Brinch Hansen, RC 4000; formalized in CMU's Hydra) is the citable principle: "Hardwiring policy and mechanism together… makes policy rigid and harder to change."
- **Duplicated rules across a tool and its playbook** is a DRY violation across representations; the standard remedy is one authoritative rule source with everything else deferring or derived.
- **How real trackers render readiness on a row**: GitHub Projects statuses are `Backlog / Ready / In progress / In review / Done`; Jira separates *status* (state) from *transitions* (rules with validators/conditions); Taskwarrior uses virtual tags `READY` and `BLOCKED` as pure state predicates. Across all three, **the row-level marker is a state noun, never a verb-phrase instruction** — the `→ run command X` column is the outlier versus established tooling.
- **Agent-tooling guidance** flags "reading remote CLI output as instructions" as an anti-pattern, and argues tool output should "provide factual information without dictating what the agent should do next." No *empirical* study was found measuring agent routing accuracy with vs. without CLI-emitted advice — architectural consensus only, flagged rather than overstated.
- On removing an affordance humans use: general UX literature (no developer-tooling-specific source found) argues for pairing removal with a visible pointer to the replacement path rather than a silent drop.

Note: this angle supports the *shape* of Option A on general principle. The repo-specific evidence below outweighs it.

## Requirements & Constraints

- **`project.md:23` Deletion bias** is scoped to "keeps, safeguards, and measurement tooling." `_workflow()` is a user-facing rendering feature, so this clause does **not** license deleting it. (Clarify cited it for Option A; that citation was wrong.)
- **`project.md:25` Solution horizon** — favors collapsing a two-owner surface that already produced one contradiction bug.
- **`backlog.md:47,:94`** ("backend branching lives in the consumer skills, not in the CLI tools") governs **backend** selection — cortex-backlog vs GitHub Issues vs Jira — a *different axis* from workflow-type routing. Invoking it for Option A is analogy, not citation. `triage.py` already complies independently (`:213-230`).
- **Zero ADRs mention triage.** ADR-0016/0019 are backend-axis. No ADR supports or blocks this change.
- **`CLAUDE.md:29`**: "Prefer structural separation over prose-only enforcement… prose-only is appropriate only where occasional deviation is cheap." Option A moves logic from tested code into prose — the opposite direction.
- **The decisive precedent — #343.** `tests/test_dev_triage_refs_wired.py:1-17` docstring, verbatim: `references/triage-rendering.md` "has since been retired: the block rendering it described is mechanical (group by epic, pick a badge from `status`, **pick a recommendation sentence from `spec:` presence**), so it moved into the `cortex-backlog-triage` verb… **Prose the model re-read on every triage became code with tests.**" The test's stated job is guarding "that the logic does not silently drift back into the skill body." It also concedes the runtime missed-read failure "stays deliberately out of scope: it is untestable in a static check, so this gate is honest rather than self-sealing."
  - **`_workflow()` IS "pick a recommendation sentence from `spec:` presence."** Its type-only branch is a *deviation* from #343's own readiness-driven design, not something #343 installed. Option A would move that computation back to prose — the exact regression #343 paid down.
- **Structural budgets**: SKILL.md cap 500, `skills/dev/SKILL.md` is 41 lines — ample. L1 ratchet row `"dev": 285` bytes at **285/285, zero headroom** — binds only if frontmatter changes (this change doesn't). `skills/dev/references/size-pin.txt` pinned at 0 bytes; keep routing in SKILL.md, not a new reference doc.
- **Process**: `CLAUDE.md:28` — `skills/` edits are lifecycle-gated and mirrors rebuild from staged blobs; never hand-stage `plugins/cortex-core/skills/dev/SKILL.md`.

## Downstream Consumers & Blast Radius

Narrow and well-fenced.

- **Sole live consumer**: `skills/dev/SKILL.md:31` Step 3 (+ its byte-identical auto-rebuilt mirror). No other skill, hook, `bin/`, or `claude/` file invokes the verb or imports the module.
- **No coupling** in overnight (`cortex_command/overnight/`), pipeline, morning-review, or the dashboard. The dashboard's `ticket_feed.py:62-63,202` imports `build_epic_map`/`collect_items` directly and never touches `triage.py`; `triage_board.html` renders its own independent badges.
- **Sibling repos** (wild-light, gaggimate-barista, Team-Builder-Bot, hall-dental): **zero** code coupling. wild-light references `cortex-backlog-triage` only in `bin-invocations.jsonl` session logs. Real exposure is a human reading the rendered text, not code.
- **`triage.py` is a wheel module, NOT in the dual-source mirror set** — the pre-commit regex (`.githooks/pre-commit:530`) covers only `skills/`, `bin/cortex-*`, `hooks/cortex-*`, `claude/hooks/cortex-*`. Only a `skills/dev/SKILL.md` edit triggers a rebuild.
- **Prose to re-check**: `docs/skills-reference.md:19,:78` ("…or direct implementation") describe dev's *general* routing, not the rendered string. Two archived docs under `cortex/lifecycle/archive/docs-audit/` are dead history.

## Skill Prose & Routing Authority

**The post-pick gap is real and textual.** `SKILL.md:12` says "First match wins"; rule 1 (`:14`) sends a no-argument invocation to Step 3 before rules 4-5 are reachable. Step 3 (`:36`) ends at "print `blocks` verbatim, then ask which item to pick up", and `:40` re-enters Step 1 only "If they change the scope." Nothing routes the *normal* case — the user picks the suggested item and doesn't override. Line 40's "honor it immediately" presupposes each row carries a suggested route, but that route is manufactured entirely by `_workflow()`, never by skill prose.

Today this is masked: the renderer prints a concrete verb, so the agent never re-derives routing. Any option that weakens the rendered verb makes a "re-apply Step 1 to the chosen item" pointer load-bearing.

Minimal delta (~1-3 lines, inside existing structure, no new Step, no new MUST):

```
- **`ok`** → print `blocks` verbatim, then ask which item to pick up. Once picked,
  route it from Step 1 (first match wins) — the item's `type` and readiness are what
  rules 3-5 need.
```

Re-entering Step 1 rather than jumping to rule 5 is what keeps rule 4's trivial-change cheap path reachable. Rule 5 itself needs no edit — it is already readiness-only and type-blind, which is the behavior the renderer violates.

**Ticket correction**: #425 cites "`SKILL.md:17` (Step 4)". There is no Step 4 — it is **Step 1, rule 4**.

No other skill prose asserts what the board renders (`skills/overnight/references/new-session-flow.md`'s "triage" hit is an unrelated suitability-triage concept).

## Test Strategy

- **Baseline is green**: `uv run pytest tests/test_dev_triage_refs_wired.py tests/test_build_epic_map.py -q` → **24 passed in 0.67s**.
- **`test_verb_renders_the_blocks:99-105`** concatenates `inspect.getsource` of `render` + `_render_epic_block` + `_workflow` and asserts four tokens. Binding `triage_mod._workflow` **by name** at `:101` means:
  - Deleting `_workflow` entirely → **AttributeError** before any assertion runs.
  - Deleting only its bug/chore branch → **passes cleanly, zero assertions break** (`/cortex-core:refine` survives in the remaining return and at `:130`; `/cortex-overnight:overnight` at `:135`).
- **`_MOVED_TOKENS` (`:30-46`) would not collide.** Those tokens guard retired reference-doc strings, and Step 3 is already fully delegated. Risk only if someone re-explains block layout in prose and reuses `"Block 1: Epic sections"`, `"Block 2: Flat ready list"`, or `"Per-epic workflow recommendation"` verbatim.
- **`tests/test_build_epic_map.py:124`** (`sorted(child.keys()) == ["id","spec","status","title"]`) is untouched — no new field is needed.
- **Zero behavioral coverage exists.** Nothing calls `render`, `_ready_set`, or `_workflow` with data anywhere.
  - *Layer A*: direct unit tests of `render()` with a local `_item(**kwargs)` factory (convention: `tests/test_backlog_readiness.py:29`, `tests/test_generate_backlog_index.py:26` — no shared `conftest.py` builder). Assert exact strings, pinning mark syntax.
  - *Layer B*: one subprocess snapshot of `main()` following `tests/test_backlog_ready_render.py:155-204`, diffing `blocks` against a pinned `tests/fixtures/triage_render.json`.
  - **The trap**: a test that recomputes the expected mark by calling the same predicate the renderer uses proves nothing — a bug in the shared predicate breaks both identically and the test still passes.
  - **The dodge**: call `render()` twice with the *same item dict* and two different `epic_map` args (once as a ready epic's child, once with `epic_map={}` so it falls into `## Ready` via `:167-169`), extract each mark by regex keyed on the id, and assert the two are byte-identical — comparing the paths against each other's real output, not a shared formula.
- **Shipped-bug regression gate**: convention is a fixture engineered to hit the prior-broken path with an inline ticket reference (`tests/test_backlog_ready_render.py:16-20,190-191`). Defect 3 qualifies.

## Tradeoffs & Alternatives

Options: **A** (delete the verb, marks only, routing to prose) — Clarify's entering pick; **B** (delete the type-only branch, readiness wins for every type, both blocks share one predicate, ~−2 lines); **C** (reorder `_is_refined()` ahead of the bug/chore branch — defect 3 only).

- **C** fails Solution horizon: it reopens as a near-identical bug the moment someone notices the unrefined case, and leaves defect 2 untouched.
- **A** closes all three defects by construction but is the largest diff and the only one forcing a test *rewrite* rather than an addition. Its benefit is largely notional for the agent path — Step 1 rule 5 already re-derives the route, which is *why* the contradiction went unnoticed. Its cost is real: the #343 conflict, the forced `test_verb_renders_the_blocks` rewrite, footer disposition, and the fact that the epic block's own mark `[needs /cortex-core:refine]` already embeds a command, so A must strip that too rather than inheriting existing vocabulary.
- **B** closes all three defects with the smallest durable diff, no test rewrite, and no conflict with #343 or `CLAUDE.md:29`.

**Resolved design questions** (apply to whichever option ships):

- **(a) Mark vocabulary** — command-free (`[refined]` / `[needs refine]`). Note the current epic mark embeds a command; command-free is an edit, not an inheritance.
- **(b) Epic footer** — bundles a command pointer with **sequencing policy** ("one at a time, each needs interactive spec approval before the next") that exists nowhere else and cannot simply be deleted. Under B the footer is unchanged; under A it would need the sequencing sentence preserved.
- **(c) `idea`** — keeps its own branch/mark, per the ticket's Edges. Do not fold into "needs refine": a discovery topic and an unspec'd feature are different next actions, and conflating them reintroduces defect 1 one level up.
- **(d) Predicate** — `_is_refined()`, not `is_item_ready()` (already consumed upstream by `_ready_set`, hence constant-true at mark time).

## Adversarial Review

**Attack on B.** Under bare B an unrefined `bug`/`chore` falls to `:84` and renders **`/cortex-core:refine`**. That satisfies defect 1's letter — but produces precisely what the ticket's Edges forbid: *"Do not simply delete the bug/chore branch… forcing a one-line typo fix through interactive refine (two unconditional human pauses) is friction that would make triage worse, not better."* **Bare B is not safe to ship**; it needs a compensating cheap-path signal.

**Prose delta — adjudicated: yes, required.** The skill-prose angle is right; the requirements and test-strategy angles are wrong on this point. Step 3 stops at "ask which item to pick up" and never routes the picked item back through Step 1. This is invisible today only because `_workflow()` prints a concrete verb. Under A, or under B-without-the-cheap-path, the masking disappears and a ~1-2 line pointer becomes load-bearing. C alone wouldn't need it.

**Failure modes nobody raised:**

- **Latent bug (pre-existing, orthogonal)**: `build_epic_map.py:136-144` adds *every* `type: epic` item to the map regardless of its own status. `render()` builds `child_ids` from **all** epics (`:152-154`) but renders blocks only for `ready_epic_ids` (`:161-165`). So a ready child of a non-ready parent epic is excluded from `flat` **and** has no epic block to appear in — **it vanishes from triage output entirely.**
- **`_is_refined()` trusts frontmatter only** — no on-disk check that the `spec:` target still exists. Every option extends its authority to `bug`/`chore` for the first time, so a stale `spec:` pointer will newly render `/cortex-core:build` for a spec that is gone.
- **Cross-block comparison is subtler than the ticket's criterion assumes**: the epic block renders all children regardless of status (no held-status gate on the mark), while Ready contains only `_ready_set()` survivors. A comparison test must restrict to the ready subset or it compares against items that structurally cannot appear in the flat block.
- **Non-issues, confirmed**: `type: epic` is filtered from Ready at `:169`; unknown types (`task`, `fix`, `spike`, `enhancement`, `needs-discovery`) already fall through to the readiness-only arm and are already rule-5-consistent.

**Verdict — none of A/B/C ships as literally described.** A fails two of #425's own acceptance criteria (criterion 1 wants a literal `/cortex-core:build` in the Ready block, which A removes; criterion 3 wants `idea → discovery` unchanged, but `_workflow()` is the only place that string is emitted). Bare B violates the cheap-path Edge. C fails the cross-block-consistency criterion.

**Ship corrected-B**: one shared predicate used by both `render()`'s flat loop and `_render_epic_block` (closes defect 2 structurally); refined items of **any** type render `/cortex-core:build` (closes defect 3, satisfies criterion 1 literally); unrefined `bug`/`chore` render an explicit pointer to rule 4's trivial-change path rather than silent "direct implementation" or forced "refine" (honors the Edge); plus the one-line Step 3 → Step 1 delegation.

## Open Questions

1. **Which option ships — A (Clarify's entering direction) or corrected-B?** *Resolved by research, pending user confirmation.* Five angles converge on corrected-B. The Option A rationale recorded at Clarify rested on two citations that research falsified: Deletion bias is scoped to safeguards, not user-facing features, and `backlog.md`'s skill-layer-routing rule governs the backend axis. Against that, #343 is a direct in-repo precedent moving this exact computation *out* of prose. **Carried to Spec as the first item to confirm with the user**, since the entering direction was a user decision.
2. **Exact render for an unrefined `bug`/`chore`.** *Open — for Spec.* Must be neither silent "direct implementation" (defect 1) nor forced "refine" (violates the Edge). Needs concrete wording that points at rule 4's judgment-based trivial-change path while leaving the judgment to the agent reading the ticket.
3. **Cheap-path delegation wording in `skills/dev/SKILL.md`.** *Open — for Spec.* Acceptance criterion 4 requires the delegation be "stated in the skill." Must avoid the three `_MOVED_TOKENS` strings and stay within What/Why-not-How.
4. **`_is_refined()` stale-pointer exposure.** *Deferred with rationale.* Adding an on-disk existence check widens scope beyond #425 and would newly couple a pure frontmatter predicate to the filesystem in a function called per-row. The exposure is pre-existing for non-bug/chore types; this change extends it rather than creating it. File separately if it bites.
5. **Child of a non-ready epic vanishes from output.** *Deferred with rationale.* Pre-existing and orthogonal to #425 — it is a membership bug in `render()`'s `child_ids`/`ready_epic_ids` split, not a routing bug. Should be pinned by a test in this change (so any accidental interaction is visible) but fixed under its own ticket.
6. **#425's acceptance criteria need amending to match what ships.** *Open — for Spec.* As written they encode the ticket's own assumed fix; criteria 1-4 must be restated against corrected-B, and the "Step 4" reference corrected to "Step 1, rule 4."
7. **Does this decision warrant an ADR?** *Open — for Spec.* Zero ADRs govern triage, but the skill-vs-CLI logic-boundary question is the same *shape* the repo has ADR'd twice for the backend axis (0016, 0019). #343 settled it once without an ADR and it drifted back; an ADR would make the next drift visible.
