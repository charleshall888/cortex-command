# Research: Refresh install/update docs + close MCP-only auto-update gaps

Scope (from Clarify): bundle Tier 1 docs (Quickstart PATH verification, merged README "Recommended settings" entry from items 2+10, consolidated `docs/setup.md#upgrade--maintenance` with trim of scattered mentions, `CORTEX_ALLOW_INSTALL_DURING_RUN=1` callout), Tier 2 code (fail-fast `command -v cortex-daytime-pipeline` preflight in `skills/lifecycle/references/implement.md §1a` Step 3), Tier 3 hygiene (handle `feature_wontfix` lifecycles as terminal so they drop off the SessionStart "incomplete lifecycles" list). Items 5 and 6 are out of scope — file as separate backlog items.

## Codebase Analysis

### Tier 1 — Docs surfaces

**`README.md`**: Quickstart at lines 16–34. Line 24 is a code-fence-embedded comment: `# Recommended to turn on Auto-Update Marketplace Plugins (this will keep CLI auto updated as well)`. No "Recommended settings" section exists in README today (grep-verified — only line 24 contains "Recommended").

**`install.sh`**:
- Line 42: existing `command -v` precedent — `command -v uv >/dev/null 2>&1 || install_uv` (graceful-install fallback).
- Line 45: `uv tool install git+"${resolved_url}"@"${tag}" --force`.
- Line 48: trailing PATH-hint log — *"if 'cortex' is not on your PATH, run 'uv tool update-shell' and reload your shell."* This is **the only signal** a fresh-install user with bare PATH receives in real time. Removing it would push the failure surface to the user's first `cortex --print-root` call.

**`docs/setup.md`** (entire file structure, grep-verified):
- H2 `Install` (lines 20–47) — already references `uv tool update-shell` at line 30: *"run `uv tool update-shell` once if it does not [land on PATH]"*.
- H2 `Verify install` (lines 167–184) — already uses `cortex --print-root --format json` as the post-install smoke test.
- H2 `Upgrade & maintenance` (lines 188–220) — already covers MCP auto-update mechanics, plugin reinstall, and the `uv tool uninstall uv` foot-gun (lines 197–203).
- H2s for `Authentication`, `Permissions`, `macOS Notifications`, `Dependencies` follow.
- **No "Recommended settings" H2 exists** (grep-verified — zero matches for "Recommended" in setup.md). The Tradeoffs agent's claim that this section already exists was incorrect.
- **No `CORTEX_ALLOW_INSTALL_DURING_RUN` reference anywhere in setup.md** today.

**Scattered upgrade-flow mentions (grep `uv tool install`, `--reinstall` across repo)**:
- `README.md:24` — marketplace auto-update comment.
- `install.sh:42,45` — install bootstrap + reinstall.
- `plugins/cortex-overnight/server.py:~10 occurrences` (lines 187, 211, 240, 295, 459, 491, 553–559, 574, 1009–1618+) — error messages and comments referencing `uv tool install --reinstall`.
- `CHANGELOG.md:19–29` — v0.2.0 unreleased migration block with `--reinstall` requirement, in-flight install guard, `CORTEX_ALLOW_INSTALL_DURING_RUN=1` reference.
- `cortex_command/cli.py::_dispatch_upgrade()` — advisory wrapper that prints `/plugin update` and `uv tool install --reinstall` instructions (exits 0 without running install).

**`cortex/requirements/pipeline.md:154`** — canonical `CORTEX_ALLOW_INSTALL_DURING_RUN=1` documentation. Contract: *"Bypassable inline via `CORTEX_ALLOW_INSTALL_DURING_RUN=1` (do NOT export)."* Carve-outs: pytest, runner-spawned children (`CORTEX_RUNNER_CHILD=1`), dashboard, cancel-force. Enforced by `cortex_command.install_guard.check_in_flight_install` (opt-in by callers, not invoked at package import).

### Tier 2 — `skills/lifecycle/references/implement.md` §1a

**Dispatch line** (lines 88–91, §1a Step 3):
```
DAYTIME_DISPATCH_ID={uuid} cortex-daytime-pipeline --feature {slug} > cortex/lifecycle/{feature}/daytime.log 2>&1
```

