# Research: Change resolve_worktree_root() branch (c) default + retire R7

## Topic

Change `resolve_worktree_root()` branch (c) default at `cortex_command/pipeline/worktree.py:159-162` from `<repo>/.claude/worktrees/<feature>` to `$TMPDIR/cortex-worktrees/<feature>` so same-repo daytime/lifecycle dispatch produces a sandbox-friendly worktree path without requiring an env-prefix; remove `cortex init` Step 8 at `cortex_command/init/handler.py:201-211` (worktree-root allowWrite registration) since it cannot relieve the Seatbelt `.mcp.json` deny; add a structural regression test in `tests/test_worktree.py`; supersede R7 (must-have) of the `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive` lifecycle with empirical evidence.

## Codebase Analysis

### Files that will change

| File | Change | Lines |
|------|--------|-------|
| `cortex_command/pipeline/worktree.py:159-162` | Branch (c) default → `$TMPDIR/cortex-worktrees/<feature>`; rename docstring; canonicalize via `Path.resolve()` | ~6 lines edited |
| `cortex_command/pipeline/worktree.py:271-289` | **`cleanup_worktree()` hardcoded fallback at line 289 (`repo / ".claude" / "worktrees" / feature`) must route through `resolve_worktree_root()` or accept the resolver's output** — see Adversarial FM-1 | ~3 lines edited |
| `cortex_command/pipeline/worktree.py:108-110` | Branch (b) substring-marker (`"worktrees/" in entry`) — fragile; consider tightening to a tagged-entry scheme — see Adversarial SC-2/A-1 | optional; tighten or document |
| `cortex_command/init/handler.py:201-211` | Delete Step 8 entirely (worktree-root registration) | -11 lines |
| `cortex_command/init/handler.py` (new logic) | **Add settings.local.json migration**: on `cortex init --update`, detect and remove legacy `<repo>/.claude/worktrees/` entry from `allowWrite` — see Adversarial FM-2 | ~10-20 lines added |
| `claude/hooks/cortex-worktree-create.sh:29` | **Hardcoded `WORKTREE_PATH="$CWD/.claude/worktrees/$NAME"`**; same `.mcp.json` deny class — must be fixed or explicitly out-of-scope — see Adversarial FM-3 | scope decision required |
| `tests/test_worktree.py:309-322` | Update `test_branch_c_default_same_repo` to assert new default | rewrite |
| `tests/test_worktree.py:371-413` | Update fallthrough tests | rewrite |
| `tests/test_worktree.py` (new) | Add structural regression test for new default + negative test asserting result does NOT start with `<repo>/.claude/` | ~30-50 lines added |
| `tests/test_init_worktree_registration.py` | Delete entire file (183 lines invalidated) | -183 lines |
| `tests/test_hooks.sh:164,199,220,235` | If hook scope decision is "fix": update assertions; if "out-of-scope": leave but add explicit decision marker | scope decision required |

### Existing test coverage map

| Test | Coverage | Action |
|------|----------|--------|
| `tests/test_worktree.py::test_branch_c_default_same_repo` (lines 309-322) | Branch (c) returns `.claude/worktrees/` | Update assertion |
| `tests/test_worktree.py::test_no_settings_file_falls_through_to_c` (371-385) | Settings absent → branch (c) | Update |
| `tests/test_worktree.py::test_settings_without_worktrees_marker_falls_through` (386-413) | Settings missing marker → branch (c) | Update |
| `tests/test_worktree.py::test_branch_d_cross_repo_tmpdir` (324-335) | Branch (d) cross-repo | No change |
| `tests/test_init_worktree_registration.py::test_same_repo_worktree_root_is_registered` (79-105) | Step 8 registers `.claude/worktrees/` | **Delete** (Step 8 removed) |
| `tests/test_init_worktree_registration.py::test_cross_repo_tmpdir_path_is_not_registered` (113-143) | Step 8 skips registration for `$TMPDIR` paths | **Delete** |
| `tests/test_init_worktree_registration.py::test_cortex_init_worktree_registration_is_idempotent` (151-182) | Step 8 idempotency | **Delete** |
| `tests/test_hooks.sh:164,199,220,235` | Hook produces `.claude/worktrees/<feature>` | Scope decision |
| `cortex_command/overnight/tests/test_dispatch_readiness.py` | Mocks resolver — unaffected | No change |

