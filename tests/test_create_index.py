"""Golden-byte + structural coverage for ``cortex-lifecycle-create-index``.

Pins the byte shape of the lifecycle ``index.md`` the
``cortex_command.lifecycle.create_index`` verb writes, across the two template
shapes (backlog-linked Shape A and ad-hoc Shape B), the skip-if-exists no-op,
the ``CORTEX_REPO_ROOT`` write-root precedence (#319 / Req 5), the
basename-input regression (the critical-review A-fix), and the
non-empty-but-missing ``--backlog-file`` contract violation.

The date seam ``create_index._today`` is monkeypatched to a fixed value so the
golden bytes are deterministic. Each golden carries a negative control (a
variant the assertion must reject), and the unquoted ``tags`` line is asserted
to round-trip through ``load_requirements_cli._extract_tags`` — the downstream
stdlib reader the unquoted-inline shape exists to satisfy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.lifecycle import create_index as ci
from cortex_command.lifecycle.create_index import create_index, main
from cortex_command.lifecycle.load_requirements_cli import _extract_tags

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

SLUG = "my-feature"
DATE = "2026-07-01"
# A real prefix-bearing basename: parent_backlog_id derives from ``326-``; the
# full stem is embedded on both sides of the wikilink.
TICKET = "326-offload-step-2.md"
STEM = "326-offload-step-2"
UUID = "427d4c22-ea92-462e-a7c1-602342ef78cc"
# The #326 ticket's own title — exercises wikilink-INERT special chars
# (``+`` / ``#`` / ``(`` / ``)``), which must embed verbatim and unquoted.
TITLE = (
    "Offload lifecycle Step 2 backlog write-back + index.md creation into "
    "CLI verbs (lifecycle analog of #322)"
)

GOLDEN_A = (
    "---\n"
    f"feature: {SLUG}\n"
    f"parent_backlog_uuid: {UUID}\n"
    "parent_backlog_id: 326\n"
    "artifacts: []\n"
    "tags: [lifecycle, cli-verbs]\n"
    f"created: {DATE}\n"
    f"updated: {DATE}\n"
    "---\n"
    f"# [[{STEM}|{TITLE}]]\n"
    "\n"
    f"Feature lifecycle for [[{STEM}]].\n"
)

GOLDEN_B = (
    "---\n"
    f"feature: {SLUG}\n"
    "parent_backlog_uuid: null\n"
    "parent_backlog_id: null\n"
    "artifacts: []\n"
    "tags: []\n"
    f"created: {DATE}\n"
    f"updated: {DATE}\n"
    "---\n"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "cortex" / "backlog").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_ticket(
    root: Path,
    name: str = TICKET,
    *,
    uuid: str | None = UUID,
    tags: str = "[lifecycle, cli-verbs]",
    title: str = TITLE,
) -> None:
    lines = ["---", f"title: '{title}'"]
    if uuid is not None:
        lines.append(f"uuid: {uuid}")
    lines += [f"tags: {tags}", "status: refined", "---", "", "Body.", ""]
    (root / "cortex" / "backlog" / name).write_text("\n".join(lines))


def _read_index(root: Path, slug: str = SLUG) -> str:
    return (root / "cortex" / "lifecycle" / slug / "index.md").read_text()


def _tags_line(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("tags:"):
            return line
    raise AssertionError("no tags: line found")


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    monkeypatch.setattr(ci, "_today", lambda: DATE)


@pytest.fixture(autouse=True)
def _no_env_root(monkeypatch):
    # Default: ignore any ambient CORTEX_REPO_ROOT; the Req-5 test sets it back.
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)


# ---------------------------------------------------------------------------
# (a) Shape A golden — special-char title, plain-kebab tags, CLI byte contract
# ---------------------------------------------------------------------------


def test_shape_a_golden_bytes_and_cli_contract(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _write_ticket(root)
    monkeypatch.chdir(root)

    rc = main(["--feature", SLUG, "--backlog-file", TICKET])
    out = capsys.readouterr().out

    assert rc == 0
    # Byte-faithful golden.
    content = _read_index(root)
    assert content == GOLDEN_A
    # Negative control: the body must NOT quote the verbatim title.
    assert f'# [[{STEM}|"{TITLE}"]]' not in content

    # The unquoted tags line round-trips through the downstream stdlib reader.
    assert _tags_line(content) == "tags: [lifecycle, cli-verbs]"
    assert _extract_tags([_tags_line(content)]) == ["lifecycle", "cli-verbs"]
    # Negative control: it is NOT the quoted form.
    assert _tags_line(content) != 'tags: ["lifecycle", "cli-verbs"]'

    # Date-only created/updated.
    for key in ("created", "updated"):
        line = next(l for l in content.splitlines() if l.startswith(f"{key}:"))
        assert line.split(": ", 1)[1].strip() == DATE

    # CLI contract: one compact JSON line on stdout, created signal.
    assert out.endswith("\n")
    assert out.count("\n") == 1
    assert ", " not in out and ": " not in out
    parsed = json.loads(out)
    assert parsed == {"signal": "created", "path": f"cortex/lifecycle/{SLUG}/index.md"}


# ---------------------------------------------------------------------------
# (a, null-field) Shape A with a uuid-less ticket emits bare unquoted null
# ---------------------------------------------------------------------------


def test_shape_a_missing_uuid_emits_bare_null(tmp_path):
    root = _repo(tmp_path)
    _write_ticket(root, uuid=None)

    create_index(SLUG, TICKET, root)
    content = _read_index(root)

    assert "parent_backlog_uuid: null\n" in content
    # Negative control: never the quoted "null" wontfix_cli would mis-read as a
    # real terminalization target.
    assert 'parent_backlog_uuid: "null"' not in content
    # parent_backlog_id still derives from the numeric prefix.
    assert "parent_backlog_id: 326\n" in content


# ---------------------------------------------------------------------------
# (b) Shape B golden — bare nulls, tags [], no heading/body
# ---------------------------------------------------------------------------


def test_shape_b_golden_no_backlog_file(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    monkeypatch.chdir(root)

    rc = main(["--feature", SLUG, "--backlog-file", ""])
    out = capsys.readouterr().out

    assert rc == 0
    content = _read_index(root)
    assert content == GOLDEN_B
    # No heading/body on the ad-hoc shape.
    assert "# [[" not in content
    assert "Feature lifecycle for" not in content
    # Bare nulls (negative control: not quoted).
    assert "parent_backlog_uuid: null\n" in content
    assert 'parent_backlog_uuid: "null"' not in content
    parsed = json.loads(out)
    assert parsed["signal"] == "created"


# ---------------------------------------------------------------------------
# (c) skip-if-exists — pre-existing index.md is byte-preserved + skip signal
# ---------------------------------------------------------------------------


def test_skip_if_exists_preserves_bytes(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _write_ticket(root)
    sentinel = "SENTINEL pre-existing index.md — must not be overwritten\n"
    lc = root / "cortex" / "lifecycle" / SLUG
    lc.mkdir(parents=True, exist_ok=True)
    (lc / "index.md").write_text(sentinel)
    monkeypatch.chdir(root)

    rc = main(["--feature", SLUG, "--backlog-file", TICKET])
    out = capsys.readouterr().out

    assert rc == 0
    assert _read_index(root) == sentinel  # byte-identical, untouched
    parsed = json.loads(out)
    assert parsed["signal"] == "skipped"


# ---------------------------------------------------------------------------
# (d) Req 5 — CORTEX_REPO_ROOT wins over CWD; write lands under the env tree
# ---------------------------------------------------------------------------


def test_env_root_precedence_over_cwd(tmp_path, monkeypatch):
    env_root = _repo(tmp_path / "env_tree")
    cwd_root = _repo(tmp_path / "cwd_tree")
    _write_ticket(env_root)
    _write_ticket(cwd_root)

    monkeypatch.chdir(cwd_root)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(env_root))

    rc = main(["--feature", SLUG, "--backlog-file", TICKET])

    assert rc == 0
    # Write landed under the env-root tree, NOT the CWD tree.
    assert (env_root / "cortex" / "lifecycle" / SLUG / "index.md").exists()
    assert not (cwd_root / "cortex" / "lifecycle" / SLUG / "index.md").exists()


# ---------------------------------------------------------------------------
# (e) basename-input regression (A-fix) — bare basename located via canonical dir
# ---------------------------------------------------------------------------


def test_basename_input_located_via_canonical_dir(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    # Ticket lives ONLY at cortex/backlog/<basename>; we pass the bare basename
    # (no cortex/backlog/ prefix), exactly as the Step-1 resolver emits it. A
    # naive ``root / backlog_file`` open would miss it.
    _write_ticket(root)
    monkeypatch.chdir(root)

    rc = main(["--feature", SLUG, "--backlog-file", TICKET])

    assert rc == 0
    assert _read_index(root) == GOLDEN_A  # Shape A written via the canonical-dir join


# ---------------------------------------------------------------------------
# (f) non-empty-but-missing --backlog-file is a contract violation (exit 1)
# ---------------------------------------------------------------------------


def test_nonempty_missing_backlog_file_returns_1(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)  # backlog dir exists but the ticket does not
    monkeypatch.chdir(root)

    rc = main(["--feature", SLUG, "--backlog-file", "999-does-not-exist.md"])
    err = capsys.readouterr().err

    assert rc == 1  # diagnostic exit, NOT a silent Shape-B write
    assert "999-does-not-exist.md" in err
    # No index.md was written (no silent fall-back).
    assert not (root / "cortex" / "lifecycle" / SLUG / "index.md").exists()
