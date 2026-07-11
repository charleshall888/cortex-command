"""Positive fold-completion discriminator for the 374 Phase-4 write-path fold.

The two overnight/pipeline transition-decision writers —
``cortex_command/overnight/advance_lifecycle.py`` and
``cortex_command/pipeline/review_dispatch.py`` — are **folded, not sanctioned**
(spec R15): they stop DECIDING transitions and route the decision + emission
through the shared ``advance``/B1 verb bodies, passing gathered facts as
arguments. This test is the *positive* structural discriminator for that fold.

It is NOT the raw-write census (``tests/test_events_log_writer_census.py``): the
census scans only raw-write syntax (``open(...,"a")``/``os.replace``/
``NamedTemporaryFile``), and both modules emit via ``log_event``/``log_event_at``
— they were never census hits, so the census is structurally blind to a
``log_event``-routed independent transition decision (decision authority is not a
write-syntax property; residue class-B, Angle-4 objection). This test closes that
gap with an AST check over the REAL module source: it FAILS if either module
contains any ``log_event``/``log_event_at`` call whose ``event`` argument is a
transition-vocabulary literal, i.e. asserts the module emits no transition rows
of its own — plus an assertion that each module invokes the advance body.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# The transition-vocabulary event names a folded module must NOT emit itself —
# these are the state-moving rows whose decision authority moved to the
# table/advance body. A log_event/log_event_at call naming one of these is an
# independent transition decision the fold forbids.
TRANSITION_VOCABULARY: frozenset[str] = frozenset(
    {
        "phase_transition",
        "review_verdict",
        "feature_complete",
        "spec_approved",
        "plan_approved",
    }
)

# The two emitter functions the discriminator watches (both funnel to the
# flock+O_APPEND writer). ``log_event_at`` may be imported under an alias
# (review_dispatch historically bound ``log_event_at as log_event``), so the
# scanner keys on the CALLED name, and we treat both bare names as emitters.
_EMITTER_NAMES: frozenset[str] = frozenset({"log_event", "log_event_at"})

_REPO_ROOT = Path(__file__).resolve().parents[1]

# The folded modules, by import path -> source file.
FOLDED_MODULES = {
    "cortex_command.overnight.advance_lifecycle": _REPO_ROOT
    / "cortex_command"
    / "overnight"
    / "advance_lifecycle.py",
    "cortex_command.pipeline.review_dispatch": _REPO_ROOT
    / "cortex_command"
    / "pipeline"
    / "review_dispatch.py",
}


def _string_constants(node: ast.AST) -> list[str]:
    """Return every string ``Constant`` value reachable directly on *node* as a
    call-argument shape the scanner understands: a keyword ``event=<str>`` or a
    dict literal ``{"event": <str>, ...}`` argument. This is intentionally
    scoped to the ``event`` slot — a string like an issue message that merely
    equals a vocabulary word elsewhere in the call is not a transition decision.
    """
    found: list[str] = []
    if not isinstance(node, ast.Call):
        return found
    # keyword form: log_event(event="phase_transition", ...)
    for kw in node.keywords:
        if kw.arg == "event" and isinstance(kw.value, ast.Constant) and isinstance(
            kw.value.value, str
        ):
            found.append(kw.value.value)
    # dict form: log_event_at(path, {"event": "phase_transition", ...})
    for arg in node.args:
        if isinstance(arg, ast.Dict):
            for k, v in zip(arg.keys, arg.values):
                if (
                    isinstance(k, ast.Constant)
                    and k.value == "event"
                    and isinstance(v, ast.Constant)
                    and isinstance(v.value, str)
                ):
                    found.append(v.value)
    return found


def _called_name(node: ast.Call) -> str | None:
    """Return the simple called name for *node* (``foo`` for ``foo(...)`` or
    ``pkg.foo(...)``), or None."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def transition_event_emissions(source: str, filename: str = "<src>") -> list[tuple[int, str]]:
    """Scan *source* and return ``(lineno, event_name)`` for every emitter call
    that names a transition-vocabulary event in its ``event`` slot.

    The discriminator: a non-empty result means the module still DECIDES a
    transition (emits a transition row itself) rather than routing it through
    the advance/table body.
    """
    tree = ast.parse(source, filename=filename)
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _called_name(node) not in _EMITTER_NAMES:
            continue
        for event_name in _string_constants(node):
            if event_name in TRANSITION_VOCABULARY:
                violations.append((node.lineno, event_name))
    return violations


