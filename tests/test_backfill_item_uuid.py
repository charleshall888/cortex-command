"""#499 — a backlog item that predates `uuid:` can be given one by the tool.

`create_item` mints a uuid for everything it creates, and the stable-citation
rule leans on it: an id collision is resolved by citing slug or uuid, never the
bare `#N`. Items that predate the field (wild-light's `008`-`070`) or that were
hand-authored had no verb to fix them, so the workaround was hand-writing
`str(uuid4())` into the frontmatter.

The invariant that matters most here is the refusal: re-minting over an
existing uuid silently breaks every citation already pointing at it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.backlog.backfill_uuid import _backlog_items, backfill

_FIXED = "11111111-2222-3333-4444-555555555555"


def _item(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def test_mints_after_schema_version(tmp_path: Path) -> None:
    """Canonical position — the slot `create_item` writes it into."""
    item = _item(
        tmp_path,
        "008-legacy.md",
        '---\nschema_version: "1"\ntitle: Legacy\nstatus: backlog\n---\nbody\n',
    )
    rec = backfill(item, mint=lambda: _FIXED)
    assert rec["state"] == "minted"
    lines = item.read_text(encoding="utf-8").splitlines()
    assert lines[1] == 'schema_version: "1"'
    assert lines[2] == f"uuid: {_FIXED}"


def test_mints_first_when_schema_version_is_absent(tmp_path: Path) -> None:
    item = _item(
        tmp_path, "010-old.md", "---\ntitle: Old\nstatus: backlog\n---\nbody\n"
    )
    backfill(item, mint=lambda: _FIXED)
    assert item.read_text(encoding="utf-8").splitlines()[1] == f"uuid: {_FIXED}"


def test_existing_uuid_is_never_overwritten(tmp_path: Path) -> None:
    """The whole point: a re-mint breaks every citation that already resolved."""
    body = '---\nschema_version: "1"\nuuid: keep-me\ntitle: Has\n---\nbody\n'
    item = _item(tmp_path, "009-has.md", body)
    rec = backfill(item, mint=lambda: _FIXED)
    assert rec["state"] == "skipped"
    assert rec["uuid"] == "keep-me"
    assert item.read_text(encoding="utf-8") == body


def test_no_frontmatter_is_reported_not_rewritten(tmp_path: Path) -> None:
    """#501's rule: there is nowhere to put the key, so do not claim otherwise."""
    item = _item(tmp_path, "011-broken.md", "no frontmatter\n")
    rec = backfill(item, mint=lambda: _FIXED)
    assert rec["state"] == "no-frontmatter"
    assert item.read_text(encoding="utf-8") == "no frontmatter\n"


def test_backfill_is_idempotent(tmp_path: Path) -> None:
    item = _item(
        tmp_path, "012-x.md", '---\nschema_version: "1"\ntitle: X\n---\nbody\n'
    )
    backfill(item, mint=lambda: _FIXED)
    first = item.read_text(encoding="utf-8")
    assert backfill(item, mint=lambda: "different")["state"] == "skipped"
    assert item.read_text(encoding="utf-8") == first


def test_sweep_skips_the_generated_index(tmp_path: Path) -> None:
    """`index.md` is regenerated output; minting into it would be overwritten."""
    _item(tmp_path, "index.md", "# Backlog\n")
    _item(tmp_path, "013-real.md", "---\ntitle: Real\n---\nbody\n")
    assert [p.name for p in _backlog_items(tmp_path)] == ["013-real.md"]


def test_console_script_is_registered() -> None:
    """An unregistered verb is unreachable — the failure is silent at install."""
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert (
        'cortex-backfill-item-uuid = "cortex_command.backlog.backfill_uuid:main"'
        in text
    )
