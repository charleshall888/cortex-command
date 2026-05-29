# Defense-of-current-design

## Per-action audit

`cortex init`'s `_run()` path performs nine ordered operations; `_run_ensure()` mirrors the same set with a hash-compare gate. Each is auditable for load-bearing value.

### A. Repo-root resolution + submodule refusal (R2, R3)

[handler.py:74-99] runs `git rev-parse --show-toplevel` and `--show-superproject-working-tree`. **What it does:** canonicalizes the target so every downstream operation pins the same path (closes a TOCTOU window — handler.py:101-105 names this explicitly). **What breaks if removed:** scaffold writes land at an arbitrary CWD relative path, and the settings-merge registration would point at a path that may not be the actual repo root. Submodule writes could pollute the parent superproject's `cortex/`. **Load-bearing.**

### B. Symlink-safety gate (R13)

[scaffold.py:207-267] resolves `cortex/` against the canonicalized repo root and refuses if it escapes. **What it does:** prevents an attacker-controlled symlink at `<repo>/cortex` from redirecting scaffold writes outside the repo. **What breaks if removed:** in a malicious repo (cloned via copy-paste from a hostile source), `cortex init` could materialize templates *outside* the repo root — including overwriting files in `~/` or the parent directory. **Load-bearing for adversarial-clone safety**, defensible-accidental for the typical "I just `git init`'d this" workflow.

### C. Malformed-settings pre-flight (R14)

[settings_merge.validate_settings] runs before scaffold writes. **What it does:** validates `~/.claude/settings.local.json` shape before the scaffold mutates the consumer repo. **What breaks if removed:** a malformed settings file causes the scaffold to half-succeed — repo files get written, then the settings-merge step crashes at write time, leaving the user with a scaffolded repo and a corrupt settings file. The pre-flight transforms this into a clean exit-2 with the original settings untouched. **Load-bearing for atomicity of the user-facing operation.**

### D. Decline gates (R6, R19)

[scaffold.py:162-204] — `check_marker_decline` (refuses if `.cortex-init` already exists) and `check_content_decline` (refuses if `cortex/` has content but no marker). **What it does:** prevents `cortex init` from clobbering an existing cortex-managed repo without `--force`, and prevents bootstrap into a directory where a non-cortex tool may already be writing under `cortex/`. **What breaks if removed:** repeat `cortex init` overwrites in-flight user edits; cortex misidentifies a foreign repo with a `cortex/` subdirectory as un-initialized and scaffolds over it. **Load-bearing for idempotency and non-cortex-repo protection.**

### E. Scaffold (5 templates) [handler.py:466-501; scaffold.py:312-365]

Materializes `cortex/lifecycle.config.md`, `cortex/backlog/README.md`, `cortex/lifecycle/README.md`, `cortex/requirements/project.md`, and (separately) splices `claude_md_authorization.md` into CLAUDE.md. **What it does:** establishes the on-disk shape consumed by every lifecycle, refine, backlog, and overnight code path. **What breaks if removed:** see §"Scaffold load-bearing audit" below — `lifecycle.config.md` is genuinely runtime-read and required by [overnight/cli_handler.py:58], [lifecycle_config.py:50,92], multiple lifecycle phase references; `requirements/project.md` is read by [skills/critical-review/SKILL.md:37], [skills/lifecycle/references/load-requirements.md:9,13]. The two README files are documentation-only.

### F. `.gitignore` append [handler.py:505; scaffold.py:552-621]

Appends `cortex/.cortex-init`, `cortex/.cortex-init-backup/`, `.claude/worktrees/` idempotently. **What it does:** keeps per-machine onboarding state (`.cortex-init` marker), backup artifacts (`.cortex-init-backup/`), and per-feature git worktrees (`.claude/worktrees/`) out of the user's commits. **What breaks if removed:** the user commits per-machine `.cortex-init` JSON (cross-machine drift, false-positive in CI), commits hundreds of backup directories on every `--force`, and commits worktree pollution on every `/cortex-core:lifecycle` implement run. **Load-bearing — the `.claude/worktrees/` entry in particular is non-cosmetic** because the lifecycle skill creates that directory unconditionally on every interactive worktree run.

### G. CLAUDE.md fence splice [handler.py:514; scaffold.py:678-757]

Inserts `<!-- cortex-managed: lifecycle-worktree-auth version=N -->` block carrying the authorization clause body. **What it does:** satisfies the live `EnterWorktree` tool schema's project-instructions gate so that `/cortex-core:lifecycle` can auto-enter interactive worktrees without firing a per-call picker. **What breaks if removed:** every `EnterWorktree` invocation falls back to the `cd`-shim path [skills/lifecycle/references/implement.md:193-195]. The cd-shim still works, but the auto-enter benefit collapses: `EnterWorktree`'s session-state cache-clear (system prompt sections, memory files, plans directory) does not fire, so the orchestrator session retains stale context after entering the worktree [implement.md:197]. **Load-bearing for the steady-state `branch-mode: worktree-interactive` default**; convenience for users who haven't opted into that mode.

