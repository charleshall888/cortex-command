---
schema_version: "1"
uuid: 3f941c1b-e844-4b43-9524-1523a36176cb
title: cortex-create-backlog-item writes bodies its own pre-commit config must rewrite, costing every caller a silent first-commit failure
status: complete
priority: medium
type: bug
created: 2026-07-28
updated: 2026-07-29
tags: ['harness', 'backlog', 'cli', 'dx']
---
**Every `--body` caller creates a file that `end-of-file-fixer` is guaranteed to modify, which aborts the caller pre-commit run by design.** The abort is then buried under ~200 lines of green hook output and reads as success.

## Why

`cortex_command/backlog/create_item.py:173` appends the caller-supplied body **verbatim**:

```python
if body is not None:
    lines.append(body)
```

No trailing newline is added. A `--body` argument almost never ends in one — shell single-quoted strings, `$(cat file)`, and Python string literals all strip or omit the final newline — so the emitted ticket ends without `0a`.

Any repo using the standard `pre-commit-hooks` set then has `end-of-file-fixer` **modify the file**, and pre-commit aborts the commit so the fix can be inspected. That is pre-commit working correctly. The cost is that the tool ships content its own ecosystem rejects.

**Measured 2026-07-28 in wild-light.** Seven tickets filed via `--body` in one batch; the commit **silently did not land**. Verified by probe:

```
$ printf %s "no trailing newline" > probe.md   # tail -c 1 => 65
$ pre-commit run end-of-file-fixer --files probe.md
fix end of files.....Failed
Fixing probe.md                                 # tail -c 1 => 0a
```

The retry succeeded because the file was already fixed — which is exactly what makes this expensive: it is a **deterministic first-attempt failure that self-heals**, so it never looks like a tool bug. It looks like flakiness.

**Why the silence matters more than the retry.** The last line of a failed run is `[INFO] Restored changes from ...patch`, preceded by a wall of passing hooks. An agent reading that output concludes the commit landed. In the wild-light session this happened four separate times and was caught each time only by an explicit `git log --oneline -1` check. An agent without that habit reports work as committed when HEAD never moved.

## Role

Normalize the body on write so the emitted file is already clean.

## Integration

- `cortex_command/backlog/create_item.py:172-173` — the fix is one line: append `\n` when `body` does not already end with one.
- **The codebase is already inconsistent here, which is the strongest argument for fixing it**: `cortex_command/overnight/report.py:465` does `frontmatter + "\n" + body + "\n"` — it normalizes. `create_item.py` does not.
- `cortex_command/lifecycle/create_index.py:142,217` is **not** affected — its body is internally constructed and already ends with `\n`. Confirmed, so it needs no change.

## Edges

- **Do not just `body + "\n"` unconditionally** — a body that already ends with a newline would gain a second one, and `end-of-file-fixer` strips trailing blanks, reintroducing the same abort from the other direction. Normalize to exactly one: `body.rstrip("\n") + "\n"`.
- Consider whether `--body` should also normalize CRLF, since `mixed-line-ending --fix=lf` is in the same standard hook set and has the identical failure shape.
- A test asserting the emitted file ends with exactly one `\n` would lock this; `tests/` already has backlog-writer coverage to extend.

## Touch-points

- `cortex_command/backlog/create_item.py`
- `cortex_command/overnight/report.py` (the existing correct pattern)
- `cortex_command/lifecycle/create_index.py` (verified unaffected)
