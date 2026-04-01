# Specification: docs-audit

## Problem Statement

The `docs/` directory contains 8 markdown files covering setup, skills, the lifecycle system, overnight runner, pipeline, backlog, dashboard, and interactive phases. Quality is uneven: several files have broken references, incomplete module tables, missing architectural explanations, and stale counts that diverge from the actual codebase. This degrades the project's stated quality attribute — "the system should remain navigable by Claude even as it grows" — and forces Claude and human operators to fill in gaps with assumptions rather than documentation. This audit fixes all identified gaps in-place, with larger rewrites permitted for the most problematic files.

## Requirements

> **Priority**: All requirements are **Must-Have**, per explicit user instruction to fix all known gaps identified in research. There are no Should-Have or Won't-Do items in this spec — every gap listed is a specific, bounded fix to an identified problem.

### skills-reference.md

1. **Remove broken serena-memory reference**: Remove the `serena-memory` skill entry. The skill does not exist in `skills/`. Acceptance: no reference to `serena-memory` in the file after the change.
2. **Fix skill count**: Correct the opening claim to match the actual number of SKILL.md files in `skills/` (currently 29; the file claims 30). Acceptance: stated count matches `ls skills/*/SKILL.md | wc -l`.
3. **Add usage guidance**: Add a brief section or inline notes explaining when to use overlapping skills — specifically the relationship between `/dev`, `/lifecycle`, and `/overnight`. Acceptance: a reader can distinguish the entry points without consulting the actual skill files.

### pipeline.md

4. **Complete module table**: Add entries for the 2 `.py` files in `claude/pipeline/` currently missing from the table: `conflict.py` and `merge_recovery.py`. (`parser.py` is already documented.) Acceptance: module table row count equals `ls claude/pipeline/*.py | wc -l`.
5. **Explain master-plan.md vs. plan.md**: Add a clear explanation of what each file contains and when each is used. Acceptance: a reader understands the two-level plan structure without consulting the code.
6. **Document revert_merge() actual behavior**: The existing recovery section calls `revert_merge('my-feature')` without explaining that this function reverts on `base_branch` (defaults to `main`) — not on the integration branch. Add a note clarifying that the function targets the base branch by default, and what argument to pass if a different base branch is needed. Acceptance: the doc makes clear which branch is targeted and how to override it.

### agentic-layer.md

7. **Add Hooks Architecture section**: Add a section covering: the list of hook events and when each fires, how hooks communicate decisions (via JSON `permissionDecision` output — `"allow"` or `"deny"` — not via exit code), stdin/stdout contracts for input-reading hooks, ordering guarantees, and what happens on hook timeout or crash. Acceptance: section covers all four areas; a developer can write a new hook without consulting the source code. Note: do not document "exit 2 = block" semantics — hooks in this project block via JSON output; verify exit code behavior against actual hook files before writing.
8. **Integrate hooks into workflow narrative**: The existing hooks table should be connected to the workflow diagram — show where hooks fire in the execution flow. Acceptance: the workflow description references hooks at their actual trigger points (e.g., "before commit," "at session start").
9. **Clarify /dev routing logic**: Explain what criteria the `/dev` skill uses to route to `/lifecycle`, `/discovery`, `/backlog`, or direct implementation. Acceptance: a reader can predict which path `/dev` will take for a given request without running it.

### overnight.md

10. **Complete module table**: Verify and add entries for any `.py` files in `claude/overnight/` missing from the table. (`integration_recovery.py` is already documented at the expected location.) Acceptance: module table row count equals `ls claude/overnight/*.py | wc -l`.
11. **Explain running status and crash recovery**: Add an explanation of when/how a feature can end up in `running` state — including normal round completion (not just crash) — and how to diagnose and recover from it. Acceptance: the recovery section lists the specific ways `running` status occurs and the recovery procedure for each.
12. **Add rationale for 3–5 features per session**: The "Session size" best practice currently states the range without explanation. Add one sentence explaining the tradeoff (context size, recovery cost, etc.). Acceptance: the rationale is present inline with the recommendation.
13. **Clarify concurrency and conflict detection**: Explain how concurrent feature execution interacts with git conflict detection — specifically, at what point conflicts are detected and what triggers a pause vs. automatic resolution attempt. Acceptance: a reader understands what determines whether concurrent features can safely run in parallel.

### interactive-phases.md