### H. Settings registration [handler.py:520; settings_merge.py:136-205]

Additively appends `<repo>/cortex/` to `~/.claude/settings.local.json::sandbox.filesystem.allowWrite` under `fcntl.flock`. **What it does:** authorizes Claude Code sessions and the overnight runner to write under `cortex/` without per-call sandbox prompts. **What breaks if removed:** see §"ADR-0003 threat-model defense" below.

### I. Stale "cortex-worktrees" expunge (migration) [handler.py:528-529]

Only fires on `--update`. **What it does:** removes leftover allowWrite entries from a pre-Phase-3 version of cortex that registered worktree-base paths. **What breaks if removed:** existing users carry harmless cruft in their settings file. **Convenience-only**; deletable once the migration window closes.

`_run_ensure()` [handler.py:129-240] adds three structural gates on top of the standard path: a `CORTEX_AUTO_ENSURE=0` opt-out [143], a worktree-attached refusal [150, 243-291] mirrored from the skill-helper as defense-in-depth (intentional duplication per spec R11), and an install-in-progress lock-check [294-334] that polls a marker for up to 5 seconds. **Load-bearing for the skill-helper invocation path** that calls `cortex init --ensure` before every lifecycle phase; without these, an upgrade-in-progress race could corrupt the scaffold during installation.

## ADR-0003 threat-model defense

ADR-0003 [0003-per-repo-sandbox-registration.md:7] frames the registration as "the only write cortex-command makes outside its own tree" and rejects two alternatives: machine-wide setup and no-carve-out.

**The actual threat being defended against is not malicious code — it is workflow degradation under sandbox prompts.** The ADR's stated cost of the "no carve-out" alternative is concrete: "interactive sessions and overnight runs [would] either prompt on every write (defeating overnight autonomy) or run with `--dangerously-skip-permissions` for ordinary work (eroding the defense-in-depth posture that makes sandbox the critical surface)." [0003:12]

This framing is honest, but worth steel-manning more carefully. The overnight runner writes to `cortex/lifecycle/sessions/`, `cortex/lifecycle/<feature>/events.log`, and emits state every few seconds across multi-hour sessions. Without a carve-out, **either** the user pre-authorizes `--dangerously-skip-permissions` (which lifts the sandbox on the *entire* writable surface, not just `cortex/`) **or** the runner stalls on every Bash hook write waiting for an interactive prompt that no human is present to answer. The "defense-in-depth" gain is not abstract: it scopes the carve-out to a narrow umbrella path (`<repo>/cortex/`) rather than the global escape hatch. **A user who would otherwise run with the global skip flag is materially safer with a narrow per-repo registration**, because hostile code running in the session can write under `cortex/` (which is gitignored) but cannot reach `~/.ssh/`, `~/.aws/credentials`, or the parent project's source tree.

**Was "no carve-out" properly costed?** Partially. The ADR's framing assumes the user wants overnight autonomy. For a user who only runs interactive sessions and is willing to click through prompts, the carve-out has no net benefit over the prompt path. **But interactive sessions also touch `cortex/`** — every `/cortex-core:lifecycle` invocation writes `events.log`, `research.md`, `spec.md`, etc. Without registration, every one of those writes prompts the user. The discovery-phase pattern (3-5 parallel research agents each appending to a research artifact) becomes uninhabitable.

**The "sketchy to new adopters" concern is real but mis-targeted.** New adopters reading the `~/.claude/settings.local.json` write log see one entry of the form `"/<their-repo>/cortex/"` added to an `allowWrite` array. That's exactly what they expect a per-repo sandbox carve-out to look like — narrower than `--dangerously-skip-permissions`, locally scoped, transparently named after a directory they just created. The legitimate concern is **discoverability of the write** (does the user know what cortex did?), not the write itself. A `cortex init` summary line on stdout naming each surface — "registered <repo>/cortex/ in ~/.claude/settings.local.json allowWrite" — would solve that without changing the write surface.

**Defensible.**

## ADR-0006 schema-binding verification

The live `EnterWorktree` schema as of May 2026 still constrains the tool to "explicitly instructed [...] either by the user directly, or by project instructions (CLAUDE.md / memory)." [verified via WebSearch and WebFetch against `github.com/Piebald-AI/claude-code-system-prompts/blob/main/system-prompts/tool-description-enterworktree.md`, 2026-05-28; exact quote: *"Use this tool ONLY when explicitly instructed to work in a worktree — either by the user directly, or by project instructions (CLAUDE.md / memory)."*]

ADR-0006's binding holds. The `.claude/cortex-authorizations.md` sibling-file alternative remains rejected for the same reason cited in the ADR: a sibling file is not CLAUDE.md and not memory, and the live schema names only those two surfaces [0006:42]. A memory-file write would also satisfy the gate [0006:44, deferred alternative], but CLAUDE.md was selected because it is the canonical project-instructions surface a contributor reads first — memory is less discoverable, and the version-fence pattern is harder to verify in a per-session memory file than in a checked-in `CLAUDE.md`.

