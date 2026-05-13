# Review: refresh-install-update-docs-close-mcp (cycle 1)

## Stage 1: Spec Compliance

### R1 — Pre-file duplicate check — PASS
The duplicate-check grep currently surfaces only the two new items (211, 212). Pre-spec verification recorded zero hits before filing; the now-present matches are the items R2/R3 created, not prior duplicates. No HALT condition.

### R2 — File item 5 as new backlog item — PASS
`cortex/backlog/211-r8-should-track-installed-wheel-commit-not-cwd-working-tree-head-146-follow-up.md` exists with the required frontmatter: `discovery_source: 210-refresh-install-update-docs-close-mcp-only-auto-update-gaps.md`, `tags: [mcp, upgrade]`, `priority: medium`, `type: bug`. Body paraphrases item 5 (R8 cwd-vs-installed-wheel divergence). Acceptance grep returns the file.

### R3 — File item 6 as new backlog item — PASS
`cortex/backlog/212-cli-pin-drift-lint-146-hygiene.md` exists with `discovery_source: 210-…`, `type: chore`, body paraphrasing item 6. Acceptance grep returns the file.

### R4 — Backfill #145 to archive — PASS
`cortex/lifecycle/archive/lazy-apply-cortex-cli-auto-update-via-sessionstart-probe-in-process-apply-on-invoke/` exists; the original directory is absent; the hand-written `feature_wontfix` event is preserved in the archived `events.log`. Three-part acceptance test passes.

### R5 — README line 24 transformation — PASS
The code-fence comment `# Recommended to turn on Auto-Update Marketplace Plugins …` is gone (0 occurrences). README:33 now carries a normal-markdown bullet that explains both layers ("marketplace auto-update at Claude Code startup" → "next MCP tool call triggers the cortex-overnight server's pre-delegate auto-update orchestration"), cross-references `docs/setup.md#upgrade--maintenance`, and avoids any function-name leak (`_ensure_cortex_installed`: 0 occurrences).

### R6 — setup.md two-layer disambiguation — PASS
`docs/setup.md` lines 200–207 spell out the two-layer model explicitly: "Upgrades happen in **two layers**", "Marketplace auto-update at Claude Code startup", "Pre-delegate auto-update orchestration on the next MCP tool call", "MCP-tool-call-gated by design", and the R10 preflight is framed as a "fail-fast preflight" diagnostic, not coverage. Cites `cortex/lifecycle/archive/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/spec.md` and `#146`. No `_ensure_cortex_installed` function-name leak.

### R7 — setup.md CORTEX_ALLOW_INSTALL_DURING_RUN callout — PASS
`docs/setup.md:209` introduces "### Carve-out: in-flight install guard (`CORTEX_ALLOW_INSTALL_DURING_RUN`)" with a blockquote callout containing the inline-only form, the "do NOT export" verbatim phrase, and the full carve-out list (pytest, `CORTEX_RUNNER_CHILD=1`, dashboard, cancel-force). No `^export CORTEX_ALLOW_INSTALL_DURING_RUN` line found.

### R8 — setup.md Verify install PATH remediation — PASS
The `#### Verify install` section contains the targeted remediation: "If `cortex --print-root` returns `command not found`, your shell's `PATH` is missing the `uv` tool bin directory — run `uv tool update-shell` and then reload your shell …" with a back-reference to `install.sh:48`. Both acceptance greps fire.

### R9 — install.sh:48 PATH hint preserved — PASS
The exact log line "if 'cortex' is not on your PATH, run 'uv tool update-shell' and reload your shell." is still emitted by `install.sh`. Acceptance grep finds the literal.

### R10 — implement.md §1a Step 3 inline preflight — PASS
`skills/lifecycle/references/implement.md:90–102` adds the **Preflight (dispatch-readiness fail-fast)** subsection immediately before the launch line, with the exact `command -v cortex-daytime-pipeline >/dev/null 2>&1` shape as a separate Bash call. The remediation pointer surfaces `uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@v0.1.0` (and the §1a-fixup commit 574433f added `--reinstall` to the user-facing prose). The scope is correctly framed as dispatch-readiness only, with a forward-looking note that future skill authors should not propagate the fail-fast pattern. Prose uses positive-routing phrasing ("When the command is found, proceed … When the command is missing, surface … do not proceed"). No MUST/CRITICAL/REQUIRED escalations introduced.

### R11 — cortex-check-parity accepts the new reference — PASS
`bin/cortex-check-parity --audit` exits 0. No W003 (orphan) warning naming `cortex-daytime-pipeline` is produced.

