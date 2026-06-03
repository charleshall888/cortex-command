# Research: Stop `cortex init` from writing the EnterWorktree worktree-authorization clause into consumer CLAUDE.md

**Clarified intent (Clarify handoff):** `cortex init` currently splices a cortex-managed `EnterWorktree` worktree-authorization fence into a repo's `CLAUDE.md` (ADR-0006). The user's directive — verbatim — is "we don't want cortex to touch **other repos'** CLAUDE.md files." The chosen mechanism in Clarify was "drop auto-enter; picker-only, all repos uniformly." Research was tasked to verify the load-bearing assumption (does a picker selection authorize `EnterWorktree`?), map the removal blast radius, design migration, and explore alternatives symmetrically.

**Headline finding (changes the scope question):** Auto-enter via `EnterWorktree` is **not a proposal — it is a complete, high-criticality feature shipped ~2 weeks ago** (#249 `complete`, #250 `complete`, ADR-0006 `accepted`; commits `379f9f49`/`64b1dcbb`/`195c3a9c`/`d5578443`). "Drop auto-enter, all repos" therefore **reverses recently-shipped work and supersedes an accepted ADR.** The user's literal complaint ("other repos") is precisely solved by a **narrower** fix that does *not* throw the feature away. This tension is the critical open question below — it must be resolved before Spec.

---

## Codebase Analysis (removal blast radius)

Only **one** `EnterWorktree` call site exists in the whole repo: `skills/lifecycle/references/implement.md` §1a step-v. Worktree *creation* never used the tool — per ADR-0004 the lifecycle creates worktrees via direct `git worktree add` (the `--worktree`/`WorktreeCreate` bypass is permanent). `EnterWorktree` was *only* the orchestrator's clean CWD-switch optimization.

Full-removal demolition map (verdict = delete unless noted):

- **`cortex_command/init/scaffold.py`**: `ensure_claude_md_authorization()` (678–757), `revoke_claude_md_authorization()` (760–817), `_find_claude_md_auth_fence()` (649–675), `_render_claude_md_auth_block()` (637–646), `_read_claude_md_auth_template()` (624–634), `live_interactive_sessions()` (841–890, only consumed by revoke pre-check). Constants `_CLAUDE_MD_AUTH_TEMPLATE` (99), `_CLAUDE_MD_AUTH_VERSION` (106), fence sigils/regex (110–117). **Modify**: remove `"claude_md_authorization.md"` from `_HASH_INPUT_TEMPLATES` (87), remove `h.update(str(_CLAUDE_MD_AUTH_VERSION)…)` (149), remove the `child.name == _CLAUDE_MD_AUTH_TEMPLATE` scaffold-copy skip (298–301), trim module docstring (31–43).
- **`cortex_command/init/handler.py`**: delete step-0b `--revoke-worktree-auth` branch (367–414), step-0c `--verify-worktree-auth` branch (416–445), step-6b call in `_run` (516–523) and in `_run_ensure` (247); trim docstrings (18–20, 551–570).
- **`cortex_command/cli.py`**: delete `--revoke-worktree-auth`/`--verify-worktree-auth` arg defs + help (≈896–939); shrink the init mutex group from 5 verbs → 3 (`--update`, `--unregister`, `--ensure`).
- **`cortex_command/init/templates/claude_md_authorization.md`**: delete file.
- **`skills/lifecycle/references/implement.md`**: rewrite §1a step-v (the verify-probe + `EnterWorktree(path=…)` + precondition probe) down to the **cd-shim entry** that already exists as the fallback (`cd $(cortex-worktree-resolve interactive/{slug})`); reword the §1 picker option (drop "auto-enters via EnterWorktree"). The §1 picker itself **stays**.
- **`skills/lifecycle/references/complete.md`** (≈181) + **`docs/internals/sdk.md`** (≈216): both reference `EnterWorktree`/`ExitWorktree` session-state as the live exit path — reword to the manual `cd` exit.
- **`CLAUDE.md`** (this repo, lines 83–89): the cortex-managed fence section.
- **Dual-source**: `implement.md`/`SKILL.md` are mirrored into `plugins/cortex-core/` by `just build-plugin`; the pre-commit drift gate fails if mirror is stale → edit canonical, run build-plugin, commit canonical+mirror together. `scaffold.py`/`handler.py`/`cli.py`/template ship in the wheel only (not mirrored).

## Web Research

- **EnterWorktree gate (verbatim, official docs + Piebald system-prompt mirror):** *"Use this tool ONLY when explicitly instructed to work in a worktree — either by the user directly, or by project instructions (CLAUDE.md / memory)."* Hard line: *"Never use this tool unless 'worktree' is explicitly mentioned by the user or in CLAUDE.md / memory instructions."*
- **`EnterWorktree` has "Permission Required: No"** — it is *not* gated by the settings `allow`/`deny` permission system, only by the prose condition above.
- **Worktree workflows can proceed entirely without `EnterWorktree`** — official docs document plain `git worktree add … && cd … && claude`, and the `claude --worktree` launch flag. This is authoritative: the cd path is a first-class, supported workflow.
- **clig.dev (CLI guidelines):** installers should *not* modify config they don't own without consent; *prefer creating a separate tool-owned file* over appending to a human-curated one. This is the strongest external argument **for** stopping the foreign-CLAUDE.md write.
- **Unconfirmed by any source:** whether a *picker label* containing "worktree" counts as the user "explicitly mentioning" it. Confidence: low.

## Requirements & Constraints

- **ADR-0003** (binding): *"the only write cortex-command makes outside its own tree"* is `~/.claude/settings.local.json`. Writing a fence into a **consumer** repo's CLAUDE.md breaches this; ADR-0006 documented the breach. Note: in cortex-command's **own** repo the fence lives in a file cortex owns, so the own-repo write is *not* an ADR-0003 violation. The violation is foreign-repo-specific.
- **ADR-0004**: worktree creation via direct `git worktree add` (bypass is permanent); `EnterWorktree` was the orchestrator CWD-switch only. The cd-shim is the documented degradation.
- **ADR emission rule (`cortex/adr/README.md`)**: three-criteria gate — *hard-to-reverse* ∧ *surprising-without-context* ∧ *real-trade-off* (all three). Supersession = ADR-0006 `status: superseded` + `superseded_by: NNNN` + a new ADR. (Reversing 0006 itself clears the three-criteria gate, so the reversal is itself ADR-worthy.)
- **Kept-pauses parity** (`tests/test_lifecycle_kept_pauses_parity.py` + `skills/lifecycle/SKILL.md`): the §1 branch-picker pause (`implement.md:49`) stays; a conditional-pause structural marker (`cortex-lifecycle-branch-mode`) within ±35 lines is required *if* the entry stays conditional. Inventory and test move together.
- **Authoring policy**: What/Why-not-How; no new MUST without an evidence artifact.

## EnterWorktree Authorization Model (the load-bearing question, adjudicated)

Two agents reached opposite conclusions; the divergence is real and resolvable:

- **claude-code-guide:** "NO (95%)" — a *clicked* picker option is not the user "explicitly mentioning" worktree; the gate wants the user to type/say it, or a standing CLAUDE.md/memory clause. Verdict: picker-only "not viable" *if you still intend to call `EnterWorktree`*.
- **Tradeoffs + Codebase:** the question is **moot** — dropping auto-enter means the implement phase **stops calling `EnterWorktree` entirely** and uses the cd-shim, which calls no gated tool and needs no authorization.

**Adjudication:** Both are right about different designs. The correct reading of "picker-only" is **cd-shim-only (P2)**: remove the `EnterWorktree` call, route the picker selection to *create worktree + `cd` into it*. In P2 the gate question never arises. The design must **not** rely on a picker click authorizing `EnterWorktree` (P1) — that path is unverified and the claude-code-guide evidence says it likely fails. The cd-shim is already shipped and is the existing fallback for every §1a failure, so P2's floor is real and exercised today (consumer repos with no fence already run on it).

**Cost of P2 (cd-shim), stated honestly (not correctness-equivalent):** the orchestrator session CWD stays at repo root — only Bash calls `cd` in; `EnterWorktree`'s cache-clear/session re-root does not happen; Edit/Write need absolute paths; no platform worktree-awareness. This is a **UX/ergonomics regression with zero correctness or data-loss risk.** Sub-agent `isolation:"worktree"` dispatch is unaffected (independently rooted regardless of entry mechanism), so the known interactive-worktree sub-agent instability is *orthogonal* — neither caused nor cured by this change.

## Tradeoffs & Alternatives

| Approach | Footprint | Keeps auto-enter? | ADR-0006 | Code delta | Churn risk |
|---|---|---|---|---|---|
| **A. Full-removal / cd-shim-only** (Clarify pick) | zero writes anywhere | **No** (removed everywhere incl. own repo) | superseded | large net deletion | **High** — reverses #249/#250 if auto-enter is wanted again |
| **B. Relocate to `.claude/memory/`** | one write into consumer `.claude/` | yes | amended | medium | rejected — "renamed CLAUDE.md"; literal auto-memory is Claude-owned + machine-local + non-portable |
| **C. Opt-in flag, default off** | **zero by default**; foreign repos untouched | **yes** (own repo opts in) | amended (narrowed) | keeps machinery + adds flag | **Low** — fixes the stated complaint, preserves the feature |

**Symmetric verdict:**
- **A is unconditionally *safe*** (failure mode = "auto-entry silently doesn't materialize; floor is the shipped cd-shim"), but it is the **maximal teardown**: it discards the own-repo auto-enter benefit and reverses recently-shipped, intended-permanent work.
- **C is the durable minimum for the *stated* problem.** The user's literal complaint is foreign repos ("other repos"). C makes the fence write opt-in/off-by-default → foreign repos are never touched (fixes the complaint + restores ADR-0003 for consumers), while cortex-command's own repo opts in and keeps auto-enter. Amends ADR-0006 rather than reversing it; no churn.
- **B is the weakest** — does not advance "stop writing outside cortex/," and the literal "memory/" surface the schema names is not a repo-portable, cortex-writable file.

**The choice between A and C hinges on one fact only the user knows: do they still want worktree auto-enter for cortex-command's own lifecycle work, or are they done with it (e.g., soured on the interactive-worktree instability)?** If wanted → C is durable, A is churn. If done with it → A is durable, C keeps dead-weight machinery.

## Migration & Rollout

- **Backward-compat is robust either way.** `implement.md` §1a routes *any* non-zero exit from `cortex init --verify-worktree-auth` (including an argparse "unknown argument" exit 2 after deletion) → skip `EnterWorktree` → cd-shim. The current prose (line 173) does **not** branch differently on exit 1 vs 2. So **immediate deletion of the verify/revoke subcommands is safe** — the migration agent's "keep one release" is over-cautious; an old plugin-mirror skill against a new CLI simply falls back to the cd-shim.
- **init-artifacts-hash flips** (template removed from `_HASH_INPUT_TEMPLATES` + version constant dropped) → one-time `cortex init --ensure` drift refresh on every marker-present consumer. This is the natural carrier for any fence cleanup.
- **Existing-fence cleanup (only relevant under A):** *leave-stranded* is the lower-risk default and is **already ADR-0006's accepted uninstall behavior** ("stranded fence has no runtime effect once no consumer survives"). It also best honors "don't touch CLAUDE.md" — *auto-remove would itself write to CLAUDE.md once* (the irony). If auto-remove is nonetheless chosen, scope it strictly to the cortex-managed fenced block (never user prose) and gate on `live_interactive_sessions` (skip-not-refuse). Recommendation: **leave-stranded**, document the one-line manual delete.
- **Versioning** is VCS-derived (`hatch-vcs`) + `auto-release.yml`; merging to main auto-bumps — no manual version edit.

## Test & Verification Surface

Full-removal (A) touches **5 test files** (adversarial corrected the under-count):
- **Delete:** `tests/test_init_claude_md_authorization.py` (11 tests), `tests/test_init_verify_worktree_auth.py` (6 tests), `tests/test_lifecycle_step_v_ordering.py` (pins the step-v order incl. `verify-worktree-auth`/`EnterWorktree(`), `tests/test_lifecycle_enterworktree_callsites.py` (requires every `EnterWorktree(` co-located with precondition tokens).
- **Modify:** `cortex_command/init/tests/test_handler_ensure.py` (drop `revoke_worktree_auth`/`verify_worktree_auth` from namespace builders), `cortex_command/lifecycle/tests/test_init_ensure.py:221-222` (the exact verb-set frozenset literal), `tests/test_init_artifacts_hash_inputs.py` (`_FENCE_TEMPLATE_NAME` + hash-input set), `cortex_command/lifecycle/init_ensure.py` (namespace stub).
- **Survives unchanged:** `tests/test_lifecycle_picker_label_pins_worktree.py` (the picker label still says "worktree").
- **New (the inverted invariant):** assert `cortex init` does **not** create/modify CLAUDE.md; assert the verify/revoke flags are gone from the CLI.
- **ADR-status assertions:** `tests/test_backlog_ready_render.py` and `tests/test_install_inflight_guard.py` reference ADR-0006 — check before flipping `accepted`→`superseded`.

Opt-in (C) is a smaller test delta: the existing fence tests stay (now exercised behind the flag), plus new "off-by-default → no CLAUDE.md write" and "flag-on → fence written" coverage.

## Adversarial Review (key challenges + adjudication)

- **Solution-horizon (highest risk):** A is potential **churn-then-revert** of #249/#250 (both `complete`, high) and reverses accepted ADR-0006. #250's framing is "decompose Approach A's surface and ship," i.e. the team wanted auto-enter — *unless* the user has since decided otherwise. CLAUDE.md's Solution Horizon principle requires surfacing the durable alternative (C) with the tradeoff rather than defaulting to the maximal teardown. **This is the gating decision.**
- **cd-shim floor is real** (verified at `implement.md:193`) but **degraded, not equivalent** (orchestrator CWD divergence) — spec must state this as an accepted UX regression, not assert equivalence.
- **Live blast radius: clear** — only `main`, no `*.interactive.pid`. No in-flight session breaks.
- **Backward-compat:** immediate subcommand deletion is safe (any non-zero → cd-shim). Drop the one-release-deprecation.
- **Irony:** auto-remove writes to CLAUDE.md once → leave-stranded is more faithful to intent.

## Open Questions

1. **[GATING — must resolve before Spec] Scope: full-removal (A) vs. opt-in/off-by-default (C).** The user's literal complaint is foreign repos ("other repos"), which C fixes durably while preserving the shipped auto-enter feature; A additionally discards the own-repo benefit and reverses #249/#250 + ADR-0006. **Decision hinges on a fact only the user knows: is worktree auto-enter still wanted for cortex-command's own lifecycle work, or is the team done with it?** Clarify selected A under a framing that did not surface that auto-enter is a recently-shipped, accepted feature; this finding warrants re-confirmation.
2. **If A:** existing-fence cleanup = leave-stranded (recommended, zero CLAUDE.md write) vs. auto-remove-once. Resolved direction: leave-stranded.
3. **If A:** delete verify/revoke subcommands immediately (recommended, backward-compat-safe) vs. one-release deprecation. Resolved direction: immediate.
4. **Reconcile #249/#250 status** — full-removal must mark them superseded/wontfix rather than leaving `complete` tickets describing machinery that no longer exists (state-integrity).
5. **The cd-shim degradation** (orchestrator CWD divergence) — accept and document as a UX regression (recommended), or is clean session re-root a hard requirement (which would argue against A and for keeping `EnterWorktree` behind C's opt-in)?

## Considerations Addressed

- *Load-bearing picker-gate assumption* — **Resolved (reframed):** the correct design (P2/cd-shim-only) does not call `EnterWorktree`, so the gate question is moot; the design must not rely on picker-click authorizing the tool (unverified, likely fails per claude-code-guide).
- *Picker-only still invokes EnterWorktree vs. cd-shim* — **Resolved:** cd-shim only; no `EnterWorktree` call under full-removal.
- *Complete removal blast radius* — **Mapped** (Codebase + Test sections); single `EnterWorktree` call site; 5 test files; dual-source mirror sequencing noted.
- *Migration for existing fences* — **Addressed:** leave-stranded recommended (already ADR-0006's accepted policy); backward-compat via cd-shim fallback on any non-zero exit.
- *Symmetric alternative exploration* — **Addressed:** A/B/C evaluated; surfaced C (opt-in) as the durable minimum that the Clarify framing missed; B rejected with reasons.
- *ADR impact* — **Addressed:** reversing 0006 clears the three-criteria gate; supersede vs. amend depends on the A/C decision (A → supersede; C → amend/narrow).
