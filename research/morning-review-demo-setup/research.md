# Research: morning-review-demo-setup

> Discovery: reduce morning-review friction by auto-launching demo environments (servers, apps, games) on the overnight branch before the user validates work.

## Research Questions

1. **What does `lifecycle.config.md` look like and how is it consumed by the runner?**
   → The template (`skills/lifecycle/assets/lifecycle.config.md`) defines `type`, `test-command`, and related fields, but the runner does NOT read this file. `test-command` is passed as a CLI arg to `runner.sh` (`--test-command`) and wired through to `batch_runner.py`. The `lifecycle.config.md` file exists in target repos (e.g. wild-light) but is never parsed by cortex-command tooling at runtime.

2. **Where in the overnight flow is the natural hook point for demo launch?**
   → **NOT the integration worktree.** runner.sh executes `git worktree remove --force "$WORKTREE_PATH"` at lines 1291–1330 as deliberate post-session cleanup, immediately after the morning report is committed and pushed. The worktree is gone well before the user opens `/morning-review`. The correct hook point is the **morning review skill itself** — at that point the user is present, and the overnight branch (`overnight/{session_id}`) still exists as a full git branch and can be checked out or have a fresh worktree created from it.

3. **What is the current "test-command" invocation path?**
   → `runner.sh` shells out via `subprocess.run(["sh", "-c", test_command], cwd=worktree_path)` in `claude/pipeline/merge.py:52-85`. This pattern is **blocking** — it waits for exit. A background demo server would require `subprocess.Popen` with explicit detachment and a PID-tracking mechanism that does not currently exist in the codebase. The `subprocess.run` pattern is not reusable for a long-running demo process.

4. **What repo types are in play and what does "demo-ready" mean for each?**
   → Two confirmed types:
   - **Dashboard / web-app** (cortex-command): `uv run python -m claude.overnight.dashboard` — a FastAPI server that can run in background and stay up while the user validates
   - **Game** (wild-light): `godot --play res://main.tscn` — requires interactive user present; must be launched at morning review time, not pre-launched
   → Both types require the same core operation: create a fresh worktree from the overnight branch at morning review time, run the `demo-command` from that worktree's directory.

5. **Where does the overnight session end?**
   → `runner.sh` execution order: (1) `session_complete` event logged → (2) state transitions to `complete` → (3) integration gate runs → (4) morning report generated → (5) morning report committed → (6) morning report pushed → **(7) integration worktree destroyed** (`git worktree remove --force`). The overnight branch (`overnight/{session_id}`) persists as a git branch after session end and is the durable reference to the session's code. The worktree is a transient working directory that does not survive to morning review.

6. **How does the morning review skill surface overnight work?**
   → `/morning-review` walks: Executive Summary → Completed Features (batch verification) → Deferred Questions → Failed Features → Auto-close backlog → Commit → PR merge. There is no current "how to validate" section. Adding demo launch at Step 3 (Completed Features) is where demo context is most useful — the user is deciding whether to verify features before approving. The morning review skill already reads the overnight branch name from the session state, making it straightforward to create a fresh worktree from it.

7. **Is `lifecycle.config.md` parsing currently a solved problem?**
   → No. The file has YAML frontmatter but no existing parser in cortex-command reads it at runtime. A `demo-command` field requires either building this parser or passing `demo-command` as a new CLI arg (like the existing `--test-command` pattern).

## Codebase Analysis

### lifecycle.config.md template (skills/lifecycle/assets/lifecycle.config.md)
Current fields:
```yaml
type: game              # web-app | cli-tool | library | game | other
test-command:           # e.g., npm test, pytest, godot --headless ...
default-tier:           # simple | complex
default-criticality:    # low | medium | high | critical
skip-specify: false
skip-review: false
commit-artifacts: true
```

### Test-command flow (current, no demo support)
- `runner.sh:723` — `--test-command "${TEST_COMMAND:-none}"` CLI arg
- `claude/pipeline/parser.py:221-223` — parsed into `MasterPlanConfig.test_command`
- `claude/pipeline/merge.py:52-85` — `run_tests()` invokes via `subprocess.run(["sh", "-c", cmd], cwd=worktree)` (blocking; waits for exit)

### Integration worktree lifecycle
- Created during overnight session bootstrap
- Path: `$TMPDIR/overnight-worktrees/{session_id}/`
- **Destroyed at session end**: runner.sh lines 1291–1330 (`git worktree remove --force`) runs immediately after morning report push, before the user wakes up
- The overnight **branch** (`overnight/{session_id}`) persists indefinitely — it is not deleted by the runner. This is the durable reference to the session's code.
- At morning review time, a fresh worktree can be created from the overnight branch via `git worktree add`

### Morning report structure (claude/overnight/report.py)
- Written to `lifecycle/sessions/{SESSION_ID}/morning-report.md`
- Sections: Executive Summary, Completed Features, Deferred Questions, Failed Features
- No current "Validation" or "Demo" section
- PR URLs are embedded in Completed Features for each merged feature
- Session ID embedded in report heading — readable by morning review skill

### Morning review skill (skills/morning-review/SKILL.md)
- Reads morning report, walks sections in order
- Already reads `overnight-state.json` which contains the session ID and overnight branch name
- Step 3 (Completed Features) asks a "single batch verification question" — demo launch fits naturally before this question
- The skill runs in the repo root context where `git worktree add` is valid

## Feasibility Assessment

