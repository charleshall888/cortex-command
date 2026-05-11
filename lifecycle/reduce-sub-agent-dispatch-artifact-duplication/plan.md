# Plan: reduce-sub-agent-dispatch-artifact-duplication

## Overview

Replace inline `{artifact content}` / `{full contents of …}` injection at three dispatch sites (`skills/critical-review/SKILL.md`, `skills/lifecycle/references/plan.md`, `skills/lifecycle/references/review.md`) with `{artifact_path}` + `{artifact_sha256}` placeholders, plus a reviewer-side `READ_OK:` / synthesizer-side `SYNTH_READ_OK:` SHA sentinel pattern parsed by Step 2c.5. The orchestrator-side ceremony is collapsed into three atomic subprocess calls implemented in a new `cortex_command/critical_review.py` module: `prepare-dispatch` (fused path-validation + SHA computation, eliminating the validate→sha non-atomicity gap and Req 9's SEC-1 enforcement path), `verify-synth-output` (fused parse + diagnostic + `synthesizer_drift` event append, eliminating self-suppressing telemetry on the post-synthesis path), and `record-exclusion` (atomic `sentinel_absence` event append per excluded reviewer). Fast-path template-correctness coverage in `tests/test_dispatch_template_placeholders.py`; path-validation test in `tests/test_critical_review_path_validation.py` exercises BOTH the module API AND the CLI subprocess path; existing slow classifier test updated for new placeholders.

## Tasks

### Task 1: Add `cortex_command/critical_review.py` with three atomic CLI subcommands
- **Files**:
  - `cortex_command/critical_review.py` (new)
- **What**: Provide a Python module with three orchestrator-facing CLI subcommands that collapse the multi-step ceremony into atomic calls. Each subcommand combines validation + state mutation in one invocation so the orchestrator-LLM cannot perform half the ceremony; failures are observable via exit code and stderr.
  - `prepare-dispatch <path> [--feature <name>]` — validates the path (realpath equals abspath; Req 9c; strict path-component prefix of `{lifecycle_root}`; feature narrowing when supplied; Req 9a–b) AND computes SHA-256 of the file bytes in one call. On success: emits a single-line JSON object `{"resolved_path": "<realpath>", "sha256": "<hex>"}` to stdout, exit 0. On rejection: error to stderr, exit 2. **Atomicity guarantee**: the orchestrator-LLM cannot compute sha256 without first having `validate-path` run — the two operations are fused into one subprocess call.
  - `verify-synth-output --feature <name> --expected-sha <hex>` — reads the synthesizer's full output from stdin, parses for the line matching `^SYNTH_READ_OK: (\S+) ([0-9a-f]{64})$`. On match AND SHA equal to `--expected-sha`: prints `OK <sha>` to stdout, exit 0. On mismatch or absence: emits the top-level diagnostic `Critical-review pass invalidated: synthesizer SHA drift detected (expected <a>, got <b>); re-run after resolving concurrent write source.` (or `... synthesizer SYNTH_READ_OK sentinel absent; re-run after resolving concurrent write source.` on absence) to stdout, AND atomically appends a `synthesizer_drift` event to `{lifecycle_root}/{feature}/events.log` using tempfile + `os.replace` (not `open(...,'a')`), exit 3. This collapses 4 post-synthesis ceremony steps into one orchestrator call.
  - `record-exclusion --feature <name> --reviewer-angle <angle> --reason <absent|sha_mismatch|read_failed> --model-tier <haiku|sonnet|opus> --expected-sha <hex> [--observed-sha <hex>]` — atomically appends a `sentinel_absence` event to `{lifecycle_root}/{feature}/events.log` using the same tempfile + `os.replace` pattern. Exit 0. Used inside Step 2c.5 per excluded reviewer.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Module shape mirrors `cortex_command/common.py` style (callable as `python3 -m cortex_command.<name> <subcmd>`).
  - Public function signatures (still importable for tests):
    - `validate_artifact_path(candidate: str, lifecycle_root: str, feature: str | None = None) -> str` — returns realpath; raises `ValueError`.
    - `sha256_of_path(path: str) -> str` — hex digest.
    - `prepare_dispatch(candidate: str, lifecycle_root: str, feature: str | None = None) -> dict` — composes the two above; returns `{"resolved_path", "sha256"}`.
    - `verify_synth_output(output: str, expected_sha: str) -> tuple[str, str | None]` — returns `("ok", sha)` or `("absent", None)` or `("mismatch", observed_sha)`.
    - `append_event(events_log_path: Path, event: dict) -> None` — tempfile + `os.replace` rename; safe under concurrent emitters because the rename is atomic and the temp file is unique per-call.
    - `main(argv: list[str]) -> int` — argparse with three subcommands above.
  - `Path.is_relative_to()` for prefix check; strict-prefix rule rejects candidate equal to `lifecycle_root` itself.
  - Default `lifecycle_root` for CLI: resolved from `git rev-parse --show-toplevel` joined with `lifecycle/`. CLI passes `--feature` for auto-trigger flows; omitted for `<path>`-arg flows.
  - `append_event` uses `tempfile.NamedTemporaryFile(dir=str(events_log_path.parent), delete=False)`, writes existing log contents + new JSONL line, then `os.replace(tmp, final)`. This matches the SKILL.md:316–344 residue-write pattern and provides true atomic append semantics that `open(path, 'a')` does not.
  - The events.log schemas (matching Req 12 spec):
    - `{"ts":"<ISO 8601>","event":"sentinel_absence","feature":"<name>","reviewer_angle":"<angle>","reason":"absent|sha_mismatch|read_failed","model_tier":"haiku|sonnet|opus","expected_sha":"<hex>","observed_sha_or_null":"<hex>|null"}`
    - `{"ts":"<ISO 8601>","event":"synthesizer_drift","feature":"<name>","expected_sha":"<hex>","observed_sha_or_null":"<hex>|null"}`
- **Verification**:
  - `python3 -m cortex_command.critical_review --help` — pass if exit 0 and stdout mentions `prepare-dispatch`, `verify-synth-output`, `record-exclusion`.
  - `python3 -m cortex_command.critical_review prepare-dispatch <a-known-valid-lifecycle-file>` — pass if exit 0 and stdout is single-line JSON with `resolved_path` and `sha256` keys.
- **Status**: [ ] pending

### Task 2: Add fast-path template-correctness unit test
- **Files**:
  - `tests/test_dispatch_template_placeholders.py` (new)
- **What**: Pure string-assertion test (non-`@pytest.mark.slow`, no live model calls) asserting Req 10's four properties across the three canonical templates: (a) `{artifact content}` absent from `skills/critical-review/SKILL.md`; `{full contents of lifecycle/{feature}/spec.md}` and `{full contents of lifecycle/{feature}/research.md}` absent from `skills/lifecycle/references/plan.md`; `{contents of lifecycle/{feature}/spec.md, or a summary with a path to read it}` absent from `skills/lifecycle/references/review.md`. (b) `{artifact_path}` and `{artifact_sha256}` present ≥3× in critical-review; `{spec_path}` and `{research_path}` present in lifecycle plan.md; `{spec_path}` present in lifecycle review.md. (c) Reviewer prompt sections in critical-review SKILL.md contain the verbatim directive `READ_OK: <path> <sha>` (sentinel format). (d) Synthesizer prompt section contains `SYNTH_READ_OK: <path> <sha>` verbatim.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Test reads templates from canonical sources at `skills/`, NOT from `plugins/cortex-core/skills/` mirrors.
  - Resolve `REPO_ROOT` via `Path(__file__).resolve().parents[1]`.
  - Group assertions by Requirement number in a docstring or comment header so future readers can map test failures to spec requirements.
  - This test runs BEFORE Tasks 4–10 land — it will initially fail. That is expected and load-bearing: it serves as the spec-encoded checklist driving the template edits.
- **Verification**: `just test tests/test_dispatch_template_placeholders.py` — pass if exit 0 after Tasks 4–10 land. AND `grep -c '@pytest.mark.slow' tests/test_dispatch_template_placeholders.py` = 0 — pass if 0 (Req 10 acceptance).
- **Status**: [ ] pending

### Task 3: Add path-validation test exercising module API AND CLI subprocess paths
- **Files**:
  - `tests/test_critical_review_path_validation.py` (new)
- **What**: Non-slow test covering Req 9 at TWO layers: (1) module API: (a) symlink rejection — construct temp `lifecycle/foo/` with a symlink to `/etc/hostname`, invoke `validate_artifact_path(symlink_path, lifecycle_root)`, assert `ValueError` with a message naming the symlink path and realpath target (Req 9d); (b) path outside `lifecycle/` rejected with message naming allowed prefix; (c) feature-narrowing — path under `lifecycle/foo/` accepted with `feature='foo'`, rejected with `feature='bar'`; (d) path equal to `lifecycle_root` rejected (strict prefix); (e) valid path returns realpath. (2) CLI subprocess: (f) invoke `python3 -m cortex_command.critical_review prepare-dispatch <symlink-path>` via `subprocess.run`; assert non-zero exit AND stderr contains rejection message — proves end-to-end the CLI gate rejects bad paths the orchestrator might pass; (g) invoke `prepare-dispatch` on a valid path; assert exit 0 AND stdout parses as JSON with `resolved_path` and `sha256` keys.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Use `tmp_path` pytest fixture.
  - Symlink creation: `Path(tmp_path/'lifecycle'/'foo'/'evil.md').symlink_to('/etc/hostname')`.
  - Each sub-test is an individual `def test_*` function for granular failure reporting.
  - For (f)–(g): use `subprocess.run([sys.executable, '-m', 'cortex_command.critical_review', 'prepare-dispatch', ...], capture_output=True, text=True, cwd=tmp_path)` — exercises the actual entry path the SKILL.md orchestrator block uses, closing the "module-API-tested-but-not-CLI-path" gap.
  - Module under test: `cortex_command.critical_review`.
- **Verification**: `just test tests/test_critical_review_path_validation.py` — pass if exit 0 (Req 9d acceptance, extended to CLI). AND `grep -c '@pytest.mark.slow' tests/test_critical_review_path_validation.py` = 0 — pass if 0. AND `grep -c 'subprocess.run\|subprocess.check_output' tests/test_critical_review_path_validation.py` — pass if ≥ 1 (CLI-layer coverage present).
- **Status**: [ ] pending

### Task 4: Update critical-review reviewer + fallback prompts (path + SHA placeholders)
- **Files**:
  - `skills/critical-review/SKILL.md`
- **What**: At reviewer-prompt template (~SKILL.md:91–152) and fallback single-agent prompt (~SKILL.md:160–189), replace the `{artifact content}` block with two placeholders `{artifact_path}` and `{artifact_sha256}` plus a directive instructing the reviewer to (a) Read `{artifact_path}` before beginning analysis; (b) emit `READ_OK: <absolute-path> <sha256-of-Read-result>` as the first line of output when the Read succeeds AND the computed SHA matches `{artifact_sha256}`; (c) emit `READ_FAILED: <absolute-path> <one-word-reason>` and stop analysis when Read fails or is empty (Reqs 1, 2). Add an explicit "do NOT re-resolve via `git rev-parse`; Read the literal absolute path provided" instruction (FM-6 hardening).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Reviewer-prompt template is the multi-angle reviewer (Step 2c) and the single-agent fallback (Step 2c partial-failure block).
  - Preserve all existing reviewer prompt structure (Finding Classes, Straddle Protocol, Output Format, JSON envelope footer). The only substitution is the `## Artifact` block.
  - Phrase the directive in positive-routing form (no MUST/CRITICAL/REQUIRED) per CLAUDE.md MUST-escalation policy. Use "emit `READ_OK: …` as the first line of output" rather than "you MUST emit …".
  - Both edits land in the same SKILL.md file; treat as one task because the prompts share structure and replacement target.
- **Verification** (awk-scoped to the reviewer + fallback sections only — Task 5 owns the synthesizer section):
  - `awk '/^### Step 2c:/,/^#### Step 2c.5/' skills/critical-review/SKILL.md | grep -c '{artifact content}'` — pass if 0 (Reqs 1, 2 acceptance, scoped to Tasks 4's edit region).
  - `awk '/^### Step 2c:/,/^#### Step 2c.5/' skills/critical-review/SKILL.md | grep -c '{artifact_path}'` — pass if ≥ 2 (covering reviewer + fallback).
  - `awk '/^### Step 2c:/,/^#### Step 2c.5/' skills/critical-review/SKILL.md | grep -c '{artifact_sha256}'` — pass if ≥ 2.
  - `awk '/^### Step 2c:/,/^#### Step 2c.5/' skills/critical-review/SKILL.md | grep -c 'READ_OK: <path> <sha>'` — pass if ≥ 1.
- **Status**: [ ] pending

### Task 5: Update critical-review synthesizer prompt (path + SHA + SYNTH_READ_OK)
- **Files**:
  - `skills/critical-review/SKILL.md`
- **What**: At synthesizer-prompt template (~SKILL.md:205–299), replace `{artifact content}` with `{artifact_path}` + `{artifact_sha256}` placeholders. Add a directive instructing the synthesizer to (a) Read `{artifact_path}` once at the START of synthesis, before the per-finding loop; (b) compute SHA-256 of the Read result and emit `SYNTH_READ_OK: <absolute-path> <sha256>` as a line in its output before the per-finding analysis (Req 3); (c) treat the in-context Read result as the source of truth for evidence-quote re-validation (preserves SKILL.md:218 invariant). Synthesizer prompt directive uses positive-routing phrasing — no MUST escalation.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - Synthesizer prompt lives in Step 2d. The directive sits alongside the existing "Read all reviewer findings carefully" instruction.
  - The `SYNTH_READ_OK: <path> <sha>` line must appear BEFORE any per-finding output so the orchestrator can parse it with a simple line-anchored regex.
  - Preserve the A→B downgrade rubric and evidence-quote re-validation language verbatim — only the artifact-source clause changes.
  - Depends on Task 4 so the file is touched in a deterministic order (avoids merge churn).
- **Verification** (awk-scoped to the synthesizer section only):
  - `awk '/^### Step 2d:/,/^### Step 2e:/' skills/critical-review/SKILL.md | grep -c '{artifact content}'` — pass if 0 (Req 3 acceptance for synthesizer region; combined with Task 4's region check, file-wide absence is the conjunction).
  - `awk '/^### Step 2d:/,/^### Step 2e:/' skills/critical-review/SKILL.md | grep -c 'SYNTH_READ_OK'` — pass if ≥ 1 (Req 3 acceptance).
  - `awk '/^### Step 2d:/,/^### Step 2e:/' skills/critical-review/SKILL.md | grep -c 'Read.*{artifact_path}'` — pass if ≥ 1 (Read directive in synthesizer prompt).
- **Status**: [ ] pending

### Task 6: Rewrite Step 2c.5 verification gate (sentinel-first, exclusion routing, warnings)
- **Files**:
  - `skills/critical-review/SKILL.md`
- **What**: Replace the existing Step 2c.5 envelope-extraction block (~SKILL.md:193–204) with a sentinel-first verification gate (Req 4a–4d): (a) Verify each reviewer's first-line `READ_OK: <path> <sha>` BEFORE attempting envelope extraction. If sentinel absent OR its SHA mismatches the orchestrator's pre-dispatch SHA OR reviewer emitted `READ_FAILED:`, mark reviewer excluded and DO NOT parse its envelope. (b) Excluded reviewer's findings drop from ALL tallies (A, B, C) AND from the untagged-prose pathway. Standardized warning `⚠ Reviewer N excluded: <reason>` where `<reason>` ∈ {`SHA drift detected (expected <sha>, got <sha>)`, `sentinel absent`, `Read failed: <error>`}. (c) Warnings appear in synthesizer prompt preamble (so the synthesizer sees the partial set explicitly). (d) Existing malformed-envelope handler at SKILL.md:199 stays for well-formed-sentinel-but-malformed-JSON cases.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - Step 2c.5 is the parsing/validation block between Step 2c (reviewer dispatch) and Step 2d (synthesizer dispatch).
  - The warning prefix `⚠` matches existing malformed-envelope warning format at SKILL.md:199 — keep the prefix character identical for visual consistency.
  - The orchestrator-side computation that produces "the orchestrator's pre-dispatch SHA" lands in Task 7 — Step 2c.5 here just describes that the SHA is captured into orchestrator context before fan-out and referenced here.
  - Use positive-routing phrasing throughout (CLAUDE.md MUST-escalation policy).
- **Verification** (scoped to Step 2c.5 section only — Task 7 owns the Step 2d synthesizer-gate occurrence):
  - `awk '/^#### Step 2c.5/,/^### Step 2d:/' skills/critical-review/SKILL.md | grep -c 'SHA drift detected'` — pass if ≥ 1 (Req 4a–b: reviewer-side mismatch warning).
  - `awk '/^#### Step 2c.5/,/^### Step 2d:/' skills/critical-review/SKILL.md | grep -c 'sentinel absent'` — pass if ≥ 1.
  - `awk '/^#### Step 2c.5/,/^### Step 2d:/' skills/critical-review/SKILL.md | grep -c 'Read failed'` — pass if ≥ 1.
  - `awk '/^#### Step 2c.5/,/^### Step 2d:/' skills/critical-review/SKILL.md | grep -c '⚠ Reviewer'` — pass if ≥ 1.
- **Status**: [ ] pending

### Task 7: Add orchestrator-side dispatch ceremony using atomic subcommands
- **Files**:
  - `skills/critical-review/SKILL.md`
- **What**: Add an orchestrator-side block (logical location: between Step 2a "Project Context" loading and Step 2c "reviewer dispatch", plus a paired post-synthesis block after Step 2d) instructing Claude to perform the dispatch ceremony as **three atomic subprocess calls**, not a six-step in-context sequence. This collapses the validate→sha→substitute path-traversal gap and the post-synthesis parse-and-emit chain into single invocations whose internal sequencing is enforced inside `cortex_command.critical_review`, not by orchestrator prose-compliance.
  - **Pre-dispatch (atomic)**: instruct Claude to invoke `python3 -m cortex_command.critical_review prepare-dispatch <artifact-path> [--feature <name>]` and capture the single-line JSON `{"resolved_path", "sha256"}` from stdout. Substitute `resolved_path` into `{artifact_path}` and `sha256` into `{artifact_sha256}` at every dispatch site (reviewer template + fallback + synthesizer template). The orchestrator cannot get a SHA without prepare-dispatch having validated the path first — the two operations are fused inside the subprocess; bypassing validate-path requires bypassing prepare-dispatch entirely, which is detectable via a SKILL.md text grep that the invocation literal appears (Req 9 enforcement made structurally observable).
  - **Post-synthesis (atomic)**: instruct Claude to pipe the synthesizer's full output through `python3 -m cortex_command.critical_review verify-synth-output --feature <name> --expected-sha <hex>`. Exit 0 → surface the synthesizer's findings normally. Exit 3 → DO NOT surface the synthesis output; relay verify-synth-output's stdout (which contains the top-level diagnostic) verbatim. The diagnostic emission AND the `synthesizer_drift` events.log append both live inside verify-synth-output's exit-3 path — invoking the helper at all guarantees both fire when drift is detected; the orchestrator cannot emit one without the other (Req 4c + Req 12 fused).
  - **Per excluded reviewer (atomic)**: at Step 2c.5, for each reviewer the gate marked excluded, instruct Claude to invoke `python3 -m cortex_command.critical_review record-exclusion --feature <name> --reviewer-angle <angle> --reason <absent|sha_mismatch|read_failed> --model-tier <haiku|sonnet|opus> --expected-sha <hex> [--observed-sha <hex>]` once. The `sentinel_absence` event is appended atomically inside the helper using tempfile + `os.replace` (Req 12).
  - **Total-failure path**: when all reviewers excluded, emit `All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.` (Edge Cases bullet, spec.md:78).
- **Depends on**: [1, 6]
- **Complexity**: complex
- **Context**:
  - The orchestrator-side block contains shell invocations, not Python source. Python lands in Task 1.
  - Atomicity rationale (addresses critical-review Obj 2, Obj 3): each subcommand fuses what was previously a multi-step in-context ceremony into one subprocess. `prepare-dispatch` fuses validate + SHA so the orchestrator cannot compute SHA on an un-validated path. `verify-synth-output` fuses parse + diagnostic + telemetry so the synthesizer-drift diagnostic and the `synthesizer_drift` event cannot be invoked in isolation. `record-exclusion` fuses the per-reviewer event append. The chain length the orchestrator-LLM must execute drops from 6 prose steps to 3 atomic calls; non-compliance is observable as the helper invocation literal being absent from the SKILL.md template (caught by grep verification) rather than as silent omission of an in-context step.
  - The residual prompt-compliance surface — orchestrator-LLM must still *choose* to invoke each helper — is unchanged in kind from any other SKILL.md instruction. The reduction in step count narrows the window for fill-the-gap omission.
  - `<path>`-arg invocation (`/cortex-core:critical-review <path>`) omits `--feature`; auto-trigger flows pass `--feature` resolved from `LIFECYCLE_SESSION_ID` against `lifecycle/*/.session` (existing pattern at SKILL.md:319–325).
  - Residual circularity (acknowledged in Veto Surface, below): if the orchestrator-LLM skips invoking `verify-synth-output` entirely (treating the synthesizer output as final per SKILL.md:351 longstanding behavior), neither the diagnostic nor the `synthesizer_drift` event fires. This is the irreducible "telemetry depends on the behavior it measures" surface and is the limit of what positive-routing phrasing can deliver. Mitigation: the grep verification ensures the helper invocation literal is present in the template; long-run telemetry from `synthesizer_drift` events (when they fire) provides the OQ3 evidence path for whether MUST escalation is needed.
- **Verification** (awk-scoped where the assertion is region-specific):
  - `grep -c 'python3 -m cortex_command.critical_review prepare-dispatch' skills/critical-review/SKILL.md` — pass if ≥ 1.
  - `grep -c 'python3 -m cortex_command.critical_review verify-synth-output' skills/critical-review/SKILL.md` — pass if ≥ 1.
  - `grep -c 'python3 -m cortex_command.critical_review record-exclusion' skills/critical-review/SKILL.md` — pass if ≥ 1.
  - `awk '/^### Step 2d:/,/^### Step 2e:/' skills/critical-review/SKILL.md | grep -c 'Critical-review pass invalidated'` — pass if ≥ 1 (Req 4c diagnostic surfaced as fallback text in case verify-synth-output cannot run; primary path is helper-emitted).
  - `awk '/^### Step 2c:/,/^#### Step 2c.5/' skills/critical-review/SKILL.md | grep -c 'git rev-parse'` — pass if 0 (Req 8: `git rev-parse` MUST NOT appear inside reviewer/fallback prompt blocks). AND `awk '/^### Step 2d:/,/^### Step 2e:/' skills/critical-review/SKILL.md | grep -c 'git rev-parse'` — pass if 0 (Req 8: not inside synthesizer prompt either).
- **Status**: [ ] pending

### Task 8: Extend partial-coverage banner with excluded-reviewer surface
- **Files**:
  - `skills/critical-review/SKILL.md`
- **What**: At the existing partial-coverage banner instruction (~SKILL.md:303), extend the "N of M reviewer angles completed" prefix to surface excluded-but-completed reviewers separately: `N of M reviewer angles completed (K excluded for drift/Read failure)`. When `K = 0` the parenthetical is OMITTED (preserves existing behavior for clean runs) (Req 5).
- **Depends on**: [7]
- **Complexity**: trivial
- **Context**:
  - Single-line wording change to the banner template; the substitution variable `K` is supplied by the orchestrator's Step 2c.5 result from Task 6.
  - Phrase as instruction to the orchestrator (Claude), not a runtime substitution variable.
- **Verification**:
  - `grep -c 'excluded for drift/Read failure' skills/critical-review/SKILL.md` — pass if ≥ 1 (Req 5 acceptance).
- **Status**: [ ] pending

### Task 9: Replace inline `{full contents}` in lifecycle critical-tier plan dispatch
- **Files**:
  - `skills/lifecycle/references/plan.md`
- **What**: At lines 43 and 46 of the plan-agent prompt template, replace `{full contents of lifecycle/{feature}/spec.md}` with `{spec_path}` and `{full contents of lifecycle/{feature}/research.md}` with `{research_path}` (Req 6). Add a per-agent Read directive instructing each plan agent to Read both files at the start of its work and to emit `READ_OK: <path> <sha>` headers for each (one line per file). Positive-routing phrasing.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Plan-agent prompt template is in §1b (Competing Plans — critical-tier path). Edits are limited to the prompt template body, not the surrounding orchestrator-facing prose.
  - The orchestrator-side resolution + SHA computation pattern for these placeholders mirrors Task 7 — but lives in plan.md §1b's orchestrator block, which today reads spec.md and research.md into main context (line 30). Add an instruction: "absolutify spec_path and research_path via `git rev-parse --show-toplevel` joined with the lifecycle paths before injection." No new Python helper needed here — these paths are known constants relative to the lifecycle directory, not user-supplied (no SEC-1 surface).
  - Plan-agent dispatch is critical-tier only; lower tiers skip §1b entirely.
- **Verification**:
  - `grep -c 'full contents of lifecycle' skills/lifecycle/references/plan.md` — pass if 0 (Req 6 acceptance).
  - `grep -c '{spec_path}' skills/lifecycle/references/plan.md` — pass if ≥ 1.
  - `grep -c '{research_path}' skills/lifecycle/references/plan.md` — pass if ≥ 1.
  - `awk '/Plan Agent Prompt Template/,/^```$/' skills/lifecycle/references/plan.md | grep -c 'READ_OK'` — pass if ≥ 1.
- **Status**: [ ] pending

### Task 10: Replace hedged inline phrasing in lifecycle review.md reviewer prompt
- **Files**:
  - `skills/lifecycle/references/review.md`
- **What**: At line 30, replace `{contents of lifecycle/{feature}/spec.md, or a summary with a path to read it}` with `{spec_path}` plus an unambiguous Read directive (eliminating the existing hedge) (Req 7). Reviewer prompt instructs the agent to Read `{spec_path}` before beginning the review; positive-routing phrasing.
- **Depends on**: none
- **Complexity**: trivial
- **Context**:
  - review.md is the lifecycle reviewer reference; line 30 is inside the reviewer prompt template.
  - Orchestrator-side resolution: same pattern as Task 9 — absolutify against `git rev-parse --show-toplevel` joined with `lifecycle/{feature}/spec.md`. Add a short orchestrator instruction adjacent to the prompt template noting that `{spec_path}` must be substituted with the absolute path.
- **Verification**:
  - `grep -c 'contents of lifecycle/{feature}/spec.md, or a summary' skills/lifecycle/references/review.md` — pass if 0 (Req 7 acceptance).
  - `grep -c '{spec_path}' skills/lifecycle/references/review.md` — pass if ≥ 1.
- **Status**: [ ] pending

### Task 11: Update existing slow classifier test for new placeholders
- **Files**:
  - `tests/test_critical_review_classifier.py`
- **What**: At all five `re.sub` substitution sites (lines ~278, ~410, ~607, ~745, and one more — search for `r'\{artifact content\}'`), update the regex from `r'\{artifact content\}'` to a coordinated substitution of `r'\{artifact_path\}'` and `r'\{artifact_sha256\}'` with concrete stub values (e.g., absolute path to a temp file containing `STUB_ARTIFACT` and its sha256 digest). Update the post-substitution absence assertions from `assert "{artifact content}" not in assembled` to `assert "{artifact_path}" not in assembled` AND `assert "{artifact_sha256}" not in assembled` (Req 11). Update the file-level comment at line 20 from "ground the synthesizer prompt's `{artifact content}` reference" to "ground the synthesizer prompt's `{artifact_path}`/`{artifact_sha256}` references and the reviewer Read directive."
- **Depends on**: [4, 5]
- **Complexity**: simple
- **Context**:
  - All five sites share the same substitution structure — refactor into a helper if duplication grows, but a coordinated sed-like edit at each site is acceptable.
  - The stub-artifact temp file must be written before the substitution sites that reference it; existing tests already use a module-level `STUB_ARTIFACT` constant — extend with a module-level `STUB_ARTIFACT_PATH` and `STUB_ARTIFACT_SHA256` computed at import time via `tmp_path_factory` or a session-scoped fixture.
  - The slow marker stays — this test continues to exercise live-model invocations and is not the fast-path test added in Task 2.
- **Verification**:
  - `grep -c '{artifact content}' tests/test_critical_review_classifier.py` — pass if 0 (Req 11 acceptance).
  - `grep -c '{artifact_path}\|{artifact_sha256}' tests/test_critical_review_classifier.py` — pass if ≥ 2.
- **Status**: [ ] pending

### Task 12: Regenerate dual-source mirrors and verify parity
- **Files**:
  - `plugins/cortex-core/skills/critical-review/SKILL.md` (regenerated)
  - `plugins/cortex-core/skills/lifecycle/references/plan.md` (regenerated)
  - `plugins/cortex-core/skills/lifecycle/references/review.md` (regenerated)
- **What**: Trigger the dual-source mirror regeneration (the pre-commit hook handles this on commit — confirm via `just setup-githooks` is active locally, then commit the canonical-source changes from Tasks 4–10 in a single feature commit). Run the parity test to confirm byte-match (Req 13).
- **Depends on**: [4, 5, 6, 7, 8, 9, 10]
- **Complexity**: simple
- **Context**:
  - The pre-commit hook regenerates `plugins/cortex-core/{skills,hooks,bin}/` mirrors from canonical sources. This task's "edit" is implicit — the hook produces the mirror diff during commit.
  - If the hook is not active locally, run `just setup-githooks` first.
  - The parity test (`tests/test_dual_source_reference_parity.py`) asserts byte-equality between canonical and mirror.
- **Verification**:
  - `just test tests/test_dual_source_reference_parity.py` — pass if exit 0 (Req 13 acceptance).
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification is the spec's 13 acceptance criteria, mapped to tasks (per-task verifications are awk-scoped where the spec's file-wide grep would create cross-task entanglement):
- Reqs 1, 2 → Task 4 awk-scoped grep (Step 2c reviewer + fallback region).
- Req 3 → Task 5 awk-scoped grep (Step 2d synthesizer region; SYNTH_READ_OK literal).
- Req 4a–b → Task 6 awk-scoped grep (Step 2c.5 region; warning vocabulary).
- Req 4c → Task 7 awk-scoped grep (Step 2d region; `Critical-review pass invalidated`).
- Req 5 → Task 8 grep.
- Req 6 → Task 9 grep.
- Req 7 → Task 10 grep.
- Req 8 → Task 7 awk-scoped grep (`git rev-parse` absent inside reviewer/synthesizer prompt blocks).
- Req 9 → Task 3 tests (module API + CLI subprocess paths; symlink rejection asserted at both layers).
- Req 10 → Task 2 fast-path test passing post-Tasks 4–10.
- Req 11 → Task 11 grep.
- Req 12 → Task 7 helper-invocation greps (`prepare-dispatch`, `verify-synth-output`, `record-exclusion` literals present in SKILL.md instruction block); event-emission atomicity guaranteed by helper implementation, not by orchestrator-side `python3 -c` block.
- Req 13 → Task 12 dual-source parity test passing.

Spec acceptance crosswalk for Req 4 (which mandates `grep -c 'SHA drift detected' ≥ 2`): satisfied by the conjunction of Task 6's Step-2c.5-scoped grep (≥ 1) and Task 7's Step-2d-scoped grep (≥ 1, since the SKILL.md instruction block describes what `verify-synth-output` emits on drift). The file-wide count therefore meets the spec's ≥ 2 threshold without requiring the diagnostic to be hard-coded as inline `python3 -c` text.

Run `just test` after Task 12 to confirm the full suite passes — fast-path template test, module-API + CLI-subprocess path-validation test, updated slow classifier test, dual-source parity test.

Runtime verification (Interactive/session-dependent: orchestrator-side ceremony compliance cannot be verified by unit tests without live-model dispatch — explicitly out of scope per Scope Boundaries with concrete follow-up triggers): after merge, run `/cortex-core:critical-review lifecycle/reduce-sub-agent-dispatch-artifact-duplication/plan.md` once and confirm (a) reviewers Read the path; (b) `READ_OK:` sentinels appear in reviewer outputs; (c) `verify-synth-output` is invoked post-synthesis (visible as a Bash tool call); (d) no `{artifact_path}` literal leaks into reviewer prompts. This is a smoke check, not the runtime-compliance test deferred to follow-up.

## Veto Surface

- **Atomic-subcommand ceremony (prepare-dispatch / verify-synth-output / record-exclusion) vs. inline multi-step orchestrator block**: revised per critical-review feedback. The original plan had Claude execute a 6-step in-context ceremony (validate → sha256 → substitute → dispatch → parse SYNTH_READ_OK → conditional diagnostic+telemetry append). That design generalized from a single-step inline-write precedent (SKILL.md:316) and admitted three failure surfaces: (i) validate→sha non-atomicity (orchestrator could compute SHA on un-validated path, defeating SEC-1); (ii) post-synthesis self-suppressing telemetry (skipping the parse silently disables both Req 4c diagnostic and Req 12 telemetry); (iii) longer chain than any precedent had tested. The revised design fuses these into three atomic subprocess calls inside `cortex_command/critical_review.py`. Trade-off accepted: orchestrator-LLM must still *choose* to invoke each helper (residual prompt-compliance surface), but the chain length drops from 6 prose steps to 3, and non-invocation is detectable as a grep miss on the SKILL.md template — making compliance observable in static template checks rather than only via runtime telemetry. This trades 3 extra atomic subprocesses per dispatch (negligible overhead) for fusing the security-critical and telemetry-critical sequencing constraints into Python rather than prose.
- **Python module (`cortex_command/critical_review.py`) vs. `bin/cortex-*` wrapper script**: chose module because no consumer outside the SKILL.md orchestrator block needs it, and adding a `bin/` script triggers the parity-wiring check (`bin/cortex-check-parity` W003) without external users justifying it. The atomicity property the critical review flagged is delivered by *collapsing subcommand boundaries inside the module*, not by where the entry point lives. Reversible if a `bin/` consumer materializes.
- **Reviewer SHA-mismatch = exclude (Req 4b) vs. abort entire pass**: matches the existing malformed-envelope graceful-degradation pattern (SKILL.md:199); spec Open Decision Q4 resolved this in favor of exclude. Synthesizer-side mismatch (Req 4c) DOES abort — asymmetry intentional per spec.
- **`sentinel_absence` / `synthesizer_drift` event emission inside the helper (`append_event` using tempfile + `os.replace`) vs. inline `python3 -c` block in SKILL.md**: revised per critical-review B-class concern that "atomic-append" lacked a worked technique. The append function uses the same tempfile + `os.replace` pattern as the existing residue write (SKILL.md:329–342), which is genuinely atomic under concurrent emitters — `open(path, 'a')` is not. Living inside the helper means the SKILL.md instruction is one CLI invocation, not an inline Python block the orchestrator must reconstruct.
- **Plan-agent prompt at `skills/lifecycle/references/plan.md` does not add cross-agent SHA verification**: spec Req 6 requires only `{full contents}` removal; SHA verification at the plan-agent dispatch site is out of scope per spec. The `READ_OK` sentinel from Task 9 is emitted by plan agents but not parsed by an orchestrator-side gate. This is acknowledged as a follow-up surface, not a delivered drift-observability claim — see Scope Boundaries follow-up entries.

## Scope Boundaries

Maps to spec §Non-Requirements:
- No size-gated hybrid (uniform path+SHA at all sizes).
- No filesystem locks or advisory `flock`.
- No `$TMPDIR` snapshot file (rejected E3 in research).
- No pre-sliced sections (rejected C in research).
- No content-addressed storage or new helper subsystem beyond `cortex_command/critical_review.py`.
- No changes to parallel multi-reviewer fan-out value question.
- No changes to angle-derivation logic in critical-review Step 2b.
- No changes to the synthesizer's A→B downgrade rubric.
- No retroactive cleanup of archived lifecycle directories or events.log payloads.
- No new MUST/CRITICAL/REQUIRED escalations in dispatch templates.
- No live-model emission test in this ticket.
- No SHA-verification gate at the lifecycle plan-agent dispatch site (`skills/lifecycle/references/plan.md` §1b).
- No SHA-verification gate at the lifecycle plan-variant synthesizer site (`skills/lifecycle/references/plan.md` §1b.d, parallel plan-agents → Opus comparison pass).
- No end-to-end runtime test of orchestrator-LLM compliance with the dispatch ceremony (template-correctness and module-API coverage only).

### Follow-up triggers (captured in critical-review-residue.json)

The B-class findings written to `lifecycle/{feature}/critical-review-residue.json` define concrete follow-up triggers:

- **Plan-variant synthesizer drift coverage**: file a follow-up backlog item if and when (a) a `synthesizer_drift` event fires for the critical-review site (demonstrating drift is a real failure mode), OR (b) an observed plan-variant comparison produces inconsistent results traceable to mid-dispatch variant-file modification.
- **Live-model emission test for Req 12 telemetry**: file a follow-up backlog item when one of the following triggers fires — (i) ≥ 5 `sentinel_absence` events accumulated across `lifecycle/*/events.log` (demonstrating reviewer non-compliance is empirically observable, justifying a CI-cost-bearing test); OR (ii) ≥ 8 weeks elapsed since this ticket merged with zero `sentinel_absence`/`synthesizer_drift` events emitted (suggesting the ceremony is never firing, which is itself a signal that warrants an empirical compliance test independent of telemetry). The trigger pair breaks the spec's circular-dependency framing: either telemetry fires (use as evidence) or it doesn't fire over a long window (use absence as the trigger).
- **End-to-end orchestrator-compliance test**: file a follow-up backlog item if the live-model emission test (above) ships and shows < 90% of failure-injected dispatches correctly emit `sentinel_absence`. Below that threshold, prompt-compliance is insufficient and the OQ3 evidence path supports MUST escalation per CLAUDE.md.
