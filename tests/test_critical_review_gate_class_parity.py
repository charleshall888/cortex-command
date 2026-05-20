"""Structural parity tests for ``cortex_command.critical_review`` gate policy.

This file is established in Phase 1 (Task 1) of the
``gate-policy-taxonomy-and-critical-review`` lifecycle. It ships
``test_no_root_pre_resolution_gate`` (Phase 1 atomicity invariant for
Fix 2 / Requirements 3 and 4), ``test_renamed_verifiers_have_caveat_substrings``
(Task 3 / Requirement 2(b) — the renamed verifier docstring caveat
contract), and ``test_every_gate_site_carries_in_scope_annotation``
(Task 4 / Requirement 2(a) — the closed-set gate-class annotation
contract). All three tests share the module-level
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
  - Requirement 2(a) binds every gate raise/return site to a
    closed-set ``# gate-class:`` annotation. If a future commit adds a
    new gate without annotation, removes an existing annotation, or
    introduces a class value outside the closed set
    ``{security, hygiene, advisory}``, the test fires immediately with
    a named failure message identifying the offending site.
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
# Task 4 / Requirement 2(a): closed-set gate-class annotation contract
# ---------------------------------------------------------------------------


# Closed set of valid gate-class values. Any value outside this set fires
# the parity test immediately. Adding a new class requires updating this
# constant AND the spec's Requirement 1 enumeration in lock-step.
_VALID_GATE_CLASSES = frozenset({"security", "hygiene", "advisory"})

# Regex matching the lines we consider gate-decision sites in
# ``validate_artifact_path``. Two shapes are matched:
#   - ``raise <Error>(...)`` — a direct raise of an Error class.
#   - ``last_err = <Error>(...)`` — a deferred raise constructed for
#     subsequent ``raise last_err`` propagation (the gate decision is
#     made at the assignment, not at the propagation site).
# The bare ``raise last_err`` propagation site is intentionally not
# matched — it carries no gate-decision logic of its own.
_VALIDATE_SITE_RE = re.compile(
    r"^[ ]+(?:raise [A-Za-z_]\w*Error\(|last_err = [A-Za-z_]\w*Error\()",
    re.MULTILINE,
)

# Regex matching the tuple-return shape in the verifier functions
# (``check_synth_stable``, ``check_artifact_stable``). Each verifier
# carries a single ``# gate-class: advisory`` annotation that classifies
# the gate as a whole — the parity assertion below verifies the
# annotation is present and that it precedes one of these tuple-return
# sites within the in-scope window.
_VERIFIER_SITE_RE = re.compile(
    r"""^[ ]+return \(["'](?:absent|mismatch|read_failed|ok)["']""",
    re.MULTILINE,
)

# In-scope window: an annotation is in-scope if it appears on one of the
# 3 lines immediately preceding the site. Generous enough to allow a
# blank line or a brief comment between the annotation and the site;
# tight enough that an annotation 30 lines away cannot silently drift.
_IN_SCOPE_WINDOW_LINES = 3

# Regex that captures a ``# gate-class: <value>`` annotation and the
# class value. Whitespace around the value is tolerated; only the
# captured value is validated against ``_VALID_GATE_CLASSES`` so that
# trailing comment text after the value (rare but legal) does not
# false-negative.
_ANNOTATION_RE = re.compile(r"#\s*gate-class:\s*([A-Za-z_]+)\b")


def _find_annotation_in_window(
    lines: list[str], site_line_idx: int
) -> str | None:
    """Return the gate-class value within ``_IN_SCOPE_WINDOW_LINES`` preceding ``site_line_idx``.

    Walks the ``_IN_SCOPE_WINDOW_LINES`` lines immediately preceding the
    site line (exclusive of the site line itself). Returns the captured
    class value (e.g. ``"hygiene"``) on the first match, or ``None`` if
    no annotation is in scope.

    Args:
        lines: The function source split on ``\\n``.
        site_line_idx: Zero-based index of the site line in ``lines``.

    Returns:
        The captured class value, or ``None`` if not found in scope.
    """
    start = max(0, site_line_idx - _IN_SCOPE_WINDOW_LINES)
    for line in lines[start:site_line_idx]:
        m = _ANNOTATION_RE.search(line)
        if m:
            return m.group(1)
    return None


def test_every_gate_site_carries_in_scope_annotation() -> None:
    """Phase 2 closed-set parity: every gate site carries an in-scope ``# gate-class:`` annotation.

    Spec Requirement 2(a) / Task 4: every gate raise/return site inside
    ``validate_artifact_path``, ``check_synth_stable``, and
    ``check_artifact_stable`` must carry an in-scope (≤
    ``_IN_SCOPE_WINDOW_LINES`` lines preceding) ``# gate-class: <value>``
    annotation where ``<value>`` is one of
    ``{security, hygiene, advisory}``.

    Two site shapes are walked:
      - ``validate_artifact_path``: ``raise <Error>(...)`` and
        ``last_err = <Error>(...)`` deferred-raise sites. The bare
        ``raise last_err`` propagation is intentionally excluded — it
        carries no gate-decision logic of its own; the decision lives
        at the ``last_err = ...`` assignment.
      - ``check_synth_stable`` and ``check_artifact_stable``:
        tuple-return sites whose first element is one of
        ``{"absent", "mismatch", "read_failed", "ok"}``. The verifier
        carries a single ``# gate-class: advisory`` annotation that
        classifies the function as a gate-as-a-whole; the parity check
        asserts that at least one such tuple-return site within the
        function has the annotation in its in-scope window (i.e. the
        annotation has not drifted away from the return it precedes).

    Failure modes detected:
      - A new gate added to ``validate_artifact_path`` without an
        accompanying ``# gate-class:`` annotation.
      - An existing annotation removed from any of the 5 site
        annotations in ``validate_artifact_path`` (Task 4 sites) or
        either of the 2 verifier annotations (Task 3 sites).
      - An annotation whose class value falls outside the closed set
        (e.g. ``# gate-class: low-priority`` or a bare
        ``# gate-class:``).

    The named failure message ``Gate-class parity violated`` matches the
    spec's Requirement 2(a) acceptance criterion so the failure is
    grep-discoverable from CI output.
    """
    # --- validate_artifact_path: every site needs its own annotation.
    validate_source = _get_function_source("validate_artifact_path")
    validate_lines = validate_source.split("\n")
    validate_sites = list(_VALIDATE_SITE_RE.finditer(validate_source))
    assert validate_sites, (
        "Gate-class parity violated — walker found zero raise/last_err "
        "sites in validate_artifact_path. The function should have at "
        "least one gate-decision site; the regex may be broken."
    )

    failures: list[str] = []
    for match in validate_sites:
        # Compute the 1-based line number of the site within the function source.
        line_idx = validate_source.count("\n", 0, match.start())
        site_text = validate_lines[line_idx].strip()
        gate_class = _find_annotation_in_window(validate_lines, line_idx)
        if gate_class is None:
            failures.append(
                f"validate_artifact_path site {site_text!r} (function-relative "
                f"line {line_idx + 1}) has no `# gate-class:` annotation in "
                f"the {_IN_SCOPE_WINDOW_LINES}-line preceding window."
            )
        elif gate_class not in _VALID_GATE_CLASSES:
            failures.append(
                f"validate_artifact_path site {site_text!r} (function-relative "
                f"line {line_idx + 1}) carries `# gate-class: {gate_class}` "
                f"which is not in the closed set "
                f"{sorted(_VALID_GATE_CLASSES)!r}."
            )

    # --- check_synth_stable and check_artifact_stable: at least one
    # tuple-return site in each function must carry an in-scope
    # advisory annotation. The verifier annotation classifies the
    # function as a gate-as-a-whole; placing it on a single tuple-return
    # site is the canonical idiom.
    for verifier in ("check_synth_stable", "check_artifact_stable"):
        verifier_source = _get_function_source(verifier)
        verifier_lines = verifier_source.split("\n")
        verifier_sites = list(_VERIFIER_SITE_RE.finditer(verifier_source))
        assert verifier_sites, (
            f"Gate-class parity violated — walker found zero "
            f"tuple-return sites in {verifier}. The regex may be broken."
        )

        # The verifier must have at least one annotated tuple-return
        # site, and every annotation that IS present must be from the
        # closed set.
        annotated_sites: list[tuple[int, str]] = []
        for match in verifier_sites:
            line_idx = verifier_source.count("\n", 0, match.start())
            gate_class = _find_annotation_in_window(verifier_lines, line_idx)
            if gate_class is not None:
                annotated_sites.append((line_idx, gate_class))
                if gate_class not in _VALID_GATE_CLASSES:
                    failures.append(
                        f"{verifier} site at function-relative line "
                        f"{line_idx + 1} carries `# gate-class: {gate_class}` "
                        f"which is not in the closed set "
                        f"{sorted(_VALID_GATE_CLASSES)!r}."
                    )

        if not annotated_sites:
            failures.append(
                f"{verifier} has no `# gate-class:` annotation in scope of "
                f"any tuple-return site. Per spec Requirement 2(a) and "
                f"Task 3, each verifier must carry one `# gate-class: "
                f"advisory` annotation preceding a tuple-return site."
            )

    assert not failures, (
        "Gate-class parity violated — "
        + str(len(failures))
        + " site(s) failed the closed-set annotation check:\n  - "
        + "\n  - ".join(failures)
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
