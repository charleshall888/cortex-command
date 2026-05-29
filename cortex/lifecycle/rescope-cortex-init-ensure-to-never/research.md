# Research: Rescope `cortex init --ensure` to never write `~/.claude/` (#273)

> Scope anchor (clarified intent): make the **in-session** `cortex init --ensure`
> path (invoked by `cortex-lifecycle-init-ensure`) never attempt any `~/.claude/`
> write. Marker-present → refresh `cortex/` only (repo-scope, sandbox-allowed).
> Marker-absent → refuse with exit 2 + a stderr directive pointing the user to
> terminal `cortex init`. **Terminal `cortex init` is unchanged** — it still writes
> the `~/.claude/` grant, because a user who typed it in their terminal consented;
> an in-session AI helper has not. The blocked in-session write currently forces a
> `dangerouslyDisableSandbox: true` retry, which is a deal-breaker first-contact UX.

## Codebase Analysis

### In-session entry point and its three `~/.claude/` touches
`cortex_command/init/handler.py:129-240` `_run_ensure()` is the `--ensure` body. Three calls touch `~/.claude/` (all with `home=None` → real `~/.claude/`):
- `settings_merge.validate_settings(home)` — **handler.py:163** — reads/validates `~/.claude/settings.local.json` and creates the `~/.claude/` dir + lockfile (pre-flight).
- `settings_merge.register(repo_root, cortex_target, home=home)` — **handler.py:233** — WRITES `~/.claude/settings.local.json` (`sandbox.filesystem.allowWrite += <repo>/cortex/`). **This is the write the sandbox blocks.**
- `settings_merge.unregister_matching_in_place("cortex-worktrees", home=home)` — **handler.py:238** — WRITES `~/.claude/settings.local.json` (legacy `cortex-worktrees` entry migration).

The actual file mutation lives in `cortex_command/init/settings_merge.py` (`register()` ~:136-205, `unregister_matching_in_place`, `validate_settings`), targeting `~/.claude/settings.local.json` via `_settings_path()` (:53-60), flock at `~/.claude/.settings.local.json.lock`. `_run_ensure` only *calls* these. `cortex_target = str(repo_root / "cortex") + "/"` (handler.py:160) — absolute path, trailing slash.

### Five-case dispatch (handler.py:173-227) — what changes
- **(i)** marker present + hash match → `return 0` early (no global write today). **UNCHANGED.**
- **(ii)** marker present + hash mismatch → `scaffold.scaffold(...)` + `write_marker(refresh=True)`, then falls through to post-dispatch register at :233-238. **CHANGE:** keep the `cortex/` refresh; drop the global register/unregister.
- **(v)** marker present, `init_artifacts_hash` missing, `cortex_version` present (R8 recovery) → same as (ii). **CHANGE:** same as (ii).
- **(iii)** marker absent + `cortex/` absent-or-empty → today **bootstraps** (`scaffold` + `write_marker(refresh=False)`), then registers. **CHANGE:** replace bootstrap with **refuse → exit 2 + directive** to run terminal `cortex init`.
- **(iv)** marker absent + `cortex/` has content → `scaffold.check_content_decline()` raises → exit 2 (R19 foreign-content protection). **UNCHANGED** (already refuses); message may be kept distinct from case (iii).

Post-dispatch block (handler.py:229-238) runs for cases ii/v (and today iii): `ensure_gitignore` + `ensure_claude_md_authorization` are **repo-scope** writes (keep — sandbox-allowed under repo root); `register` + `unregister_matching_in_place` are the **`~/.claude/` writes to REMOVE**.

### Terminal `cortex init` — unchanged
`handler.py:438-535` standard path short-circuits `--ensure` at :445 (`if args.ensure: return _run_ensure(args)`). The terminal path keeps Step 7 `settings_merge.register(...)` (~:528) and Step 7b `unregister_matching_in_place` (on `--update`). So the `~/.claude/` grant is still created — by the user-typed terminal command. Only the in-session helper stops writing it. This is the consent boundary the ticket encodes.

### Lifecycle wiring — halt-on-non-zero already exists
`skills/lifecycle/SKILL.md:128`: "Run `cortex-lifecycle-init-ensure` before advancing to Step 3. If the command exits non-zero, halt and surface its diagnostic to the user — do not proceed to phase execution." **The halt-on-non-zero contract is already in place**, so the new marker-absent exit-2 routes through it automatically. The substantive new work is the handler's exit-2 *directive message*, not new SKILL.md control flow. Canonical source is `skills/lifecycle/SKILL.md`; `plugins/cortex-core/skills/lifecycle/SKILL.md` is an **auto-generated mirror** (edit canonical only; mirror regenerates via the dual-source pre-commit hook). The ticket's touch-point citing the plugin mirror should be redirected to the canonical path.

