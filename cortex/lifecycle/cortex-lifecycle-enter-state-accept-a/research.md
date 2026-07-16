# Research: lifecycle identity — canonical `lifecycle_slug` resolved once, never invented by a writer

**Ticket**: #379 — `cortex-lifecycle-enter`/`state` accept a numeric feature and create a shadow lifecycle dir instead of resolving or rejecting
**Tier**: complex · **Criticality**: high · **Angles dispatched**: 8 (3 core + 4 chosen + adversarial)

## Clarified intent

A lifecycle's identity is the backlog item's canonical `lifecycle_slug`, resolved once in the served-verb class and emitted for every state including `new`, so a ticket number is always a valid **input** and never becomes a stored **identity** — with `enter` failing loud rather than materializing a directory it cannot account for.

## Codebase Analysis

**The producer defect.** `resolve.py:204-211` (the `new` branch) returns the raw caller token as `feature` while the resolved backlog dict carrying `lifecycle_slug` is in scope at `:208`. The #370 remap at `:188` fires only when `slug and slug != feature and (lifecycle_base / slug).is_dir()`, so it never fires on a first entry.

**The write path.** `enter.py:169` calls `create_index(feature, ...)`; `:175` passes `lifecycle_slug=feature` into `start_sync`, which writes it back to backlog frontmatter (`start_sync.py:111`, gated on `phase == "none"`, `start_sync.py:110-112`). So the first `enter` **pins** whatever token it was handed as the permanent canonical identity.

**The change is additive.**
- `resolved_from` already exists (`resolve.py:179, 189, 231-233`) and is already served on the `resume` arm (`next_verb.py:459-460`). No new field shape, no protocol bump.
- `next_verb.py` passes `new` through **verbatim** via `_ROUTING_PASSTHROUGH` (`:88-96`, `:421-424`), so a `resolve.py` fix reaches `cortex-lifecycle-next` with **zero** `next_verb.py` changes.
- No skill prose changes: `skills/lifecycle/SKILL.md:53` already threads `{feature}` opaquely.

**Fail-loud conventions.** There is **no `die()` helper** anywhere in `cortex_command/` (zero grep hits). The house pattern is: raise a purpose-built exception from the core function, catch by type in `main()`, write a `cortex-lifecycle-enter: <what/why>` line to stderr, return a specific exit code. **Exits 1 and 2 are already taken** in `enter.py` (`:261-267` unresolved `--backlog-file`; `:268-269` ambiguous slug) — a new guard needs its own code.

**Out of scope but adjacent.** `state_cli.py:146-150` performs zero resolution — a bare `Path("cortex")/"lifecycle"/feature/"events.log"` join, printing `{}` on no match. It will keep returning `{}` for a hand-typed numeric id after this fix. `/cortex-core:dev` defaults that to `criticality: medium`.

**Residue resolver is a victim, not a defendant.** `critical_review/resolve_feature_cli.py` takes a positional `session_id`, globs `cortex/lifecycle/*/.session`, and prints the parent dirname. It returned `"269"` in the incident only because `enter` had written `.session` into the shadow dir. Fixing `enter` fixes it for free — no code change needed there.

## Requirements & Constraints

**ADR status is load-bearing and was nearly missed.** Only **ADR-0010 is `accepted`**; ADR-0019, ADR-0024, and ADR-0027 are all `status: proposed`. Per `cortex/adr/README.md:61-63`, a skill "MUST NOT automatically treat a proposed or deprecated ADR as binding" and "SHOULD surface the relevant ADR(s) to the user." The constraints below are recorded design intent to weigh, not automatic law.

