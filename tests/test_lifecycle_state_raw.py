"""``cortex-lifecycle-state --field <x> --raw`` — the bare-scalar composition mode.

#400 finding 2: the lifecycle references document, verbatim,

    cortex-resolve-model --criticality "$(cortex-lifecycle-state --feature f \
        --field criticality --raw)"

so the substitution must ALWAYS yield a valid criticality/tier enum on a clean
log — the value when set, the documented caller default (criticality
``medium``, tier ``simple``) when the axis was never set or the log is absent.
The one exception is fail-loud by design: a corrupted log whose requested axis
is unknowable exits 2 rather than emitting a default a gate-deciding consumer
would trust (the JSON form carries ``"corrupted": true`` for that path).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.lifecycle import state_cli

SLUG = "raw-feat"


def _seed(root: Path, content: str | None) -> None:
    fd = root / "cortex" / "lifecycle" / SLUG
    fd.mkdir(parents=True, exist_ok=True)
    if content is not None:
        (fd / "events.log").write_text(content, encoding="utf-8")


def _run(monkeypatch, capsys, root: Path, argv: list[str]) -> tuple[int, str, str]:
    monkeypatch.chdir(root)
    with pytest.raises(SystemExit) as exc:
        state_cli.main(argv)
    out = capsys.readouterr()
    return int(exc.value.code or 0), out.out, out.err


def test_raw_emits_bare_value(tmp_path, monkeypatch, capsys) -> None:
    _seed(tmp_path, '{"event": "lifecycle_start", "criticality": "high", "tier": "complex"}\n')
    code, out, _ = _run(monkeypatch, capsys, tmp_path,
                        ["--feature", SLUG, "--field", "criticality", "--raw"])
    assert (code, out) == (0, "high\n")
    code, out, _ = _run(monkeypatch, capsys, tmp_path,
                        ["--feature", SLUG, "--field", "tier", "--raw"])
    assert (code, out) == (0, "complex\n")


def test_raw_defaults_when_axis_never_set(tmp_path, monkeypatch, capsys) -> None:
    _seed(tmp_path, '{"event": "some_other_event"}\n')
    code, out, _ = _run(monkeypatch, capsys, tmp_path,
                        ["--feature", SLUG, "--field", "criticality", "--raw"])
    assert (code, out) == (0, "medium\n")
    code, out, _ = _run(monkeypatch, capsys, tmp_path,
                        ["--feature", SLUG, "--field", "tier", "--raw"])
    assert (code, out) == (0, "simple\n")


def test_raw_defaults_when_log_missing(tmp_path, monkeypatch, capsys) -> None:
    _seed(tmp_path, None)
    code, out, _ = _run(monkeypatch, capsys, tmp_path,
                        ["--feature", SLUG, "--field", "criticality", "--raw"])
    assert (code, out) == (0, "medium\n")


def test_raw_fails_loud_on_corrupted_unknowable_axis(tmp_path, monkeypatch, capsys) -> None:
    # A torn line with no axis value: corrupted per the reducer, axis absent.
    _seed(tmp_path, "{torn\n")
    code, out, err = _run(monkeypatch, capsys, tmp_path,
                          ["--feature", SLUG, "--field", "criticality", "--raw"])
    assert code == 2
    assert out == ""
    assert "unknowable" in err and "corrupted" in err


def test_raw_keeps_recovered_value_despite_torn_line(tmp_path, monkeypatch, capsys) -> None:
    # The requested axis survived the corruption — emit it, don't refuse.
    _seed(tmp_path, "{torn\n" '{"event": "lifecycle_start", "criticality": "low", "tier": "simple"}\n')
    code, out, _ = _run(monkeypatch, capsys, tmp_path,
                        ["--feature", SLUG, "--field", "criticality", "--raw"])
    assert (code, out) == (0, "low\n")


def test_raw_requires_field(tmp_path, monkeypatch, capsys) -> None:
    _seed(tmp_path, None)
    code, _, err = _run(monkeypatch, capsys, tmp_path, ["--feature", SLUG, "--raw"])
    assert code == 2
    assert "--raw requires --field" in err


def test_json_form_unchanged_without_raw(tmp_path, monkeypatch, capsys) -> None:
    _seed(tmp_path, '{"event": "lifecycle_start", "criticality": "high", "tier": "complex"}\n')
    code, out, _ = _run(monkeypatch, capsys, tmp_path,
                        ["--feature", SLUG, "--field", "criticality"])
    assert (code, out) == (0, '{"criticality":"high"}\n')
