# Research: Offload lifecycle Step 2 backlog write-back + index.md creation into CLI verbs (#326)

**Backlog:** #326 (parent epic #336 "Offload deterministic lifecycle mechanics to CLI verbs") · **Tier:** complex · **Criticality:** high

**Clarified intent:** Offload lifecycle Step 2's *remaining* deterministic mechanics — the `cortex-update-item` backlog write-backs (in_progress / lifecycle-slug / close-lifecycle-complete) with their three-arm backend routing and exit-2 handling, plus `index.md` creation/templating (hand-narrated in `discovery-bootstrap.md`) — into `cortex-lifecycle-*` verbs, so the skill issues unconditional commands while routing/templating/exit-handling live in code.

## Epic Reference

Epic #336 ("Offload deterministic lifecycle mechanics to CLI verbs") sets the build order and shared discipline. **#326's foundational siblings have all landed since this ticket was filed:** #330 (`cortex-lifecycle-event` gained `--set`/`--set-json`; migrated `backlog-writeback.md`/`refine-delegation.md` event sites), #331 (`cortex-lifecycle-stage-artifacts` + `cortex-lifecycle-complete-route`), #329 (`cortex-lifecycle-parse-args` + structural Step-1 routing), and #322 (refine Step-2 offload; **established ADR-0019** on verb backend handling). #326 is the last child and sits atop all of this — it should *reuse* these, not re-derive. The epic's shared discipline: **pin the byte-identical-output invariant** so consolidation cannot silently change behavior, and **reuse the resolve-once backend routing** rather than re-deriving it per child.

---

## Scope: what #330 already did vs. what remains for #326

**ALREADY DONE by #330 — do NOT re-touch event emission.** The `feature_complete` close-path emission in `skills/lifecycle/references/backlog-writeback.md:34-36` is already migrated from raw NDJSON to `cortex-lifecycle-event log --event feature_complete --feature <name>`, and is golden-pinned by `tests/test_lifecycle_event_roundtrip.py` (`FILE_EVENTS["…/backlog-writeback.md"] = {"feature_complete": 1}` + a `feature_complete` GOLDEN case + the `scan_lifecycle.py` substring-needle test). `feature_complete` is also a detect-phase event (`cortex_command/common.py`). **#326 adds no new events.**

