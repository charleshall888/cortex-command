# Specification: Document overnight pipeline operations and architecture

## Problem Statement

A docs audit surfaced 13 gaps in overnight pipeline documentation; research surfaced 8 more. A contributor (or future-me debugging at 2am) currently cannot understand how overnight actually works without code-diving through `batch_runner.py`, `review_dispatch.py`, `merge.py`, `brain.py`, `runner.sh`, and the orchestrator prompt. This ticket produces a new `docs/overnight-operations.md` covering all 21 gaps, relocates architecture/debug content out of `docs/overnight.md` using a progressive-disclosure split, trims duplication in `docs/pipeline.md`, adds a source-of-truth convention to `CLAUDE.md`, and adds a pytest guarding the documented per-task tool allowlist against code drift.

## Requirements

1. **New file `docs/overnight-operations.md` exists**: Acceptance — `test -f docs/overnight-operations.md && exit 0`. Pass if exit code = 0.

2. **All 21 gaps are documented**, each by a dedicated subsection (H3 or deeper) whose heading contains the named keyword(s) below. Acceptance — `grep -c` returns ≥1 for each keyword string, checked manually during review:

   Original 13 (from ticket body):
   - "review_dispatch" or "Post-Merge Review"
   - "allowed_tools" or "Per-Task Agent Capabilities"
   - "pipeline/prompts" and "overnight/prompts" (both, distinguishing the two prompt directories)
   - "escalations.jsonl" or "Escalation System"
   - "overnight-strategy.json" or "Strategy File"
   - "Conflict Recovery" or "trivial fast-path"
   - "Cycle-breaking" or "cycle-breaking"
   - "Test Gate" or "integration_health"
   - "--tier" or "Concurrency Tuning"
   - "brain.py" or "SKIP/DEFER/PAUSE"
   - "lifecycle.config.md"
   - "apiKeyHelper" or "Auth Resolution"
   - "orchestrator_io"

   8 additional (from research):
   - ".runner.lock" or "Runner Lock"
   - "report.py" or "Morning Report Generation"
   - "agent-activity.jsonl"
   - "Dashboard Polling" or "dashboard state"
   - "Session Hooks" or "SessionStart" or "notification hooks"
   - "Scheduled Launch" or "scheduled-launch"
   - "interrupt.py" or "Startup Recovery"
   - "Log Disambiguation" or a table that names `events.log`, `pipeline-events.log`, `agent-activity.jsonl` together

3. **Extraction from `docs/overnight.md` — move-everything model**: All architectural, debugging, and operator-reference sections move fully into `docs/overnight-operations.md`. No stub-plus-full duplication is retained. `docs/overnight.md` adds one short "Where to find everything else" paragraph near the top pointing to `docs/overnight-operations.md` for mechanics, state files, recovery, and debugging. Sections to move in full: Authentication (98-156), Execution Phase / Round Loop / Circuit Breakers / Signal Handling / Module Reference (259-362), State Files and Artifacts (390-425), Conflict avoidance and resource protection (470-503), Recovery: corrupt state (524-565), Recovery: merge conflict (567-585). Acceptance — (a) `grep -c "^## Authentication\|^## State Files\|^### Module Reference\|^### The Round Loop\|^### Circuit Breakers\|^### Signal Handling\|^## The Execution Phase\|^### Recovery: corrupt\|^### Recovery: merge conflict\|^### Conflict avoidance" docs/overnight.md` = 0; (b) `grep -c "overnight-operations.md" docs/overnight.md` ≥ 1.

4. **Cross-link hygiene**: All anchors in `docs/overnight.md:15` jump-nav and `docs/overnight.md:263, 297, 444` pointers are updated to target either the retained Level 1 section or the new `docs/overnight-operations.md` anchor. Acceptance — every `](overnight.md#...)` and `](overnight-operations.md#...)` link in `docs/`, `README.md`, and any skill files resolves to a real heading in the target file. Interactive/session-dependent: this ticket deliberately does not introduce a markdown-link-checker; resolution is verified by the reviewer following each updated link once.

