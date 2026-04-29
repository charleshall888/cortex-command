"""Entry-point dispatch tests for the four packaged backlog modules.

Asserts that each ``cortex_command.backlog.<mod>:main`` callable is
importable, exits cleanly when invoked with ``--help``, and calls
``_telemetry.log_invocation(...)`` with the expected user-visible
command name. Spec R5 / R8 / R12.

These tests do NOT depend on ``uv tool install -e . --reinstall`` —
they exercise the Python entry-point callables directly.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


_PARAMS = [
    ("cortex_command.backlog.update_item", "cortex-update-item"),
    ("cortex_command.backlog.create_item", "cortex-create-backlog-item"),
    ("cortex_command.backlog.generate_index", "cortex-generate-backlog-index"),
    ("cortex_command.backlog.build_epic_map", "cortex-build-epic-map"),
]


@pytest.mark.parametrize("module_name,command_name", _PARAMS, ids=[p[1] for p in _PARAMS])
def test_main_calls_log_invocation(
    module_name: str,
    command_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each main() must call _telemetry.log_invocation with the right command name."""
    import importlib

    module = importlib.import_module(module_name)
    monkeypatch.setattr("sys.argv", [command_name, "--help"])

    with patch.object(module._telemetry, "log_invocation") as mock_log:
        # All four mains exit with SystemExit when given --help (argparse
        # for create_item / build_epic_map; manual usage-print + return 1
        # for update_item / generate_index — return 1 is valid main() behavior).
        try:
            rc = module.main()
        except SystemExit as exc:
            rc = exc.code

        # The dispatch test asserts the telemetry hook fired, not a
        # specific exit code (the four modules have different argparse
        # configurations that emit 0, 1, or 2 on `--help`).
        assert rc in (0, 1, 2), f"main() returned unexpected code {rc!r}"
        assert mock_log.call_count == 1, (
            f"expected exactly one log_invocation call, got {mock_log.call_count}"
        )
        called_with = mock_log.call_args.args[0]
        assert called_with == command_name, (
            f"log_invocation called with {called_with!r}, expected {command_name!r}"
        )