- **ADR-0019** is scoped to caller-passed `--backend`-shaped flags. The proposed `enter` guard (argument + filesystem validation, no resolution) **does not implicate it at all** — that is the normal job of a skill-helper verb per `project.md:35`. **No scope extension is required.** ADR-0019 is also a record-it-knowingly precedent, already stretched twice (`Scope extension (#326)`, `Scope extension (#371)`), not an absolute bar — so the ticket's Option 1 is *permitted but costly*, not prohibited.
- **ADR-0024** sanctions `next`/`advance`/`describe` alone to "resolve identity." `resolve.resolve_invocation` **is** `next`'s in-process identity engine (`next_verb.py:6`, `:72`, `:416`), so the fix site is inside the sanctioned surface. The separate `cortex-lifecycle-resolve` console script (`pyproject.toml:75`) is dormant per `bin/.parity-exceptions.md:22` ("no SKILL.md or shell path invokes the CLI wrapper").
- **ADR-0010** governs `FeatureTask` in the overnight dispatch path only. It is a **same-shaped precedent**, not a governing record for feature identity. Cite as analogy, not authority.
- **ADR-0027**: `lifecycle_slug` is already on `STRING_INTENDED_KEYS` (`frontmatter_quote.py:36-37`). Any producer writing it to frontmatter must route through the quoter.
- **Nothing in the repo governs lifecycle directory naming or slug format** — no requirement, no ADR, no area doc. This is why the ticket could not define "unmatched": there was never a recorded answer. The operator's decision is the record.
- **Solution horizon** (`project.md:21`) resolves to the durable version only if a second call site needing the same resolution can be **named now**. It can — see Consumer Reachability.

## Web Research

- **"Parse, don't validate"** (Alexis King) names this exact failure: **shotgun parsing** — normalization scattered across call sites, each making its own divergent judgment, so input is partially normalized before anything notices. Prescribed fix: transform once at the boundary; interior code only ever sees the parsed form. This is the proposed design.
- **`git rev-parse`** resolves any input form to one canonical object id, and on an ambiguous prefix **errors and lists candidates rather than guessing** — precedent for fail-loud over invent-an-identity.
- **Rails FriendlyId `:history`** keeps prior slugs resolvable after the derived slug drifts — the grandfathering precedent. Collisions are resolved with a counter/UUID suffix against a uniqueness constraint.
- **Kubernetes Name vs UID** is the strongest **counter-argument**: durable identity should be the system-assigned immutable key (→ the ticket number), with the human-friendly name (→ the slug) as an alias, precisely because a title-derived name drifts. See Open Question 3.
- **Anti-patterns confirmed**: UPSERT-without-a-key (silently does the wrong one), Perl autovivification and S3 implicit-prefix creation (read/lookup paths must be structurally incapable of creating state). **No system found silently truncates a slug and accepts a collision** — uniqueness is always enforced at a constraint layer.

## Historical Intent

- **The `is_dir()` conjunct is #370's deliberate BOUND, not a bug.** #370's Integration text is a literal acceptance criterion: *"Only emit `state: "new"` when neither the numeric-token dir nor the backlog-slug dir exists."*
- **The comment/code "contradiction" at `:162-188` does not exist.** Both were born in commit `db7c8b1c`. The comment's "before any dir-existence verdict" refers to the two *return-point* guards below it; the `is_dir()` inside the remap tests the *candidate* dir — exactly what #370 required.
- **#378 ratified numeric dirs as legitimate**, verbatim: *"Does NOT reject or reclassify bare-numeric feature tokens at parse time (**dropped after critical review**): numeric backlog IDs are a first-class supported input... **374/378 are legitimate numeric-keyed dirs**."* It also explicitly declined to move them ("kebab-remap would break resolution").
- **`374/` and `378/` were created by `/cortex-core:refine`** given a bare number (`5a179d78`, `3a4929d8`) — mechanical output of the pre-#254 behavior, later *ratified* (reactively, while fixing a crash), never originally designed.
- **The record is SILENT** on whether `state: new` may return a **normalized** `feature` value when the slug dir does not yet exist. Never specified or tested by #370, #378, or #254. This proposal lands in genuinely unspecified territory.
- **#254's DR4 install_guard concern is CLOSED** — it was about the *bash* `bin/cortex-resolve-backlog-item` avoiding wheel-side imports; #254 eliminated that boundary by promoting it to a Python entry point. It does not apply to `resolve.py`, which already imports `cortex_command.backlog.resolve_item` directly. #254's own R11 explicitly anticipates this design: *"Resolver does NOT verify lifecycle directory existence... Callers needing directory verification do it separately."*

## Identity Chain Correctness

