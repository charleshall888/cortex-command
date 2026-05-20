"""Atomic CLI helpers for the /cortex-core:discovery skill.

The discovery skill emits three new event types per spec R8b:

  - ``architecture_section_written``    (research-phase Architecture write)
  - ``approval_checkpoint_responded``   (R4 research->decompose gate AND
                                         R15 decompose->commit batch-review gate)
  - ``prescriptive_check_run``          (decompose-phase ticket-body scan)

Each event carries a small but non-trivial payload (e.g. the
``prescriptive_check_run.flag_locations[]`` nested array) that meets the
project.md L33 "skill-helper module" paraphrase-vulnerability threshold:
authoring the JSON inline in skill prose invites the orchestrator-LLM to
silently drop fields or fold the array shape.

This module collapses each emission into one atomic CLI subcommand that
fuses input validation + JSONL append + path resolution. The orchestrator
invokes:

  python3 -m cortex_command.discovery emit-architecture-written ...
  python3 -m cortex_command.discovery emit-checkpoint-response  ...
  python3 -m cortex_command.discovery emit-prescriptive-check   ...
  python3 -m cortex_command.discovery resolve-events-log-path   ...

The first three emit-* subcommands internally call ``resolve-events-log-path``
to pick the correct events.log target -- never hardcoded. Path resolution
rules (spec R9 + R13 + EVT-1):

  1. If ``LIFECYCLE_SESSION_ID`` is set in the env AND a lifecycle directory
     under ``{repo_root}/cortex/lifecycle/`` contains a ``.session`` (or
     ``.session-owner``) file whose contents byte-equal that ID, the active
     lifecycle slug is that directory's basename and the target is
     ``cortex/lifecycle/{lifecycle-slug}/events.log``.

  2. Otherwise, when the supplied topic slug has a trailing ``-N`` suffix
     (decimal integer, N >= 2 per R13's re-run rule), the target is
     ``cortex/research/{topic}-N/events.log``.

  3. Otherwise, the target is ``cortex/research/{topic}/events.log``.

Public functions are importable for unit testing; the CLI is a thin
argparse wrapper.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cortex_command._brief_scoring import _score_brief_patterns


# ---------------------------------------------------------------------------
# Defaults: resolve repo root from git toplevel
# ---------------------------------------------------------------------------

def _default_repo_root() -> str:
    """Resolve the git toplevel as the default repo root."""
    try:
        toplevel = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "Could not resolve git toplevel; run from inside a git "
            "repository or pass --repo-root explicitly."
        ) from e
    return toplevel


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with seconds."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Active-lifecycle detection
# ---------------------------------------------------------------------------

def _active_lifecycle_slug(repo_root: Path) -> str | None:
    """Return the active lifecycle slug under ``repo_root``, or ``None``.

    The SessionStart hook (``hooks/cortex-scan-lifecycle.sh``) injects
    ``LIFECYCLE_SESSION_ID`` into the environment. The active lifecycle
    feature is the ``cortex/lifecycle/<slug>/`` directory whose ``.session`` (or
    chain-migrated ``.session-owner``) file contents byte-equal that ID.

    Args:
        repo_root: Absolute path to the repo root.

    Returns:
        The matching lifecycle slug, or ``None`` if no env var is set, no
        ``cortex/lifecycle/`` directory exists, or no slug's ``.session`` matches.
    """
    session_id = os.environ.get("LIFECYCLE_SESSION_ID", "").strip()
    if not session_id:
        return None
    lifecycle_dir = repo_root / "cortex" / "lifecycle"
    if not lifecycle_dir.is_dir():
        return None
    for candidate in sorted(lifecycle_dir.iterdir()):
        if not candidate.is_dir():
            continue
        if candidate.name == "archive":
            continue
        for marker_name in (".session", ".session-owner"):
            marker = candidate / marker_name
            if not marker.is_file():
                continue
            try:
                content = marker.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if content == session_id:
                return candidate.name
    return None


# ---------------------------------------------------------------------------
# Slug-to-events.log path resolution (spec R9 + R13 + EVT-1)
# ---------------------------------------------------------------------------

_TOPIC_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
_RERUN_SUFFIX_RE = re.compile(r"-(\d+)$")


def _validate_topic_slug(slug: str) -> None:
    """Reject slugs that are empty, path-traversal, or non-kebab-case.

    Raises:
        ValueError: with a message naming the offending slug.
    """
    if not slug:
        raise ValueError("topic slug must be non-empty")
    if "/" in slug or "\\" in slug or ".." in slug:
        raise ValueError(
            f"topic slug must not contain path separators or '..': {slug!r}"
        )
    if not _TOPIC_SLUG_RE.match(slug):
        raise ValueError(
            f"topic slug must be lowercase-kebab-case: {slug!r}"
        )


def resolve_events_log_path(
    topic: str,
    repo_root: Path,
) -> Path:
    """Resolve the events.log target for the discovery skill.

    Resolution rules (spec R9 + R13 + EVT-1):

      1. If an active lifecycle is detected (``LIFECYCLE_SESSION_ID`` env
         set AND a ``cortex/lifecycle/<slug>/.session`` file matches), the target
         is ``{repo_root}/cortex/lifecycle/{lifecycle-slug}/events.log``. The
         topic argument is honored for slug validation but the lifecycle
         path takes precedence per EVT-1.

      2. Otherwise, if ``topic`` has a trailing ``-N`` decimal suffix
         (R13 re-run semantics, N >= 2), the target is
         ``{repo_root}/cortex/research/{topic}/events.log`` where the ``-N`` is
         already in the slug.

      3. Otherwise, the target is ``{repo_root}/cortex/research/{topic}/events.log``.

    Args:
        topic: The discovery topic slug (lowercase-kebab-case, may carry a
            ``-N`` re-run suffix).
        repo_root: Absolute path to the repo root.

    Returns:
        The absolute path to the events.log target. Parent directory may
        not yet exist; ``append_event`` creates it on write.

    Raises:
        ValueError: If ``topic`` fails slug validation.
    """
    _validate_topic_slug(topic)
    lifecycle_slug = _active_lifecycle_slug(repo_root)
    if lifecycle_slug is not None:
        return repo_root / "cortex" / "lifecycle" / lifecycle_slug / "events.log"
    # Cases (2) and (3) both produce cortex/research/{topic}/events.log -- the
    # -N suffix is already part of the slug per R13 (the agent generates
    # ``{topic}-2`` and passes that as the topic argument). Per spec R9:
    # "When the slug has a -N suffix (per R13 re-run semantics), the
    # resolver returns cortex/research/{topic}-N/events.log" -- i.e. the same
    # cortex/research/{slug}/events.log shape, with the slug already including
    # the suffix.
    return repo_root / "cortex" / "research" / topic / "events.log"


def _has_rerun_suffix(topic: str) -> bool:
    """Return True if ``topic`` ends with a ``-N`` decimal suffix (N >= 2)."""
    m = _RERUN_SUFFIX_RE.search(topic)
    if not m:
        return False
    try:
        return int(m.group(1)) >= 2
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Atomic events.log append (tempfile + os.replace) -- ported from
# critical_review.py to keep both helpers consistent.
# ---------------------------------------------------------------------------

def append_event(events_log_path: Path, event: dict) -> None:
    """Atomically append a JSON event line to ``events_log_path``.

    Uses tempfile + ``os.replace`` rather than ``open(path, 'a')`` so the
    append is atomic against concurrent emitters.

    Args:
        events_log_path: Path to the JSONL events log.
        event: Dict to serialize as one JSONL line.
    """
    events_log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = b""
    if events_log_path.exists():
        existing = events_log_path.read_bytes()
        if existing and not existing.endswith(b"\n"):
            existing += b"\n"

    line = (
        json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")

    tmp = tempfile.NamedTemporaryFile(
        dir=str(events_log_path.parent),
        prefix=f".{events_log_path.name}-",
        suffix=".tmp",
        delete=False,
    )
    try:
        tmp.write(existing)
        tmp.write(line)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, events_log_path)
    except BaseException:
        try:
            tmp.close()
        except Exception:
            pass
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Gate brief word cap (derived from corpus measurement; see
# cortex/lifecycle/discovery-output-density-investigate-author-centric/word-cap-derivation.md)
# ---------------------------------------------------------------------------

GATE_BRIEF_WORD_CAP: int = 250
"""Maximum word count for the research→decompose gate brief.

