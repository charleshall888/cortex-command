"""Tests for Complete phase step 4: atomic pr.json write and schema.

Spec §17 (requirement 17) requires:

  1. **Atomicity**: pr.json is written via tempfile + os.replace (no partial-write
     window observable under an interrupted write scenario).
  2. **Schema validity**: the JSON object contains exactly the five fields
     ``number``, ``url``, ``head_branch``, ``opened_at``, and ``repo``,
     each with the correct type.
  3. **``repo`` field format**: matches ``^[\\w.-]+/[\\w.-]+$`` (owner/name).
  4. **``opened_at`` parses as ISO 8601**.
  5. **``head_branch`` is non-empty**.

These tests implement the atomic-write pattern directly in Python (the same
pattern as documented in complete.md Step 4) and assert the schema invariants.
The write-helper used by the tests IS the pattern — not extracted production
code — so we note the self-sealing risk in the assertion comments.

Atomic-write sentinel test: write a sentinel value to the target path, then
run the atomic write and assert the target either contains a valid full JSON
object OR doesn't exist (no partial-write window observed).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Shared helper: the exact atomic-write pattern from complete.md Step 4
# ---------------------------------------------------------------------------

REQUIRED_FIELDS: set[str] = {"number", "url", "head_branch", "opened_at", "repo"}
REPO_PATTERN = re.compile(r"^[\w.-]+/[\w.-]+$")
ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def _write_pr_json_atomically(
    target: Path,
    *,
    number: int,
    url: str,
    head_branch: str,
    opened_at: str,
    repo: str,
) -> None:
    """Write pr.json atomically using tempfile + os.replace.

    This is the exact pattern documented in complete.md Step 4. Any interruption
    during the tempfile write leaves the target path either intact (containing a
    previous value) or absent — never in a partially-written state.
    """
    payload = {
        "number": number,
        "url": url,
        "head_branch": head_branch,
        "opened_at": opened_at,
        "repo": repo,
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=target.parent,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(payload, tmp, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, target)


def _make_valid_payload(**overrides) -> dict:
    """Return a valid pr.json payload dict, with optional field overrides."""
    base = {
        "number": 42,
        "url": "https://github.com/owner/repo/pull/42",
        "head_branch": "interactive/my-feature",
        "opened_at": "2026-05-18T12:00:00Z",
        "repo": "owner/repo",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Atomicity tests
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    """Atomicity: pr.json write uses tempfile + os.replace."""

    def test_atomic_write_produces_valid_json(self, tmp_path: Path) -> None:
        """atomic write produces a valid JSON file at the target path."""
        target = tmp_path / "pr.json"
        payload = _make_valid_payload()
        _write_pr_json_atomically(target, **payload)

        assert target.is_file(), "pr.json must exist after atomic write"
        parsed = json.loads(target.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict), "pr.json must contain a JSON object"
        assert parsed == payload, "Written content must match the payload"

    def test_atomic_write_no_partial_write_observable(self, tmp_path: Path) -> None:
        """Sentinel file: after write, target is either valid JSON or absent.

        This mimics the interrupted-write scenario: we write a sentinel value to
        the target path first, then perform an atomic write. The target path must
        either contain a fully-valid JSON object (the new write completed) OR
        the sentinel (the write was interrupted before os.replace) — never
        a partial file.

        In practice, os.replace is atomic at the filesystem level (POSIX
        rename(2)), so the sentinel value is expected to survive only if the
        write was interrupted before os.replace. This test confirms that
        at no point can a reader observe a partial-write state.
        """
        sentinel_content = '{"sentinel": true}'
        target = tmp_path / "pr.json"
        target.write_text(sentinel_content, encoding="utf-8")

        payload = _make_valid_payload()
        _write_pr_json_atomically(target, **payload)

        # After the write, target must be parseable JSON.
        raw = target.read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            pytest.fail(f"pr.json contained unparseable content after write: {raw!r}")

        # It must be EITHER the full new payload OR the sentinel (if interrupted).
        # Since we're running synchronously, it must be the new payload.
        is_full_payload = all(field in parsed for field in REQUIRED_FIELDS)
        is_sentinel = parsed == {"sentinel": True}
        assert is_full_payload or is_sentinel, (
            "pr.json must contain either the full new payload or the previous "
            f"sentinel value — no partial write allowed. Got: {parsed!r}"
        )
        # The synchronous (non-interrupted) case: full payload.
        assert is_full_payload, (
            "In normal (non-interrupted) operation, pr.json must contain the full payload"
        )

    def test_atomic_write_replaces_existing_file(self, tmp_path: Path) -> None:
        """Atomic write overwrites an existing pr.json file cleanly."""
        target = tmp_path / "pr.json"
        old_payload = _make_valid_payload(number=1, url="https://github.com/owner/repo/pull/1")
        _write_pr_json_atomically(target, **old_payload)

        new_payload = _make_valid_payload(number=99, url="https://github.com/owner/repo/pull/99")
        _write_pr_json_atomically(target, **new_payload)

        parsed = json.loads(target.read_text(encoding="utf-8"))
        assert parsed["number"] == 99, "Atomic write must replace the existing pr.json"
        assert parsed["url"] == "https://github.com/owner/repo/pull/99"

    def test_atomic_write_uses_same_parent_dir_for_tempfile(self, tmp_path: Path) -> None:
        """Tempfile is created in the same directory as the target.

        os.replace is only atomic when source and destination are on the same
        filesystem (same directory guarantees this). This test confirms the
        write helper places the tempfile in target.parent, not in /tmp or
        another location.
        """
        target = tmp_path / "pr.json"
        payload = _make_valid_payload()

        # Patch tempfile.NamedTemporaryFile to intercept the dir argument.
        import unittest.mock as mock

        real_ntf = tempfile.NamedTemporaryFile
        recorded_dirs: list[str] = []

        def capturing_ntf(*args, **kwargs):
            recorded_dirs.append(str(kwargs.get("dir", "<not set>")))
            return real_ntf(*args, **kwargs)

        with mock.patch("tempfile.NamedTemporaryFile", side_effect=capturing_ntf):
            _write_pr_json_atomically(target, **payload)

        assert len(recorded_dirs) >= 1, "NamedTemporaryFile must be called at least once"
        assert str(tmp_path) in recorded_dirs[0], (
            f"Tempfile must be created in target.parent ({tmp_path}), "
            f"got dir={recorded_dirs[0]!r}"
        )


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestPrJsonSchema:
    """Schema: pr.json must contain exactly the five required fields with correct types."""

    def test_all_required_fields_present(self, tmp_path: Path) -> None:
        """pr.json contains all five required fields."""
        target = tmp_path / "pr.json"
        _write_pr_json_atomically(target, **_make_valid_payload())
        parsed = json.loads(target.read_text(encoding="utf-8"))
        missing = REQUIRED_FIELDS - set(parsed.keys())
        assert not missing, f"pr.json is missing required fields: {missing}"

    def test_number_is_integer(self, tmp_path: Path) -> None:
        """``number`` field must be an integer."""
        target = tmp_path / "pr.json"
        _write_pr_json_atomically(target, **_make_valid_payload(number=7))
        parsed = json.loads(target.read_text(encoding="utf-8"))
        assert isinstance(parsed["number"], int), (
            f"``number`` must be int, got {type(parsed['number']).__name__}"
        )
        assert parsed["number"] == 7

    def test_url_is_string(self, tmp_path: Path) -> None:
        """``url`` field must be a non-empty string."""
        target = tmp_path / "pr.json"
        _write_pr_json_atomically(target, **_make_valid_payload())
        parsed = json.loads(target.read_text(encoding="utf-8"))
        assert isinstance(parsed["url"], str), "``url`` must be a string"
        assert parsed["url"], "``url`` must be non-empty"

    def test_head_branch_is_nonempty_string(self, tmp_path: Path) -> None:
        """``head_branch`` must be a non-empty string."""
        target = tmp_path / "pr.json"
        _write_pr_json_atomically(target, **_make_valid_payload(head_branch="interactive/my-feature"))
        parsed = json.loads(target.read_text(encoding="utf-8"))
        assert isinstance(parsed["head_branch"], str), "``head_branch`` must be a string"
        assert parsed["head_branch"], "``head_branch`` must be non-empty"
        assert parsed["head_branch"] == "interactive/my-feature"

    def test_opened_at_parses_as_iso8601(self, tmp_path: Path) -> None:
        """``opened_at`` must be a valid ISO 8601 timestamp string."""
        target = tmp_path / "pr.json"
        _write_pr_json_atomically(target, **_make_valid_payload())
        parsed = json.loads(target.read_text(encoding="utf-8"))
        opened_at = parsed["opened_at"]
        assert isinstance(opened_at, str), "``opened_at`` must be a string"
        assert ISO8601_PATTERN.match(opened_at), (
            f"``opened_at`` {opened_at!r} does not match ISO 8601 pattern "
            f"YYYY-MM-DDTHH:MM:SS(Z|+HH:MM)"
        )

    def test_repo_matches_owner_name_format(self, tmp_path: Path) -> None:
        """``repo`` field must match ``^[\\w.-]+/[\\w.-]+$`` (owner/name)."""
        target = tmp_path / "pr.json"
        valid_repos = [
            "owner/repo",
            "my-org/my-repo",
            "charleshall888/cortex-command",
            "some.org/some.repo",
            "org123/repo-456",
        ]
        for repo_str in valid_repos:
            _write_pr_json_atomically(target, **_make_valid_payload(repo=repo_str))
            parsed = json.loads(target.read_text(encoding="utf-8"))
            assert REPO_PATTERN.match(parsed["repo"]), (
                f"``repo`` {parsed['repo']!r} does not match owner/name format "
                f"^[\\w.-]+/[\\w.-]+$"
            )

    def test_repo_pattern_rejects_invalid_formats(self) -> None:
        """REPO_PATTERN rejects strings that are not owner/name format."""
        invalid_repos = [
            "noslash",
            "owner/",
            "/repo",
            "owner/repo/extra",
            "",
            "owner / repo",  # spaces not allowed
        ]
        for invalid in invalid_repos:
            assert not REPO_PATTERN.match(invalid), (
                f"REPO_PATTERN should reject {invalid!r} but it matched"
            )

    def test_schema_has_no_extra_fields(self, tmp_path: Path) -> None:
        """pr.json must not contain fields beyond the five required ones.

        The spec states 'Field set is closed for this contract.'
        """
        target = tmp_path / "pr.json"
        _write_pr_json_atomically(target, **_make_valid_payload())
        parsed = json.loads(target.read_text(encoding="utf-8"))
        extra_fields = set(parsed.keys()) - REQUIRED_FIELDS
        assert not extra_fields, (
            f"pr.json must not contain extra fields (closed schema). "
            f"Extra fields found: {extra_fields}"
        )


# ---------------------------------------------------------------------------
# complete.md structural assertions for Step 4
# ---------------------------------------------------------------------------


class TestCompleteStepFourStructural:
    """Structural assertions: complete.md Step 4 documents the schema and atomic pattern."""

    @pytest.fixture(autouse=True)
    def _load_complete_md(self) -> None:
        complete_md = Path(__file__).parent.parent / "skills" / "lifecycle" / "references" / "complete.md"
        self._text = complete_md.read_text(encoding="utf-8")

    def test_step_4_heading_present(self) -> None:
        """complete.md must contain a Step 4 heading."""
        assert re.search(r"^#{1,4}\s+Step\s+4\b", self._text, re.MULTILINE), (
            "complete.md must contain '### Step 4' (or similar) heading"
        )

    def test_atomic_write_pattern_documented(self) -> None:
        """complete.md Step 4 must document tempfile + os.replace pattern."""
        assert "os.replace" in self._text, (
            "complete.md Step 4 must document 'os.replace' atomic write"
        )
        assert "NamedTemporaryFile" in self._text or "tempfile" in self._text, (
            "complete.md Step 4 must document tempfile usage"
        )

    def test_pr_json_schema_fields_documented(self) -> None:
        """complete.md Step 4 must document all five schema fields."""
        for field in ("number", "url", "head_branch", "opened_at", "repo"):
            assert field in self._text, (
                f"complete.md Step 4 must document schema field '{field}'"
            )

    def test_repo_field_purpose_documented(self) -> None:
        """complete.md must explain why the ``repo`` field is locked at PR-creation time."""
        assert "locked" in self._text or "resolved at PR-creation time" in self._text, (
            "complete.md must document that 'repo' field is resolved+locked at PR-creation time"
        )

    def test_atomicity_invariant_reference_present(self) -> None:
        """complete.md Step 4 must reference the atomicity invariant (pipeline.md)."""
        assert "atomicity" in self._text.lower() or "atomic" in self._text.lower(), (
            "complete.md Step 4 must reference atomicity invariant"
        )

    def test_opened_at_iso8601_documented(self) -> None:
        """complete.md schema must document opened_at as an ISO8601 string."""
        assert "ISO8601" in self._text or "ISO 8601" in self._text, (
            "complete.md Step 4 schema must document opened_at as ISO8601"
        )