5. **`docs/pipeline.md` deduplication**: The following named sections are trimmed or converted to cross-links: `§Recovery Procedures` (lines 107-167) — replaced with a 1-2 sentence pointer to `overnight-operations.md` for orchestrator-side recovery behavior, while per-module Files/Inputs/Returns entries for `conflict.py`, `merge_recovery.py`, `integration_recovery.py` remain. Acceptance — Interactive/session-dependent: manual read confirms no behavioral claim about repair/review/recovery appears in both `pipeline.md` and `overnight-operations.md`; a line count drop is an indicator, not the gate.

6. **Source-of-truth rule added to `CLAUDE.md`**: A new convention bullet or subsection documents the ownership boundary: `docs/overnight-operations.md` owns round loop + orchestrator behavior; `docs/pipeline.md` owns pipeline-module internals; `docs/sdk.md` owns SDK model-selection mechanics. Acceptance — `grep -F "overnight-operations.md" CLAUDE.md` returns ≥1 match; `grep -F "source of truth" CLAUDE.md` (case-insensitive) returns ≥1 match in the same paragraph.

7. **Pytest guards per-task tool allowlist**: A new test asserts the documented tool allowlist equals `claude.pipeline.dispatch._ALLOWED_TOOLS`. Acceptance — `just test` runs the new test and passes (exit 0); deliberately mutating the list in `dispatch.py` or the documented snippet causes the test to fail. The test lives in `tests/` alongside existing tests and uses existing fixtures.

8. **`retros/` 2am-pain mining (bounded)**: Before finalizing section content, the author greps up to the 10 most recent `retros/*.md` files for "2am", "couldn't find", "unclear", "surprising", "stuck". Each surfaced pain-point is dispositioned as one of: (a) added to `docs/overnight-operations.md` with a named subsection reference, (b) filed as a separate backlog ticket (ticket number recorded), or (c) explicitly dismissed with rationale. Acceptance — at least 3 retros scanned (sanity floor); the PR description enumerates "mined N retros; dispositions: {added: X, filed: Y, dismissed: Z with rationale}"; binary-check — `gh pr view --json body | grep -E "mined [0-9]+ retros?"` returns ≥1 match AND the dispositions sum to the scanned count. Interactive/session-dependent: the quality of disposition choices is reviewer-judged.

9. **Security and Trust Boundaries section exists in the new doc**: A dedicated H2 section enumerates each boundary once — `--dangerously-skip-permissions`, the `_ALLOWED_TOOLS` SDK-level bound, dashboard `0.0.0.0` unauthenticated by design, keychain prompt as a session-blocking failure mode, "local network" ≠ "home network". Acceptance — `grep -c "^## Security" docs/overnight-operations.md` = 1.

10. **Tool allowlist documented literally**: The doc reproduces `_ALLOWED_TOOLS` verbatim (not by intent-prose) and contains a comment like "source of truth: `claude/pipeline/dispatch.py`; pytest enforces equivalence." Acceptance — the pytest from requirement 7 passes.

11. **No line-number cross-references; positive anchor resolution**: Cross-references use filename + function name or filename + section heading only. Acceptance — (a) negative check: `grep -E "\.py:[0-9]+|\.md:[0-9]+" docs/overnight-operations.md` returns zero matches (one intentional exception permitted: an optional "state at commit {SHA}" footer that clearly disclaims rot risk); (b) positive check: Interactive/session-dependent — the reviewer spot-checks 5 randomly-picked function-name and section-heading cross-references and confirms each target actually exists in the referenced file.

12. **`brain.py` disambiguation lede**: The `brain.py` subsection's opening disambiguates it from a "repair" agent — pinning down what it is (post-retry triage), what it does (SKIP/DEFER/PAUSE decision), and that there is no RETRY action by design. Acceptance — Interactive/session-dependent: manual review confirms the disambiguation precedes any other content under the heading; the exact phrasing is the author's choice, and brittle string-pinning is intentionally avoided.