Original derivation: 90th percentile of compressed Headline Finding word
counts across the cortex/research corpus, applying the 2.5× compression
baseline from the prior reader study, rounded to the nearest 25 words →
150 words.

Loosened to 250 after observing that the Sonnet sub-agent producing the
brief consistently emits ~300-word output regardless of the explicit
word target in the rubric — a well-known SDK pattern where word-count
instructions in system prompts are weakly enforced. The 250 cap (+25
tolerance = 275 effective ceiling) accommodates the model's natural
compression while still distinguishing a tight gate brief from a full
section dump. Pair with the retry-on-overflow logic in
``_cmd_generate_brief`` for additional resilience.
"""

_GATE_BRIEF_EXAMPLE_TOKENS: dict[str, tuple[str, ...]] = {
    "decision": ("decided", "chose", "settled", "selected"),
    "alternatives": ("alternatives", "options", "considered", "weighed"),
    "tradeoff": ("tradeoff", "cost", "drawback", "compromise"),
}
"""Agent-facing representative tokens per anchor, drawn from the canonical floor.

Single source of truth for tokens that appear in agent-facing prose:
``GATE_BRIEF_RUBRIC`` examples (this module) and the retry-feedback prompt
(see ``_cmd_generate_brief``). This is **not** the validator's accepted
vocabulary — the validator accepts the full 30-token canonical floor
(Reqs 3-5 of the fix-validate-brief-substring-anchors spec), pinned by a
frozen literal in ``tests/test_discovery_gate_brief.py``. The deliberate
asymmetry between agent-facing examples and validator-accepted vocabulary
is the regression guard against lockstep shrinkage.
"""

GATE_BRIEF_RUBRIC: str = f"""\
You are writing a gate brief for a software-development discovery run. \
Your reader is the developer who will approve, revise, drop, or promote \
the topic after reading your brief. Write as if you are talking directly \
to that developer in plain natural prose — no headers, no bullets, \
no numbered lists, no labels, no Markdown formatting.

Your brief must answer three questions in order:

1. What was {_GATE_BRIEF_EXAMPLE_TOKENS['decision'][0]}? State the central \
conclusion of the research in one or two sentences. Use ordinary words — \
verbs like {', '.join(_GATE_BRIEF_EXAMPLE_TOKENS['decision'])} are all fine. \
Do not argue with the finding — just state what the research settled on.

2. What {_GATE_BRIEF_EXAMPLE_TOKENS['alternatives'][0]} were \
{_GATE_BRIEF_EXAMPLE_TOKENS['alternatives'][2]}? Name the \
{_GATE_BRIEF_EXAMPLE_TOKENS['alternatives'][0]} or \
{_GATE_BRIEF_EXAMPLE_TOKENS['alternatives'][1]} that were \
{_GATE_BRIEF_EXAMPLE_TOKENS['alternatives'][2]} or \
{_GATE_BRIEF_EXAMPLE_TOKENS['alternatives'][3]} on the table, and briefly \
explain why each was not chosen or was held as a phase-2 trigger.

3. What {_GATE_BRIEF_EXAMPLE_TOKENS['tradeoff'][0]} was accepted? Name the \
concrete {_GATE_BRIEF_EXAMPLE_TOKENS['tradeoff'][1]}, \
{_GATE_BRIEF_EXAMPLE_TOKENS['tradeoff'][2]}, or \
{_GATE_BRIEF_EXAMPLE_TOKENS['tradeoff'][3]} the chosen direction carries \
(equivalently a {_GATE_BRIEF_EXAMPLE_TOKENS['tradeoff'][0]}). Be specific \
— "it is simpler but does not cover X" is acceptable; "there are tradeoffs" \
is not.

