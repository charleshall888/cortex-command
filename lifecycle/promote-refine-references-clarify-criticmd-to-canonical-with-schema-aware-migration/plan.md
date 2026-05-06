# Plan: promote-refine-references-clarify-criticmd-to-canonical-with-schema-aware-migration

## Overview

Land schema_version + JSONL emission contract + Python legacy-tolerance + replay fixtures additively first, then a single migration commit that rewires §3a (with depth-correct cross-skill path), updates one live doc reference, deletes the legacy lifecycle copy, and stages the auto-rebuilt plugin mirror so both deletions appear in the same commit. Pre-migration tasks make the canonical version safe to depend on; the migration commit collapses the duplication atomically per R13. The pre-commit drift hook is a parity REJECTOR, not an auto-stager — Task 6 explicitly invokes `just build-plugin && git add plugins/cortex-core/` before commit so Phase 4's `git diff --quiet -- plugins/$p/` check sees a clean working-tree-vs-index match.

## Tasks

### Task 1: Edit canonical clarify-critic.md — schema_version, JSONL example, v1.5 enumeration, producer-prose alignment

- **Files**: `skills/refine/references/clarify-critic.md`
- **What**: (a) Add `schema_version` field to required-fields prose (SHOULD on producer; readers MUST tolerate absence as v1); (b) replace the multi-line YAML example block with a single-line JSONL example that includes `schema_version: 2`; (c) document the JSONL-emission requirement in `## Event Logging`; (d) enumerate the three pre-v2 shapes (minimal v1, v1+dismissals, YAML-block on-disk) in the legacy-tolerance prose; (e) align the `## Dispositioning` directives at lines 113–116 to refer to JSONL emission (replace "YAML payload" / "YAML artifact" / "writes this YAML **verbatim**" with the equivalent JSONL phrasings); (f) update the example header at line ~163 from "Example (YAML block format, same as other lifecycle events):" to "Example (single-line JSONL, written verbatim by the orchestrator):". After this task the canonical reference is internally consistent — `## Event Logging` and `## Dispositioning` agree on JSONL.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `## Event Logging` section spans roughly lines 128–193 of the file. Field list at line ~138; example block at lines ~166–193; legacy-tolerance prose at line ~157; example header at line ~163. `## Dispositioning` section's load-bearing producer directives are at lines 113–116 — verbatim today: "After classifying every objection, the dispositioning step produces one structured artifact and nothing else. That artifact is the `clarify_critic` event itself — a YAML payload matching the schema defined in `## Event Logging` below, including the `dismissals` array. ... The **sole output** of the dispositioning step is the structured YAML artifact. It is not free-form prose. The orchestrator writes this YAML **verbatim** to `lifecycle/{feature}/events.log` as the `clarify_critic` event." Replace "YAML payload" → "single-line JSONL payload"; "structured YAML artifact" → "structured single-line JSONL artifact"; "writes this YAML **verbatim**" → "writes this single-line JSON object **verbatim**". The new schema_version field is phrased as `schema_version: <int>  # 2 for current schema; readers MUST tolerate absence as v1` (positive routing, OQ3-grandfather-compliant per spec Decisions §3 and CLAUDE.md OQ3 policy). The JSONL example mirrors the structural pattern of `skills/lifecycle/references/plan.md:138`'s `plan_comparison` v2 example — a single-line JSON object beginning `{"ts": ...,"event": "clarify_critic", ...}`. A "structural breakdown" YAML rendering may be retained inline as documentation but the primary, structurally-dominant example is JSONL. The three pre-v2 shapes are described by behavioral effect, not version label, using the literal tokens "minimal v1", "v1+dismissals", and "YAML-block".
- **Verification**:
  - `grep -c 'schema_version' skills/refine/references/clarify-critic.md` ≥ 3 — pass if count ≥ 3 (R4)
  - `grep -q 'single-line JSON' skills/refine/references/clarify-critic.md` — pass if exit 0 (R9.a)
  - `python3 -c "import re; t=open('skills/refine/references/clarify-critic.md').read(); m=re.search(r'## Event Logging.*?(?=^## )', t, re.DOTALL|re.MULTILINE); assert any(line.strip().startswith('{') and '\"event\":' in line and '\"clarify_critic\"' in line for line in m.group().splitlines()), 'no inline single-line JSON clarify_critic example'"` — pass if exit 0 (R9.b)
  - `grep -q 'minimal v1' skills/refine/references/clarify-critic.md && grep -q 'v1+dismissals' skills/refine/references/clarify-critic.md && grep -q 'YAML-block' skills/refine/references/clarify-critic.md` — pass if exit 0 (R10)
  - `! grep -q 'writes this YAML \*\*verbatim\*\*' skills/refine/references/clarify-critic.md` — pass if exit 0 (`## Dispositioning` legacy YAML directive removed)
  - `grep -q 'writes this single-line JSON object \*\*verbatim\*\*' skills/refine/references/clarify-critic.md` — pass if exit 0 (`## Dispositioning` JSONL directive present)
  - `! grep -q '^Example (YAML block format' skills/refine/references/clarify-critic.md` — pass if exit 0 (legacy YAML example header removed)
