# Research: Best mechanism for lifecycle worktree entry without cortex writing to consumer CLAUDE.md

**Clarified intent:** Determine, from first principles and an empirical gate test, the best mechanism for the lifecycle implement phase to enter an interactive worktree **without `cortex init` writing an authorization fence into a consumer repo's human-curated `CLAUDE.md`**. Land on ONE recommendation with rationale, rejected alternatives, blast radius, and a durability call. Complexity: complex. Criticality: high.

**This exploration ran the empirical gate test (Q1) the prior research deferred.** Its result is the fact the recommendation rests on, and it changes the answer.

---

## Headline findings

1. **Q1 RESOLVED (empirically, this session): a live picker selection authorizes `EnterWorktree`, and the gate is soft — the harness does not enforce it.** A controlled dispatch (fence revoked, no typed mention) showed a fresh orchestrator agent judge itself authorized by the user's *selection* of a worktree-labeled picker option, invoke `EnterWorktree(path=…)`, and have the **harness accept the call** — it failed only on the orthogonal `path=`-existence check, never on authorization. A control agent (user chose "current branch", no mention) correctly declined. This is the single fact the prior research sidestepped (it relied on a sub-agent's *opinion* that a click "likely fails, 95%").

2. **The fence is load-bearing for exactly ONE path: the suppressed-picker path** (`branch-mode: worktree-interactive` preset → no live mention). Every other path (picker fires → user selects the worktree option) carries a live mention that authorizes `EnterWorktree` with no standing surface. That suppressed-picker path has **never fired in this repo** (`branch-mode: prompt`) and is a power-user opt-in.

3. **The reported interactive-worktree instability is ORTHOGONAL to the orchestrator's entry mechanism.** Implement sub-agents run `Agent(isolation: "worktree")` and each re-roots into its own worktree (verified: `implement.md:195/227`; memory feedback says "sub-agents each re-root"). The instability comes from that sub-agent isolation mutating shared `.git`/`.venv` state — it persists identically whether the orchestrator entered via `EnterWorktree` or sits at repo root via the cd-shim. *Dropping `EnterWorktree` neither causes nor cures it.* (One core-wave agent argued entry *causes* the instability via `isolation=<none>` sub-agents; that premise was checked and is unfounded — the telemetry has no `isolation` field, so "=none" was inferred from an absent field. Adjudicated against.)

4. **Recommendation: Option B — per-invocation authorization, delete the standing fence.** Keep `EnterWorktree` on the picker-fired path (now empirically validated to authorize); delete the entire consumer-`CLAUDE.md` fence apparatus; the suppressed-picker path degrades to the already-shipped cd-shim. This fixes the stated objection permanently, keeps the in-use path, deletes dead-weight rather than parking it behind a flag, and **amends (narrows) ADR-0006 rather than superseding it** — so #249/#250 stay valid. It degrades gracefully because the cd-shim is already the fallback for any gate decline. Durable, not churn.

---

## Empirical Gate Test (Q1)

### Live dispatch result (this session)
Method: temporarily revoked the repo's standing fence (`cortex init --revoke-worktree-auth`), then dispatched two fresh orchestrator agents — one where the user **selected** the picker option "Implement on feature branch with worktree", one control where the user selected "Implement on current branch" — each told to read the live `EnterWorktree` schema, decide authorization, and attempt the call if authorized. Repo state restored afterward (fence re-added; tracked tree clean).