### R12 — Document the wontfix workflow — PASS
`skills/lifecycle/references/wontfix.md` exists and explicitly lists the three steps in order: (a) `git mv` to `archive/`, (b) append `feature_wontfix` event to the now-archived `events.log`, (c) `cortex-update-item … status=wontfix lifecycle_phase=wontfix session_id=null`. The "Why the step order matters" section makes the load-bearing nature of "`git mv` first" explicit. `skills/lifecycle/SKILL.md:225` cross-references the new reference.

### R13 — Python detector recognizes feature_wontfix as terminal — PASS
`cortex_command/common.py:216` declares `feature_wontfix_seen = False`; line 237–238 adds the `elif event_type == "feature_wontfix":` branch alongside `phase_transition`; line 248–254 performs the flag-then-check return of `phase=complete` before the legacy `feature_complete` substring scan. Functional acceptance: a `pathlib.Path`-typed feature_dir with a single-line `{"event": "feature_wontfix", …}` events.log returns `{'phase': 'complete', …}`. (The spec's acceptance snippet used `str(d)`, which fails on a pre-existing type signature constraint at line 388 — `feature_dir / "events.log"` requires Path; the underlying behavior is correct when called with the documented signature.)

### R14 — Statusline mirror — PASS
`claude/statusline.sh:405–406` adds the sibling `elif … grep -q '"feature_wontfix"' "$_lc_fdir/events.log"` line that sets `_lc_phase="complete"`. Adjacency check passes (`grep -A2 '"feature_wontfix"'` shows `_lc_phase="complete"` on the very next line). Single occurrence count (1 ≥ 1).

### R15 — Parity-test fixture — PASS
`tests/fixtures/lifecycle_phase_parity/events-feature-wontfix/events.log` exists with the canonical `{"event": "feature_wontfix", "feature": "x"}` row.

### R16 — Parity test covers wontfix terminal — PASS
`pytest tests/test_lifecycle_phase_parity.py -v -k 'wontfix or feature_wontfix'` reports 5 passing (`test_statusline_ladder_matches_canonical[events-feature-wontfix]`, `test_hook_end_to_end_emit_matches_glue_prediction[events-feature-wontfix]`, `test_feature_wontfix_canonical_python_returns_complete`, `test_feature_wontfix_statusline_ladder_returns_complete`, `test_feature_wontfix_hook_end_to_end`). Full suite: 45 passed.

### R17 — Register feature_wontfix in bin/.events-registry.md — PASS
Row present in `bin/.events-registry.md` with scope `per-feature-events-log`, scan coverage `gate-enforced`, producer `skills/lifecycle/references/wontfix.md`, consumers `cortex_command/common.py:_detect_lifecycle_phase_inner` and `claude/statusline.sh`, status `live`, and the spec-mandated rationale. `bin/cortex-check-events-registry --staged` exits 0.

## Stage 2: Code Quality

- **Naming conventions**: `feature_wontfix_seen` mirrors the existing flag naming (`spec_approved`, `plan_approved`, `spec_transitioned_out`). Event type literal matches the `feature_complete` precedent. Skill reference filename (`wontfix.md`) follows the `references/<topic>.md` convention.
- **Error handling**: Detector branch inherits the JSONDecodeError-tolerant outer loop (per Edge Cases). Statusline grep mirrors the line-403 pattern, including `2>/dev/null` suppression.
- **Test coverage**: Parity test suite passes end-to-end (45/45); the three-layer-equivalent assertions (Python canonical, statusline ladder, hook end-to-end) all exercise the new fixture. `cortex-check-events-registry --staged` and `cortex-check-parity --audit` both exit 0.
- **Pattern consistency — three-layer parity**: Python detector, bash statusline mirror, and parity-test fixture all land together (commit b6a33f9 lands all six R12–R17 atomically per Technical Constraints note). The flag-then-check shape is preserved (exact-match `event_type ==`, not substring scan).
- **Pattern consistency — preflight prose**: §1a preflight uses positive-routing phrasing ("When the command is found, proceed … When missing, surface … do not proceed"), with no MUST/CRITICAL/REQUIRED escalations. The scope-limiting paragraph explicitly tells future skill authors not to copy the fail-fast pattern outside dispatch-readiness contexts.
- **Pattern consistency — dual-source mirrors**: `plugins/cortex-core/skills/lifecycle/SKILL.md`, `plugins/cortex-core/skills/lifecycle/references/wontfix.md`, and `plugins/cortex-core/skills/lifecycle/references/implement.md` are byte-identical to their canonical sources.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
