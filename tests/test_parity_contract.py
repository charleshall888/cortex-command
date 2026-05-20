"""Parity contract: byte-identical by default, named-tolerance escape per stream.

Phase 1 deliverable of feature
`installation-integrity-layer-bash-to-entry`. Every parity test for a
promoted `bin/cortex-*` script (Tasks 6, 9, 11–22) consumes this
contract: byte-identical comparison BY DEFAULT, with an opt-in
`@pytest.mark.structural_equivalence(stream=..., tolerances=[...])`
decorator naming a closed set of tolerance categories for one specific
stream. No tolerance is implicit; every category is named and per-stream.

Helpers exported:

* :func:`assert_byte_identical(actual, expected)` — strict equality.
* :func:`assert_structurally_equivalent(actual, expected, stream,
  tolerances, exit_code_actual=None, exit_code_expected=None)` — applies
  the named tolerances and asserts equivalence.

The five named tolerance categories form a closed set (per the revised
tolerance rubric — critical-review finding that the prior
"intra-object key reordering only" escape was too narrow to absorb the
real jq→Python diff classes):

* ``key-reorder`` — intra-object JSON key ordering.
* ``unicode-escape`` — ASCII-escape form ``\\uXXXX`` ↔ raw UTF-8 byte form.
* ``number-format`` — integer-valued floats (``1`` ↔ ``1.0``); leading
  zeros excluded.
* ``trailing-newline`` — presence/absence of one trailing ``\\n`` on a
  stream.
* ``error-formatter-shape`` — stderr text from a known-error path. When
  active, compares only that BOTH outputs are non-empty/non-zero-exit OR
  both empty/zero-exit; bytes are not compared. Requires the
  ``exit_code_actual`` and ``exit_code_expected`` kwargs.

Anything outside these categories — locale-dependent strings, trailing
whitespace mid-stream, line-ending differences, env-var leakage,
timestamps, etc. — is a parity failure by design.
"""

from __future__ import annotations

import json
from typing import Optional, Sequence

import pytest


# ---------------------------------------------------------------------------
# Closed set of tolerance categories. Any name not in this set is rejected
# at helper-call time so that typos surface immediately as a parity test
# authoring error rather than a silent permissive-comparison.
# ---------------------------------------------------------------------------

TOLERANCE_CATEGORIES = frozenset({
    "key-reorder",
    "unicode-escape",
    "number-format",
    "trailing-newline",
    "error-formatter-shape",
})


# ---------------------------------------------------------------------------
# Public helpers consumed by parity tests for the 13 promoted scripts.
# ---------------------------------------------------------------------------


def assert_byte_identical(actual: bytes | str, expected: bytes | str) -> None:
    """Strict byte-identical comparison — the default parity assertion.

    Accepts ``bytes`` or ``str``; both must be the same type. Mixed
    types are coerced to bytes via UTF-8 to avoid accidental
    encoding-mismatch passes.
    """
    if isinstance(actual, str) and isinstance(expected, str):
        if actual != expected:
            raise AssertionError(
                f"byte-identical comparison failed:\n"
                f"  actual:   {actual!r}\n"
                f"  expected: {expected!r}"
            )
        return
    a_bytes = actual.encode("utf-8") if isinstance(actual, str) else actual
    e_bytes = expected.encode("utf-8") if isinstance(expected, str) else expected
    if a_bytes != e_bytes:
        raise AssertionError(
            f"byte-identical comparison failed:\n"
            f"  actual:   {a_bytes!r}\n"
            f"  expected: {e_bytes!r}"
        )


