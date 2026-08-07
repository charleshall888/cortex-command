# Research: Make concurrent agents unable to allocate colliding ADR numbers

**Clarified intent:** Make concurrent agents unable to allocate colliding ADR numbers, by
fixing how ADR identity is claimed — because the overnight path has no human checkpoint,
which is the one place the ADR README's prose-only enforcement rationale does not hold.

**Headline finding — the ticket's premise is wrong.** The collision is not a worktree race.
Both numbers were chosen at **plan time, in the home repo, by concurrent plan-gen sub-agents
globbing the same `cortex/adr/` directory**. The worktrees are where the collision becomes
*unrecoverable* (git cannot see it at merge), not where it is *decided*. This inverts the
option set: `O_EXCL` — the already-ratified #027 remedy the ticket dismissed as inapplicable —
applies directly, in one shared directory, in one process tree.

---

## Codebase

### No code allocates or writes ADR numbers

The entire shipped surface for ADR authorship is two lines of template prose:

- `skills/refine/references/specify.md:13` — draft any hard-to-reverse decision into `## Proposed ADR`.
- `skills/refine/references/specify.md:75-78` — `<!-- Replace with '### Proposed ADR: <NNNN-slug>' -->`.
- `skills/refine/references/specify.md:98` — the approval surface lists proposed ADRs as `<NNNN-slug>`.

**Neither says how `NNNN` is derived.** No `cortex_command` module writes to `cortex/adr/`;
the only ADR-aware module, `cortex_command/adr_citation_audit.py`, is read-only
(`load_corpus` at `:91-120` uses `adr_dir.iterdir()`). `skills/build/` contains zero ADR
mentions. The ADR file's creation is unscripted, emergent agent behavior. **There is no
allocation code path to make atomic — there is no allocation code at all.**

Mirror `plugins/cortex-core/skills/refine/references/specify.md` is byte-identical.

### Where the number is actually claimed (three times, rotting between each)

Verified against the incident artifacts in wild-light:

| Phase | Where it runs | Evidence |
|---|---|---|
| Spec proposes `NNNN` | Home repo, interactive refine | `a-generator-version-bump-has-an/spec.md:113-115` proposed 0077, self-marked "Number provisional" |
| **Plan re-derives it** | **Home repo, concurrent sub-agents** | `.../plan.md:42` "Next free ADR number is **0080**… The spec's provisional 0077 is stale" |
| Implement writes the file | Isolated worktree | Committed 02:15 and 02:34 |

`no-gate-anywhere-runs-pytest-so/plan.md:134` records the rot explicitly: *"The number has
rotted twice already. The spec proposes 0078; at plan time `ls cortex/adr/` shows 0078 and
0079 both already landed from concurrent sessions. The lowest free number at plan time is 0080."*

**Plan generation runs in the home repo, concurrently.** Verified directly:
`cortex_command/overnight/prompts/orchestrator-round.md:483` — *"Do NOT commit the generated
`plan.md` files yourself. The runner commits them into each feature's integration worktree
after this round returns; committing them here would land them on the home repo's `main`."*
Step 3c (`:474`) confirms parallel dispatch: *"After all sub-agents complete."*

So both plan-gen agents `ls cortex/adr/` in **the same directory, on the same filesystem, in
the same process tree, at the same time.** This is the classic TOCTOU scan-then-write race —
identical in shape and in scope to #027.

### Overnight never runs refine

`cortex_command/overnight/backlog.py:46` — `ELIGIBLE_STATUSES = ("backlog", "ready",
"in_progress", "implementing", "refined")`; `cortex_command/pipeline/prompts/` holds only
`implement.md` and `review.md`. There is no refine/specify prompt. Spec authoring happens
before overnight ever creates a worktree.

### The existing duplicate detector

`cortex_command/adr_citation_audit.py`, stdlib-only, `:6` *"Report-only: exits 0 on every path."*

- `_CORPUS_FILENAME_RE` (`:73`) — `^([0-9]{4})-([a-z0-9-]+)\.md$`; corpus index keyed `int`.
- `detect_duplicates(index)` (`:128-142`) — emits a `duplicate_number` finding for any number
  with >1 corpus file. **This is exactly the detector that would have caught the two 0080 files.**
- `detect_gaps(index)` (`:143-161`) — emits a finding per missing number in `1..max(filed)`.
- `_SCAN_EXTENSIONS` (`:76`) — **`.md` and `.py` only.**
- `_EXCLUDED_DIR_PARTS` (`:79-83`) — `.git`, the test fixture dir, `plugins/cortex-core`.
- `main()` (`:334-340`) always returns 0.