Word target: write no more than {GATE_BRIEF_WORD_CAP} words. If you cannot \
fit the three questions within that budget, compress the alternatives section \
first — never drop the tradeoff or the decision.

Strict prohibitions — do not use any of the following in your output:
- The tokens DR-N, OQ-N, RQ-N, or §N (any numbered label of this pattern)
- The phrase "named contract surfaces"
- The phrase "walked back"
- The phrase "decomposition history"
- The phrase "per template rule"
- Citation suffixes such as [path:line] or any [file:number] pattern
- Any reference to the structure or history of the research document itself \
(e.g. "the research noted", "in the architecture section", \
"the original decomposition")

Do not start with a title, heading, or the word "Brief". \
Begin directly with the decision statement.
"""
"""Rubric injected as the system prompt for the ``generate-brief`` sub-dispatch.

The rubric structures output around the decision-content fidelity anchor
(decided / alternatives / tradeoff) and prohibits the six reader-study
patterns identified in research.md: forward refs to undefined vocab (DR-N,
OQ-N, RQ-N, §N), named-contract-surface phrasing, walked-back author-process
narration, decomposition-history narration, per-template-rule narration, and
citation-as-credibility-signal suffixes.

The word target references ``GATE_BRIEF_WORD_CAP`` by name in the rubric
prose so changes to the cap constant propagate without rewriting the rubric.
"""


_GATE_BRIEF_RETRY_TEMPLATE: str = (
    "Your previous attempt failed validation: {reason}\n"
    "\n"
    f"Rewrite at no more than {GATE_BRIEF_WORD_CAP} words "
    f"(hard ceiling {GATE_BRIEF_WORD_CAP + 25}). The brief must contain all "
    "three decision-content anchors. Use one of these tokens for the "
    "decision anchor: "
    f"{', '.join(_GATE_BRIEF_EXAMPLE_TOKENS['decision'])}. Use one of these "
    "tokens for the alternatives anchor: "
    f"{', '.join(_GATE_BRIEF_EXAMPLE_TOKENS['alternatives'])}. Use one of "
    "these tokens for the tradeoff anchor: "
    f"{', '.join(_GATE_BRIEF_EXAMPLE_TOKENS['tradeoff'])}. Include at least "
    "one token from each anchor. Compress the alternatives section first if "
    "you must trim — never drop the decision statement or the tradeoff "
    "statement."
)
"""Retry-feedback template bound to ``_GATE_BRIEF_EXAMPLE_TOKENS``.

The token enumerations for each anchor are interpolated from
``_GATE_BRIEF_EXAMPLE_TOKENS`` at module load (single source of truth shared
with ``GATE_BRIEF_RUBRIC``). The ``{reason}`` placeholder is a plain
``str.format`` placeholder — it is NOT an f-string interpolation because
``reason`` is dynamic per dispatch and is supplied at the call site via
``_GATE_BRIEF_RETRY_TEMPLATE.format(reason=...)``.

