---
schema_version: "1"
uuid: 4db31ffe-3956-405f-bab1-a31509ff8d61
title: "critical-review Step 2c.5 tempfile-write collides with Write-tool read-first guard"
status: complete
priority: medium
type: bug
created: 2026-05-26
updated: 2026-05-26
---

## Why

`skills/critical-review/SKILL.md` Step 2c.5 instructs the orchestrator to "write the reviewer's raw stdout to a tempfile (do NOT pipe through stdin to avoid shell-quoting hazards on four parallel outputs), then invoke `cortex-critical-review check-artifact-stable --input-file <tmpfile-path>`." If the orchestrator uses the Write tool to land those tempfiles and the target path has stale files from a prior session (e.g. `$TMPDIR/critreview/r1.txt` left by an earlier run), the Write tool's read-before-overwrite guard rejects the call. Observed today during plan-phase critical-review for `re-establish-perf-budget-for-cortex` (lifecycle session ID 7ba1c89b-...): all four `Write` calls to `/tmp/claude-503/critreview/r{1..4}.txt` returned `File has not been read yet`; worked around with `cat > … <<EOF` heredoc via Bash.

## Role

Future critical-review runs will hit the same wall whenever `$TMPDIR` has leftover files from a prior session. The skill's instructed Write path is not reliably usable; the workaround is undocumented.

## Integration

Two reasonable fixes:

1. **Session-unique tempdir**: Instruct the orchestrator to write to a path derived from `$LIFECYCLE_SESSION_ID` or `mktemp -d` so collisions are impossible (e.g. `$TMPDIR/critreview-${LIFECYCLE_SESSION_ID}/r{1..N}.txt`).
2. **Heredoc as canonical pattern**: Document the heredoc-via-Bash idiom in `skills/critical-review/references/verification-gates.md` as the supported way to land these tempfiles, since they're transient and don't need Read-tracking.

Fix #1 is preferred — it avoids relying on undocumented harness behavior.

## Edges

- Does NOT affect overnight runs (those don't share `$TMPDIR` state across sessions in the same way; verify before closing).
- Does NOT affect the `prepare-dispatch` or `check-synth-stable` subcommands themselves — the issue is purely the orchestrator's tempfile staging.
- Affects only the four-parallel-reviewer dispatch path in Step 2c.5; the total-failure fallback (Step 2c §b) doesn't stage tempfiles.

## Touch-points

- `skills/critical-review/SKILL.md` Step 2c.5
- `skills/critical-review/references/verification-gates.md` (Step 2c.5 section: "write the reviewer's raw stdout to a tempfile")
- Plugin mirror: `plugins/cortex-core/skills/critical-review/`

## Done When

- Critical-review's reviewer-tempfile staging step works without manual heredoc workaround across consecutive invocations in the same `$TMPDIR`.
- Either: (a) `skills/critical-review/references/verification-gates.md` Step 2c.5 names a session-unique tempdir mechanism (e.g. derived from `$LIFECYCLE_SESSION_ID` or `mktemp -d`); or (b) the canonical heredoc-via-Bash idiom for landing reviewer tempfiles is explicitly documented in that file.
- A regression test or doc test verifies the tempfile path is collision-free across consecutive critical-review invocations.
