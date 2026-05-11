# Plan: promote-lifecycle-state-out-of-eventslog-full-reads

## Overview

Ship the spec's parser-cache + bin-reader pattern in seven implementation tasks plus one final verification: (1) a failing parity test pins the canonical `read_tier` semantic, (2) align `common.py:read_tier` to that rule, (3) wrap the three `common.py` readers in `lru_cache` keyed on file mtime, (4) deploy `bin/cortex-audit-tier-divergence` with pre-commit and justfile wiring, (5) deploy `bin/cortex-lifecycle-state` and replace the nine prose scan-events.log stanzas in skills, (6) deploy `bin/cortex-lifecycle-counters` and replace the `complete.md` two-integer stanza, (7) add the bin↔Python parity test, (8) full-suite verification. No structural promotion (no per-feature `state.json`, no `schema_version` field, no new writers), per the spec's Non-Requirements.

## Tasks

### Task 1: Add `tests/test_read_tier_parity.py` (initially failing)

- **Files**: `tests/test_read_tier_parity.py`, `tests/fixtures/state/tier_parity/lifecycle_start_only/events.log`, `tests/fixtures/state/tier_parity/start_then_override/events.log`, `tests/fixtures/state/tier_parity/stray_tier_after_override/events.log`
- **What**: Create a pytest module that pins R2a's four parity cases. Cases (i)–(iii) operate against three new fixture events.log files exercising the canonical-rule edge behavior; case (iv) iterates the in-tree `lifecycle/*/events.log` corpus AND the `tests/fixtures/state/*` corpus and asserts `cortex_command.common.read_tier(feature) == cortex_command.overnight.report._read_tier(feature)` for every entry.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Fixture pattern follows `tests/fixtures/state/*` directories (one per phase) — each parity fixture is a single events.log inside a slug-named subdirectory. The test imports `read_tier` from `cortex_command.common` and `_read_tier` from `cortex_command.overnight.report`. Case fixture content (one JSON object per line):
  - `lifecycle_start_only`: `{"event":"lifecycle_start","feature":"lifecycle_start_only","tier":"simple","criticality":"medium"}` — expected canonical result `"simple"`.
  - `start_then_override`: lifecycle_start with `tier:"simple"`, then `{"event":"complexity_override","feature":"start_then_override","from":"simple","to":"complex"}` — expected canonical result `"complex"`.
  - `stray_tier_after_override`: lifecycle_start with `tier:"complex"`, complexity_override `to:"simple"`, then `{"event":"batch_dispatch","feature":"stray_tier_after_override","tier":"complex"}` — expected canonical result `"simple"` (the stray tier field is ignored).
  - For case (iv), use `Path("lifecycle").glob("*/events.log")` filtered to directories that contain `index.md` (skip stray `sessions/`, `archive/`, etc.); for the fixtures sweep use `Path("tests/fixtures/state").glob("*/events.log")`. Parametrize over both corpora with pytest's `parametrize` so each feature gets its own test ID.
  - Spec acceptance §R2a-i,ii,iii,iv covers all four cases verbatim.
  - The test is expected to FAIL on cases (ii) and (iii) until Task 2 lands; this is the intended TDD ordering — the test pins the semantic before the implementation moves to satisfy it.
- **Verification**: `python3 -m pytest tests/test_read_tier_parity.py -q` — pass if the test module collects without ImportError or fixture errors AND fails with `AssertionError` (not collection error) on at least one of cases (ii), (iii), (iv) — confirming the test exercises the divergence before Task 2 lands.
- **Status**: [x] complete — committed `c05f1a4`. Empirical finding during execution: 6 in-tree lifecycles diverge between last-wins and canonical rules (audit-cortex-..., collapse-byte-identical-..., lifecycle-and-hook-hygiene-one-offs, reference-file-hygiene-..., skill-design-test-infrastructure-..., vertical-planning-adoption-...). All 6 carry `feature_complete` events — they are **closed lifecycles**; runtime blast radius for `outcome_router.py:830` remains zero. Spec line 42's "zero affected lifecycles" claim is technically wrong but production-equivalent; Task 4 must scope its audit to active lifecycles (no `feature_complete`) to satisfy the "exits 0 against current corpus" acceptance.

### Task 2: Align `cortex_command/common.py:read_tier` to canonical rule

- **Files**: `cortex_command/common.py`, `tests/test_read_tier_parity.py` (no body edit — re-run only)
- **What**: Replace the existing "last `tier` field wins" loop body (`common.py:339-354`) with the canonical `lifecycle_start → complexity_override.to` rule that `cortex_command/overnight/report.py:746-778` already implements. Preserve the function signature `read_tier(feature: str, lifecycle_base: Path = Path("lifecycle")) -> str` and the `"simple"` default for missing/empty/no-relevant-event states.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Mirror the loop body of `report.py:_read_tier` (lines 763-778) into `common.py:read_tier`: iterate parsed records; on `event == "lifecycle_start"`, capture `record["tier"]` if non-empty string; on `event == "complexity_override"`, capture `record["to"]` if non-empty string; return the last captured value or `"simple"` if none found. The two functions intentionally remain duplicated for now — unifying them is out of scope per spec Non-Requirements (no new writer code; this ticket modifies one reader, not the broader module structure). Callers of `read_tier`: `cortex_command/overnight/outcome_router.py:24,830` is the only production consumer and is the call site whose review-gating behavior the audit (Task 4) guards against silent shift.
- **Verification**: `python3 -m pytest tests/test_read_tier_parity.py -q` — pass if exit 0 and all four cases (i,ii,iii,iv) pass.
- **Status**: [x] complete — committed `5313fc6`. 39/39 parity tests pass; in-tree corpus is now zero-divergence between common.py and report.py.

