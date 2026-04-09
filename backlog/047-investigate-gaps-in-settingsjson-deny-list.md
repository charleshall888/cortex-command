---
schema_version: "1"
uuid: 5732add4-258e-4767-ae7e-e8d88299a8a3
title: "Investigate gaps in settings.json deny list"
status: complete
priority: medium
type: task
created: 2026-04-08
updated: 2026-04-09
---

Audit of `claude/settings.json` deny list surfaced six items worth a conscious decision. Goal is investigation and intentional accept/deny for each — not necessarily applying all of them.

## Items to investigate

1. **`git restore *` is in the allow list** — permanently discards uncommitted working directory changes with no recovery path (unlike `git reset --hard`, which at least leaves a reflog). Consider moving to `deny` or `ask`.

2. **`Read(~/.config/gh/hosts.yml)` is missing** — the GitHub CLI stores your auth token here in plaintext. The list covers `.git-credentials`, `.npmrc`, `.aws/` etc. but misses `gh`'s token file.

3. **`Read(**/*.p12)` is missing** — `.p12` is a common certificate/key bundle format alongside `.pem`, `.key`, `.pfx` (all of which are denied). Used in signing certs and mobile dev toolchains.

4. **Plain `rm *` (non-recursive) is allowed** — only `rm -rf` and `rm -fr` are denied. `rm file.txt` permanently deletes individual files. Decide if this is intentional (allowing temp file cleanup) or an oversight.

5. **`crontab *` is unaddressed** — not in allow or deny, falls through to the default prompt. Installing a cron job is a persistence mechanism that survives the session. Worth an explicit decision.

6. **`WebFetch(domain:0.0.0.0)` is missing** — `localhost` and `127.0.0.1` are denied but `0.0.0.0` is another loopback alias on most systems.

## Out of scope

Applying these changes — this ticket is investigation only. Each item may have a deliberate reason for its current state.

> Subsumed by #056 (apply-confirmed-safe-permission-tightening).