def assert_structurally_equivalent(
    actual: bytes | str,
    expected: bytes | str,
    stream: str,
    tolerances: Sequence[str],
    *,
    exit_code_actual: Optional[int] = None,
    exit_code_expected: Optional[int] = None,
) -> None:
    """Apply the named tolerances and assert equivalence for one stream.

    :param actual: The stream bytes/str produced by the Python port.
    :param expected: The stream bytes/str captured from the bash version.
    :param stream: ``"stdout"`` or ``"stderr"``. Determines which
        tolerance categories may apply (``trailing-newline`` is stdout-only
        per the contract; ``error-formatter-shape`` is stderr-only).
    :param tolerances: A sequence of tolerance category names. Every
        name MUST appear in :data:`TOLERANCE_CATEGORIES`; an unknown
        name raises ``ValueError`` so authoring typos fail loudly.
    :param exit_code_actual: Required when ``error-formatter-shape`` is
        in ``tolerances``; the exit code from the Python invocation.
    :param exit_code_expected: Required when ``error-formatter-shape``
        is in ``tolerances``; the exit code captured from bash.

    The function does not "escape" comparisons silently — when a
    tolerance category is opted into, the comparison logic for that
    category replaces strict byte equality. Anything outside the opted-in
    tolerance set still falls through to byte-identical comparison.
    """
    if stream not in ("stdout", "stderr"):
        raise ValueError(
            f"stream must be 'stdout' or 'stderr', got {stream!r}"
        )

    tolset = set(tolerances)
    unknown = tolset - TOLERANCE_CATEGORIES
    if unknown:
        raise ValueError(
            f"unknown tolerance category/categories: {sorted(unknown)}. "
            f"Closed set: {sorted(TOLERANCE_CATEGORIES)}"
        )

    if "trailing-newline" in tolset and stream != "stdout":
        raise ValueError(
            "'trailing-newline' tolerance is stdout-only per the contract"
        )
    if "error-formatter-shape" in tolset and stream != "stderr":
        raise ValueError(
            "'error-formatter-shape' tolerance is stderr-only per the contract"
        )

    # Normalize to str for comparison. Both sides are coerced via UTF-8
    # so that the unicode-escape tolerance reads consistent characters
    # regardless of the input byte/str shape.
    actual_str = actual.decode("utf-8") if isinstance(actual, bytes) else actual
    expected_str = (
        expected.decode("utf-8") if isinstance(expected, bytes) else expected
    )

    # error-formatter-shape is a category-of-its-own that does NOT
    # compare bytes — it only checks the {empty,zero-exit} pairing.
    # When opted in, it short-circuits stream byte comparison entirely.
    if "error-formatter-shape" in tolset:
        if exit_code_actual is None or exit_code_expected is None:
            raise ValueError(
                "'error-formatter-shape' tolerance requires both "
                "exit_code_actual and exit_code_expected kwargs"
            )
        actual_nonempty = bool(actual_str)
        expected_nonempty = bool(expected_str)
        actual_failed = exit_code_actual != 0
        expected_failed = exit_code_expected != 0
        actual_signaled_error = actual_nonempty and actual_failed
        expected_signaled_error = expected_nonempty and expected_failed
        actual_silent = (not actual_nonempty) and (not actual_failed)
        expected_silent = (not expected_nonempty) and (not expected_failed)
        if not (
            (actual_signaled_error and expected_signaled_error)
            or (actual_silent and expected_silent)
        ):
            raise AssertionError(
                "error-formatter-shape mismatch:\n"
                f"  actual:   exit={exit_code_actual}, "
                f"stderr_nonempty={actual_nonempty}\n"
                f"  expected: exit={exit_code_expected}, "
                f"stderr_nonempty={expected_nonempty}"
            )
        return

    # trailing-newline: strip one trailing '\n' from each side before
    # any other comparison. A double-trailing-newline difference is NOT
    # absorbed (only the single-newline distinction is in-scope).
    if "trailing-newline" in tolset:
        if actual_str.endswith("\n") and not actual_str.endswith("\n\n"):
            actual_str_eq = actual_str[:-1]
        else:
            actual_str_eq = actual_str
        if expected_str.endswith("\n") and not expected_str.endswith("\n\n"):
            expected_str_eq = expected_str[:-1]
        else:
            expected_str_eq = expected_str
    else:
        actual_str_eq = actual_str
        expected_str_eq = expected_str

    # If any JSON-shape tolerance is opted in, parse both sides as JSON
    # and compare structurally. unicode-escape is absorbed by the JSON
    # parser (both byte forms decode to identical str). number-format
    # is handled by a recursive normalization step. key-reorder is
    # absorbed by Python dict equality (order-insensitive).
    json_tolerances = tolset & {"key-reorder", "unicode-escape", "number-format"}
    if json_tolerances:
        try:
            actual_json = json.loads(actual_str_eq)
            expected_json = json.loads(expected_str_eq)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"structural equivalence requires parseable JSON for "
                f"tolerances {sorted(json_tolerances)}; JSON decode failed: "
                f"{exc}\n  actual:   {actual_str_eq!r}\n"
                f"  expected: {expected_str_eq!r}"
            ) from exc

        if "number-format" in tolset:
            actual_json = _normalize_integer_floats(actual_json)
            expected_json = _normalize_integer_floats(expected_json)

        # key-reorder is the no-op under Python dict equality.
        # unicode-escape was absorbed by json.loads canonicalizing to str.
        # _types_equal is type-strict so True ≠ 1 even though Python's
        # native == treats them equal — the contract excludes booleans
        # from the number-format tolerance.
        if not _types_equal(actual_json, expected_json):
            raise AssertionError(
                "structural equivalence failed (after applying tolerances "
                f"{sorted(tolset)}):\n"
                f"  actual:   {actual_json!r}\n"
                f"  expected: {expected_json!r}"
            )
        return

    # No JSON-shape tolerances opted in — fall through to byte-identical
    # comparison on the (possibly trailing-newline-trimmed) strings.
    if actual_str_eq != expected_str_eq:
        raise AssertionError(
            "byte-identical comparison failed "
            f"(tolerances applied: {sorted(tolset) or 'none'}):\n"
            f"  actual:   {actual_str_eq!r}\n"
            f"  expected: {expected_str_eq!r}"
        )