- **Internally consistent**: all five input forms (uuid-prefix, numeric, kebab, `lifecycle_slug`-frontmatter, title-phrase) that resolve to the same item converge on the same `_build_json` output.
- **Collisions**: 372 items → **372 unique 6-word-capped slugs, zero collisions today**; zero duplicate frontmatter values. 141 titles are truncated. **But see Adversarial §2 — this measurement is survivorship.**
- **No uniqueness enforcement exists anywhere.** `update_item.py` writes `lifecycle_slug` as a plain scalar with no cross-item check. `create_index.py:164-165` is **skip-if-exists**, so a collision would silently merge two tickets' `events.log`/`spec.md`/`plan.md` with no error.
- **`resolved_from` is inert**: present only on `resume`; **zero readers in all of `skills/`**. Adding it to `new` is an evidence trail, not a feature.
- **Fixed point**: converges on call 2 — but to "whatever was typed first," not to the canonical slug.
- **`374` works by accident**, not by grandfather design: the read and write sides agree on the literal string `"374"` because the same raw token was used for both.
- **Context B**: `backlog = None`, the remap never fires, caller token stands. `derive-slug` (`resolve.py:116-125`) is a **model judgment call with zero collision checking**.

## Consumer Reachability & Write Surface

**Producer + `enter` guard is not a complete closure of the vivification class.** Writers that create a lifecycle dir from a caller-supplied token, ranked by blast radius:

1. **`cortex-lifecycle-event`** — zero identity validation, unconditional vivification, and **actively hand-invoked** from `criticality-matrix.md`, `critical-review-gate.md`, `worktree-entry.md`, plus documented as `advance.py`'s `_SANCTIONED_OVERRIDE`. Highest exposure.
2. **The 4 standalone B1 CLIs** (`plan-decision`/`review-verdict`/`spec-approve`/`implement-transition`) — same mechanics; deliberately kept callable per `docs/rollforward-exit.md`.
3. **`cortex-critical-review-write-residue`** — vivifies unconditionally with only a kebab regex. **Its own siblings in the same file already implement the guard.**
4. **`record_pr_opened`**, **`create_index` Shape B**, **`finalize`** — vivify with no identity check.

**The guard pattern is already shipped and proven here.** `critical_review/__init__.py:484-494`'s `_lifecycle_dir_exists()` suppresses the dir-creating side effect when the target dir is absent, "so a non-feature review cannot create a phantom lifecycle dir." The proposed `enter` guard is a **fourth application of an existing in-repo pattern**, not a new invention.

**Critical correction to that angle's own recommendation.** It proposed generalizing the guard onto `lifecycle_event.py`'s write primitive. That is **refuted by the repo's own docstring** (`critical_review/__init__.py:490-492`): *"The guard lives in the callers, NOT in `log_event_at` (which must keep creating the dir for the legitimate fresh-lifecycle first-write at Site A, `refine.py`)."* Standalone refine has no `enter` and mkdirs the dir itself (`refine.py:212`, `:289`). **Guard the callers; never the primitive.**

**Safe by construction (verified)**: `overnight/advance_lifecycle.py:191-192` fails closed on `events_path.exists()`. `diagnose_session_path.py` degrades to a `cortex/debug/` fallback on a missing dir and never writes the artifact. `register_artifact` fails closed (`no-index`).

**A third identity producer exists**: `overnight/backlog.py:104-129` (`BacklogItem.resolve_slug()`) independently implements the same derivation chain, and `filter_ready` (`:518-521`) checks `cortex/lifecycle/{slug}/research.md`. **The overnight runner already assumes the derived-slug convention this fix establishes** — today it can silently disagree with what `enter` created. The fix makes them agree.

## Adversarial Review

**1. Path traversal — the fix would remove an accidental circuit-breaker on a live hole.**
`_reject_unsafe_slug` is a house pattern in **seven** verbs (`describe.py:55-63`, `plan_decision.py:71-79`, `review_verdict.py:101-109`, `next_verb.py:134-144`, `advance.py:171-179`, `implement_transition.py:88-96`, `spec_approve.py:116-124`). **`enter.py`, `create_index.py`, `finalize.py`, `register_artifact.py` have none.** `_resolve_lifecycle_slug` (`resolve_item.py:135-136`) returns the frontmatter value **unsanitized** (`if slug: return str(slug)` — no regex, unlike the constrained `slugify` fallback). Today the vector is inert because the value can only reach `feature` when `(lifecycle_base / slug).is_dir()` is already true. **Dropping that conjunct removes the circuit-breaker.** And `next_verb.py`'s sanitizer is scoped to the `resume` arm only (`:433`); `new` returns verbatim at `:421-424` and never reaches it. A backlog item with `lifecycle_slug: ../../../../tmp/evil` — from a bug, a corrupted write, or an autonomously-authored item — would remap, pass unsanitized, and be written. **The fix MUST add `_reject_unsafe_slug` to `enter.py`.**

