"""Parity test: cortex_command.backlog.resolve_item vs bash cortex-resolve-backlog-item.

Golden-replay fixture test asserting that the Python wheel-tier port produces
byte-identical output (or, for the two cases whose output embeds live backlog
data, structurally-asserted output) on stdout, stderr, and exit code compared
to the captured bash/PEP-723 original.

Each fixture case in tests/fixtures/cortex-resolve-backlog-item/ is stored as
flat sibling files:
  <case>.argv      one argv element per line (line 1 is sys.argv[1])
  <case>.stdin     literal bytes to pipe to stdin (empty for all current cases)
  <case>.stdout    captured stdout bytes
  <case>.stderr    captured stderr bytes
  <case>.exitcode  decimal exit status + trailing newline

Most cases carry the full five-file quintuple. The two structurally-asserted
cases below OMIT their de-pinned snapshot: title_phrase_ambiguous has no
.stderr file and numeric_unambiguous has no .stdout file (both removed as
drift sources). Their .argv/.exitcode/.stdin and the empty sibling stream
remain, so the cases stay discovered (_discover_cases globs *.argv) and their
other streams stay byte-exact.

Three golden-replay cases are defined (exit codes 0/2/3):
  numeric_unambiguous     — numeric ID resolves to one match (exit 0, JSON stdout)
  title_phrase_ambiguous  — title phrase resolves to >1 matches (exit 2, candidates stderr)
  no_match                — input matches nothing (exit 3, stderr message)

Structural exceptions (Abseil Tip #135 — test the contract, not the
implementation): title_phrase_ambiguous (stderr) and numeric_unambiguous
(stdout) embed live backlog data — the ambiguous match count plus candidate
listing, and item 252's live title — so they are asserted STRUCTURALLY against
live output (format/shape pinned; the incidental count, titles, and ordering
deliberately not pinned) rather than byte-compared. This evolves these two
cases from byte-exact migration snapshots toward format-contract regression
guards; the rationale is recorded here and in the fixture README.

no_match's stderr (`no match for '<input>'`) echoes only the input argument,
is independent of backlog content, and is the one case still reproduced
byte-for-byte.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_parity_contract import assert_byte_identical


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-resolve-backlog-item"
BACKLOG_DIR = REPO_ROOT / "cortex" / "backlog"

# Determinism env-var overrides mirroring the capture harness (see README).
_DETERMINISM_ENV_OVERRIDES: dict[str, str] = {
    "LC_ALL": "C",
    "TZ": "UTC",
    "CORTEX_BACKLOG_DIR": str(BACKLOG_DIR),
}


# ---------------------------------------------------------------------------
# Fixture discovery helpers
# ---------------------------------------------------------------------------


def _discover_cases() -> list[str]:
    """Return sorted list of case names present in the fixture directory."""
    cases: list[str] = []
    for path in FIXTURE_DIR.glob("*.argv"):
        cases.append(path.stem)
    return sorted(cases)


def _read_argv(case: str) -> list[str]:
    """Parse <case>.argv: one element per line (strip trailing newlines)."""
    text = (FIXTURE_DIR / f"{case}.argv").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line]


def _read_stdin(case: str) -> bytes:
    """Read <case>.stdin as raw bytes (may be empty)."""
    return (FIXTURE_DIR / f"{case}.stdin").read_bytes()


def _read_expected_stdout(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdout").read_bytes()


def _read_expected_stderr(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stderr").read_bytes()


def _read_expected_exitcode(case: str) -> int:
    text = (FIXTURE_DIR / f"{case}.exitcode").read_text(encoding="utf-8").strip()
    return int(text)


# ---------------------------------------------------------------------------
# Environment construction
# ---------------------------------------------------------------------------


def _build_env() -> dict[str, str]:
    """Build a deterministic environment for fixture invocations.

    Inherits the current process environment (so Python itself is reachable),
    then applies determinism overrides and the CORTEX_BACKLOG_DIR pointing to
    the repo's committed backlog state at fixture-capture time.
    """
    env = dict(os.environ)
    env.update(_DETERMINISM_ENV_OVERRIDES)
    return env


# ---------------------------------------------------------------------------
# Invocation helper (cached per case)
# ---------------------------------------------------------------------------

_result_cache: dict[str, subprocess.CompletedProcess] = {}


def _invoke_case(case: str) -> subprocess.CompletedProcess:
    """Run python3 -m cortex_command.backlog.resolve_item for the given fixture case.

    Results are memoized per case because stdout, stderr, and exitcode tests
    all share the same invocation.
    """
    if case in _result_cache:
        return _result_cache[case]

    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)
    env = _build_env()

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.resolve_item"] + argv,
        input=stdin_bytes,
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
    )

    _result_cache[case] = result
    return result


# ---------------------------------------------------------------------------
# Structural assertion helpers (drift-immune; see fixture README + plan #276)
# ---------------------------------------------------------------------------


def _assert_ambiguous_stderr_structure(result: subprocess.CompletedProcess) -> None:
    """Assert the ``ambiguous: N matches`` stderr *format* against live output.

    Pins the format contract of ``_format_candidates`` (header, candidate
    ``filename<TAB>title`` shape, and the ``... (N-5 more)`` truncation
    arithmetic) without byte-pinning the volatile match count or titles, which
    drift whenever a "lifecycle"-titled backlog item is added or removed.
    """
    assert result.returncode == 2, f"expected exit 2, got {result.returncode}"
    lines = result.stderr.decode("utf-8").splitlines()
    assert lines, "expected non-empty stderr"

    header = re.match(r"^ambiguous: (\d+) matches$", lines[0])
    assert header is not None, f"header line did not match: {lines[0]!r}"
    n = int(header.group(1))
    assert n > 1, f"ambiguous case requires N > 1, got {n}"

    expected_candidates = min(n, 5)
    candidate_lines = lines[1 : 1 + expected_candidates]
    assert len(candidate_lines) == expected_candidates, (
        f"expected {expected_candidates} candidate lines, got {len(candidate_lines)}"
    )
    for cand in candidate_lines:
        filename, tab, title = cand.partition("\t")
        assert tab == "\t", f"candidate line missing TAB separator: {cand!r}"
        assert filename.endswith(".md"), f"candidate filename not .md: {filename!r}"
        assert title, f"candidate title empty: {cand!r}"

    remaining = lines[1 + expected_candidates :]
    if n > 5:
        assert len(remaining) == 1, f"expected one truncation line, got {remaining!r}"
        trunc = re.match(r"^\.\.\. \((\d+) more\)$", remaining[0])
        assert trunc is not None, f"truncation line did not match: {remaining[0]!r}"
        assert int(trunc.group(1)) == n - 5, (
            f"truncation count {trunc.group(1)} != {n - 5}"
        )
    else:
        assert not remaining, f"unexpected trailing lines for N<=5: {remaining!r}"


def _assert_numeric_stdout_structure(result: subprocess.CompletedProcess) -> None:
    """Assert the resolved-JSON *shape* for the numeric case against live output.

    Pins the exit-0 object's key set and the ``252-`` id prefix without
    byte-pinning item 252's live title, which drifts if the item is retitled.
    Slug-priority is covered by ``tests/test_resolve_backlog_item.py``.
    """
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}"
    payload = json.loads(result.stdout)
    for key in ("filename", "backlog_filename_slug", "title", "lifecycle_slug"):
        assert key in payload, f"missing key {key!r} in {payload!r}"
    assert re.match(r"^252-", payload["filename"]), payload["filename"]
    assert re.match(r"^252-", payload["backlog_filename_slug"]), (
        payload["backlog_filename_slug"]
    )
    assert isinstance(payload["title"], str) and payload["title"], (
        "title must be a non-empty str"
    )
    assert payload["lifecycle_slug"], "lifecycle_slug must be present and non-empty"


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str) -> None:
    """Exit code matches the fixture capture."""
    expected_exitcode = _read_expected_exitcode(case)
    result = _invoke_case(case)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}"
    )


@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_parity(case: str) -> None:
    """stderr is byte-identical to the fixture capture, except for the
    structurally-asserted ``title_phrase_ambiguous`` case.

    ``no_match``'s stderr is a fixed-format string reproduced byte-for-byte.
    ``title_phrase_ambiguous`` embeds the live ambiguous-match count and a
    candidate listing, so it is asserted *structurally* against live output
    rather than byte-compared (its ``.stderr`` snapshot is de-pinned). The
    structural branch runs first so the deleted snapshot is never read.
    """
    if case == "title_phrase_ambiguous":
        _assert_ambiguous_stderr_structure(_invoke_case(case))
        return
    expected_stderr = _read_expected_stderr(case)
    actual_stderr = _invoke_case(case).stderr
    assert_byte_identical(actual_stderr, expected_stderr)


def test_ambiguous_structure_rejects_malformed() -> None:
    """No-op-freedom guard: the ambiguous structural assertion must reject real
    ``_format_candidates`` regressions, not merely confirm a non-empty stderr.

    Feeds crafted bad stderr (reworded header, space-for-TAB separator, wrong
    truncation count) and asserts each raises ``AssertionError``; one
    well-formed sample must pass. This is the automatable realization of the
    spec's mutation-resistance requirement (no resolver mutation needed).
    """

    def _cp(stderr: str, returncode: int = 2) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=b"", stderr=stderr.encode("utf-8")
        )

    candidates = "\n".join(f"00{i}-item.md\tTitle {i}" for i in range(1, 6))
    good = f"ambiguous: 7 matches\n{candidates}\n... (2 more)"
    _assert_ambiguous_stderr_structure(_cp(good))  # must not raise

    bad_header = f"ambig: 7 match\n{candidates}\n... (2 more)"
    bad_separator = (
        "ambiguous: 7 matches\n"
        + "\n".join(f"00{i}-item.md Title {i}" for i in range(1, 6))
        + "\n... (2 more)"
    )
    bad_truncation = f"ambiguous: 7 matches\n{candidates}\n... (99 more)"
    for bad in (bad_header, bad_separator, bad_truncation):
        with pytest.raises(AssertionError):
            _assert_ambiguous_stderr_structure(_cp(bad))


@pytest.mark.parametrize("case", _discover_cases())
def test_stdout_parity(case: str) -> None:
    """stdout is byte-identical except for the structurally-asserted numeric case.

    ``numeric_unambiguous`` (exit 0, JSON) is asserted *structurally* (key set +
    ``252-`` id prefix) because its stdout embeds item 252's live title; its
    ``.stdout`` snapshot is de-pinned. The structural branch runs first so the
    deleted snapshot is never read. All other cases have empty stdout and stay
    byte-identical.
    """
    if case == "numeric_unambiguous":
        _assert_numeric_stdout_structure(_invoke_case(case))
        return
    expected_stdout = _read_expected_stdout(case)
    actual_stdout = _invoke_case(case).stdout
    assert_byte_identical(actual_stdout, expected_stdout)


# ---------------------------------------------------------------------------
# Edge-case suite — exercises exit codes 64 and 70 (not in golden-replay
# fixtures per the README, but covered here to complete the contract).
# ---------------------------------------------------------------------------


def _invoke_with_argv(argv: list[str], env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run the module directly with the given argv list."""
    env = _build_env()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.resolve_item"] + argv,
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
    )


def test_exit_64_empty_input() -> None:
    """Empty string input produces exit code 64 (usage error)."""
    result = _invoke_with_argv([""])
    assert result.returncode == 64, (
        f"expected exit 64 for empty input, got {result.returncode}"
    )
    assert result.stderr, "expected non-empty stderr for usage error"


def test_exit_64_whitespace_input() -> None:
    """Whitespace-only input produces exit code 64 (usage error)."""
    result = _invoke_with_argv(["   "])
    assert result.returncode == 64, (
        f"expected exit 64 for whitespace input, got {result.returncode}"
    )


def test_exit_70_missing_backlog_dir() -> None:
    """Missing backlog directory produces exit code 70 (software/IO error)."""
    result = _invoke_with_argv(
        ["some-item"],
        env_overrides={"CORTEX_BACKLOG_DIR": "/nonexistent/backlog/dir/xyz"},
    )
    assert result.returncode == 70, (
        f"expected exit 70 for missing backlog dir, got {result.returncode}"
    )
    assert result.stderr, "expected non-empty stderr for missing backlog dir"