13. **Progressive-disclosure principle acknowledged with rationale**: Either `CLAUDE.md` (near the source-of-truth rule from req 6) or `docs/overnight-operations.md` (preamble) explains in one paragraph (≥3 sentences) how the doc split applies the progressive-disclosure concept from `claude/reference/claude-skills.md` to human-facing docs — specifically naming which reader access pattern the split optimizes for (e.g., "readers landing on `overnight.md` via cross-link vs. landing on `overnight-operations.md` via stack trace"). Acceptance — (a) `grep -F "progressive disclosure" CLAUDE.md docs/overnight-operations.md` returns ≥1 match (case-insensitive); (b) Interactive/session-dependent — reviewer confirms the paragraph explains the generalization rather than just dropping the term.

## Non-Requirements

- **No runtime/behavior changes to the overnight runner, pipeline, dashboard, or any Python/shell code** other than the single pytest file added for requirement 7. This is a docs ticket; code changes are limited to tests.
- **No automated gap-coverage checker**: user selected "section checklist in spec + manual review" over tooling. No `just docs-audit` recipe is added by this ticket.
- **No reorganization of `docs/agentic-layer.md`, `docs/sdk.md`, `docs/dashboard.md`, `docs/backlog.md`, or `docs/setup.md`** beyond optional 1-line cross-link additions.
- **No new doc index or docs landing page** is created. Each doc continues to link to others directly; no `docs/README.md` or `docs/index.md`.
- **No enforcement of the orchestrator `rationale` field convention**. This is a pre-existing convention gap (requirements/pipeline.md:127); the doc will describe it as it stands — convention documented, enforcement requires prompt changes — not close the gap.
- **No expansion of `orchestrator_io` API**. The doc documents what's there today (4 re-exports); it does not propose additions.
- **Not a full `pipeline.md` rewrite**. Only duplicated sections are trimmed; the module table and state-schema sections stay.
- **No "last validated" date headers on individual procedures**. The whole doc carries a single file-level note in the footer (see requirement 14 in Edge Cases below — actually handled as a convention, not a requirement).

## Edge Cases

- **Content that fits badly under any of the 3 named sections (Architecture/Tuning/Observability)**: extra H2 sections are permitted (e.g., `## Internal APIs` for `orchestrator_io`, `## Code Layout` for the prompts-directory split, `## Security and Trust Boundaries`). Do not contort the three-section outline.
- **A gap is partially covered in an existing doc (e.g., model selection in `sdk.md`)**: the operations doc owns tier × criticality → role dispatch logic; detailed per-model SDK configuration stays in `sdk.md` with a cross-link in both directions.
- **A retro surfaces a pain-point that belongs to a different ticket** (e.g., a bug, not a doc gap): note in the PR description under "mined retros, deferred to follow-up"; file a backlog ticket if the author has time, otherwise note for the user.
- **Pytest from requirement 7 is self-demonstrating**: the test's assertion structure is explicit (`set(doc_tools) == set(dispatch._ALLOWED_TOOLS)`) such that a reviewer can see the drift-catch behavior without running a mutation experiment. No mutation ritual is required as part of shipping.
- **Doc exceeds reasonable length** (say, >1000 lines): progressive disclosure allows moving specific deep-reference content to a small appendix file (pointer, not enumeration), per research recommendations. Appendix filename pattern: `docs/overnight-operations-{topic}.md`. An appendix is justified only when the content is a reference lookup (schema, API surface) that readers consult rarely — not when it is prose.
- **`pipeline-events.log` is referenced as append-only JSONL in `requirements/pipeline.md:126` but not in current docs**: the new doc documents the append-only contract explicitly.
- **Anchors that disappear when sections move**: do not leave redirect stubs in `docs/overnight.md`. If an external reference to a removed anchor exists, update the reference; the ticket does not introduce per-anchor HTML redirects.

## Changes to Existing Behavior