**2. The collision measurement is survivorship — the fix introduces the vector.**
Collisions cannot occur today *because* the raw numeric token (unique by construction) is what gets written. **225 items have no pinned `lifecycle_slug`; 204 of those are truncated at the 6-word cap.** Under the fix, two items capping to the same slug would both resolve to one dir on first entry, and `create_index`'s skip-if-exists would **silently merge them**. This is a new create-time vector the current design structurally cannot produce.

**3. Title-drift race on first entry (the Kubernetes argument, made concrete).**
`refine`'s SKILL.md Step 1 **re-resolves independently** ("use it directly, don't re-derive") rather than trusting a slug handed down by `next`. So one `/cortex-core:lifecycle <ticket>` run has **two** derivation moments. A title edit between them splits the dir `index.md`/`.session` point at from the dir artifacts land in. This is not possible today because the `new` state's `feature` is the title-independent ticket number. **The pin-on-first-`enter` closes the window for all subsequent invocations, but the first entry is exposed.** Likelihood: low in solo interactive use; higher for the overnight runner and multi-agent/consumer-repo scenarios — i.e. exactly where #379 came from.

**4. `isdigit()` removal is the safer choice.** Keeping it would fail loud only when a mis-threaded token *looks* numeric, letting a typo'd or stale non-numeric slug pass into a shadow-dir write. Dropping it catches **every** existence/phase mismatch regardless of token shape.