def invokes_advance_body(source: str, filename: str = "<src>") -> bool:
    """True iff *source* calls the shared ``advance`` verb body (directly or via
    a wrapper whose name contains ``advance``) — the positive half of the
    discriminator: the module routes its transition through the advance body."""
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _called_name(node)
            if name is not None and ("advance" in name):
                return True
    return False


@pytest.mark.parametrize("module_path", sorted(FOLDED_MODULES), ids=lambda p: p.rsplit(".", 1)[-1])
def test_folded_module_emits_no_transition_vocabulary(module_path: str) -> None:
    """FAILS if the folded module re-introduces a transition-vocabulary
    ``log_event``/``log_event_at`` emission — the structural fold-completion gate.
    Runs against the REAL module source (AST of the actual file), never a copy."""
    src_file = FOLDED_MODULES[module_path]
    source = src_file.read_text(encoding="utf-8")
    violations = transition_event_emissions(source, filename=str(src_file))
    assert violations == [], (
        f"{module_path} still emits transition-vocabulary rows itself (the fold "
        f"is incomplete — route these through the advance/table body): "
        + "; ".join(f"line {ln}: event={ev!r}" for ln, ev in violations)
    )


@pytest.mark.parametrize("module_path", sorted(FOLDED_MODULES), ids=lambda p: p.rsplit(".", 1)[-1])
def test_folded_module_invokes_advance_body(module_path: str) -> None:
    """The positive half: each folded module must actually invoke the advance
    body (route the decision through it), not merely fall silent."""
    src_file = FOLDED_MODULES[module_path]
    source = src_file.read_text(encoding="utf-8")
    assert invokes_advance_body(source, filename=str(src_file)), (
        f"{module_path} does not invoke the advance body — the fold routes the "
        f"transition decision through advance()."
    )


# ---------------------------------------------------------------------------
# Detector self-tests — prove the discriminator has teeth WITHOUT touching the
# real files (the discriminator itself asserts against the real module AST).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snippet",
    [
        # keyword form
        'log_event(event="phase_transition", feature=f, fields=[])',
        'log_event(event="feature_complete", feature=f)',
        # aliased/dict form (review_dispatch's historical shape)
        'log_event(path, {"event": "review_verdict", "feature": f})',
        'log_event_at(path, {"event": "plan_approved", "feature": f})',
        'log_event_at(path, {"event": "spec_approved"})',
    ],
)
def test_detector_flags_reintroduced_transition_emission(snippet: str) -> None:
    """A reintroduced transition-vocabulary emission (either call shape) is
    caught — the red-proof, encoded so it cannot silently rot."""
    assert transition_event_emissions(snippet) != []


@pytest.mark.parametrize(
    "snippet",
    [
        # non-transition events are fine (telemetry / other vocabulary)
        'log_event(event="lifecycle_start", feature=f)',
        'log_event_at(path, {"event": "pr_opened", "number": 1})',
        # a vocabulary word appearing outside the event slot is not a decision
        'log_event_at(path, {"event": "batch_dispatch", "note": "phase_transition"})',
        # calling advance is not an emission
        'advance(verb="review-verdict", verdict="APPROVED")',
    ],
)
def test_detector_ignores_non_transition_emissions(snippet: str) -> None:
    assert transition_event_emissions(snippet) == []