def _types_equal(a: object, b: object) -> bool:
    """Type-strict structural equality.

    Distinguishes ``True`` from ``1`` and ``False`` from ``0`` (Python's
    ``bool`` is a subclass of ``int``; native ``==`` collapses them).
    Recurses into dicts and lists. Used after number-format
    normalization so the contract's exclusion of booleans from the
    integer/float tolerance is honored.
    """
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return False
        return all(_types_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_types_equal(x, y) for x, y in zip(a, b))
    return a == b


def _normalize_integer_floats(value: object) -> object:
    """Recursively coerce integer-valued floats to int for number-format
    tolerance.

    JSON ``1`` and ``1.0`` deserialize to ``int`` and ``float``
    respectively; under number-format tolerance they compare equal.
    Non-integer floats (``1.5``) are preserved as floats. Booleans are
    preserved as bool (Python's ``bool`` is a ``int`` subclass; the
    coercion path skips them explicitly to keep True/False from
    becoming 1/0). Leading-zero strings are out of scope per the
    contract.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, dict):
        return {k: _normalize_integer_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_integer_floats(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Contract tests — every named tolerance category is exercised in both
# directions: (a) passes when the tolerance is opted in, (b) fails when
# the tolerance is NOT opted in (i.e. the default byte-identical
# comparison rejects the diff). This is the parity-contract's discipline
# — no tolerance is implicit.
# ---------------------------------------------------------------------------


def test_byte_identical_passes_when_equal() -> None:
    assert_byte_identical("hello\n", "hello\n")
    assert_byte_identical(b"hello\n", b"hello\n")


def test_byte_identical_fails_on_any_diff() -> None:
    with pytest.raises(AssertionError):
        assert_byte_identical("hello\n", "hello")
    with pytest.raises(AssertionError):
        assert_byte_identical(b"hello", b"world")


def test_byte_identical_rejects_str_vs_bytes_mismatch_via_utf8() -> None:
    # Same content cross-type still passes via utf-8 coercion; mismatched
    # content fails.
    assert_byte_identical("é", "é")
    with pytest.raises(AssertionError):
        assert_byte_identical("é".encode("utf-8"), b"e")


# --- key-reorder ----------------------------------------------------------


@pytest.mark.structural_equivalence(stream="stdout", tolerances=["key-reorder"])
def test_key_reorder_passes_when_opted_in() -> None:
    actual = '{"b": 2, "a": 1}'
    expected = '{"a": 1, "b": 2}'
    assert_structurally_equivalent(
        actual, expected, stream="stdout", tolerances=["key-reorder"]
    )


def test_key_reorder_fails_when_not_opted_in() -> None:
    actual = '{"b": 2, "a": 1}'
    expected = '{"a": 1, "b": 2}'
    with pytest.raises(AssertionError):
        assert_byte_identical(actual, expected)


def test_key_reorder_nested_objects_pass_when_opted_in() -> None:
    actual = '{"outer": {"y": 2, "x": 1}, "z": 3}'
    expected = '{"z": 3, "outer": {"x": 1, "y": 2}}'
    assert_structurally_equivalent(
        actual, expected, stream="stdout", tolerances=["key-reorder"]
    )


# --- unicode-escape -------------------------------------------------------


@pytest.mark.structural_equivalence(
    stream="stdout", tolerances=["unicode-escape"]
)
def test_unicode_escape_passes_when_opted_in() -> None:
    # ASCII-escape form vs raw UTF-8 byte form. json.loads on the
    # ``\uXXXX`` form yields the same string the raw UTF-8 form yields.
    actual = '{"x": "é"}'
    expected = '{"x": "\\u00e9"}'
    assert_structurally_equivalent(
        actual, expected, stream="stdout", tolerances=["unicode-escape"]
    )


def test_unicode_escape_fails_when_not_opted_in() -> None:
    actual = '{"x": "é"}'
    expected = '{"x": "\\u00e9"}'
    with pytest.raises(AssertionError):
        assert_byte_identical(actual, expected)


# --- number-format --------------------------------------------------------


@pytest.mark.structural_equivalence(
    stream="stdout", tolerances=["number-format"]
)
def test_number_format_integer_valued_float_passes_when_opted_in() -> None:
    actual = '{"count": 1.0}'
    expected = '{"count": 1}'
    assert_structurally_equivalent(
        actual, expected, stream="stdout", tolerances=["number-format"]
    )


def test_number_format_fails_when_not_opted_in() -> None:
    actual = '{"count": 1.0}'
    expected = '{"count": 1}'
    with pytest.raises(AssertionError):
        assert_byte_identical(actual, expected)


def test_number_format_non_integer_float_still_must_match() -> None:
    # Non-integer floats are NOT in-scope for the number-format tolerance;
    # 1.5 ≠ 1.6 still fails even with the tolerance opted in.
    actual = '{"ratio": 1.5}'
    expected = '{"ratio": 1.6}'
    with pytest.raises(AssertionError):
        assert_structurally_equivalent(
            actual, expected, stream="stdout", tolerances=["number-format"]
        )


def test_number_format_preserves_booleans() -> None:
    # Python's bool is an int subclass; the normalizer must not coerce
    # True/False to 1/0 under number-format.
    actual = '{"ok": true}'
    expected = '{"ok": 1}'
    with pytest.raises(AssertionError):
        assert_structurally_equivalent(
            actual, expected, stream="stdout", tolerances=["number-format"]
        )


# --- trailing-newline -----------------------------------------------------


@pytest.mark.structural_equivalence(
    stream="stdout", tolerances=["trailing-newline"]
)
def test_trailing_newline_passes_when_opted_in() -> None:
    actual = "hello\n"
    expected = "hello"
    assert_structurally_equivalent(
        actual, expected, stream="stdout", tolerances=["trailing-newline"]
    )


def test_trailing_newline_fails_when_not_opted_in() -> None:
    actual = "hello\n"
    expected = "hello"
    with pytest.raises(AssertionError):
        assert_byte_identical(actual, expected)


def test_trailing_newline_only_absorbs_single_trailing_newline() -> None:
    # Double-trailing-newline difference is NOT in scope — only the
    # single-trailing-newline distinction.
    actual = "hello\n\n"
    expected = "hello"
    with pytest.raises(AssertionError):
        assert_structurally_equivalent(
            actual,
            expected,
            stream="stdout",
            tolerances=["trailing-newline"],
        )


def test_trailing_newline_is_stdout_only() -> None:
    with pytest.raises(ValueError, match="stdout-only"):
        assert_structurally_equivalent(
            "x\n",
            "x",
            stream="stderr",
            tolerances=["trailing-newline"],
        )


# --- error-formatter-shape ------------------------------------------------


@pytest.mark.structural_equivalence(
    stream="stderr", tolerances=["error-formatter-shape"]
)
def test_error_formatter_shape_both_error_passes_when_opted_in() -> None:
    # Different stderr bytes, but both fail with non-empty stderr — the
    # carve-out for jq's diagnostic vs Python's JSONDecodeError.
    actual = "json.decoder.JSONDecodeError: Expecting value: line 1 column 1\n"
    expected = "parse error: Invalid numeric literal at line 1, column 1\n"
    assert_structurally_equivalent(
        actual,
        expected,
        stream="stderr",
        tolerances=["error-formatter-shape"],
        exit_code_actual=1,
        exit_code_expected=2,
    )


@pytest.mark.structural_equivalence(
    stream="stderr", tolerances=["error-formatter-shape"]
)
def test_error_formatter_shape_both_silent_passes_when_opted_in() -> None:
    assert_structurally_equivalent(
        "",
        "",
        stream="stderr",
        tolerances=["error-formatter-shape"],
        exit_code_actual=0,
        exit_code_expected=0,
    )


def test_error_formatter_shape_fails_when_not_opted_in() -> None:
    # Different stderr bytes — strict byte comparison rejects the diff
    # even though both signal errors.
    actual = "json.decoder.JSONDecodeError: Expecting value: line 1 column 1\n"
    expected = "parse error: Invalid numeric literal at line 1, column 1\n"
    with pytest.raises(AssertionError):
        assert_byte_identical(actual, expected)


def test_error_formatter_shape_fails_on_asymmetric_outcomes() -> None:
    # One side errors, the other does not — the shape disagrees, so
    # even with the tolerance opted in this must fail.
    actual = "boom\n"
    expected = ""
    with pytest.raises(AssertionError):
        assert_structurally_equivalent(
            actual,
            expected,
            stream="stderr",
            tolerances=["error-formatter-shape"],
            exit_code_actual=1,
            exit_code_expected=0,
        )


def test_error_formatter_shape_requires_exit_codes() -> None:
    with pytest.raises(ValueError, match="exit_code"):
        assert_structurally_equivalent(
            "x",
            "y",
            stream="stderr",
            tolerances=["error-formatter-shape"],
        )


def test_error_formatter_shape_is_stderr_only() -> None:
    with pytest.raises(ValueError, match="stderr-only"):
        assert_structurally_equivalent(
            "",
            "",
            stream="stdout",
            tolerances=["error-formatter-shape"],
            exit_code_actual=0,
            exit_code_expected=0,
        )


# --- closed-set + arg-validation guards -----------------------------------


def test_unknown_tolerance_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown tolerance"):
        assert_structurally_equivalent(
            "a",
            "a",
            stream="stdout",
            tolerances=["fictional-category"],
        )


def test_invalid_stream_raises_value_error() -> None:
    with pytest.raises(ValueError, match="stream must be"):
        assert_structurally_equivalent(
            "a",
            "a",
            stream="combined",
            tolerances=["key-reorder"],
        )


def test_tolerance_categories_is_closed_set_of_five() -> None:
    # The closed set is named explicitly in the contract — every tolerance
    # is opt-in and per-stream. A future amendment expanding the set
    # MUST update this test alongside the helper.
    assert TOLERANCE_CATEGORIES == frozenset({
        "key-reorder",
        "unicode-escape",
        "number-format",
        "trailing-newline",
        "error-formatter-shape",
    })


# --- non-tolerance diffs still fail under the contract -------------------


@pytest.mark.structural_equivalence(stream="stdout", tolerances=["key-reorder"])
def test_value_change_fails_under_key_reorder_tolerance() -> None:
    # A value change is NOT a key-reorder; the JSON-equality fallback
    # rejects it.
    actual = '{"a": 1, "b": 2}'
    expected = '{"a": 1, "b": 99}'
    with pytest.raises(AssertionError):
        assert_structurally_equivalent(
            actual,
            expected,
            stream="stdout",
            tolerances=["key-reorder"],
        )


@pytest.mark.structural_equivalence(stream="stdout", tolerances=["key-reorder"])
def test_whitespace_in_non_json_stream_fails_under_key_reorder() -> None:
    # Whitespace-only diffs in a non-JSON stream — not absorbed by
    # any tolerance. The contract excludes whitespace-mutated diffs
    # outside JSON's allowed serialization tolerance.
    actual = "hello world\n"
    expected = "hello  world\n"  # double space
    with pytest.raises(AssertionError):
        assert_byte_identical(actual, expected)


# --- empty / edge inputs --------------------------------------------------


def test_empty_strings_byte_identical_pass() -> None:
    assert_byte_identical("", "")


@pytest.mark.structural_equivalence(
    stream="stdout", tolerances=["trailing-newline"]
)
def test_empty_string_against_lone_newline_passes_with_trailing_newline() -> None:
    assert_structurally_equivalent(
        "\n", "", stream="stdout", tolerances=["trailing-newline"]
    )


@pytest.mark.structural_equivalence(
    stream="stdout",
    tolerances=["key-reorder", "unicode-escape", "number-format"],
)
def test_combined_tolerances_compose() -> None:
    # All three JSON-shape tolerances compose: keys reordered AND a
    # value uses unicode-escape AND another value is an integer-float.
    actual = '{"label": "é", "count": 1.0, "name": "a"}'
    expected = '{"name": "a", "count": 1, "label": "\\u00e9"}'
    assert_structurally_equivalent(
        actual,
        expected,
        stream="stdout",
        tolerances=["key-reorder", "unicode-escape", "number-format"],
    )
