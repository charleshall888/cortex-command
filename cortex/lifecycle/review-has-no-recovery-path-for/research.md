# Research: Give the interactive review phase a verb-level gate that refuses to advance past a missing review.md, and sanction resuming the idle reviewer in review.md §2's single-writer rule

> **Dispatch note.** Three of four dispatched research agents (Codebase, Requirements & Constraints,
> and the earlier clarify-critic) returned idle notifications with no artifact across explicit chases —
> the *same failure mode this ticket exists to fix*, reproduced four times on 2026-08-07. The Codebase
> and Requirements & Constraints angles below were therefore executed directly by the orchestrator, not
> synthesized from agent returns. Every claim is anchored to `file:line` and was read, not inferred,
> except where explicitly marked.

## Codebase

### The detection gap is in the verbs, not only the prose

Two verbs run in the interactive review chain and neither observes the artifact:

- `cortex_command/lifecycle/register_artifact.py:96-130` — resolves `index.md`, regex-rewrites the
  `artifacts:` inline array, bumps `updated:`, returns `registered`. It never stats the artifact file
  it is registering.
- `cortex_command/lifecycle/advance.py:427-435` — the `review-verdict` arm validates only that
  `--verdict ∈ _VERDICTS` and `--drift ∈ _DRIFT_VALUES`. It never stats the artifact either.

Consequence: an interactive review can reach `complete` with an orchestrator-supplied verdict, an
`artifacts:` array asserting a review exists, and no `review.md` on disk.

`skills/build/references/review.md:33` is nominally reachable for this case — an absent file does "lack
`## Requirements Drift`" — but its remediation instruction is *"read the existing file and append it"*,
incoherent for a file never written. Nothing routes the orchestrator there, because nothing detects the
state.

### Secondary consequence: cycle mis-routing

`cortex_command/lifecycle/review_brief.py:35-37` documents that `review.md` "must exist continuously —
`common.py`'s phase detection falls through to the plan-based step when it is missing and reports
`review` instead of `implement-rework`." So the failure can also mis-route the following cycle, not just
go unnoticed.

### Blast radius: `register_artifact` has no Python consumers

`register_artifact` has **zero non-test Python callers**. (`finalize.py` and `enter.py` mention the
string in docstrings; they do not call it.) Its actual consumers are five skill-prose call sites:

| Call site | Artifact |
|---|---|
| `skills/build/references/review.md:35` | `review` |
| `skills/build/references/plan.md:76` | `plan` |
| `skills/build/references/backlog-writeback.md:19` | (generic recipe) |
| `skills/refine/SKILL.md:76` | `spec` |
| `skills/refine/references/research-phase.md:23` | `research` |

**None of them branch on the returned state.** They are bare one-liners ("Register it: `…`"). This is
the single most important finding for design: adding a new state to this verb breaks nothing *and
accomplishes nothing* — a gate whose signal no consumer reads is not a gate. Any verb-side change here
requires a paired prose change to be load-bearing.

There is also a `bin/cortex-lifecycle-register-artifact` dual-channel wrapper, and tests at
`cortex_command/lifecycle/tests/test_register_artifact.py` that exercise states directly.

### The exit-code route conflicts with a documented contract

`register_artifact.main()` unconditionally `return 0` (`:190`), and the module docstring states this is
deliberate: the CLI "always emits JSON and exits 0", "matching the sibling verbs", behind a
never-crash net. Making it exit non-zero would break a contract shared across the verb family, not just
this verb.

### Option B (refuse inside `advance review-verdict`) — reject, on corrected grounds

> **Correction (post-approval, verified).** An earlier revision of this file argued that a refusal here
> "leaks into the overnight path and threatens ADR-0015's preserve-and-flag arm." **That was wrong**, and
> a late-returning research agent caught it. The overnight pipeline *does* import and call `advance`
> (`review_dispatch.py:36`), but `_advance_review_complete` is reached only at `:414` and `:703`, both
> guarded by `verdict_str == "APPROVED"`. `parse_verdict` runs first, and a missing `review.md` returns
> the `_ERROR_RESULT` sentinel, which can never equal `APPROVED`. An existence gate would therefore never
> fire on the overnight path. `_advance_or_warn` (`:52-86`) additionally treats `refused` as best-effort.

The two reasons that survive verification:

1. **The generic `refused` remedy is wrong for this refusal.** `advance.py:184` carries a `refused`
   state whose `refusal:` discriminant has exactly one value today, `gate-mismatch` (`:1082`).
   `skills/build/SKILL.md:61` prescribes the remedy for it — "re-run `cortex-lifecycle-next` and
   re-invoke threading `advance_contract.expected_from_state`" — which does nothing to make `review.md`
   appear. Siting here needs prose disambiguation regardless, erasing the "no prose change" advantage.
