# Research: Extract /dev epic-map parse into bin/cortex-build-epic-map

## Topic

Extract `/dev` Step 3b's epic→children map construction (parent-field normalization at `skills/dev/SKILL.md:159-167`) into a new global script `bin/cortex-build-epic-map` that consumes `backlog/index.json` and emits a deterministic JSON map. Step 3a (`cortex-generate-backlog-index`) and Step 3c (decision tree → workflow recommendation) remain unchanged. The script must be wired into `skills/dev/SKILL.md` to satisfy SKILL.md-to-bin parity enforcement, shipped via `just build-plugin` to `plugins/cortex-interactive/bin/`, and tested.

Per refine protocol (complex-tier + high-criticality with implementation suggestions in the ticket), this research explores at least one alternative to the ticket's proposal.

## Codebase Analysis

### Step 3b normalization to extract (`skills/dev/SKILL.md:151-166`)

The four-step parent-field normalization is fully specified in narrative form:

1. **Null/missing check**: If `parent:` is absent or its value is `null`, skip — not a child of any epic.
2. **Strip quotes**: If the value is surrounded by quotes (e.g., `"103"`), remove them to get the bare value (`103`).
3. **Skip UUIDs**: If the bare value contains a `-` character (UUID format, e.g., `58f9eb72-...`), skip — UUID-format parent references belong to a deprecated schema era.
4. **Integer comparison**: Parse remaining value as integer and compare to the epic's numeric ID. If they match, append the entry's fields (`id`, `title`, `status`, and `spec` field — non-null means refined) to that epic's child list.

Output contract (line 166): a `epic_id → [children]` map where each child entry contains `id`, `title`, `status`, and a refinement-flag boolean. Step 3c (`SKILL.md:168-260`) consumes this map for grouped rendering, blocked-children counts, status-based variations, and per-epic workflow recommendations.

### bin/cortex-* wrapper convention

Existing scripts (`bin/cortex-generate-backlog-index`, `bin/cortex-update-item`, `bin/cortex-create-backlog-item`, `bin/cortex-count-tokens`) follow a uniform bash-wrapper pattern:

```bash
#!/bin/bash
"$(dirname "$0")/cortex-log-invocation" "$0" "$@" || true
set -euo pipefail

# Branch (a): packaged form
if python3 -c "import cortex_command.backlog.MODULE_NAME" 2>/dev/null; then
    exec python3 -m cortex_command.backlog.MODULE_NAME "$@"
fi

# Branch (b): CORTEX_COMMAND_ROOT points at a checkout
if [ -n "${CORTEX_COMMAND_ROOT:-}" ] && grep -q '^name = "cortex-command"' "$CORTEX_COMMAND_ROOT/pyproject.toml" 2>/dev/null; then
    exec python3 "$CORTEX_COMMAND_ROOT/backlog/MODULE_NAME.py" "$@"
fi

# Branch (c): not found
echo "cortex-command CLI not found — run 'cortex setup' or point CORTEX_COMMAND_ROOT at a cortex-command checkout" >&2
exit 2
```

Python implementations live in `backlog/*.py`, importable as `cortex_command.backlog.*`. They use `Path(__file__).resolve().parent.parent` + `sys.path.insert` to locate the project root, then import from `cortex_command.common`.

### Plugin mirroring

`justfile` `build-plugin` recipe runs `rsync -a --delete --include='cortex-*' --exclude='*' bin/ "plugins/$p/bin/"` for each build-output plugin (`cortex-interactive`, `cortex-overnight-integration`). The `--include='cortex-*'` filter means any new `bin/cortex-*` script is auto-picked up — no recipe change needed.

Drift enforcement is two-layered: `.githooks/pre-commit` (installed via `just setup-githooks`) runs `just build-plugin` on staged source-side paths, then `git diff --exit-code` on each plugin tree. If the working tree differs from staged after rebuild, the commit fails with a "drift" message pointing at the source.

### SKILL.md-to-bin parity linter (`bin/cortex-check-parity`)

Detects script wiring via three signal categories:
- Path-qualified (`bin/cortex-foo`)
- Inline code (`` `cortex-foo` `` or `` `bin/cortex-foo` ``)
- Fenced-code blocks (` ```...``` `)

Scan scope: `skills/**/*.md`, `CLAUDE.md`, `justfile`, `hooks/cortex-*.sh`, `claude/hooks/cortex-*.sh`, `tests/**`, `requirements/**/*.md`, `docs/**/*.md`. Plugin tree directories are NOT scanned (they are mirrors).

