# Review: document-claude-config-dir-direnv-pattern-for-per-repo-permissions-scoping

## Stage 1: Spec Compliance

### Requirement 1: "Per-repo permission scoping" section exists in `docs/setup.md` with all required content
- **Expected**: Seven sub-ACs — section heading, both upstream issues, direnv/envrc + CLAUDE_CONFIG_DIR counts, cp -R + rm + symlink warnings, all 5 foot-guns, upstream partial-support pointer, research backlink.
- **Actual**: All seven sub-ACs pass against `docs/setup.md` at commit 77602c9.
  - **R1.1 heading**: `grep -cE '^##+ .*[Pp]er-repo permission' docs/setup.md` = 1 (section `## Per-repo permission scoping` at line 163).
  - **R1.2 upstream issues**: `grep -q 'issues/12962'` and `grep -q 'issues/26489'` both pass (linked inline in the status preamble).
  - **R1.3 direnv walkthrough**: section-scoped `grep -c '\.envrc'` = 2, section-scoped `grep -c 'CLAUDE_CONFIG_DIR'` = 10 (well above the ≥4 threshold the plan tightened to).
  - **R1.4 cp -R symlink trap with explicit `rm`**: section-scoped `grep -cE 'cp -[rR]'` = 3, `grep -cE 'rm [^[:space:]]+'` = 4 (one rm per host-shared file, meeting the plan's tightened 4-filename coverage), `grep -c 'symlink'` = 11 file-wide (well above ≥2).
  - **R1.5 all 5 foot-guns**: section-scoped `grep -qi` passes for `setup-merge`, `just setup`, `notify`, `evolve|auto-memory|audit-doc|count-tokens`, and `concurrent|scope confusion`. Each foot-gun is framed with failure mode plus workaround.
  - **R1.6 upstream partial-support**: literal `#36172` appears in the "Upstream Claude Code partial-support bugs" sub-list along with `#38641`, `#42217`, `#34800` for context.
  - **R1.7 research backlink**: `grep -c 'research/user-configurable-setup/research.md'` = 1 (final line of section: "For the full decision record and failure-mode inventory, see `research/user-configurable-setup/research.md`.").
- **Verdict**: PASS
- **Notes**: Plan's stricter negative checks also pass — `cp -RL` is absent from the section body, and no occurrence of `handles` appears within 80 characters of any foot-gun keyword (forward or reverse). Ordering check passes: first `symlink` mention at body-line 10 precedes first `setup-merge` mention at body-line 38, so the cp -R symlink-trap warning lands before the foot-guns list as the spec requires.

### Requirement 2: DR-7 audit re-check at execution time, before any file edits
- **Expected**: Executing agent runs `gh issue view` against 12962 and 26489, compares structured JSON fields against the WARM criteria, and either proceeds or halts. Interactive/session-dependent.
- **Actual**: `events.log` shows Task 1 `task_complete` at 2026-04-11 with `note: "DR-7 audit proceed verdict. Both issues OPEN, no assignees, labels do not match halt regex."` Task 2 and Task 3 proceeded after Task 1. No `plan_halt` event appears in `events.log`. The Task 1 note directly references the plan's three narrowed halt criteria (state=OPEN, assignees empty, label regex non-match) and reports a clean proceed verdict for both issues. No commits or file edits occurred before the audit.
- **Verdict**: PASS
- **Notes**: Task 1 is interactive/session-dependent per spec and plan; the events.log entry is the only durable trace and it is present, timestamped, and clearly records a WARM-confirming outcome.

### Requirement 3: Section length and location are bounded
- **Expected**: (3.1) section added to existing `docs/setup.md`, not a new file — `test -f docs/per-repo-permissions.md` must return 1. (3.2) Section body between 30 and 80 lines inclusive by the spec's `awk c++` line counter (plan tightens to non-blank lines in [30, 80]).
- **Actual**:
  - **R3.1**: `test -f docs/per-repo-permissions.md` returns 1 (file does not exist). Content is embedded in `docs/setup.md` between the existing `## Customization` and `## macOS Notifications` sections, matching the spec's location constraint exactly.
  - **R3.2 (spec metric)**: `awk '/^##+ .*[Pp]er-repo permission/{flag=1; c=0; next} flag && /^## /{exit} flag{c++} END{print c}' docs/setup.md` = 54, within [30, 80].
  - **R3.2 (plan metric)**: `grep -c '[^[:space:]]'` on the extracted body = 35 non-blank lines, within [30, 80].
- **Verdict**: PASS
- **Notes**: Length sits comfortably in the lower half of the envelope — the spec's 30-line minimum was a concern in the critical-review events, but the implementation lands at 35 non-blank lines / 54 total with no cruft padding.

## Requirements Drift

**State**: none
**Findings**:
- None. The implementation adds documentation only; it does not introduce any new behavior that the global `settings.json` template, the sandbox configuration, or the file-based state architecture would need to reflect. The quality attribute "Defense-in-depth for permissions" in `requirements/project.md` describes what the ships-to-users *template* does (conservative allows, comprehensive deny, sandbox on). `CLAUDE_CONFIG_DIR` is an upstream Claude Code mechanism that has always been available; this section merely tells users it exists and warns about foot-guns. Nothing the cortex-command framework itself does has changed, and there is no new cortex-owned surface that widens or narrows the permission envelope. The tension flagged during the refine phase's clarify_critic — that a user could create a more-permissive shadow settings.json — is a property of Claude Code's design, not of anything this commit adds; the docs section in fact warns against it (foot-gun #1 tells users not to run `/setup-merge` from a shadowed shell precisely because it would bypass the hardened defaults). Documenting a known limitation is not drift.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Section heading `## Per-repo permission scoping` matches the sentence-case, single-`##` pattern used by every other top-level section in `docs/setup.md` (`## Before You Start`, `## Quick Setup`, `## Customization`, etc.). Sub-headings `### How it works`, `### Setup with direnv`, `### Limitations and foot-guns` mirror the existing `### settings.json`, `### Adding an MCP Server`, `### Option A: API Key` depth convention. Inline-code formatting (backticks around `CLAUDE_CONFIG_DIR`, `~/.claude`, `.envrc`, `/setup-merge`) is consistent with the rest of the file.
- **Error handling**: N/A — this is a documentation change. The prose equivalent is *failure-mode framing*, and the section honors the spec's Technical Constraints strictly:
  - The `cp -R` symlink trap is explicitly the first limitation, flagged as "(most severe)", before the foot-guns bullet list — matching spec constraint "the `cp -R` symlink trap must lead the limitations."
  - `cp -RL` is explicitly rejected with an explanation ("dereferencing all symlinks produces a frozen snapshot that won't pick up repo updates, which is the wrong default for a living cortex-command install"), matching spec constraint "Do NOT recommend `cp -RL` as a blanket fix."
  - Foot-guns are framed as rules-to-follow, not as things cortex-command handles automatically — the intro sentence reads "None of them are managed automatically — treat each as a rule to follow, not a problem the shadow resolves for you," which directly addresses spec Technical Constraint #3 ("The docs say 'don't do X' or 'X has the following failure mode'; they do NOT say 'cortex-command handles X for you.'"). Negative grep confirms zero `handles` near foot-gun keywords.
  - Each foot-gun includes (a) anchor keyword, (b) failure mode description, and (c) workaround, matching the plan's Content element 5 structure.
- **Test coverage**: Plan's verification block (Task 2, ~25 checks including section-scoping, length, content presence, negative checks, rm 4-filename coverage, literal #36172, and ordering) was executed per events.log task-2 note and all checks pass against the final state of `docs/setup.md`. I re-ran the spec's R1 ACs independently (file-wide and section-scoped) and all pass. The plan's length metric (non-blank = 35) and the spec's length metric (all lines = 54) both land in [30, 80].
- **Pattern consistency**: The section reads clearly for a user without research context — the opening paragraph explains the problem (additive merge, no subtraction), the mechanism (`CLAUDE_CONFIG_DIR`), the upstream tracker issues (with inline links), and the workaround framing in one paragraph before diving into "How it works" and "Setup with direnv". Numbered steps in "Setup with direnv" use the same numbered-list pattern as "Authentication > Option A/B" elsewhere in the file. Code fences use bare (no language) or plain-text blocks consistent with the rest of `docs/setup.md` (which also uses bare fences for shell commands in Backup and Quick Setup sections). Section placement between `## Customization` (which discusses `settings.json`, permissions, and MCP) and `## macOS Notifications` is logical — users looking for permission scoping will be reading Customization already.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