2. **It intercepts later than necessary.** In the real skill sequence `register-artifact` runs first
   (`review.md:35`) and `advance` second (`review.md:48`), so Option B can only ever catch what Option C
   already caught.

The `advance.py:1054-1069` no-machine-rows deadlock ("no row → fallback → refuse → still no row",
session `overnight-2026-07-29-0145`) is **not** reintroduced by either option: that loop was
self-perpetuating because the gate consulted `resolve_lifecycle_phase`, which degrades to the
artifact-presence legacy fallback. A bare filesystem stat consults neither, and stops refusing the
moment the file is written.

### An in-repo convention for this check already exists

`skills/refine/references/research-phase.md:23` already performs precisely this check, in prose, for the
sibling artifact: *"verify `research.md` exists and is non-empty (else surface and halt), then register
it."* `review.md:35` registers without any such verification. So the repo already has a settled idiom;
the review phase simply omits it.

### Options weighed

| Option | Protocol cost | Load-bearing? | Verdict |
|---|---|---|---|
| **A** — new `artifact-missing` state on `register_artifact` | Floor bump (see Requirements) | No — no prose reads states | Reject: pays the highest cost for no effect |
| **B** — refusal in `advance review-verdict` | None (reuses existing `refused` state) | Yes, unbypassable | **Reject** — but see the correction below; the original reason was wrong |
| **C** — `register_artifact` **refuses to register** an absent-or-empty artifact, returning the existing `error` state with a diagnostic `message` | None | **Yes** — enforcement is the withheld write, not a read return value | **Recommended** (as revised by Adversarial finding 1) |
| **D** — prose-only check in `review.md` §3, matching `research-phase.md:23` | None | Weakest — prose-only enforcement, and the failure class *is* the orchestrator not noticing | Fallback only |

**Recommendation: Option C, in its revised form.** The enforcement is the *withheld write to `index.md`*,
not a state the prose must read — which is what makes it load-bearing at all five call sites rather than
just at `review.md:35` (Adversarial finding 1). Today the verb records a false claim that a review exists;
refusing removes the falsehood, and every downstream reader of `index.md` benefits without any prose
change. It costs no protocol floor bump (no new state value), stays entirely out of the overnight path
(`register_artifact` has no pipeline caller), and generalizes to research/spec/plan for free. Match
`research-phase.md:23`'s stronger *"exists and is non-empty"* idiom rather than a bare stat (Adversarial
finding 2). A paired `review.md` §3 prose edit remains desirable so the orchestrator has a defined
response, and may be byte-neutral (Adversarial finding 3) — but the gate no longer depends on it.

## Requirements & Constraints

### Protocol versioning — the constraint that eliminates Option A

`cortex_command/lifecycle/protocol.py:52` sets `PROTOCOL_VERSION = 3`; the plugin-side compat range in
`skills/build/references/protocol-expectation.txt` is `min=3`, `max=3`. The module docstring states the
rule: bump "when a payload change is **not backward-compatible for the prose**", append-only, moving the
plugin expectation range in the same commit, and "a bump that would strand out-of-repo consumers is a
*protocol-floor* decision made deliberately by the operator."

The version history establishes the decisive precedent: *"2: spec-approve may return state
`approved-direct` … prose predating the fork has no route for that state."* **A new returned state value
is a floor bump.** `register_artifact` stamps `protocol` into its payload (`:188`), so it is
protocol-governed like the served verbs — Option A is not exempt.

Reusing the **existing** `error` state with a new trigger condition adds no state value the prose lacks a
route for, so on the stated rule it is backward-compatible and needs no bump. (See Open Questions — this
is the one inference in the recommendation rather than a quoted rule.)

ADR-0035 (`cortex/adr/0035-*.md`, accepted) confirms the direction: introducing a verb "changes no served
payload — it moves where existing prose lives, not what a reviewer is ultimately told", and therefore did
not bump the floor. Shape changes to served payloads do.

### Reference-size ratchet — zero headroom, and a mirror pin

`skills/build/references/size-pin.txt` pins **57175** bytes; the directory measures **exactly 57175**
(verified: sum of all regular files excluding `size-pin.txt`). There is no headroom. Any added prose must
be offset by a trim in the same directory or carried by a documented `# raised:` exception line.

The established format, from the two precedents in that file:

```
# raised: <what changed> because <why it was unrepresentable/wrong>, lifecycle-id=<id>, date=<YYYY-MM-DD>
```

A byte-identical mirror pin exists at `plugins/cortex-core/skills/build/references/size-pin.txt` (same
57175 and the same two `# raised:` lines) and must be kept in sync.