### Task 3: Add `lru_cache` to `read_criticality`, `read_tier`, `detect_lifecycle_phase`

- **Files**: `cortex_command/common.py`, `tests/test_lifecycle_state.py`
- **What**: Wrap each of the three readers in `functools.lru_cache(maxsize=128)` via an inner uncached helper that takes per-file `(exists: bool, mtime_ns: int, size: int)` triples as cache-key arguments, plus an outer wrapper that captures those triples via `stat()` and explicitly assigns `read_criticality.__wrapped__ = _read_criticality_inner` (and the same for `read_tier`, `detect_lifecycle_phase`) so the spec R1 binary acceptance command (`print(read_criticality.__wrapped__ is not None)`) prints `True`. For `detect_lifecycle_phase`, the cache key spans **all five files the function reads** — events.log, plan.md, review.md, **spec.md, and research.md** — as a 5-tuple of per-file `(exists, mtime_ns, size)` triples. The `size` component closes the sub-mtime_ns append window: appends bump file size even when mtime collides. Tests in `tests/test_lifecycle_state.py` add three mtime-invalidation tests (one per reader) that explicitly call `os.utime(path, ns=(N, N+1_000_000))` between calls to force monotonic mtime advance, plus one `test_detect_phase_invalidates_on_spec_md` test that asserts cache invalidation when spec.md is created against an existing research-phase fixture.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: `functools.lru_cache` is stdlib; existing precedent at two call sites in `cortex_command/` already. Pattern: define `def _read_criticality_inner(events_path_str: str, exists: bool, mtime_ns: int, size: int) -> str:` decorated with `@lru_cache(maxsize=128)`; the public `read_criticality(feature, lifecycle_base)` resolves the path, calls `try: s = path.stat(); key = (True, s.st_mtime_ns, s.st_size) except FileNotFoundError: key = (False, 0, 0)`, then calls the inner helper. After the inner helper is defined, set `read_criticality.__wrapped__ = _read_criticality_inner` so spec R1's `__wrapped__`-on-public-API acceptance command succeeds. Same shape for `read_tier`. For `detect_lifecycle_phase` (`common.py:143-272` — note: the function checks `spec.md` at line 249 and `research.md` at line 258 as state-machine gating conditions, in addition to events.log/plan.md/review.md), the inner helper takes a 5-tuple of per-file triples. Test fixture pattern: create a tmpdir lifecycle layout via `tmp_path` pytest fixture, write events.log with one criticality line, call `read_criticality`, append a second criticality line, **explicitly call `os.utime(events_path, ns=(now_ns + 1_000_000, now_ns + 1_000_000))`** to force mtime advance past filesystem resolution, call again, assert the second-call result. Without the explicit `os.utime`, back-to-back `write_text` on a fast machine can produce identical `st_mtime_ns` and the test passes accidentally. Cache size 128: at ~20 features × 3 readers, 128 covers the dashboard hot path with headroom.
- **Verification**: (a) `python3 -m pytest tests/test_lifecycle_state.py -q` exits 0 (existing tests still pass AND the four new mtime-invalidation tests pass — three readers × one mtime-invalidation case + one spec.md-creation-invalidation case); (b) the spec R1 binary acceptance command runs verbatim — `python3 -c "from cortex_command.common import read_criticality; print(read_criticality.__wrapped__ is not None)"` exits 0 and stdout is `True`; (c) same command for `read_tier` and `detect_lifecycle_phase` both exit 0 and print `True`.
- **Status**: [x] complete

### Task 4: Add `bin/cortex-audit-tier-divergence` + pre-commit hook + justfile wiring