14. **Remove non-existent references/directories**: Remove references to `skills/refine/references/` and `skills/interview/references/` — these directories do not exist. Acceptance: no reference to those paths after the change; replace with correct paths or remove entirely.
15. **Clarify manual tier escalation behavior**: Explain what happens when a user manually escalates the complexity tier mid-lifecycle — specifically, whether the escalation is persisted to the backlog item's YAML frontmatter. Acceptance: the explanation is explicit about persistence behavior.
16. **Document stale artifact behavior**: Add a note explaining that the readiness gate checks file existence, not content freshness — and what a practitioner should do if they suspect research or spec artifacts are stale. Acceptance: the behavior is documented as a known limitation with a suggested workaround.

### backlog.md

17. **Promote readiness gate callout**: Move the "readiness gate checks file existence, not quality" callout from Best Practices to the Gate section where it is most relevant. Acceptance: the callout appears in the Gate section (before Best Practices), not only in Best Practices.
18. **Enumerate TERMINAL_STATUSES**: List the actual terminal status values. Source: `claude/common.py` — the canonical definition is `frozenset({"complete", "abandoned", "done", "resolved", "wontfix", "won't-do", "wont-do"})`. The existing doc lists 5 of these; update to the full 7. Acceptance: the doc lists all 7 values and cites `claude/common.py` as the source, without requiring the reader to open the file.
19. **Add thin spec example**: Add a brief example illustrating what a "thin spec" looks like and why it causes blocking deferrals in the overnight runner. Acceptance: the example is concrete (shows actual YAML or spec content) rather than abstract.

### setup.md

20. **Fix Windows Terminal section nesting**: The Windows Terminal setup content currently appears under the "Ghostty Terminal (macOS)" heading. Move or re-nest it under a clear platform-specific heading. Acceptance: Windows and macOS terminal setup are visually and structurally separated.
21. **Clarify caffeinate-monitor.sh dual role**: Explain whether `caffeinate-monitor.sh` is solely a symlinked binary or also registered as a launchd service, and what the difference means for users who want it to start automatically vs. run on demand. Acceptance: both use cases are explicitly described.
22. **Document MCP plugin patterns**: Add a brief example of what an MCP plugin entry looks like in `claude/settings.json`. Acceptance: a reader can add a new MCP plugin entry without consulting another repo.

### dashboard.md

23. **Clarify deployment scenarios**: Explain whether the dashboard is designed for localhost only or can be safely proxied. Given the no-authentication note, add guidance on when proxying is appropriate. Acceptance: the Known Limitations section explicitly addresses the localhost-vs-proxied question.
24. **Add state file schemas**: For the listed data sources (`overnight-state.json`, `overnight-events.log`), add the key fields each contains. Acceptance: a reader can locate a specific piece of runtime information without trial-and-error.
25. **Document polling interval**: State the HTMX polling refresh rate and the expected latency for new feature status to appear. Acceptance: interval value is explicit (or "not configurable" if hardcoded).

## Non-Requirements

- Do not create new doc files — only modify existing files in `docs/`
- Do not reorganize the overall docs structure (file names, top-level nav links)
- Do not add documentation for skill SKILL.md files, lifecycle reference files, or CLAUDE.md — those are separate from the docs/ audit
- Do not cover external tool setup (Tailscale, mosh, Cloudflare Tunnel configuration details) — those belong in machine-config
- Do not add a formal changelog or versioning scheme — the existing docs have none and adding one is out of scope

## Edge Cases

- **Non-existent referenced file**: If a file referenced in a doc (e.g., a `.py` module) is not found at the expected path, document its absence explicitly rather than fabricating a description. The gap itself is informative.
- **Renamed reference**: If a broken reference points to something renamed (vs. deleted), update the reference to the current name and verify by reading the actual file.
- **Accurate but unclear section**: Prefer targeted clarification over full rewrite when the content is correct but poorly explained. Full rewrites are reserved for sections that are materially wrong or missing.
- **Count drift**: Skill and module counts stated in the spec are point-in-time values at audit execution. If counts differ at implementation time, use the live `wc -l` result as truth — not the counts in this spec.
- **Hook behavior verification**: Before documenting any hook exit code or output contract, read the actual hook file. Do not document inferred behavior — hooks in this project use JSON output for decisions, not exit codes, but individual hooks may differ.

## Technical Constraints

- All file paths written into docs must be verified to exist before inclusion
- Skill count corrections must use `ls skills/*/SKILL.md | wc -l` as the authoritative source at implementation time
- Module table corrections for pipeline.md and overnight.md must use `ls claude/pipeline/*.py | wc -l` and `ls claude/overnight/*.py | wc -l` respectively
- Existing nav link structure (`[← Back to ...]`) and `For:` / `Assumes:` header patterns must be preserved in all modified files
- No changes to how anything works — this is documentation only; no code, script, or config changes