- **Status**: [ ] pending

### Task 2: Create v1 replay fixture and provenance

- **Files**: `tests/fixtures/clarify_critic_v1.json` (NEW), `tests/fixtures/clarify_critic_v1.json.provenance` (NEW)
- **What**: Pin a v1 clarify_critic event as the test fixture (decoupled from live-archive churn) and document its provenance in a sibling markdown-comment file.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Source line is `lifecycle/archive/define-output-floors-for-interactive-approval-and-overnight-compaction/events.log:2` — a ~1074-byte single-line JSONL clarify_critic event with bare-string findings (length 4), no `parent_epic_loaded`, no `dismissals`. Copy the exact line content (a single line of JSON) into `clarify_critic_v1.json`. The provenance file is a single-line markdown comment of the form `Source: lifecycle/archive/define-output-floors-for-interactive-approval-and-overnight-compaction/events.log:2 — pre-feature v1 clarify_critic event (bare-string findings, no parent_epic_loaded, no dismissals).` (token "define-output-floors" must appear so R7's grep passes).
- **Verification**:
  - `test -f tests/fixtures/clarify_critic_v1.json` — pass if exit 0 (R7)
  - `test -f tests/fixtures/clarify_critic_v1.json.provenance && grep -q 'define-output-floors' tests/fixtures/clarify_critic_v1.json.provenance` — pass if exit 0 (R7)
  - `python3 -c "import json; e=json.loads(open('tests/fixtures/clarify_critic_v1.json').read()); assert e.get('event')=='clarify_critic'; assert isinstance(e.get('findings'), list); assert all(isinstance(f, str) for f in e['findings']); assert 'parent_epic_loaded' not in e"` — pass if exit 0 (fixture is structurally a v1 event)
- **Status**: [ ] pending

### Task 3: Add `_normalize_clarify_critic_event` helper and rewire `check_invariant`

- **Files**: `tests/test_clarify_critic_alignment_integration.py`
- **What**: Add the legacy-tolerance normalizer as a sibling helper and route `check_invariant` through it so it stops crashing on bare-string findings.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: `check_invariant` lives at lines 192–204 of the test file. Helper signature: `def _normalize_clarify_critic_event(evt: dict) -> dict`. Per R5 the helper applies three field-level normalizations: `schema_version` defaults to 1 when absent; `parent_epic_loaded` defaults to `False` when absent; each item in `findings` that is a `str` is wrapped as `{"text": <str>, "origin": "primary"}` while `dict` items pass through unchanged. Hybrid lists (mix of `str` and `dict`) are normalized per-element. Per the Edge Cases section, a finding that is neither `str` nor `dict` raises `TypeError` with a message identifying the offending item type. `check_invariant` should call the normalizer at the top of its body before iterating findings, so existing synthetic-dict callers continue to work and real archived bare-string events stop crashing.
- **Verification**:
  - `grep -c '_normalize_clarify_critic_event' tests/test_clarify_critic_alignment_integration.py` ≥ 2 — pass if count ≥ 2 (definition + ≥1 call site, R5)
  - `python3 -c "import sys; sys.path.insert(0, 'tests'); from test_clarify_critic_alignment_integration import check_invariant, _normalize_clarify_critic_event; import json; evt = json.loads(open('tests/fixtures/clarify_critic_v1.json').read()); assert check_invariant(_normalize_clarify_critic_event(evt)) is True"` — pass if exit 0 (R6)
- **Status**: [ ] pending

### Task 4: Add v1 replay test

- **Files**: `tests/test_clarify_critic_alignment_integration.py`
- **What**: Add `test_clarify_critic_v1_replay_invariant` that loads the pinned fixture, applies the normalizer, and asserts the legacy-tolerance contract holds.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**: Test name carries `_v1_` per spec Edge Cases (a future v2 corpus gets a sibling `_v2_` test). Fixture path resolved via `pathlib.Path(__file__).parent / "fixtures" / "clarify_critic_v1.json"`. Per R8 the test asserts: (a) `schema_version == 1` post-normalization, (b) `parent_epic_loaded is False` post-normalization, (c) every item in `findings` is a `dict` with keys `text` (str) and `origin` (str), (d) every `origin` value is `"primary"` (no alignment findings in v1), (e) `check_invariant(normalized_evt) is True`.
- **Verification**:
  - `pytest tests/test_clarify_critic_alignment_integration.py::test_clarify_critic_v1_replay_invariant -x` — pass if exit 0 (R8)
- **Status**: [ ] pending

### Task 5: Create migration cutoff fixture and add post-migration JSONL emission check test

- **Files**: `tests/fixtures/jsonl_emission_cutoff.txt` (NEW), `tests/test_clarify_critic_alignment_integration.py`
- **What**: Record the migration cutoff (single ISO-8601 line) and add `test_post_migration_clarify_critic_events_are_jsonl`, which walks active `lifecycle/*/events.log` (excluding `lifecycle/archive/`) and asserts that any post-cutoff `clarify_critic` event is a single-line JSON object — never a YAML-block event.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: The cutoff fixture is a single ISO-8601 timestamp line. To avoid retroactively binding pre-existing on-disk YAML-block clarify_critic events, the implementer MUST record a cutoff strictly later than the maximum `ts` of any pre-existing `clarify_critic` event in active `lifecycle/*/events.log` trees. Capture `now_utc()` and verify `cutoff > max(existing_clarify_critic_ts)` before writing the file; if `now_utc()` is not strictly later, advance by 1 second.

  **Test parsing strategy — regex line-scan, NOT `yaml.safe_load_all`.** The live events.log files mix JSONL and YAML-block events with no document separator (this lifecycle's own events.log has YAML lines 1–41 immediately followed by JSONL line 42). `yaml.safe_load_all` raises `ScannerError` on the JSONL line because YAML cannot consume `{...}` as a flow-mapping document with no preceding `---`. The test instead uses a pure regex line-scan:

  1. Compile two regexes: `JSONL_RE = re.compile(r'^\{.*"event"\s*:\s*"clarify_critic".*\}\s*$')` for one-line JSONL events, and `YAML_HEAD_RE = re.compile(r'^- ts:\s*([0-9T:Z+-]+)\s*$')` for YAML-block headers.
  2. For each `events.log` under `Path("lifecycle").glob("*/events.log")` whose path-parts do NOT include `archive`:
     - Read all lines.
     - For each line `i`:
       - If `JSONL_RE.match(line)`: `evt = json.loads(line)`; if `evt["event"] == "clarify_critic"`, parse `evt["ts"]` as ISO-8601 and compare to cutoff.
       - Elif `YAML_HEAD_RE.match(line)`: extract candidate `ts` from the regex group; look ahead up to 5 lines for a line matching `^\s+event:\s*clarify_critic\s*$`. If found, this is a YAML-block clarify_critic event with the candidate `ts`. Parse `ts` and compare to cutoff.
  3. Both branches normalize `ts` through the same helper: `def _parse_ts(s: str) -> datetime: return datetime.fromisoformat(s.replace("Z", "+00:00"))`. The helper accepts only strings — both regex branches yield strings, so types are uniform.
  4. **Failure assertion (R14)**: collect all `(file, line_number, ts)` tuples where the event was YAML-block AND `ts >= cutoff`. The test asserts this list is empty with a clear failure message naming each offending file and line number.
  5. **Positive-control assertion** (defends against silent-parse-skip regressions): the test counts the total number of `clarify_critic` events successfully detected (both pre- and post-cutoff, both formats). In the development tree where this plan ships, ≥1 detection is expected (this lifecycle's own pre-cutoff YAML-block event). The assertion is conditional: `if Path("lifecycle/<this-feature>/events.log").exists(): assert detections >= 1`. In a fresh-clone CI tree with no events.log files, the detections-≥-1 check is bypassed; the YAML-block-violation list is asserted empty unconditionally.

  No `yaml` library import is needed. Note: the spec's Decisions §1 places the normalizer in `tests/` for now; promotion to `cortex_command/` is the named follow-up at backlog #186 (out of scope).
- **Verification**:
  - `test -f tests/fixtures/jsonl_emission_cutoff.txt && python3 -c "from datetime import datetime; datetime.fromisoformat(open('tests/fixtures/jsonl_emission_cutoff.txt').read().strip().replace('Z','+00:00'))"` — pass if exit 0 (cutoff file is a valid ISO-8601 line)
  - `python3 -c "from datetime import datetime, timezone; from pathlib import Path; import re,json; cutoff=datetime.fromisoformat(open('tests/fixtures/jsonl_emission_cutoff.txt').read().strip().replace('Z','+00:00')); JR=re.compile(r'^- ts:\s*([0-9T:Z+-]+)\s*$'); maxts=None; [maxts := (ts if (maxts is None or ts>maxts) else maxts) for p in Path('lifecycle').glob('*/events.log') if 'archive' not in p.parts for i,line in enumerate(p.read_text().splitlines()) for m in [JR.match(line)] if m for la in p.read_text().splitlines()[i+1:i+6] if re.match(r'^\s+event:\s*clarify_critic\s*$', la) for ts in [datetime.fromisoformat(m.group(1).replace('Z','+00:00'))]]; assert maxts is None or cutoff > maxts, f'cutoff {cutoff} not strictly greater than max existing clarify_critic ts {maxts}'"` — pass if exit 0 (cutoff > max-existing-ts invariant)
  - `pytest tests/test_clarify_critic_alignment_integration.py::test_post_migration_clarify_critic_events_are_jsonl -x` — pass if exit 0 (R14)
- **Status**: [ ] pending

### Task 6: Migration commit — §3a rewire (depth-correct), live-doc update, legacy delete, plugin mirror staged-rebuild

- **Files**:
  - `skills/lifecycle/references/clarify.md` (edit line 55)
  - `skills/lifecycle/references/clarify-critic.md` (delete)
  - `docs/internals/sdk.md` (edit line 23)
  - `plugins/cortex-core/skills/lifecycle/references/clarify-critic.md` (deleted via `just build-plugin` rsync `--delete`, then explicitly staged)
  - `plugins/cortex-core/skills/lifecycle/references/clarify.md` (rebuilt via `just build-plugin`, then explicitly staged)
  - `cortex_command/overnight/events.py` (NOT touched — verified by R11)
- **What**: Land all duplication-collapsing changes in a single commit by composing the manual edits, then invoking `just build-plugin` to rebuild the plugin mirror tree, then staging the rebuilt plugin tree, then committing. The pre-commit hook's Phase 4 is a parity REJECTOR (verified at `.githooks/pre-commit:180-203`: `git diff --quiet -- plugins/$p/` exits 1 if working-tree-vs-index drift exists) — it does NOT auto-stage. Manual `git add plugins/cortex-core/` is the canonical workflow, not a recovery footnote.
- **Depends on**: [1, 3, 4, 5]
- **Complexity**: simple
- **Context**:
  - **Path depth correction**: `skills/lifecycle/references/clarify.md` is two directory levels below `skills/`. From that file, `../` resolves to `skills/lifecycle/`, NOT `skills/`. The correct cross-skill relative path to `skills/refine/references/clarify-critic.md` requires TWO `..` segments: `../../refine/references/clarify-critic.md`. The 5 instances at `skills/refine/SKILL.md:39, 66, 87, 157, 164` use single `..` because that file is one level below `skills/` — they are NOT direct precedent for the depth needed here. Of those 5, only 3 (lines 39, 66, 87) use the bare `..` form; the other 2 use `${CLAUDE_SKILL_DIR}/..` (env-var-anchored) which is a different resolution mechanism.
  - `skills/lifecycle/references/clarify.md:55` reads `Read \`references/clarify-critic.md\` and follow its protocol.` — change to `Read \`../../refine/references/clarify-critic.md\` and follow its protocol.` Verify resolution from the citing-file's directory: `cd skills/lifecycle/references && ls ../../refine/references/clarify-critic.md` must exit 0.
  - `docs/internals/sdk.md:23` table row currently lists `skills/lifecycle/references/clarify-critic.md` — update to `skills/refine/references/clarify-critic.md`.
  - **Canonical commit composition** (this is the happy path, not a recovery procedure):
    1. Edit `skills/lifecycle/references/clarify.md:55` (depth-correct path).
    2. Edit `docs/internals/sdk.md:23` (canonical path).
    3. `git rm skills/lifecycle/references/clarify-critic.md` (stages legacy delete).
    4. `just build-plugin` (mutates `plugins/cortex-core/` to match the canonical tree; rsync `--delete` removes the plugin-mirror legacy file from working tree).
    5. `git add plugins/cortex-core/` (stages the auto-rebuilt plugin tree, including the deletion of the plugin-mirror legacy file and the rebuilt `clarify.md` mirror).
    6. `git add docs/internals/sdk.md skills/lifecycle/references/clarify.md` (stages the manual edits).
    7. Commit. Pre-commit hook Phase 3 re-runs `just build-plugin` (idempotent), Phase 4 finds zero working-tree-vs-index drift (because step 5 staged everything), commit succeeds.
  - `cortex_command/overnight/events.py` MUST NOT be modified — `clarify_critic` is intentionally absent from `EVENT_TYPES` (R11; spec §Non-Requirements §2).
  - Caller enumeration confirmed live (excluding archives, backlog, lifecycle artifacts, plugin auto-mirror): `skills/lifecycle/references/clarify.md`, `docs/internals/sdk.md`. Other matches are in `lifecycle/archive/`, `lifecycle/<other-feature>/{plan,research,spec,review,index}.md`, `backlog/`, and `research/archive/` and `research/vertical-planning/` — those are historical or planning artifacts and are deliberately not edited (see Veto Surface).
- **Verification**:
  - `test ! -f skills/lifecycle/references/clarify-critic.md` — pass if exit 0 (R1)
  - `test ! -f plugins/cortex-core/skills/lifecycle/references/clarify-critic.md` — pass if exit 0 (R2)
  - `[ "$(grep -c '\.\./\.\./refine/references/clarify-critic\.md' skills/lifecycle/references/clarify.md)" = "1" ]` — pass if exit 0 (R3, depth-correct double-`..` form)
  - `[ "$(grep -cE '(^|[^.])\.\./refine/references/clarify-critic\.md' skills/lifecycle/references/clarify.md)" = "0" ]` — pass if exit 0 (single-`..` broken form is absent — depth-bug regression guard)
  - `[ "$(grep -c 'skills/lifecycle/references/clarify-critic\.md' docs/internals/sdk.md)" = "0" ] && grep -q 'skills/refine/references/clarify-critic\.md' docs/internals/sdk.md` — pass if exit 0 (live doc updated; no broken path remains)
  - `[ "$(git show --name-status HEAD -- 'skills/lifecycle/references/clarify-critic.md' 'plugins/cortex-core/skills/lifecycle/references/clarify-critic.md' | grep -c '^D')" = "2" ]` — pass if exit 0 (R13)
  - `[ -z "$(git show --name-status HEAD -- cortex_command/overnight/events.py)" ]` — pass if exit 0 (R11)
- **Status**: [ ] pending

### Task 7: Final integration verification — full test file passes

- **Files**: `tests/test_clarify_critic_alignment_integration.py` (read-only execution)
- **What**: Confirm that all tests in the integration file (existing + the three new tests added in Tasks 3–5) pass after the migration commit lands.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: This is the R12 acceptance gate. No file modifications. If failure occurs, diagnose the failing test and fix forward — do not revert prior tasks.
- **Verification**:
  - `pytest tests/test_clarify_critic_alignment_integration.py -x` — pass if exit 0 (R12)
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification combines all 14 acceptance checks from spec §Requirements:

1. **Schema markdown is updated** (R4, R9, R10): Task 1 verification covers `schema_version` count, `single-line JSON` token, inline JSONL clarify_critic example, and the three pre-v2 shape tokens.
2. **Replay scaffolding is in place** (R5, R6, R7, R8): Tasks 2–4 verifications cover normalizer existence and call-through, fixture file presence and provenance grep, and v1 replay test exit code.
3. **Producer-side JSONL contract binds going forward, with positive control** (R14): Task 5 verification runs the post-migration emission check, asserts cutoff strictly exceeds max pre-existing ts, and includes a positive-control detection-count assertion to guard against silent parse-skip regressions.
4. **Migration is atomic and depth-correct** (R1, R2, R3, R11, R13): Task 6 verification asserts both deletions in HEAD's `--name-status`, confirms the §3a path is the depth-correct double-`..` form (with explicit single-`..` regression guard), confirms `events.py` is untouched, and confirms `docs/internals/sdk.md` no longer references the legacy path.
5. **Existing test surface remains green** (R12): Task 7 runs the full integration file.

After Task 7 passes, all 14 acceptance criteria from spec §Requirements are satisfied.

## Veto Surface

- **Migration cutoff timestamp written at Task 5 execution time, not at the migration commit time**: spec R14 says "at migration time." A literal reading would place the cutoff write inside Task 6. The plan's choice (T5) was made because T5's verification depends on the cutoff existing, but it broadens the binding window to include all pre-migration on-disk emissions. The cutoff > max-existing-ts invariant added to T5 prevents retroactive binding of pre-existing events; the remaining concern is concurrent emissions in unrelated lifecycles between T5 and T6 (judged low risk under the plan's implementer-window scope). Operator confirmed T5 placement during plan critical-review.
- **Live-doc update for `docs/internals/sdk.md:23` is added to Task 6 even though spec §Requirements does not enumerate it**: the spec's R3 names only `skills/lifecycle/references/clarify.md`. Plan reference §"Caller Enumeration" requires every live caller of a deleted file to be updated in the same task; `docs/internals/sdk.md:23` is the only other live reference outside of archive and lifecycle artifacts. Without this edit, that table row points to a deleted file. Veto if the spec's R-list is intended to be exhaustive on broken-reference repair (in which case file a follow-up ticket).
- **Archive housekeeping deferred**: `research/archive/claude-code-sdk-usage/research.md:42` cites the to-be-deleted file's line numbers. The Adversarial review flagged this as a "minor doc-rot vector" with "trim during this ticket as housekeeping," but spec §Requirements does not list it. The plan does NOT touch this file. Veto if archive housekeeping should be in scope (would add ~3 minutes to Task 6).
- **Producer-side normalizer remains in `tests/`**: per spec Decisions §1 and Non-Requirements §5, this is intentional — promotion to `cortex_command/` waits for backlog #186 to land a production consumer. Veto if the consumer landscape has changed since the spec was approved.
- **Cross-skill `..` reference in `clarify.md` §3a is added without a markdown link-validator**: spec §Technical Constraints calls this latent risk and out of scope. The depth-correct `../../` precedent does not yet exist elsewhere in the codebase; this is the first instance. Veto if a link-validator should be added in this ticket (would be a separate task; surfacing here in case scope policy has shifted).

## Scope Boundaries

Excluded from this feature (per spec §Non-Requirements):

- **Reformatting the 43 archived YAML-block clarify_critic events** to JSONL — they remain on-disk as text but invisible to `parse_events()`. Recommended follow-up ticket: "Backfill or re-archive the 43 YAML-block clarify_critic events for parse_events() visibility."
- **Migrating the producer to `record_event()`** (i.e., adding `clarify_critic` to `EVENT_TYPES` in `cortex_command/overnight/events.py`).
- **Runtime cross-field invariant validator and closed-allowlist warning template runtime enforcement** — covered by backlog #186.
- **Markdown link-validator pre-commit hook** for cross-skill `..` references — flag for follow-up.
- **Production-side normalizer in `cortex_command/`** — promotion gated by backlog #186.
- **Backporting `schema_version` to existing archived events** — frozen v1 events live forever per event-sourcing convention.
- **OQ3 evidence-gathering for promoting `schema_version` from SHOULD to MUST on the producer side** — phrased as SHOULD now; future producer-side regression triggers OQ3 evidence collection per CLAUDE.md OQ3 policy.
