---
status: accepted
---

# Reconcile and gate the two lifecycle.config.md sources

## Context

The lifecycle config schema exists as two near-identical, independently-maintained
files in different distribution channels:

- the `cortex-core` plugin **asset** `skills/lifecycle/assets/lifecycle.config.md`
  — what the docs cite and what plugin-only users (who installed `cortex-core` via
  `/plugin install` and never `uv tool install`ed the CLI) read as the schema
  reference; and
- the CLI **init template** `cortex_command/init/templates/cortex/lifecycle.config.md`
  — dropped verbatim into a repo by `cortex init`.

They share all frontmatter except a `backlog:` block (added to the template by
#317, absent from the asset), plus one intended body difference (the asset's
"Copy this file to your project root…" sentence, which the auto-placed template
omits). No tooling linked the two files, so they drifted silently: a user copying
the asset got a config missing the `backlog:` backend section, and the docs
compounded it by citing the stale asset as the "source of truth." The asset is
parsed by nothing at runtime — the live config is the project-root copy dropped
from the template — so the blast radius is doc-completeness, not runtime behavior.

## Decision

Keep both files hand-maintained and reconcile the asset **up** to the template
(asset ← template's `backlog:` block), guarded by a parity test that byte-compares
the **frontmatter region** of the two files (the bytes between the `---`
delimiters, read via `Path.read_bytes()` — not via `lifecycle_config.py`
`_extract_frontmatter_text`, whose line-ending normalization would mask CRLF /
trailing-newline drift). The test additionally asserts the asset frontmatter
carries the load-bearing option lines, which catches convergent comment loss a
bare two-file diff would miss. Comparing the frontmatter region only tolerates
the asset's body sentence for free, with no allowlist.

Keep the **asset** as the canonical schema referent in the docs **for the
scaffolded field set** — it ships in the `cortex-core` plugin, so plugin-only
users without the CLI can reach it, and the parity gate is what makes that
citation trustworthy on the frontmatter / field list. The asset's body prose and
any consumed-but-unscaffolded field (e.g. `branch-mode`, consumed by
`read_branch_mode` but in neither scaffolded template) are explicitly outside the
gate's guarantee and are handled as documented exceptions, not as part of the
asset's enumeration.

## Trade-off / rejected alternatives

Accepts ongoing dual-maintenance of the shared frontmatter in exchange for
avoiding:

- **Generate the asset from the template** (a deterministic transform + `--check`
  pre-commit, the `sync-install-guard` shape). Rejected: it inverts the channel
  dependency (the CLI package would drive plugin source) and stamps a
  self-contradictory "GENERATED — DO NOT EDIT" header onto a file the docs tell
  users to copy and edit.
- **A `yaml.safe_load` parsed-dict parity gate.** Rejected: the block's
  `github-issues` / `jira` / `none` / `instructions:` lines are all YAML comments,
  which `safe_load` discards — the gate would pass the instant the asset had
  `backend: cortex-backlog`, even with every documenting comment stripped (the
  exact "missing backend section" defect).
- **Collapse the asset to a thin pointer / delete it.** Rejected: plugin-only
  users have neither the init template nor `cortex init` on disk; the asset is
  their only schema reference.
- **Reconcile with no gate.** Rejected: it does nothing to prevent recurrence, and
  the schema is still moving (#318 hardens external backends; advisory keys are
  slated for activation) — a named "applies in multiple known places" condition
  that argues for a cheap durable gate now.

The parity test runs under developer-run `just test`, not commit-time, and —
since the #386 CI repair — also as a blocking step in `validate.yml` (the
push-time allowlist), superseding the earlier deliberate deferral; the
asset↔mirror pair remains pre-commit-blocking as well. Reconcile is
**up**, never down: editing the template would change the init-artifacts hash and
fire a one-time `.cortex-init` drift report into every initialized repo, and a
collapse-down would silently regress #317 (no test catches it —
`test_init_backlog_scaffold.py` only asserts the default). The maintenance
*mechanism* (hand-maintain + gate) is reversible to a generator later, but the
content reconcile is effectively a one-way ratchet once plugin-only users have
copied the completed asset.
