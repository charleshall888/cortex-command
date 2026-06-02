---
schema_version: "1"
uuid: 68318507-7d0f-4d6a-9de3-e896c9438481
title: "Pre-commit gates silently skip deep-nested files: Path.match('**') under-scan in check-parity / check-prescriptive-prose / check-events-registry + bare-python-import 3.12 break"
status: complete
priority: medium
type: bug
created: 2026-06-02
updated: 2026-06-02
complexity: complex
criticality: high
spec: cortex/lifecycle/pre-commit-gates-silently-skip-deep/spec.md
areas: ['hooks']
blocked-by: 279
---
**Why:** `Path.match("dir/**/*.md")` treats `**` as exactly one path segment on all supported Python versions (3.12+), so the `--staged` corpus-membership test in three pre-commit checkers silently skips depth-1 and depth-≥3 in-scope files — about 72% of the corpus. The bash pre-commit trigger still fires for these files (its `case` globs span slashes), the checker runs, then the inner `.match` filter discards the file — a false-green: the gate appears to pass while never scanning the edit. Affected: `cortex-check-parity` (`parity_check.py`), `cortex-check-prescriptive-prose` (`prescriptive_prose.py`), and `cortex-check-events-registry` (`bin/cortex-check-events-registry`). Separately, `cortex-check-bare-python-import` already migrated to `PurePath.full_match` (which handles `**` correctly) — but `full_match` was added in Python 3.13 while `requires-python` is `>=3.12`, so that checker raises `AttributeError` on 3.12. Surfaced during #279's deferred-item investigation; #279 fixes only the `cortex-check-contract` instance (its R8).

**Role:** Make the pre-commit gates actually scan the deep-nested files they claim to cover, on every supported Python, so they stop silently passing edits to those files.

**Integration:** Mirror the `cortex-check-contract` R8 approach from #279 — replace `Path.match(glob)`-against-`_SCAN_GLOBS` membership with a recursive matcher congruent with each checker's `--audit`/`root.glob` corpus, Python-3.12-safe (`fnmatch.fnmatch`, not bare `full_match`). The `bare-python-import` `full_match` usage must also be made 3.12-safe. A shared membership helper across the checkers would prevent the drift from recurring.

**Edges:** Do not over-scan beyond each checker's existing `--audit` corpus (hard-exclusions still apply). Exit semantics change only to surface violations in files that were previously skipped — expect each checker to start flagging genuine issues in deep files that were silently passing, so each may need its own follow-up to clear real findings. True-positive check: stage a depth-≥3 in-scope file with a known violation and confirm each gate now flags it; confirm no `AttributeError` on Python 3.12. Verify across 3.12 and 3.13+ (the `full_match`/`fnmatch` portability boundary).

**Touch-points:** `cortex_command/lint/parity_check.py`, `cortex_command/lint/prescriptive_prose.py`, `bin/cortex-check-events-registry`, `cortex_command/lint/bare_python_import.py` (the existing in-repo comment there names this exact bug), plus each checker's test fixtures. Related: #279 (the `cortex-check-contract` instance and R8 precedent).