**Still hand-narrated → in scope for #326** (in `backlog-writeback.md` + `discovery-bootstrap.md`):
1. The three `cortex-update-item` write-backs, each wrapped in the three-arm backend routing (`cortex-backlog`/`none`/external) + exit-2 handling:
   - close path (`phase != none`): `cortex-update-item <slug> --status complete --lifecycle-phase complete --session-id null`
   - lifecycle-start: `cortex-update-item <path> --status in_progress --session-id $LIFECYCLE_SESSION_ID --lifecycle-phase research` (runs on all proceed phases)
   - lifecycle-slug (`phase == none` only): `cortex-update-item <path> --lifecycle-slug {lifecycle-slug}`
   - **(Codebase correction)** Step-2 sites use ONLY these four flags (`--status`, `--session-id`, `--lifecycle-phase`, `--lifecycle-slug`). The `--complexity`/`--criticality`/`--areas`/`--spec` flags exist on `cortex-update-item` but are written by *refine* (#322), not lifecycle Step 2.
2. The "Backend routing (resolve once)" block + per-call inline routing prose.
3. The `cortex-update-item` exit-2 canonical block.
4. `index.md` creation + 7-field templating (`discovery-bootstrap.md`) and the canonical artifact-registration recipe (`backlog-writeback.md:76-85`).

**Stays prose (ticket's "do NOT offload" residuals, confirmed):** the external-tracker backend arm (verb emits a `needs_agent: <intent>` signal; prose composes the `gh issue` best-effort), the Close/Continue `AskUserQuestion` *presentation* (a registered kept-pause; a verb cannot call `AskUserQuestion`), and discovery-bootstrap's epic-context What/Why guidance.

## Codebase Analysis

**Files that will change:**
- **New** `cortex_command/lifecycle/start_sync.py` — the backend-routed `cortex-update-item` write-backs + close branch + exit-2.
- **New** `cortex_command/lifecycle/create_index.py` (dedicated; NOT an `init_ensure` fold — see Tradeoffs) — the `index.md` template + skip-if-exists guard + (optionally) artifact-registration.
- `pyproject.toml` `[project.scripts]` — one `cortex-lifecycle-<name> = "cortex_command.lifecycle.<module>:main"` line per verb (alphabetized in the `cortex-lifecycle-*` block).
- `skills/lifecycle/references/backlog-writeback.md` + `discovery-bootstrap.md` — replace the deterministic blocks with verb invocations; keep the residual prose.
- `skills/lifecycle/SKILL.md` Step 2 (the Backlog Status/index.md/Write-Back ordering block, ~lines 110-121).
- **Mirrors:** `plugins/cortex-core/skills/lifecycle/{SKILL.md,references/*}` regenerate via `just build-plugin`. **`cortex_command/*.py` is NOT mirrored** (it ships in the wheel; console-script registration is all that's needed). Drift pre-commit hook requires canonical skill prose + regenerated mirror committed together.
- New tests (see Precedent-Pattern test template).

**Integration points / key data gap:** the `cortex-resolve-backlog-item` stdout JSON (`resolve_item.py` `_build_json`) exposes only `filename`, `backlog_filename_slug`, `title`, `lifecycle_slug` — **NOT** `uuid` or `tags`. The index verb needs `uuid`, `tags`, `title`, and the filename-derived `NNN`+`slug`, so it must **re-parse the resolved backlog file's frontmatter** (the `stage_artifacts._resolve_backlog_filename` → `resolve_item._parse_frontmatter` pattern), rather than widening the resolver's closed-set JSON.

**Resolver-divergence note (verified, partially unavoidable):** `update_item`/`resolve_item`/`backlog_backend_cli`/`wontfix_cli` use `_resolve_user_project_root()` (honors `CORTEX_REPO_ROOT`); `lifecycle_event`/`complete_route`/`stage_artifacts` use `_resolve_user_project_root_from_cwd()` (worktree-aware, ignores `CORTEX_REPO_ROOT`). Passing the Step-1-resolved backlog path *into* the write-back verb fixes the backlog read, but the `index.md` write and any `log_event` append still resolve a root independently. Under overnight (`CORTEX_REPO_ROOT` set, CWD differs) the close path already splits today — this is **pre-existing**, to be documented, not claimed "solved."

## Web Research

- **Idempotency = desired-state, not command-sequence.** Each step a skip-if-exists guard; a second run is a same-result no-op. Resumable multi-step mutation = atomic phases + recovery points (Brandur/Stripe): never perform an irreversible action without first persisting that you're about to attempt it. → maps onto branch-on-disk-state write-backs.
- **Atomic file writes** (the load-bearing primitive): write a temp file in the same dir, `fsync`, `os.replace` (atomic rename). Never write the target in place.
- **PyYAML is NOT byte-stable**: `safe_dump` sorts keys (need `sort_keys=False`), defaults to block arrays (inline needs forced flow), quotes dates, can't round-trip comments/order. For byte-exact frontmatter use a **deterministic string template + golden-file test**, and pin the trailing newline. (Empirically confirmed by the index.md angle.)
- **"Don't make the model do deterministic work"** (Anthropic *Building effective agents* — workflows have predefined control flow in code; agents put the LLM in charge): the textbook justification for #326. Counter-consideration: Claude Code deliberately leaves many nudges prompt-based because models follow instructions well; offload when the step is *truly deterministic and correctness-critical*, keep prose when it's judgment/low-cost-of-deviation.
- **The sentinel-exit-code → caller-prompts-human → re-invoke-with-decision pattern** is established prior art (Brandur "Command exit status"; HITL three-state approve/reject/pending flags; git plumbing-vs-porcelain). The verb is plumbing (stable machine-parseable contract, sentinel exit codes); the interactive skill is porcelain (does the human prompting). **Consolidation guidance** (Anthropic tool-writing): prefer one verb that does the discrete operations internally over several primitives the agent must orchestrate.

## Requirements & Constraints

- **Authoring shape (project.md "Skill-helper modules"):** collapse SKILL.md dispatch ceremony into atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry; expose a `[project.scripts]` console-script. Mirror the landed #330/#331/#329 verbs.
- **Backend handling — ADR-0019 (governing):** the skill resolves the backend once via `cortex-read-backlog-backend` and passes `--backend`; the verb acts on the caller-passed value as a **structural guard only** and must **NOT self-resolve** the backend (#322's "self-resolve" phrasing was explicitly rejected). The external-tracker adapter logic stays skill-side (LLM best-effort per `backlog.instructions`). **The overnight fail-closed backend guard must not be touched or DRY-merged** with the interactive fail-open reader.
- **Hard invariants to pin:** byte-identical `feature_complete` row on the `cortex-backlog` arm (already #330's, leave intact); exact `cortex-update-item` flag sets; `index.md` 7-field frontmatter + inline `artifacts: []` + bare-`null` fields + parseable inline `tags`; skip-if-exists guard; both `phase=none`/`phase!=none` close paths; resolver exit-3 silent-skip; exit-2 candidate-surfacing.
- **Gates most likely to bite:**
  - `cortex-check-contract` (E101 missing required flag / E102 unknown flag / E103 missing subcommand) **AST-validates every `cortex-*` prose invocation** — the new verbs' invocations in thinned prose must carry all `required=True` flags + a valid subcommand (placeholders allowed) or get ledger exceptions.
  - `cortex-check-parity` W003 (console-script must be referenced from an in-scope file — the edited reference markdown satisfies it).
  - the dual-source **mirror drift hook** (regenerate + stage `plugins/cortex-core/skills/lifecycle/` via `just build-plugin` in the same commit).
  - `cortex-check-events-registry` — only fires if an `--event` emission is added/moved; #326 adds none, so this should stay quiet (confirm).
  - `tests/test_lifecycle_kept_pauses_parity.py` — string-matches the literal `AskUserQuestion` token (±~35-line tolerance) at the kept-pause anchor; keep the token in the thinned `backlog-writeback.md` and update the `kept-pauses.md` line reference together.

## Precedent-Pattern Analysis (#330/#331/#329/#322)

The landed siblings give a copy-ready template; **clone `cortex_command/lifecycle/stage_artifacts.py`'s shape** (a write-side verb), borrowing from `wontfix_cli.py` (the shell-to-`cortex-update-item` + exit-2 pattern) and `complete_route.py` (the re-entry seam).

- **Module skeleton:** `from __future__ import annotations`; pure helpers + a thin `main(argv: Optional[list[str]] = None) -> int` that builds the parser, resolves root in `try/except CortexProjectRootError` (stderr + `return 1`), calls the pure engine, and serializes **compact JSON** `json.dumps(result, separators=(",", ":")) + "\n"`. `if __name__ == "__main__": sys.exit(main())`.
- **Exit codes:** `0` success/no-op; `1` usage error / unresolvable project root; `2` user-correctable gate failure — the exit-2 ambiguous-slug passthrough from a downstream `cortex-update-item` (re-emit candidate stderr, `return 2`), exactly `wontfix_cli`'s `WontfixError(2, …)`. All `gh`/git side-effects degrade to a valid exit-0 verdict, never a traceback.
- **Backlog resolution:** `_resolve_backlog_filename(slug, root)` → `cortex_command.backlog.resolve_item.resolve(slug, backlog_dir)`; `None` on not-found/ambiguous → silent skip (matches resolver exit-3 semantics).
- **Backend routing:** branch on the **caller-passed `--backend`** (ADR-0019), not an in-verb `resolve_backlog_backend()` call.
- **Event emission:** in-process verbs call `cortex_command.lifecycle_event.log_event(event, feature, fields=None)` directly (the `wontfix_cli` precedent imports `_append_event_atomic`); but see Adversarial #1 — for #326 the cleanest is to **leave the close-path `feature_complete` emission as the existing prose `cortex-lifecycle-event log` call** and NOT fold it into the write-back verb.
- **Packaging:** console-script ONLY — **no `bin/` wrapper, no `bin/` mirror** (the newer-verb pattern; the legacy `bin/` dual-channel wrapper exists only for `cortex-lifecycle-state`/`-counters`). `cortex_command/*.py` ships in the wheel, not mirrored. Add `_telemetry.log_invocation("cortex-…")` as the first line of `main` (backlog-mutating-verb precedent).
- **Tests — copy BOTH arms:**
  - *Real-git round-trip* (`tests/test_stage_artifacts.py`): throwaway repo with pinned identity; assert the live git/disk state **==** the verb's self-reported JSON **==** a hardcoded expected set ("neither assertion trusts the other"); drive `main([...])` under `monkeypatch.delenv("CORTEX_REPO_ROOT")` + `chdir` + `capsys`; CLI-contract byte assertions (`out.endswith("\n")`, single line, `", " not in out and ": " not in out`, exact key set); **negative controls** that witness the defect not the fixture.
  - *Golden-byte emission* (`tests/test_lifecycle_event_roundtrip.py`): fixed-timestamp / fixed-date seam monkeypatched, `assert line == golden` against an inline byte string.
- **Prose→verb migration pattern:** mechanism moves to code; triage/affordance/why stays prose (wontfix kept WHEN/WHY + exit-2 pointer; complete kept the `orphan_ambiguous` user-pick; Step-1 kept the `needs-derivation` prose). For #326: thin the routing/write-back/template blocks; keep the `AskUserQuestion`, the external-tracker arm, the "don't copy epic content" guidance, and the "consume Step 1's result, never re-scan" invariant.

## Verb-Shape & Re-entry Contract

**Step-2 branch enumeration** (the surface being offloaded):

| Input | Behavior | Interactive? | Deterministic? |
|---|---|---|---|
| B0 resolver exit-3 | skip status check; fall through (write-back also silent-skips) | no | yes |
| B1 match, `status != complete` | skip; fall through | no | yes |
| B2 match, `status == complete` | `AskUserQuestion` {Close/Continue}; if AUQ unavailable → **default Continue, never auto-close** | **YES (the one pause)** | choice no; classification yes |
| B2-Continue | fall through (→ index.md → in_progress write-back) | no | yes |
| B2-Close, `phase != none` | (1) `feature_complete` event [stays prose]; (2) `cortex-update-item --status complete …`; (3) **exit immediately** | no | yes |
| B2-Close, `phase == none` | **exit immediately, create nothing** | no | yes |

**Re-entry precedent:** `complete_route.py`'s `orphan_ambiguous` route (verb classifies → no side effect → prose owns the `AskUserQuestion` → skill writes the chosen side-effect → re-runs the verb) is the canonical verb↔skill seam, consumed at `complete.md`.

**Recommended write-back verb contract (`apply` subcommand):**
```
cortex-lifecycle-start-sync apply --on-complete {close|continue} \
    --backend <resolved> --backlog-file <path|""> --phase <none|…> \
    --session-id "$LIFECYCLE_SESSION_ID" --lifecycle-slug <slug>
```
- `--on-complete close`, `phase != none`: backend-gated `cortex-update-item <slug> --status complete --lifecycle-phase complete --session-id null`; emit `{"route":"closed","terminal":true,…,"needs_agent":null}`.
- `--on-complete close`, `phase == none`: no-op (create nothing); `terminal:true`.
- `--on-complete continue` (≡ the B0/B1 proceed path): backend-gated `--status in_progress …`; when `phase==none` additionally `--lifecycle-slug`; exit-3/`--backlog-file ""` → silent skip. Emit `{"route":"started","terminal":false,…}`.
- The skill acts on `terminal:true` to honor "exit immediately" (do not advance to index/init-ensure/Discovery Bootstrap/Step 3).

**Whether to also ship a `status-check` read subcommand is contested** — the Verb-Shape angle proposed it; the Adversarial angle argues to drop it (see Open Questions #1).

## index.md Templating & Byte-Identity

**The exact creation template** (`discovery-bootstrap.md:13-37`, verified against on-disk files):

Shape A (backlog match):
```
---
feature: {lifecycle-slug}
parent_backlog_uuid: {uuid|null}
parent_backlog_id: {NNN-as-int|null}
artifacts: []
tags: [{inline, comma-space}]   # or `[]`
created: {YYYY-MM-DD}
updated: {YYYY-MM-DD}
---

# [[{full-stem}|{title}]]

Feature lifecycle for [[{full-stem}]].
```
Shape B (resolver exit-3): same frontmatter with `parent_backlog_uuid: null`, `parent_backlog_id: null`, `tags: []`; **no heading/body** (blank line after the closing fence).

**Construction rules:** 7 fixed-order fields; `parent_backlog_id` unquoted int; `artifacts: []` always inline-flow at creation; **bare unquoted `null`** (NOT `"null"` — `wontfix_cli._frontmatter_value` matches `^key:\s*(\S+)` and treats `"null"`-with-quotes as a real target); dates unquoted; wikilink uses the **full filename stem** (prefix+slug) on both sides; `title` must be **unquoted** from frontmatter (the #326 ticket's own `title:` is single-quoted and contains `+`, `#`, parens).

**Templating approach:** manual f-string assembly (PyYAML empirically unusable — no flag combo yields ordered-block-doc + inline-unquoted-arrays + unquoted-dates + bare-`null`); atomic write (temp + `os.replace`); **structural skip-if-exists guard**; **injectable `_today()` seam** so the golden-date test isn't flaky (mirror `lifecycle_event._now_iso`).

**Byte-identity is narrower than "byte-identical or downstream breaks" (Adversarial #9, verified):** `detect-phase` reads events.log + artifact `.md` files (NOT index.md); `scan_lifecycle.py` reads `cortex/backlog/index.json` (NOT lifecycle index.md); statusline reads neither. The **only** programmatic index.md readers are `wontfix_cli` (`parent_backlog_uuid`/`parent_backlog_id` via tolerant regex) and `load_requirements_cli` (`tags` via `_extract_tags`, tolerant of quoting/block). So the genuine constraints are the bare-`null` lines and a `_extract_tags`-parseable inline `tags`; the on-disk corpus is itself non-canonical (≈184 quoted / 111 unquoted / 3 block `artifacts` across 298 files). Frame the target as a **canonical creation form + golden regression guard**, not "matching legacy files."

**Artifact-registration** (`backlog-writeback.md:76-85`) is the *append* path used by later phases (`plan.md`, `review.md` point at it) — currently 100% prose, no code owns index.md content. It's out of #326's *creation* scope but lives in the same file; preserve/relocate+re-point it (Adversarial #3). The same verb *could* own a `--register` mode so the byte template lives in one place (Open Questions #2).

## Tradeoffs & Alternatives

- **(A) one god-verb** owning status + write-backs + index + close: best token win, worst maintainability (mode-matrix tests, fuses orthogonal backend-routed-mutation and pure-FS-templating concerns) — cuts against the single-purpose family grain.
- **(B) two single-purpose verbs** (write-back verb + dedicated index verb): best maintainability (each invariant gets an isolated golden test), matches the wontfix/stage-artifacts/emit-lifecycle-start grain. **Recommended.**
- **(C) minimal** (offload only the non-interactive write-backs, keep status+close+index as prose): lowest risk but leaves the highest-leverage offload (the error-prone index template) in prose — under-delivers on the audit's stated value.

**index.md home — reject the `init-ensure` fold (decisive grounds, re-grounded per Adversarial #12):** the *primary* reasons are **feature-blindness** (`init_ensure.main` is argless, builds a fixed `Namespace`, cannot know which feature) and **separation-of-concerns** (it bootstraps repo-level `cortex/` scaffolding; feature templating is a different job). The ticket's secondary objections (worktree-refusal R11; 2-of-4→last reordering) are **weak** — index creation only happens at `phase=none` which is always on main (R11 won't fire), and nothing in sub-procs 3-4 reads index.md (reorder is tidiness, not correctness). **The plan must state plainly that it overrides the ticket author's explicit "fold into init-ensure" Role suggestion, citing feature-blindness.**

**Offload/keep boundary:** the ticket's three residuals are directionally right. Refinements: the external arm should emit a *typed* `needs_agent` signal (not re-derive "are we external" in prose); the Close/Continue prompt is a confirmed kept-pause; and discovery-bootstrap's mechanical "Epic Research Detection" pseudo-code (read `discovery_source`/`research` frontmatter → stat file) *could* fold into the index verb's JSON output, while the "don't copy epic content" What/Why stays prose (lower-value; optional).

## Adversarial Review

Verified findings that materially shape the spec (file:line where confirmed):
- **#1 — event-emission contradiction.** Folding `feature_complete` into the write-back verb (and deleting the prose line) breaks `tests/test_lifecycle_event_roundtrip.py:152-154` (`FILE_EVENTS` expects exactly one on-disk `cortex-lifecycle-event log --event feature_complete` in `backlog-writeback.md`). **Decide explicitly:** keep the prose verb-call (recommended — honors "do not re-touch event emission"), OR drop the `FILE_EVENTS` entry.
- **#2 — close-path partial-failure ordering.** Status Check keys off the *backlog* `status` field, not events.log. Event-first-then-crash leaves an orphaned `feature_complete` with `status != complete`; a re-run proceeds and writes `in_progress`, contradicting the event. **Fix:** do the backlog `--status complete` write FIRST (self-healing re-detect), OR have status detection also read events.log `feature_complete` (the `complete_route.classify` approach). Idempotent-guarding only the event append is insufficient.
- **#3 — three live cross-refs into the thinned prose:** `complete.md:133` → exit-2 canonical (`backlog-writeback.md:72-74`); `plan.md:250` + `review.md:130` → artifact-registration recipe (`:76-85`); `complete.md:137` → "Step 9 write-back already backend-gated." Preserve/relocate these blocks and re-point the references.
- **#4 — `cortex-check-contract`** AST-validates the new verbs' prose invocations (required flags + subcommand) — satisfy or add ledger exceptions.
- **#5 — `wontfix_cli` bare-`null` coupling** (see index.md section): emit bare `null`, never `"null"`.
- **#6 — missed consumer `load_requirements_cli`** reads index.md `tags`; the synthesis's original consumer list was wrong on 3 of 4.
- **#10 — drop `status-check` verb (over-engineering).** It wraps a single `status == complete` comparison the skill already holds from Step-1's parsed frontmatter, and cannot compute `needs_prompt` (depends on AUQ availability, which only the skill knows). "Is this done? ask the user" is What/Why judgment, not mechanics — keep it in prose adjacent to its kept-pause. Ship `apply` + index verb only. ("Complexity must earn its place.")
- **#13/#14 — honesty about claims:** the resolver divergence is only half-sidestepped (document the residual events/index vs backlog root split as pre-existing); `terminal:true` is a *prose-consumed* gate (the index verb can't self-defend on `phase==none` close), so don't call it "structural" — though the `complete_route` precedent makes prose-consumption defensible.
- **#15 — backend ordering + event unconditionality:** resolve `--backend` once at Step-2 *entry* (the close path runs first); the close-path **event append is UNCONDITIONAL** (`backlog-writeback.md:34` is not backend-gated; only the `:38-42` update-item is) — if `apply` routes the *whole* close path on `--backend` it wrongly skips the event on `none`/external. Pin: event always; only the backlog write is routed.
- **#16 — exit-2 partially vestigial:** passing the resolved filename in makes `cortex-update-item` re-resolution unambiguous, so its exit-2 is unreachable from `apply` (keep as defensive dead-code-with-test, or note unreachable) — but `complete.md:133` still needs the exit-2 *canonical* for its own un-pre-resolved Step-9 call.
- **Minor accuracy fixes:** `emit-lifecycle-start` is a `cortex-refine` *subcommand* (`refine.py`), not a standalone console script; index.md corpus counts are ≈184/111/3, not 71/44/3.

## Open Questions

These are spec-shaping design decisions. Each is **deferred to the Spec interview** with rationale (the Spec §4 complexity/value gate and the user are the right place to settle scope/decomposition for a `priority: low` chore that the adversarial pass showed can be drawn at several scope lines).

1. **Ship `status-check` as a read subcommand, or keep the status comparison in prose?** Verb-Shape proposed `status-check`; Adversarial argues it's over-engineering (single field comparison the skill already has; can't compute `needs_prompt`). *Deferred to Spec — leaning: drop it; ship `apply` + index verb only.*
2. **One verb with subcommands/modes, or two separate verbs** (`start-sync` write-back + `create-index`)? And should the index verb also own the `--register` append path so index.md byte-handling lives in one module? *Deferred to Spec — leaning: two verbs (Approach B); fold registration into the index verb.*
3. **Close-path scope + ordering.** Does `apply --on-complete close` own the `cortex-update-item --status complete` write only (leaving the `feature_complete` event as the existing #330 prose line), and in what order relative to the event, to avoid the partial-failure inconsistency (Adversarial #2)? *Deferred to Spec — leaning: keep the event in prose; `apply` does the backlog write; pin backlog-write-first OR add events.log to status detection.*
4. **`feature_complete` fold vs leave (Adversarial #1).** Confirm the event emission is NOT folded into the verb (keep the `FILE_EVENTS` golden valid). *Deferred to Spec — leaning: leave in prose.*
5. **How much of discovery-bootstrap's "Epic Research Detection" to offload** into the index verb's JSON output (mechanical) vs keep as prose (the What/Why). *Deferred to Spec — leaning: optional/out-of-scope for #326; keep prose to bound blast radius.*

None of these block the Spec phase — each has a stated leaning and is a scope/decomposition choice the Spec interview resolves with the user.

## Considerations Addressed

- **Reuse the resolve-once backend routing per epic #336:** Addressed — the governing convention is ADR-0019 (skill resolves once via `cortex-read-backlog-backend`, passes `--backend`; verb structural-guards on the passed value, does NOT self-resolve). The overnight fail-closed guard must stay separate.
- **Mirror the just-landed #330/#331/#329/#322 verb patterns:** Addressed — clone `stage_artifacts.py`'s module skeleton; `wontfix_cli.py` for the shell-to-`cortex-update-item` + exit-2 pattern; `complete_route.py` for the re-entry seam; console-script-only packaging (no `bin/` wrapper/mirror); the two-arm byte-identity test template.
- **Pin the byte-identical-output invariant (events.log rows, index.md, cortex-update-item flag sets):** Addressed and *refined* — the `feature_complete` row is already #330's (leave intact); the genuine index.md constraints are bare-`null` lines + parseable inline `tags` (framed as canonical-creation-form + golden guard, since almost no consumer reads index.md); pin the exact four-flag `cortex-update-item` sets via argv-assertion tests with negative controls.
