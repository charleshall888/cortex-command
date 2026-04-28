# Research: Add runtime adoption telemetry for bin/cortex-* scripts (DR-7)

## Epic Reference

This ticket is a sub-ticket of epic 113 (now complete). Epic-level research lives at `research/extract-scripts-from-agent-tool-sequences/research.md` (DR-7 in particular); it established the three failure modes for script-adoption (day-one missing, drift, runtime-non-adoption) and identified the runtime-non-adoption gap that DR-5 (static parity lint, ticket 102) cannot close. This ticket scopes specifically to closing that runtime gap; alternative approaches and detection completeness are evaluated below against the original DR-7 framing.

## Clarified Intent

Add runtime adoption telemetry for `bin/cortex-*` scripts so a "wired-but-never-invoked" script is detectable from real interactive-session and overnight-runner activity — closing the runtime-adoption-failure detection gap that DR-5's static parity lint cannot reach. The proposed mechanism (PreToolUse Bash hook matcher writing to a JSONL log, plus an aggregator CLI) is one of several viable approaches surfaced by research.

## Codebase Analysis

### Hook infrastructure (post-epic-113)

- **Existing PreToolUse Bash matcher** lives at `plugins/cortex-interactive/hooks/hooks.json:3-12` with one entry calling `${CLAUDE_PLUGIN_ROOT}/hooks/cortex-validate-commit.sh`. A new hook entry would be appended to that same `hooks` array under `"matcher": "Bash"`.
- **Reference implementation pattern**: `plugins/cortex-interactive/hooks/cortex-validate-commit.sh:5-11` reads stdin (`INPUT=$(cat)`), parses with `jq`, returns a JSON response with `hookSpecificOutput.permissionDecision`, and exits 0 (fail-open). `plugins/cortex-interactive/hooks/cortex-output-filter.sh` follows the same pattern with optional `cwd` field at line 40.
- **Multiple hooks under one matcher fire sequentially** in JSON array order. The first hook returning `permissionDecision: "deny"` blocks subsequent hooks. Both hooks parse stdin independently (two `jq` invocations per Bash call).

### Dual-source enforcement

- Canonical hook scripts live at top-level `hooks/cortex-*.sh` (or `claude/hooks/cortex-*.sh`); canonical bin scripts at `bin/cortex-*`. Both are auto-mirrored to `plugins/cortex-interactive/{hooks,bin}/` via `just build-plugin` (justfile:470-503).
- **`HOOKS=(...)` is an explicit array, not a glob**: `justfile:480` lists `cortex-validate-commit.sh`, `cortex-worktree-create.sh`, `cortex-worktree-remove.sh`. A new hook script must be added by hand.
- **Pre-commit drift trigger regex is also explicit**: `.githooks/pre-commit:78` matches only `^(skills/|bin/cortex-|hooks/cortex-validate-commit\.sh$)`. A new `hooks/cortex-*.sh` filename will NOT trigger the dual-source rebuild without regex update.
- **`hooks.json` is hand-maintained** — no auto-merge logic. Adding a second entry under the existing Bash matcher is a third manual edit.
- **Bin distribution is glob-based**: `BIN=(cortex-)` at justfile:481, with `rsync --include='cortex-*'` at line 501 — new `bin/cortex-*` files are auto-distributed.

### Current `bin/cortex-*` inventory (9 files)

`cortex-archive-rewrite-paths`, `cortex-archive-sample-select`, `cortex-audit-doc`, `cortex-count-tokens`, `cortex-create-backlog-item`, `cortex-generate-backlog-index`, `cortex-git-sync-rebase`, `cortex-jcc`, `cortex-update-item`.

### JSONL writer pattern

- Canonical pattern at `cortex_command/pipeline/state.py:288-304` (`log_event()`): POSIX `open(path, "a")`, no locking, no rotation. Same pattern used at `claude/overnight/dispatch.py:485-528` for `agent-activity.jsonl`.
- **No existing rotation logic anywhere in the repo.**

### `~/.claude/` write paths

