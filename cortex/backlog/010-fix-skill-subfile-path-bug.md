---
schema_version: "1"
uuid: a3b93933-ae9c-4445-978a-e9478b101e77
id: 010
title: "Fix skill sub-file path bug across all skills"
type: chore
status: complete
priority: high
parent: 009
tags: [requirements, skills, sandbox]
created: 2026-04-03
updated: 2026-04-03
discovery_source: cortex/research/requirements-audit/research.md
session_id: null
lifecycle_phase: research
lifecycle_slug: fix-skill-sub-file-path-bug-across-all-skills
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/fix-skill-sub-file-path-bug-across-all-skills/spec.md
---

# Fix skill sub-file path bug across all skills

## Context from discovery

Skills with sub-files (e.g., `references/gather.md`) reference them with relative links in their SKILL.md. When a skill is invoked from any repo other than cortex-command, Claude resolves these as `~/.claude/skills/{skill}/references/foo.md` — a path outside the CWD that triggers sandbox permission prompts. This worked silently when skills lived in machine-config (the CWD at the time); moving skills to the separate cortex-command repo exposed the bug.

The fix is to use repo-relative absolute paths (e.g., `skills/requirements/references/gather.md`) everywhere a SKILL.md references a sub-file. These paths resolve correctly from within cortex-command, and sub-files are never loaded directly by other repos.

Additionally, the skill authoring reference (`claude/reference/context-file-authoring.md`) should document this as a required convention so new skills don't repeat the mistake.

## Scope

- Audit all skills under `skills/` for relative sub-file references
- Replace relative links with repo-relative absolute paths
- Document the convention in the skill authoring reference
