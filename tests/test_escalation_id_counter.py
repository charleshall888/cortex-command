"""Standalone verification artifact for Task 6 of the MCP control-plane spec.

Covers R17 + R18 of the escalations migration:

- ``_next_escalation_n`` counts within a per-session escalations file
  (counter scope is per-session, not repo-wide).
- ``escalation_id`` includes the ``session_id`` prefix so IDs remain
  globally unique even though the counter scope is per-session.
- Two distinct sessions writing the same feature+round produce distinct
  ``escalation_id`` values.

Note: this test exercises only ``deferral.py`` directly. The matching
caller updates in ``outcome_router.py`` and ``feature_executor.py`` are
the responsibility of Task 7; existing test fixtures elsewhere will be
red until that follow-up lands.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cortex_command.overnight.deferral import (
    EscalationEntry,
    _next_escalation_n,
    write_escalation,
)


def _make_session_dir(parent: Path, name: str) -> Path:
    """Create and return a per-session directory under *parent*."""
    session_dir = parent / "sessions" / name
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def test_scoped_to_session_dir() -> None:
    """`_next_escalation_n` counts only within the per-session file.

    Write 2 entries to fixture session A and 1 to session B with the
    same feature+round, then assert next-N = 3 for A and 2 for B.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session_a = _make_session_dir(root, "alpha-2026-04-24")
        session_b = _make_session_dir(root, "bravo-2026-04-24")

        feature = "feat-x"
        round_n = 1

        # Two escalations in session A.
        for n in (1, 2):
            entry = EscalationEntry.build(
                session_id="alpha-2026-04-24",
                feature=feature,
                round=round_n,
                n=n,
                question=f"Q{n}?",
                context=f"ctx{n}",
            )
            write_escalation(entry, session_dir=session_a)

        # One escalation in session B.
        entry_b = EscalationEntry.build(
            session_id="bravo-2026-04-24",
            feature=feature,
            round=round_n,
            n=1,
            question="QB1?",
            context="ctxB1",
        )
        write_escalation(entry_b, session_dir=session_b)

        # Counter is scoped to each session_dir independently.
        assert _next_escalation_n(feature, round_n, session_a) == 3
        assert _next_escalation_n(feature, round_n, session_b) == 2


def test_escalation_id_includes_session_prefix() -> None:
    """The persisted escalation_id matches `{session_id}-{feature}-{round}-q{N}`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session_id = "alpha-2026-04-24"
        session_dir = _make_session_dir(root, session_id)

        feature = "feat-y"
        round_n = 7
        n = _next_escalation_n(feature, round_n, session_dir)
        assert n == 1

        entry = EscalationEntry.build(
            session_id=session_id,
            feature=feature,
            round=round_n,
            n=n,
            question="Should we proceed?",
            context="Investigating",
        )
        expected_id = f"{session_id}-{feature}-{round_n}-q{n}"
        assert entry.escalation_id == expected_id

        write_escalation(entry, session_dir=session_dir)

        escalations_path = session_dir / "escalations.jsonl"
        assert escalations_path.is_file()
        line = escalations_path.read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert record["escalation_id"] == expected_id
        assert record["session_id"] == session_id
        assert record["feature"] == feature
        assert record["round"] == round_n


def test_escalation_ids_unique_across_two_sessions_same_feature_same_round() -> None:
    """Two sessions writing the same feature+round produce distinct IDs.

    The per-session counter would otherwise produce identical N values;
    the session_id prefix is what guarantees global uniqueness.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session_a_id = "alpha-2026-04-24"
        session_b_id = "bravo-2026-04-24"
        session_a = _make_session_dir(root, session_a_id)
        session_b = _make_session_dir(root, session_b_id)

        feature = "shared-feature"
        round_n = 3

        n_a = _next_escalation_n(feature, round_n, session_a)
        n_b = _next_escalation_n(feature, round_n, session_b)
        # Same counter value because each session is empty.
        assert n_a == n_b == 1

        entry_a = EscalationEntry.build(
            session_id=session_a_id,
            feature=feature,
            round=round_n,
            n=n_a,
            question="QA?",
            context="ctxA",
        )
        entry_b = EscalationEntry.build(
            session_id=session_b_id,
            feature=feature,
            round=round_n,
            n=n_b,
            question="QB?",
            context="ctxB",
        )

        write_escalation(entry_a, session_dir=session_a)
        write_escalation(entry_b, session_dir=session_b)

        # Even though feature, round, and N collide, the IDs differ
        # because of the session_id prefix.
        assert entry_a.escalation_id != entry_b.escalation_id
        assert entry_a.escalation_id.startswith(f"{session_a_id}-")
        assert entry_b.escalation_id.startswith(f"{session_b_id}-")