**Surrounding control-flow context**:
- Lines 12–51: §1 existing pre-flight (importlib probe for `cortex_command` package — pattern: exit 0 → all options; exit 1 → silent-hide; other → fail-open with diagnostic).
- Lines 62–67: double-dispatch guard (separate Bash calls — `cat .../daytime.pid` → `kill -0 $pid` — no compound commands per skill prose convention).
- Lines 69–74: overnight concurrent guard (4 sequential Bash calls).
- Lines 76–100: §1a launch sequence — §1a Step 3 dispatch is where a `command -v` preflight would insert.

**Existing `command -v` precedent in skill prose**: `skills/lifecycle/references/complete.md:39,42` uses `command -v cortex-*` as **warn-and-continue** (graceful degradation, never `exit 127`). The Tier 2 preflight differs in posture: fail-fast abort vs graceful degrade.

**`bin/cortex-check-parity:431`** already tracks the `command -v cortex-*` pattern — new skill-prose `command -v cortex-daytime-pipeline` will be parity-recognized without an exception.

### Tier 3 — `cortex_command/common.py` `detect-phase` and `feature_wontfix`

**`_cli_detect_phase()`** at `cortex_command/common.py:746–752`; `_run()` dispatcher at 763–786; **`detect_lifecycle_phase()`** core at 341–387; cached inner `_detect_lifecycle_phase_inner` at 178–338.

**Terminal-condition checks**:
- `common.py:248–255` — `feature_complete` check via **substring scan**: `'"feature_complete"' in events_content`. Quoted-literal substring, not JSON parse.
- `common.py:256–280` — review.md verdict regex routes APPROVED→complete, CHANGES_REQUESTED→implement-rework, REJECTED→escalated.
- `common.py:282–305` — artifact presence (plan.md `[x]` tally / spec.md / research.md) + approval gates.
- `common.py:216–235` — **separate JSON-parsing loop** (`for line in events_content.splitlines(): try: json.loads(line)`) used for `phase_transition` event detection. This is the pre-existing structured-parse path.

**Phase-detector mirrors** (R12 parity contract):
- `hooks/cortex-scan-lifecycle.sh:252–264` — delegates to Python (`python3 -m cortex_command.common detect-phase <dir>`); **does not need code change** for new terminal events.
- `claude/statusline.sh:403` — **separate bash ladder** by R12b structural exception (statusline.sh:376–389). Currently: `if grep -q '"feature_complete"' "$_lc_fdir/events.log" 2>/dev/null; then _lc_phase="complete"`. **MUST be updated to mirror any new Python terminal check** or `tests/test_lifecycle_phase_parity.py::test_statusline_ladder_matches_canonical` (lines 300–347) fails.

**`feature_wontfix` producer — phantom event**:
- Grep across `skills/`, `hooks/`, `bin/`, `cortex_command/`, `plugins/` for `feature_wontfix` returns ZERO programmatic emitters.
- Single occurrence: `cortex/lifecycle/lazy-apply-cortex-cli-auto-update-via-sessionstart-probe-in-process-apply-on-invoke/events.log:12` — **one hand-edited event** from 2026-04-25.
- Not registered in `bin/.events-registry.md`.
- `feature_complete` IS registered (gate-enforced; producers: `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/complete.md`, `skills/morning-review/references/walkthrough.md`, `cortex_command/pipeline/review_dispatch.py`; consumers: `cortex_command/pipeline/metrics.py:212`, `cortex_command/common.py:198`, `cortex_command/overnight/report.py:1691`).

**Archive convention** (alternative durable fix):
- `hooks/cortex-scan-lifecycle.sh:227` — `[[ "$feature" == "archive" ]] && continue` (skips `cortex/lifecycle/archive/` from SessionStart enumeration).
- The #146 lifecycle is already at `cortex/lifecycle/archive/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/` — this pattern is in use.
- If #145 had been moved to archive at wontfix time, the SessionStart-noise symptom would not exist today.

### Items 5/6 filing — parent-field semantics