- The only documented `~/.claude/` write today is `cortex init` via `cortex_command/init/settings_merge.py:register()`, which `fcntl.flock`-serializes appends to `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array.
- **`~/.claude/` is NOT in the sandbox `allowWrite` list** in this user's config — only `~/cortex-command/lifecycle/sessions/` and `~/.cache/uv` are allowlisted. A PreToolUse hook attempting to append to `~/.claude/bin-invocations.jsonl` will be sandbox-blocked unless registered.

### Aggregator script pattern

- Existing reports follow the pattern of `bin/overnight-status` (bash + `jq`) and the Python wrappers (`cortex-create-backlog-item` etc.). For multi-field structured data, JSON; for human-readable reports, plain text. Exit 0 on success; non-zero on hard failure. Missing-data handling: emit "No data" message and exit 0.

## Web Research

### PreToolUse Bash payload (verified)

```json
{
  "session_id": "...",
  "transcript_path": "/Users/.../{session-id}.jsonl",
  "cwd": "/Users/.../my-project",
  "permission_mode": "default | bypassPermissions | ...",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": { "command": "...", "description": "...", "timeout": 120000, "run_in_background": false },
  "tool_use_id": "toolu_01ABC...",
  "agent_id": "...",
  "agent_type": "..."
}
```

- `tool_use_id` matches the OTel `claude_code.tool_result` event id — useful for cross-source correlation. Source: https://code.claude.com/docs/en/hooks, https://support.claude.com/en/articles/14477985-monitor-claude-cowork-activity-with-opentelemetry.

### Hook semantics

- Exit 0 allows; exit 2 blocks (stderr fed to Claude as deny reason). For logging-only DR-7, exit 0 unconditionally. Source: https://code.claude.com/docs/en/hooks.
- **`"async": true` shipped Jan 2026** — fire-and-forget, removes hook from Claude's critical path. https://reading.sh/claude-code-async-hooks-what-they-are-and-when-to-use-them-61b21cd71aad.
- Per-command-hook overhead ~34.6 ms (process spawn + JSON-on-stdin handoff). Bash+`jq` is faster than Node/Python; persistent-daemon hooks reach 0.31 ms. https://github.com/anthropics/claude-code/issues/39391.
- **`async: true` Windows risk**: https://github.com/anthropics/claude-plugins-official/issues/351 documents recurring startup hangs with async-tagged plugin hooks on Windows. Not a concern on macOS but worth recording.
- **`${CLAUDE_PLUGIN_ROOT}` resolves at runtime** for PreToolUse hooks (https://code.claude.com/docs/en/plugins-reference). Known bugs (#27145, #24529, #9354) affect SessionStart and command markdown only, not PreToolUse.

### JSONL append atomicity

- POSIX `O_APPEND` is atomic for writes ≤ 4 KB on local Linux/macOS FS; 8 KB is the cross-POSIX safe ceiling. NFS breaks this. Truncate `tool_input.command` to ~2 KB before append as insurance. https://nullprogram.com/blog/2016/08/03/.
- Concurrent writers from parallel worktree sessions are safe at sub-4KB record sizes without `flock`.

### Prior art

- **Anthropic issue #35319** explicitly proposes `~/.claude/analytics/skill-usage.jsonl` for skill-invocation analytics — the exact pattern DR-7 mirrors for scripts. No Anthropic response. https://github.com/anthropics/claude-code/issues/35319.
- **disler/claude-code-hooks-multi-agent-observability** captures all 12 lifecycle events to SQLite via HTTP endpoint — over-architected for DR-7. https://github.com/disler/claude-code-hooks-multi-agent-observability.
- **TechNickAI/claude_telemetry** ships OTel spans from a wrapper. Heavier than DR-7 needs.

### Rotation patterns

- Docker `json-file` driver default (`max-size=10m`, `max-file=3`, ~30 MB ceiling) is the canonical rule of thumb.
- **Aggregator-side rotation** (rotate-and-gzip on aggregator startup when log > threshold) avoids putting rotation on the hot hook path. No daemon, no cron.
- `logrotate copytruncate` is heavier; not needed for DR-7 scope.

## Requirements & Constraints

- **`requirements/observability.md`**: enumerates 5 in-session-visibility subsystems. DR-7 adds a 6th (script-invocation telemetry). The "No writes" non-functional requirement at line 85 scopes to *session state files* (`lifecycle/overnight-state.json`, per-feature `events.log`) — the new JSONL is per-user runtime telemetry at `~/.claude/`, NOT a session state file. **No constraint conflict.** Spec phase will need to add a 6th subsystem section.
- **No explicit latency budget** for PreToolUse hooks in observability.md. Implied: <10 ms synchronous, OR `async: true`.
- **`requirements/project.md` defense-in-depth**: the overnight runner uses `--dangerously-skip-permissions`. Hooks fire during overnight too. The proposed hook is safe (deterministic I/O only), but observability under permission-bypass mode versus default mode produces a sample-bias risk (see Adversarial F7).
- **`requirements/pipeline.md`**: pipeline observability (`agent-activity.jsonl`, `pipeline-events.log`) is explicitly separate. Ticket 103 scope excludes pipeline integration.
- **`requirements/multi-agent.md`**: hook fires across parallel agent worktrees. JSONL append atomicity at sub-4KB records makes this safe.
- **`requirements/remote-access.md`**: tangential. The shared host-global `~/.claude/` log works across reattached sessions.

## Tradeoffs & Alternatives

Five alternatives evaluated. Per the alternative-exploration rule for complex+high features with implementation suggestions, the proposed approach is graded against credible alternatives, not rubber-stamped.

| Alt | Description | Detection scope | Latency cost | Drift surface | Day-one signal |
|-----|-------------|-----------------|--------------|---------------|----------------|
| 1 (proposed) | PreToolUse Bash hook → `~/.claude/bin-invocations.jsonl` → aggregator | Zero-invocation only | ~34 ms/call sync, or async fire-and-forget | New hook + JSONL schema + rotation policy + dual-source surfaces | Zero (starts collecting at deploy) |
| 2 | SessionEnd zsh-history scan | **Wrong source** — captures user-typed commands, not Claude's Bash tool calls | None | Cross-shell complexity | None |
| 3 | Post-hoc analyzer over `~/.claude/projects/{project}/*.jsonl` session transcripts | Zero-invocation **AND** "agent did Read+Grep instead" via tool_use sequences | None (post-hoc) | Couples to undocumented Claude Code internal schema | 399 historical sessions on disk today |
| 4 | Skip telemetry; rely on DR-5 static lint | None for runtime-non-adoption | None | None | n/a — leaves DR-7 gap open |
| 5 | Per-script invocation-logging shim | **Cannot detect non-invocation** (only fires when script runs) | ~minimal (only on invocation) | Touch every script + every future script | None |

### Detailed assessment

**Alt 1 (proposed)**: matches existing repo patterns (mirrors `cortex-validate-commit.sh`); real-time signal; reuses JSONL writer pattern. Per-call overhead is 34 ms baseline for a Bash-call frequency that runs ~100 calls/session — neutralizable with `async: true`. Sandbox write-target issue is material (see Adversarial F7).

**Alt 2**: rejected. zsh-history records user-typed commands; Claude's Bash tool calls do not pass through the user's shell.

**Alt 3 (post-hoc analyzer)**: tempting because 399 sessions of backfilled history exist today and there's zero critical-path cost. But Adversarial review surfaced multiple data-loss bugs (#41591, #53417) and structural gaps (subagent transcripts in separate directories, overnight-pipeline transcripts under different project keys, cleanup-period config dependence). The "schema-coupling self-check" mitigation does not save it from silent partial failures across history.

**Alt 4**: rejected per epic research's load-bearing DR-7 finding. Re-litigating without new evidence.

**Alt 5 (per-script shim)**: zero schema-coupling to Claude Code internals; no sandbox interaction; no privacy surface (records only the script's own argv); most stable signal source. Detection-completeness gap (cannot detect non-invocation) is exactly the gap DR-5 already covers via static lint. **Alt 5 + DR-5 = full coverage with the smallest surface.** The Tradeoffs agent rejected this alternative too quickly without considering composition with DR-5.

### Recommendation

**No clean winner from research alone.** The Tradeoffs agent recommended Alt 3; the Adversarial agent rejected Alt 3 on data-loss-bug grounds and proposed Alt 1+M2 (with sandbox-friendly write target) or Alt 5+DR-5 hybrid. The choice is consequential and depends on priors the research cannot resolve:

- Is the Anthropic auto-update data-loss risk acceptable for a passive analyzer (Alt 3)?
- Is the per-script-shim drift surface acceptable for the simplest-coupling approach (Alt 5)?
- Is the proposed approach (Alt 1) salvageable with the sandbox-friendly write target M2?

Surface to user in spec phase.

## Adversarial Review

### Failure modes (ordered by severity)

- **F1. Claude Code auto-updates have silently deleted session JSONLs** in this user's likely cohort. Issue #41591 documents 520/520 sessions wiped over 2 months; status open, data-loss labeled. Alt 3's "backfilled history" advantage may evaporate at any auto-update.
- **F6. Cross-version writer silent-failure**: Issue #53417 — resumed sessions silently stop writing tool_use blocks to JSONL after upgrade. **Affected versions 2.1.104–2.1.119**; this user's range is 2.1.90–2.1.121, exactly inside the affected window. Alt 3 false-negatives indistinguishably from "no cortex-* invocations."
- **F7. Alt 1's `~/.claude/bin-invocations.jsonl` is NOT writable from the sandbox**. Verified: `~/.claude/settings.json` `sandbox.filesystem.allowWrite` allowlists only `lifecycle/sessions/` and `~/.cache/uv`. Issues #29048 and #33681 confirm `allowWrite` is *not enforced* under `--dangerously-skip-permissions` / `bypassPermissions`. So the write succeeds in bypass mode but silently fails in default mode — **mode-dependent observability is itself a sample-bias anti-pattern**.
- **F3. Alt 3 misses subagent Bash invocations entirely**. Subagent transcripts live in a separate `subagents/{agent-id}.jsonl` directory tree, NOT in the parent session JSONL. One verified parent session had 16 `Agent` tool calls → 16 separate subagent files the analyzer must traverse.
- **F4. Alt 3 misses overnight pipeline dispatches** unless the analyzer reads many `~/.claude/projects/-private-tmp-claude-503-overnight-worktrees-*` keys. Complexity inflates significantly.
- **F8. `just build-plugin` does NOT auto-discover new top-level hook scripts** — `HOOKS=(...)` is explicit; `.githooks/pre-commit:78` regex is explicit; `hooks.json` is hand-maintained. Three manual edits required for any new hook (HOOKS array + pre-commit regex + hooks.json entry). Forgetting any one leaves the plugin tree silently stale.
- **F10. "Read+Grep instead of script" detection has high false-positive rate** (Alt 3). A Read on `bin/cortex-audit-doc` could be (a) the agent legitimately reading before invoking, (b) ignoring the wired script, (c) /lifecycle plan rendering, (d) a research agent doing inventory. Distinguishing requires session-intent classification — unbounded analyzer cost.
- **F11. macOS APFS atomicity edge cases**: Time Machine's APFS-snapshot clone-on-write semantics had at least one CVE (CVE-2021-30752, macOS 11.5) for partial writes under heavy fork pressure. Edge case but adds risk surface.
- **F12. Rotation policy is undefined**. ~100 Bash calls × multiple sessions/day across worktrees = unbounded growth on `~/.claude/bin-invocations.jsonl`. Aggregator-side rotation runs only when aggregator runs (weekly per scope) — chicken-and-egg.

### Security/privacy

- **S1. Session JSONL contains user prompt content**. Alt 3 analyzer must filter strictly to `tool_use.input.command`, never `message.content`. If aggregator output ever lands in PR comments / commit messages / backlog tickets, prompt content leaks.
- **S2. Bin-invocations log is sensitive**. Alt 1's matcher fires on ALL Bash; if filtering happens *after* write (server-side), the log itself contains arbitrary credentials/tokens/file paths. **Filter to `cortex-*` inside the hook before writing**, not after.
- **S3. Mode-dependent telemetry is sample-biased**. F7 means Alt 1 records bypass-mode runs and silently drops default-mode runs. Reports are systematically skewed.

### Assumptions that may not hold

- **A1.** Alt 3's "schema stable across 22 minor versions" is a *retrospective* observation; the JSONL schema is undocumented internal state. Anthropic does not consider schema breaks a regression. Confirmed via https://code.claude.com/docs/en/hooks (no schema documented).
- **A4.** "Append atomicity makes multi-agent worktree writes safe" assumes a shared `~/.claude/` across all worktree subprocesses. If sandbox modes localize HOME, every worktree writes its own JSONL and the aggregator must merge N files. Not verified.
- **A5.** "The aggregator surface is identical between Alt 1 and Alt 3" is wrong. Alt 1 reads structured `{ts, command}`; Alt 3 must walk session JSONL + `subagents/` directories AND filter `isMeta`/`attachment` records.

### Mitigations recommended (if Alt 1 is chosen)

- **M2. Switch write target to `lifecycle/sessions/<session-id>/bin-invocations.jsonl`** — already in sandbox `allowWrite`; per-session retention semantics inherit from the rest of lifecycle observability; aggregator merges across sessions. Avoids F7 entirely.
- **M3. Filter to `cortex-*` invocations *inside* the hook before writing** — privacy + ~10×–100× volume reduction. Regex like `^[[:space:]]*(/[^[:space:]]+/)?cortex-[a-z-]+([[:space:]]|$)`.
- **M4. Update pre-commit regex AND HOOKS array AND hooks.json in the same plan task** — three edits, single commit, called out explicitly.
- **M6. Privacy redaction layer in aggregator** — strip everything except matched cortex-* commands and their argv. Emit only `{script_name, count, last_seen}` aggregates.
- **M7. Record `tool_use_id`** for OTel cross-source correlation if telemetry expands later.

## Open Questions

The following are deferred to the Spec phase, where the user will resolve them via structured interview. None are ambiguities the orchestrator should decide unilaterally.

- **Approach selection (highest priority)**: Alt 1 (proposed PreToolUse hook + JSONL aggregator), Alt 3 (post-hoc analyzer over Claude Code session JSONL), Alt 5 + DR-5 (per-script shim composed with existing static lint), or hybrid? Each has a distinct trade-off profile (Adversarial F1, F3–F4, F6, F7 vs F8 vs detection completeness). **Deferred: will be resolved in Spec by asking the user.**

- **Sandbox write target (if Alt 1 is selected)**: `~/.claude/bin-invocations.jsonl` requires either `cortex init` registration (broadens sandbox surface globally) or accepts mode-dependent silent failure (F7). Mitigation M2 proposes `lifecycle/sessions/<session-id>/bin-invocations.jsonl` instead — already allowlisted, per-session retention. Trade-off: aggregator must merge across sessions and historical JSONLs are tied to lifecycle session retention. **Deferred: will be resolved in Spec by asking the user.**

- **Hook synchronicity (if Alt 1 is selected)**: `async: true` removes per-call latency entirely (Jan 2026 feature) — cortex is macOS-only so the Windows startup-hang risk (Anthropic plugins issue #351) does not apply. Default vs explicit `async: true` is a trivial config choice but should be deliberate. **Deferred: will be resolved in Spec by asking the user.**

- **Privacy filtering point (if Alt 1 is selected)**: filter to `cortex-*` invocations *inside* the hook before writing (M3 — recommended) vs record all Bash and filter at the aggregator. Privacy posture and log size both depend. **Deferred: will be resolved in Spec by asking the user.**

- **Inventory-drift mechanism**: how does the matcher's known-script set stay in sync with the canonical `bin/cortex-*`? Auto-glob inside the hook on every invocation (cheap on small inventory) vs static list checked into the hook source (drift risk). **Deferred: will be resolved in Spec by asking the user.**

- **Rotation policy (if Alt 1 is selected)**: aggregator-side rotation when log > 10 MB (Docker pattern) vs accept unbounded growth and revisit later (low write volume after M3 filtering may make rotation unnecessary for years). **Deferred: will be resolved in Spec by asking the user.**

- **Aggregator output scope**: per-script invocation counts + non-invoked inventory list (canonical DR-7 deliverable) is the floor. Should the aggregator also surface co-occurrence patterns (Alt 3's strength — "agent did Read+Grep on `skills/audit/` but never invoked `cortex-audit-doc`") if the chosen approach can support them? **Deferred: will be resolved in Spec by asking the user.**
