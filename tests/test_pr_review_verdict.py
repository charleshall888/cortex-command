"""Contract test for the /pr-review fail-loud verdict state machine (spec Req 10).

Pins the deterministic verdict derivation in
``plugins/cortex-pr-review/skills/pr-review/scripts/derive_verdict.py`` against
the five verdict cases from spec ``## Grounding & Verdict Vocabulary``, plus the
internal derivation of degradation signals 5/6 and the ``__main__`` stdin path.

The module is loaded via ``importlib.util.spec_from_file_location`` because the
plugin directory name contains a hyphen (not importable via normal package
syntax). The ``RUNTIME_SIGNALS`` constant is imported from the module rather
than re-typed here, so the helper and the test cannot drift on signal names.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DERIVE_VERDICT_PATH = (
    REPO_ROOT
    / "plugins"
    / "cortex-pr-review"
    / "skills"
    / "pr-review"
    / "scripts"
    / "derive_verdict.py"
)


def _load_module():
    """Load ``derive_verdict`` as a standalone module from its plugin path."""
    module_name = "derive_verdict_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, DERIVE_VERDICT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not create module spec for {DERIVE_VERDICT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_mod = _load_module()
derive_verdict = _mod.derive_verdict
RUNTIME_SIGNALS = _mod.RUNTIME_SIGNALS


def _finding(severity: str, grounding: str) -> dict:
    """Build a minimal finding dict matching the output-format schema keys."""
    return {
        "severity": severity,
        "grounding": grounding,
        "label": "issue (blocking)" if severity == "blocking" else "suggestion",
        "file:line": "foo.py:42",
        "body": "synthetic finding",
    }


# ---------------------------------------------------------------------------
# The five verdict cases (spec Req 10)
# ---------------------------------------------------------------------------


def test_grounded_blocking_requests_changes():
    """Case 1: a grounded blocking finding → REQUEST_CHANGES."""
    findings = [_finding("blocking", "grounded")]
    assert derive_verdict(findings, set()) == "REQUEST_CHANGES"


def test_all_evidence_weak_is_inconclusive():
    """Case 2: surfaced findings, none grounded (signal 5 derived) →
    REVIEW_INCONCLUSIVE. No runtime signal is passed."""
    findings = [
        _finding("non-blocking", "evidence-weak"),
        _finding("non-blocking", "evidence-weak"),
    ]
    assert derive_verdict(findings, set()) == "REVIEW_INCONCLUSIVE"


def test_evidence_weak_blocking_is_inconclusive():
    """Case 3: an evidence-weak blocking finding (signal 6 derived) →
    REVIEW_INCONCLUSIVE. No runtime signal is passed.

    A grounded finding co-exists so signal 5 (none grounded) does NOT fire;
    this isolates signal 6 as the trigger."""
    findings = [
        _finding("non-blocking", "grounded"),
        _finding("blocking", "evidence-weak"),
    ]
    assert derive_verdict(findings, set()) == "REVIEW_INCONCLUSIVE"


def test_zero_findings_with_runtime_signal_is_inconclusive():
    """Case 4: zero findings + a runtime signal → REVIEW_INCONCLUSIVE.

    The signal name is pulled from the imported RUNTIME_SIGNALS constant
    rather than a hard-coded literal, so test and helper cannot drift."""
    runtime_signal = next(iter(RUNTIME_SIGNALS))
    assert derive_verdict([], {runtime_signal}) == "REVIEW_INCONCLUSIVE"


def test_all_grounded_non_blocking_approves():
    """Case 5: all findings grounded, none blocking, no degradation → APPROVE."""
    findings = [
        _finding("non-blocking", "grounded"),
        _finding("non-blocking", "grounded"),
    ]
    assert derive_verdict(findings, set()) == "APPROVE"


# ---------------------------------------------------------------------------
# Signals 5 and 6 are derived internally, not passed by the caller (Req 10 #6)
# ---------------------------------------------------------------------------


def test_signals_5_and_6_derived_from_findings_not_runtime_signals():
    """Signals 5 (surfaced-none-grounded) and 6 (evidence-weak blocking) are
    derived from `findings`; the caller passes only RUNTIME_SIGNALS.

    Confirms both cases route to REVIEW_INCONCLUSIVE with `runtime_signals` empty
    AND that the derived signals are NOT members of RUNTIME_SIGNALS (which holds
    only the four runtime signals)."""
    assert "surfaced_none_grounded" not in RUNTIME_SIGNALS
    assert "evidence_weak_blocking" not in RUNTIME_SIGNALS
    assert len(RUNTIME_SIGNALS) == 4

    # Signal 5: surfaced but none grounded.
    assert (
        derive_verdict([_finding("non-blocking", "evidence-weak")], set())
        == "REVIEW_INCONCLUSIVE"
    )
    # Signal 6: evidence-weak blocking (with a grounded peer so signal 5 stays off).
    signal_6 = [
        _finding("non-blocking", "grounded"),
        _finding("blocking", "evidence-weak"),
    ]
    assert derive_verdict(signal_6, set()) == "REVIEW_INCONCLUSIVE"


# ---------------------------------------------------------------------------
# The __main__ stdin path (Req 10 #7)
# ---------------------------------------------------------------------------


def test_main_stdin_path_prints_verdict():
    """Invoke the script as __main__ over stdin and assert the printed verdict.

    Pins the `{"findings": [...], "runtime_signals": [...]}` JSON contract that
    protocol.md pipes to the script."""
    payload = {
        "findings": [_finding("blocking", "grounded")],
        "runtime_signals": [],
    }
    result = subprocess.run(
        [sys.executable, str(DERIVE_VERDICT_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"exited {result.returncode}; stderr:\n{result.stderr}"
    assert result.stdout.strip() == "REQUEST_CHANGES"