The CLAUDE.md fence is **load-bearing for any feature using `branch-mode: worktree-interactive` as the suppressed-picker default**, which is the convergence target per [implement.md:19-99]. It is convenience-only for users who never enable that mode or who explicitly fire the picker each time.

## Scaffold load-bearing audit

| Template | Runtime read by | Verdict |
|---|---|---|
| `cortex/lifecycle.config.md` | [overnight/cli_handler.py:58] (synthesizer gate), [lifecycle_config.py:50,92] (branch-mode, commit-artifacts), [skills/lifecycle/references/complete.md:9-13], [implement.md:32], [plan.md:17], [post-refine-commit.md:16], [specify.md:9], [critical-review/SKILL.md:38] (project-type prefix), [morning-review/references/walkthrough.md:88,108,144,187,607-609] (demo-command), [overnight/prompts/orchestrator-round.md:235] | **Load-bearing.** Multiple runtime readers across overnight + interactive paths. Removing it forces every consumer to ship its own fallback. |
| `cortex/requirements/project.md` | [critical-review/SKILL.md:37,40,42], [skills/lifecycle/references/load-requirements.md:9,13], [skills/lifecycle/references/review.md:81], [skills/requirements/SKILL.md:9], [skills/requirements-write/SKILL.md:11,16,24], [skills/requirements-gather/SKILL.md:37,60] | **Load-bearing as a path** (skills read `cortex/requirements/project.md` directly); the **scaffolded body is a TODO stub**, not load-bearing content. The shipped template is convenience-only, but the directory must exist for `requirements-write` to land synthesis output without scaffolding it lazily. |
| `cortex/backlog/README.md` | None found in runtime code. Referenced only in research/archive and decomposed docs [research/archive/.../research.md:264,295]. | **Documentation-only.** Convenience for human contributors reading the directory; no skill or hook reads it. |
| `cortex/lifecycle/README.md` | None found in runtime code. Same as above. | **Documentation-only.** |
| `claude_md_authorization.md` | [scaffold.py:624-634] (`_read_claude_md_auth_template`) | **Load-bearing.** Not scaffolded to disk; spliced into consumer CLAUDE.md by `ensure_claude_md_authorization`. Required by `EnterWorktree` schema (per ADR-0006). |

**Honest summary:** 3 of 5 templates are load-bearing or carry load-bearing structural meaning (the path matters even when the body is a stub). 2 of 5 (`backlog/README.md`, `lifecycle/README.md`) are pure documentation that could be moved to `docs/` or omitted entirely without runtime impact. The `.cortex-init` marker is load-bearing for `--ensure`'s provenance check [scaffold.py:485-549].

## Verdict

Categorizing each current init action:

**Load-bearing (removing breaks documented runtime behavior):**
- A. Repo-root resolution + submodule refusal — TOCTOU + correctness
- B. Symlink-safety gate — adversarial-clone protection
- C. Malformed-settings pre-flight — atomicity of operation
- D. Decline gates (R6, R19) — idempotency + non-cortex-repo protection
- E1. Scaffold `cortex/lifecycle.config.md` — read by 7+ runtime paths
- E2. Scaffold `cortex/requirements/project.md` (path, not body) — required by `requirements-write`'s write target + critical-review's project-context read
- E3. CLAUDE.md fence splice — required by live `EnterWorktree` schema for auto-enter
- F. `.gitignore` append (esp. `.claude/worktrees/`) — prevents per-feature worktree pollution
- H. Settings registration — prevents overnight stall and lifts the user off `--dangerously-skip-permissions`
- E4. `.cortex-init` marker — required by `--ensure`'s provenance discrimination

**Defensible-accidental (justifiable but with weaker evidence):**
- E5. `claude_md_authorization.md` template file shipped in the package — could be inlined as a Python string constant; shipped as a file because the body is large and editing prose in `.md` is more pleasant than in escaped Python literals. Defensible on author-ergonomics grounds.
- I. Stale "cortex-worktrees" expunge migration — defensible during the migration window, deletable after.

**Convenience-only (no runtime consumer; removing affects only contributor docs):**
- E6. `cortex/backlog/README.md` template — could be moved to `docs/` or shipped at first `cortex-create-backlog-item` run.
- E7. `cortex/lifecycle/README.md` template — same.

**Honest concession:** the scope-reduction discovery is correctly aimed at the **stub README templates** (E6, E7) and at **discoverability of writes** (the `~/.claude/` write is fine, but `cortex init` should narrate what it did). The `~/.claude/settings.local.json` write itself is genuinely load-bearing for the overnight runner's autonomy and for any interactive session that uses the lifecycle skill — removing it would force `--dangerously-skip-permissions` on the entire surface, which is the *less* defense-in-depth posture, not more. The CLAUDE.md fence is similarly load-bearing and bound to an external schema we don't control.

The defensible scope reduction is: drop the two stub READMEs, add a stdout summary of every write, and leave the four protected surfaces in place.