**Arming status: manual only.** Wired at `justfile:471-472` and `pyproject.toml:69`
(console script). No hit in `.githooks/`, none in `.github/workflows/`, none in the pipeline.

### The #027 precedent — applicable after all

`cortex_command/overnight/deferral.py:178-243`, `write_deferral()`: an `O_CREAT | O_EXCL |
O_WRONLY` loop that atomically claims the destination filename, incrementing on
`FileExistsError`. Docstring (`:189-192`): *"This eliminates the TOCTOU race inherent in a
scan-then-write pattern."* `next_question_id()` is only a starting hint; atomicity comes from
the OS-level open.

The ticket claims this "cannot reach across worktrees." True but **irrelevant** — the ADR
number is not claimed across worktrees. It is claimed in one shared home-repo directory,
which is precisely the scope `O_EXCL` covers.

### Backlog IDs

`cortex_command/backlog/create_item.py:83-98` `_get_next_id()` — plain glob+max, no lock.
`:181-193` writes a `uuid:` frontmatter field. Not invoked from `pipeline/` or `overnight/`.

Separately, `cortex_command/overnight/report.py:969-987` `_next_backlog_id()` runs **serially
in the runner process, post-merge** — this is why backlog numbers do not collide in practice.

### Constraints any change must satisfy

- **`superseded_by: NNNN`** (`cortex/adr/README.md:38`) — "the zero-padded four-digit number
  of the superseding ADR." A bare number in machine-readable frontmatter with no slug to
  disambiguate. Seven live pointers in wild-light.
- **Reference-size ratchet — zero headroom.** `skills/refine/references/size-pin.txt` = 20568
  against 20568 measured. `measure()` counts all regular files, not just `.md`. Any prose
  addition fails `tests/test_reference_size_ratchet.py` unless offset byte-for-byte.
  `skills/morning-review/references/` is likewise at 21074/21074.
- **Dual-source mirror** — `skills/refine/` is mirrored into `plugins/cortex-core/`; the
  pre-commit hook rebuilds from staged blobs. Note the known `rsync -a` same-byte-length blind
  spot (`project.md:60`): an `ADR-0080` → `ADR-0081` edit is same-byte-length and therefore
  invisible to the reconciler.

### ADR-0010 precedent

`cortex/adr/0010-task-id-is-task-identity-not-number.md` (accepted): `task_id` string becomes
sole identity; `.number` demoted to a non-unique telemetry-only group ordinal. Its safety came
from `task_id == str(number)` for the unsuffixed case — *"byte-identical to its pre-change form
by construction."* **No analogous property exists for ADRs**: `ADR-0080` and
`the-python-suite-runs-inside-test-command` are not the same string.

---

## Web

### log4brains hit this exact bug and fixed it by dropping the number

