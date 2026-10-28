---
schema_version: "1"
uuid: 17af35c0-54a1-4a35-8ad3-cd4d31da7507
title: 'Commit-message rules are learned only by a refused commit: state them where agents read before committing'
status: backlog
priority: low
type: chore
created: 2026-10-28
updated: 2026-10-28
tags: ['hooks']
blocked-by: []
blocks: []
---
## Why
`hooks/cortex-validate-commit.sh` refuses a subject that starts lower-case, ends in a period, is under 10 chars, or opens in past tense. Agents in wild-light hit it about 30 times across sessions on 2026-10-25..28 ("Subject must start with a capital letter", "Subject too short"). Each refusal costs a retry. Agents never see the rules until a commit fails.

## What
Put the four rules in one short line where agents read them before they commit (the cortex plugin's injected guidance or the commit skill), or print all four on the first refusal. Do not change the rules.

## Done when
A session's first commit passes the subject rules without a retry.