### Governing policy

- **`CLAUDE.md`**: "Prefer structural separation over prose-only enforcement for sequential gates;
  prose-only is appropriate only where occasional deviation is cheap." Deviation here is *not* cheap —
  it silently advances a lifecycle to `complete` with no review — which argues against pure Option D and
  for C's verb half.
- **`cortex/requirements/project.md`, "Enforcement gates carry named evidence"**: a new gate survives
  only by naming the specific evidenced failure it prevents. This gate's named evidence: the consumer
  lifecycle of 2026-08-05, plus four same-day agent-idle-without-artifact recurrences on 2026-08-07
  (three of them during this ticket's own refine).
- **`cortex/requirements/project.md`, "Deletion bias"**: burden of proof sits on adding. Option C adds
  one stat call and one prose clause — the smallest addition among the load-bearing options.
- **`cortex/requirements/pipeline.md` § Post-Merge Review** and **ADR-0015**: untouched by Option C,
  since `register_artifact` has no pipeline caller. This is the constraint that eliminated Option B.
- **Area doc**: `cortex/requirements/lifecycle.md` does not exist (in-flight #469), so this feature
  reviewed against `project.md` only — the exact hazard `review.md:9` warns about.

### The §2 single-writer rule, verbatim

`skills/build/references/review.md:23`:

> **Single-writer rule** — only the reviewer role writes `review.md`: this sub-task plus §3's
> missing-drift re-dispatch and §3a's cap-2 re-dispatches. Any sub-agent the reviewer spawns is
> read-only and returns findings as a message envelope.

The amendment must add resumption of the original reviewer as a fourth permitted writer. Note the rule is
role-scoped ("only the reviewer role"), so a resumed reviewer is arguably already inside the role and the
closed list is what excludes it — the amendment is therefore a list edit, not a principle change.

## Adversarial

> **Dispatched agent returned nothing; this pass was executed by the orchestrator against its own
> recommendation.** Self-critique is weaker than an independent reviewer — and §3b's critical-review gate
> will *not* compensate, because it requires `tier = complex` and this feature is `moderate`. Treat the
> findings below as the only adversarial coverage this spec receives.

**1. Option C's verb half is theatre at four of its five call sites.** If enforcement lives in
`review.md` §3's prose branching on a returned state, then the verb's signal is read by exactly one
consumer, and `plan.md:76` / `SKILL.md:76` / `research-phase.md:23` / `backlog-writeback.md:19` receive
an error nobody reads. The original framing of Option C does not survive this.

*Resolution — it changes the design.* The gate's teeth should not be a returned state at all, but a
**refusal to register**. Today `register_artifact` writes `review` into `index.md`'s `artifacts:` array
when no review exists — it records a false claim about the lifecycle's own history. Refusing the write
is a durable, observable correction that does not depend on any prose reading a return value, and it
protects every downstream reader of `index.md` (phase detection, dashboards, morning review) uniformly
across all five call sites. The returned `error` state then carries the diagnostic rather than carrying
the enforcement.

**2. Stat-only detection has a slow-writer race.** A reviewer mid-write leaves a file that exists but is
truncated; `os.path.exists` passes and the verdict block may be absent. `research-phase.md:23`'s
established idiom is stronger — *"exists and is non-empty"* — and should be matched rather than
weakened. This does not close the race (a partial write is non-empty), but it strictly dominates a bare
existence check at no extra cost.

**3. The ratchet cost may be zero, which undercuts Open Question 3.** `review.md:33` currently reads
*"If review.md lacks `## Requirements Drift` (the reviewer ran out of context), re-dispatch once …
Still absent → escalate."* That sentence is already the missing-artifact arm's natural home; rewriting
it to cover an absent *file* as well as an absent *section* is plausibly **byte-neutral or negative**,
requiring no `# raised:` exception and no offsetting trim. The spec should attempt the byte-neutral
rewrite first and fall back to an exception only if it cannot be met.

**4. Assumption that will not hold: "the orchestrator notices."** The entire failure class is an
orchestrator *not* noticing. Any design whose final safeguard is orchestrator attention re-creates the
bug. This is the strongest argument for finding 1's refusal-to-register: it is the only proposed
mechanism that changes state without requiring anyone to read anything.

**5. Residual, unmitigated.** A reviewer that writes a syntactically complete but substantively empty
`review.md` defeats every option here. Detection of *bad* reviews is out of scope and stays out — but
the spec should say so, because "review.md exists and is non-empty" reads like a stronger guarantee than
it is.

### Findings from the late-returning adversarial agent

The dispatched agent returned after approval. Three findings, dispositioned:

**6. Worktrees make the root-resolution risk live — ACCEPTED, spec strengthened.** The agent's stated
mechanism is wrong (it named the documented `enter`-vs-`register-artifact` divergence, but `enter` is not
the writer and does not sit on this path). Its underlying risk is right and was understated here: the
interactive branch-mode flow runs in worktrees under `.claude/worktrees/`, and two were checked out at
the time of writing. If the reviewer subagent writes into a different tree than the orchestrator's cwd
resolves to, the gate false-refuses on a file that exists. Promoted from "a precondition" to an
implementer obligation in the spec's Edge Cases.

**7. "Just copy `research-phase.md:23`'s prose pattern, zero code changes" — REJECTED, with reason.**
The agent argues a prose-only pre-check is cheaper on every axis. It is cheaper, but it does not do the
same job: it leaves `index.md` recording `artifacts: [review]` for a review that does not exist. The
verb refusal fixes that data corruption independently of whether any prose is read, and the failure class
under study is precisely an orchestrator not reading carefully (Adversarial finding 4). The agent does
not address the false-index.md-claim argument.

**8. Resume race — ACCEPTED, added to spec Edge Cases.** A resumed reviewer may be several turns from
flushing `review.md`; an orchestrator that re-checks immediately re-triggers the halt and can loop. The
spec now states that the response to a refusal is resume-then-await-the-agent's-return, never
resume-then-immediately-recheck.

## Open Questions

1. **Does reusing the existing `error` state with a new trigger condition require a `PROTOCOL_VERSION`
   bump?** — *Resolved by reading, with one inference.* `protocol.py`'s stated rule keys on the prose
   having "no route for that state"; `error` is already in `KNOWN_STATES:61` and predates the change, so
   no route is missing. The inference is that a *trigger* change to an existing state is not a "payload
   change not backward-compatible for the prose". Spec should confirm against
   `tests/test_protocol_parity.py` before relying on it; if it turns out to require a bump, Option D
   becomes the recommendation, since a floor bump is disproportionate to this fix.

2. **Should the gate fire for all four artifacts or only `review`?** — *Resolved: all four.* The check
   lives in the verb, which is artifact-generic, and `research-phase.md:23` shows the refine side already
   wants it. Restricting to `review` would require artifact-conditional logic for no benefit. Note this
   means `plan.md:76` and `SKILL.md:76` inherit a new failure mode they did not have; the spec must state
   that as intended, not incidental.

3. **Where do the ratchet bytes come from for the §3 clause?** — *Deferred to Spec, with rationale, and
   de-risked.* Now that enforcement is the withheld `index.md` write rather than a prose branch
   (Adversarial finding 1), the prose edit is desirable but **not load-bearing** — if no bytes can be
   found, the gate still works. Three admissible routes, in preference order: (i) rewrite `review.md:33`'s
   existing missing-drift sentence to cover an absent *file* as well as an absent *section*, plausibly
   byte-neutral (Adversarial finding 3); (ii) an offsetting trim elsewhere in
   `skills/build/references/`; (iii) a `# raised:` exception with lifecycle-id. Choosing requires the
   clause's final byte count, which the spec produces and research cannot — so this defers a measurement,
   not a design decision. Remember the byte-identical mirror pin at
   `plugins/cortex-core/skills/build/references/size-pin.txt`.

4. **Adversarial angle had no independent reviewer.** — *Resolved by orchestrator self-critique; residual
   risk accepted and named.* The dispatched agent returned nothing (the failure mode under study), so the
   `## Adversarial` pass above was run by the orchestrator against its own recommendation. **Correction to
   an earlier draft of this file:** §3b's critical-review gate does *not* backstop this — it fires only at
   `tier = complex`, and this feature is `moderate`, so the gate will skip. There is therefore no
   independent adversarial review of this design at any point before approval. That self-critique
   materially changed the recommendation (see Adversarial finding 1), which is evidence the gap was real
   rather than formal.

5. **Root-resolution mismatch (the highest-risk false-refusal source)** — *Resolved directly.*
   `register_artifact` resolves its root with `_resolve_user_project_root_from_cwd`
   (`register_artifact.py:100`), and `review_brief.py:607` uses the **same** resolver, building the
   reviewer's absolute `review_path` from it at `:618`. Writer path and stat path therefore agree by
   construction, and the docstring's documented `enter`-vs-`register-artifact` divergence
   (`CORTEX_REPO_ROOT`-honoring vs cwd) does not sit between these two verbs. Residual risk is narrow and
   statable: only a cwd change *between* the brief call and the register call — e.g. the orchestrator
   entering a worktree mid-phase — could split them. The spec should note this as a precondition rather
   than guard it.