`cortex_command/lifecycle/init_ensure.py` (`cortex-lifecycle-init-ensure`) delegates to `handler.main()` and passes exit codes through (0 success/no-op, 2 user-correctable, 1 unexpected). It already returns 2 for the worktree-attached refusal; the new marker-absent refusal reuses the same exit-2 contract.

### Dependent spec — must be amended (deliberate contract revision)
`cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/spec.md` (`status: complete`):
- R4 acceptance #1 (spec.md:28): "`cortex init --ensure` in a clean scratch repo (no `cortex/`) exits 0 and writes `cortex/.cortex-init`." #273 **reverses** this → exit 2 refuse.
- Why (spec.md:5): "Brand-new clean repos (no `cortex/` directory) also bootstrap automatically on first `/lifecycle` invocation." #273 reverses this clause.
- R5 (marker-absent + `cortex/`-has-content → R19 decline) is **preserved**.
Amend inline with rationale + #273 commit linkage (the ticket sanctions inline amendment OR follow-on lifecycle).

### Docs
- `README.md:27` "# 3. OPTIONAL - In each project where you want cortex active." (with `cortex init` at :30) — remove the OPTIONAL framing for `cortex init`: terminal `cortex init` becomes a **required first step** because in-session bootstrap is gone. (README:25's OPTIONAL is the *overnight plugin* — leave it.)
- `docs/index.html:6656-6671` — the cortex-core "required · start here" block (:6656) currently leads `/plugin install cortex-core` → `/lifecycle` (:6659); `cortex init` appears only at :6671 as a sub-note of the *overnight* block. Surface `cortex init` as a required step before `/lifecycle` in the cortex-core start-here path.
- `CLAUDE.md:5` ("cortex init additionally registers the repo's `cortex/` umbrella path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array …") stays **accurate for terminal `cortex init`** (unchanged) — no lockstep edit strictly required; an optional clarifying note that in-session `--ensure` does not perform this write.

### Tests
- `cortex_command/init/tests/test_handler_ensure.py` (ticket cites :517-545, `test_r8_bundle5`, case-iii expectation): case (iii) flips from bootstrap/exit-0 to refuse/exit-2. Any test asserting `--ensure` writes `~/.claude/settings.local.json` flips to asserting **no** `~/.claude/` write. New test for the marker-absent directive + exit code.

## Web Research
Claude Code settings/sandbox precedence (code.claude.com/docs/en/sandboxing, /settings — verified by docs agent):
- The sandbox **denies writes to Claude Code's `settings.json` files at every scope** and to the managed-settings dir; `~/.claude/` is outside the repo CWD, and the default sandbox write-scope is CWD + subdirs + explicit `allowWrite`. So an in-session sandboxed Bash invocation of `cortex init --ensure` is denied when it calls `register()`/`validate_settings`/`unregister`, forcing the `dangerouslyDisableSandbox` retry the ticket targets. **Premise confirmed.**
- Repo-scope writes (scaffolding under `<repo>/cortex/`, `<repo>/CLAUDE.md`, `<repo>/.gitignore`) are under CWD → sandbox-allowed with no grant. So the marker-present refresh path needs no `~/.claude/` access. ✓
- `sandbox.filesystem.allowWrite` IS honored from project-local `.claude/settings.local.json` and merged (concatenated) across scopes — relevant background, but NOT needed for #273, since the grant continues to be written by terminal init to `~/.claude/`.

## Requirements & Constraints
- `cortex/requirements/project.md` "Defense-in-depth for permissions": settings.json ships minimal allow; overnight runs `--dangerously-skip-permissions`; **sandbox is the critical surface.** #273 strengthens the in-session posture — no AI-driven sandbox bypass on first contact.
- ADR-0003 "Per-repo sandbox registration": records that `cortex init` writes the `cortex/` grant to `~/.claude/settings.local.json`. #273 does **not** change this for terminal init, so **ADR-0003's decision stands — no supersession/amendment needed.** (ADR-0003 has no "Revisit when" clause; an earlier framing that claimed one was incorrect.)
- Convention: edit canonical `skills/lifecycle/SKILL.md`; `plugins/cortex-core/` mirror regenerates via pre-commit (`just check-dual-source` / dual-source drift test).
- Exit-code contract (handler.py:24-38): 0 success/no-op, 2 user-correctable gate failure, 1 unexpected. Marker-absent refuse uses exit 2 (consistent with worktree-attached and R19 refusals).
- The auto-apply spec is `status: complete`; the ticket explicitly sanctions amending it as a deliberate contract revision.

## Tradeoffs & Alternatives
The ticket fixes the high-level design (refresh-only + refuse-exit-2; terminal init unchanged). The remaining choices are mechanism-level:
- **Marker-absent (clean repo) handling**: (A) refuse with exit 2 + directive [ticket's choice] vs (B) bootstrap but skip the global write. **(B) rejected** — bootstrapping `cortex/` in-session without the grant leaves a half-set-up repo whose grant the AI cannot create, re-introducing prompts and muddying the consent boundary. **(A) chosen.**
- **SKILL.md change**: (A) none — :128 already halts on non-zero [likely sufficient] vs (B) add a one-line note that exit-2 means "run terminal `cortex init`, then re-run". **Lean (B-lite)**: a clarifying note so the halt reads as expected-first-contact, not a bug; rely on the handler's directive for the actionable text.
- **auto-apply spec**: (A) inline amendment of R4#1 + Why [ticket's lean] vs (B) follow-on lifecycle. **Lean (A)** — small, tightly coupled to #273.
- The drift-era "where should the grant live" comparison (repo-local vs committed vs global) is **moot**: the grant stays in `~/.claude/` via terminal init.

## Adversarial Review
- **First-contact halt must be actionable.** New flow: fresh repo → `/plugin install cortex-core` + `/lifecycle` → `--ensure` exits 2 → lifecycle halts. If the stderr directive isn't crystal-clear ("run `cortex init` in your terminal, then re-run `/lifecycle`"), this reads as a broken tool — the very distrust the ticket is trying to remove. Mitigation: precise directive (OQ2) + README/landing telling users to run `cortex init` first (OQ5). **Highest-risk surface.**
- **Removing `validate_settings` removes a pre-flight** that validated `~/.claude/settings.local.json` shape. Since `--ensure` no longer writes that file, the pre-flight is moot for `--ensure`; terminal init retains its own. No regression.
- **Refresh no longer re-registers the grant.** If a future cortex version changes the `allowWrite` entry *shape* (the shape `b"cortex/"` is part of the init-artifacts hash per auto-apply R1), in-session `--ensure` will refresh `cortex/` but cannot apply the new grant — only terminal `cortex init --update` can. Acceptable and consistent with the consent boundary; note as a known edge in the spec.
- **CI / read-only `~/.claude`** ceases to be a `--ensure` failure surface entirely (it no longer touches `~/.claude/`) — a net simplification.
- **Marker-present + drift in a sandboxed session**: case (ii) scaffolds `cortex/` (repo-scope, allowed) → works in-session with no bypass. ✓
- **Overnight**: independent of the global grant — per-spawn `--settings` tempfiles are authoritative (`cortex_command/overnight/sandbox_settings.py`; allow-list = worktree path + 6 risk-targeted writers; never reads `~/.claude/settings.local.json`). Unaffected. ✓

## Open Questions
- **OQ1 (SKILL.md scope)**: Does the lifecycle skill need any edit beyond the existing halt-on-non-zero at :128? *Deferred — resolved in Spec.* Lean: a one-line clarifying note + ensure the handler's exit-2 directive is actionable; no new control flow.
- **OQ2 (directive message)**: Exact stderr wording for the marker-absent (clean-repo) refusal, distinct from the R19 foreign-content message. *Deferred — resolved in Spec with the user.*
- **OQ4 (auto-apply spec)**: Amend R4#1 + Why inline vs follow-on lifecycle. *Deferred — resolved in Spec.* Lean: inline.
- **OQ5 (docs placement)**: Exact `README.md:27` edit and `docs/index.html` placement for the now-required terminal `cortex init`. *Deferred — resolved in Spec.*

## Considerations Addressed
- *"CLAUDE.md's intro documents the global-write behavior and must be updated in lockstep when the global write is removed."* — **Reclassified**: under the actual design, terminal `cortex init` retains the global write, so `CLAUDE.md:5` stays accurate; at most an optional clarifying note that in-session `--ensure` does not perform it. Not a required lockstep edit. (The consideration was framed against a drifted "remove the write entirely" reading.)
- *"The overnight redundancy claim must be verified by confirming no overnight code path relies on the inherited persistent global grant rather than the per-spawn settings tempfile."* — **Confirmed**: overnight builds a self-contained per-spawn `--settings` tempfile (`cortex_command/overnight/sandbox_settings.py`) and never reads the persistent `~/.claude/settings.local.json` for the umbrella write; the in-session change does not affect overnight (and terminal init still writes the grant regardless).
