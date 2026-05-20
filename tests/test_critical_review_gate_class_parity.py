"""Structural parity tests for ``cortex_command.critical_review`` gate policy.

This file is established in Phase 1 (Task 1) of the
``gate-policy-taxonomy-and-critical-review`` lifecycle. It ships
``test_no_root_pre_resolution_gate`` (Phase 1 atomicity invariant for
Fix 2 / Requirements 3 and 4) and ``test_renamed_verifiers_have_caveat_substrings``
(Task 3 / Requirement 2(b) — the renamed verifier docstring caveat
contract). Future Phase 2 additions will extend this file with
``# gate-class:`` annotation assertions, reusing the module-level
``_get_function_source`` helper.

Why a structural parity test (not prose convention):
  - The spec's Requirement 4 binds atomicity to executable check rather
    than to commit-discipline prose. If a future commit reverts the
    under-root scoping without restoring the root pre-resolution gate
    (or vice versa), the test fires immediately with a named failure
    message.
  - Requirement 2(b) binds the renamed verifier docstrings' honesty
    caveat to an executable check rather than to author intent. If a
    future commit rewrites the docstring and drops the
    ``Does NOT detect ... engagement`` caveat, the test fires
    immediately so the rename's primary value (honesty: name +
    docstring + ``advisory`` annotation match what the gate actually
    delivers) cannot silently regress.
"""

from __future__ import annotations

import inspect
import re

from cortex_command import critical_review


# ---------------------------------------------------------------------------
# Module-level helpers (reused by Tasks 3 and 4)
# ---------------------------------------------------------------------------


def _get_function_source(name: str) -> str:
    """Return the textual source of ``critical_review.<name>`` via ``inspect``.

    Used by every parity assertion in this file (and by future Phase 2
    additions for ``check_artifact_stable`` and ``check_synth_stable``).
    Centralizing the lookup here keeps the assertions terse and ensures
    every parity check observes the same source-truth definition.

    Args:
        name: Bare attribute name on the ``critical_review`` module
            (e.g. ``"validate_artifact_path"``).

    Returns:
        The function's source text as returned by ``inspect.getsource``.
    """
    func = getattr(critical_review, name)
    return inspect.getsource(func)


# ---------------------------------------------------------------------------
# Phase 1 atomicity invariant (Requirement 2(c) / Requirement 4)
# ---------------------------------------------------------------------------


def test_no_root_pre_resolution_gate() -> None:
    """Phase 1 atomicity invariant: under-root scoping present, no root pre-resolution gate.

    Spec Requirements 3 + 4 (atomic Fix 2): ``validate_artifact_path``
    must use ``Path(root).resolve()`` + ``is_relative_to`` for under-root
    scoping, AND must NOT pre-resolve each root via ``os.path.realpath``
    and compare against ``abspath`` (the old redundant root-symlink gate
    that was removed in the same commit as the candidate-symlink gate
    replacement).

    Failure modes detected:
      - The under-root scoping was reverted without restoring the
        candidate-symlink gate (loss of containment): the
        ``is_relative_to`` + ``.resolve()`` pair disappears from source.
      - The redundant root-symlink gate was re-introduced (atomicity
        broken in a later commit): a ``realpath(root) != abspath`` shape
        re-appears anywhere in ``validate_artifact_path``.

    The named failure message ``Phase 1 atomicity invariant violated —
    root pre-resolution gate present`` matches the spec's
    Requirement 4 acceptance criterion verbatim so the failure is
    grep-discoverable from CI output.
    """
    source = _get_function_source("validate_artifact_path")

    # --- (A) Positive: under-root scoping via Path(...).resolve() +
    #         is_relative_to is present (Requirement 3 + 2(c) first clause).
    # The under-root scoping check must (i) call .resolve() on a root,
    # (ii) call is_relative_to() against a resolved-root-derived expression.
    # We enforce both substrings appear in source; the assertion is a
    # presence check rather than a structural-AST check because the
    # call sites are stable and a regex/substring check is sufficient
    # to catch reverts.
    assert ".resolve()" in source, (
        "Phase 1 invariant violated — under-root scoping missing: "
        "validate_artifact_path no longer contains a `.resolve()` call "
        "on a root path. The Fix 2 atomic landing requires "
        "`Path(root).resolve()` for under-root scoping."
    )
    is_relative_to_count = len(re.findall(r"\bis_relative_to\s*\(", source))
    assert is_relative_to_count >= 1, (
        "Phase 1 invariant violated — under-root scoping missing: "
        "validate_artifact_path contains zero `is_relative_to(...)` "
        "call sites. Fix 2 requires the under-root scoping check "
        "`<candidate>.is_relative_to(<root>.resolve())`."
    )

    # --- (B) Negative: no root pre-resolution gate (Requirement 4 +
    #         2(c) second clause).
    # The forbidden pattern is `os.path.realpath(<root-ish>) != ...
    # abspath(...)` (or any rearrangement of the inequality comparing
    # realpath-of-root against abspath-of-root). The old code shape
    # was: ``root_real = os.path.realpath(root); if root_real != root_abs``.
    # We detect this by looking for any line that pairs ``realpath`` with
    # an inequality (``!=``) and a sibling ``abspath`` reference within
    # a small window of the same function. A single check covers both
    # the direct one-line form and the two-line bind-then-compare form.
    #
    # We strip Python comments and the docstring before regex-matching so
    # that documentation referencing the removed pattern (intentional
    # archaeological references explaining why the gate is gone) does
    # not false-positive.
    body = _strip_docstring_and_comments(source)

    # Pattern 1: one-line direct form, e.g. `if os.path.realpath(root) != os.path.abspath(root):`
    one_line_pattern = re.compile(
        r"os\.path\.realpath\([^)]*\)\s*!=\s*[^=\n]*abspath",
    )
    # Pattern 2: also catch `abspath(...) != os.path.realpath(...)` (operand-flipped).
    one_line_pattern_flipped = re.compile(
        r"abspath\([^)]*\)\s*!=\s*[^=\n]*realpath",
    )
    # Pattern 3: two-line bind-then-compare form, e.g.
    #   root_real = os.path.realpath(root)
    #   root_abs = os.path.abspath(root)
    #   if root_real != root_abs:
    # We detect the *structural shape* by checking for the joint presence
    # of (a) a `realpath` bind whose argument names a root and (b) an
    # `abspath` bind whose argument names a root and (c) an inequality
    # (``!=``) in the function. The conjunction is what telegraphs the
    # forbidden gate; each piece alone is benign.
    #
    # To avoid false-positives on the legitimate
    # `realpath = os.path.realpath(candidate)` binding (which is the
    # candidate's realpath, not the root's pre-resolution), we narrow to
    # bindings whose RHS argument contains the word "root".
    realpath_root_bind = re.compile(
        r"=\s*os\.path\.realpath\([^)]*root[^)]*\)",
    )
    abspath_root_bind = re.compile(
        r"=\s*os\.path\.abspath\([^)]*root[^)]*\)",
    )
    has_realpath_root_bind = bool(realpath_root_bind.search(body))
    has_abspath_root_bind = bool(abspath_root_bind.search(body))
    has_inequality = bool(re.search(r"!=", body))
    two_line_gate_present = (
        has_realpath_root_bind and has_abspath_root_bind and has_inequality
    )

    violations = (
        bool(one_line_pattern.search(body))
        or bool(one_line_pattern_flipped.search(body))
        or two_line_gate_present
    )
    assert not violations, (
        "Phase 1 atomicity invariant violated — root pre-resolution "
        "gate present. validate_artifact_path contains a "
        "`realpath(root) != abspath` style check; the redundant "
        "root-symlink gate (previously at :103-111) must remain "
        "removed in the same commit that lands the under-root scoping "
        "fix. Restore atomicity by deleting the pre-resolution check."
    )