Per spec Req 9 / Adversarial Review §7: the verbatim "use one of these
tokens" phrasing is preserved deliberately — retry is recovery, not
teaching, and the verbatim phrasing maximizes recovery rate. The retry
feedback exposes only the agent-facing representative subset (the example
tokens), not the validator's full 30-token floor — this is an intentional
asymmetry (see ``_GATE_BRIEF_EXAMPLE_TOKENS`` docstring).
"""


# ---------------------------------------------------------------------------
# Event payload validators
# ---------------------------------------------------------------------------

_CHECKPOINT_VALUES = frozenset({"research-decompose", "decompose-commit"})
_RESPONSE_VALUES = frozenset({
    "approve",
    "revise",
    "drop",
    "promote-sub-topic",
    "approve-all",
    "revise-piece",
    "drop-piece",
})
_STATUS_VALUES = frozenset({"draft", "approved", "revised", "walk-back"})


def _validate_architecture_payload(
    topic: str,
    piece_count: int,
    has_why_n_justification: bool,
    status: str,
    re_walk_attempt: int | None,
) -> None:
    _validate_topic_slug(topic)
    if not isinstance(piece_count, int) or piece_count < 0:
        raise ValueError(
            f"piece_count must be a non-negative int: got {piece_count!r}"
        )
    if not isinstance(has_why_n_justification, bool):
        raise ValueError(
            "has_why_n_justification must be bool: got "
            f"{type(has_why_n_justification).__name__}"
        )
    if status not in _STATUS_VALUES:
        raise ValueError(
            f"status must be one of {sorted(_STATUS_VALUES)}: got {status!r}"
        )
    if re_walk_attempt is not None and (
        not isinstance(re_walk_attempt, int) or re_walk_attempt < 0
    ):
        raise ValueError(
            f"re_walk_attempt must be a non-negative int or None: "
            f"got {re_walk_attempt!r}"
        )


def _validate_checkpoint_payload(
    topic: str,
    checkpoint: str,
    response: str,
    revision_round: int,
) -> None:
    _validate_topic_slug(topic)
    if checkpoint not in _CHECKPOINT_VALUES:
        raise ValueError(
            f"checkpoint must be one of {sorted(_CHECKPOINT_VALUES)}: "
            f"got {checkpoint!r}"
        )
    if response not in _RESPONSE_VALUES:
        raise ValueError(
            f"response must be one of {sorted(_RESPONSE_VALUES)}: "
            f"got {response!r}"
        )
    if not isinstance(revision_round, int) or revision_round < 0:
        raise ValueError(
            f"revision_round must be a non-negative int: got {revision_round!r}"
        )


def _validate_prescriptive_payload(
    topic: str,
    tickets_checked: int,
    flagged_count: int,
    flag_locations: list,
) -> None:
    _validate_topic_slug(topic)
    if not isinstance(tickets_checked, int) or tickets_checked < 0:
        raise ValueError(
            f"tickets_checked must be a non-negative int: got "
            f"{tickets_checked!r}"
        )
    if not isinstance(flagged_count, int) or flagged_count < 0:
        raise ValueError(
            f"flagged_count must be a non-negative int: got {flagged_count!r}"
        )
    if not isinstance(flag_locations, list):
        raise ValueError(
            f"flag_locations must be a list: got "
            f"{type(flag_locations).__name__}"
        )
    for i, loc in enumerate(flag_locations):
        if not isinstance(loc, dict):
            raise ValueError(
                f"flag_locations[{i}] must be a dict: got "
                f"{type(loc).__name__}"
            )
        for required_key in ("ticket", "section", "signal"):
            if required_key not in loc:
                raise ValueError(
                    f"flag_locations[{i}] missing required key "
                    f"{required_key!r}: {loc!r}"
                )


# ---------------------------------------------------------------------------
# Emit helpers (importable)
# ---------------------------------------------------------------------------

def emit_architecture_written(
    topic: str,
    piece_count: int,
    has_why_n_justification: bool,
    status: str,
    repo_root: Path,
    re_walk_attempt: int | None = None,
) -> Path:
    """Validate + emit one ``architecture_section_written`` event.

    Returns the events.log path written to.
    """
    _validate_architecture_payload(
        topic, piece_count, has_why_n_justification, status, re_walk_attempt
    )
    events_log = resolve_events_log_path(topic, repo_root)
    event: dict = {
        "ts": _now_iso(),
        "event": "architecture_section_written",
        "topic": topic,
        "piece_count": piece_count,
        "has_why_n_justification": has_why_n_justification,
        "status": status,
    }
    if re_walk_attempt is not None:
        event["re_walk_attempt"] = re_walk_attempt
    append_event(events_log, event)
    return events_log


def emit_checkpoint_response(
    topic: str,
    checkpoint: str,
    response: str,
    revision_round: int,
    repo_root: Path,
) -> Path:
    """Validate + emit one ``approval_checkpoint_responded`` event.

    Returns the events.log path written to.
    """
    _validate_checkpoint_payload(topic, checkpoint, response, revision_round)
    events_log = resolve_events_log_path(topic, repo_root)
    event = {
        "ts": _now_iso(),
        "event": "approval_checkpoint_responded",
        "topic": topic,
        "checkpoint": checkpoint,
        "response": response,
        "revision_round": revision_round,
    }
    append_event(events_log, event)
    return events_log


def emit_prescriptive_check(
    topic: str,
    tickets_checked: int,
    flagged_count: int,
    flag_locations: list,
    repo_root: Path,
) -> Path:
    """Validate + emit one ``prescriptive_check_run`` event.

    Returns the events.log path written to.
    """
    _validate_prescriptive_payload(
        topic, tickets_checked, flagged_count, flag_locations
    )
    events_log = resolve_events_log_path(topic, repo_root)
    event = {
        "ts": _now_iso(),
        "event": "prescriptive_check_run",
        "topic": topic,
        "tickets_checked": tickets_checked,
        "flagged_count": flagged_count,
        "flag_locations": flag_locations,
    }
    append_event(events_log, event)
    return events_log


# ---------------------------------------------------------------------------
# Brief validation helper (used by generator pre-persist and test suite)
# ---------------------------------------------------------------------------

_VALIDATE_BRIEF_DECISION_TOKENS: tuple[str, ...] = (
    "decide",
    "decided",
    "decision",
    "decisions",
    "chose",
    "chosen",
    "concluded",
    "settled",
    "selected",
    "picked",
    "opted",
    "agreed",
)
"""Canonical floor of decision-anchor tokens accepted by ``validate_brief()``.

Frozen by spec Req 3 (fix-validate-brief-substring-anchors). The parity test
in ``tests/test_discovery_gate_brief.py`` pins this set against an
independently-declared literal so silent shrinkage is caught.
"""

_VALIDATE_BRIEF_ALTERNATIVES_TOKENS: tuple[str, ...] = (
    "alternative",
    "alternatives",
    "option",
    "options",
    "considered",
    "considerations",
    "weighed",
    "evaluated",
    "rejected",
)
"""Canonical floor of alternatives-anchor tokens accepted by ``validate_brief()``.

Frozen by spec Req 4. Both ``considered`` and ``considerations`` are
enumerated separately — under word-boundary regex, ``\\bconsidered\\b`` does
not match within ``considerations`` (boundary at position 9 fails because
both adjacent chars are ``\\w``).
"""

_VALIDATE_BRIEF_TRADEOFF_TOKENS: tuple[str, ...] = (
    "tradeoff",
    "trade-off",
    "cost",
    "drawback",
    "downside",
    "sacrifice",
    "consequence",
    "compromise",
    "risk",
)
"""Canonical floor of tradeoff-anchor tokens accepted by ``validate_brief()``.

