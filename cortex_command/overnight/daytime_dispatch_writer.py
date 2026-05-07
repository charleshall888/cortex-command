"""Atomic-write helper for ``lifecycle/{feature}/daytime-dispatch.json``.

Owns the contract for the daytime-dispatch file's two write modes:

- ``init``: write a fresh dispatch JSON with ``pid: null``.
- ``update-pid``: read the existing dispatch JSON, mutate ``pid``, atomic-rewrite.

Replaces the inline ``tempfile.mkstemp`` + ``os.replace`` recipes formerly
duplicated in the lifecycle skill's ``implement.md`` §1a. The atomic-write
pattern uses :func:`cortex_command.common.atomic_write`, which itself uses
``durable_fsync`` for the F_FULLFSYNC barrier on Darwin.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from cortex_command.common import atomic_write


def _dispatch_path(feature: str) -> Path:
    return Path(f"lifecycle/{feature}/daytime-dispatch.json")


def _write_init(feature: str, dispatch_id: str) -> None:
    path = _dispatch_path(feature)
    data = {
        "schema_version": 1,
        "dispatch_id": dispatch_id,
        "feature": feature,
        "start_ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pid": None,
    }
    payload = json.dumps(data, indent=2) + "\n"
    atomic_write(path, payload)


def _write_update_pid(feature: str, pid: int) -> None:
    path = _dispatch_path(feature)
    with open(path) as f:
        data = json.load(f)
    data["pid"] = pid
    payload = json.dumps(data, indent=2) + "\n"
    atomic_write(path, payload)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m cortex_command.overnight.daytime_dispatch_writer",
        description="Atomic-write helper for daytime-dispatch.json.",
    )
    p.add_argument("--feature", required=True, help="Feature slug.")
    p.add_argument(
        "--mode",
        required=True,
        choices=["init", "update-pid"],
        help="init = write fresh dispatch JSON with pid=null; "
        "update-pid = read existing, mutate pid, atomic-rewrite.",
    )
    p.add_argument(
        "--dispatch-id",
        help="32-char hex dispatch UUID (required for --mode init).",
    )
    p.add_argument(
        "--pid",
        type=int,
        help="Subprocess PID (required for --mode update-pid).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "init":
        if not args.dispatch_id:
            print("error: --dispatch-id required for --mode init", file=sys.stderr)
            return 2
        _write_init(args.feature, args.dispatch_id)
    else:  # update-pid
        if args.pid is None:
            print("error: --pid required for --mode update-pid", file=sys.stderr)
            return 2
        _write_update_pid(args.feature, args.pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
