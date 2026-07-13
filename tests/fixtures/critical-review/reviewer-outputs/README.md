# Reviewer-output fixture corpus

These fixtures drive the unit tests in `tests/test_critical_review_sentinel_window.py` that exercise `verify_reviewer_output` (see `cortex_command/critical_review.py` and the spec at `cortex/lifecycle/critical-review-sentinel-gate-relax-first/spec.md`). Each `case-*.txt` reviewer output has a sibling `case-*.meta.json` declaring its `expected_classification` and `expected_sha`.

## Cases

- **`case-ok-line-1`** — sentinel on line 1 (zero preamble). Exercises the trivial pass path.
- **`case-ok-after-preamble`** — sentinel on line 3 (brief preamble). Exercises shallow-preamble pass.
- **`case-ok-deeper-preamble`** — sentinel on line 11 (multi-paragraph preamble). Exercises deep-preamble pass within the 50-line window.
- **`case-absent`** — sentinel entirely missing (reviewer prose intact). Exercises the `absent` route.
- **`case-mismatch`** — sentinel present on line 1 but carrying a different 64-hex SHA. Exercises the `mismatch` route; the observed SHA is the SHA-256 of another committed file (CLAUDE.md).
- **`case-adversarial-quoted-sha`** — load-bearing fixture for the first-match-matching-SHA semantics at `spec.md:85`. Line 3 contains a quoted exemplar `READ_OK:` whose SHA does NOT match `expected_sha`; line 8 carries the reviewer's real sentinel whose SHA does match. A naive first-match parser would return `mismatch`; a correct implementation iterates matches and routes to the first whose SHA equals `expected_sha`.
- **`case-sentinel-absent-but-stable`** — ADDED for the #376 gate-time re-hash CLI wrappers (`_cmd_check_artifact_stable` / `_cmd_check_synth_stable`; spec `critical-review-sentinel-gate-excludes-async` R2/R3). The `.txt` is sentinel-free (pure verifier classifies `absent`); the meta additionally carries `pinned_artifact_content` and its real `expected_sha`. The wrapper advisory-pass test writes that content to a file, passes it as `--artifact-path` + `--expected-sha`, and the wrapper re-hashes it to the matching SHA → exit 0 + `sentinel_advisory` (no drift). Distinct from `case-absent`, which documents only the pure-verifier `absent` route; do NOT fold the two.

## Capture provenance

- **Date of capture**: 2026-05-16.
- **Source artifact for the `case-ok-*` fixtures**: `cortex/lifecycle/critical-review-sentinel-gate-relax-first/spec.md` (SHA-256 `cb308316a58baf4078ca15e25e0d8444ab321177f5c0e73cdb15c46fe8a9fdc5` at capture time). The three OK fixtures were produced by dispatching parallel reviewer agents (general-purpose) against this spec.md; the `case-absent`, `case-mismatch`, and `case-adversarial-quoted-sha` fixtures were hand-synthesized from a Task-3a OK fixture per the Task-3b template.
- **SHA-generation method**: SHAs in `expected_sha` and `observed_sha_in_fixture` fields are real `sha256sum` outputs of committed files in this repository (NOT `git hash-object`, which emits 40-hex SHA-1).

## Maintenance

These fixtures MUST NOT be re-baselined casually. They encode behavioral expectations that `tests/test_critical_review_sentinel_window.py` relies on — in particular, the line position of the sentinel in each OK fixture is the empirical anchor for the 50-line window-size choice (Requirement 5 of the spec), and the `case-adversarial-quoted-sha` fixture is the regression case for the first-match-matching-SHA defense. Before regenerating any fixture, re-read the spec's Requirement 5 and 6 and confirm the new content still satisfies the named test cases (a)-(l) at Requirement 6.
