# Research: Close the /cortex-core:lifecycle reserved-sub-command routing gap and offload the wontfix workflow to an order-enforcing verb

> Lifecycle: `wire-cortex-corelifecycle-wontfix-invocation-and` (backlog #329) · tier `complex` · criticality `high`
> Clarify-approved scope: **fix both** — a general reserved-first-word routing mechanism in SKILL.md Step 1 (covering `wontfix` *and* the co-broken `resume`) **plus** a new order-enforcing verb `cortex-lifecycle-wontfix`. Research subsequently surfaced a **third** co-victim class (phase tokens, incl. the already-shipped-broken `complete <slug>`) — see Open Questions.

## Codebase Analysis

### Files that change (canonical sources; mirrors noted)

- **`skills/lifecycle/SKILL.md`** — the root-cause file.
  - **Step 1 parse (line 34)**: `first word = feature name (strip a leading # first…), second word = explicit phase override`. Single code path; no reserved-word branch. The reserved-first-word mechanism inserts here, composing with the `#`-sigil strip (line 34) and the prose-vs-slug derivation (line 36, valid-slug regex `^[a-z0-9]+(-[a-z0-9]+)*$`).
  - **Invocation block (lines 24–26)**: already advertises `resume {{feature}}` (line 26, broken) and `{{phase}}`-as-first-word (line 25, broken). `wontfix <slug>` is *not* advertised here — only in `complete.md:148`. Add `wontfix <slug>` and reconcile the advertised forms with the parse.
  - **References-list line 183**: the `wontfix.md` situational-reference link **is still present** (the ticket's "now removed in the list collapse" is **stale** — account for it; the discoverability anchor exists).
  - Frontmatter `argument-hint` (line 5, `<feature> [phase]`) and `inputs` (lines 6–8) encode a **feature-first** contract that contradicts the phase-first/resume-first Invocation forms (see Routing Parse §contract contradiction).
  - Mirror: `plugins/cortex-core/skills/lifecycle/SKILL.md` (regen via `just build-plugin`).
- **`skills/lifecycle/references/wontfix.md`** — the prose workflow to thin.
  - 3 steps: (a) `git mv` archive (lines 9–15), (b) printf `feature_wontfix` append (lines 17–39), (c) `cortex-update-item … --status wontfix --lifecycle-phase wontfix --session-id null` (lines 41–47).
  - Prose-only ordering gate at line 5 + "Why the step order matters" (lines 49–53) — the gate to structuralize.
  - **Stale citation**: lines 5 & 15 cite `hooks/cortex-scan-lifecycle.sh:227` for the archive-skip; that hook is now a 9-line wrapper and the real skip is `cortex_command/hooks/scan_lifecycle.py:907` (`if feature in ("archive","sessions"): continue`). Fix the citation while here.
  - Mirror: `plugins/cortex-core/skills/lifecycle/references/wontfix.md`.
- **`skills/lifecycle/references/complete.md`** — Branch 1 `feature_wontfix` detection (lines 88–94) and the `wontfix <slug>` advertisement (line 148). Also advertises the **already-broken** `complete <slug>` finalize re-invocation (lines 72, 80). Mirror under `plugins/cortex-core/…`.
- **NEW `cortex_command/lifecycle/wontfix_cli.py`** + `pyproject.toml [project.scripts]` entry `cortex-lifecycle-wontfix = "cortex_command.lifecycle.wontfix_cli:main"` (lines 52–57 block). **Wheel-only — no plugin mirror** (`just build-plugin` rsyncs only `bin/cortex-*`).
- **NEW test** `cortex_command/lifecycle/tests/test_wontfix_cli.py` (alongside `test_counters.py`, `test_init_ensure.py`).
- **`bin/.events-registry.md`** (`feature_wontfix` row, line 26) — producers-column hygiene update (not gate-required; see Test & Parity).

### Integration points (consumers of the contract — all tolerant readers)

- `cortex_command/common.py:_detect_lifecycle_phase_inner` (lines 278–345): `json.loads` + `event.get("event") == "feature_wontfix"` → terminal `phase=complete`. The "archive-internal detector patch" stays intact.
- `claude/statusline.sh:424,442`: `grep '"feature_wontfix"'` substring → `phase=complete`. Bash/Python parity enforced by `tests/test_lifecycle_phase_parity.py`.
- Also (per Adversarial §10): `scan_lifecycle.py` (enumeration-skip + complete→awaiting-merge promotion, :968–989), `clean.py` (archive pin-set, **depth-2** `archive/*/events.log` glob), `overnight/report.py`, dashboard templates, `init/_relocation_migration.py`. All tolerant *readers* — safe **provided the move is atomic and lands at the right depth**.

### Conventions to follow

- Lifecycle CLI module shape: `_build_parser()` → `main(argv=None) -> int`; `_telemetry.log_invocation("cortex-…")` first line (per `branch_mode_cli.py:41`, `dispatch_choice_cli.py`).
- Editing the editable-installed `cortex_command` package → **sequential/trunk dispatch, not worktree** (`just test` runs the editable install; a worktree would verify stale code).
- Commit canonical + regenerated mirror together (drift pre-commit hook); commit via `/cortex-core:commit`.

## Web Research

- **Reserved-verb vs free-form-positional collision** is a recognized hard CLI problem (Cobra issues #610/#498; CLI11 `subcommand_fallthrough` toggle). The durable answer: an **explicit, documented precedence** (git's ordered ref-resolution rules) so the reserved verb deterministically wins, plus a **literal escape** (git's `--`) for a value that collides with a reserved name. A valid alternative mitigation is to *forbid* names colliding with reserved words (GitHub now blocks ambiguous branch/tag names).
- **Order-enforcing destructive ops**: the saga/compensating-transaction rule is "irreversible step **last**, after validations." This reconciles with the ticket's "archive **first**" because here **the archive IS the desired safe end-state**, not an un-undoable side effect — the move is the **pivot transaction**. Correct shape: *all validation before the pivot; the pivot is the state-defining step; every post-pivot step (append, tracker update) is idempotent/resumable* so a crash leaves a safe state and re-running completes the bookkeeping (Azure compensating-transaction guidance; idempotent-command patterns: state-check-before-act, deterministic IDs, no exception-driven idempotency).
- **Byte-stable serialization**: RFC 8785 / canonical JSON exists, but it only helps if you control both sides — if the *existing* rows aren't canonical you must match *their* exact key order/format. The general rule: pin an explicit serializer config (fixed key order, fixed timestamp format, no incidental whitespace) and lock it with a golden round-trip test. (Caveat reinforced by Adversarial §9 below: pinning *bytes* over-constrains when consumers are tolerant.)

## Requirements & Constraints

- **CLAUDE.md — "Prefer structural separation over prose-only enforcement for sequential gates."** Direct mandate for the verb half. *Note the Adversarial §8 tension:* this same principle argues the **parse** half should be structural too, not a prose table.
- **CLAUDE.md — "prescribe What and Why, not How"** and **"resolve `${CLAUDE_SKILL_DIR}` in the body, then propagate"** (SP001/SP002, ADR-0009): a console-script verb sidesteps skill-dir resolution entirely (it's on PATH) — the recommended idiom.
- **CLAUDE.md — MUST-escalation policy**: use soft positive-routing prose for the routing/ordering docs; the *structural* gate is precisely what removes the temptation to escalate to MUST.
- **project.md — Skill-helper modules**: "collapse SKILL.md dispatch ceremony into atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry … `[project.scripts]` console-script entry … New events register in `bin/.events-registry.md`." `cortex-lifecycle-wontfix` is exactly this.
- **project.md — "Destructive operations preserve uncommitted state"**: cleanup scripts removing user-visible artifacts SKIP on uncommitted state; inline destructive sequences extract into named scripts. Architectural support for the verb — *and* a constraint to weigh against fail-forward (Adversarial §1/§3).
- **wontfix is already a canonical `TERMINAL_STATUS`** (`common.py:183`; `normalize_status` maps `wontfix → abandoned`, line 1061). **No vocabulary widening.** `feature_wontfix` is **already registered** (`bin/.events-registry.md:26`).
- **ADR**: the order-enforcing verb **does not clear the ADR three-criteria bar** (one-pattern refactor with precedent) → **back-point to ADR-0004** (the on-point precedent: a multi-step, sequentially-ordered Complete phase citing structural-over-prose). No new ADR.
- **Atomic-append discipline** (`pipeline.md:126`): `fcntl.flock` + tempfile + `os.replace` — the established write discipline (`lifecycle_event.py:_append_event_atomic`).
- **Size/L1**: SKILL.md 183/500 lines; `lifecycle` is in `ROUTING_PRESSURE_CLUSTER` (L1 budget 890) — body edits don't touch L1. No size concern.

## Tradeoffs & Alternatives

### Axis A — the reserved-first-word mechanism in Step 1
- **A1 — reserved-word TABLE** (checked after `#`-strip, before slug-validate; maps each reserved word → route). *Pros*: single locus; it's *data the model applies* not *procedure it narrates*; mirrors the Step 2 route-table; enumerates the shadowing rule explicitly; extensible. *Cons*: still model-applied prose (not a hard gate).
- **A2 — per-word if/elif prose ladder.** *Reject* — reintroduces exactly the check-ordering bug class #329 fixes; the closed set is never enumerated.
- **A3 — dispatch HELPER VERB** (`cortex-lifecycle-parse-args "$ARGUMENTS"` → `{mode,feature,phase}` JSON). *Pros*: genuinely structural + unit-testable; idiomatic (Step 1 already shells to `cortex-resolve-backlog-item`, `cortex-common detect-phase`); permanently kills the ambiguity class. *Cons*: line-36 prose-derivation (summarize intent → kebab slug) is irreducible model judgment a deterministic verb can't own → A3 is a hybrid (verb returns `needs-derivation`, model finishes); adds a module + parity/contract surface.

**Tradeoffs-agent recommendation: A1**, reserved set = {phase tokens} ∪ {resume, wontfix}, with A3 held as the **documented escalation lever**. **Adversarial counter (§8):** the already-shipped-broken `complete <slug>` *is* the evidence artifact that prose first-word parsing is already fragile here — which argues A3 is warranted **now**, not as a deferred lever. → **Open Question OQ-G.**

Two sub-decisions either way: (1) canonical check order; (2) the `wontfix` route is **terminal/short-circuiting** (dispatches and halts, does not fall through to Step 2).

### Axis B — verb invocation site & fate of wontfix.md
- **B1** (Step 1 calls verb directly; wontfix.md gutted/deleted) — *reject a pure delete*: discards irreducible WHEN/WHY (use-case triage, exit-2 handling, R13 detector-belt note).
- **B2 — thinned wontfix.md** (keeps WHEN/WHY prose, replaces the 3 bash HOW-snippets with a single `cortex-lifecycle-wontfix <slug> --reason …` call). **Recommended.** Preserves the situational-reference architecture, honors What/Why-not-How (prose = why/when, verb = how), satisfies parity (verb cited in an in-scope ref), removes B3's dual-source drift.
- **B3** (keep prose substantially + call verb) — *reject*: dual source of truth for the ordering invariant (the exact drift the verb exists to eliminate). The "why git mv first" rationale belongs as a **code comment in the verb**, not the doc.

## Verb Design & Contract Integrity

- **Placement**: `cortex_command/lifecycle/wontfix_cli.py` (per-lifecycle *operation*, belongs in the package with its siblings — `cortex-lifecycle-event` is top-level only because it predates the package and is a pure emitter). Console-script entry as above.
- **Row contract (verified by execution)**: `json.dumps({"ts":…,"event":"feature_wontfix","feature":…,"reason":…})` with **default** separators `(", ", ": ")` and insertion-ordered dict reproduces `wontfix.md:22` byte-for-byte. Timestamp must be **`Z`-suffixed** (`strftime("%Y-%m-%dT%H:%M:%SZ")`) — *not* `lifecycle_event.py`'s `+00:00`. No `schema_version`, no `worktree_path`. No shared JSONL emitter exists (every module rolls its own `json.dumps`).
- **Arg shape**: argparse **positional `slug`** (keeps the contract-lint clean — see Test & Parity) + `--reason` + optional `--backlog-slug`. **Adversarial §12 correction**: pass `--backlog-slug` from the **resolved backlog filename captured earlier in the lifecycle**, not the raw lifecycle slug — the 6-word-capped lifecycle slug often ≠ the backlog stem and may lack `lifecycle_slug:` frontmatter, so `cortex-update-item`'s resolution can fall to title-phrase → exit-2/3 and silently *not* terminalize the backlog item.
- **Structural order**: the three steps as sequential statements in one function, each gated on the prior; **fail-forward, not transactional** (never roll back the move).
- **`cortex-update-item` invocation**: shell-to-console-script (decoupled; preserves exit-2 + backlog-backend routing) **vs** import the library (`resolve_item.resolve()` + `update_item.update_item()`; structured `ResolutionResult.status`, but couples the lifecycle subpackage to backlog). → **Open Question OQ-C.** (Note: `update_item.main()` reads `sys.argv` directly with no `argv` param, so the CLI route must be a subprocess.)
- **Exit codes**: `0` success; **propagate `2`** for ambiguous backlog resolution (and argparse usage errors, per `state_cli.py`); non-zero (`1`) for move/IO failure. Prefix stderr `cortex-lifecycle-wontfix:`. Because order is load-bearing, a non-zero exit *after* the move still leaves the lifecycle archived; document that re-invocation hits the no-op-if-archived path and only retries step (c).

## Routing Parse & Edge Cases

The mechanism must run **after** the `#`-sigil handling and **before** the slug/prose test, and must rebind the resolver/Step-2 target to **word #2** for reserved verbs.

1. **`#`-sigil vs reserved-match**: option (A) strip `#` then match (`#wontfix` routes to the verb — collision accepted); option (B) `#`-prefix = "literal id, suppress reserved-match" (`#wontfix` → feature slug `wontfix`), giving a free degenerate-case escape. The Tradeoffs agent leans (A)/accept-collision; the Routing agent recommends (B). → **Open Question OQ-A.**
2. **Slug-vs-prose**: `wontfix`/`resume`/all phase tokens are valid kebab slugs → they skip prose-derivation and reach feature-parse today. **Confirmed mis-handled**: `lifecycle wontfix add-foo` → `feature="wontfix", phase="add-foo"`. Reserved-match must precede the slug test.
3. **Degenerate case is vacuous**: no `cortex/lifecycle/{wontfix,resume}/` dir and no backlog item literally named `wontfix`/`resume`/phase-token exists. Reserving these words breaks nothing on disk. (OQ-A's option B is the documented ruling-out mechanism the ticket Edge asks for.)
4. **Phase tokens ARE co-victims (confirmed YES)**: `research|specify|plan|implement|review|complete` all parse first-word-as-feature; **`complete <slug>` is already advertised+broken** in `complete.md:72/80/148`. Line 169 (`/cortex-core:lifecycle <phase>` honor-with-warning) documents intent but sits in Step 3 territory, *after* line 34 has already bound `feature=<phase>` — aspirational, not implemented. A **contract contradiction** exists (frontmatter `<feature> [phase]` feature-first vs Invocation/complete.md phase-first). → **Open Question OQ-B.**
5. **Post-recognition targets**: `wontfix <slug>` → invoke the verb, require word #2 (error, don't create a `wontfix` feature, if missing), do not enter Step 2, no-op if already archived. `resume <slug>` → bind word #2 as feature and route into existing Step 2 phase-detection, but **require an existing dir** (report "no such lifecycle", don't silently create — this is `resume`'s value beyond bare `<slug>`). *Adversarial §5 flag*: "require-existing-dir" is a **new behavioral contract** not in the ticket; today `resume foo` is broken-but-tolerated and nothing relies on it (no regression), but it's an authoring decision being introduced.
6. **Resolver/empty-fallback**: reserved recognition happens *before* the `cortex-resolve-backlog-item` call (line 42) and rebinds the resolver target to word #2; the empty-`$ARGUMENTS` incomplete-lifecycle scan (line 50) is unaffected (reserved match lives in the non-empty branch only).

**Canonical parse order**: empty-check → `#`-sigil handling → reserved-word match → slug/prose-derive → resolve & route (except `wontfix`, which terminates at the verb).

## Test & Parity Surface

- **No `bin/` wrapper needed.** The 5 *modern* lifecycle console-scripts (event, branch-mode, dispatch-choice, init-ensure, picker-decision) have **no `bin/cortex-*` wrapper** → console-script-only. (`cortex-lifecycle-state` *does* have one; the Verb Design agent cloned from it — this is the OQ-D contradiction. Lean console-script-only per the modern norm; a wrapper only buys `CORTEX_COMMAND_FORCE_SOURCE` working-tree dogfooding.) → **Open Question OQ-D (low-stakes).**
- **`cortex_command` is wheel-only** — the new module + pyproject change have **no mirror**.
- **Tests to add** (mirror `cortex_command/tests/test_lifecycle_event.py`): order-enforcement (move-first; partial-failure still leaves it archived), the events.log row, the `cortex-update-item` call incl. exit-2, and the exit-code contract. **Adversarial §9**: assert **semantic parse-compatibility** (`json.loads`→`event=="feature_wontfix"` AND matched by the statusline grep patterns), *not* byte-identity — a golden byte test fails spuriously on a legit field-add. → **Open Question OQ-F.**
- **Gates that fire (pre-commit) and what they require**:
  - **SKILL.md-to-bin/console-script parity** (W003 orphan): the `cortex-lifecycle-wontfix` literal in `wontfix.md` is the wiring signal — **no `.parity-exceptions.md` row**. Must ride in the same commit as the `skills/*` edit (pyproject isn't in the trigger pattern).
  - **Contract lint (E101/E103)**: use **argparse with a positional `slug`, no required flags** → contract-clean, no ledger row. (Hand-rolled `sys.argv` → needs a `non-argparse-module` row.)
  - **Events registry**: **no change gate-required** (the gate only fails on *unregistered* literals). Hygiene: update the producers column / optionally flip `scan_coverage` to `manual`.
  - **Mirror/dual-source drift** (`test_dual_source_reference_parity.py` byte-compares every `SKILL.md` + `references/*.md` vs mirror): run `just build-plugin`, stage **both** `SKILL.md` and `wontfix.md` mirrors in the same commit.
  - **Kept-pauses parity**: fires only if a new `AskUserQuestion` is added under `skills/lifecycle/` or `skills/refine/`. wontfix/resume routing stays non-interactive → **no change**. (The exit-2 ambiguity is a halt-and-surface, not a pause.)
  - **Backlog `grep -c`**: `grep -c "feature_wontfix"` resolves (registered token). Avoid inventing new shape-matching event tokens.

## Adversarial Review (highest-leverage challenges, several empirically verified)

1. **`git mv` hard-fails on fully-untracked lifecycle dirs** (verified: `fatal: source directory is empty`, exit 128, not moved) — the dominant wontfix case (premise rejected before any commit). Move-first + fail-forward then yields **zero** primary outcome. The archive-skip is **name-based** (`scan_lifecycle.py:907`), so `os.rename` (fallback `shutil.move`) achieves the identical enumeration-drop, works on untracked dirs, and is atomic (same-fs). The verb performs no commit, so staging the rename is moot. → **recommend `os.rename` over `git mv` (contradicts the ticket; OQ-E).**
2. **`git mv` silently NESTS into an existing destination** (verified: exit 0 → `archive/foo/foo/`), invisible to `clean.py`'s depth-2 glob. The **4-case pre-flight existence guard is mandatory** regardless of primitive (`shutil.move` also nests; only `os.rename` errors cleanly).
3. **Concurrent-session zombie resurrection**: `lifecycle_event.py:88` `mkdir(exist_ok=True)` — a concurrent session writing to the *active* path after the move recreates the dir (reappears as `phase=research`, no marker). Low probability; mitigate with a `.session`-liveness check before archiving, or accept-and-document.
4. **Worktree root-resolution hazard**: `_resolve_user_project_root()` stops at the first `.git` (= worktree root); `_resolve_user_project_root_from_cwd()` follows CWD. Lifecycle dirs are **main-resident** — the verb must anchor to the **canonical main root**, or guard the worktree-invocation case loudly.
5. **Path traversal**: the standalone console-script bypasses SKILL.md's kebab regex; a direct-caller `slug` with `/` or `..` escapes `cortex/lifecycle/`. **Validate the slug against `^[a-z0-9]+(-[a-z0-9]+)*$` inside the verb.**
6. **"Don't reuse `log_event`" overcorrects**: the only real blocker is the hardcoded non-archive path (extra fields + separators are tolerated). **Parametrize `_append_event_atomic` with an archive-aware path and reuse the flock/tempfile/`os.replace` atomicity** — don't hand-roll `printf >>` (loses atomicity).
7. **Byte-identity is the wrong test contract** (consumers tolerant) — assert semantic compatibility (OQ-F).
8. **Structural-over-prose self-deception**: the verb half is structural; the routing half stays prose. The already-broken `complete <slug>` contract is evidence the prose first-word parse already drifted — argues for structuralizing the parse (A3) now (OQ-G).
9. **Solution-Horizon half-fix**: **three** advertised-broken forms (`wontfix`, `resume`, `complete <slug>`). Shipping the first two while leaving `complete <slug>` re-creates the identical bug one token over — either absorb the phase tokens now or file an explicit cross-linked sibling ticket; don't ship silent (OQ-B).

## Open Questions

Resolutions recorded at the Research Exit Gate (2026-06-29) are inline below; remaining `(design — Spec)` forks are deferred to the structured spec interview with rationale.

- **OQ-B — phase-token co-victims / `complete <slug>` — RESOLVED (user, Exit Gate).** Scope = the **three slug-taking verbs** fully wired (`wontfix`, `resume`, `complete <slug>`), and the structural parser **recognizes the full grammar incl. the bare phase tokens** so the drift-guard test is complete and bare `plan`/`review` stop silently creating phantom lifecycles (minimal non-broken fallback: error asking for a feature). **Deferred** to a cross-linked sibling ticket: the bare-phase-token "active feature" *routing behavior* (needs an active-feature concept that doesn't exist yet). Rationale: fixes every currently-broken *advertised* command (Solution Horizon — `complete <slug>` is a named live-broken site), immunizes against recurrence, stops short of the active-feature redesign. User framed it as "localized brittleness, not system rot."
- **OQ-G — parse mechanism — RESOLVED (user, Exit Gate): A3, the structural `cortex-lifecycle-parse-args` helper.** Plus a **drift-guard test** asserting every advertised invocation form (frontmatter `argument-hint` + Invocation block + `complete.md`) parses correctly — this is the recurrence-prevention piece and the durable core of the fix. The only residual prose is the irreducible prose→slug derivation (helper returns `needs-derivation`, model finishes).
- **OQ-E — archive move — RESOLVED (Exit Gate): `os.rename` (fallback `shutil.move`), overriding the ticket's `git mv`.** Empirical: `git mv` hard-fails (exit 128) on untracked lifecycle dirs (the dominant wontfix case) and silently nests into existing destinations; the archive-skip is name-based so git-tracking is irrelevant. The 4-case pre-flight existence guard remains mandatory regardless of primitive.
- **OQ-F — test contract (design — Spec; nuances ticket).** The ticket says "byte-identical"; consumers are tolerant. Recommend asserting **semantic** parse-compatibility (`json.loads`→`event=="feature_wontfix"` AND matched by the statusline grep patterns), optionally keeping a current-row regression check, rather than a brittle byte-golden that fails on a legit field-add.
- **OQ-A — `#`-sigil semantics (design — Spec).** Literal-slug escape that suppresses reserved-match (Routing agent) vs accept-the-collision/strip-then-match (Tradeoffs agent). The escape doubles as the degenerate-case ruling-out the ticket Edge requests. (Note: with A3, this lives in the parser and is unit-testable either way.)
- **OQ-C — `cortex-update-item` step: shell-out vs import the library (design — Spec).** Decoupling vs structured error handling.
- **OQ-D — `bin/` wrapper vs console-script-only (design — Spec; low-stakes).** Lean console-script-only per the 5 modern precedents; a wrapper only adds `CORTEX_COMMAND_FORCE_SOURCE` working-tree dogfooding.

**Folded-in design requirements (not open — corrections to carry into Spec):** validate the slug inside the verb (path traversal); anchor to the canonical main root; reuse the atomic flock-append with an archive-aware path; mandatory 4-case pre-flight existence guard; pass `--backlog-slug` from the resolved backlog filename; `resume` require-existing-dir is a deliberate new contract to state explicitly; fix the stale `scan_lifecycle.sh:227` citation and the stale "line-183 removed" claim; thin `wontfix.md` (B2); back-point ADR-0004; regen both skill mirrors in the offload commit.
