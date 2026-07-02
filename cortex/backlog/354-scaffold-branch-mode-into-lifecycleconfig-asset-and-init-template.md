---
schema_version: "1"
uuid: e58571ec-3c61-4f10-853a-e6773a6d980c
title: Scaffold branch-mode into lifecycle.config asset and init template
status: backlog
priority: low
type: chore
created: 2026-07-02
updated: 2026-07-02
---
## Why
The `branch-mode` field is read by `read_branch_mode` (the lifecycle branch-selection preflight) but is scaffolded into neither the cortex-core plugin asset (skills/lifecycle/assets/lifecycle.config.md) nor the init template (cortex_command/init/templates/cortex/lifecycle.config.md). Operators adopting cortex-command must set it by hand; until they do the field is absent and the picker fires every time. This is the pre-existing "consumed-but-unscaffolded exception" documented in the docs/overnight-operations.md branch-mode note. Surfaced during #352, which consolidated the branch-mode value docs into that note.

## Role
Add `branch-mode` to both scaffolded sources with a behavior-preserving default (`prompt` = picker fires every time, identical to field-absent), so a fresh `cortex init` scaffolds it. Because the ADR-0017 parity gate keeps the asset and init-template frontmatter byte-identical, both files must be edited together in one commit.

## Integration
tests/test_lifecycle_config_parity.py compares the asset and init-template frontmatter regions byte-for-byte and also checks a load-bearing option-line allowlist. Edit both sources together and add the new line to the allowlist if the gate requires it. Repo instances (cortex/lifecycle.config.md) already set branch-mode explicitly and are unaffected. Regenerate the cortex-core plugin mirror in the same commit if the asset lives under a build-output tree.

## Edges
- The scaffolded default must be `prompt` (or omitted-equivalent) so existing adopters see no routing change.
- Once shipped, update the docs/overnight-operations.md "separate follow-up" note to reflect that branch-mode is now scaffolded.

## Touch points
- skills/lifecycle/assets/lifecycle.config.md
- cortex_command/init/templates/cortex/lifecycle.config.md
- tests/test_lifecycle_config_parity.py (option-line allowlist, if applicable)
- docs/overnight-operations.md (the :717 unscaffolded-exception note)