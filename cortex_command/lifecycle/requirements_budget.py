"""Byte ceiling for a requirements doc — shared by the validator and the loader.

``cortex-load-requirements`` makes the model read every listed doc whole, at
clarify, research, spec and review, so a doc's size is paid many times per
lifecycle. The ceiling makes growth visible: the validator fails over it and
the loader warns over it.

A doc raises its own ceiling with one line near its top::

    > Size budget: 48000 bytes

That line is the whole ratchet — one reviewed line in the doc's own diff, no
side config to learn or bypass. Stdlib-only: the loader runs under the
dual-channel wrapper's system ``python3``.
"""

from __future__ import annotations

import re
from typing import Tuple

# ~8k tokens. The largest area doc in this repo is 25 KB; the docs that prompted
# the ceiling ran 127-277 KB.
DEFAULT_BYTE_CEILING = 32_000

_BUDGET_LINE = re.compile(r"^>\s*Size budget:\s*([\d,_]+)\s*bytes\b", re.IGNORECASE | re.MULTILINE)


def byte_ceiling(text: str) -> int:
    """The doc's declared ``> Size budget:`` override, else the default."""
    m = _BUDGET_LINE.search(text)
    if not m:
        return DEFAULT_BYTE_CEILING
    digits = re.sub(r"[,_]", "", m.group(1))
    return int(digits) if digits else DEFAULT_BYTE_CEILING


def measure(text: str) -> Tuple[int, int]:
    """Return ``(size_bytes, ceiling_bytes)`` for a doc's text."""
    return len(text.encode("utf-8")), byte_ceiling(text)