| Approach | Effort | Viable? | Notes |
|----------|--------|---------|-------|
| A. Background launch from worktree at session end | M | **No** | Worktree deleted before morning review; `subprocess.run` is blocking |
| B. Generate `launch-demo.sh` pointing at worktree | S | **No** | Script references a path that no longer exists at run time |
| C. Morning review skill creates fresh worktree from overnight branch, launches demo | S | **Yes** | Overnight branch persists; skill already reads session/branch state; user is present |
| D. Hybrid of A/B/C | M-L | **Partial** | Only the C leg is viable; A/B legs are broken |

**Viable approach**: C only, with background mode for server-type repos (non-blocking launch using `Popen` + PID tracking at morning review time) and interactive/foreground mode for game/app types.

## Decision Records

### DR-1: Where does demo launch happen — session end or morning review?

- **Context**: The integration worktree is destroyed by runner.sh at session end, before morning review. Session end launch is therefore not viable for any approach that needs the worktree. The overnight *branch* persists.
- **Options considered**:
  1. Launch at session end from worktree — **not viable**: worktree deleted, no background process plumbing in runner.sh
  2. Generate launch script at session end — **not viable**: script references deleted worktree path
  3. Morning review skill creates fresh worktree from overnight branch, launches demo — **viable**: overnight branch persists, skill already reads session/branch state, user is present
  4. Morning review skill shows launch instructions only (no actual launch) — viable and simpler; user runs command manually
- **Recommendation**: Option 3 (Approach C) for repos with `demo-command` set. At Step 2.5 of the morning review walkthrough (between Executive Summary and Completed Features), the skill: (1) reads `demo-command` from `lifecycle.config.md` in the repo root, (2) creates a fresh worktree from `overnight/{session_id}`, (3) runs the demo-command from that worktree — as a background `Popen` for server types, as a blocking launch for interactive types. Surfaces result (URL / PID / instructions) before the batch verification question.
- **Trade-offs**: Adds `git worktree add` + `Popen` plumbing to the morning review skill. Server processes launched during review need cleanup when PR merge completes (Step 6). Worktree creation can fail if worktrees are somehow left over — handle with `--force` if needed.

### DR-2: New `demo-command` field vs. reuse `test-command`

- **Context**: `test-command` runs the automated test suite (headless, exits). A demo command may launch a long-running interactive session.
- **Options considered**:
  1. Reuse `test-command` with a `demo: true` flag
  2. New `demo-command` field alongside `test-command`
  3. A `run-command` field (more general)
- **Recommendation**: New `demo-command` field. The semantics are different: `test-command` is exit-code-verified automation; `demo-command` is "start this for human inspection." Keeping them separate avoids accidental invocation of a long-running process in the test gate.
- **Trade-offs**: Adds one field to the config schema; repos without it leave it absent, feature skips entirely.

### DR-3: lifecycle.config.md is not read at runtime — should this change?

- **Context**: The runner currently gets `test-command` via CLI arg. The morning review skill would need `demo-command`. Two integration paths exist.
- **Options considered**:
  1. Morning review skill reads `lifecycle.config.md` directly from the repo root — simple read, no parser needed for the skill (no worktree involved; it reads from the working repo)
  2. Add `demo-command` as a CLI arg to the overnight runner (following existing test-command pattern) and embed it in the morning report for the skill to consume
  3. Fix the gap fully: build a YAML frontmatter parser, migrate `test-command` from CLI arg to file-based config across runner.sh, parser.py, and overnight SKILL.md
- **Recommendation**: Option 1 for this feature. The morning review skill already operates against the repo root and can read `lifecycle.config.md` directly without a parser change to the runner. Option 3 (fixing the gap fully) is disproportionate scope: it requires changes at `runner.sh:723`, `parser.py:221-223`, overnight SKILL.md, a new YAML frontmatter parser, and backward-compat handling for the existing `--test-command` CLI arg — all to fix something that works correctly today. A gap that has no current defect should not be dragged into a different feature's scope.
- **Trade-offs for Option 1**: The morning review skill reads a Python YAML file with a simple frontmatter parse (~5 lines); this is new but narrow. The overnight runner's `--test-command` path is unchanged.
- **New failure mode to watch (Option 3 only)**: Moving `test-command` to parsed file config would silently break the integration gate if `lifecycle.config.md` is missing or malformed in the target repo — a regression in auditability. This is a reason to NOT do Option 3 in this ticket.

### DR-4: How to handle repos without a `demo-command`

- **Options**: Skip silently / log "no demo configured" in report / display a placeholder in morning review.
- **Recommendation**: Skip entirely — no worktree created, no morning review prompt. The feature is opt-in per repo.

## Open Questions

- Should `demo-command` be per-repo (one command for the whole project) or per-feature (different features may demo at different entry points)? For web apps this is clearly per-repo. For games, individual features might demo at different scenes (`res://combat.tscn` vs `res://main.tscn`). Needs user input before spec.
- For background-launched servers at morning review time: what is the cleanup contract? The process is spawned during the review and should be stopped when the PR merge completes (Step 6). Should the morning review skill kill it automatically, or leave it running for the user to stop manually?
- The fresh worktree created at morning review time (`git worktree add`) needs a stable path. Where should it be created? Options: `lifecycle/sessions/{id}/demo-worktree/` (repo-tracked) or `$TMPDIR/demo-{id}/` (temporary).
- Should `demo-command` be able to reference lifecycle template variables (e.g., `{session_id}`, `{branch}`) or is running with `cwd=demo_worktree_path` always sufficient?
- What happens when the morning review skill runs but the overnight branch has already been deleted (e.g., PR was merged before `/morning-review` ran)? Should the skill offer to create a worktree from `main` instead, or skip demo entirely?
