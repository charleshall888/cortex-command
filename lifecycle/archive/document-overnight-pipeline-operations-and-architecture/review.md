# Review: document-overnight-pipeline-operations-and-architecture (Cycle 2)

Cycle 2 review — cycle 1 issues resolved in commit `c1afdbc` ("Resolve empty skeleton stubs in overnight-operations.md (review cycle 1)"). Scope: verify the two empty-subsection FAILs are fixed, re-check the remaining 11 requirements for regression, and verify anchor/duplication hygiene for the rework.

## Cycle 1 issue verification

**Issue 1 (Req 2) — `### Test Gate and integration_health` empty (Architecture):** RESOLVED. The subsection at `docs/overnight-operations.md:182` now contains substantive content across L184–L194: a lede paragraph disambiguating the branch-level gate from per-feature `ci_check`, a `**Files**` block, an `**Inputs**` block, separate "Flow on pass" and "Flow on fail" paragraphs (the fail path enumerates all three state changes: `INTEGRATION_DEGRADED=true`, `integration_health="degraded"`, warning block prepended to PR body), and a closing cross-link to the Tuning-side `#test-gate-and-integration_health-tuning`. The Tuning back-reference at L274 ("The Test Gate and integration_health subsection under Architecture documents the flow") is no longer a dangling forward-pointer.

**Issue 2 (Req 2) — `### lifecycle.config.md fields and absence behavior` empty (Tuning):** RESOLVED via deletion. The empty heading at the former L289 is gone from the Tuning section; the canonical coverage lives at `docs/overnight-operations.md:497` under Internal APIs as `### lifecycle.config.md consumers and absence behavior`. Deletion is acceptable because (a) the required keyword "lifecycle.config.md" is still documented with content (Req 2 acceptance is keyword coverage with content, not "coverage in the Tuning section specifically"), and (b) no other part of the doc back-references the deleted Tuning heading.

**Empty-heading scan:** a Python scan over all H2/H3 headings looking for any heading with no non-blank content before the next heading returned 5 hits, all of which are H2 banners (`## Architecture`, `## Code Layout`, `## Tuning`, `## Observability`, `## Internal APIs`) whose H3 children are the content — the same structural pattern present in cycle 1. No empty H3 stubs remain.

**Anchor integrity:** extracted all 18 unique `](#...)` anchor references from the doc; computed the GitHub-slug of every H2/H3 heading; every reference resolves. In particular:
- `#test-gate-and-integration_health` → L182 (now has content)
- `#test-gate-and-integration_health-tuning` → L272
- `#overnight-strategyjson-contents-and-mutators` → L301
- `#strategy-file-overnight-strategyjson--mutators-and-consumers` → L57 (em-dash collapses to double-hyphen in the slug)
- `#post-merge-review-review_dispatch`, `#repair-caps`, `#auth-resolution-apikeyhelper-and-env-var-fallback-order`, `#orchestrator_io-re-export-surface`, `#runner-lock-runnerlock`, `#internal-apis`, `#security-and-trust-boundaries`, `#conflict-recovery-trivial-fast-path-and-repair-fallback`, `#cycle-breaking-for-repeated-escalations`, `#strategy-file-overnight-strategyjson-schema`, `#architecture`, `#code-layout`, `#tuning`, `#observability` all resolve.

No broken anchors, no anchors pointing at empty headings, no dangling forward-pointers introduced by the rework.

## Stage 1: Spec Compliance

### Req 1 — New file `docs/overnight-operations.md` exists
**Verdict:** PASS. File exists at `docs/overnight-operations.md`, now 523 lines (up from 513 in cycle 1, consistent with the rework adding Test Gate prose and removing one empty heading).

### Req 2 — All 21 gap subsections documented with content
**Verdict:** PASS. Cycle 1's two content-quality failures are resolved (see "Cycle 1 issue verification" above). Keyword coverage of all 21 gap topics is preserved: the "Test Gate or integration_health" keyword lands at L182 (Architecture, now filled) and L272 (Tuning); the "lifecycle.config.md" keyword lands at L497 (Internal APIs, unchanged and substantive). Empty-heading scan is clean.

### Req 3 — Extraction from `docs/overnight.md`
**Verdict:** PASS. Unchanged by the rework. No edits to `docs/overnight.md` in cycle 2's rework scope; cycle 1's PASS stands.

### Req 4 — Cross-link hygiene
**Verdict:** PASS. All 18 anchor references resolve (full enumeration above). The rework added one new internal cross-link (`#test-gate-and-integration_health-tuning` from the new Architecture prose back to Tuning) which resolves correctly, and preserved the pre-existing reciprocal link from Tuning back to the Architecture subsection. No dangling references.