Allowlist at `bin/.parity-exceptions.md` uses a 5-column markdown table: `script | category | rationale | lifecycle_id | added_date`. Categories are closed-enum (`maintainer-only-tool`, `library-internal`, `deprecated-pending-removal`); rationale is ≥30 chars and forbids vague literals (`internal`, `misc`, `tbd`, etc.).

The linter has W003 ("orphan") and W005 ("allowlist-superfluous") detection: an allowlisted-but-wired script triggers W005, an unallowlisted-and-unwired script triggers W003. E002 ("drift") fires when a SKILL.md references a non-existent script.

### backlog/index.json shape

`generate_index.py:131` stores `parent` after `_opt()` strip-quotes (`backlog/generate_index.py:64-67`). Real JSON values per active item include: `id` (int), `title` (str), `status` (str), `priority` (str), `type` (str, default "feature"), `parent` (str or null), `spec` (str or null — the spec path; non-null ⇒ refined), `blocked_by` (array), `blocks` (array), `tags`/`areas` (arrays), `uuid` (str), `lifecycle_slug`/`session_id`/`lifecycle_phase`, `schema_version` ("1"). Archive items are excluded by `generate_index.py:91` (`if "archive" in path.parts: continue`).

### claude/common.py and cortex_command/common.py

`cortex_command/common.py` provides `slugify`, `atomic_write`, `normalize_status`, `TERMINAL_STATUSES`. **No existing parent-field normalization or epic-map builder.** Both must be net-new. `claude/common.py` (the Python module — separate file) hosts `detect_lifecycle_phase()` and other helpers; not directly relevant here.

### Test patterns

`tests/test_check_parity.py` and `tests/test_common_utils.py` use pytest with fixture directories under `tests/fixtures/`. Pattern: subprocess-invoke the script with controlled args, capture stdout/exit code, parse JSON, assert against expected output. Fixtures provide minimal repo trees.

### Files to create vs. modify

**Created**:
- `bin/cortex-build-epic-map` — bash wrapper (≈25 lines per existing convention).
- `backlog/build_epic_map.py` — Python implementation (≈80–120 lines).
- `tests/test_build_epic_map.py` — pytest covering the four normalization rules + edge cases + schema-version validation.
- Test fixture(s) under `tests/fixtures/build_epic_map/` (mini index.json variants).

**Modified**:
- `skills/dev/SKILL.md` — Step 3b lines 151–166: replace the inline 4-step normalization narrative with an invocation of `cortex-build-epic-map` and a description of the output it produces; preserve the upstream "Read the Ready section" wording (Step 3b pre-amble, lines 143–149) and the downstream Step 3c logic.

**Auto-mirrored** (no manual edit):
- `plugins/cortex-interactive/bin/cortex-build-epic-map` — copy of top-level via `just build-plugin`.

## Web Research

### Skill-to-script extraction guidance

