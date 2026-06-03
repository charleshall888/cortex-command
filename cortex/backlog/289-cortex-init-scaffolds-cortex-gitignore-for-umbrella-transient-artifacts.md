---
schema_version: "1"
uuid: 2cfdcb31-bca3-489e-a0b6-0ca7e84cf9b9
title: "cortex init scaffolds cortex/.gitignore for umbrella transient artifacts"
status: backlog
priority: medium
type: feature
areas: [install]
created: 2026-06-03
updated: 2026-06-03
---
**Why:** Critical-review writes `critical-review-residue.json`, and the lifecycle/overnight runtime writes `.session`, `.lock`, `.dispatching`, `agent-activity.jsonl`, `metrics.json`, `learnings/recovery-log.md`, `backlog/*.events.jsonl`, and `_adhoc/` into the `cortex/` umbrella. In this dogfooding repo those are ignored by the root `.gitignore`, but the per-repo scaffolder's `ensure_gitignore` (`cortex_command/init/scaffold.py:552`) only appends the `.cortex-init` markers plus a commented `# cortex/` all-or-nothing toggle to a consumer's **root** `.gitignore` (`_GITIGNORE_TARGETS` is just the markers + `.claude/worktrees/`). So a consumer gets a binary choice: commit the entire umbrella (the default — which sweeps every transient scratch file into history alongside real backlog/lifecycle/requirements artifacts) or uncomment `# cortex/` and ignore the whole umbrella including their project state. There is no selective middle setting. `critical-review-residue.json` is the artifact that surfaced this (it is read off-disk by `cortex_command/overnight/report.py`, never via git, so it never needs tracking), but it is one of ~8 transient artifacts that leak in every consumer repo.

**Role:** A tracked `cortex/.gitignore`, shipped with the umbrella scaffold, gives every repo the same selective ignoring this repo hand-maintains — independent of the host root `.gitignore` and compatible with the `# cortex/` toggle (the nested file is harmlessly moot when the whole umbrella is ignored). The canonical content already exists at `cortex/.gitignore` (seeded in the commit that files this ticket); this work wires the scaffolder to write/refresh it in consumer repos.

**Integration:** Add an idempotent, versioned write of `cortex/.gitignore` to the scaffold step, mirroring the CLAUDE.md-fence pattern (version-stamped, replace-on-version-bump, do not clobber a consumer's hand-edits). Source the bytes from a template under the init package rather than hardcoding. Mirror the change into the cortex-core plugin per dual-source enforcement. Once the nested file is canonical, de-duplicate the cortex-scoped transient rules from this repo's root `.gitignore`. Trim the now-inaccurate "un-gitignored residue" wording in `skills/lifecycle/references/complete.md` and `skills/lifecycle/references/post-refine-commit.md` (and their plugin mirrors): a directory-scoped `git add` no longer sweeps residue once it is gitignored, so that rationale shifts (the enumerated-staging guard is still good practice for un-ignored scratch, but the residue example becomes stale).

**Edges:**
- A consumer that already has a `cortex/.gitignore` — merge/version rather than clobber.
- Existing tracked residue (78 files in this repo: 43 archived, 35 active) is NOT untracked by adding the rule — git only applies ignore rules to untracked paths. Decide separately whether to `git rm --cached` the active copies.
- The init-state idempotency hash folds `repr(_GITIGNORE_TARGETS)` (`cortex_command/init/scaffold.py:148`); adding a template input must extend that hash so the `--ensure` drift check re-runs the scaffold when the template changes.
- The relocation migration (`cortex_command/init/_relocation_migration.py`) rglobs residue files to rewrite `artifact` keys — it operates on working-tree files and is unaffected by tracking status, but confirm it still finds them.
- Interaction with the `# cortex/` toggle, and with any consumer who deliberately commits residue as design history (none known — the harness treats it as transient).

**Touch-points:** `cortex_command/init/scaffold.py` (`ensure_gitignore` / a new umbrella-gitignore writer + template), `cortex_command/init/handler.py` (scaffold step ordering, init-state hash), `cortex/.gitignore` (canonical template source, already seeded), the cortex-core plugin mirror of the init package, `skills/lifecycle/references/complete.md` + `skills/lifecycle/references/post-refine-commit.md` (wording trim), the root `.gitignore` (de-dup), and `cortex_command/init/tests/` (idempotency, no-clobber, versioned-refresh, consumer-with-existing-file).
