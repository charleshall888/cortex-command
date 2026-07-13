"""#378 req-3: defensive reader coercion of a numeric ``lifecycle_slug``.

A tool-managed writer can emit ``lifecycle_slug`` as an unquoted YAML integer,
which ``yaml.safe_load`` reads back as ``int``. The two ``lifecycle_slug`` read
sites must coerce a non-``None`` value to ``str`` so a numeric backlog ID keeps
resolving as its string slug (``"374"`` against dir ``374``) instead of
crashing the served resolve path:

  * ``resolve_item._resolve_lifecycle_slug`` — returned ``fm["lifecycle_slug"]``
    raw; a numeric value leaked as ``int`` into the JSON output.
  * ``lifecycle.resolve.resolve_invocation`` — ``(lifecycle_base / slug)`` raised
    ``TypeError`` when ``slug`` was an ``int`` (``Path / int``).

The ``None`` sentinel must stay ``None`` (fall through the derivation chain),
never become the string ``"None"``.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.backlog.resolve_item import _resolve_lifecycle_slug
from cortex_command.lifecycle import resolve as resolve_mod


# ---------------------------------------------------------------------------
# Path 1: resolve_item._resolve_lifecycle_slug
# ---------------------------------------------------------------------------


def test_resolve_lifecycle_slug_coerces_int_to_str() -> None:
    """A numeric ``lifecycle_slug`` (int 374) coerces to the string ``"374"``."""
    result = _resolve_lifecycle_slug({"lifecycle_slug": 374}, "Some Title")
    assert result == "374"
    assert isinstance(result, str)


def test_resolve_lifecycle_slug_str_value_unchanged() -> None:
    """An already-string ``lifecycle_slug`` passes through verbatim."""
    result = _resolve_lifecycle_slug({"lifecycle_slug": "my-feature"}, "Some Title")
    assert result == "my-feature"
    assert isinstance(result, str)


def test_resolve_lifecycle_slug_none_falls_through_not_string_none() -> None:
    """A ``None`` sentinel falls through to the title derivation, never ``"None"``."""
    result = _resolve_lifecycle_slug({"lifecycle_slug": None}, "Some Title")
    assert isinstance(result, str)
    assert result == "some-title"
    assert result != "None"


# ---------------------------------------------------------------------------
# Path 2: lifecycle.resolve.resolve_invocation (the lifecycle_base / slug join)
# ---------------------------------------------------------------------------


def test_resolve_invocation_coerces_numeric_backlog_slug(
    tmp_path: Path, monkeypatch
) -> None:
    """A numeric backlog ``lifecycle_slug`` remaps to its string-named dir
    without raising ``TypeError``/``AttributeError`` on ``Path / int``."""
    # Lifecycle dir keyed by the numeric-looking slug string "374".
    lifecycle_dir = tmp_path / "cortex" / "lifecycle" / "374"
    lifecycle_dir.mkdir(parents=True)

    # Backlog resolution returns a raw int slug (the type leak this guards).
    monkeypatch.setattr(
        resolve_mod,
        "_resolve_backlog",
        lambda feature: {"lifecycle_slug": 374},
    )

    # Token that does not name an on-disk lifecycle dir, forcing the backlog
    # remap path (resolve.py:181) to run.
    result = resolve_mod.resolve_invocation("some-alias", project_root=tmp_path)

    assert result["state"] == "resume"
    assert result["feature"] == "374"
    assert isinstance(result["feature"], str)
    # Evidence trail: the invocation token that remapped onto the numeric slug.
    assert result["resolved_from"] == "some-alias"
