# Failure-of-alternative analysis

Adversarial review of a maximally-rescoped `cortex init` that writes only to `<repo>/cortex/` (no `~/.claude/settings.local.json`, no `<repo>/CLAUDE.md` fence, no `<repo>/.gitignore`). The brief is to actively find ways this rescoping fails. Where it actually survives my best attacks, I report that.

## Memory/ alternative: viability check

ADR-0006 deferred — not rejected — the option of writing the `EnterWorktree` authorization to `.claude/memory/` instead of `CLAUDE.md` [cortex/adr/0006-cortex-init-consumer-claude-md-authorization-surface.md:44]. I verified the live `EnterWorktree` schema (loaded via ToolSearch as of 2026-05-28):

> *"Never use this tool unless 'worktree' is explicitly mentioned by the user or in CLAUDE.md / memory instructions"* [EnterWorktree tool description, live schema, 2026-05-28]

So the schema text holds. But "memory" in that gate has a very specific meaning per the live Anthropic docs (2026-05-27 fetch of https://code.claude.com/docs/en/memory):

- **CLAUDE.md / CLAUDE.local.md / .claude/CLAUDE.md / .claude/rules/*** — written by you, loaded into every session.
- **Auto memory** — written *by Claude*, stored at `~/.claude/projects/<project>/memory/MEMORY.md`, machine-local, not in the repo.

The docs draw a sharp line: *"Auto memory is machine-local. All worktrees and subdirectories within the same git repository share one auto memory directory. Files are not shared across machines or cloud environments."*

This kills the "lift to memory/" alternative as a way to dodge `CLAUDE.md`:

1. **There is no repo-local `.claude/memory/` surface that loads into sessions.** The docs enumerate "Project instructions" as exactly `./CLAUDE.md` or `./.claude/CLAUDE.md` plus `.claude/rules/`. Auto-memory lives outside the repo, machine-local, written by Claude. Cortex-command writing into that path would be inappropriate (Claude owns that surface) *and* ineffective at team portability.
2. **A `.claude/rules/cortex-worktree-auth.md` lift is just a renamed CLAUDE.md.** It still creates a per-repo committed artifact outside `cortex/`. The "writes nothing outside `cortex/`" goal isn't satisfied.
3. **"Memory instructions" in the schema text most plausibly refers to CLAUDE.md-equivalent project memory, not auto-memory.** The schema text predates the 2026 auto-memory feature (auto memory requires v2.1.59+ per docs). Banking on an undocumented reading of a load-bearing gate is a bet I would not take.

**Schema evolution risk.** ADR-0006 explicitly contemplated re-litigation: *"A future variant landing the clause in `memory/` instead can be considered if `CLAUDE.md` appendation produces unexpected friction"* [cortex/adr/0006:44]. The deferral was conditional on observed friction, not on principle.

**Verdict for §1:** the memory/ alternative does not give us a path to "write nothing outside `cortex/`." Either we satisfy the gate (requires writing CLAUDE.md or `.claude/{rules,CLAUDE.md}`, all outside `cortex/`) or we abandon the gate (and the suppressed-picker auto-enter benefit). The dichotomy ADR-0006 named is intact.

## Maximally-rescoped init: runtime failures

The hypothetical: `cortex init` creates only `<repo>/cortex/` scaffold + marker. No `.gitignore`, no `CLAUDE.md` fence, no `~/.claude/settings.local.json`.

### First `/lifecycle` invocation in a fresh repo

**Failure 1: sandbox prompt storm.** Per ADR-0003, the umbrella `<repo>/cortex/` is registered into `allowWrite` precisely because *"interactive Claude Code sessions and the overnight runner both need to write under `cortex/` without per-call sandbox prompts"* [cortex/adr/0003-per-repo-sandbox-registration.md:7]. Without that registration, every Bash-routed write under `cortex/lifecycle/{slug}/` in an interactive session fires a sandbox-permission prompt. Lifecycle writes touch many distinct subpaths per session, and sandbox grants are path-based, so each new subpath is a fresh prompt. The user hits prompt storm exactly on first contact — the worst moment for friction.

**Failure 2: §1a `EnterWorktree` always fails the gate.** Per `skills/lifecycle/references/implement.md:173`, the auto-enter sequence runs `cortex init --verify-worktree-auth` and routes to a fallback `cd`-shim on non-zero exit. Under the rescoped init, the CLAUDE.md fence is never written, so `--verify-worktree-auth` always returns exit 1 (fence absent), and `EnterWorktree` is *never* called. The diagnostic surfaces each time: `EnterWorktree skipped: --verify-worktree-auth exit 1 (clause absent — run cortex init to restore)` [implement.md:193]. The lifecycle still works via cd-shim — but the entire ADR-0004 auto-enter design point is dead. Skip-rate: 100%.

**Failure 3: no in-session path-grant persistence carries this.** [premise-unverified: not-searched Claude Code's session-level sandbox persistence semantics]. Even if path consent persists session-to-session, each new repo, each new `cortex/lifecycle/{slug}/`, each new sub-agent worktree at `<repo>/.claude/worktrees/<task>/` is a fresh sandbox decision.

### Multi-hour session subpath surface

A representative implement-phase session touches at minimum:
- `cortex/lifecycle/{slug}/{research,spec,plan,review,index,preflight}.md` + `events.log`
- `cortex/lifecycle/sessions/{slug}.interactive.pid` [scaffold.py:863]
- `cortex/lifecycle/sessions/{session_id}/sandbox-deny-lists/` [docs/overnight-operations.md:491]
- `cortex/lifecycle/sessions/{session_id}/escalations.jsonl`
- `cortex/lifecycle/morning-report.md`
- `<repo>/.claude/worktrees/<task>/` per-sub-agent worktrees

The umbrella `<repo>/cortex/` grant was introduced specifically because *"a single umbrella cortex/ grant covers all cortex-managed state under the repo root"* [handler.py:517]. Without it, each subpath is a fresh decision.

### Overnight runner: does it need allowWrite registration?

This is the rescoped init's strongest survivable position. Overnight uses `--dangerously-skip-permissions`:

- `cortex_command/overnight/runner.py:1044` — `"--dangerously-skip-permissions"` in orchestrator spawn
- `cortex_command/overnight/seatbelt_probe.py:199` — same flag in the probe

Confirmed by requirements: *"Overnight runs `--dangerously-skip-permissions`; sandbox is the critical surface"* [cortex/requirements/project.md:52]. Per-spawn sandbox is built via `--settings` tempfiles [runner.py:1022–1031]; user-scope `allowWrite` is not load-bearing for overnight at all.

**Overnight survives the rescoped init.** The `~/.claude/settings.local.json` entry is load-bearing for *interactive* sessions only. The chicken-and-egg is squarely on the interactive surface.

### `.gitignore` absent — what gets accidentally committed?

The init's `.gitignore` append registers three targets [scaffold.py:71–75]:

```
cortex/.cortex-init
cortex/.cortex-init-backup/
.claude/worktrees/
```

- **`cortex/.cortex-init`** — JSON marker [scaffold.py:467–472]. Committing means every clone shows version+timestamp drift in git. Cleanliness wart.
- **`cortex/.cortex-init-backup/`** — backed-up content from `--force` overwrites. Harmless but bloats over time.
- **`.claude/worktrees/`** — *load-bearing*. Per `scaffold.py:69`: *"`.claude/worktrees/` holds per-feature git worktrees ... and must never be committed."* Committing this means embedding worktree filesystems including in-flight uncommitted work into git history. Real correctness failure mode.

**Mitigation against me:** the user notices on first `git status`. But "would notice" assumes attentive use; the rescoped init has decided not to ship a working default for the most common worktree-using workflow.

### CLAUDE.md fence absent — `EnterWorktree` user-visible failure

Covered above. Functionally degraded; not broken. The fallback path exists [implement.md:193]; rescoping just guarantees it always fires.

## Migration nightmares

Hypothetical: v2.14.x users have all four surfaces written; v2.15 stops writing some/all. What happens to stale artifacts?

### Stranded `~/.claude/settings.local.json` allowWrite entries

- **Behavior**: harmless. The sandbox check is "is this path in the allow list?", not "does the registering tool still want it?" Stale entries continue granting write access. No correctness failure.
- **Hygiene**: bloats `settings.local.json` over time. Existing `cortex init --unregister` [handler.py:347–357] handles cleanup; if v2.15 drops `--unregister`, users edit JSON by hand.
- **Conclusion**: not load-bearing for breakage.

### Stranded `CLAUDE.md` cortex-managed fences

ADR-0006 already accepts this state for uninstall: *"the stranded fence has no runtime effect because no consumer of the clause survives the uninstall"* [cortex/adr/0006:38].

Wrinkle: the fence carries `version=N` [scaffold.py:106]. v2.15 that no longer writes the fence won't increment the canonical version. Three subcases:

1. **v2.15 still ships `--verify-worktree-auth`** without writing the fence. Stale v1 fence → exit 0 (version matches). Works.
2. **v2.15 drops `--verify-worktree-auth`**. The implement.md probe runs it, gets "no such argument" → non-zero exit → routes to fallback. Auto-enter dead, lifecycle continues.
3. **v2.15 ships v2 fence semantics**. Stale v1 fences → exit 2 (stale) → routes to fallback. Same outcome.

All three are harmless or harmless-but-degraded. No data loss.

### Stranded `.gitignore` entries

Three entries. If v2.15 stops writing them but the worktree feature is still alive, *existing* entries continue to protect old users — beneficial stranding. If the worktree feature is removed too, the entries are dead config. Not a problem either way.

### Marker hash drift on upgrade

The `init_artifacts_hash` is computed over template bytes + `_GITIGNORE_TARGETS` + `_CLAUDE_MD_AUTH_VERSION` + `"cortex/"` [scaffold.py:120–151]. v2.15 dropping the fence shifts the hash; `cortex init --ensure` reports drift → additive scaffold. Migration is automated.

**Downgrade pathology**: v2.14 against a v2.15-initialized repo. Hash mismatch routes through `--update` [handler.py:174–207], which re-writes all four surfaces. Downgrade *silently resurrects* the fence on the consumer's CLAUDE.md and re-registers `allowWrite`. Not a correctness failure, but unintuitive: downgrading the tool *adds* artifacts the user thought were gone.

## Edge case enumeration

| # | Edge case | Failure mode | Severity | Mitigatable? |
|---|---|---|---|---|
| 1 | CI / headless | Per-call sandbox prompt blocks autonomously; no user to answer | High in CI | Yes — CI uses `--dangerously-skip-permissions` or mandates pre-granted paths; user-doc burden |
| 2 | Fresh clone by user B | Fence loads from committed CLAUDE.md (auto-enter intact); sandbox unregistered → prompt storm on cortex/ writes | Same as Failure 1 | Yes if B runs `cortex init`; rescoping defeats the purpose of avoiding that |
| 3 | Attached worktree | Refused at `handler.py:243–291` | Unchanged | Unchanged |
| 4 | Multi-repo same user, concurrent lifecycle | Each repo's `cortex/` is a fresh sandbox decision per session | High; multi-repo is common | Partial — batch-register verb possible |
| 5 | Downgrade v2.15-rescoped → v2.14-with-writes | Hash mismatch → v2.14 silently re-writes all four surfaces | Low correctness; high astonishment | No graceful path |
| 6 | Partial uninstall `uv tool uninstall cortex-command` | Stranded artifacts everywhere they were | Same as ADR-0006 | Same as today — `--revoke-worktree-auth` + `--unregister` pre-uninstall |
| 7 | EnterWorktree schema evolution | Schema-version drift; fence becomes unrecognized | Low; speculative | High — fence-version field is the pivot lever |
| 8 | Non-git directory | Refused at R2 [handler.py:81–82] | Unchanged | N/A |
| 9 | `cortex/` symlinks outside repo | Refused at R13 [scaffold.py:262–265] | Unchanged | N/A |

## Chicken-and-egg recurrence

User's framing: move `~/.claude/` writes into an opt-in verb like `cortex grant-permissions`. Does this dodge the chicken-and-egg or just relocate it?

The chicken-and-egg shape: from inside a Claude Code session, `cortex` is invoked via the Bash tool, which runs sandboxed. Writing to `~/.claude/settings.local.json` from a sandboxed Bash subprocess requires that path be in the allowWrite list — and that allowance has to come from somewhere. ADR-0003's resolution: `cortex init` runs at install time outside any Claude session, before the sandbox applies. The write is made from a non-Claude Bash session (the user's terminal post-`uv tool install`).

The opt-in verb has the same property: if run from the user's terminal post-install, it writes without sandbox interference. If run from inside a Claude session, the sandbox intercedes and the write fails with EPERM. The chicken-and-egg is **avoided** as long as the verb is documented as terminal-only with a stderr diagnostic on sandboxed invocation.

But: the practical effect is to trade a mandatory step for an optional step that materially degrades the experience if skipped. The chicken-and-egg is structurally resolved; the UX bet — that adopters will run the opt-in more readily than they'd tolerate the current automatic write — is behavioral, not technical. The current research dispatch is a fair venue to test it.

**Discoverability concern.** Today's `cortex init` is the canonical first command per `docs/setup.md`. The opt-in verb needs equally prominent documentation *and* a runtime diagnostic in the `EnterWorktree skipped` path naming the verb. The fallback diagnostic already points users to `cortex init` to restore [implement.md:193]; updating it to name `cortex grant-permissions` is a one-line change.

## Verdict on rescoping

**Where the alternative is hopeless:**

- The `.claude/memory/` lift as a dodge does not work. Auto-memory is machine-local + Claude-authored. Repo-local persistent-instruction surfaces are exactly `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md`, and `.claude/rules/*` — all outside `cortex/`. Either we accept writing outside `cortex/`, or we accept the suppressed-picker auto-enter dies.
- Eliminating the `.gitignore` write while keeping the worktree feature is a real correctness regression on `.claude/worktrees/` — users would commit worktree directory contents without noticing.

**Where the alternative is fragile:**

- Interactive sandbox prompt storm on first contact with `cortex/lifecycle/{slug}/` subpaths is the headline failure. The umbrella `<repo>/cortex/` grant was chosen specifically to suppress this. The maintainers' own ADR explains why.
- Multi-repo workflows multiply the prompt-storm problem.
- Stranded `allowWrite` and stranded fences communicate bad state-hygiene stories; downgrades silently resurrect them.

**Where the alternative actually survives my attacks:**

- **Overnight runner is unaffected.** Overnight uses `--dangerously-skip-permissions` + per-spawn `--settings` tempfiles; user-scope `allowWrite` is not load-bearing for overnight. Rescoping does not break autonomous execution.
- **Attached-worktree refusal, symlink safety, not-a-repo gate** — all unchanged by rescoping.
- **Uninstall cleanliness is no worse than today.** ADR-0006 already accepts stranded fence-prose post-uninstall. Rescoping just changes it to "no fence ever existed" instead of "stale fence sits as dead prose."
- **The chicken-and-egg objection to an opt-in verb is weaker than it first sounds.** Run from the user's terminal (not inside Claude Code), the sandbox does not apply and registration goes through. The hard question is UX discoverability, not technical feasibility.

**Bottom line:** the maximally-rescoped position fails on the interactive sandbox-prompt-storm vector and on the auto-enter-feature kill. Both are mitigable — the first via an opt-in verb, the second via accepting the degradation as a price of distribution UX. The memory/ alternative does *not* offer an escape route to the gate.

The strongest version of the rescoping position is not "writes nothing outside `cortex/`" — it's "writes outside `cortex/` only when the user runs an explicit opt-in verb, and the lifecycle degrades gracefully when the opt-in hasn't run." That position survives my attacks. The unconditional zero-write-outside-cortex position does not.