### Req 5 — `docs/pipeline.md` deduplication
**Verdict:** PASS. Unchanged by the rework; cycle 1's PASS stands.

### Req 6 — Source-of-truth rule in `CLAUDE.md`
**Verdict:** PASS. Unchanged by the rework; cycle 1's PASS stands.

### Req 7 — Pytest guards per-task tool allowlist
**Verdict:** PASS. Unchanged by the rework; cycle 1's PASS stands (`tests/test_dispatch_allowed_tools.py` exists and passes).

### Req 8 — `retros/` 2am-pain mining
**Verdict:** PARTIAL (PR-body gated — to verify in PR). Unchanged by the rework; cycle 1's assessment stands. The mining artifact at `learnings/retros-mining.md` is still present and coherent.

### Req 9 — Security and Trust Boundaries section
**Verdict:** PASS. The H2 still resolves (`## Security and Trust Boundaries` at L475; a single H2 in the doc). Rework did not touch this section.

### Req 10 — Tool allowlist documented literally
**Verdict:** PASS. `docs/overnight-operations.md:118-120` fenced block and the "source of truth: `claude/pipeline/dispatch.py`" comment are unchanged by the rework.

### Req 11 — No line-number cross-references
**Verdict:** PASS. The new Test Gate prose (L184–L194) does not introduce any `.py:NN` or `.md:NN` references — it names files by path (`claude/overnight/runner.sh`, `claude/overnight/integration_recovery.py`, `claude/overnight/strategy.py`), functions by name (`load_strategy`/`save_strategy`), and cross-links via anchors rather than line numbers. Step-heading-level pointer to the "Integration gate" block in `runner.sh` uses a prose descriptor ("the Integration gate block around the post-merge PR-prep stage") rather than a line number, matching the doc's existing convention for prompt-owned subsystems.

### Req 12 — `brain.py` disambiguation lede
**Verdict:** PASS. Unchanged by the rework; cycle 1's PASS stands.

### Req 13 — Progressive-disclosure rationale
**Verdict:** PASS. Unchanged by the rework; cycle 1's PASS stands.

## Requirements Drift

**State:** none.

**Findings:** The rework is a pure doc-content edit (adding prose under an existing heading, deleting an empty heading). No runtime behavior is described that was not already in `requirements/project.md`, `requirements/pipeline.md`, or `requirements/observability.md`. The new Test Gate prose describes pre-existing behavior of `runner.sh`, `integration_recovery.py`, and `strategy.py` — not new behavior. The `integration_health="degraded"` field, `INTEGRATION_DEGRADED=true` env var, and PR-body warning are all existing behaviors of the runner, documented now for the first time.

**Update needed:** no.

## Stage 2: Code Quality

### Pattern conformance
The new Test Gate content follows the established `**Files**` / `**Inputs**` / flow-paragraph pattern used throughout the doc (e.g. L186 `**Files**:`, L188 `**Inputs**:`, then "Flow on pass" / "Flow on fail" paragraphs). Prose voice, cross-link style, and paragraph cadence are consistent with neighboring subsections like Startup Recovery (L196) and Runner Lock (L208).

### Duplication check
The new prose at L184–L194 covers the flow (when the gate fires, what it invokes on failure, what state gets written). The Tuning subsection at L272 covers *only* tunable surfaces (`--test-command` choice, the unconditional-repair rule, `integration_health` semantics as a tunable). There is a small deliberate overlap: both subsections name `INTEGRATION_DEGRADED=true` and the PR-body warning when describing the failure outcome, but the Architecture side describes these as a *flow* (three things happen in order) while the Tuning side describes them as a *surface* (what operators observe). This matches the doc's stated "Architecture describes flow, Tuning describes tunable surfaces" split and is not duplication in the redundancy sense.

The Internal APIs subsection `### lifecycle.config.md consumers and absence behavior` (L497) still exists as the single canonical location for that content after the Tuning-side empty heading was removed. No duplication was introduced by the removal.

### Anchor-from-Tuning-to-Architecture resolution
The Tuning back-link `[Test Gate and integration_health](#test-gate-and-integration_health)` at L274 now resolves to a substantive Architecture subsection rather than an empty heading — the specific failure mode cycle 1 flagged is fixed. The new forward-link from Architecture to Tuning at L194 (`[Test Gate and integration_health tuning](#test-gate-and-integration_health-tuning)`) also resolves and closes the reciprocal-link pair.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 2,
  "issues": [],
  "requirements_drift": "none"
}
```