- **MODIFIED: `docs/overnight.md`** — all architectural and operator-reference content (Authentication, Execution Phase, Round Loop, Circuit Breakers, Signal Handling, Module Reference, State Files, Conflict avoidance, Recovery procedures) removed in full and replaced with one short paragraph pointing to `docs/overnight-operations.md`. Jump-to nav pruned to what remains. Cross-links updated. The file becomes a lean "how to run overnight" guide.
- **MODIFIED: `docs/pipeline.md`** — Recovery Procedures section trimmed to cross-link to `overnight-operations.md` for orchestrator behavior; pipeline-internal details retained. Line count drops ≥30.
- **MODIFIED: `CLAUDE.md`** — new source-of-truth rule added (1-3 lines) documenting doc-ownership boundaries between `overnight-operations.md`, `pipeline.md`, and `sdk.md`.
- **ADDED: `docs/overnight-operations.md`** — new primary reference for overnight mechanics and debugging.
- **ADDED: `tests/test_dispatch_allowed_tools.py`** (or equivalent name, author's judgment) — pytest asserting doc snippet equals `dispatch._ALLOWED_TOOLS`.
- **No changes** to `batch_runner.py`, `review_dispatch.py`, `dispatch.py`, `brain.py`, `runner.sh`, `strategy.py`, `deferral.py`, `orchestrator_io.py`, or any other Python/shell module.

## Technical Constraints

**Exact-phrase constraints (from `requirements/` — must be preserved verbatim or very close)**:
- Forward-only phase transitions: `planning → executing → complete`; any phase → `paused`.
- Atomic state writes: tempfile + `os.replace()`.
- Integration branches persist after session completion (not auto-deleted).
- Artifact commits travel on the integration branch; only the morning report commit stays on local main.
- State file reads are not lock-protected by design — permanent architectural constraint.
- Repair attempt cap is fixed: single Sonnet→Opus escalation for merge conflicts; max 2 attempts for test-failure repair. **Two different codepaths, two different numbers — do not unify.**
- Dashboard binds `0.0.0.0`, unauthenticated, by design. Dashboard is read-only.
- Orchestrator owns parallelism — agents never spawn peer agents.
- Tier concurrency limit 1-3 is hard, not runtime-overridable by agents.
- Escalation ladder haiku → sonnet → opus, no downgrade.
- `--dangerously-skip-permissions` makes sandbox config the critical security surface for autonomous execution.
- PR `--merge` strategy is load-bearing for `--theirs` rebase semantics.
- `pipeline-events.log` is append-only JSONL.
- Orchestrator `rationale` field convention exists but enforcement requires prompt changes — document as-is.

**Scope boundaries (must not be described as current)**:
- Cross-repo work in a single overnight session is **deferred**.
- Migration from file-based state is **deferred**.
- Sandbox socket access, mobile push alerting, metrics tracking are **should-have** — not framed as load-bearing guarantees.

**Known gaps to acknowledge (must not paper over)**:
- `remote/SETUP.md` is referenced but missing.
- Notification/session failures are silent; no log mechanism.
- Orchestrator `rationale` field: convention documented, enforcement not yet in prompts.

**Style constraints**:
- ATX headings; H1 only at top of file.
- Code fences: ```` ```bash `, ```` ```json `, ```` ```python ` (no language for ASCII trees).
- Em-dashes (—), not `--`.
- Inline backticks for paths, filenames, function names, env vars, branch names.
- File paths in prose are project-root-relative; absolute only in code blocks.
- Cross-links: relative paths inside `docs/`; anchors lowercase, hyphenated.
- Breadcrumb `[← Back to ...](source.md)` at line 1 of the new doc.
- Audience header: `**For:** ... **Assumes:** ...` near top.
- Jump-to blockquote nav: `> **Jump to:** ... | ... | ...`.
- Recovery subsections: H3 with **Diagnosis** and **Recovery** bolded run-in heads.

**Progressive-disclosure model (adapted from `claude/reference/claude-skills.md`)**:
- `docs/overnight.md` stays compact: how to run overnight + one paragraph pointing to `docs/overnight-operations.md` for everything else. A human reader landing here via the README or a "how do I use overnight?" link gets the minimum they need. No duplication of mechanics.
- `docs/overnight-operations.md` is the single source of truth for mechanics, debugging, recovery, state files, and internal APIs. A human reader landing here via a stack trace, retro link, or cross-link from another doc finds the complete picture in one file.
- Optional deep-reference content (appendices): used only when the primary doc would exceed readable length; prefer pointers + invariants over enumerations for code-proximate content (`orchestrator_io`, config schema). The trigger for creating an appendix is length-driven (>1000 lines), and the appendix name pattern is `docs/overnight-operations-{topic}.md`.

## Open Decisions

None. All design questions resolved during the Clarify and Specify interviews.
