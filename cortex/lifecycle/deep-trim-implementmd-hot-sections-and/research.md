# Research: Deep-trim implement.md hot sections and replace dead §1a-i liveness check

## Epic Reference

Child of epic **347 — Skill value scorecard follow-through** (`cortex/research/skill-value-scorecard/report.html`). The epic scored 528 skill sections; #348 owns the highest-value single file — `skills/lifecycle/references/implement.md`, whose content rides into every dispatched builder prompt, so each resident token multiplies. This research is scoped to #348's implement.md verdicts only; sibling tickets (349 commit, 350 research, 351 project.md, 352 lifecycle.config, 353 provisional/dup sweep) own their own files.

## Codebase Analysis — Verdict Enumeration

**Source of truth**: `cortex/research/skill-value-scorecard/master_candidates.json`, filtered to `.file == "skills/lifecycle/references/implement.md"` → **13 candidates, all `status: verified_survives`** (no provisional candidates for this file).

**Count reconciled** (resolves the ticket's "11 vs 13"): 13 total; **2 already applied** (`s4`, `s7`, `applied_in_commit` = "Trim verified low-value prose…", git `0df456e0` on the unpushed `skill-value-trims` branch); **11 remain in-scope** for #348. Both figures are correct at different scopes.

### The 11 in-scope verdicts (current line anchors — stored anchors predate the inline-trim commit, so locate by heading + token)

| id | type | weighted | current heading : lines | pin re-validation |
|----|------|----------|-------------------------|-------------------|
| s13 | COMPRESS | 4190 | `**Step v — Auto-enter sequence**` : 121–147 | step-v ordering test + enterworktree-callsites + ADR-0008; **safe target 10–15%, NOT 20%** |
| s21 | COMPRESS | 1680 | `### Builder Prompt Template` : 215–237 | keep self-sealing verification guard content (commit c2daec5b) |
| s18 | LAZY_REF | 1699 | `**e. Worktree Integration**` : 192–202 | → new `references/merge-back.md`; keep inline skip line (cross-ref at :149) |
| s23 | COMPRESS | 1478 | `### 4. Transition` : 257–276 | event-roundtrip count pin; semantic parity with `common.py:846 requires_review` |
| s6 | COMPRESS | 1378 | `**Runtime probe**` : 48–58 | gate/gated-binary parity test (shared with s12 — see Adversarial D) |
| s3 | LAZY_REF | 1426 | `**Branch selection**` picker bullets : 22–26 | worktree **label list-item** must stay inline in §1 (two tests) |
| s14 | COMPRESS | 1176 | `**vi.**`/`**vii.**` : 151–153 | ADR-0004; **coordinate with s13** (terminator, see Adversarial #6) |
| s5 | COMPRESS | 1166 | `**Uncommitted-changes guard**` : 46 | no pins |
| s12 | COMPRESS | 1128 | `**iii. Worktree creation.**` : 109–119 | ⚠️ unrecorded pins: `create_worktree` token, `--feature interactive-`, `**iii.` marker |
| s11 | MERGE_DEDUP | 715 | `**ii. Overnight concurrent guard.**` : 101–107 | keep exactly 2× `bash -s --` + 2× sidecar mentions; keep `**iii.`/`**iv.` scaffolding |
| s10 | COMPRESS→**REPLACE** | 672 | `**i. Interactive worktree liveness check.**` : 94–99 | replace with real lock probe (user decision 2026-07-02) |

Sum of the 8 pure compressions (s3, s5, s6, s11, s12, s14, s21, s23) = **10,147 weighted** ≈ ticket's "~10.1k". Excluded already-applied: s7 (§1 dispatch/guards, 2510 wt), s4 (§1 branch-mode preflight, 2266 wt).

**s13 preconditions** (from the failure-history lens, which caps it at 10–15% because the section is already once-trimmed residue from commit 333cd43b): (1) keep the fallback's **"silent non-invocation"** clause — sole remaining coverage of research finding F6 after ADR-0008 deleted the `verify-worktree-auth` probe; (2) do **not** re-cut the cache-clear enumeration (that trade was already adjudicated in 333cd43b).

## Design Resolution

### Phantom path — definitively dead (premise confirmed)
`cortex/lifecycle/sessions/{slug}.interactive.pid` has **zero production writers**. `cortex/lifecycle/sessions/` is a gitignored dir of UUID-keyed per-session `bin-invocations.jsonl` telemetry — unrelated to feature slugs; no `.pid` files exist. The path is documented as **"a path-naming error"** (`cortex/lifecycle/add-bidirectional-concurrency-guards-for-interactive/spec.md:9`), introduced 2026-05-18 (bc32dc0d) as a rename of a `daytime.pid` guard, never tied to an observed failure. The **real** lock is `cortex_command/interactive_lock.py` (console script `cortex-interactive-lock`) writing JSON to `cortex/lifecycle/{slug}/interactive.pid`. Both implement.md §1a-i **and** `lifecycle_implement.py` fire-condition (iv) / `_has_live_interactive_session` (`_SESSIONS_RELDIR` at ~line 45) read the dead path.

**Consequence**: the `suppressed` entry mode (`branch-mode: worktree-interactive` bypasses the picker → jumps straight to §1a, skipping §1 Step A/B) has **zero real same-slug concurrency protection today** — §1a-i is its only guard and it guards nothing.

### s10 lens conflict — resolved
s10 (index 65) carries three lenses: two want to keep the phantom-path token as a "parity contract" with `_has_live_interactive_session`; the failure-history lens says defer to the real verb. Since the "contract" is with dead code, **the failure-history lens is correct** → replace §1a-i's phantom `cat`+`kill -0` prose with a call to the real `cortex-interactive-lock` verb (structural, exit-code-branched). This matches the user's 2026-07-02 "replace with a probe" decision and yields net token reduction.

### §1a-i replacement (entry-mode-conditioned)
The replacement **must condition on entry mode** — a naive unconditional `acquire` self-rejects on the `selected` path (Step B already acquired; a second `acquire` in the same session hits the session_id-match LIVE row → exit 1; **verified by live probe**). Shape:
- entry mode `selected` → Step B already acquired for `{slug}`; skip, proceed to §1a-ii.
- entry mode `suppressed` → run `cortex-interactive-lock acquire {slug}`; exit 0 → proceed; non-zero → surface the script's stderr rejection verbatim and exit §1a without creating a worktree.

**Affordance protected** (per CLAUDE.md gate-authoring): prevents a second concurrent interactive session on the same slug from creating a colliding worktree/branch → shared-index corruption (a real, previously-hit hazard). Structural (delegates to the single console-script source of truth) — not prose. The entry-mode marker (`selected`/`suppressed`) is already recorded and in scope at §1a. **Open ordering question — see Open Questions.**

### Fire-condition iv rewire (coupled — same commit)
Repoint `_has_live_interactive_session` at the real lock: `return slug in scan_live_locks(pathlib.Path(repo_root))` (`scan_live_locks(project_root)` takes an explicit root — the deliberate exception already reused by `overnight/orchestrator.py`; verified signature). Drop `_SESSIONS_RELDIR` (no other consumer). This flips a previously-dead branch to live — **drive E2E, not just unit-test.**

### Docstrings — BOTH must be fixed (Adversarial correction)
`lifecycle_implement.py` has **two** stale phantom references: (1) `:74-76` in `_has_live_interactive_session` cites `implement.md:78–82` (now §1a-i at 94–99); (2) `:124` in `should_fire_picker` cites the phantom `sessions/{slug}.interactive.pid` path for condition (iv). Fix both; drop the line-number cite in favor of `interactive_lock.py::scan_live_locks` + section name.

### Merge-back sibling (s18)
New file `skills/lifecycle/references/merge-back.md` holding the five-case merge-back procedure (skipped entirely for sequential dispatch). Read-trigger at §2e for the worktree-dispatch arm only, via the **body-resolved absolute path** (SP001/SP002-safe: `${CLAUDE_SKILL_DIR}/references/merge-back.md` prefixed form, mirroring the sidecar at implement.md:104, or pure-prose "body-resolved merge-back path"). Keep the inline skip line (implement.md:149 cross-references "§2(e) merge-back applies unchanged"). Add a manifest entry to `skills/lifecycle/SKILL.md`'s Reference-path propagation block (:146-160). New file must be `git add`-ed and committed **in the same commit** as the implement.md edit + regenerated mirror.

### dup_groups `$model` cluster → deferred to #353
The three dup_groups touching implement.md are all the identical `cortex-resolve-model` "halt and escalate" boilerplate shared across implement.md:170-176 ↔ competing-plans.md ↔ orchestrator-review.md (~68 tok each). Single-sourcing requires editing files **outside #348's scope**. #353 owns the cross-file sweep. **#348 leaves lines 170-176 a verifiable no-op** (physically disjoint from every #348 cut range) so the single-sourcing happens exactly once, in #353.

## Web Research

Prior art is thin (internal-tooling change) but includes one directly-analogous precedent: **github/copilot-cli#3255** — an AI coding CLI whose session lock went stale after SIGKILL, causing false "session active." Their fix layers `kill -0` existence + `ps -p` command-match to defeat PID reuse. Corroborates: treat "stale lock" as the primary path, and prefer probing an **existing** lock over a new mechanism. The real `interactive_lock.py` already implements a richer multi-row liveness table (better than the naive §1a-i `kill -0`), reinforcing "delegate to the verb." On structural-vs-prose gate enforcement, external art (arXiv agent-security) merely **confirms** the project's existing CLAUDE.md stance — not novel; do not cite as new authority. On dead-code removal: no prompt-file-specific art; apply generic discipline (reachability proof + fail-then-pass test around the deletion) by analogy.

## Requirements & Constraints

- **Mirror / same-commit discipline**: `just build-plugin` rsyncs the whole `skills/lifecycle/` tree (incl. `references/implement.md`, `references/merge-back.md`, `SKILL.md`) into `plugins/cortex-core/skills/lifecycle/`. The `.githooks/pre-commit` dual-source drift gate **blocks** unless canonical + mirror are staged in the **same commit**. `cortex_command/lifecycle_implement.py` is **not** mirrored (only skills/, bin/cortex-*, hooks/*.sh).
- **Tests that gate the change** (run all post-edit): `test_lifecycle_step_v_ordering`, `test_lifecycle_enterworktree_callsites`, `test_implement_worktree_interactive_contract`, `test_implement_option2_worktree_creation`, `test_lifecycle_picker_label_pins_worktree`, `test_lifecycle_implement_branch_mode`, `test_lifecycle_event_roundtrip`, `test_common_utils`, `test_lifecycle_kept_pauses_parity`, `test_lifecycle_references_resolve`, `test_bidirectional_concurrency_contract`. Plus lints: `cortex-check-skill-path --audit`, contract, parity.
- **Gate-authoring** (CLAUDE.md): the §1a-i replacement is a concurrency **gate** → route through the console-script exit code (structural), state the decision + cite the exit-code contract, do **not** re-narrate the internal liveness algorithm. Identify + preserve the affordance (done above); this boundary is load-bearing, not ceremonial.
- **Skill-path (SP001/SP002, ADR-0009)**: implement.md is a reference file and cannot resolve `${CLAUDE_SKILL_DIR}` itself — the merge-back read directive must carry a body-resolved absolute path (propagated from SKILL.md), never a bare-relative `Read`. Enforced by `cortex-check-skill-path` (pre-commit Phase 1.87).
- **Size/L1**: implement.md is a **reference file, exempt** from both the 500-line SKILL.md size budget (`test_skill_size_budget.py` globs `*/SKILL.md` only) and the L1 surface ratchet (frontmatter-scoped). No byte/line cap gates it — only the token/order/proximity pins above.
- **#353 vs #348 split**: #348 = all 11 in-scope implement.md verdicts; #353 = the cross-file `$model` dup-group single-sourcing. Epic 347 discipline: consume verdicts from master_candidates.json (re-validate, don't re-derive), rank by weighted resident tokens, regenerate mirror same-commit.

## Adversarial Review

Evidence-backed (files read + live lock probes):

1. **Orphan-lock ordering hazard (real).** §1a-i `acquire` (line ~94) runs *before* the §1a-ii overnight guard (line ~101). If §1a-ii rejects, the acquired lock is never released (`release_lock` is dead in the skill flow), so the same session self-blocks on retry and concurrents see false-LIVE until stale recovery. **The selected path already carries the symmetric latent version** (Step B acquires at :78, §1a-ii can still reject) — so this is parity with an existing hazard, not a fresh regression. Durable fix = overnight-check-before-acquire on both paths (mirror §1 Step A→Step B order) or release-on-reject. **→ Open Questions.**
2. **s13+s14 terminator cross-cut (real).** `test_lifecycle_step_v_ordering.py` extracts the step-v block up to the next `**`-prefixed line. Terminators today: `**Fallback`(:147), `**vi.`(:151), `**vii.`(:153). If s13 strips `**Fallback` **and** s14 strips `**vi.`, no terminator remains → `pytest.fail`. **Coordinate the two cuts to leave ≥1 `**`-line after step-v.**
3. **Two stale docstrings, not one** (see Design Resolution) — fix `:74-76` **and** `:124`.
4. **a3 fixture MUST-DOs**: the rewritten test must write JSON with `"magic": "cortex-interactive-lock"` (line 508 skips non-magic files) + a **live self-PID** (dead PID → STALE → test fails). `session_id:null` + self-PID + `start_time:null` classifies **LIVE** (verified). Existing `.git/info/exclude` (`cortex/`) still hides the new path — clean-tree check unaffected.
5. **Corrections to pin ownership**: `test_common_utils.py` is a pure-function test that never reads implement.md — s23's matrix compression **cannot** break it (constraint is semantic parity with `common.py:846`, a reviewer check). `test_gate_and_gated_path_use_same_binary` binds **s12** (§1a-iii region), not just s6. **s3** must keep the worktree **label list-items** inline in §1 (two tests) — only the When-to-pick descriptions may move (low ceiling).
6. **Additional unrecorded pins**: s12 must retain `create_worktree`, the `--feature interactive-` invocation shape (:112), and the `**iii.` marker; s11 must keep the `**iii.`/`**iv.` scaffolding; s23 must keep exactly `{batch_dispatch:1, phase_transition:2}` and the §4 `phase_transition` field-map `--set tier= --set from= --set to=` (all `--set`, not `--set-json`). Enterworktree callsites are **safe from line-shift** (cuts only move tokens closer to the callsite; sole break vector is token removal, i.e. s12).
7. **kept-pauses ±35 tolerance holds** (line-shift only shrinks the span); update the `implement.md:37` inventory anchor for hygiene anyway.

## Open Questions

- **[Deferred to Spec §4 approval] Acquire-ordering / orphan-lock scope.** Adding `acquire` on the suppressed path (§1a-i replacement) inherits the same latent orphan-lock-on-overnight-reject hazard the already-shipped selected path has. Three options to present at Spec approval: **(a) Minimal/parity** — acquire at §1a-i matching the existing selected-path ordering; smallest change, fully in #348 scope, accepts the pre-existing latent hazard equally on both paths. **(b) Durable** — reorder overnight-guard-before-acquire (or release-on-reject) on **both** paths; fixes the latent hazard but expands scope to touch the selected-path Step B. **(c) Carve-out** — ship (a) now + file a follow-up ticket for the cross-path ordering/release-symmetry fix. Deferred here (not resolved mid-research) because it is a scope/tradeoff decision best made with the full spec in view; the CLAUDE.md solution-horizon rule requires surfacing minimal-vs-durable with the tradeoff, which is the Spec §4 surface. Lean: **(c)** — keep #348 focused on the trim + dead-check replacement, name the durable fix in a follow-up.
- **[Assumption to record, not blocking] Bash-tool shell persistence.** The cross-session value of the new suppressed-path guard depends on the lock's recorded `pid=os.getppid()` staying alive (persistent shell). If the harness spawns per-call shells, cross-session `scan_live_locks` sees a dead parent → STALE → doesn't block, degrading the guard to same-session-only. Pre-existing #241 behavior, not worsened here. Spec should state the assumption; no code change implied.
- **[Assumption] Suppressed-path reachability** requires `branch-mode: worktree-interactive` config to be set (a live but rarely-exercised feature). The docstring/wiring correctness fixes (fire-condition iv + docstrings) stand regardless of how often the suppressed path runs.

## Considerations Addressed

- *The 1a-i probe is a user-directed net-new guard, not a master_candidates.json verdict — validate it's a real correctness gain and keep it minimal.* **Addressed**: confirmed the suppressed path has zero real same-slug guard today (§1 Step A/B gated to `selected`; §1a-i reads a dead path), so the probe is a genuine correctness gain, not scope-creep; the replacement reuses the existing `cortex-interactive-lock` console script (no new lock mechanism) and is a net token reduction. The residual scope question (acquire ordering) is deferred to Spec, keeping the addition minimal.
