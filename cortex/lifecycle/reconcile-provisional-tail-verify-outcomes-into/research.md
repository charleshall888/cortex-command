# Research: Reconcile #359 + #360 provisional-tail verdicts into master_candidates.json (key on file,id)

**Scope anchor (from Clarify):** Fold *only* the two remaining #357 provisional-tail children — #359 (discovery + backlog-author) and #360 (critical-review) — into `cortex/research/skill-value-scorecard/master_candidates.json` as composite-`(file,id)`-keyed `status` entries, setting `applied_in_commit` only on the newly-folded rows. **Out of scope** (separate tracked debt): the ~89-row global backfill of pre-existing orphaned `verified_survives` rows (incl. #353's), and re-location of the #340 s9 / #186 s3 drifted line anchors (owned by those tickets). #358 and #361 are already discharged (#361 via sibling #366, commit `16cc9429`).

**Complexity/criticality:** complex / medium. It mutates a hand-maintained audit/research ledger (no runtime consumers), but a mis-key silently corrupts audit provenance, so correctness of the keying/parsing is the real risk — not blast radius.

---

## Codebase Analysis

**Target file:** `cortex/research/skill-value-scorecard/master_candidates.json` — a flat JSON **list** of 265 objects. `(file, id)` is unique across all rows (0 duplicate composite keys); bare `id` is not (`s3` recurs 31×). This is the only file a reconciler must write.

**No reconciler code exists.** Searches of `bin/`, `cortex_command/`, `tests/` for `master_candidates` return zero hits. Both prior folds were one-off inline JSON edits during a lifecycle's commit step:
- **#358** (`635af70c`, "Direct-write #358 verify outcomes to ledger") — *rich* write shape: set `status`, bumped `votes` 0→1 and `survive_votes` 0→1, appended a structured `verdict_summaries` entry, set `applied_in_commit` to a **short-SHA**.
- **#361 / #366** (`16cc9429`, "Reconcile #361 verify-outcomes into master_candidates ledger") — *minimal* write shape: flipped `status` only, added `applied_in_commit` as a **commit subject-line string**, left `votes`/`survive_votes`/`verdict_summaries` untouched (still `0`/`0`/`[]`). Commit message states verbatim: *"applied_in_commit subject strings, ledger convention."* This superseded #358's shape and is what the direct sibling used.

**Schema.** Object keys: `id, heading, start_line, end_line, tokens, weighted_cost, value, category, claim, pins, file, slug, status, votes, survive_votes, needs_user_input, verdict_summaries, mech_pins, mech_pin_count`, plus optional `applied_in_commit` (77/265), `overlaps_ticket` (13/265), `reproposal_of` (11/265). `status ∈ {unverified, verified_survives, verified_refuted}` (90 / 166 / 9 at snapshot). `applied_in_commit` never appears on `verified_refuted` rows.

**Serialization (pinned by byte-exact round-trip):** `json.dumps(data, indent=1, ensure_ascii=True)` reproduces the file — **with NO trailing newline** after the closing `]`. Non-ASCII is `\uXXXX`-escaped. Read → mutate rows in place → write with these exact params for a minimal diff.

**Conventions to follow:** key strictly on composite `(file, id)`; only touch rows where `status == "unverified"`; for `verified_survives` set `status` + `applied_in_commit` (subject-string); for `verified_refuted` set `status` only; leave the vote/summary fields untouched (minimal shape).

## Requirements & Constraints

