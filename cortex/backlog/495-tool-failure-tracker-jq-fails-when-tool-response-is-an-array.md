---
schema_version: "1"
uuid: f2b1265f-9207-4290-9f48-51b506cd42e7
title: cortex-tool-failure-tracker.sh dies on every array-shaped tool_response (1,240 observed failures)
status: backlog
priority: medium
type: bug
created: 2026-08-19
updated: 2026-08-19
tags: ['hooks', 'observability', 'jq', 'cortex-core']
areas: ['observability']
---
Filed from wild-light, 2026-08-19, during a hook performance audit of that repo.

## Why

`hooks/cortex-tool-failure-tracker.sh:21` reads the exit code as:

```bash
EXIT_CODE=$(echo "$INPUT" | jq -r '.tool_response.exit_code // 0')
```

`.tool_response` is **not always an object.** Several tools return an array, and jq cannot
index an array with a string, so the hook aborts with:

```
jq: error (at <stdin>:1): Cannot index array with string ("exit_code")
```

The hook then exits **5**, which Claude Code records as `hook_non_blocking_error`.

## Evidence

Measured across 6,042 Claude Code session transcripts for the wild-light project
(`~/.claude/projects/-Users-charliehall-Workspaces-wild-light*/**.jsonl`), counting
`attachment` records where `hookEvent` is set:

| hook | spawns | exit 0 | exit 5 |
|---|---|---|---|
| `cortex-tool-failure-tracker.sh` | 1,240 | 0 | **1,240** |

**It has never once succeeded.** Every recorded invocation failed with the jq error above.
Because the failure is non-blocking, nothing surfaced it — the tool-failure tracker has been
tracking no tool failures for the entire life of the corpus.

## Integration

Same file also reads `.tool_response.stderr` on line 22, which fails identically on the
array shape. Lines 20, 23, 24 read top-level keys and are unaffected.

## Edges

- The guard must not silently swallow a genuinely missing `exit_code` on an object-shaped
  response — that is a real "no exit code reported" case and should still yield 0.
- An array-shaped `tool_response` is not an error condition; it is the normal shape for
  some tools. The hook should treat it as "no exit code available" and move on.
- Worth auditing sibling hooks for the same `.tool_response.<key>` assumption before fixing
  only this one.

## Touch-points

- `plugins/cortex-core/hooks/cortex-tool-failure-tracker.sh:21-22`

Suggested shape:

```bash
EXIT_CODE=$(echo "$INPUT" | jq -r 'if (.tool_response|type)=="object" then (.tool_response.exit_code // 0) else 0 end')
STDERR_TEXT=$(echo "$INPUT" | jq -r 'if (.tool_response|type)=="object" then (.tool_response.stderr // empty) else empty end')
```