### Callers of `resolve_worktree_root()` (4)

1. `cortex_command/init/handler.py:207` — Step 8 (being removed)
2. `cortex_command/overnight/daytime_pipeline.py:122` (`_worktree_path()`) — same-repo, gets new default
3. `cortex_command/overnight/readiness.py:110` — probe target, gets new default
4. `cortex_command/pipeline/worktree.py:196` (`create_worktree()`) — same-repo, gets new default

### Callers of `cleanup_worktree()` without explicit `worktree_path` (3) — see FM-1

1. `cortex_command/overnight/daytime_pipeline.py:260` (orphan-guard cleanup)
2. `cortex_command/overnight/daytime_pipeline.py:451` (merge-failure cleanup)
3. `cortex_command/overnight/smoke_test.py:124`

These will mismatch unless `cleanup_worktree`'s line-289 fallback is routed through the resolver.

### Hook & second worktree codepath — see FM-3

`claude/hooks/cortex-worktree-create.sh:29` hardcodes `WORKTREE_PATH="$CWD/.claude/worktrees/$NAME"`. Consumed by `Agent(isolation:"worktree")` (the parallel-execution dispatch path documented in `skills/lifecycle/references/parallel-execution.md:7-29`, `skills/research/SKILL.md:188`, and used in implement.md's `worktree/{task-name}` flow). This is a second worktree codepath that hits the same `.mcp.json` deny class — **the proposed fix does not address it**. Scope decision required: fix this hook in scope, or explicitly out-of-scope with a follow-up ticket.

### Skill prose & documentation references (~27 active, 11 files + plugin mirrors) — see SC-3/A-6

Agent 1 missed these; Adversarial enumerated them:

- `cortex/requirements/multi-agent.md:30,77` — REQUIREMENT-LEVEL: "Same-repo worktrees go to `.claude/worktrees/` by design"
- `cortex/requirements/pipeline.md:165-167` — hardcoded-deny constraints
- `docs/internals/pipeline.md:139`
- `docs/internals/sdk.md:29,144,160`
- `skills/lifecycle/references/parallel-execution.md:14,17` — "creates the worktree outside the sandbox write path" (already false today!)
- `skills/lifecycle/references/implement.md:200,202` — operator instructions including `git worktree remove .claude/worktrees/{task-name}` — wrong after fix
- `skills/overnight/SKILL.md:133`
- All plugin mirrors under `plugins/cortex-core/`
- `cortex_command/pipeline/worktree.py:5,12,14,127` (docstrings/comments)
- `cortex_command/init/handler.py:204` (comment)
- `tests/test_hooks.sh:164,199,220,235`
- `bin/cortex-archive-rewrite-paths:61-68` (path-rewriter logic)

`bin/cortex-check-parity --staged` catches literal mirror mismatch but not semantic doc drift.

### R7 verbatim (the supersession target)

From `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/spec.md:32`:

> **7. `cortex init` registers the worktree root**: Extend `cortex_command/init/handler.py` to call `resolve_worktree_root()` and register the result via existing `settings_merge.register_path` in `~/.claude/settings.local.json` `sandbox.filesystem.allowWrite`. Uses the same `fcntl.flock`-serialized additive append already in use for the `cortex/` umbrella. Cross-repo paths (resolved to `$TMPDIR/...`) skip registration — they're already sandbox-writable per the existing convention. **Acceptance**: after `cortex init` in a test repo, `jq '.sandbox.filesystem.allowWrite' ~/.claude/settings.local.json` includes the resolved worktree-root path; new test `tests/test_init_worktree_registration.py` (or extension of existing init tests) exit 0. **Phase**: 2. **Priority**: must-have

R6 (resolver default for same-repo branch (c) = `.claude/worktrees/<feature>/`) is also affected.

## Web Research

### `.mcp.json` Seatbelt deny mechanism

- Anthropic's `anthropic-experimental/sandbox-runtime` (Apache-licensed, open-source) is the canonical reference. DeepWiki documents `.mcp.json` in the **mandatory deny list** in `src/sandbox/macos-sandbox-utils.ts` — always-blocked from writes regardless of `allowWrite`. Cross-references `.ripgreprc` as a parallel always-denied entry.
- anthropics/claude-code#51303 groups `.mcp.json` with home-dir-mapping dotfiles distinct from the `.vscode`/`.idea` hardcoded-deny set. Reconciliation: the deny may be enforced at JS level via `denyWithinAllow` rather than via Seatbelt SBPL, but the user-observable effect is the same — writes to `.mcp.json` inside `.claude/` are denied even with parent path on `allowWrite`.
- Threat-model rationale: `.mcp.json` ships MCP server invocation commands; a tracked-state write would let attackers execute arbitrary code via committed `.mcp.json`. Same category as `.git/config` and `.git/hooks/**` patterns claudefa.st documents as always-mandatory-deny.
- **`allowWrite` cannot override mandatory deny** per Anthropic's settings-array merge precedence (settings.json reference). The only escape is `excludedCommands` (exits sandbox entirely) or `dangerouslyDisableSandbox` (user prompt).
- **Conclusion**: R7's premise (allowWrite registration relieves the deny) is structurally unachievable. The architectural fix is to put the worktree where `.mcp.json` is not in the deny scope — i.e., outside `.claude/`.

### `$TMPDIR` semantics under Seatbelt

- macOS: `$TMPDIR` is per-user, set by launchd to `/var/folders/XX/YYY/T/`, which is a **symlink** to `/private/var/folders/XX/YYY/T/`. Seatbelt operates on literal path strings — profiles must list both forms or canonicalize via `Path.resolve()`. Reference: nodejs/node#11422; Igor Stechnoclub sandbox-exec primer.
- Linux/WSL2 bubblewrap: `$TMPDIR` is the runtime-injected `/tmp/claude` value — also allowed.
- Pattern is **portable across both platforms**.
- Implementation requirement: `Path(os.environ.get("TMPDIR", "/tmp")).resolve()` before handing to git, or downstream Seatbelt rules that check `/private/var/folders/...` may still reject.
- Cleanup pattern in cortex-command exists: `cortex_command/overnight/plan.py:367-368` uses `shutil.rmtree(worktree_path, ignore_errors=True)`.

### Test patterns for sandbox-aware code

- `monkeypatch.setenv("TMPDIR", str(tmp_path))` + `monkeypatch.delenv("TMPDIR", raising=False)` for path-computation tests.
- `pytest.mark.skipif(os.environ.get("CLAUDE_CODE_SANDBOX") != "1", ...)` to gate live-sandbox integration tests (Claude Code sets `CLAUDE_CODE_SANDBOX=1` inside sandbox per issue #10952).
- **Important** (per Adversarial A-2): path-computation tests are necessary but insufficient. They prove what code computes, not what the OS sandbox enforces. The harden-autonomous-dispatch regression class is "the path passed to git is rejected by the OS sandbox" — only catchable by a Seatbelt-active integration test.

### macOS `$TMPDIR` purge behavior — see FM-4

- `dirhelper` runs nightly via `com.apple.bsd.dirhelper.plist` and removes files in `/var/folders/.../T/` that have not been **accessed** in 3 days. Sources: Apple Developer Forums threads #71382, #756124; magnusviri.com/what-is-var-folders.
- Active short-running features safe (continuous atime refresh).
- Hazard: a feature placed into paused/deferred state at end-of-session and not resumed within 3 days. Working-tree files purged; `.git/worktrees/{feature}/` admin state survives; `git worktree prune` removes the entry — silently destroying unmerged dispatched work. Decision needed: accept the risk (interactive features are short-lived, mirrors cross-repo overnight convention) or add a guard.

## Requirements & Constraints

### Architectural contracts being reversed

**`cortex/requirements/multi-agent.md:30,77`** (requirement-level):
> Worktrees for the default repo are created inside the repo at `.claude/worktrees/`; cross-repo worktrees go to `$TMPDIR` to avoid sandbox restrictions.

**This is a documented contract that the proposed fix REVERSES.** The supersession is not just R7 of a sublifecycle — it's a requirements-level convention change. Multi-agent.md must be updated as part of the fix.

### Related requirements

- **R6** (`harden-autonomous-dispatch-path-for-interactive/spec.md:30`): defines `resolve_worktree_root()` with branch (c) returning `.claude/worktrees/<feature>/`. Branch (c) edit is an R6 amendment.
- **R8** (spec.md:34): `probe_worktree_writable()` — unchanged in behavior; will now probe the new default.
- **`pipeline.md:165-167`**: documents hardcoded-deny constraints; should note the new default.

### CLAUDE.md guidance

**Solution horizon** (`cortex/requirements/project.md:21`): "A scoped phase of a multi-phase lifecycle is not a stop-gap." Empirical evidence (probe A/B + sandbox-runtime mandatory-deny enumeration) qualifies R7 for retirement rather than stop-gap rationalization.

**Structural separation over prose-only enforcement** (CLAUDE.md:58): "A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction." Resolver-default change satisfies this; prose-prefix alternative violates it.

**Prescribe What and Why, not How** (CLAUDE.md:64-70): the resolver default is the What/Why; the env-prefix would be a How.

**MUST-escalation policy** (CLAUDE.md:72-81): applies to *adding* MUSTs, not retiring them. R7 retirement still needs an evidence artifact citation in the supersession note (events.log F-row or transcript URL referencing the original `.mcp.json` deny + the new probe A/B result).

### Sandbox preflight gate

`bin/cortex-check-parity` SANDBOX_WATCHED_FILES (lines 103-123):
- `cortex_command/pipeline/dispatch.py`
- `cortex_command/overnight/runner.py`
- `cortex_command/overnight/sandbox_settings.py`
- `pyproject.toml`

This proposal's edits to `worktree.py` and `init/handler.py` are NOT in the watched set — preflight gate does NOT fire. No preflight.md required.

## Tradeoffs & Alternatives

Five approaches weighed; **Approach A** recommended.

| Approach | Description | Verdict |
|----------|-------------|---------|
| **A. Resolver-default to `$TMPDIR` + drop Step 8** (proposed) | Change branch (c); delete Step 8; structural test. | **Recommended** |
| B. Skill-prose env-prefix | Restore `CORTEX_WORKTREE_ROOT=...` prefix to implement.md launch line. | Rejected — violates structural-vs-prose preference; Step 8 dead code persists; drift risk across non-skill callers. |
| C. Step 8 registers a `$TMPDIR` path | Keep Step 8 but compute `$TMPDIR/cortex-worktrees/` at init time. | Rejected — `$TMPDIR` is per-shell on macOS; registered path is volatile and non-portable. |
| D. CLI auto-injection at dispatch | `cortex-daytime-pipeline` sets env var internally. | Rejected — forks policy across resolver and CLI layers; doesn't relieve Step 8 dead code. |
| E. Hybrid (A + corrected Step 8) | A plus registration ceremony. | Rejected — inherits C's `$TMPDIR` fragility; registration entry has no functional effect on Seatbelt deny; pure ceremony. |

### A's tradeoffs

**Pros**: Lowest complexity (3-5 files); converges branch (c) on the `$TMPDIR` pattern branch (d) already uses; satisfies CLAUDE.md structural-over-prose; removes dead code; transparent to existing callers (all route through resolver).

**Cons**:
- Worktrees less discoverable for humans `ls`-ing the repo (path is `/var/folders/.../T/cortex-worktrees/<feature>`).
- `$TMPDIR` volume-volatile on macOS (FM-4 — 3-day `dirhelper` purge).
- R7 must be explicitly superseded; multi-agent.md must be updated; ~27 prose references must be swept.
- **cleanup_worktree() hardcoded fallback must be re-routed** (FM-1).
- **Legacy settings.local.json `allowWrite` entries must be migrated** (FM-2).
- **`cortex-worktree-create.sh` hook is a second worktree codepath with the same bug** — scope decision required (FM-3).

## Adversarial Review

The adversarial agent identified six substantive defects in the original scope and three implicit assumptions that don't hold. The defects materially expand the proper scope of this fix:

### Critical correctness defects (block merge until addressed)

**FM-1: `cleanup_worktree()` hardcoded fallback bypasses resolver.** `worktree.py:289` has `wt_path = worktree_path if worktree_path is not None else (repo / ".claude" / "worktrees" / feature)`. Three `cleanup_worktree(feature)` callsites — `daytime_pipeline.py:260,451`, `smoke_test.py:124` — do not pass `worktree_path`. After the fix, dispatches create at `$TMPDIR/...` but cleanup runs against `.claude/worktrees/...`. Result: orphan TMPDIR worktree directories + orphan `git worktree list` entries + orphan `pipeline/{feature}` branches every run.

**FM-2: Legacy settings.local.json `worktrees/` entry re-asserts the old path.** Branch (b) `_registered_worktree_root` returns the first allowWrite entry containing `"worktrees/"`. Every user who ran `cortex init` already has `<repo>/.claude/worktrees/` registered (Step 8 wrote it). After the fix, branch (b) finds the legacy entry **before** the new branch (c) — resolver default never engages. Must ship a migration: `cortex init --update` detects and removes the legacy entry.

**FM-3: `claude/hooks/cortex-worktree-create.sh` is unfixed.** Line 29 hardcodes `WORKTREE_PATH="$CWD/.claude/worktrees/$NAME"`. Consumed by `Agent(isolation:"worktree")` — the parallel-execution dispatch path. After the proposed fix, the daytime/lifecycle dispatch is sandbox-friendly but parallel-feature dispatch via `Agent(isolation:"worktree")` **still hits the same `.mcp.json` deny**. The claim that this fix retires the harden-autonomous-dispatch failure class is overstated unless the hook is also fixed (or explicitly out-of-scope with a follow-up).

**A-2: Path-computation tests don't exercise the Seatbelt boundary.** `monkeypatch.setenv("TMPDIR", tmp_path)` proves what the code computes; it does not prove the OS sandbox accepts the result. The harden-autonomous-dispatch regression class requires a live-sandbox integration test or a citable transcript/events-log artifact showing the new default works under active Seatbelt.

### Substantive but lower-priority concerns

**FM-4: 3-day `$TMPDIR` purge against paused features.** Active features are safe (continuous atime). Paused/deferred features lose working-tree state silently if not resumed within 3 days. Decision needed: accept (mirrors cross-repo overnight convention) or guard.

**FM-5: CWD-asymmetry between create-side and cleanup-side.** Create-side resolves a CWD-independent target ($TMPDIR); cleanup-side's `_repo_root()` is CWD-dependent. Calling cleanup from inside a sub-worktree (post parallel-execution dispatch) attaches branch-delete to the wrong repo context. Today's bug is co-located; the proposed bug splits the failure across two file-tree locations.

**FM-6: `.gitignore` policy reversal implications.** `.gitignore` lines 1-3 ignore `.claude/worktrees/` and `worktrees/`. A future rollback or older hook leaves orphan worktrees still gitignored. New `$TMPDIR/...` worktrees are outside the repo's .gitignore scope entirely. Theoretical for cortex-command, category-error for adopters with stricter ignore policies.

### Hidden assumptions

**SC-1: Multi-user shared dev box.** Per-user `$TMPDIR` + repo-shared `.git/worktrees/` admin tree creates less-diagnosable collisions than today's repo-shared worktree path. Single-user laptops unaffected; should be acknowledged explicitly.

**SC-2/A-1: `"worktrees/"` substring marker is fragile.** Any unrelated `allowWrite` entry containing the substring poisons the resolver. Tighten to a tagged-entry scheme.

**SC-3/A-5/A-6: Doc-sweep was underscoped.** Approximately 27 active references to `.claude/worktrees/` across 11 files (plus plugin mirrors). Agent 1 missed all of these. Updating only multi-agent.md leaves prose-vs-code drift.

**A-3: R7 supersession evidence specification.** "Empirical A/B probe" is the right shape but needs a citable artifact in the supersession note (events.log F-row reference + this lifecycle's research.md reference). The original `harden-autonomous-dispatch-path-for-interactive/events.log` likely contains the F-row showing the original `.mcp.json` deny that justified R7.

### Recommended mitigations (8)

1. **Block change until `cleanup_worktree`'s default is wired through `resolve_worktree_root`.** Three call-sites to fix (FM-1).
2. **Add legacy settings.local.json migration** in `cortex init --update` (FM-2).
3. **Fix `cortex-worktree-create.sh` hook in scope OR explicitly out-of-scope with follow-up** (FM-3). Updating `tests/test_hooks.sh` if fixing.
4. **Doc-sweep task** covering ~27 references across 11 files + mirrors (SC-3/A-5/A-6).
5. **Seatbelt-active integration test** OR citable transcript artifact for R7 supersession (A-2/A-3).
6. **Decide & document the 3-day `$TMPDIR` purge stance** for paused features (FM-4).
7. **Update all requirements docs**, not just multi-agent.md (pipeline.md, internals).
8. **Replace substring marker with tagged-entry scheme** in `_registered_worktree_root` (SC-2/A-1).

## Open Questions

All resolved with user via AskUserQuestion at research-exit gate (2026-05-15):

1. **`cortex-worktree-create.sh` hook scope** — **Resolved: fix in this lifecycle.** Apply the same `$TMPDIR/cortex-worktrees/` pattern to the hook; update `tests/test_hooks.sh`. Without this, the lifecycle wouldn't retire the harden-autonomous-dispatch failure class — only one of two affected codepaths.
2. **Legacy settings.local.json migration** — **Resolved: no migration code.** Rationale (user): "We are on the only user of this system right now." The single existing user's legacy `.claude/worktrees/` allowWrite entry will be removed manually as part of implementation verification (or via direct settings.local.json edit); no `cortex init --update` migration code is added. Cortex-command is effectively single-operator at this point; the migration cost outweighs the benefit.
3. **Branch (b) substring-marker tightening** — **Resolved: include.** Replace `"worktrees/" in entry` substring scan with an explicit tagged-entry scheme (per SC-2/A-1).
4. **3-day `$TMPDIR` purge stance** — **Resolved: include atime-touch guard.** Add an atime-touch on lifecycle resume for paused features so `dirhelper` doesn't silently purge unmerged work (per FM-4).
5. **Seatbelt-active integration test** — **Resolved: include.** Add a `pytest.mark.skipif(CLAUDE_CODE_SANDBOX != "1", ...)` test exercising `probe_worktree_writable()` on the new default in an active sandbox. Catches the regression class R7 was opened against.
6. **`Path.resolve()` canonicalization** — **Resolved: include.** Call `.resolve()` on the `$TMPDIR`-derived path so downstream Seatbelt comparisons against canonical `/private/var/folders/...` paths still match.

## Considerations Addressed

(None — `research-considerations` was empty.)

## References

- `cortex_command/pipeline/worktree.py:5-14,108-110,114-162,196,271-289,127`
- `cortex_command/init/handler.py:201-211,124-134`
- `cortex_command/overnight/daytime_pipeline.py:116-122,260,451`
- `cortex_command/overnight/readiness.py:108-117`
- `cortex_command/overnight/smoke_test.py:124`
- `cortex_command/overnight/plan.py:363,367-368`
- `claude/hooks/cortex-worktree-create.sh:29`
- `skills/lifecycle/references/implement.md:88,200,202`
- `skills/lifecycle/references/parallel-execution.md:7-29,14,17`
- `skills/overnight/SKILL.md:133`
- `cortex/requirements/project.md:21,28,39`
- `cortex/requirements/multi-agent.md:23,30,77`
- `cortex/requirements/pipeline.md:158,165-167`
- `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/spec.md:30,32,34,70-75,129,135`
- `tests/test_worktree.py:309-322,371-413,324-335`
- `tests/test_init_worktree_registration.py:79-105,113-143,151-182`
- `tests/test_hooks.sh:164,199,220,235`
- `bin/cortex-check-parity:99-123` (SANDBOX_WATCHED_FILES — not triggered by this proposal)
- anthropics/claude-code#51303 (hardcoded `_SBX` denies)
- anthropic-experimental/sandbox-runtime (mandatory-deny list, source-of-truth)
- DeepWiki for sandbox-runtime (`.mcp.json` in mandatory deny)
- Apple Developer Forums #71382, #756124 (macOS `$TMPDIR` purge behavior)
- CLAUDE.md: Solution horizon, Structural-over-prose, MUST-escalation policy
