---
schema_version: "1"
uuid: 99d6aaf6-4300-4428-9711-f1a6aa1f714f
title: lifecycle.config template ships dormant skip-specify/skip-review live, warning on every CLI invocation
status: in_progress
priority: low
type: chore
created: 2026-07-15
updated: 2026-07-16
tags: ['lifecycle', 'cli', 'config']
areas: ['lifecycle']
lifecycle_phase: research
lifecycle_slug: lifecycleconfig-template-ships-dormant-skip-specify
complexity: complex
criticality: medium
spec: cortex/lifecycle/lifecycleconfig-template-ships-dormant-skip-specify/spec.md
---
## Why

Every `cortex-*` CLI invocation that reads `lifecycle.config.md` in a consumer repo (wild-light) prints 2–4 stderr warnings of the form `'<field>' … is documented but not honored by any consumer — setting it currently has no effect`, for the four fields `default-tier`, `default-criticality`, `skip-specify`, and `skip-review`.

The warning itself is working as designed — the config reader defines a dormant-keys set and flags them deliberately. The papercut is that the **shipped `cortex init` template still sets two of them (`skip-specify`, `skip-review`) live** while commenting out the other two, so a repo seeded from the template carries the two live keys and warns on essentially every lifecycle/backlog CLI call. The template is internally inconsistent (two dormant fields commented, two live), and the constant noise trains operators to ignore config warnings — including the genuine `unknown key` / `malformed YAML` warnings emitted by the same code.

## Proposed direction

Decide per field and make the template consistent with the decision:

- If these stay dormant: comment out `skip-specify` / `skip-review` in the template (matching `default-tier` / `default-criticality`), so a fresh `cortex init` does not seed live dormant keys. Optionally offer a one-time migration/lint that comments them in existing consumer configs.
- If they should be honored: wire the four `_DORMANT_KEYS` into their consumers (tier/criticality override, specify/review skipping) and drop them from `_DORMANT_KEYS`.

Either way the goal is: a freshly-initialized repo does not emit dormant-key warnings on every CLI call.

## Edges — considered

- The warning mechanism is intentional and should stay — this ticket is about not shipping a template that trips it by default, not about silencing the warning.
- Consumer repos already seeded (e.g. wild-light) keep the live keys until their own config is edited; a framework-side template fix does not retroactively quiet them. A migration/lint is optional scope.

## Touch points

- `cortex_command/lifecycle_config.py:47` — `_DORMANT_KEYS`; `:55-66` — `_warn_config_keys` (the emitter, called from every `read_*` config reader).
- `cortex_command/init/templates/cortex/lifecycle.config.md:10-13` — the inconsistency (default-tier/default-criticality commented; skip-specify/skip-review live).