- `bin/cortex-load-parent-epic` `normalize_parent` rejects values containing `-` (line 73): `if "-" in value: return None`. **UUIDs always contain hyphens** — `parent: <UUID>` parses to `None`.
- Ticket 210 is `type: chore` (line 14 of `cortex/backlog/210-…md`). All existing `parent:` references point to `type: epic` items (verified at parents 003, 009, 014, 018 — all epic).
- Alternative field: `discovery_source: 210-refresh-install-update-docs-close-mcp-only-auto-update-gaps.md` is the documented sibling pointer that does not require epic-typing.

## Web Research

### `uv tool install` upgrade idioms

`uv tool upgrade <name>` exists (docs.astral.sh/uv/guides/tools/) but its behavior with git-source pins is unreliable — community workaround for tools installed via `git+<url>@<tag>` is to re-run `uv tool install git+<url>@<new-tag>` (replacing the pin) rather than relying on `uv tool upgrade`. Astral issues #8067, #14954, #18120 document related failure modes. Quote: *"Tool upgrades will respect the version constraints provided when installing the tool."* For cortex-command, the canonical upgrade path remains `uv tool install --reinstall git+...@<tag>`.

### `uv tool update-shell` semantics

Per `docs.astral.sh/uv/concepts/tools/`: *"The `uv tool update-shell` command can be used to add the executable directory to the `PATH` in common shell configuration files."* uv itself emits a warning when `~/.local/bin` is missing from PATH; canonical guidance is *"run it if you see the warning,"* not unconditionally. The command modifies `~/.bashrc` / `~/.zshrc` / `~/.bash_profile` — running it unconditionally is a dotfile mutation. Safe-to-recommend posture is conditional remediation, not always-emit step.

### PATH verification idiom

