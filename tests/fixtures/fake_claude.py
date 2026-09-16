#!/usr/bin/env python3
"""Stand-in for the ``claude`` CLI, driven entirely by environment variables.

Used by ``tests/test_claude_stream.py`` to exercise the spawn-and-parse seam in
``cortex_command/claude_stream.py`` without a real binary. It writes its
outputs *before* reading stdin, so every run also exercises the seam's
write-prompt-from-a-separate-task path.

Environment:
  FAKE_CLAUDE_STDERR_BYTES  write at least this many bytes to stderr, in lines
  FAKE_CLAUDE_FRAMES        path to a file copied verbatim to stdout
  FAKE_CLAUDE_ECHO_STDIN_TO path the full stdin bytes are written to
  FAKE_CLAUDE_ENV_TO        path a JSON dump of os.environ is written to
  FAKE_CLAUDE_SLEEP         seconds to sleep after writing outputs
  FAKE_CLAUDE_EXIT          exit code (default 0)
"""

import json
import os
import sys
import time


def main() -> int:
    stderr_bytes = int(os.environ.get("FAKE_CLAUDE_STDERR_BYTES", "0"))
    line = b"x" * 999 + b"\n"
    written = 0
    while written < stderr_bytes:
        sys.stderr.buffer.write(line)
        written += len(line)
    sys.stderr.buffer.flush()

    frames_path = os.environ.get("FAKE_CLAUDE_FRAMES")
    if frames_path:
        with open(frames_path, "rb") as fh:
            sys.stdout.buffer.write(fh.read())
        sys.stdout.buffer.flush()

    env_to = os.environ.get("FAKE_CLAUDE_ENV_TO")
    if env_to:
        with open(env_to, "w", encoding="utf-8") as fh:
            json.dump(dict(os.environ), fh)

    data = sys.stdin.buffer.read()
    echo_to = os.environ.get("FAKE_CLAUDE_ECHO_STDIN_TO")
    if echo_to:
        with open(echo_to, "wb") as fh:
            fh.write(data)

    sleep_s = float(os.environ.get("FAKE_CLAUDE_SLEEP", "0"))
    if sleep_s:
        time.sleep(sleep_s)

    return int(os.environ.get("FAKE_CLAUDE_EXIT", "0"))


if __name__ == "__main__":
    sys.exit(main())
