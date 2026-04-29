"""C11 helper: mark an overnight session complete via the canonical state-machine API.

This module is the canonical implementation behind the
``cortex-morning-review-complete-session`` bash shim. It reads an
``overnight-state.json`` file, validates and applies the
``executing -> complete`` phase transition through
``cortex_command.overnight.state.transition()``, persists the result via
``save_state()``, and optionally unlinks an active-session pointer file.

Behaviour summary (see lifecycle spec for the full matrix):

* Missing state file -> exit 0 silently.
* Unparseable / structurally invalid / malformed-phase state file ->
  exit non-zero with a stderr error.
* ``phase == "executing"`` -> transition to ``complete``, save, optionally
  unlink the pointer. Exit 0.
* ``phase`` in {``"complete"``, ``"paused"``, ``"planning"``} -> no-op,
  exit 0. Pointer is left untouched.
* ``save_state`` raising ``OSError`` -> exit non-zero with a stderr
  error. Pointer is NOT unlinked.

The pointer unlink is only attempted when ``--pointer`` is supplied AND
``save_state`` returned normally.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cortex_command.overnight.state import load_state, save_state, transition


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="complete-morning-review-session",
        description=(
            "Mark an overnight session complete by transitioning its state "
            "from 'executing' to 'complete' via the canonical state-machine "
            "API. Optionally unlink the active-session pointer file."
        ),
    )
    parser.add_argument(
        "state_path",
        type=Path,
        help="Path to the overnight-state.json file.",
    )
    parser.add_argument(
        "--pointer",
        dest="pointer",
        type=Path,
        default=None,
        help=(
            "Optional path to an active-session pointer file. When supplied "
            "and the state write succeeds, this file is unlinked "
            "(missing_ok=True)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    state_path: Path = args.state_path
    pointer_path: Path | None = args.pointer

    # Case 1: Missing state file -> silent exit 0. Do not touch the pointer.
    if not state_path.exists():
        return 0

    # Case 2: Load + validate. A single catch covers all loud-failure
    # subclasses raised by load_state(): JSONDecodeError (corrupt JSON),
    # KeyError (missing required raw key), and ValueError (phase not in
    # PHASES, raised from OvernightState.__post_init__).
    try:
        state = load_state(state_path)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(
            f"[complete-morning-review-session] error loading {state_path}: {e}",
            file=sys.stderr,
        )
        return 1

    # Case 4: phase is a valid PHASES member but not "executing" -> no-op.
    # Do NOT call transition() (would ValueError per the forward grammar).
    # Do NOT touch the pointer.
    if state.phase != "executing":
        return 0

    # Case 3: phase == "executing" -> transition, save, optionally unlink
    # pointer. transition() may raise ValueError if the grammar rejects the
    # edge; that path is unreachable here (executing -> complete is a valid
    # forward edge) but we leave it uncaught to surface as a real bug rather
    # than a silent skip.
    new_state = transition(state, "complete")

    try:
        save_state(new_state, state_path)
    except OSError as e:
        # Case 5: save_state failed -> exit non-zero, do NOT unlink pointer.
        print(
            f"[complete-morning-review-session] error writing {state_path}: {e}",
            file=sys.stderr,
        )
        return 1

    # Save succeeded. Now (and only now) unlink the pointer if supplied.
    if pointer_path is not None:
        Path(pointer_path).unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