Running the tool with `--version` (or in cortex's case `--print-root --format json`) is the user-facing verification idiom. `command -v` is the scripted check. `which` is discouraged (not POSIX, distro variance). Cortex-command already has the verification pattern at `docs/setup.md:167–184` ("Verify install" section).

### `command -v` preflight pattern (gold standard: Homebrew installer)

```bash
if ! command -v curl >/dev/null
then
  abort "You must install cURL before installing Homebrew. See: <url>"
fi
```

Homebrew writes the actionable message to stderr via `abort` and exits with **code 1** (not 127). Exit 127 is conventional for "command not found" per Red Hat docs (the shell itself returns 127), but Homebrew uses 1 to keep "missing dep" undistinguishable from any fatal init failure. Either is defensible; **Claude Code's Bash tool reports both as "non-zero exit" verbatim** — no downstream consumer distinguishes 1 from 127.

Anti-pattern: `which X` (not POSIX, behavior varies between distros, ignores shell builtins).

### Claude Code marketplace auto-update vs cortex-command's claim

Anthropic's docs at `code.claude.com/docs/en/discover-plugins`: *"Claude Code can automatically update marketplaces and their installed plugins **at startup**."* This describes the **plugin-file refresh layer** — refreshing the marketplace file and updating installed plugins to their latest versions. This is a different layer than cortex-command's CLI auto-update.

The two layers chain: (1) Marketplace auto-update at startup refreshes the plugin file and bumps `CLI_PIN`; (2) the next MCP tool call's R13 schema-floor check (in `plugins/cortex-overnight/server.py:_ensure_cortex_installed()`) compares plugin-pin vs installed-CLI version and orchestrates `uv tool install --reinstall` if they diverge.

The cortex-command "MCP-tool-call-gated by design" claim is grounded in #146's spec (`cortex/lifecycle/archive/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/spec.md:7,32`) — specifically R8: the check fires *"before delegating a tool call."* This is the CLI auto-update layer, not the plugin-file refresh layer. **The claim is correct but needs disambiguation in the docs**: marketplace auto-update happens at Claude Code startup; the CLI's `uv tool install --reinstall` is triggered on the next MCP tool call, not at startup.

### Terminal-state additions to event-sourced FSMs

Consensus guidance (AWS prescriptive, Martin Fowler, Azure architecture): (a) version events not states; (b) replay must be forward-compatible; (c) don't migrate old logs; (d) keep old terminal-detection branches intact and add new branches additively. Anti-pattern: rewriting historical JSONL. For cortex-command's detector, this means: when adding a new terminal event, leave existing branches intact, add new branch additively, and cover with fixture-based regression tests for old-only and new-event logs.

## Requirements & Constraints

### Distribution model
- `cortex/requirements/project.md:5–8` and `CLAUDE.md:1–22`: cortex-command ships as a non-editable wheel installed via `uv tool install git+<url>@<tag>` plus plugins via `/plugin install`. `cortex init` additively registers the repo's `cortex/` umbrella to sandbox `allowWrite`.

### MCP auto-update architecture
- `cortex/requirements/observability.md:140–147`: **`plugins/cortex-overnight/server.py:_ensure_cortex_installed()` is the ONLY install-mutation entry point under wheel install** — runs before each MCP tool handler delegates to a `cortex` subprocess. On cortex-absent it shells out to `uv tool install --reinstall git+<url>@<tag>` under a flock at `${XDG_STATE_HOME}/cortex-command/install.lock`.
- `cortex_command.cli._dispatch_upgrade()`: post-141 **advisory-only** (prints `/plugin update` + `uv tool install --reinstall` instructions, exits 0 without running install).
- `_orchestrate_upgrade` and `_orchestrate_schema_floor_upgrade` (R10/R11/R12): dormant under wheel install (short-circuit when `.git/` absent).

### Pre-install in-flight guard
- `cortex/requirements/pipeline.md:154`: `cortex` aborts when an active overnight session is detected. Bypassable inline via `CORTEX_ALLOW_INSTALL_DURING_RUN=1` — explicit "do NOT export" contract. Carve-outs: pytest, `CORTEX_RUNNER_CHILD=1`, dashboard, cancel-force. Enforced by `cortex_command.install_guard.check_in_flight_install` (opt-in by callers).

### Phase-detection contract
- `cortex_command/common.py:341–369`: artifact-presence state machine. Order: (1) `feature_complete` in events.log → complete; (2) review.md verdict → complete/implement-rework/escalated; (3) plan.md tasks all `[x]` → review, else implement; (4) spec.md → plan; (5) research.md → specify; (6) default → research. No explicit terminal event beyond `feature_complete` today.
- `bin/.events-registry.md:11–12`: `feature_complete` and `phase_transition` are gate-enforced with documented producer/consumer chains.
- `bin/.events-registry.md:22`: `lifecycle_cancelled` precedent — *"(no live consumer; halt-state marker for human inspection)"*. Documented producer (specify.md / plan.md on Cancel), no live consumer.

### Skill / phase authoring guidelines
- `CLAUDE.md:56–62`: prefer structural separation over prose-only enforcement for sequential gates. Kept user pauses inventory in `skills/lifecycle/SKILL.md`; parity test `tests/test_lifecycle_kept_pauses_parity.py` enforces sync.
- `CLAUDE.md:68–74` (Design principle: prescribe What and Why, not How): capable models determine method given clear decision criteria; spelling out procedure constrains agent judgment.

### MUST-escalation policy
- `CLAUDE.md:76–85`: default to soft positive-routing phrasing for new authoring. Adding new MUST/REQUIRED escalation requires effort=high/xhigh demonstrably-fail evidence + events.log F-row link or transcript URL.

### Solution Horizon
- `CLAUDE.md:64–67` and `project.md:21–22`: durable version preferred when redo is foreseeable (follow-up planned, patch applies in multiple known places, sidesteps known constraint). Simpler-fix correct otherwise. **A scoped phase of a multi-phase lifecycle is not a stop-gap.**

### Docs ownership precedent
- `CLAUDE.md:50`: *"Overnight docs source of truth: `docs/overnight-operations.md` owns the round loop and orchestrator behavior… update the owning doc and link from the others rather than duplicating content."* Directly supports hub-and-spoke consolidation pattern.

### Events registry mechanics
- `bin/cortex-check-events-registry` scans `skills/**/*.md` and `cortex_command/overnight/prompts/*.md` for `"event": "<name>"` literals (regex `EVENT_NAME_RE = re.compile(r'"event"\s*:\s*"([a-z_][a-z0-9_]*)"')`). Python source is out-of-scan (manual catalog). The gate fires only when literal appears in scanned scopes.
- Registry header: *"Adding an entry is an architectural commitment: each row promises a documented consumer."*

### Parent-field semantics
- `bin/cortex-load-parent-epic:61–83` and `cortex_command/backlog/build_epic_map.py:55`: `normalize_parent` returns `None` for any value containing `-`. UUIDs always contain hyphens → UUIDs are rejected. `parent:` is reserved for integer IDs that resolve to `type: epic` files.

## Tradeoffs & Alternatives

Recommendations per deliverable (refined under adversarial review — see ## Open Questions for items still requiring user resolution):

### A — Docs consolidation strategy

**Adopt: Hub-and-spoke with 1-sentence pointers retained.** Setup.md owns the canonical `Upgrade & maintenance` mechanism narrative (the H2 already exists at lines 188–220 — extend it, don't replace it). README and CHANGELOG keep 1-sentence cross-references; **`install.sh:48` PATH-hint log line stays intact** (it is the only real-time PATH signal a fresh-install user receives; trimming creates the failure surface that C3 was designed to catch *after* the failure). This matches the `CLAUDE.md:50` overnight-docs convention.

### B — README "Recommended settings" entry (items 2+10 merged)

**Adopt: A single dedicated section in setup.md (canonical), with a 1-line cross-reference in README's Quickstart.** Combine item 2's mechanism-accurate copy and item 10's tightened phrase ("auto-updates the CLI on next MCP tool invocation") into one bullet that explains the two-layer chain (marketplace refresh at startup → next MCP tool call triggers `uv tool install --reinstall`). Disambiguating language addresses the apparent contradiction with Anthropic's "auto-update at startup" docs.

A new "Recommended settings" H2 in either README or setup.md is **net-new structure** (not mirroring — neither file has it today). Pick one canonical location (recommend setup.md, under `Upgrade & maintenance`) and link from the other.

### C — Quickstart PATH step

**Adopt: Verification-snippet pattern (C3).** After install in the Quickstart, run `cortex --print-root --format json` (already canonical at `docs/setup.md:167`). If it fails, run `uv tool update-shell` and reload your shell. Phrase conditionally — `update-shell` modifies dotfiles and should not be invoked unconditionally per Anthropic-pattern guidance.

### D — `implement.md §1a` preflight check

**Adopt: Inline `command -v cortex-daytime-pipeline` guard with positive-routing phrasing and exit 1 (Homebrew style, not 127).** The check sits at the top of §1a Step 3, immediately before the dispatch line. The error message points at `uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@v0.1.0`. Avoid `exit 127` — Claude Code's Bash tool does not distinguish 127 from 1, and exit 1 matches Homebrew's gold-standard pattern. Avoid `MUST/REQUIRED` framing per CLAUDE.md:76–85 unless an effort=high failure case is documented (none exists).

Note: `complete.md:39,42` `command -v` precedent is warn-and-continue, not fail-fast. The Tier 2 deliverable adds a **new posture** (fail-fast). Justified by the dispatch-readiness criticality — if the console-script is missing, the background subprocess launch will silently fail to `daytime.log`, and the user has no signal to diagnose. The preflight surfaces the failure synchronously with an actionable pointer.

### E — Tier 3 `feature_wontfix` handling — re-scoped under adversarial review

The original Clarify decision was "Patch detect-phase only" (option a from the umbrella ticket). Adversarial review surfaced that this premise is incomplete:

- **`feature_wontfix` has zero programmatic emitters today.** The only occurrence in the entire repo is one hand-edited event row in `cortex/lifecycle/lazy-apply-cortex-cli-auto-update-via-sessionstart-probe-in-process-apply-on-invoke/events.log:12` (2026-04-25). No skill, hook, or bin script emits this event today.
- **Patching the consumer (`detect_lifecycle_phase`) without naming a producer creates a registry anomaly.** `bin/.events-registry.md` documents producer/consumer chains as architectural commitments; a row with `producers: (none — hand-edited)` has no precedent.
- **The `lifecycle_cancelled` precedent (`bin/.events-registry.md:22`) is the inverse**: documented producer (specify.md/plan.md on Cancel) + no live consumer. There is no `feature_wontfix`-shaped precedent (consumer + no documented producer).
- **The #146 lifecycle is already at `cortex/lifecycle/archive/decouple-…`** — the archive convention already excludes wontfix'd-then-archived lifecycles from SessionStart enumeration (`hooks/cortex-scan-lifecycle.sh:227`). If #145 had been moved to archive at wontfix time, the symptom would not exist.
- **The statusline bash mirror at `claude/statusline.sh:403` is enforced by `tests/test_lifecycle_phase_parity.py::test_statusline_ladder_matches_canonical` (lines 300–347).** Patching Python without patching statusline + adding a fixture creates a test-red interim state.

This shifts the Tier 3 deliverable from a 1-line patch to a meaningful design choice. See ## Open Questions Q-O1.

### F — Filing items 5 and 6

Items 5 and 6 should be filed via `cortex-backlog add` at lifecycle-start, but **NOT** with `parent: <ticket-210-UUID>`:

1. `normalize_parent` rejects values containing hyphens — UUIDs always contain hyphens.
2. Ticket 210 is `type: chore`, not `type: epic`. All existing `parent:` references in the repo point to `type: epic` items.

**Alternative**: use `discovery_source: 210-refresh-install-update-docs-close-mcp-only-auto-update-gaps.md` (the sibling-pointer field) or omit any parent association and let the cross-reference live in the body. Decide at spec time.

**Pre-file check**: grep for existing tickets covering R8 / `_maybe_check_upstream` and `CLI_PIN` drift before creating duplicates.

## Adversarial Review

Surviving challenges that informed the recommendations above:

- **MCP-tool-call-gated language is correct** — Web agent's apparent contradiction conflated two layers. Marketplace auto-update (plugin file refresh) happens at Claude Code startup; CLI auto-update (`uv tool install --reinstall`) is triggered by the next MCP tool call via R8/R13 in `_ensure_cortex_installed()`. Cite #146 spec lineage when documenting.
- **Phantom `feature_wontfix` event** — Tier 3 premise needs re-scoping (Q-O1).
- **`install.sh:48` trim risk** — keep the PATH hint; only real-time signal for bare-PATH users.
- **`exit 127` vs `exit 1`** — Claude Code's Bash tool doesn't distinguish. Use 1 (Homebrew style).
- **Substring scan vs JSON-parsing loop** — preferred to extend `common.py:216–235`'s existing JSON loop rather than add a second substring scan at line 249. Reduces parallel-detection-mechanism debt.
- **`parent: <UUID>` cannot work** for items 5/6 — use `discovery_source:` or omit.
- **`CORTEX_ALLOW_INSTALL_DURING_RUN` docs callout** — must restate the "inline-only; do NOT export" contract from `pipeline.md:154` verbatim and show only the inline-prefix form. Do not show an `export` form.
- **`uv tool update-shell` should be conditional remediation**, not an unconditional Quickstart step (dotfile mutation).
- **README "Recommended settings" is net-new structure**, not a mirror of an existing setup.md section (verified — does not exist in setup.md). Decide canonical location, cross-reference from the other.
- **Tier 1 time estimate is optimistic** (~45 min in umbrella; realistic ~90 min including the new section creation, install.sh consideration, contract-restate, and `uv tool upgrade` vs `--reinstall` accuracy check).

## Open Questions

These items surfaced in research. All blocking items resolved at the Research → Specify gate (user + critical-judgment); resolutions captured inline below for Spec consumption.

**Q-O1: Tier 3 deliverable shape (re-scoped).**
`feature_wontfix` has no programmatic producer today (single hand-edited event in #145's events.log). Three durable options:

- **(O1-a)** Wire a producer: add a `/wontfix` skill or `cortex-wontfix-feature` bin script that emits the `feature_wontfix` event and writes a backlog status update, then patch `detect_lifecycle_phase` to recognize it AND update `claude/statusline.sh:403` AND add a fixture at `tests/fixtures/lifecycle_phase_parity/events-feature-wontfix/` AND register the event in `bin/.events-registry.md`. Roughly 4–6 files touched + 1 new bin/skill. The 1-line-patch framing in the umbrella ticket is misleading; the durable version is meaningful work.
- **(O1-b)** Amend wontfix workflow to move directories to `cortex/lifecycle/archive/` instead of emitting an event. Matches #146's pattern (archived under `cortex/lifecycle/archive/decouple-…`). Requires defining/documenting the wontfix workflow (does a skill prose for it exist today?) and ensuring the SessionStart enumeration's existing `archive/` skip at `hooks/cortex-scan-lifecycle.sh:227` handles the case. Backfill #145 manually: `git mv cortex/lifecycle/lazy-apply-…/  cortex/lifecycle/archive/lazy-apply-…/`. Simpler durable fix; no new event, no parity-test churn.
- **(O1-c)** Both: amend the workflow (O1-b) AND patch detect-phase + statusline + fixture (O1-a-minus-producer-wiring) as belt-and-suspenders. Slightly more work; covers the case where a wontfix'd lifecycle has not yet been moved to archive.
- **(O1-d)** Drop Tier 3 from this lifecycle and file as a separate backlog item with proper scope (the umbrella ticket already flagged Tier 3 hygiene as "small but reduces SessionStart noise meaningfully" — adversarial review showed it's not small).

**Q-O2: Items 5 and 6 parent-association at filing time.**
- **(O2-a)** Use `discovery_source: 210-refresh-install-update-docs-close-mcp-only-auto-update-gaps.md` (sibling-pointer field; no epic-typing required).
- **(O2-b)** Omit any parent/discovery_source association; let the body text cross-reference ticket 210.
- **(O2-c)** Promote ticket 210 to `type: epic` and use `parent: 210` (integer). Most expressive but a metadata change that affects discovery/epic-map rendering.

**Q-O3: "Recommended settings" canonical location.**
- **(O3-a)** Create a "Recommended settings" H2 in `docs/setup.md` under or adjacent to `Upgrade & maintenance`; README's Quickstart links to it.
- **(O3-b)** Create a "Recommended settings" subsection inside README's Quickstart; setup.md links to it.
- **(O3-c)** Put both items (auto-update + PATH) in `Upgrade & maintenance` itself (no new section); README has a 1-line teaser.

**Q-O4: Detect-phase patch implementation (conditional on Q-O1 selecting `a` or `c`).**
- **(O4-a)** Add a literal-substring scan branch at `common.py:249` next to the `feature_complete` check (matches existing pattern, two parallel detection mechanisms).
- **(O4-b)** Extend the existing JSON-parsing loop at `common.py:216–235` to set a terminal flag on `feature_wontfix` event (one detection mechanism, slightly more code but durable).

**Q-O5: Pre-file duplicate check for items 5/6.**
Before filing items 5 (R8 cwd-vs-installed-wheel divergence) and 6 (CLI_PIN drift lint), grep for existing tickets covering `_maybe_check_upstream`, `CLI_PIN`, and any related #146 follow-ups to avoid duplicates. Confirm at spec time after the grep is run, or include the grep result inline in the spec.

---

## Resolutions at Research → Specify gate

- **Q-O1 → O1-c (both)**: Amend wontfix workflow to `git mv` the lifecycle directory into `cortex/lifecycle/archive/` (matching #146's pattern); backfill #145 with `git mv`. Additionally patch `detect_lifecycle_phase` to recognize `feature_wontfix` events as terminal (returning `phase=complete`), mirror in `claude/statusline.sh:403`, add parity fixture, register in `bin/.events-registry.md`. Defense-in-depth: workflow prevents new occurrences; detector handles transient wontfix'd-but-not-yet-archived state.
- **Q-O2 → discovery_source pointer**: Items 5 and 6 are filed via `cortex-backlog add` with `discovery_source: 210-refresh-install-update-docs-close-mcp-only-auto-update-gaps.md`. No `parent:` field (incompatible with UUID hyphens + chore typing).
- **Q-O3 → No new H2; reuse existing canonical homes**: Auto-update mechanism content extends `docs/setup.md#upgrade--maintenance` (existing H2). PATH verification content extends `docs/setup.md#verify-install` (existing H2). README replaces line 24's code-fence comment with a single "Recommended:" bullet in normal markdown that cross-references setup.md. No new "Recommended settings" H2 in either README or setup.md.
- **Q-O4 → Extend JSON-parsing loop**: The detect-phase patch extends the existing `for line in events_content.splitlines(): json.loads(line)` loop at `cortex_command/common.py:216–235` to set a terminal flag on `feature_wontfix` events. Single detection mechanism; reduces parallel-scan debt.
- **Q-O5 → Defer to Spec**: Spec phase will run the grep for `_maybe_check_upstream` / `CLI_PIN` follow-ups and include the result inline before items 5 and 6 are filed.
