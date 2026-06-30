# Review: offload-lifecycle-step-2-backlog-write

Review of #326 (epic #336 last child) across commits `fad82d13` (create-index, Tasks 1+2)
and `10f62b6d` (start-sync, Tasks 3+4+4b). `cortex/lifecycle/fix-feature-complete-emission-ordering-strand/*`
paths excluded (concurrent #339 session). Read-only review — no source files modified.

## Stage 1: Spec Compliance

### Requirement 1: `cortex-lifecycle-create-index` creates index.md byte-faithfully
- **Expected**: New `create_index.py` + `[project.scripts]` entry; writes `cortex/lifecycle/{slug}/index.md`
  with 7 fixed-order fields, inline `artifacts: []`, wikilink body on match (full stem both sides, unquoted
  title), heading/body omitted on `--backlog-file ""`. Golden-byte test for both shapes; `pytest` exits 0.
- **Actual**: `create_index.py:_render` emits exactly the 7 ordered fields + `artifacts: []` + the
  `# [[stem|title]]` / `Feature lifecycle for [[stem]].` body on Shape A, frontmatter-only on Shape B.
  `tests/test_create_index.py` pins `GOLDEN_A`/`GOLDEN_B` byte strings; suite green (19 passed incl. start-sync).
  pyproject entry present at line 55, alphabetized between `-counters` and `-dispatch-choice`.
- **Verdict**: PASS

### Requirement 2: index.md field forms match the two real consumers + pinned canonical style
- **Expected**: bare unquoted `null` for absent uuid/id; unquoted inline `tags: [a, b]` parseable by
  `_extract_tags`; date-only `created`/`updated`. Golden asserts the literal `parent_backlog_uuid: null`,
  the unquoted tags round-trip, and `^\d{4}-\d{2}-\d{2}$`.
- **Actual**: `_render` emits `uuid_val = uuid if uuid else "null"` (bare) and `_render_tags` produces the
  unquoted flow form. `test_shape_a_missing_uuid_emits_bare_null` asserts `parent_backlog_uuid: null\n`
  present and `"null"` (quoted) absent; the tags assertion calls the **real** imported
  `load_requirements_cli._extract_tags` and round-trips `["lifecycle", "cli-verbs"]`; date assertion holds.
  Confirmed the bare-`null` coupling is load-bearing: `wontfix_cli._read_backlog_target` treats a value as a
  live terminalization target only when `value.lower() != "null"`, so a quoted `"null"` would mis-route.
- **Verdict**: PASS

### Requirement 3: create-index idempotent via structural skip-if-exists guard
- **Expected**: If index.md exists, no write + no-op signal; file byte-identical after the call.
- **Actual**: `create_index()` returns `{"signal":"skipped",...}` before any write when `target.exists()`.
  `test_skip_if_exists_preserves_bytes` writes a sentinel, runs, asserts byte-identical + `skipped` signal.
- **Verdict**: PASS

### Requirement 4: create-index uses an injectable date-only seam
- **Expected**: Local `_today()` returning `YYYY-MM-DD` (not `_now_iso`'s `…T..:..:..Z`), monkeypatched.
- **Actual**: `def _today()` at create_index.py:63 returns `datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")`;
  defined locally (no `_now_iso` import); test fixture `_frozen_today` monkeypatches it. `grep def _today` = 1 line.
- **Verdict**: PASS

### Requirement 5: create-index write-root matches the backlog write tree (no worktree split)
- **Expected**: Resolve via `_resolve_user_project_root` (CORTEX_REPO_ROOT-honoring), NOT
  `_resolve_user_project_root_from_cwd`; write lands under env-root tree when env ≠ CWD.
- **Actual**: `main()` calls `_resolve_user_project_root()`. `test_env_root_precedence_over_cwd` sets
  `CORTEX_REPO_ROOT` to a different tree than CWD and asserts the write lands under env-root and NOT under CWD.
- **Verdict**: PASS

### Requirement 6: `discovery-bootstrap.md` creation block replaced by a verb invocation
- **Expected**: Template/wikilink prose → a single full-flag invocation; skip-if-exists pointer + consume-Step-1
  invariant + epic guidance remain terse. `grep -c create-index` = 1; 7-field enumeration removed.
- **Actual**: `grep -c cortex-lifecycle-create-index` = 1; `grep -c parent_backlog_uuid` = 0 (template prose
  gone). The skip-if-exists pointer, "do not re-scan / consume Step 1's `{backlog-file}`" invariant, and the
  Epic Research Detection / Context Injection / Refine Starting-Point sections survive unchanged. File shrank
  by 34 lines.
- **Verdict**: PASS

### Requirement 7: `cortex-lifecycle-start-sync` owns the lifecycle-start write-backs only
- **Expected**: New `start_sync.py` + script entry; 5 required flags; runs `cortex-update-item <ref>
  --status in_progress --session-id <id> --lifecycle-phase research` and, when `phase==none`, additionally
  `--lifecycle-slug <slug>`. Exact argv pinned per phase; `pytest` exits 0.
- **Actual**: `sync()` runs the status call always (on `cortex-backlog`) and the slug call only on `phase=="none"`.
  `test_cortex_backlog_phase_none_emits_both_calls` pins the EXACT ordered argv `[STATUS_CALL, SLUG_CALL]`;
  `test_cortex_backlog_non_none_phase_status_only` pins status-only. Positional is `Path(backlog_file).stem`
  (`326-foo`), preserving the historic invocation. pyproject entry at line 61, alphabetized.
- **Verdict**: PASS

### Requirement 8: Backend routing follows ADR-0019 (caller-passed `--backend`, structural-guard skip, no adapter logic)
- **Expected**: Verb routes on passed `--backend`, never self-resolves; `cortex-backlog` runs writes; `none`
  skips + advisory; external skips local + advisory, no `gh`/`needs_agent` payload. Three arms + negative controls.
- **Actual**: `sync()` branches only on the passed `backend`; no `resolve_backlog_backend` import, no `gh`/
  `needs_agent` token (the docstring `gh ` hits are false positives inside "passthrough"). Tests cover all
  three arms: `cortex-backlog` (calls run), `none` (`calls == []`, `skipped`), external/`github`
  (`calls == []`, `external`), plus the empty-`--backlog-file` zero-call arm; each carries a zero-call negative
  control. The external-arm return is a fixed literal with only `signal`/`backend`/`note` — no adapter payload
  is structurally possible.
- **Verdict**: PASS

### Requirement 9: exit-2 ambiguous-slug passthrough preserved
- **Expected**: A `cortex-update-item` exit 2 → re-emit candidate stderr, return 2.
- **Actual**: `_update_item` raises `_Exit2` on `returncode == 2` after writing the child stderr; `main` catches
  and returns 2 with no stdout. `test_exit2_passthrough_returns_2_and_surfaces_candidates` asserts `rc == 2`,
  the candidate list on stderr, and empty stdout.
- **Verdict**: PASS

### Requirement 10: only "Backlog Write-Back (Lifecycle Start)" thinned; cross-ref canonical blocks survive
- **Expected**: Discriminating greps on the **target** file: `Exit-2 Handling (canonical)` = 1,
  `Registering an Artifact in index.md (canonical)` = 1, `cortex-lifecycle-start-sync` = 1.
- **Actual**: All three greps = 1. The Backlog Status Check section (Close/Continue `AskUserQuestion` kept-pause),
  the Exit-2 canonical heading + rule, and the Registering-an-Artifact canonical block are intact. The stale
  "three `cortex-update-item` write-backs below" enumeration is reconciled (grep = 0) — the top routing block
  now describes the close-lifecycle inline write-back + points to `start-sync --backend` for the lifecycle-start
  writes; the Exit-2 block re-enumerates call sites to include the verb. The close path retains its current
  event-first order (Non-Requirements honored).
- **Verdict**: PASS

### Requirement 11: new verb prose invocations satisfy `cortex-check-contract`
- **Expected**: Every invocation written in full with all required flags; contract gate exits 0.
- **Actual**: Both prose invocations carry all required flags (create-index: `--feature`/`--backlog-file`;
  start-sync: all five). All parser args are `required=True`. `cortex-check-contract --audit` (editable venv)
  exits 0.
- **Verdict**: PASS

### Requirement 12: console-script registration + prose invocation in the same commit (W003)
- **Expected**: pyproject script + prose co-committed; `cortex-check-parity` exits 0 (no W003 orphan).
- **Actual**: `fad82d13` bundles create_index.py + test + pyproject entry + canonical & mirror
  discovery-bootstrap together; `10f62b6d` bundles start_sync.py + test + pyproject entry + canonical & mirror
  backlog-writeback + ADR. `cortex-check-parity` exits 0.
- **Verdict**: PASS

### Requirement 13: mirrors regenerated and committed with canonical edits
- **Expected**: `plugins/cortex-core/skills/lifecycle/` mirror regenerated; canonical ↔ mirror identical.
- **Actual**: `diff -q` reports both `discovery-bootstrap.md` and `backlog-writeback.md` byte-identical to their
  mirrors; both mirrors are in the respective commits.
- **Verdict**: PASS

### High-risk areas (critical-review surfaced)
1. **`--backlog-file` basename A-fix**: `create_index` locates the ticket via
   `root / "cortex" / "backlog" / Path(backlog_file).name` (create_index.py:167), never `root / backlog_file`.
   A non-empty-but-absent file raises `OSError` from `_parse_frontmatter`, caught in `main` → `return 1`
   (no silent Shape-B fallback). Case (e) `test_basename_input_located_via_canonical_dir` places the ticket ONLY
   at the canonical dir and passes a bare basename — a `root / backlog_file` regression would miss it. Case (f)
   `test_nonempty_missing_backlog_file_returns_1` asserts `rc == 1`, the basename on stderr, and no index.md
   written. Both discriminate. **Verified.**
2. **Byte-faithful template**: bare `null`, unquoted inline `tags` round-tripping through the real
   `_extract_tags`, date-only dates, `CORTEX_REPO_ROOT` precedence — all confirmed (Reqs 2 & 5). **Verified.**
3. **start_sync ADR-0019 guard**: acts on `--backend`, never self-resolves; status-always + slug-on-`none`;
   `none`/external make zero local calls; exit-2 → 2 with stderr; positional = `.stem`. **Verified.**
4. **Prose offload fidelity**: full-flag invocations, no leftover template/routing prose, kept blocks intact,
   stale enumerations reconciled. **Verified.**
5. **No MUST-escalation added**: `grep -E 'MUST|CRITICAL|REQUIRED'` returns none in both thinned files;
   the offload smuggled in no new imperative escalation. **Verified.**

## Stage 2: Code Quality
- **Naming conventions**: Consistent with siblings — modules `create_index.py`/`start_sync.py` map to console
  scripts `cortex-lifecycle-create-index`/`-start-sync`, matching `stage_artifacts.py` → `-stage-artifacts`.
  Helpers (`_render`, `_render_tags`, `_atomic_write`, `_today`, `_update_item`, `_Exit2`, `sync`) are
  clear and idiomatic.
- **Error handling**: `create_index` clones the `try/except CortexProjectRootError → return 1` arm and adds an
  `OSError → return 1` diagnostic for the absent-ticket contract violation; `_atomic_write` cleans up its temp
  file on any `BaseException`. `start_sync` honestly omits the `CortexProjectRootError` arm because it resolves
  no project root (shells `cortex-update-item` only) — the deviation is documented in the module docstring and
  the plan's Risks, and is structural, not a gap. Non-exit-2 child returncodes are swallowed best-effort,
  matching the historic prose's non-halting write-back. Appropriate.
- **Test coverage**: Strong discriminating power. create-index: golden bytes for both shapes, a quoted-`null`
  negative control, a quoted-tags negative control, a **real** `_extract_tags` round-trip (genuine downstream
  coupling, not a self-assertion), the env-root precedence test, and the (e)/(f) A-fix regression pair.
  start-sync: exact ordered-argv pinning per arm, a zero-call negative control per non-writing arm, a
  no-`--lifecycle-slug` control on the non-`none` phase, exit-2 passthrough, a parametrized all-five-required
  check, and the compact-JSON contract. No tautologies. Suite green: `pytest test_create_index test_start_sync`
  = 19 passed; kept-pauses + event-roundtrip parity = 35 passed.
- **Pattern consistency**: Both verbs follow the console-script-only shape — compact JSON
  `json.dumps(..., separators=(",", ":")) + "\n"`, thin `main(argv) -> int`, `if __name__` guard. Both place
  `_telemetry.log_invocation(...)` as the first line of `main` per the spec's Technical Constraints (a positive
  deviation from the literal `stage_artifacts` skeleton, which omits telemetry). No `bin/` wrapper or mirror —
  `cortex_command/*.py` ships in the wheel.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