| Condition | Verdict | Action | Harness response |
|---|---|---|---|
| **Picker-selected the worktree option** | **AUTHORIZED** | Invoked `EnterWorktree(path=…)` | **Accepted the call**; failed only on `path=` existence (`ENOENT` — the test path wasn't a registered worktree). **No authorization block.** |
| **Control: selected "current branch"** | **NOT AUTHORIZED** | Declined; did not call | n/a (correctly self-declined) |

**What this proves:**
- The authorization gate is **soft model-judgment, not harness-enforced.** The harness evaluated the picker agent's call and only the *path-validity* hard check (schema: "The path must appear in `git worktree list`") rejected it. Authorization was never the blocker.
- **A user's selection of a worktree-labeled option authorizes the call.** The picker agent reasoned that the rule's intent is to block *agent*-initiated worktrees without consent — and a deliberate selection of a worktree option *is* user consent, "a stronger, less ambiguous expression of intent than free-form text." This matches the shipped ADR-0004/R19 design and refutes the prior research's "picker click likely fails" lean.
- **The soft gate is not trivially permissive** — the control correctly declined when there was no worktree mention.

**Honest residual:** the picker agent itself flagged the selection-vs-mention seam as "genuinely underdetermined" in the rule's literal text ("mentioned"/"says"), resolved via protective intent. A stricter model/effort could decline. This is the irreducible epistemics of a *soft* gate: any single observation samples a judgment, not a hard barrier. **Mitigation is structural and already shipped:** `implement.md` §1a routes any `EnterWorktree` decline (the `EnterWorktree skipped` branch) to the cd-shim. So a "no" at runtime costs only the orchestrator re-root, never correctness.

### Documentary corroboration (Web angle)
- Official Claude Code tools-reference lists `EnterWorktree`/`ExitWorktree` as **Permission Required: No** — not gated by the settings allow/deny prompt flow; governed only by the prose condition. (They *can* be hard-*denied* via `permissions.deny`/PreToolUse hook/subagent tool lists — but deny can only *forbid*, never *authorize*, so it is not a mechanism for fence-free entry.)
- Verbatim gate: *"Use this tool ONLY when explicitly instructed to work in a worktree — either by the user directly, or by project instructions (CLAUDE.md / memory)."* / *"Never use this tool unless 'worktree' is explicitly mentioned by the user or in CLAUDE.md / memory instructions."* No authorization-token parameter exists; the only hard check is `path=` validity.

### The deferral this exploration corrects
The original auto-enter feature (#249/#250, ADR-0006) shipped to `accepted`/`complete` with this exact bet **unverified**: `events.log` carries `manual_verification_deferred` (R21/R22), `review.md` marks them PARTIAL, and the spec labels it the "Live-empirical bet… NOT proven by any in-scope automated test." Shipping the #288 recommendation without running the test would repeat that defect — so it was run (above).

---

## Codebase Analysis (per-option blast radius)

**Single call site, cd-shim already the floor.** The only `EnterWorktree(` invocation is `skills/lifecycle/references/implement.md` §1a step-v (line ~180), behind a `cortex init --verify-worktree-auth` probe (~173) that **already falls back to the cd-shim (`cd $(cortex-worktree-resolve interactive/{slug})`, ~193) on any non-zero exit.** The cd-shim is therefore the live path in every repo lacking the fence. Worktree *creation* is always `git worktree add` (ADR-0004; permanent) — `EnterWorktree` is only the orchestrator CWD-switch.

**Fence apparatus (deleted under A/B):**
- `cortex_command/init/scaffold.py`: `ensure_claude_md_authorization()`, `revoke_claude_md_authorization()`, `_find_claude_md_auth_fence()`, `_render_claude_md_auth_block()`, `_read_claude_md_auth_template()`, `live_interactive_sessions()` + `_pid_is_live()`; constants `_CLAUDE_MD_AUTH_TEMPLATE`/`_CLAUDE_MD_AUTH_VERSION`/fence sigils+regex; remove the template from `_HASH_INPUT_TEMPLATES` (**flips the init-artifacts hash** → one-time `cortex init --ensure` drift refresh on marker-present consumers — the natural migration carrier).
- `cortex_command/init/handler.py`: step-0b `--revoke-worktree-auth`, step-0c `--verify-worktree-auth`, step-6b `ensure_…` call in `_run` and `_run_ensure`.
- `cortex_command/cli.py`: `--revoke-worktree-auth`/`--verify-worktree-auth` arg defs; init mutex group 5→3 verbs.
- `cortex_command/init/templates/claude_md_authorization.md`: delete file.
- `cortex_command/lifecycle/init_ensure.py`: drop the two namespace flags.
- `CLAUDE.md` (this repo, 83-89): fence section (one-time manual delete once regeneration stops).
- Docs: `skills/lifecycle/references/complete.md:181` (ExitWorktree exit prose) — **note `tests/fixtures/complete_md_hard_guard.txt` is a byte-snapshot of this line; regenerate in lockstep**; `docs/internals/sdk.md:216`.

**Option-specific deltas:**
- **B (recommended):** same fence deletions as A, **but keeps the `EnterWorktree` call site** on the picker-fired path. `--verify-worktree-auth` can be dropped (no fence to verify) — restructure step-v to drop the probe; the cd-shim fallback still covers a runtime decline. `implement.md` §1 picker option keeps its "worktree" label (now the sole authorization surface — `test_lifecycle_picker_label_pins_worktree.py` becomes load-bearing, which is correct). Suppressed-picker (`branch-mode: worktree-interactive`) routes to cd-shim.
- **A:** B's deletions **plus** delete the `EnterWorktree` call (cd-shim everywhere) — also kills the in-use picker-fired entry.
- **D:** keep all machinery, gate the fence *write* on an opt-in flag (config field via the `read_branch_mode` reader pattern, or a CLI verb). Smallest code delta but **grows** maintained surface.
- **C:** relocate the write target to a cortex-owned surface — still a write into the consumer's `.claude/` tree.
- **E:** no non-fragile "is-foreign-repo" signal exists pre-first-init (the `.cortex-init` marker is written in the *same* `cortex init` run as the fence) → **E collapses into D**'s opt-in verb.

**Tests pinning current behavior:** `test_init_claude_md_authorization.py`, `test_init_verify_worktree_auth.py`, `test_lifecycle_step_v_ordering.py` (pins `verify-worktree-auth`+`EnterWorktree(` order — rewrite under B to drop the verify token), `test_lifecycle_enterworktree_callsites.py` (asserts ≥1 call site — **survives under B**, fails under A), `test_init_artifacts_hash_inputs.py`, `test_handler_ensure.py`, `test_init_ensure.py` (verb-set frozenset), `test_complete_md_hard_guard_snapshot.py` (fixture regen). `test_create_worktree_bypass.py` (ADR-0004) and `test_lifecycle_kept_pauses_parity.py` are unaffected (picker pause stays).

**Dual-source:** `skills/`/`SKILL.md` edits mirror to `plugins/cortex-core/` via `just build-plugin` (commit canonical+mirror together; mirror currently in sync). `cortex_command/init/*`, `cli.py`, template, tests ship in the wheel only (not mirrored).

**Backward-compat:** `implement.md` routes *any* non-zero `--verify-worktree-auth` exit (including argparse exit-2 after deletion) → cd-shim, so immediate subcommand deletion is safe.

**#249/#250/#273:** #249 (auto-enter drop-the-cd-handoff) and #250 (the fence shipper) are `complete`, high. **B keeps the auto-enter core (EnterWorktree on selection) and removes only the standing-fence surface → #249/#250 stay `complete`; only ADR-0006 narrows.** A would have to mark them superseded/wontfix (state-integrity churn). #273 (`complete`, high — restrict `cortex init --ensure` to never write `~/.claude/`) is direct precedent: "*a write the user explicitly typed in their terminal can mutate outside-cortex surfaces; an in-session AI write cannot.*"

---

## Web Research (gate semantics, surfaces, norm)

- **Permission model:** `EnterWorktree`/`ExitWorktree` = Permission Required: No (verified, official tools-reference). Soft prose gate; can be hard-*denied* but not hard-*required*.
- **No-`EnterWorktree` path is first-class:** `claude --worktree`/`-w` at launch and `git worktree add … && cd … && claude` are both officially documented. Caveat: bare in-session `cd` outside the project root is reset by the Bash tool, so `EnterWorktree(path=…)` (or `--add-dir`) is the clean *mid-session* re-root — relevant to what the cd-shim sacrifices.
- **Authorization-surface portability** (for option C): the only repo-portable instruction surfaces other than the hand-curated `./CLAUDE.md` are `.claude/rules/*.md` and a committed `@path` import. `CLAUDE.local.md`, user rules/memory, and auto-memory are machine-local. But the tool names only "CLAUDE.md / memory", so `.claude/rules/` is medium-high-confidence-but-unverified, and **C still writes into the consumer's `.claude/` tree** — a renamed foreign write, not an eliminated one.
- **Config-ownership norm is a published standard-adjacent guideline, not folk practice:** clig.dev — *"If you automatically modify configuration that is not your program's, ask the user for consent… Prefer creating a new config file rather than appending to an existing config file."* Plus the XDG Base Directory spec. This is external validation for **stopping the foreign-`CLAUDE.md` write** (and, if inline were unavoidable, the dated-delimiter pattern the current fence approximates).

---

## Requirements & Constraints

- **ADR-0003** (`accepted`): *"the only write cortex-command makes outside its own tree"* is `~/.claude/settings.local.json`. The foreign-`CLAUDE.md` fence is a *second* outside-tree write — ADR-0006 acknowledges this as "scope creep on ADR-0003's 'only write' claim" but **ADR-0003 was never amended**, so two `accepted` ADRs literally contradict. Removing the fence (A/B) fixes the contradiction; D leaves it live behind a flag. (Own-repo fence is *not* an ADR-0003 violation — cortex owns its own CLAUDE.md; the breach is foreign-repo-specific.)
- **ADR-0004** (`accepted`): creation via `git worktree add` (permanent); `ExitWorktree` is a cross-session no-op so the multi-step Complete phase relies on the user manually exiting before re-invoke (accepted long-tail edge). **Defect: line 49 cites "ADR-0005" for the fence shape / rejected sibling-file alternative — that content is in ADR-0006; ADR-0005 is "Repo-relative worktree placement."** One-line `0005`→`0006` fix, land regardless of option.
- **ADR-0006** (`accepted`): the decision under question. Rejected the `.claude/cortex-authorizations.md` sibling file (schema names only CLAUDE.md/memory); **deferred** (not rejected) a pure `memory/` write, noting "either surface satisfies the gate." Three subcommands: write / `--revoke-worktree-auth` / `--verify-worktree-auth`.
- **Supersede vs amend** (`cortex/adr/README.md`): supersession = `status: superseded` + `superseded_by: NNNN` + a *new* ADR (required for a reversal). Amendment = in-file appended section (+ optional status edit), no new number — appropriate for narrowing. **B amends ADR-0006 (narrow the authorization surface to the live-mention path); A supersedes it.**
- **Solution-Horizon** (`project.md`): durable over churn; "a scoped phase of a multi-phase lifecycle is not a stop-gap"; "anchor on current knowledge, not prediction." Cuts both ways here — it argues against reversing shipped #249/#250 (against A) *and* against carrying never-used machinery (against D).
- **Kept-pauses parity:** the §1 branch-picker pause stays; the `cortex-lifecycle-branch-mode` structural marker must stay within ±35 lines of the picker `AskUserQuestion` site (`test_lifecycle_kept_pauses_parity.py`). B keeps the picker, so the inventory entry is unchanged.
- **Authoring/MUST policy:** What/Why-not-How; no new MUST without an evidence artifact — any new skill prose uses soft positive-routing.
- **Destructive-ops:** any fence-removal migration skips on uncommitted state and lives in a named script.

---

## Tradeoffs & Options (neutral comparison + steelman)

| Option | Zero foreign writes (C1) | Implement correct+ergonomic (C2) | Maintenance (C3) | Durable, not churn (C4) | ADR/state reconciliation |
|---|---|---|---|---|---|
| **A. Full removal / cd-shim** | ✓✓ | ✓ correct; ✗ loses re-root on the in-use picker path too | ✓✓ deletes everything | ✗ reverses #249/#250, supersedes ADR-0006 | supersede 0006 + #249/#250 → superseded/wontfix |
| **B. Per-invocation (drop fence, keep EnterWorktree on live mention)** | ✓✓ | ✓✓ keeps validated picker-fired entry; suppressed-picker → cd-shim | ✓ deletes fence machinery, keeps one call site | ✓✓ amends 0006; #249/#250 stay valid; degrades gracefully | amend (narrow) 0006 |
| **C. Relocate to cortex surface** | ✗ still writes consumer `.claude/` | ✓✓ | ✓ | ✓ | amend 0006; needs surface-honored verification |
| **D. Opt-in flag, default off** | ✓✓ | ✓✓ | ✗ keeps full apparatus + a flag (grows surface) | ✓ amends 0006 but parks dead-weight; leaves 0003↔0006 live | amend (narrow) 0006 |
| **E. Foreign-skip** | ✓/✗ needs reliable signal | ✓✓ | ✗ adds a fragile detector | ✓ | folds into D |
| **F. Status quo** | ✗✗ writes fence everywhere — the objection | ✓✓ | ✓ | n/a (doesn't solve C1) | none |

**Filter on C1 (the hard requirement):** F and C fail (both write outside cortex's owned tree into the consumer). E is conditional → folds into D. Survivors: **A, B, D.**

**Steelman for keeping EnterWorktree (against A):** the whole-session re-root buys structural stray-edit containment for orchestrator-direct authoring, CWD-cache correctness, and the exit-time keep/remove data-loss prompt. But the telemetry (below) shows the orchestrator is mostly a dispatch-and-merge wrapper, so the re-root's value is real-but-thin on the suppressed path — and B *retains* it on the picker-fired path. The steelman's strongest point lands against A (don't reverse a working, shipped, in-use path), not against B.

**Why B over A and D:**
- **vs A:** A additionally kills the in-use, now-validated picker-fired entry (ergonomic regression for a working path) and incurs supersession + #249/#250 surgery. B keeps the working path and only narrows the fence surface. B is strictly A-plus-opportunistic-EnterWorktree: it degrades to A's behavior if the soft gate ever declines (cd-shim fallback), so it dominates A.
- **vs D:** D keeps the entire fence apparatus (template, verify/revoke, 4+ tests, the live ADR-0003↔0006 contradiction) behind a default-off flag — to serve the suppressed-picker path that has **never fired**. That is the dead-weight Solution-Horizon trims; a future harness-review prunes it (a partial revert). B deletes it now.

---

## cd-shim Cost (Q2) & Interactive-Worktree Value (Q4)

- **Stray-edit risk under cd-shim:** low and the *safe* direction — under the shim the orchestrator CWD stays on the main checkout, so a stray relative-path edit lands where `git status` makes it immediately visible, not buried in a diverged worktree branch. Not data-loss either way.
- **Stale-cache cost:** cosmetic-to-minor — the orchestrator barely reads/edits worktree files directly; it dispatches sub-agents (fresh contexts, no stale cache).
- **Usage telemetry:** orchestrator-in-worktree entry was used **3 times ever** (all one day, 2026-05-29, none since; zero live `.interactive.pid`). The feature is ~9 days old and the fence only landed in this repo 2026-05-29. **Caveat (adversarial):** this is a small sample over a window including the feature's bootstrap; it supports "the *suppressed-picker* auto-enter is unproven," **not** "interactive entry is dead." The operator hit the instability at 09:48 and still entered worktrees 3× that afternoon — tolerance, not abandonment.
- **Instability causation:** orthogonal to entry (see Headline #3). The decision rests on value-vs-footprint, not a safety defect.

---

## Adversarial Review (key challenges + adjudications)

- **Instability-causation contradiction — adjudicated:** the "entry causes instability" claim rests on implement sub-agents running `isolation=<none>`; verified false (spec uses `isolation:"worktree"`; the telemetry has no `isolation` field, so "=none" was inferred from absence). Instability is orthogonal — neither cited *for* dropping entry nor *for* keeping it.
- **Telemetry reframing:** "barely used" is about the suppressed-picker path specifically (never fired here under `branch-mode: prompt`), not interactive entry generally. Fair basis to call the *fence* low-value; not a basis to call the *picker-fired entry* dead.
- **Gate test was deferred once and must not be deferred again** — it was run (above), which is what makes B's recommendation rest on a measurement, not a bet.
- **7th-option scan:** `permissions.deny` is a red herring (forbids, can't authorize). "Never suppress the picker" (B′) is a genuine distinct Pareto point — always force the picker so there's always a live mention; costs the always-prompt friction #249 removed. Folded into B as the suppressed-picker handling (degrade to cd-shim rather than force the picker — lower-friction, and the suppressed path is never-fired).
- **The "spec-vs-practice isolation divergence" is a phantom** — do not "fix" sub-agent dispatch to use worktree isolation; it already does.

---

## Recommendation: Option B (per-invocation authorization; delete the standing fence)

**Decision.** Delete the consumer-`CLAUDE.md` fence apparatus entirely. Keep `EnterWorktree` callable on the **picker-fired path**, authorized by the user's live selection of the worktree-labeled option (empirically validated this session). The **suppressed-picker path** (`branch-mode: worktree-interactive`) degrades to the already-shipped cd-shim. Amend (narrow) ADR-0006; fix the ADR-0004:49 mis-citation and reconcile ADR-0003. This is option **B** from the ticket, now resting on a measurement rather than the prior research's deferred bet.

**Why each other option loses:**
- **F (status quo):** writes the fence into every consumer `CLAUDE.md` — the exact objection; fails C1.
- **C (relocate):** still writes into the consumer's `.claude/` tree (renamed foreign write); the schema-eligible portable surface is unverified; ADR-0006 already rejected the sibling-file variant. Fails C1.
- **E (foreign-skip):** no non-fragile foreign-repo signal exists before first init; collapses into D.
- **D (opt-in flag):** keeps the full apparatus + the live ADR-0003↔0006 contradiction behind a default-off flag to serve a never-fired path — dead-weight a future pass prunes (partial revert).
- **A (full removal):** also deletes the in-use, validated picker-fired entry and forces supersession of ADR-0006 + #249/#250 surgery — more churn than B, for no gain over B (B degrades to A's behavior on any gate decline via the cd-shim).

**Blast radius / migration (B):** delete the fence functions/constants/template + `--verify`/`--revoke` subcommands (CLI mutex 5→3); restructure `implement.md` §1a step-v to drop the verify probe while keeping `EnterWorktree` on the picker path (cd-shim fallback retained); regenerate the `complete_md_hard_guard.txt` snapshot; mirror skill edits via `just build-plugin` (commit canonical+mirror together); the init-artifacts-hash flip carries a one-time `cortex init --ensure` drift refresh; existing consumer fences are **left-stranded** (already ADR-0006's accepted uninstall behavior; auto-removal would itself write to CLAUDE.md once — document the one-line manual delete). Tests: delete the fence/verify tests, rewrite `test_lifecycle_step_v_ordering.py` to drop the verify token, keep `test_lifecycle_enterworktree_callsites.py` and `test_lifecycle_picker_label_pins_worktree.py` (now load-bearing). ADRs: **amend** ADR-0006 (narrow the authorization surface to the live-mention path, record the gate-test result as the justification artifact), append the reconciling note to ADR-0003, fix ADR-0004:49. #249/#250 stay `complete` (their auto-enter core survives).

**Durability (Solution-Horizon).** Durable: fixes the stated objection permanently (no foreign writes ever), keeps the empirically-validated path, deletes dead-weight instead of parking it, amends rather than reverses ADRs, and degrades gracefully if the soft gate ever changes (cd-shim floor). Residual churn risk: if the operator later sours on interactive entry *entirely*, B's `EnterWorktree` call becomes vestigial and drifts toward A — but that is a clean future deletion of a graceful-fallback call, not a costly reconstruction, and current knowledge (3 uses, kept-using-after-instability) doesn't support "unwanted." Per "anchor on current knowledge, not prediction," B is the durable choice now.

---

## Open Questions

1. **Soft-gate confidence (resolved, with residual).** The gate test confirmed a picker selection authorizes `EnterWorktree` and the harness does not hard-block; but a soft gate is model-dependent and a stricter reading could decline. **Resolved direction:** accept the risk — the shipped cd-shim fallback (`EnterWorktree skipped`) makes any decline cost only the orchestrator re-root, never correctness. No further action needed; the spec records the cd-shim fallback as the safety net.
2. **Suppressed-picker (`branch-mode: worktree-interactive`) handling under B.** Should it degrade to cd-shim (recommended — never-fired, lowest friction), force the picker (B′ — restores a live mention but reintroduces the prompt #249 removed), or get an opt-in cortex-owned standing surface (B+D blend — earns its complexity only if a consumer needs it)? **Deferred to Spec:** default to cd-shim degradation; revisit via a future opt-in ticket only if a consumer reports needing suppressed-picker auto-enter. (YAGNI now.)
3. **ADR-0003 reconciliation scope.** B fixes the 0003↔0006 contradiction by removing the foreign write — does ADR-0003 need an amendment note, or does narrowing ADR-0006 suffice? **Deferred to Spec:** append a one-line reconciling note to ADR-0003; spec to confirm wording.
4. **Lifecycle terminus (per the user's Clarify choice "decide at spec approval").** At the spec-approval gate, the recommendation (B) and its blast radius are presented and the user decides: implement now in this lifecycle / split implementation into a follow-up ticket / close (no path here is "status quo", so close is unlikely). **Deferred to the spec-approval surface by user instruction.**
