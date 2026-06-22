# Research: refine-default-interactive-not-overnight

## Clarified Intent (scope anchor)

Stop `/cortex-core:refine` from assuming overnight execution. The Specify interview
should always assume the work runs **interactively** (user present to verify), and
refine should surface an **advisory warning at refinement-complete** only when the
ticket is a poor overnight candidate. The warning is informational to the human at
refine time — it does not gate or change what the overnight runner selects.

## Where the overnight assumption lives today (codebase findings)

All paths are canonical sources under `skills/`; mirrors under
`plugins/cortex-core/skills/` regenerate via `just build-plugin`.

1. **`skills/lifecycle/references/specify.md:96`** — Open Decision Resolution step 2:
   "Ask the user directly — the user is present during spec; *implementation may run
   overnight without them*." This is the line that frames the interview around
   autonomous (overnight) verifiability and motivates "how do we test this overnight?"
   interrogation. `specify.md` is shared by **every** lifecycle Specify run (refine
   standalone *and* `/cortex-core:lifecycle`), so this is the cross-cutting site.

2. **`skills/lifecycle/references/specify.md:126`** — acceptance-criteria format
   `(a) command + expected output` / `(b) observable state` / `(c) "Interactive/
   session-dependent: [rationale]"`. The format itself is fine (testable criteria are
   good practice regardless of execution mode). The defect is *posture*: option (c) is
   currently treated as a fallback "if a command check is not possible," which invites
   the interview to push back / interrogate rather than accept interactive verification
   as a first-class, legitimate outcome.

3. **`skills/refine/SKILL.md`** framing assumes overnight throughout:
   - L3 `description` — "Prepare a backlog item for overnight execution by running it
     through Clarify → Research → Spec." (also the L1 routing surface)
   - L4 `when_to_use` — "preparing a backlog item for overnight execution"
   - L9 `outputs` — "approved specification ready for overnight planning"
   - L19 purpose — "Prepares a single backlog item for overnight execution… the
     overnight runner can plan and execute it without further human input."
   - L180–188 Step 6 Completion — ends with "Ready for overnight execution." (this is
     the refinement-complete surface where the new warning belongs)
   - L194 constraint table — "overnight auto-generates plans" (informational; keep)

4. **`skills/refine/SKILL.md:53`** — "overnight requires both" (research+spec) is a
   state-consistency warning, not an execution-mode assumption. Leave as-is.

5. **`skills/lifecycle/references/clarify.md:72`** — references the overnight runner only
   as an example of shared infrastructure for criticality assessment. Unrelated. Keep.

## What "good/poor overnight candidate" means (new notion)

`cortex_command/overnight/batch_plan.py` selects work on `status: refined` alone — there
is **no existing overnight-suitability definition** in the codebase to reuse. This
feature introduces the notion as a refine-time heuristic. Decided posture (hybrid):

- **Mechanical anchor** (always cited when present): any acceptance criterion marked
  `Interactive/session-dependent`, and any unresolved item in `## Open Decisions`.
- **Judgment reasons** (cited when refine assesses them): needs network/credentials the
  sandbox can't reach, requires human-visual or human-judgment verification, or scope is
  exploratory/under-specified.
- The warning **lists the specific reasons**. When none apply, no warning is emitted.

## Reframe scope (decided: full, but terse)

Purpose/framing reframes from "prepare for overnight execution" to "prepare a backlog
item for **execution**" (execution-agnostic, no "interactive or overnight" verbosity).
**Constraint:** the routing keywords stay for discoverability — refine remains the
overnight-prep entry point.

## Constraints & couplings (must be honored)

- **L1 surface ratchet** (`tests/test_l1_surface_ratchet.py`): `refine`'s budget is
  **644 bytes** (description + when_to_use); refine is in `ROUTING_PRESSURE_CLUSTER`
  (exempt from the ≤400 default). Measured via `bin/cortex-measure-l1-surface`. Per the
  re-cap rule (`cortex/requirements/project.md`, "SKILL.md L1 surface ratchet"), if the
  reframe *reduces* the surface, ratchet the budget **down** to the new measured value;
  never raise it.
- **Trigger fixture** (`tests/fixtures/skill_trigger_phrases.yaml`): refine's surface
  must keep substrings `"refine backlog item"`, `"prepare for overnight"`,
  `"prepare feature for execution"`, `"Clarify → Research → Spec"`. The reframe must
  preserve all four (overnight stays as a discoverability keyword).
- **Mirror parity** (`tests/test_plugin_mirror_parity.py`): run `just build-plugin` and
  commit canonical + `plugins/cortex-core/skills/refine/SKILL.md` together (drift-hook
  coupling on `main`).
- **MUST-escalation policy** (CLAUDE.md): the new completion-warning instruction uses
  soft positive-routing phrasing — no MUST/CRITICAL/REQUIRED.
- **Prescribe What/Why, not How**: describe the warning's trigger and shape; let the
  model judge the judgment-reason dimensions.

## Known limitation (carry to Non-Requirements)

The warning is advisory to the **human at refine time**. The overnight runner still
selects any `status: refined` item regardless of the warning — this feature does **not**
add a runner-side gate that skips poor candidates. A poor candidate run overnight may
still fail to self-verify; that is accepted and out of scope.

## Open Questions

None. The two design decisions (warning heuristic = hybrid; reframe scope = full-but-terse)
were resolved with the user during Clarify. Remaining choices are authoring details
resolvable at spec time.
