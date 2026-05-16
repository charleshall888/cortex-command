---
status: accepted
---

# File-based state, no database

Cortex stores lifecycle, backlog, pipeline, and session state as many small markdown, JSON, and YAML files under the per-repo `cortex/` umbrella that `cortex init` already authorizes for sandbox writes (the only `~/.claude/` write the tool performs is registering that umbrella path). We chose plain files over a database because file-based state composes directly with that pre-authorized write surface — no daemon, no schema migrations, no extra credential or process — and remains diffable, grep-able, and reviewable in pull requests alongside the code that produces it. A database was considered and rejected: it would add a runtime dependency and an out-of-band store that the existing sandbox/PR review surface cannot inspect, in exchange for query power the current consumers (skills, hooks, overnight runner) do not need.