# ---------------------------------------------------------------------------
# Task 3 / Requirement 2(b): renamed-verifier docstring caveat contract
# ---------------------------------------------------------------------------


def test_renamed_verifiers_have_caveat_substrings() -> None:
    """Renamed verifier docstrings must carry the three-substring honesty caveat.

    Spec Requirement 2(b) / Task 3: the docstrings of
    ``check_artifact_stable`` and ``check_synth_stable`` must each contain
    ALL THREE of the substrings:

      - ``Does NOT detect``
      - ``orchestrator-fabricated input``
      - ``engagement``

    The multi-substring check resists single-word rephrasing — a future
    docstring rewrite that drops any one substring fires the assertion.

    Why these three substrings and not a single sentinel phrase:
      - ``Does NOT detect`` pins the gate's negative-capability framing.
      - ``orchestrator-fabricated input`` names the specific bypass
        surface (the orchestrator-LLM controls both the SHA and the
        input file).
      - ``engagement`` names the property the gate cannot enforce
        (reviewer/synth engagement quality).

    Lands in the same commit as the docstring + ``# gate-class: advisory``
    annotation per Task 3's atomicity constraint — no inter-commit drift
    window between the docstring contract and the test that enforces it.
    """
    required_substrings = (
        "Does NOT detect",
        "orchestrator-fabricated input",
        "engagement",
    )

    for func_name in ("check_artifact_stable", "check_synth_stable"):
        func = getattr(critical_review, func_name)
        doc = func.__doc__ or ""
        missing = [s for s in required_substrings if s not in doc]
        assert not missing, (
            f"Renamed verifier ``{func_name}`` docstring missing required "
            f"honesty-caveat substring(s) {missing!r}. Per spec Requirement "
            f"2(b) the docstring must contain all of: {list(required_substrings)!r}. "
            f"Restore the substrings (or update the spec — but the spec is "
            f"the source of truth here)."
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _strip_docstring_and_comments(source: str) -> str:
    """Return ``source`` with the leading docstring and ``#`` comments removed.

    Used by the structural-invariant regex so that archaeological prose
    inside the function's docstring (or inline comments narrating the
    removed gate) does not false-positive on the forbidden pattern.

    Implementation: removes the first triple-quoted block found after a
    ``def`` line (the docstring), then strips every ``# ...`` segment
    from each remaining line. Crude but adequate for a single-function
    source slice (no nested docstrings, no f-string sharps).
    """
    # Remove the docstring: matches the first triple-quoted block.
    no_docstring = re.sub(
        r'""".*?"""',
        "",
        source,
        count=1,
        flags=re.DOTALL,
    )
    # Strip inline `#` comments.
    lines = []
    for line in no_docstring.splitlines():
        # Find a `#` that isn't inside a string (heuristic: no string
        # parsing — the critical_review.py file does not embed `#` in
        # string literals inside validate_artifact_path).
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        lines.append(line)
    return "\n".join(lines)