Frozen by spec Req 5. ``trade-off`` matches under Python's ``\\b`` because
the hyphen is a ``\\W`` character.
"""


def _anchor_match(brief: str, tokens: tuple[str, ...]) -> bool:
    """Return True if any token in ``tokens`` appears in ``brief`` as a whole word.

    Matching is case-insensitive and uses Python's ``\\b`` word-boundary
    semantics, which treats ``-`` as ``\\W`` (so hyphenated tokens like
    ``trade-off`` match correctly).
    """
    for tok in tokens:
        if re.search(r"\b" + re.escape(tok) + r"\b", brief, re.IGNORECASE):
            return True
    return False


def validate_brief(brief: str) -> tuple[bool, str]:
    """Check a generated brief for decision-content anchors and word-cap tolerance.

    Decision-content anchors. The brief must contain at least one token from
    each of three canonical floors. Matching is case-insensitive and uses
    Python's ``\\b`` word-boundary regex (via ``_anchor_match``): a token
    matches only as a whole word, so ``decide`` does not match inside
    ``undecided`` or ``decides``. The hyphen in ``trade-off`` is treated as
    ``\\W`` by ``\\b``, so the hyphenated form matches as a single token. The
    canonical sets are pinned by the parity test in
    ``tests/test_discovery_gate_brief.py``; the authoritative tuples live at
    module scope:

    - decision (12 tokens, ``_VALIDATE_BRIEF_DECISION_TOKENS``): ``decide``,
      ``decided``, ``decision``, ``decisions``, ``chose``, ``chosen``,
      ``concluded``, ``settled``, ``selected``, ``picked``, ``opted``,
      ``agreed``.
    - alternatives (9 tokens, ``_VALIDATE_BRIEF_ALTERNATIVES_TOKENS``):
      ``alternative``, ``alternatives``, ``option``, ``options``,
      ``considered``, ``considerations``, ``weighed``, ``evaluated``,
      ``rejected``. Both ``considered`` and ``considerations`` are listed
      separately because ``\\bconsidered\\b`` does not match inside
      ``considerations`` under word-boundary semantics.
    - tradeoff (9 tokens, ``_VALIDATE_BRIEF_TRADEOFF_TOKENS``): ``tradeoff``,
      ``trade-off``, ``cost``, ``drawback``, ``downside``, ``sacrifice``,
      ``consequence``, ``compromise``, ``risk``.

    Word-cap tolerance: the brief must be at most ``GATE_BRIEF_WORD_CAP + 25``
    words (Req 5a).

    Args:
        brief: The generated brief text to validate.

    Returns:
        A tuple ``(ok, reason)`` where ``ok`` is ``True`` when the brief passes
        all checks, and ``reason`` is an empty string on success or a
        human-readable failure description on failure.
    """
    if not brief or not brief.strip():
        return False, "brief is empty"

    # Decision anchor
    if not _anchor_match(brief, _VALIDATE_BRIEF_DECISION_TOKENS):
        return False, (
            "brief is missing decision anchor (one of: "
            "decided, chose, settled, ...)"
        )

    # Alternatives anchor
    if not _anchor_match(brief, _VALIDATE_BRIEF_ALTERNATIVES_TOKENS):
        return False, (
            "brief is missing alternatives anchor (one of: "
            "alternatives, options, considered, weighed, evaluated, "
            "rejected, ...)"
        )

    # Tradeoff anchor
    if not _anchor_match(brief, _VALIDATE_BRIEF_TRADEOFF_TOKENS):
        return False, (
            "brief is missing tradeoff anchor (one of: "
            "tradeoff, cost, drawback, downside, compromise, risk, ...)"
        )

    # Word-cap tolerance
    word_count = len(brief.split())
    cap = GATE_BRIEF_WORD_CAP + 25
    if word_count > cap:
        return False, (
            f"brief word count {word_count} exceeds cap {cap} "
            f"(GATE_BRIEF_WORD_CAP={GATE_BRIEF_WORD_CAP} + 25 tolerance)"
        )

    return True, ""


# ---------------------------------------------------------------------------
# generate-brief: fresh-context sub-dispatch
# ---------------------------------------------------------------------------

try:
    from claude_agent_sdk import (  # type: ignore[import]
        query as _sdk_query,
        ClaudeAgentOptions as _ClaudeAgentOptions,
        AssistantMessage as _AssistantMessage,
        TextBlock as _TextBlock,
    )
    _BRIEF_SDK_AVAILABLE = True
except ImportError:
    _BRIEF_SDK_AVAILABLE = False


def _derive_topic_from_path(research_md: Path) -> str | None:
    """Attempt to derive a topic slug from the parent directory of research.md.

    Returns the grandparent directory name when the path matches
    ``cortex/research/<topic>/research.md`` or similar, otherwise returns
    ``None``.  The result is validated via ``_TOPIC_SLUG_RE``; non-conformant
    values are silently dropped (the caller falls back to omitting the event
    path resolution).
    """
    # research_md.parent is the topic dir; its name is the slug.
    candidate = research_md.parent.name
    if candidate and _TOPIC_SLUG_RE.match(candidate):
        return candidate
    return None


async def _run_brief_query(
    research_md_content: str,
    retry_feedback: str | None = None,
) -> str:
    """Dispatch a fresh-context sub-agent to generate a gate brief.

    Uses ``claude_agent_sdk.query()`` directly — not ``dispatch_task`` — to
    avoid the full pipeline overhead (worktrees, sandbox settings, session
    dirs) that is unsuitable for a single-shot brief generation.  The fresh
    context is load-bearing: it resets the attention-decay window that drove
    Phase 1 drift (per research.md §"Mechanisms that BIND prose-output
    constraints").

    Args:
        research_md_content: The research.md content to summarize.
        retry_feedback: When non-empty, this string is prepended to the
            prompt inside a ``<retry-feedback>`` block so the sub-agent
            can correct the prior validation failure (e.g. an over-cap
            word count). The fresh context is preserved per dispatch;
            ``retry_feedback`` is the only signal carried across attempts.

    Returns:
        The brief text collected from the agent's assistant messages.

    Raises:
        RuntimeError: If ``claude_agent_sdk`` is not installed.
    """
    if not _BRIEF_SDK_AVAILABLE:
        raise RuntimeError(
            "claude_agent_sdk is not installed. "
            "Install it with: pip install claude-agent-sdk"
        )

    # Clear CLAUDECODE so the sub-agent does not hit the nested-session guard.
    _env: dict[str, str] = {
        "CLAUDECODE": "",
        "TMPDIR": os.environ.get("TMPDIR") or tempfile.gettempdir(),
    }
    if _api_key := os.environ.get("ANTHROPIC_API_KEY"):
        _env["ANTHROPIC_API_KEY"] = _api_key
    if _oauth_token := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        _env["CLAUDE_CODE_OAUTH_TOKEN"] = _oauth_token

    options = _ClaudeAgentOptions(
        model="sonnet",
        max_turns=3,
        system_prompt=GATE_BRIEF_RUBRIC,
        env=_env,
        permission_mode="bypassPermissions",
    )

    if retry_feedback:
        prompt = (
            f"<retry-feedback>\n{retry_feedback}\n</retry-feedback>\n\n"
            f"{research_md_content}"
        )
    else:
        prompt = research_md_content

    output_parts: list[str] = []
    async for message in _sdk_query(
        prompt=prompt, options=options
    ):
        if isinstance(message, _AssistantMessage):
            for block in message.content:
                if isinstance(block, _TextBlock):
                    output_parts.append(block.text)

    return "\n".join(output_parts).strip()


def _cmd_generate_brief(args: argparse.Namespace) -> int:
    """Handle the ``generate-brief`` subcommand.

    Reads the research.md content at ``--research-md``, dispatches a
    fresh-context sub-agent with ``GATE_BRIEF_RUBRIC`` as the system prompt,
    captures the brief, and prints it to stdout.  Emits one
    ``gate_brief_generated`` event via ``append_event``.

    When ``--persist-to`` is supplied, the brief is written to that path after
    stdout emission, but only if it passes ``validate_brief``.  On empty
    output, generator failure, or validation failure, persistence is skipped,
    the event carries ``status: "empty"`` or ``"validation_failed"``, and the
    subcommand exits non-zero so the gate's caller can route to the dense
    Architecture fallback.

    Returns 0 on success, non-zero on failure.
    """
    import asyncio

    research_md_path = Path(args.research_md).resolve()
    if not research_md_path.is_file():
        print(
            f"generate-brief: research.md not found: {research_md_path}",
            file=sys.stderr,
        )
        return 2

    try:
        research_content = research_md_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"generate-brief: failed to read research.md: {e}", file=sys.stderr)
        return 2

    # Resolve the optional persist-to path early so we can check writeability.
    persist_to: Path | None = None
    if getattr(args, "persist_to", None):
        persist_to = Path(args.persist_to).resolve()

    # Resolve events log path (best-effort: topic derived from arg or path).
    topic = getattr(args, "topic", None) or _derive_topic_from_path(research_md_path)
    events_log_path: Path | None = None
    if topic is not None:
        repo_root = _resolve_repo_root_arg(args)
        if repo_root is not None:
            try:
                events_log_path = resolve_events_log_path(topic, repo_root)
            except ValueError:
                events_log_path = None

    def _emit_event(
        status: str,
        word_count: int,
        brief_text: str | None = None,
    ) -> None:
        """Best-effort event emission; non-fatal on OSError.

        When ``status == "validation_failed"`` and ``brief_text`` is a
        non-empty string, the event payload includes a ``brief_excerpt``
        field containing the first 200 characters of the rejected brief.
        Successful events (status ``"ok"`` / ``"empty"`` / pre-brief
        failures) omit the field, keeping the schema backward-compatible
        with legacy readers.
        """
        if events_log_path is None:
            return
        payload: dict = {
            "ts": _now_iso(),
            "event": "gate_brief_generated",
            "status": status,
            "brief_word_count": word_count,
            "patterns_detected_count": 0,
        }
        if status == "validation_failed" and brief_text:
            payload["brief_excerpt"] = brief_text[:200]
        try:
            append_event(events_log_path, payload)
        except OSError as exc:
            print(
                f"generate-brief: warning: failed to emit event: {exc}",
                file=sys.stderr,
            )

    # Run the fresh-context dispatch.
    try:
        brief = asyncio.run(_run_brief_query(research_content))
    except RuntimeError as e:
        print(f"generate-brief: SDK not available: {e}", file=sys.stderr)
        _emit_event("validation_failed", 0)
        return 1
    except Exception as e:
        print(f"generate-brief: dispatch failed: {e}", file=sys.stderr)
        _emit_event("validation_failed", 0)
        return 1

    brief_word_count = len(brief.split()) if brief else 0

    # Empty-brief check.
    if not brief:
        print("generate-brief: dispatch returned empty brief", file=sys.stderr)
        _emit_event("empty", 0)
        return 1

    # Decision-content anchor + word-cap validation.
    valid, reason = validate_brief(brief)

    # Retry once on validation failure: the Sonnet sub-agent weakly enforces
    # word targets and decision-anchor instructions from system prompts, so a
    # second dispatch with the specific failure as feedback recovers many
    # otherwise-rejected briefs without expanding the contract.
    if not valid:
        retry_feedback = _GATE_BRIEF_RETRY_TEMPLATE.format(reason=reason)
        try:
            brief = asyncio.run(
                _run_brief_query(research_content, retry_feedback=retry_feedback)
            )
        except RuntimeError as e:
            print(f"generate-brief: retry SDK not available: {e}", file=sys.stderr)
            _emit_event("validation_failed", brief_word_count, brief_text=brief)
            return 1
        except Exception as e:
            print(f"generate-brief: retry dispatch failed: {e}", file=sys.stderr)
            _emit_event("validation_failed", brief_word_count, brief_text=brief)
            return 1

        brief_word_count = len(brief.split()) if brief else 0
        if not brief:
            print(
                "generate-brief: retry dispatch returned empty brief",
                file=sys.stderr,
            )
            _emit_event("empty", 0)
            return 1
        valid, reason = validate_brief(brief)

    if not valid:
        print(
            f"generate-brief: brief failed validation: {reason}",
            file=sys.stderr,
        )
        _emit_event("validation_failed", brief_word_count, brief_text=brief)
        return 1

    # Brief is valid — emit success event and write to stdout.
    _emit_event("ok", brief_word_count)

    sys.stdout.write(brief)
    if not brief.endswith("\n"):
        sys.stdout.write("\n")

    # Persist to file if --persist-to was supplied.
    if persist_to is not None:
        try:
            persist_to.parent.mkdir(parents=True, exist_ok=True)
            persist_to.write_text(brief if brief.endswith("\n") else brief + "\n",
                                  encoding="utf-8")
        except OSError as e:
            print(
                f"generate-brief: warning: failed to persist brief to "
                f"{persist_to}: {e}",
                file=sys.stderr,
            )
            # Persistence failure does not invalidate the brief; exit 0.

    return 0


# ---------------------------------------------------------------------------
# score-corpus: post-merge regression scanner
# ---------------------------------------------------------------------------

def _extract_headline_and_architecture(research_md: Path) -> str:
    """Extract the Headline Finding and Architecture sections from a research.md.

    Used as the fallback scoring target when no brief.md exists for a topic.
    Returns the concatenated text of those two sections, or the full file
    content if neither heading is found.
    """
    try:
        text = research_md.read_text(encoding="utf-8")
    except OSError:
        return ""

    lines = text.splitlines()
    collected: list[str] = []
    in_section = False
    target_headings = {"## Headline Finding", "## Architecture"}

    for line in lines:
        stripped = line.rstrip()
        if stripped in target_headings:
            in_section = True
            collected.append(line)
            continue
        if in_section and stripped.startswith("## ") and stripped not in target_headings:
            in_section = False
            continue
        if in_section:
            collected.append(line)

    if collected:
        return "\n".join(collected).strip()
    # Fallback: return entire file when headings are absent.
    return text.strip()


def _cmd_score_corpus(args: argparse.Namespace) -> int:
    """Handle the ``score-corpus`` subcommand.

    Walks ``--root`` recursively for ``brief.md`` files. When a topic directory
    contains no ``brief.md``, falls back to scoring the Headline Finding and
    Architecture excerpts from ``research.md`` in the same directory.

    Emits one line per file scored to stdout:
        <path> patterns_reproducing=<N>/<6> word_count=<N>

    Exit code is always 0 on a successful walk; non-zero only on argument or
    I/O error.  Pattern-count failures are a report signal for operator retro
    review, not a process-level gate.
    """
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"score-corpus: root path does not exist: {root}", file=sys.stderr)
        return 2

    threshold: int = args.threshold

    # Collect topic directories: any directory under root that either contains
    # a brief.md or a research.md.
    topic_dirs: list[Path] = []
    for candidate in sorted(root.iterdir()):
        if not candidate.is_dir():
            continue
        if (candidate / "brief.md").is_file() or (candidate / "research.md").is_file():
            topic_dirs.append(candidate)

    if not topic_dirs:
        # Also try the root itself if it contains brief.md / research.md directly.
        if (root / "brief.md").is_file() or (root / "research.md").is_file():
            topic_dirs = [root]

    if not topic_dirs:
        print(
            f"score-corpus: no topic directories found under {root} "
            "(expected subdirectories containing brief.md or research.md)",
            file=sys.stderr,
        )
        return 2

    any_scored = False
    for topic_dir in sorted(topic_dirs):
        brief_path = topic_dir / "brief.md"
        if brief_path.is_file():
            try:
                text = brief_path.read_text(encoding="utf-8").strip()
            except OSError as e:
                print(
                    f"score-corpus: warning: could not read {brief_path}: {e}",
                    file=sys.stderr,
                )
                continue
            source_path = brief_path
        else:
            # Fall back to research.md Headline + Architecture excerpts.
            research_path = topic_dir / "research.md"
            if not research_path.is_file():
                continue
            text = _extract_headline_and_architecture(research_path)
            source_path = research_path

        if not text:
            continue

        scores = _score_brief_patterns(text)
        reproducing = sum(scores.values())
        word_count = len(text.split())

        flag = " [FLAGGED]" if reproducing >= threshold else ""
        print(
            f"{source_path} patterns_reproducing={reproducing}/6"
            f" word_count={word_count}{flag}"
        )
        any_scored = True

    if not any_scored:
        print(
            f"score-corpus: no scoreable files found under {root}",
            file=sys.stderr,
        )
        return 2

    return 0


# ---------------------------------------------------------------------------
# CLI subcommand dispatch
# ---------------------------------------------------------------------------

def _resolve_repo_root_arg(args: argparse.Namespace) -> Path | None:
    if args.repo_root:
        return Path(args.repo_root).resolve()
    try:
        return Path(_default_repo_root()).resolve()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return None


def _cmd_resolve_events_log_path(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root_arg(args)
    if repo_root is None:
        return 2
    try:
        target = resolve_events_log_path(args.topic, repo_root)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    sys.stdout.write(str(target) + "\n")
    return 0


def _cmd_emit_architecture_written(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root_arg(args)
    if repo_root is None:
        return 2
    try:
        target = emit_architecture_written(
            topic=args.topic,
            piece_count=args.piece_count,
            has_why_n_justification=args.has_why_n_justification,
            status=args.status,
            repo_root=repo_root,
            re_walk_attempt=args.re_walk_attempt,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Failed to append architecture_section_written event: {e}",
              file=sys.stderr)
        return 2
    sys.stdout.write(str(target) + "\n")
    return 0


def _cmd_emit_checkpoint_response(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root_arg(args)
    if repo_root is None:
        return 2
    try:
        target = emit_checkpoint_response(
            topic=args.topic,
            checkpoint=args.checkpoint,
            response=args.response,
            revision_round=args.revision_round,
            repo_root=repo_root,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Failed to append approval_checkpoint_responded event: {e}",
              file=sys.stderr)
        return 2
    sys.stdout.write(str(target) + "\n")
    return 0


def _cmd_emit_prescriptive_check(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root_arg(args)
    if repo_root is None:
        return 2
    # flag_locations comes in as a JSON string on the CLI (stdin or arg).
    if args.flag_locations_json == "-":
        raw = sys.stdin.read()
    else:
        raw = args.flag_locations_json
    try:
        flag_locations = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError as e:
        print(f"--flag-locations-json must be valid JSON: {e}", file=sys.stderr)
        return 2
    try:
        target = emit_prescriptive_check(
            topic=args.topic,
            tickets_checked=args.tickets_checked,
            flagged_count=args.flagged_count,
            flag_locations=flag_locations,
            repo_root=repo_root,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Failed to append prescriptive_check_run event: {e}",
              file=sys.stderr)
        return 2
    sys.stdout.write(str(target) + "\n")
    return 0


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------

def _add_repo_root_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--repo-root",
        default=None,
        help="Override repo root (default: git rev-parse --show-toplevel).",
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m cortex_command.discovery",
        description=(
            "Atomic CLI helpers for the /cortex-core:discovery skill. "
            "Fuses payload-validation + slug-to-events.log resolution + "
            "JSONL append into single subprocess calls so the orchestrator-LLM "
            "cannot silently drop fields or hardcode the events.log path."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    # resolve-events-log-path
    rp = sub.add_parser(
        "resolve-events-log-path",
        help=(
            "Resolve the events.log target for a topic slug, honoring the "
            "-N re-run suffix (R13) and active-lifecycle env override (EVT-1)."
        ),
    )
    _add_repo_root_arg(rp)
    rp.add_argument("--topic", required=True, help="Discovery topic slug.")
    rp.set_defaults(func=_cmd_resolve_events_log_path)

    # emit-architecture-written
    ea = sub.add_parser(
        "emit-architecture-written",
        help="Validate and emit one architecture_section_written event.",
    )
    _add_repo_root_arg(ea)
    ea.add_argument("--topic", required=True)
    ea.add_argument("--piece-count", required=True, type=int)
    ea.add_argument(
        "--has-why-n-justification",
        required=True,
        choices=("true", "false"),
    )
    ea.add_argument(
        "--status",
        required=True,
        choices=sorted(_STATUS_VALUES),
    )
    ea.add_argument(
        "--re-walk-attempt",
        type=int,
        default=None,
        help="Optional R12 re-walk attempt counter.",
    )
    ea.set_defaults(
        func=lambda a: _cmd_emit_architecture_written(
            _coerce_bool_namespace(a, "has_why_n_justification")
        )
    )

    # emit-checkpoint-response
    ec = sub.add_parser(
        "emit-checkpoint-response",
        help="Validate and emit one approval_checkpoint_responded event.",
    )
    _add_repo_root_arg(ec)
    ec.add_argument("--topic", required=True)
    ec.add_argument(
        "--checkpoint",
        required=True,
        choices=sorted(_CHECKPOINT_VALUES),
    )
    ec.add_argument(
        "--response",
        required=True,
        choices=sorted(_RESPONSE_VALUES),
    )
    ec.add_argument(
        "--revision-round",
        required=True,
        type=int,
        help="Revision-loop counter (0 for the first response).",
    )
    ec.set_defaults(func=_cmd_emit_checkpoint_response)

    # emit-prescriptive-check
    ep = sub.add_parser(
        "emit-prescriptive-check",
        help="Validate and emit one prescriptive_check_run event.",
    )
    _add_repo_root_arg(ep)
    ep.add_argument("--topic", required=True)
    ep.add_argument("--tickets-checked", required=True, type=int)
    ep.add_argument("--flagged-count", required=True, type=int)
    ep.add_argument(
        "--flag-locations-json",
        required=True,
        help=(
            "JSON list of {ticket, section, signal} dicts. Pass '-' to read "
            "JSON from stdin."
        ),
    )
    ep.set_defaults(func=_cmd_emit_prescriptive_check)

    # generate-brief
    gb = sub.add_parser(
        "generate-brief",
        help=(
            "Read a research.md file and dispatch a fresh-context sub-agent "
            "to generate a plain-prose gate brief on stdout. "
            "Emits one gate_brief_generated event."
        ),
    )
    _add_repo_root_arg(gb)
    gb.add_argument(
        "--research-md",
        required=True,
        help="Path to the research.md file to summarise.",
    )
    gb.add_argument(
        "--topic",
        default=None,
        help=(
            "Discovery topic slug for event log resolution. "
            "If omitted, derived from the research.md parent directory name."
        ),
    )
    gb.add_argument(
        "--persist-to",
        default=None,
        dest="persist_to",
        metavar="PATH",
        help=(
            "When set, write the validated brief to this path after stdout "
            "emission (e.g. cortex/research/<topic>/brief.md). "
            "Persistence is skipped on empty output or validation failure; "
            "the subcommand exits non-zero in those cases so the gate caller "
            "can route to the dense-Architecture fallback."
        ),
    )
    gb.set_defaults(func=_cmd_generate_brief)

    # score-corpus
    sc = sub.add_parser(
        "score-corpus",
        help=(
            "Walk a corpus root for brief.md files (or research.md Headline + "
            "Architecture excerpts when no brief.md exists) and score each "
            "against the six reader-study patterns. "
            "Emits one line per file: '<path> patterns_reproducing=N/6 word_count=N'. "
            "Exit code 0 on success; pattern-count failures are a report signal "
            "for operator retro review, not a process-level gate."
        ),
    )
    sc.add_argument(
        "--root",
        required=True,
        metavar="PATH",
        help=(
            "Root directory to scan for topic subdirectories containing "
            "brief.md or research.md (e.g. cortex/research/)."
        ),
    )
    sc.add_argument(
        "--threshold",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Pattern count at or above which a file is flagged with [FLAGGED] "
            "in the report. Default: 1 (any pattern triggers the surface signal). "
            "Operator-tunable; does not affect exit code."
        ),
    )
    sc.set_defaults(func=_cmd_score_corpus)

    return p


def _coerce_bool_namespace(args: argparse.Namespace, name: str) -> argparse.Namespace:
    """Coerce a "true"/"false" argparse string into a real Python bool."""
    raw = getattr(args, name)
    setattr(args, name, raw == "true")
    return args


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
