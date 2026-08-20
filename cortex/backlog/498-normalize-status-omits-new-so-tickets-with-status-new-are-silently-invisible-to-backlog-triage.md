---
schema_version: "1"
uuid: 1c155f36-e15d-423e-a644-e66ba6ada5e5
title: 'normalize_status omits ''new'', so tickets with status: new are silently invisible to backlog triage'
status: backlog
priority: medium
type: bug
created: 2026-08-19
updated: 2026-08-19
tags: ['backlog', 'status-vocabulary', 'triage']
areas: ['tooling']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-08-19, during #593 (backfilling two backlog tickets that carry no `uuid:`).

## Why

`normalize_status` in `cortex_command/common.py` maps eight legacy spellings onto the canonical
vocabulary (`open`->`backlog`, `done`->`complete`, `wontfix`->`abandoned`, and so on). **`new` is not
in `_STATUS_MAP`**, so it passes through unchanged and is treated as its own bucket rather than as a
synonym for `backlog`.

## Measured consequence

In the wild-light backlog on 2026-08-19, six live tickets carried `status: new`: `#539`, `#542`,
`#543`, `#574`, `#575`, `#577`. **`cortex-backlog-triage` listed none of them.** A control with
`status: backlog` (`#554`) listed. After rewriting the six to `status: backlog`, all six appeared.

So six real tickets were invisible to the triage board, which is the CLI's primary "what should I work
on" surface, with no error and no warning anywhere.

## Suggested fix

Add `"new": "backlog"` to `_STATUS_MAP`. `new` is the natural word a human writes when hand-authoring
a ticket, and it means the same thing as `backlog` in every reading of the board.

Consider also whether an unrecognised status should be surfaced rather than silently passed through.
The current behaviour — "unknown values pass through unchanged" — is what makes this failure mode
silent: the item is neither terminal nor listed, and nothing says so.
