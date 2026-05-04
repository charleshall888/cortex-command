"""Static spawn-site env-var assertion (Task 14).

Closes residue B-1/B-3's most-likely refactor mistake: a future change
drops ``CORTEX_RUNNER_CHILD`` from one of the two spawn sites in
``cortex_command/overnight/runner.py``, silently disabling Phase 0
enforcement on that path. The hook still loads but never fires for
commits issued through the affected spawn chain — a particularly
insidious failure mode.

This is a cheap static literal-count check on the runner.py source
text. It does NOT exercise the spawn chain at runtime — that
integration test (50+ LOC of test scaffolding for runner.py
end-to-end) remains deferred per spec's Open Decisions section
(``lifecycle/install-pre-commit-hook-rejecting-main-commits-during-overnight-sessions/spec.md``,
"Spawn-site CORTEX_RUNNER_CHILD assertion").

Caveat documented in the test logic: a future refactor that moves env
construction to a helper function (e.g. ``env=_runner_child_env()``)
keeps the literal-string count low. The assertion accepts EITHER

* count of ``CORTEX_RUNNER_CHILD`` literal-string occurrences ≥ 2
  (the two known spawn-site dict-literal forms), OR
* count == 1 AND a recognizable helper-function definition matching
  the regex ``def\\s+\\w*[Cc]hild_env\\b`` exists in the source (the
  helper definition itself contains the literal string, plus ≥ 1
  spawn-site call would push the count higher; count == 1 means
  every spawn site routes through the helper).

If neither condition holds, the assertion fails with a message
pointing back to spec's Architectural Insight section so a future
maintainer knows where to look.
"""

from __future__ import annotations

import re
from pathlib import Path


RUNNER_PATH = (
    Path(__file__).resolve().parent.parent
    / "cortex_command"
    / "overnight"
    / "runner.py"
)

ENV_VAR = "CORTEX_RUNNER_CHILD"
HELPER_PATTERN = re.compile(r"def\s+\w*[Cc]hild_env\b")


def test_spawn_sites_pass_cortex_runner_child_env_var() -> None:
    """Assert runner.py still passes CORTEX_RUNNER_CHILD at both spawn sites.

    See module docstring for the accepted shapes (literal-dict count ≥ 2,
    or helper-function refactor with count == 1 + helper def present).
    """
    assert RUNNER_PATH.is_file(), f"runner.py missing at {RUNNER_PATH}"
    source = RUNNER_PATH.read_text(encoding="utf-8")

    literal_count = source.count(ENV_VAR)
    helper_match = HELPER_PATTERN.search(source)

    if literal_count >= 2:
        return
    if literal_count == 1 and helper_match is not None:
        return

    raise AssertionError(
        f"Spawn-site env-var canary tripped: found {literal_count} "
        f"occurrence(s) of {ENV_VAR!r} in {RUNNER_PATH} and "
        f"{'a' if helper_match else 'no'} helper-function definition "
        f"matching {HELPER_PATTERN.pattern!r}. The two spawn sites "
        f"(_spawn_orchestrator and _spawn_batch_runner) must each pass "
        f"env={{**os.environ, {ENV_VAR!r}: '1'}} (or route through a "
        f"shared *_child_env helper that does so) — otherwise Phase 0 "
        f"enforcement silently fails for the affected spawn chain. "
        f"See lifecycle/install-pre-commit-hook-rejecting-main-commits-"
        f"during-overnight-sessions/spec.md, 'Architectural Insight' "
        f"section."
    )