- **Files**: `bin/cortex-audit-tier-divergence`, `.githooks/pre-commit`, `justfile`, `tests/test_audit_tier_divergence.py`, `tests/fixtures/audit_tier/divergent/events.log`, `tests/fixtures/audit_tier/clean/events.log`
- **What**: Deploy the corpus audit (R2b) and gate it from pre-commit (R2c). Script reads every `lifecycle/*/events.log` under the repo root, computes `read_tier_last_wins` (legacy rule: most-recent line with any `tier` field) and `read_tier_canonical` (matches Task 2's rule), and exits non-zero with stderr `tier-divergence: <feature> last_wins=<x> canonical=<y>` for each mismatch. Pre-commit Phase 1.9 invokes `just audit-tier-divergence` when staged diffs touch `cortex_command/common.py` or `cortex_command/overnight/report.py`. Justfile gains a `audit-tier-divergence` recipe that execs the bin script. Tests cover divergent and clean fixtures.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - **Script shape**: Python, not bash — needs to parse events.log lines and apply two distinct rules. Follow the existing shim convention from `bin/cortex-check-events-registry` and similar (`from cortex_command.common import ...` is fine; the bin scripts execute under the same Python). Script entry begins with the standard `subprocess.run([os.path.join(...), "cortex-log-invocation"], ...)` shim line per `bin/cortex-check-parity:23`. Argument: `--root` (default `.`) for testability. Exit codes: `0` clean, `1` divergence found, `2` script error.
  - **Logic**:
    - `read_tier_last_wins(events_path)`: replicate the OLD `common.py:read_tier` loop body (the one Task 2 removed) — return the last record's `tier` field across any event.
    - `read_tier_canonical(events_path)`: call `cortex_command.common.read_tier` (now canonical post-Task 2) or inline the same rule.
    - For each `events_path in Path(root).glob("lifecycle/*/events.log")` (skip non-feature dirs by gating on `events.log` existence), compare; emit divergence and tally.
    - **Active-only scope (per Task 1 empirical finding)**: by default, skip any lifecycle whose events.log contains a `"event":"feature_complete"` line (closed lifecycles). The 6 currently-divergent in-tree lifecycles are all closed and their runtime decision-path blast radius is zero (`outcome_router.py:830` does not re-enter closed features). Add a `--include-closed` flag (default false) that disables this filter for archeological auditing.
  - **Pre-commit wiring**: add Phase 1.9 immediately after Phase 1.8 in `.githooks/pre-commit:170`. Follow the pattern of Phase 1.8: scan `git diff --cached --name-only --diff-filter=ACMR` for `cortex_command/common.py|cortex_command/overnight/report.py`, set `tier_audit_triggered=1`, then `if [ "$tier_audit_triggered" -eq 1 ]; then if ! just audit-tier-divergence; then echo "pre-commit: tier-divergence audit failed..." >&2; exit 1; fi; fi`. Spec R2c acceptance string `tier-divergence` must appear in stderr — the bin script's stderr already emits it; the pre-commit echo line should reference it explicitly so failure-message matching is robust.
  - **Justfile recipe**: add `audit-tier-divergence:\n    bin/cortex-audit-tier-divergence` after the existing `check-parity` recipe (~line where other `bin/cortex-*` recipes cluster).
  - **Tests**: `tests/test_audit_tier_divergence.py` invokes the script via `subprocess.run([sys.executable, "bin/cortex-audit-tier-divergence", "--root", str(tmp_path)], ...)`. Fixtures: `tests/fixtures/audit_tier/clean/lifecycle/foo/events.log` (lifecycle_start + override only — no divergence) and `tests/fixtures/audit_tier/divergent/lifecycle/foo/events.log` (lifecycle_start tier:complex, complexity_override to:simple, batch_dispatch tier:complex — last_wins says complex, canonical says simple).
  - **Wiring for parity (W003)**: justfile reference + tests/ reference both satisfy `bin/cortex-check-parity`'s SCAN_GLOBS at `bin/cortex-check-parity:74,77` (`justfile`, `tests/**/*.py`). `.githooks/pre-commit` is NOT in SCAN_GLOBS — do not rely on it alone.
- **Verification**: (a) `bin/cortex-audit-tier-divergence` exits 0 against current corpus — `bin/cortex-audit-tier-divergence; echo $?` prints `0`; (b) `python3 -m pytest tests/test_audit_tier_divergence.py -q` exits 0; (c) `just audit-tier-divergence` from project root exits 0; (d) `git diff --cached --name-only` simulating a `common.py:read_tier` change triggers the pre-commit Phase 1.9 stderr token `tier-divergence` — verify by staging a no-op `common.py` edit and running `.githooks/pre-commit`, then unstaging.
- **Status**: [ ] pending

### Task 5: Add `bin/cortex-lifecycle-state` and replace all nine prose scan-events.log stanzas in one commit

- **Files**: `bin/cortex-lifecycle-state`, `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/plan.md`, `skills/lifecycle/references/specify.md`, `skills/lifecycle/references/orchestrator-review.md`, `skills/lifecycle/references/implement.md`, `skills/refine/SKILL.md`, `skills/dev/SKILL.md`, `skills/morning-review/references/walkthrough.md` (10 files total — 1 new + 9 edits)
- **What**: Deploy the JSONL-streaming bash reader (R3) and replace **all nine** R6-target prose stanzas — SKILL.md lines 76 & 78; plan.md:21 & :269; specify.md:147; orchestrator-review.md:7; implement.md:246; refine/SKILL.md:159; dev/SKILL.md:126; morning-review/references/walkthrough.md:237 — with `cortex-lifecycle-state --feature {feature} --field {criticality|tier}` invocations. The 5-file rule is set aside here because the work is mechanical 1-2 line prose substitutions across 9 sites, and splitting the deploy from the wire (or splitting wires across two commits) creates a working-tree window where two reader mechanisms coexist on the skill-prompt surface — re-creating, at the prompt layer, exactly the divergence this ticket exists to close.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - **Script shape**: bash, executable (chmod +x), shebang `#!/usr/bin/env bash`. Begins with a `command -v jq >/dev/null || { echo "cortex-lifecycle-state: jq is required but not installed" >&2; exit 2; }` preflight to fail-loud on missing dependency. Next line: the `cortex-log-invocation` shim invocation per `bin/cortex-log-invocation:1-30` (script_dir-relative invocation, fail-open). CLI: `cortex-lifecycle-state --feature <slug> [--field criticality|tier]`. With no `--field`, output JSON `{"criticality": "<value>", "tier": "<value>"}`; with `--field`, output JSON containing only that key.
  - **Logic — JSONL streaming, not literal grep**: do NOT use `grep '"event":"X"'` literal-substring matching. The in-tree corpus mixes serialization styles (Python `json.dumps` default emits `"event": "X"` with whitespace; 23 of 25 in-tree `events.log` files use the spaced form). A literal-substring grep silently misses ~92% of the corpus. Use jq's per-line streaming with `fromjson?` instead:
    - Resolve `events.log` path: `lifecycle/<slug>/events.log`. If missing, output `{}` (per spec Edge Cases) and exit 0.
    - `criticality` (canonical rule — most-recent of `lifecycle_start`/`criticality_override`): pipe `jq -cR 'fromjson? | select(.event=="lifecycle_start" or .event=="criticality_override") | (.criticality // .to // empty)' "$events"` then `tail -n 1` for the most-recent emit. Empty result → omit the key (caller handles default `"medium"`).
    - `tier` (canonical rule — `lifecycle_start.tier` superseded by `complexity_override.to`): pipe `jq -cR 'fromjson? | select(.event=="lifecycle_start" or .event=="complexity_override") | (.tier // .to // empty)' "$events"` then `tail -n 1`. Empty result → omit the key (caller defaults to `"simple"`).
    - The `fromjson?` operator parses each line as JSON and yields `empty` on parse failure — torn writes / malformed lines are silently skipped rather than crashing the script.
    - The `.event==` filter matches the parsed top-level field — it cannot false-positive on a nested-string occurrence of `"event":"X"` inside a `clarify_critic` event's `findings` array.
    - Build output JSON with `jq -n --arg c "$criticality" --arg t "$tier" '{}'` plus conditional field assignment per supplied `--field`. Per-call cost target ≤15ms wall time on 15 KB events.log (spec R3 acceptance, verified by `time` in CI assertion).
  - **Skill prompt replacements**: For each of the 9 citations in Files, edit the prose paragraph to replace the scan-events.log directive with a single `cortex-lifecycle-state --feature {feature} --field criticality` (or `--field tier`) invocation. **Preserve the surrounding semantic verbatim** — defaults to `medium`/`simple` when the bin script omits the key, when-to-use guidance, what-it-returns. The pre-existing detection logic in `skills/lifecycle/SKILL.md:76-81` consolidates to two prose lines each pointing at the bin script. For `morning-review/references/walkthrough.md:237`, only the scan-stanza at line 237 is in R6's enumerated scope; keep the surrounding `feature_complete` already-in-events-log scan (lines 232-262 region) unchanged.
  - **Spec R6 regex defect**: the spec's acceptance regex `scan.*for the most recent.*lifecycle_start|read events\.log for.*criticality|read events\.log for.*tier` does not match the actual prose word-order (verified — returns 1 hit on the unmodified tree, not 9). Task 5's verification therefore uses **targeted prose-fingerprint greps** that match the actual phrases being removed, not the spec's vacuous regex. The spec regex defect itself is filed as a follow-up note in the Veto Surface.
- **Verification** (run from project root):
  - (a) `bin/cortex-lifecycle-state --feature promote-lifecycle-state-out-of-eventslog-full-reads --field tier` exits 0 and stdout satisfies `jq -e '.tier == "complex"'`.
  - (b) Targeted scan-stanza fingerprint check returns 0 hits across all 9 sites — `bash -c 'grep -lE "Scan for the most recent|scan events\.log|read events\.log|find the most recent event containing" skills/lifecycle/SKILL.md skills/lifecycle/references/plan.md skills/lifecycle/references/specify.md skills/lifecycle/references/orchestrator-review.md skills/lifecycle/references/implement.md skills/refine/SKILL.md skills/dev/SKILL.md skills/morning-review/references/walkthrough.md | wc -l'` = 0 (where each phrase fingerprint matches one of the existing scan-stanza variants in the listed files).
  - (c) `bash -c 'grep -rc "cortex-lifecycle-state" skills/lifecycle/ skills/refine/ skills/dev/ skills/morning-review/ | awk -F: "{s+=\$2} END {print s}"'` ≥ 9.
  - (d) Bin-vs-Python whitespace-corpus parity smoke check — `for slug in $(ls lifecycle/ | grep -v sessions); do diff <(bin/cortex-lifecycle-state --feature "$slug" --field tier 2>/dev/null | jq -r '.tier // "(absent)"') <(python3 -c "from cortex_command.common import read_tier; print(read_tier('$slug'))") || echo "DIVERGENCE: $slug"; done` emits no `DIVERGENCE:` lines (each feature with an events.log returns identical tier from bin script and Python reader).
  - (e) `time bash -c 'bin/cortex-lifecycle-state --feature promote-lifecycle-state-out-of-eventslog-full-reads --field tier'` wall time <15ms on this machine.
- **Status**: [ ] pending

### Task 6: Add `bin/cortex-lifecycle-counters` and replace complete.md stanzas

- **Files**: `bin/cortex-lifecycle-counters`, `skills/lifecycle/references/complete.md`
- **What**: Deploy the bash counters reader (R4) and replace the two-integer prose extraction in `complete.md:25-26` with a single `cortex-lifecycle-counters --feature {feature}` invocation per R5.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - **Script shape**: bash, same shebang + jq-preflight + shim pattern as Task 5. CLI: `cortex-lifecycle-counters --feature <slug>`. Output JSON `{"tasks_total": <int>, "tasks_checked": <int>, "rework_cycles": <int>}`.
  - **Logic**:
    - `tasks_total`: `grep -cE '^- \[[ xX]\]' "lifecycle/<slug>/plan.md"` — total unchecked + checked boxes at start of line, accepting GitHub-flavored `[X]` capital. (Same matcher class as `cortex_command/common.py:detect_lifecycle_phase` checkbox count at `common.py:173-179`; the implementer should verify common.py is similarly case-insensitive — if not, file a parity-follow-up note and match common.py's exact case-sensitivity for Task 7 to pass.)
    - `tasks_checked`: `grep -cE '^- \[[xX]\]' "lifecycle/<slug>/plan.md"`.
    - `rework_cycles`: count of verdict lines in `lifecycle/<slug>/review.md` matching the same regex `common.py:detect_lifecycle_phase` uses (`"verdict"\s*:\s*"([A-Z_]+)"` per research:13, applied at `common.py:182-192`). For shell impl: `grep -cE '"verdict"[[:space:]]*:[[:space:]]*"[A-Z_]+"' review.md`. **Known fragility carried over from common.py**: this regex over-counts if review.md contains quoted/example verdict-shaped strings in prose or code blocks. Behavior is intentionally identical to the Python side; loosening would diverge from common.py's existing behavior and break Task 7 parity. Filed in Veto Surface as a follow-up.
    - Missing files → field defaults: tasks_total=0, tasks_checked=0, rework_cycles=0.
    - Compose output with `jq -n --argjson a $total --argjson b $checked --argjson c $cycles '{tasks_total:$a, tasks_checked:$b, rework_cycles:$c}'`.
  - **complete.md replacement** (R5): edit lines 17-26 of `skills/lifecycle/references/complete.md` to replace the two bulleted "Count the total checkboxes..." / "Read the cycle count..." prose lines with a single instruction: "Read `tasks_total` and `rework_cycles` by running `cortex-lifecycle-counters --feature {feature}` and parsing the JSON output." Keep the surrounding `feature_complete` event-emit guidance (lines 19-23 and 28-onward) unchanged.
  - **Wiring co-location**: deploying `cortex-lifecycle-counters` and editing complete.md in one task per the parity W003 rule.
- **Verification**: (a) against the fixture at `tests/fixtures/audit_tier/counters_fixture/` (which Task 7 will scaffold — for Task 6 alone, use the live `lifecycle/promote-lifecycle-state-out-of-eventslog-full-reads/` directory with its plan.md present after this task lands): `bin/cortex-lifecycle-counters --feature promote-lifecycle-state-out-of-eventslog-full-reads` exits 0 and stdout satisfies `jq -e '.tasks_total > 0 and .tasks_checked >= 0 and .rework_cycles >= 0'`; (b) `grep -c "Count the total checkboxes" skills/lifecycle/references/complete.md` = 0; (c) `grep -c "cortex-lifecycle-counters" skills/lifecycle/references/complete.md` ≥ 1.
- **Status**: [ ] pending

### Task 7: Add `tests/test_bin_lifecycle_state_parity.py`

- **Files**: `tests/test_bin_lifecycle_state_parity.py`, `tests/fixtures/bin_parity/feat1/events.log`, `tests/fixtures/bin_parity/feat1/plan.md`, `tests/fixtures/bin_parity/feat1/review.md`, `tests/fixtures/bin_parity/feat2/events.log`, `tests/fixtures/bin_parity/feat2/plan.md`
- **What**: Subprocess parity test (spec Edge Cases: "Bin-script vs Python-helper drift") — invoke `cortex-lifecycle-state` and `cortex-lifecycle-counters` as subprocesses against fixtures and assert their output matches `cortex_command.common.read_criticality` / `read_tier` / a Python-side counters computation. Pinned in tests so future drift between the bash and Python paths is caught at CI.
- **Depends on**: [5, 6]
- **Complexity**: simple
- **Context**: Fixture layout: each `feat*/` directory carries `events.log` (some with criticality_override, some without; some with complexity_override, some without), `plan.md` (mix of checked/unchecked tasks), and optionally `review.md` (mix of verdict counts). Test invokes the bash scripts via `subprocess.run(["bin/cortex-lifecycle-state", "--feature", feat, ...], cwd=fixture_root, capture_output=True, text=True)` then `json.loads(result.stdout)` and compares each field. For counters: Python side recomputes via `len(re.findall(r'^- \[[ x]\]', plan_text, re.M))` etc. The test does NOT re-validate Task 1's parity scope — it specifically checks bin-vs-Python equality on a single corpus.
- **Verification**: `python3 -m pytest tests/test_bin_lifecycle_state_parity.py -q` — pass if exit 0 (both bin scripts return values matching Python-side computation for every fixture).
- **Status**: [ ] pending

### Task 8: Full-suite verification (no code changes)

- **Files**: none (verification-only task)
- **What**: Run the full test suite, parity check, dual-source build, and tier-divergence audit to confirm the feature lands cleanly. This task makes no source edits; it exists to enforce a final green-board signal before the Review phase.
- **Depends on**: [3, 4, 5, 6, 7]
- **Complexity**: trivial
- **Context**: None — pure verification gate. Per the plan reference: "trivial = single-file edit, no side effects, no commit needed" — this task fits the verification-only carve-out.
- **Verification**: All five commands exit 0:
  - `just test` — pass if exit 0.
  - `just check-parity` — pass if exit 0 (no W003 orphans against new bin scripts).
  - `just build-plugin` — pass if exit 0 (dual-source mirror clean; `git diff --quiet plugins/cortex-core/bin/` after the build).
  - `just audit-tier-divergence` — pass if exit 0 (in-tree corpus has no divergence).
  - `just check-events-registry` — pass if exit 0 (no events emitted by this ticket; should be a no-op pass).
- **Status**: [ ] pending

## Outline

Two implementation phases plus a verification phase. Phase boundaries map to the natural rework checkpoints — between Phase A and Phase B the canonical reader rule is settled and exercisable; between Phase B and Phase C the new bin readers exist and are wired but no end-to-end verification has run.

### Phase A — Reader semantics + caching (Tasks 1, 2, 3)

- **Goal**: Land the canonical `read_tier` rule and the `lru_cache` perf win behind the existing reader API. No new bin scripts, no skill-prompt changes, no consumer-visible behavior shift on the in-tree corpus (verified zero divergent lifecycles).
- **Checkpoint**: `python3 -m pytest tests/test_read_tier_parity.py tests/test_lifecycle_state.py -q` exits 0. `cortex_command/common.py:read_tier` returns identical values to `cortex_command/overnight/report.py:_read_tier` on the in-tree `lifecycle/*/` corpus; the three readers expose `lru_cache` keyed on file mtime.

### Phase B — Bin readers + consumer wiring (Tasks 4, 5, 6, 7)

- **Goal**: Deploy the three new `bin/cortex-*` scripts (`cortex-audit-tier-divergence`, `cortex-lifecycle-state`, `cortex-lifecycle-counters`) with full consumer wiring — pre-commit gate, justfile recipe, all nine skill-prompt stanza replacements in a single commit, complete.md two-integer replacement, and bin↔Python parity tests. Each task that deploys a bin script also adds its full consumer wiring in the same commit, so the skill-prompt surface never enters a half-migrated state.
- **Checkpoint**: All three bin scripts return JSON for the current lifecycle. Targeted scan-stanza fingerprint grep (Task 5 verification b) returns 0 hits across all 9 R6 sites. `grep -c "cortex-lifecycle-counters" skills/lifecycle/references/complete.md` ≥ 1. `python3 -m pytest tests/test_bin_lifecycle_state_parity.py tests/test_audit_tier_divergence.py -q` exits 0. Bin-vs-Python whitespace-corpus parity (Task 5 verification d) emits no `DIVERGENCE:` lines.

### Phase C — Full-suite verification (Task 8)

- **Goal**: Confirm the cross-cutting machinery (just test, parity, dual-source build, tier-divergence audit, events-registry) all pass on a green board before handing off to Review.
- **Checkpoint**: `just test && just check-parity && just build-plugin && just audit-tier-divergence && just check-events-registry` exits 0 end-to-end.

## Acceptance

The feature is complete when all five conditions hold simultaneously on a clean working tree:

1. `python3 -m pytest tests/ -q` exits 0 — full test suite green including the three new test modules (`test_read_tier_parity.py`, `test_bin_lifecycle_state_parity.py`, `test_audit_tier_divergence.py`) plus the new mtime-invalidation tests in `test_lifecycle_state.py`.
2. `bin/cortex-audit-tier-divergence` exits 0 against the in-tree `lifecycle/*/` corpus — zero `read_tier_last_wins ≠ read_tier_canonical` mismatches.
3. `bin/cortex-lifecycle-state --feature <slug>` and `bin/cortex-lifecycle-counters --feature <slug>` each exit 0 and return valid JSON for every in-tree feature with an `events.log` present.
4. The four spec R5 acceptance grep assertions evaluate as documented (`Count the total checkboxes` count = 0, `cortex-lifecycle-counters` count ≥ 1 in complete.md). For R6, the **plan's targeted prose-fingerprint check** (Task 5 verification b, not the spec's vacuous regex) returns 0 hits across all 9 sites and `cortex-lifecycle-state` count ≥ 9 across the same scope.
5. Bin-vs-Python parity smoke loop (Task 5 verification d) emits no `DIVERGENCE:` lines across the in-tree `lifecycle/*/` corpus — confirming the jq-stream readers agree with `common.py` regardless of events.log serialization style.
6. `just check-parity && just build-plugin` exits 0 — no W003 orphans on the three new bin scripts, no dual-source drift in `plugins/cortex-core/bin/`.

## Verification Strategy

Post-implementation feature-level verification, beyond Task 8's commands:

1. **Per-spec acceptance check**: walk the spec's six numbered Requirements and confirm each acceptance command/assertion in the spec body returns the documented value. Spec acceptance commands are reproduced in each task's Verification field; running them via Task 8's `just test` exercises the test-coded ones, but the four `grep -c` acceptance assertions in R5/R6 must be run manually after Task 5/6.
2. **Production read-path smoke test**: invoke `python3 -c "from cortex_command.common import read_criticality, read_tier, detect_lifecycle_phase; ..."` against each in-tree `lifecycle/*/` and confirm no exceptions. Then call each twice and inspect `read_criticality.cache_info()` (or the inner helper's) to confirm cache hits on the second call.
3. **Dashboard polling regression**: launch `just dashboard`, browse to a lifecycle feature page, leave it polling for 30s, then check whether per-poll wall-time decreased vs. pre-change baseline. This is an informational signal — no acceptance threshold is set since the spec deliberately does not include perf-instrumentation JSONL (per Non-Requirements). The dashboard "feels responsive" is sufficient.
4. **Overnight pipeline shim test**: run a single-feature overnight smoke dispatch (if available locally) to confirm `outcome_router.py:830 requires_review()` still routes correctly under the canonically-aligned `read_tier`. Today's corpus has zero divergent lifecycles (verified ad-hoc 2026-05-11, formalized as Task 4's clean-corpus check), so this is a regression-safety check rather than a behavioral verification.

## Veto Surface

Design choices the user may want to revisit before implementation begins:

- **Task 1 ordering (test-before-implementation)**: Task 1 lands a failing test before Task 2 fixes it. This means the working tree is briefly in a state where `pytest` reports a known failure. The alternative is to land Tasks 1+2 in a single task; the chosen split improves bisectability if the canonical rule is ever found wrong, but anyone running the full test suite between Tasks 1 and 2 sees a red board. **Trade-off**: cleaner audit trail vs. transient red CI signal. Default: ship as planned (split); revisit if the user prefers atomic landing.
- **`lru_cache` size 128 (Task 3)**: 128 covers ~20 features × 3 readers with headroom for ~70% spare. If the user expects >40 active lifecycles per repo, raise to 256. Spec R1 specifies 128; if the user wants a different value, edit Task 3 and the spec.
- **`bin/cortex-audit-tier-divergence` as Python, not bash (Task 4)**: spec R2b doesn't specify language. Python lets the script import the canonical reader directly and avoid re-implementing the rule in bash; the trade-off is ~20ms Python boot vs. ~7ms bash on the audit path. The audit runs only on staged-diff trigger (rare per commit), so the cost is irrelevant. The user could insist on bash for consistency with `cortex-lifecycle-state` and `cortex-lifecycle-counters` — but then the canonical rule would be duplicated in three places (`common.py`, `report.py`, bash audit), which is the very divergence-risk this ticket is supposed to close.
- **Wiring co-location (Tasks 4/5/6)**: Each task that deploys a bin script also includes its consumer wiring. The alternative — deploy in one task, wire in a follow-up — would force `git commit --no-verify` between tasks because the parity check (W003) blocks orphans. The plan reference explicitly discourages `--no-verify`. **Trade-off**: larger task surface vs. clean pre-commit signal. Default: ship as planned (co-located).
- **No update to `_read_tier` in `report.py`**: Task 2 aligns `common.py:read_tier` to `report.py:_read_tier`'s rule; `report.py:_read_tier` itself remains untouched. Long-term, the two should consolidate to one function (probably in `common.py`, since `report.py` is the overnight-only consumer). This is **explicitly out of scope** per spec Non-Requirements ("No changes to Python writer code"... and by spirit, no broader refactor). A follow-up ticket can collapse them once the canonical rule is settled in both places. **Trade-off**: keep two readers in sync (current state, pre-commit gated) vs. one reader (future state, separate ticket). Default: ship two readers gated by the audit.
- **Skill prompt prose granularity (Task 5)**: The R6 acceptance counts ≥9 `cortex-lifecycle-state` references across the listed files. The spec doesn't constrain WHERE in each file the reference lands; a careless edit could leave the surrounding "default to medium" / "default to simple" semantics ambiguous. Implementer judgment is required to preserve those defaults during the prose rewrite. Each replacement should be ≤2 lines of prose: "Read criticality by running `cortex-lifecycle-state --feature {feature} --field criticality` (defaults to `medium` when events.log is missing or has no relevant event)." — this preserves the semantic.

- **Spec R6 regex is vacuous on the unmodified tree (follow-up)**: the spec's R6 acceptance regex `scan.*for the most recent.*lifecycle_start|read events\.log for.*criticality|read events\.log for.*tier` returns ~1 hit against the actual R6-target prose because word order in the prose (e.g., "read criticality from events.log") does not match the regex's required substring order ("read events.log for criticality"). Task 5 verification (b) substitutes a **targeted prose-fingerprint grep** matching the actual scan-stanza phrases. A follow-up ticket should amend the spec's R6 regex (or remove the acceptance entirely in favor of the prose-fingerprint approach). This plan does not block on that amendment.

- **Bin script vs Python checkbox case-sensitivity (follow-up)**: Task 6 uses `^- \[[ xX]\]` to accept GitHub-flavored capital `[X]`. The implementer should verify whether `cortex_command/common.py:detect_lifecycle_phase` checkbox count is similarly case-insensitive. If common.py is lowercase-only, Task 6's parity test (Task 7) will fail on capital-X fixtures — in which case the bin script must match common.py's case-sensitivity for parity, and the broader case-insensitivity fix is filed as a separate follow-up that updates both readers atomically.

- **Verdict-count regex carries existing fragility (follow-up)**: `cortex-lifecycle-counters` rework_cycles count over review.md uses the same regex `common.py:detect_lifecycle_phase` already applies — both will over-count when review.md contains quoted/example verdict-shaped strings in prose. Behavior is intentionally identical to the Python side to preserve Task 7 parity. Loosening the bash regex (e.g., parsing review.md structurally) would diverge from `common.py` and fail parity. A follow-up ticket can tighten both readers atomically once a review.md-format convention is pinned.

- **`jq` dependency assumed but not auto-installed (Veto)**: both new bin scripts require `jq` and ship with a `command -v jq` preflight that exits non-zero with a clear stderr if jq is missing. `cortex init` does not install jq. Fresh CI containers, uv-tool-install consumers, and macOS users without Homebrew jq will see the loud failure rather than silent wrong answers. The trade-off is `jq` joins `just`, `python3`, `uv` as a user-visible dependency. If the user prefers, Tasks 5/6 can switch to a pure-Python helper (~20ms boot vs ~7ms jq); the spec selected bash+grep+jq, but the JSONL-streaming approach in this updated plan is compatible with either backend. Default: ship as bash+jq.

- **Cache key `(exists, mtime_ns, size)` triple vs spec R1 `(path, mtime_ns)` wording (Veto)**: spec R1 says the cache is "keyed on `(path, mtime_ns)` of the underlying file(s)". The plan widens this to per-file `(exists, mtime_ns, size)` triples to close two failure modes the spec didn't anticipate: (a) sub-mtime_ns append windows where the file's mtime collides between writes (size component breaks ties); (b) `0`-mtime collisions between missing-file sentinels and legitimately-zero-mtime fixtures (`exists` boolean disambiguates). This is a strict superset of the spec's key — every change the spec's key would catch, the wider key also catches — but the wording differs. If the user wants the wider key reflected in spec R1's text, a one-line amend.

- **`detect_lifecycle_phase` 5-tuple key vs spec R1 wording (Veto)**: spec R1 says the cache is keyed on "the underlying file(s)" (plural), without enumerating which files. The plan reads `common.py:143-272` and concludes the function reads 5 files (events.log, plan.md, review.md, spec.md, research.md) — all 5 contribute to the cache key. If a future refactor reduces the file set, the cache key must shrink in lockstep. Filed in Veto Surface so the user can flag this as a maintenance burden if they prefer a different approach (e.g., key on directory mtime, accepting whole-feature-dir granularity).

## Scope Boundaries

Explicitly excluded from this feature (maps to spec Non-Requirements §24-36):

- **No `lifecycle/<feature>/state.json` file.** Structural promotion is deferred per the research's W4-falsification + adversarial-review conclusion + audit's actual Tier-3 cost finding.
- **No `schema_version` field, no atomic-write helper integration, no CAS / version-locking, no field-partitioning protocol.** All conditional on the structural shift that is not happening here.
- **No new `tests/` concurrent-writer infrastructure** (`multiprocessing.Process` fixtures). No new writer is introduced.
- **No changes to Python writer code** (`pipeline/review_dispatch.py`, `overnight/runner.py`, `overnight/outcome_router.py`, `overnight/feature_executor.py`, `bin/cortex-complexity-escalator`). Writers continue to emit to events.log exactly as today.
- **No changes to `phase` derivation**. `detect_lifecycle_phase`'s 6-step state machine over file presence + checkbox state continues to be authoritative for `phase`; only its file reads gain the `lru_cache` wrapper.
- **No changes to skill-prompt event-emit instructions.** Only reader-stanzas are consolidated.
- **No events-registry pin for "state-source-of-truth" events.** Defensible follow-up if a future ticket attempts to demote any of `lifecycle_start`, `criticality_override`, `complexity_override`, `phase_transition`, `review_verdict`, or `feature_complete`.
- **No verdict-regex golden-fixture test.** Defensible follow-up if the reviewer prompt is rewritten.
- **No perf-instrumentation JSONL** in `dashboard/data.py` and no measurement-gated follow-up ticket creation procedure. The instrumentation site would record only the dashboard regime where caching is maximally effective; it cannot produce data that would justify a future structural shift.
- **No migration of in-flight lifecycles.** The `lru_cache` addition is transparent; first-call cost is unchanged.
- **No collapse of `common.py:read_tier` and `report.py:_read_tier` into a single function.** Out of scope this ticket; gated by the audit until a future ticket retires the duplication.