- Anthropic's [skill-creator SKILL.md](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) explicitly recommends extracting deterministic logic into `scripts/`: "if all 3 test cases resulted in the subagent writing a `create_docx.py`... that's a strong signal the skill should bundle that script. Write it once, put it in `scripts/`, and tell the skill to use it." This applies to parent-field normalization — it's exactly the kind of mechanical work an LLM subtly miscodes per invocation.
- ["AI skills vs. scripts" (mig8447, Mar 2026)](https://blog.mig8447.me/ai/2026/03/06/ai-skills-vs-scripts.html) frames the boundary as "scripts for logic, skills for judgment." MECHANICAL-PARSE work (deterministic, no interpretation) → script. Decision-tree work (Step 3c) → skill prose.
- [Simon Willison (Oct 2025)](https://simonwillison.net/2025/Oct/16/claude-skills/) notes scripts are "validation and efficiency aids, not requirements" — counterweight against over-extraction. For this case, the extraction signal is strong (research C4 explicitly classified MECHANICAL-PARSE).

### CLI design conventions

- argparse is the consensus choice for small JSON-emitting Python scripts ([pythonsnacks](https://www.pythonsnacks.com/p/click-vs-argparse-python), [trickster.dev](https://www.trickster.dev/post/building-python-script-clis-with-argparse-and-click/)). Click justifies its dependency only for production tools with subcommands. cortex-command's existing scripts already use argparse; adding click would be gratuitous.
- Positional argument for input file path is the Unix tradition (cp/mv/jq); hidden defaults are an anti-pattern that hurts testability.
- Exit codes: collapse to 0/1/2 unless callers branch. sysexits.h is BSD-only and not POSIX. [Chris Down](https://chrisdown.name/2013/11/03/exit-code-best-practises.html) load-bearing point: distinct codes only earn their keep when the caller actually branches on them.

### Build-time mirroring

- The dominant pattern is single-source-of-truth + verify-on-commit (canonical edit → regenerate → `git diff --exit-code` → fail with instructions). cortex-command already does this via `just setup-githooks` + `.githooks/pre-commit`.
- Anti-pattern flagged in the wild: hooks that silently re-stage generated files (per [psf/black#1857](https://github.com/psf/black/issues/1857)). Better is fail-with-instructions so the developer reviews the diff. cortex-command's drift hook already follows the recommended pattern.
- Closest direct prior art: [agentsfolder/agents-cli](https://github.com/agentsfolder/agents-cli) — "canonical-projection-with-drift-detection." Same pattern.

### Caveats

No URLs were blocked. No directly relevant prior art for the *exact* triple (Claude Code skill → Python `bin/` → JSON → plugin mirror) was found, but the composed pattern is well-documented.

## Requirements & Constraints

### From `requirements/project.md`

- **L25 (file-based state)**: All state in plain files. The new script consumes JSON + emits JSON; aligned.
- **L27 (SKILL.md-to-bin parity enforcement)**: `bin/cortex-*` must be wired through SKILL.md/requirements/docs/hooks/justfile/tests. Drift is pre-commit-blocking. Allowlist exceptions live at `bin/.parity-exceptions.md`. **Direct constraint on this ticket**: `cortex-build-epic-map` must be referenced from `skills/dev/SKILL.md` Step 3b (inline-code or fenced-code mention). No allowlist entry needed or appropriate.
- **L35 (Context efficiency)**: This quality attribute is about substring-grep output filtering of verbose tool output via `output-filters.conf`. **Not** about extracting deterministic logic from skill flows. (The clarify-critic flagged that this requirements line was misapplied during clarify; the corrected alignment cites only the parity enforcement in L27.)

### From `CLAUDE.md`

- **Repo structure (L18-19)**: `bin/` is canonical source; `cortex-interactive` plugin's `bin/` is the mirror via dual-source enforcement.
- **Distribution (L21-22)**: Cortex ships as `uv tool install -e .` plus plugins via `/plugin install`. New scripts must work in both packaged-Python and `CORTEX_COMMAND_ROOT` modes (per the wrapper convention).
- **Hook executability (L46)**: Wrappers in `bin/` must be `chmod +x`.
- **Setup (L48)**: `just setup-githooks` enables the dual-source drift hook.

### From `bin/.parity-exceptions.md`

- 5-column schema: `script | category | rationale | lifecycle_id | added_date`. Categories are closed-enum. Rationale ≥30 chars; forbidden literals: `internal`, `misc`, `tbd`, `n/a`, `pending`, `temporary`. Lifecycle ID required.
- This script does NOT belong on the allowlist (it is wired via SKILL.md).

### From `docs/observability.md`

- Every `bin/cortex-*` script is required to invoke `cortex-log-invocation` as its first non-shebang line: `"$(dirname "$0")/cortex-log-invocation" "$0" "$@" || true`. The shim is fail-open and writes to `lifecycle/sessions/<id>/bin-invocations.jsonl` when `LIFECYCLE_SESSION_ID` is set; in CI/test environments it logs to `~/.cache/cortex/log-invocation-errors.log` and exits 0.

### From `docs/plugin-development.md`

- `cortex-interactive` is a "build-output plugin" (assembled, not hand-edited). Drift loop verifies via `git diff` that the freshly-built tree matches what's staged.

## Tradeoffs & Alternatives

### Alt A (ticket): freestanding `bin/cortex-build-epic-map`

New bash wrapper + `backlog/build_epic_map.py` Python impl. Auto-detects epics in index.json, emits `{epic_id: {children: [...]}}` JSON for all epics in one call.

- **Pros**: matches existing bin/cortex-* pattern; statically lintable via parity gate; clean MECHANICAL-PARSE vs. judgment split; one subprocess per skill run.
- **Cons**: dual-maintenance with `generate_index.py` (schema drift risk); output shape commits the contract early.
- **Failure modes**: if index schema bumps to `schema_version: "2"` the script may silently misnormalize; "Ready" semantics are not encoded in the script today (see Open Questions).

### Alt B: extend `cortex_command.common` + thin CLI wrapper

Add `build_epic_map()` function to `cortex_command/common.py`; expose via `python3 -m cortex_command.common build-epic-map`. Wrapper is thin or omitted.

- **Pros**: centralized parent-normalization helper; reusable by overnight orchestrator and other Python callers.
- **Cons**: violates DR-2 (narrow `common.py` schema growth); risk of "wired-but-unused at runtime" — agent reaches for `Read + Grep + Python loop` instead of the wrapper (DR-7 failure mode); CLI wrapper still required for SKILL.md static reference, so the proposal saves nothing on the parity surface.
- **Verdict**: the centralization is a real maintenance benefit, but the surface-area growth in `common.py` and the runtime-adoption risk outweigh it for this ticket. **Reject for now**; revisit if/when a second consumer (e.g., overnight) needs the same logic.

### Alt C: per-epic invocation, agent loops

Script takes `--epic-id N` and returns one epic's children. Agent iterates over Ready epic IDs.

- **Pros**: narrowest schema (DR-2); easier per-epic unit test.
- **Cons**: 5× subprocess startup cost (≈100–200ms each) for a typical Ready set; agent must implement aggregation logic (more error surface); SKILL.md prose grows to explain the loop pattern.
- **Verdict**: **reject**. The latency multiplier and agent-side aggregation are real downsides for a Warm-heat path; DR-2 narrow-schema benefit is too small to justify them.

### Alt D: bake into `cortex-generate-backlog-index`, emit `epics.json` sidecar

`generate_index.py` emits a second output file alongside `index.json`. Agent reads `epics.json` directly; no new script.

- **Pros**: zero new abstractions; data computed in same pass as index generation; lowest latency.
- **Cons**: tightens coupling between two responsibilities (index generation + epic-map construction); two output files create partial-failure surface (one writes, the other fails); `generate_index.py` becomes harder to evolve; loses the single-purpose script pattern that the parity linter and DR-5 are built around.
- **Verdict**: **reject**. The DR-2 narrow-script discipline is more valuable than the latency savings. Index generation is a separate concern from epic-map construction.

### Recommended: Alt A

The ticket's suggestion holds up under alternative pressure. Decisive factors:

1. **Existing pattern fit** — `cortex-generate-backlog-index` → `backlog/generate_index.py`, `cortex-update-item` → `backlog/update_item.py`. Alt A mirrors this exactly.
2. **Lintability** — DR-5 parity linter detects a static reference in SKILL.md. Alt B's thin-wrapper or direct-module-call patterns are harder to lint reliably.
3. **Single-purpose scripts** — DR-2 prefers narrow scripts, and Alt A fits cleanly. Alt D explicitly compresses two responsibilities into one script.
4. **MECHANICAL-PARSE classification** — research C4 classified the work as MECHANICAL-PARSE with judgment downstream. Alt A keeps that boundary clean; Alt B and Alt D blur it.

### Recommended answers to ticket open questions

- **Output shape per child vs. per epic**: per-child fields `{id, title, status, refined}`. Step 3c reads per-child status/refinement signals; epic-level aggregation would be lossy. Confirmed against `skills/dev/SKILL.md:168-260`. (See Open Question 1 for whether to additionally include `priority`/`blocked_by`/`type` for forward compatibility.)
- **Epic detection vs. epic IDs as input**: provisionally **script auto-detects** via `type:epic` scan (simpler agent calling, single subprocess), but **see Open Question 2** — the "Ready" filter is currently agent-determined, not encoded in any data file. The script may need to accept a `--epic-ids` flag to let the caller filter.
- **Single-call-all-epics vs. per-epic**: single call. Avoids subprocess multiplication; aligns with Step 3b's "build the full map before rendering" prose.
- **CLI args**: positional `[index_path]` defaulting to `backlog/index.json` resolved relative to repo root (matching the implicit assumption in SKILL.md). No flags on day one; reserve `--epic-ids` and `--schema-version` flags for future extension.
- **No parity exception**: the script is wired via SKILL.md Step 3b; do NOT add an entry to `bin/.parity-exceptions.md`.

## Adversarial Review

The adversarial pass surfaced nine angles. The high-impact ones are condensed here; lower-impact items are flagged as defensive improvements.

### High impact

1. **"Ready" semantics are not encoded in any data file.** SKILL.md Step 3b refers to "the Ready section," but `generate_index.py:154-227` only emits `## Refined`, `## Backlog`, `## In-Progress` (and optional `## Warnings`) sections. There is no literal "Ready" section in `index.md`, and `index.json` carries no "ready" flag. The current agent-side narrative reading is "Refined ∪ Backlog (excluding items with unresolved blockers)." If the new script auto-detects ALL `type:epic` entries in `index.json`, it will include In-Progress epics, Backlog epics still blocked, etc. — broader than what Step 3c expects. **This is a contract gap to resolve in spec.** (Carried as Open Question 2.)

2. **Step 3c may need fields beyond `{id, title, status, refined}`.** Reading lines 168–260: the decision tree branches on child `status` (covered), `spec` non-null (covered as `refined`), and `blocked_by` count for the "Note: N children are blocked" prepend (NOT covered by the proposed shape). The agent could re-derive `blocked_by` from index.json, but that defeats the script's abstraction. **Decision needed in spec**: include `blocked_by` (and possibly `priority`, `type`) in the per-child shape from day one, or document that the agent fetches them separately.

3. **Schema versioning resilience.** `index.json` items carry `schema_version` (currently "1"). If the schema bumps (e.g., parent-field rename), `build_epic_map.py` will silently misnormalize. Defensive validation: read the first item's `schema_version`, error out (exit 2) on anything other than the supported version. Frozen at v1 today; document in the script's docstring. (Carried as Open Question 3.)

### Medium impact (mitigations during implementation)

4. **`cortex-log-invocation` shim in tests.** The shim is fail-open, so tests will not crash if `LIFECYCLE_SESSION_ID` is unset. But test assertions about logging are flaky in CI. Mitigation: tests focus on the JSON output (script stdout), not on invocation-log side effects. If logging is asserted, use a `tmp_path`-based fixture that sets `LIFECYCLE_SESSION_ID` and creates the session dir.

5. **Parent-field normalization frozen at schema v1.** Document explicitly in the script's docstring and as a comment in `skills/dev/SKILL.md` Step 3b. Future schema changes require coordinated updates to both `generate_index.py` and `build_epic_map.py`.

### Low impact (acknowledged, no action required)

6. **`--no-verify` bypass of pre-commit drift hook.** Known cortex-wide concern (research C4's epic file flagged this in DR-5). Out of scope for this ticket; mitigated by repo culture and the secondary safeguard of CI checks if added later.

7. **Allowlist confusion / W003 orphan detection.** Known parity-linter behavior; do NOT allowlist this script. If a future refactor accidentally drops the SKILL.md reference, W003 will catch it on the next commit.

8. **Manual `index.json` edits.** Out of scope — `generate_index.py` is canonical; users editing the generated index by hand is a self-foot-gun, not a script-side concern.

9. **Concurrency.** Multiple simultaneous /dev invocations both calling the script: read-only stdout, no shared state. Safe.

## Open Questions

1. **Per-child shape — minimal vs. forward-compatible.** Should the script's per-child object be the minimal `{id, title, status, refined}` (matching today's Step 3b output contract), or pre-emptively wide `{id, title, status, refined, priority, blocked_by, type}` to avoid contract churn when Step 3c's blocked-children counting needs `blocked_by`?
   - Deferred: will be resolved in Spec by asking the user, with a recommendation toward the minimal shape + a documented extension path (CLI flag like `--include=blocked_by,priority`).

2. **"Ready" filter inside the script vs. caller-supplied.** Two viable contracts: (a) script auto-detects all `type:epic` entries in index.json (simple, but emits more than Step 3c needs); (b) script accepts a `--epic-ids ID,ID,...` flag and processes only those IDs (caller filters to "Ready"). Recommended: ship (a) for simplicity, with `--epic-ids` reserved as a future filter flag if needed. Step 3c already filters at render time (epics not in Ready set are not displayed), so (a) is functionally correct, just slightly over-eager.
   - Deferred: will be resolved in Spec by asking the user.

3. **Schema-version validation strictness.** Hard error (exit 2) on any `schema_version ≠ "1"`, or warn and proceed? Hard-error is safer; warn-and-proceed is more forgiving for partial-migration repos.
   - Deferred: will be resolved in Spec by asking the user. Recommendation: hard error; the script is small and easy to update when schema bumps.

4. **Test invocation entry point.** `pytest tests/test_build_epic_map.py` invokes the script via subprocess (`bin/cortex-build-epic-map fixture/index.json`), or imports `backlog.build_epic_map.main()` directly? Existing tests use both styles depending on coverage goal.
   - Deferred: will be resolved in Spec by asking the user. Recommendation: subprocess for end-to-end; one or two unit tests on the normalize function for tight feedback.

5. **Output destination — stdout only or also a sidecar file.** Stdout-only is simpler and matches DR-2 narrow-schema; a sidecar (`backlog/.epic-children-map.json`) would let Step 3c read once without re-running. Recommendation: stdout only — Step 3c invokes the script once and parses the JSON; no sidecar needed.
   - Deferred: will be resolved in Spec by asking the user.