- **No ADR or requirements doc governs `cortex/research/` or the skill-value-scorecard lineage.** Governance is entirely the ticket chain (#357 umbrella → #358–#361 children → #363/#366 reconcilers) plus commit precedent. An ADR is **not** warranted (this repeats precedent; no novel rejected-alternative trade-off, per `cortex/adr/README.md`'s three-criteria gate).
- **Skill-helper-module constraint** (`project.md`) fires only for *a SKILL.md dispatch ceremony that invites paraphrase*. This reconciliation is not invoked by any skill, so it does **not** oblige a promoted `cortex_command/<skill>.py` module.
- **A committed `cortex-*` verb would trigger obligations:** SKILL.md-to-bin **parity** (W003 orphan unless wired into an in-scope file or `bin/.parity-exceptions.md`), `[project.scripts]` console-script, `bin/.events-registry.md` registration, and tests. A throwaway/uncommitted script triggers none — matching what #358 and #361 actually did.
- **grep-c gate caveat** (`tests/test_backlog_grep_targets_resolve.py`): the tokens `verified_survives` / `verified_refuted` / `applied_in_commit` resolve in **neither** `bin/.events-registry.md` **nor** `cortex_command/`. A `grep -c "<token>"` Done-When in a **backlog** file would fail this lint — but it scopes to `cortex/backlog/*.md` only, **not** `spec.md`. So the spec's acceptance criteria may grep these tokens against the ledger/artifacts; a backlog ticket must not.
- **Philosophy of Work — Solution horizon:** propose durable infra only when redo is already known-needed. Here it is not (see Tradeoffs).

## Verdict-Source Mapping (evidence-grounded cross-check)

**#359 — `.../sweep-provisional-tail-discovery-backlog-author/outcomes.md`:** 43 rows (31 `APPLIED`, 12 `REFUTED`). Format: `- APPLIED|REFUTED <id> <file> — <reason> (commit: <subject line>)` for APPLIED / `(pinned by: <reason>)` for REFUTED. Rows carry **full ledger paths** and **commit subject-lines** already.

**#360 — `.../sweep-provisional-tail-critical-review-cluster/verdicts.md`:** 26 rows (24 `verified_survives`, 1 `verified_refuted`, 1 `correction`). Format: `- <id>(<basename>) → <disposition> — <evidence> [<short-SHA>]` (SHA on applied rows only). Rows carry **bare basenames** and **short-SHAs** — both need reconstruction/resolution (see Adversarial #1, #6).
- The single **`correction`** row: `s3(verification-gates.md)` [`cd48c762`] — "NOT a trim: the Step 2c.5 line wrongly naming `check-synth-stable` as the canonical SHA-computation path corrected to `prepare-dispatch`." The file *was* edited (a factual fix), but the proposed MERGE_DEDUP trim did **not** land; 0 token savings.

**Ledger cross-check (snapshot 2026-07-03T16:48Z):** all 43 + 26 = 69 `(file,id)` pairs match a ledger row exactly; all `status: unverified`; **0 absent, 0 already-reconciled.** Each child's row set exactly equals the ledger's own filtered subset (`unverified`, under the child's prefixes, minus `overlaps_ticket`/`reproposal_of`). All #359 subjects and #360 short-SHAs verified present in `git log`. **Counts are a moving target** — the ledger is under active concurrent mutation — so the reconciler must recompute at execution, not hardcode.

**Disposition → (status, applied_in_commit) mapping:**

| Source disposition | Ledger `status` | `applied_in_commit` |
|---|---|---|
| #359 `APPLIED` | `verified_survives` | subject-line (verbatim from row's `(commit: …)`) |
| #359 `REFUTED` | `verified_refuted` | *(omit)* |
| #360 `verified_survives` | `verified_survives` | subject-line **resolved from bracketed short-SHA** via git |
| #360 `verified_refuted` | `verified_refuted` | *(omit)* — 1 row: `s3(SKILL.md)` Contents-TOC |
| #360 `correction` | **open — see Open Questions** | **open** — 1 row: `s3(verification-gates.md)` |

**Excluded (leave untouched):** the 19 `overlaps_ticket`/`reproposal_of` rows under the three prefixes (neither child references them), and `skills/critical-review/references/reviewer-prompt.md` **s9** — a pre-existing `verified_survives` NOT in #360's set.

## Tradeoffs & Alternatives (implementation approach)

- **A — one-off scratch script (recommended):** two per-source parsers + an idempotent `(file,id)` upsert, run once from the lifecycle session, **not** committed to `cortex_command/`/`bin/`. Matches both prior precedents exactly; zero parity/console-script/events-registry obligations.
- **B — reusable committed CLI verb** (`cortex-reconcile-ledger`): durable, testable, discoverable — but net-new infra for a ledger no skill dispatches into, dragging in all the parity/registry/test obligations. Over-built.
- **C — per-source normalizer + thin shared upsert core:** the *shape* to borrow (the two source formats are genuinely heterogeneous, so some per-source parsing is unavoidable), but kept as scratch code, not promoted.

**Recommendation: A, structured internally like C.** Solution-horizon test ("do I already know this needs redoing?") → **no**: #357 partitioned exactly four children, two already folded, only these two remain, and the audit source is a static 2026-07-02 artifact (no fifth child expected). *Note (per Adversarial #11): the tool choice is correct even if a fifth child appeared, because a committed verb triggers obligations regardless — "drained" is supporting context, not the load-bearing argument.*

## Adversarial Review (failure modes that reshape the spec)

1. **CRITICAL — #360 path reconstruction.** #360 rows carry bare basenames; the naive rule "prepend `skills/critical-review/`" is **wrong** — only `SKILL.md` is flat, every other file is under `references/`. Reconstruct via an explicit file→path map and **hard-fail (not skip) on any reconstructed key absent from the ledger.**
2. **CRITICAL — basename+id is ambiguous; no fallback.** `(SKILL.md, s3)` maps to **6** distinct ledger paths (17 basename+id collisions total). A basename/fuzzy fallback could flip the wrong skill's row (#360's `s3(SKILL.md)` is `verified_refuted`). Full-path reconstruction is the only safe key.
3. **HIGH — #359 subject parser must handle nested parens.** Subjects contain `(#359)`, `{s1,s4}` etc.; a non-greedy `\(commit: [^)]*\)` truncates. Extract from `(commit: ` to the **last** `)` on the line, and round-trip-verify each stored subject with `git log --grep` before writing.
4. **HIGH — drive folds from the child artifacts' explicit verdict rows** (43 + 26), using the prefix filter only as a post-hoc coverage cross-check. The a-to-b-downgrade-rubric exclusion currently holds only by coincidence.
5. **MEDIUM — strengthen the double-fold guard into assert-or-raise.** "`status != unverified` → skip" silently accepts a concurrent actor's *disagreeing* verdict (or richer #358 shape). On an already-folded target, compare existing status to the source verdict and **abort on mismatch** rather than blind-skip.
6. **MEDIUM — resolve #360 short-SHAs at execution with `git rev-parse --verify`**, hard-failing on ambiguity/absence (the active branch may rebase/amend, making an 8-char prefix ambiguous or stale).
7. **Minimal shape is consumer-safe but internally inconsistent.** Grep confirms **nothing** reads the ledger or the vote fields programmatically, so `votes=0` on new `verified_survives` rows causes no runtime bug. But `report.html` (static, already stale) would render them as "survived with zero survive-votes" if ever regenerated. Document reconciled rows as a **distinct provenance class** (verdict-derived, `votes=0` expected).
8. **`correction` row — prefer an honest status.** Marking a candidate whose file *was* edited as `verified_refuted` records false history: a future audit scanning refuted rows sees a rejected MERGE_DEDUP whose stale claim could be re-proposed against the corrected text. A dedicated `status: corrected` is savings-neutral (tallies sum only `verified_survives`) *and* honest.
9. **Atomic rename ≠ no lost update.** The real threat is a stale read: reconciler reads → concurrent actor commits an organic edit → reconciler writes its whole-file image, clobbering it. Use **compare-and-swap**: re-read + hash-check immediately before the atomic temp-file+rename, abort-and-retry on change.
10. **Pre-flight for coherence.** If the target rows are already non-`unverified` at start (the concurrent actor folded them first, as it did #361→#366), **stop and report** rather than race.
12. Line anchors are already globally stale post-trim (not just #340/#186) — the reconciler correctly should not fix them; treat ledger anchors as advisory downstream.

## Open Questions

1. **`correction`-row status mapping** (the single `verification-gates.md s3` row). Options: (a) `status: corrected` — a new fourth status value, honest, savings-neutral (Adversarial #8, recommended); (b) `verified_refuted` + a new `corrected_in_commit` key — preserves the 3-value status contract but records a semantically false "refuted"; (c) `verified_refuted` only — loses the correction provenance entirely. No code validates the status enum, so a new value is technically safe but sets first-of-its-kind precedent. **Recommend (a); carry to Spec for explicit user sign-off** since it introduces a new status value.
2. **Concurrency contract.** Should the reconciler be specced as fail-fast — pre-flight check (Adversarial #10) + compare-and-swap write (Adversarial #9) + assert-or-raise double-fold guard (Adversarial #5) — accepting that it may correctly no-op if the concurrent actor folds #359/#360 first? *Resolved-inline recommendation:* **yes** — these are cheap, and the alternative (racing/clobbering an audit ledger) is the failure this whole lineage exists to prevent. Spec should encode all three as requirements.
3. **Write shape** — minimal (#361/#366: flip `status` + `applied_in_commit` only) vs rich (#358: also bump `votes`/`survive_votes`/append `verdict_summaries`). *Resolved-inline:* **minimal**, matching the most-recent convention and the direct sibling #366; the vote fields have no consumer. Documented rather than user-gated.
4. **#360 `applied_in_commit` value** — resolve short-SHAs to subject-lines (convention match) vs keep raw short-SHAs (31 ledger rows already store bare SHAs, so not unprecedented). *Resolved-inline:* **resolve to subject-lines** to match the explicit #366 "ledger convention," via `git rev-parse --verify` + `git log -s --format=%s`. Minor; documented.