The single most on-point prior art. [log4brains ADR
20201016](https://thomvaill.github.io/log4brains/adr/adr/20201016-use-the-adr-slug-as-its-unique-id/)
records the identical failure: two developers create ADRs on separate branches, `git merge`
accepts both files because the filenames differ, and the tool then has two ADRs claiming one
number. **Decision:** supersede `NNNN-title.md` with `YYYYMMDD-title.md`, making the
date-prefixed slug the identity, and push ordering out of the filename into a tool-computed
fallback chain (`date` field → git creation date → filesystem date → slug).

Stated cost: any consumer expecting "sort by filename == sort by decision order" loses that
for free.

### adr-tools and the rest of the ADR ecosystem do not address it

- **adr-tools** (Nat Pryce) — `adr new` reads the highest existing `NNNN-*.md` and increments.
  No locking, no reservation. The README does not mention concurrency, branches, or merges at all.
- **MADR**, **adr-manager**, **dotnet-adr**, **pyadr**, **Structurizr**, **arc42** — all use
  sequential `NNNN`; none documents collision handling. Structurizr's importer explicitly
  inherits adr-tools' naming and sorts alphabetically by filename.

### Every mature migration system demoted the sequential number

- **Alembic** — identity is a random hex revision id plus a `down_revision` parent pointer;
  history is a DAG walked by topological sort. Concurrent branches produce **multiple heads**,
  a normal detected condition resolved by `alembic merge` generating a diamond node. The most
  mature instance of dropping the display number entirely.
- **Django** — the number is a hint; the `dependencies` graph is identity. Two branches adding
  `0004_*` produce multiple leaves, reconciled by `makemigrations --merge` synthesizing a no-op
  merge migration.
- **Rails** — `YYYYMMDDHHMMSS` timestamps dodge prefix collisions; the real pain is the single
  `schema.rb` `version:` line conflicting on every merge, resolved procedurally.
- **Flyway** — same collision is a known pain point (issue #1323); answers are timestamp-based
  versions and `outOfOrder=true`, i.e. collision *tolerance*.
- **Liquibase** — changesets are keyed by an `(author, id)` **pair** precisely because a bare
  sequential id collides across branches. Practitioners recommend embedding a ticket key or a GUID.

### Git cannot detect this

Merge drivers (`.gitattributes` + `merge=<driver>`) fire only when git's three-way merge
detects **the same path** changed on both sides. Two branches adding `0080-a.md` and
`0080-b.md` are two unrelated additions; no driver, no conflict, no hook is invoked. Git has no
unique-index concept across filenames. The state of the art is a domain-aware tool that
rebuilds the index after merge (`alembic heads`, Django leaf detection) — routing around git's
blindness rather than fixing it.

---

## Requirements & Constraints

### project.md

- **Deletion bias** (`:23`) — discharge requires *"a consumer that turns a build or gate red
  when the surface is removed — **not a report-only or manually-invoked script** — or a filed
  bug recording observed failure."* **A report-only surface cannot discharge deletion bias for
  itself**, so anything shipped in that shape parks permanently on the deletion block.
- **Enforcement gates carry named evidence** (`:41`) — *"A new gate enters only with its named
  failure stated here."* The ADR citation audit's recorded evidence is *"a consumer repo
  accumulated dozens of phantom-ADR references plus a duplicate number."*
- **Solution horizon** (`:25`) — the "patch applies in multiple known places" branch is live:
  the same glob+max shape exists in `create_item.py:_get_next_id` and was already fixed once in
  `deferral.py` (#027).
- **Lifecycle identity is the canonical slug** (`:59`) — ratified, but **narrowly scoped**: it
  governs only the `resolve_invocation`-mediated path, numeric-keyed dirs remain permitted, and
  the defensive str-coercions MUST be retained. Even this precedent shipped as accept-both,
  never migrate-all.
- **Mirror rebuild same-byte-length blind spot** (`:60`).

### CLAUDE.md / docs/policies.md

- Editing `skills/` is **lifecycle-gated** (`CLAUDE.md:28`). `cortex_command/adr_citation_audit.py`
  is not in the gated list.
- **`CLAUDE.md:29` / `policies.md:11` prefer structural separation over prose-only enforcement**,
  and say prose-only is acceptable only *"where the cost of occasional deviation is low."*
- `policies.md:15` — apply verb-first (behavior into CLI verbs) rather than raising a pin.
- Shipped surfaces carry no repo governance (`CLAUDE.md:33`).

### cortex/adr/README.md

Three-criteria emission gate (`:19-27`). Frontmatter contract (`:29-49`) including
`superseded_by: NNNN`. Consumer-rule discipline (`:57-63`).

**The prose-only rationale has a named hole on the autonomous path.** `README.md:11-17` rests
on three grounds; two do not hold overnight:

- *"New ADRs are individually PR-reviewable… The gate has a human checkpoint"* — assumes a human
  evaluates before merge. Overnight opens the PR itself.
- *"This README surfaces on PRs touching `cortex/adr/`"* — assumes a human opens the diff.
- *"Stray ADRs are recoverable via `status: deprecated`"* — authorship-agnostic; **this one holds.**

### Prior rulings

- **#304 Edges** — *"Must stay report-only… a blocking gate would contradict that ratified
  posture"* AND *"The next-free-number helper is an explicit non-goal: existing ADRs are
  contiguous with no gaps or collisions, so a number-allocation tool solves a problem that has
  not occurred."* **The second clause's premise is now falsified twice over** — the collision
  occurred, and wild-light has five gaps (0007, 0008, 0022, 0025, 0027) that its own README
  ratifies as normal.
- **#027** — the ratified `O_EXCL` fix for the identical glob+max race.
- **#198 is a *performance* ticket** (trimming a ~21ms shim). The `CORTEX_REPO_ROOT` worktree
  pin landed as its Task 3 so `cortex-log-invocation` could skip `git rev-parse`
  (`pipeline/dispatch.py:695-700`). **It is not an identity-isolation ruling**, so nothing here
  "reverts #198." The trap it does leave: any allocator resolving the parent via
  `CORTEX_REPO_ROOT` reserves inside its own worktree and silently no-ops.
- **ADR-0005** — worktrees at `<repo>/.claude/worktrees/<feature>/`, each a separate checkout.
- **multi-agent.md:33** — the repo already resolves concurrent **branch-name** collisions with
  `pipeline/{feature}-2`, `-3` suffixes. Detect-and-suffix is an in-repo precedent.

### Scope

No ADR-specific area doc exists; ADR tooling is governed only by `project.md:48` pointing at
`cortex/adr/README.md`. No requirements doc states a worktree isolation guarantee for
filesystem-scanned identity allocators — a genuine gap.

---

## Tradeoffs & Alternatives

Options, with the corrected race location applied.

### (a) Reserve at spec time from the shared parent repo

**Does not fix it.** The number that collided was claimed at *plan* time; both plans discarded
the spec's value. Reserving at spec time without binding downstream adds a fourth place to rot.
Also: a plain write into `<repo>/cortex/adr/` from a *dispatched builder* is denied —
`OUT_OF_WORKTREE_ALLOW_WRITERS` (`overnight/sandbox_settings.py:66-73`) is six cache/tmp paths.
(Irrelevant at plan time, where the agent already writes to the home repo's `cortex/` tree.)

### (b) Slug-primary identity, number demoted to display

Prevents *ambiguity*, not collision — both `0080-*.md` files still exist; `ADR-0080` simply was
never a valid citation. Forward-only produces a permanently mixed corpus. `superseded_by: NNNN`
is a schema change with a migration. Lacks ADR-0010's byte-identity safety property.

### (c) Arm the existing detector into the morning report

Zero citation blast radius, zero schema change, no skill prose, already shipped in every
consumer repo. But see Adversarial §3 — the signal-to-noise numbers refute it.

### (d) Drop the number entirely for new ADRs

Prevents completely, but unnumbered files fail `_CORPUS_FILENAME_RE` (`:73`), so `load_corpus`
drops them: the auditor goes blind to the new half of the corpus. `superseded_by: NNNN` breaks.

### (e) Date- or content-derived identity

**The date variant does not prevent the incident** — two same-run worktrees share a date and
both produce `20260807-…`. A short hash is collision-resistant but opaque, unsortable, and
destroys the human-citable form; same auditor blindness as (d).

### (f) Post-merge allocation in the runner

Builders author `cortex/adr/DRAFT-<slug>.md`; a post-merge runner step renames to the next free
number and rewrites citations — mirroring `_next_backlog_id` (`overnight/report.py:969-987`),
the pattern that demonstrably keeps backlog numbers unique. Structurally prevents the
collision, zero final blast radius. **But see Adversarial §2 — the rewrite step is the
dangerous part.**

### (g) Allow duplicates; make `superseded_by` carry the slug

Accept that two ADRs may share a number, and fix only the one machine-readable consumer.
Seven sites in wild-light vs. policing 28,439 citations. Surfaced by the Adversarial pass.

### (h) `O_EXCL` claim at plan time in the home repo

The #027 remedy applied at the actual allocation site. Not proposed by any core angle because
all four inherited the ticket's worktree framing.

### The "uuid makes collisions harmless" premise is false

Backlog item `130`:30 records an actual display-ID collision: overnight wrote follow-ups at
101/102/103, a later `/discovery` decompose allocated the same IDs to unrelated content, and
*"the body content — parse-error context, failure rationale — is permanently lost."* The uuid
did not save it. **The proven pattern in this repo is serialized allocation, not uuid-rescue.**

---

## Adversarial

Ranked strongest first. Where this section contradicts an earlier one, this section is the
later evidence and was independently verified.

### 1. The race is misdiagnosed — it is not a worktree problem (verified)

`orchestrator-round.md:483` places plan-gen in the home repo; Step 3c (`:474`) confirms
parallel dispatch. Both agents glob the same directory concurrently. Consequences:

- "`O_EXCL` does not generalize across worktrees" is **true but irrelevant** — the allocation
  site is not across worktrees. `O_EXCL` generalizes exactly.
- The sandbox analysis answers a question nobody needs to ask — plan-gen already writes into
  the home repo's `cortex/` tree.
- Option (f)'s premise (allocation *must* be deferred post-merge because builders cannot see
  each other) is false at the point the number is actually chosen.

### 2. Option (f)'s citation rewrite is more dangerous than the bug

- **The scanner it would be built on is blind to most of a consumer repo.** `_SCAN_EXTENSIONS`
  is `.md`/`.py` only (`adr_citation_audit.py:76`). wild-light is a Godot project: ~2,349 ADR
  tokens in `.gd`, 665 in `.json`, plus `.gdshader`/`.js`/`.txt`/`.html`/`.yaml`. A rewrite
  renumbers the `.md` citations and leaves thousands wrong. **A duplicate is ambiguous but
  internally consistent; a half-applied renumber is actively wrong and invisible to the same
  tool that caused it.**
- **It must mutate files outside both merged features** — `superseded_by:` frontmatter on
  pre-existing ADRs, with no slug to verify against.
- **Same-byte-length hazard**: `ADR-0080` → `ADR-0081` is byte-length-preserving, so the
  `rsync -a` mirror reconciler cannot see it (`project.md:60`).
- Slugs themselves collide: `two-scenario-enemies-are-aliased-onto/spec.md:276` proposed
  `0075-fixture-actor-positions-…`, which shipped as `0077-fixture-actor-positions-…`. Under
  (f) those are two identically-named `DRAFT-*` files.
- A DRAFT slug cited in a commit message or PR body is immutable.

### 3. Option (c) is refuted by its own signal-to-noise

Measured:

- **cortex-command**: 66 findings — 41 `slug_mismatch`, 25 `unresolved`, **0 duplicates, 0 gaps**.
  None actioned.
- **wild-light**: 565 findings across 293 files — 492 `unresolved`, 68 `slug_mismatch`, 5 `gap`,
  0 duplicates (already fixed by hand).

The proposal adds one finding to a list of 565 with an established 100% non-action rate, to
catch an event with a base rate of one. Worse, `detect_gaps()` emits 5 findings that wild-light's
own ADR README ratifies as normal ("number gaps are withdrawn or never-emitted numbers, left
as-is") — five permanent false positives on day one. **That is how the other 66 got ignored.**
Both plausible landing surfaces are at zero ratchet headroom.

### 4. The "just re-check before writing" mitigation was already written, and returned green during the failure

Both plans already contained it. `no-gate-anywhere-runs-pytest-so/plan.md:134`: *"Re-run
`ls cortex/adr/` immediately before creating the file and use whatever the lowest free number
is then."* And both wrote a verification step for exactly this:
`a-generator-version-bump-has-an/plan.md:424`: `ls cortex/adr/ | grep -c '^0080-'` → expect `1`.

**That check ran in a worktree and returned `1` in both worktrees.** A verification step
designed to detect a duplicate ADR number passed during the duplicate. Any fix that adds more
instructions, re-reads, or verification lines at implement time has already been tried and has
a measured green-on-failure. **The observation window is wrong, not the diligence.**

### 5. "Make the spec's number binding" is refuted — but spec-time *reservation* is not

The two specs held **distinct** numbers (0077, 0078) and lost them only because unrelated
evening sessions consumed 0077/0078/0079 (`cb37f9f9` 22:07, `35438fef` 22:36, `4af07de1` 22:45).
Binding a stale spec number converts a probabilistic collision into a guaranteed one against a
third party. But a spec-time **reservation** (zero-byte `O_EXCL` claim) would have prevented
both this collision and the evening consumption. Its own failure mode: an abandoned reservation
is a phantom ADR that `load_corpus()` would index as real — it needs a reaper, and reservations
must be distinguishable from ADRs by a name shape the corpus regex rejects.

### 6. The measured harm is nine lines

wild-light `7ebc1ded`: **5 files changed, 9 insertions, 7 deletions.** One rename, one H1, six
citation lines, two README index rows — fixed by a human in one morning commit with a tiebreak
that took no investigation ("claimed it first (02:15), so it keeps 0080").

The "7,879 citations / 1,361 files" framing is a **ceiling, not a marginal**. Only six citations
were affected. Report the marginal.

### 7. "Cite ADRs by meaning" already existed and did not survive contact

wild-light `CLAUDE.md:167` carries *"Cite ADRs by meaning, not bare number."* Measured across
that tree: **28,439 bare/prefix-form citations vs. 3,746 slug-carrying path-form — 88% bare.**
All six citations broken by this incident were bare. **"Write the convention down" is not an
untried option; it is the status quo that failed.** Symmetrically, mandating slug-carrying
citations is a 28,439-site rewrite.

### 8. What a duplicate number actually costs, enumerated

- **Nothing computes on ADR numbers.** No build, test, gate, hook, or runtime path resolves one.
  The corpus is a human lookup surface.
- Path-form citations still resolve unambiguously — 3,746 sites already safe.
- Bare-number citations become ambiguous — a *reading* cost at lookup time, not a correctness cost.
- **One genuine corruption vector: `superseded_by: NNNN`** — a bare number in machine-readable
  frontmatter with no disambiguator. Seven live pointers. This is the single strongest argument
  for uniqueness, and it argues for fixing 7 sites, not policing 28,439.
- README index rows collide visually — cosmetic.

### 9. A second, more frequent defect nobody proposed anything for

`7ebc1ded`'s message: *"Neither branch had added its ADR to `cortex/adr/README.md`; both rows
are added here."* **Two-for-two miss rate on the index update**, versus one-in-N on the number.
No option touches it, and `detect_duplicates()` cannot see it.

### 10. #304's stated premise is factually false

*"existing ADRs are contiguous with no gaps or collisions"* — wild-light has five gaps, and its
README ratifies gaps as normal. #304 ratified report-only on a false premise, which both weakens
it as binding precedent and proves gap detection is noise.

### Where the core angles are simply right

The web survey is sound and primary-sourced; its conclusion — every mature system demoted the
sequential number to a display ordinal and moved identity to something a merge cannot collide —
is the correct long-horizon answer and matches ADR-0010. The deletion-bias reading is correct.
`detect_duplicates()` does work as described.

---

## Open Questions

1. **Does a plan-time `O_EXCL` claim in the home repo's `cortex/adr/` solve this outright?**
   — *Resolved in direction, deferred in mechanism.* The allocation site is verified as a single
   shared directory with concurrent writers (`orchestrator-round.md:483`, `:474`), which is
   exactly #027's ratified scope. What is **not** resolved and belongs in Spec: the reservation's
   name shape (must be rejected by `_CORPUS_FILENAME_RE` at `adr_citation_audit.py:73` so
   phantoms are never indexed as real ADRs), its reaper for abandoned claims, and whether the
   claim is made at spec time, plan time, or both.

2. **Does the fix need to reach the daytime/interactive path too?** — *Deferred to Spec: this is
   a scope decision for the requirements interview, not a question code-reading settles.*
   Research established the facts it turns on: three ADRs landed from concurrent non-overnight
   sessions on the evening of 08-06, so the daytime path is not serial either, and a claim verb
   invoked only by the overnight orchestrator would leave that untouched. It bears directly on
   whether the fix lands in shipped skill prose (zero ratchet headroom) or in a CLI verb both
   paths call.

3. **Contradiction — citation counts.** Tradeoffs measured wild-light at 7,879 citations / 1,361
   files; Adversarial measured 28,439 bare-form tokens and could not reproduce the first figure.
   *Do not spec against either number.* The marginal figure that matters is verified: **six
   citations, nine lines** (`7ebc1ded`).

4. **Contradiction — the recommendation.** Tradeoffs recommends arming the detector (c);
   Adversarial refutes it on measured signal-to-noise (565 findings, 0 actioned, 5 sanctioned
   false positives). *Resolved against (c) as a standalone deliverable* — the non-action rate is
   measured, not hypothetical, and `project.md:23` independently bars a report-only surface from
   discharging deletion bias for itself.

5. **Is the ticket justified at all under the front-door evidence bar?** — *Open, and Spec must
   answer it explicitly.* One incident, one repo, one night, nine lines of damage, caught and
   fixed by a human in one commit. Against that: the allocation site is a verified TOCTOU race
   with a ratified in-repo remedy (#027) that is cheap at the point of use. The Value section of
   the spec must state this honestly rather than leaning on the ceiling figure.

6. **Should `superseded_by` carry a slug regardless of which option ships?** — *Deferred to Spec
   as an in-or-out scope call.* Research settled the facts: it is the only machine-readable
   consumer of the bare number, it has seven live sites in wild-light, and it is the one place a
   duplicate is genuinely unresolvable rather than merely ambiguous. Whether that small fix rides
   along with the allocation change is a requirements decision, not a research finding.

7. **The README-index miss (two-for-two) is out of scope but unowned.** — *Deferred with
   rationale:* it is a distinct defect from number allocation, has a higher observed rate, and
   folding it in would widen a ticket whose evidence base is already thin. File separately.