**5. `phase != "none"` is a sound discriminant.** The only prose invocation of `enter` is `skills/lifecycle/SKILL.md:53`, and `:56` passes `none` for `new`, else the served `state` (non-`none` only when `dir_exists` was already true). No legitimate caller passes a non-`none` phase for a non-existent dir. **TOCTOU** (dir deleted between `resolve` and `enter`) trips the guard — which is the *desired* behavior (fail loud, don't resurrect), but needs an error message distinguishing "dir vanished mid-flight" from "caller mis-threaded the identity."

**6. Migration: no hazard for the 175 pinned dirs, none for `374`/`378`.** The fix changes behavior **only** when `slug != feature` AND the slug's dir does not yet exist — i.e. exclusively first-time entries on not-yet-pinned items. A cheap pre-ship acceptance check comparing every `cortex/lifecycle/*/` dirname against its item's frontmatter is recommended to rule out in-flight dirs created via the `refine.py` mkdir bypass.

**7. Protocol.** `protocol.py:24-27` bumps on "payload change not backward-compatible for the prose." This changes a field's **value semantics** without changing envelope **shape**, so no bump by the letter — but that policy has **no mechanism to flag semantic-value drift for out-of-repo consumers**, which is precisely the wild-light scenario that produced #379.

**8. Steelmen assessed.** *(a) Do nothing* — not costless: the disagreement caused #379's real incident, and 204/225 unpinned items sit near the truncation boundary. *(b) Fix refine to store the raw token instead* — wider blast radius: refine already routes through `cortex-resolve-backlog-item`, and `lifecycle-slug` is referenced by name across `refine/SKILL.md:86,94,98`; this would mean un-deriving a shared field. *(c) #378 incompatibility* — not retroactive: #378 ratified numeric **input** and the existing dirs, not a mandate that new dirs be numeric-named.

**9. Pre-existing bugs found, orthogonal to this fix.** `complete <nonexistent-slug>` misclassifies as `state: new` instead of erroring like `resume` does (`resolve.py:158`'s "feature / resume / complete" comment is aspirational — there is no `mode == "complete"` branch). `phase_override` can set a phase on a non-existent dir, but `SKILL.md:56` hardcodes `none` for `new`, masking it.

## Open Questions

1. **Does the collision vector (Adversarial §2) require uniqueness enforcement in this ticket?** — **RESOLVED (operator, this session): in scope.** Zero collisions exist today (372/372 unique), but the fix converts a structurally-impossible failure into a merely-improbable one whose failure mode is silent cross-ticket state merging via `create_index`'s skip-if-exists. Mitigation to spec: have `enter` verify that an existing target dir's `index.md` refers to the *same* backlog item as `--backlog-file`, and fail loud on mismatch — a caller-side guard consistent with the house pattern, closing the merge without adding a uniqueness constraint. **Constraint: must not require new skill prose.**

2. **Must `_reject_unsafe_slug` land in `enter.py` as part of this ticket (Adversarial §1)?** — **RESOLVED (operator, this session): yes, in scope.** The hole is live today in four verbs and is currently held shut for `new` only by the conjunct this fix removes; shipping the producer fix without it is a net security regression rather than a neutral deferral. `enter.py` adopts the 7-verb house pattern. The broader `create_index`/`finalize`/`register_artifact` gap, plus the unsanitized `_resolve_lifecycle_slug` return (`resolve_item.py:135-136`), is **deferred to a separate security ticket** — it is live today, independent of this fix, and larger than #379.

3. **Is the title-drift race on first entry (Adversarial §3) acceptable?** — **RESOLVED (operator, this session): accept and document.** Scope correction to the adversarial finding: `enter` pins `lifecycle_slug` to frontmatter at SKILL.md Step 2, **before** refine re-resolves at Step 3, and frontmatter is priority-1 in `_resolve_lifecycle_slug` — so refine reads the pin rather than re-deriving. The exposure is the Step 1 → Step 2 window (one skill turn), not a whole run. Verified empirically this session: `enter` wrote `lifecycle_slug: cortex-lifecycle-enter-state-accept-a` and every subsequent resolution consumed it. Standalone refine (no `enter`, no pin — `refine.py:212`, `:289`) already re-derives from the title on every call **today**, so the fix adds no new class of exposure; it makes lifecycle match refine's existing behavior. **Document the provisional-until-pinned window in code docstrings and `spec.md` only — not in skill prose.**

4. **Scope of the vivifying-writer class.** — **DEFERRED to a follow-up ticket.** Rationale: `cortex-lifecycle-event`, the 4 B1 CLIs, `record_pr_opened`, `create_index` Shape B, and `finalize` form a coherent, nameable class whose repair is the same guard applied at each caller. Per `project.md:21`'s Solution horizon, the durable version is named and surfaced rather than silently inflating #379, and per ADR-0007 decomposition is the repo's convention. `write_residue_cli` is a candidate for inclusion **in** #379 since the ticket names the residue path and the guard exists in its own sibling functions.

5. **Does `state_cli.py` stay unfixed?** — **DEFERRED.** It is one of #379's three named surfaces but performs zero resolution and cannot corrupt (read-only, returns `{}`). It works for any caller threading the envelope; only a hand-typed numeric id degrades, defaulting `/cortex-core:dev` to `criticality: medium`. Fixing it requires either resolution in a dumb verb (a genuine ADR-0019 question) or accepting the degrade.

6. **The record is silent on the core question.** — **RESOLVED by operator decision, recorded here.** Whether `state: new` may return a normalized `feature` was never specified by #370/#378/#254. The operator decided (this session): the ticket number is a valid **input**, never a stored **identity**; `374`/`378` are grandfathered untouched. This research is the record.

7. **Failure mechanism for the `enter` guard.** — **RESOLVED (operator constraint: no skill-prose bloat).** Exits 1 and 2 are taken (`enter.py:261-269`). A *new exit code* would force a new arm into SKILL.md Step 2's prose. Returning `{"state": "error", ...}` instead is handled by Step 2's **existing** line ("`ensure-failed`/`error` → halt"), costs zero prose, and matches the never-crash `{"state": ...}` house envelope. **Spec constraint: the guard's failure must be expressible through prose that already exists.**

## Operator decisions recorded (this session)

The record was silent on every question below; these decisions **are** the record.

1. **A ticket number is a valid input, never a stored identity.** One canonical identity, many accepted inputs.
2. **`374`/`378` are grandfathered untouched** — no migration, no dir renames, no frontmatter rewrites.
3. **Both companion guards are in scope** (traversal + same-item collision check), because the producer fix is what unblocks them.
4. **Title-drift on first entry is accepted and documented**, not mitigated.
5. **No skill-prose bloat.** All documentation lands in code docstrings and `spec.md`. Zero `skills/**` edits — achievable because `SKILL.md:53` already threads `{feature}` opaquely and the guard reports through the existing `error` arm.

## Considerations Addressed

_None — no `research-considerations-file` was passed (no parent epic; the alignment sub-rubric did not run)._
