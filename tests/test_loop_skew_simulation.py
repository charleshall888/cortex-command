"""Loop-side skew-halt simulations (epic 371 Phase C, Task 19 / R17 loop-side).

The served next/advance loop halts with a documented remediation on four
distinct skew / verb-unavailability signals. This repo never hits them
naturally — the wrapper's branch-(c) working-tree fallback always resolves the
in-tree module — so each case is **scripted** here (spec Technical Constraints:
"Skew paths must be exercised by scripted tests").

Each test drives the **shipped** mechanism the loop relays, never a copy of the
remediation text embedded in the loop prose (a self-sealing check the task
explicitly warns against). Concretely the halt-with-remediation the loop
produces is anchored to:

  * ``cortex_command.lifecycle.protocol.classify_protocol`` — the compat
    classifier (legacy / ok / out-of-range).
  * ``cortex_command.lifecycle.protocol.remediation_message`` /
    ``REMEDIATION_COMMAND`` — the shipped copy-pasteable fix.
  * ``cortex_command.lifecycle.next_verb.next_state`` — the real ``next`` verb's
    ``{"state": "protocol-skew", "remediation": ...}`` short-circuit.
  * ``bin/cortex-lifecycle-next`` — the real dual-channel wrapper's branch-(d)
    exit-2 remediation.

The four cases (R17 loop-side acceptance): legacy payload (no ``protocol``
field), out-of-range ``protocol``, wrapper branch-(d) exit-2 (wheel absent),
and command-not-found.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from cortex_command.lifecycle import next_verb
from cortex_command.lifecycle.protocol import (
    PROTOCOL_VERSION,
    REMEDIATION_COMMAND,
    classify_protocol,
    remediation_message,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
NEXT_WRAPPER = REPO_ROOT / "bin" / "cortex-lifecycle-next"

# The plugin-side expectation the loop reads from protocol-expectation.txt at
# HEAD (min == max == wheel PROTOCOL_VERSION); both sides move together in-repo.
_EXPECT_MIN = PROTOCOL_VERSION
_EXPECT_MAX = PROTOCOL_VERSION


# ---------------------------------------------------------------------------
# Case 1 — legacy payload (no ``protocol`` field)
# ---------------------------------------------------------------------------


def test_legacy_payload_classifies_legacy_and_halts_with_remediation() -> None:
    """A served payload with no ``protocol`` field (an old wheel predating the
    field) classifies ``legacy``; the loop halts and relays the shipped
    remediation (served rendered ``<absent>``)."""
    verdict = classify_protocol({}, expected_min=_EXPECT_MIN, expected_max=_EXPECT_MAX)
    assert verdict == "legacy"

    msg = remediation_message(served=None, expected_min=_EXPECT_MIN, expected_max=_EXPECT_MAX)
    # Anchored to the SHIPPED template/command, not a loop-local copy.
    assert REMEDIATION_COMMAND in msg
    assert "protocol skew" in msg
    assert "<absent>" in msg  # legacy payload → served rendered absent


# ---------------------------------------------------------------------------
# Case 2 — out-of-range ``protocol``
# ---------------------------------------------------------------------------


def test_out_of_range_classifies_and_next_verb_serves_protocol_skew() -> None:
    """A served ``protocol`` outside the caller's expected range classifies
    ``out-of-range``; and the REAL ``next`` verb, handed an expectation the
    served value cannot satisfy, short-circuits to a ``protocol-skew`` envelope
    whose ``remediation`` IS the shipped ``remediation_message`` (non-self-sealing:
    the loop's halt text is the wheel's, not a prose copy)."""
    hi = PROTOCOL_VERSION + 4  # served (== PROTOCOL_VERSION) is below this floor
    verdict = classify_protocol(
        {"protocol": PROTOCOL_VERSION}, expected_min=hi, expected_max=hi
    )
    assert verdict == "out-of-range"

    # The short-circuit runs before any identity resolution, so a ghost feature
    # slug never touches the filesystem.
    envelope = next_verb.next_state("ghost-feature", expect_min=hi, expect_max=hi)
    assert envelope["state"] == "protocol-skew"
    assert envelope["served_protocol"] == PROTOCOL_VERSION
    assert envelope["remediation"] == remediation_message(
        served=PROTOCOL_VERSION, expected_min=hi, expected_max=hi
    )
    assert REMEDIATION_COMMAND in envelope["remediation"]


# ---------------------------------------------------------------------------
# Case 3 — wrapper branch-(d) exit-2 (cortex-command wheel absent)
# ---------------------------------------------------------------------------


def _force_branch_d_env(tmp_path: Path) -> dict[str, str]:
    """Build an env that forces the ``cortex-lifecycle-next`` wrapper to
    branch-(d): a fake ``python3`` that fails the import probe (branch-b), and a
    ``CORTEX_COMMAND_ROOT`` with no cortex-command ``pyproject.toml`` (branch-c),
    with ``CORTEX_COMMAND_FORCE_SOURCE`` unset (branch-a)."""
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    fake_python = fakebin / "python3"
    # Any invocation (notably the branch-b `python3 -c "import ..."` probe) fails.
    fake_python.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_python.chmod(0o755)

    noproject = tmp_path / "noproject"  # no pyproject.toml → branch-c grep fails
    noproject.mkdir()

    env = dict(os.environ)
    env.pop("CORTEX_COMMAND_FORCE_SOURCE", None)
    env["CORTEX_COMMAND_ROOT"] = str(noproject)
    env["PATH"] = f"{fakebin}{os.pathsep}{env.get('PATH', '')}"
    return env


def test_wrapper_branch_d_exits_2_with_remediation(tmp_path: Path) -> None:
    """With the wheel absent (branches a/b/c all defeated), the real wrapper
    hits branch-(d): exit 2 with the shipped remediation on stderr. This is the
    halt the loop relays when its entry verb's wrapper reports a missing wheel."""
    assert NEXT_WRAPPER.is_file() and os.access(NEXT_WRAPPER, os.X_OK)
    proc = subprocess.run(
        [str(NEXT_WRAPPER), "some-feature"],
        env=_force_branch_d_env(tmp_path),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2, (
        f"expected branch-(d) exit 2, got {proc.returncode}\nstderr:\n{proc.stderr}"
    )
    # The wrapper's shipped remediation names the missing wheel and the fix.
    assert "wheel not found" in proc.stderr
    assert "uv tool install" in proc.stderr


# ---------------------------------------------------------------------------
# Case 4 — command not found
# ---------------------------------------------------------------------------


def test_command_not_found_is_a_missing_verb_with_install_remediation() -> None:
    """When ``cortex-lifecycle-next`` is not on PATH at all, invoking it raises
    the OS missing-command signal (``FileNotFoundError`` / ENOENT). The loop's
    documented response is a halt whose remediation is the shipped install
    command — anchored here to ``REMEDIATION_COMMAND`` rather than a loop-local
    copy, so this is not self-sealing."""
    with pytest.raises(FileNotFoundError):
        subprocess.run(
            ["cortex-lifecycle-next-nonexistent-xyzzy", "some-feature"],
            capture_output=True,
            text=True,
        )
    # The remediation the loop points a missing verb at is the shipped install.
    assert REMEDIATION_COMMAND
    assert "uv tool install" in REMEDIATION_COMMAND
