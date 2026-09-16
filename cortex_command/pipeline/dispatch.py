"""Claude CLI dispatch wrapper for pipeline task execution.

Spawns the operator's ``claude`` through :mod:`cortex_command.claude_stream`
(``-p --output-format stream-json``, prompt on stdin) to provide effort/budget
tier selection based on task complexity, progress streaming via state event
logging, and structured error classification for the retry module.

Model selection is deliberately absent: dispatches pass no ``--model`` and
run on the CLI default. The model each dispatch actually used is read back off
the ``assistant`` frames and reported on ``dispatch_complete`` for cost
aggregation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, get_args

from cortex_command import cli_resolver
from cortex_command.claude_stream import ClaudeSpawnError, build_argv, build_env, run_claude
from cortex_command.cli_resolver import resolve_claude_cli
from cortex_command.pipeline.state import log_event

# Lazy imports of cortex_command.overnight.sandbox_settings + state (Req 5)
# inside dispatch_task to avoid the circular-import cycle:
# cortex_command.overnight.__init__ → orchestrator → feature_executor →
# cortex_command.pipeline.conflict → cortex_command.pipeline.dispatch.
# Top-level import of the overnight package would resolve the parent
# __init__ before dispatch.py finishes loading.

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_input_summary(tool_name: str, input_dict: dict[str, Any]) -> str:
    """Return the first 80 characters of the primary input field for a tool call.

    Args:
        tool_name: Name of the tool being called (e.g. "Bash", "Read").
        input_dict: The tool's input parameters.

    Returns:
        A string of at most 80 characters representing the primary input.
    """
    if tool_name in ("Read", "Write", "Edit"):
        value = input_dict.get("file_path", "")
    elif tool_name == "Bash":
        value = input_dict.get("command", "")
    elif tool_name in ("Glob", "Grep"):
        value = input_dict.get("pattern", "")
    else:
        value = next(iter(input_dict.values()), "") if input_dict else ""
    return str(value)[:80]


def _deep_merge(base: dict, overlay: dict) -> None:
    """Recursively merge overlay into base in-place.

    For dict values, recurse.  For all other values, overlay wins.

    Args:
        base: The dict to merge into (mutated in-place).
        overlay: The dict whose values take precedence.
    """
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _load_project_settings(repo_root: Path) -> dict:
    """Load and merge .claude/settings.json and .claude/settings.local.json.

    Iterates the two filenames in order; for each: skips silently if missing;
    parses JSON and deep-merges into the accumulator; on JSONDecodeError prints
    to stderr and skips.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Accumulated settings dict (may be empty if no files found).
    """
    import sys

    result: dict = {}
    for filename in ("settings.json", "settings.local.json"):
        path = repo_root / ".claude" / filename
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"dispatch: failed to parse {path}: {e}", file=sys.stderr)
            continue
        _deep_merge(result, data)
    return result


# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------

# ``max_budget_usd`` is the real cost guard: it is enforced by the CLI, and
# tripping it surfaces as ``budget_exhausted`` whose recovery pauses the whole
# session. ``max_turns`` is only a runaway-loop backstop, so it belongs an order
# of magnitude above real work rather than inside it.
#
# The previous ceilings (15/20/30) sat squarely in the working range and bound
# routinely. Measured across every session on disk at the time of this change —
# 32 dispatches with a recorded turn count — successful runs spanned 7 to 30
# turns (median 14), i.e. the busiest healthy dispatch landed exactly on the
# ``complex`` ceiling. The two that hit the limit were not runaways: an
# implement dispatch stopped at 21 of 20 and a review at 31 of 30, and the
# review's kill reverted an already-merged feature (session
# overnight-2026-07-28-1216, #414). A backstop that fires on ordinary work is
# not a backstop.
#
# Cost stays bounded because the budget cap still binds first: at the worst
# observed cost-per-turn ($0.585), even the smallest new ceiling would imply
# ~$88 against a $5 simple cap, so an agent burning money is stopped by
# ``max_budget_usd`` long before it exhausts turns. What the turn ceiling now
# catches is the cheap pathological loop — an agent cycling on near-free calls
# that the budget guard would never notice.
TIER_CONFIG: dict[str, dict] = {
    "simple": {"max_turns": 150, "max_budget_usd": 5.00},
    "moderate": {"max_turns": 200, "max_budget_usd": 25.00},
    "complex": {"max_turns": 300, "max_budget_usd": 50.00},
}

# NOTE: cortex no longer selects a model for dispatched agents. No `--model` is
# passed, so the dispatched agent runs on the CLI's own default, and the model it
# actually ran on is read back off the `assistant` frames and recorded on
# `dispatch_complete` for the cost aggregators and dashboard.
# Selection was previously a (complexity, criticality) matrix plus a
# haiku -> sonnet -> opus retry ladder; both were removed deliberately.

# 2D effort matrix: (complexity, criticality) -> effort level passed as `--effort`.
# Cell values were set for earlier models (spec: lifecycle/adopt-xhigh-effort-
# default-for-overnight-lifecycle-implement) and have not been re-swept on the
# current CLI default, where the vendor guidance is to start at "high" and sweep
# down — "low"/"medium" are the primary cost lever and "xhigh"/"max" are for
# measured wins. Re-sweep against metrics.json's per-effort cost buckets before
# changing any cell.
#
# Effort is now resolved without reference to a model, because cortex no longer
# picks one. An effort the running model does not accept is handled at the CLI
# boundary, loudly, by the existing clamp/`dispatch_effort_ignored` path — see
# the `effort_override` docstring on dispatch_task.
_EFFORT_MATRIX: dict[tuple[str, str], str] = {
    ("simple",   "low"):      "low",
    ("simple",   "medium"):   "low",
    ("simple",   "high"):     "high",
    ("simple",   "critical"): "high",
    ("moderate", "low"):      "high",
    ("moderate", "medium"):   "high",
    ("moderate", "high"):     "high",
    ("moderate", "critical"): "high",
    ("complex",  "low"):      "high",
    ("complex",  "medium"):   "high",
    ("complex",  "high"):     "xhigh",
    ("complex",  "critical"): "xhigh",
}

# Skill-based effort overrides applied AFTER matrix lookup. Per spec §2
# Technical Constraints: review-fix and integration-recovery warrant the highest
# reasoning ceiling. Formerly gated on resolved model == "opus"; the gate went
# with model selection, so these now apply unconditionally. Kept as a small flat
# dict (not a 3D matrix) per spec Non-Requirements; promote only if a third
# skill-specific exception lands.
_SKILL_EFFORT_OVERRIDES: dict[str, str] = {
    "review-fix":           "max",
    "integration-recovery": "max",
}

_VALID_CRITICALITY = {"low", "medium", "high", "critical"}

# Closed vocabulary of dispatch-call sites, emitted on dispatch_start so
# downstream aggregators can group by skill (Req: per-skill pipeline aggregates).
# Add new skills here only after wiring the corresponding caller; runtime guard
# in dispatch_task rejects values not in this set.
Skill = Literal[
    "implement",
    "review",
    "review-fix",
    "conflict-repair",
    "merge-test-repair",
    "integration-recovery",
    "brain",
    "orchestrator-round",  # documentation-only: never passed to dispatch_task; runner.py emits via pipeline.state.log_event
]

def resolve_effort(complexity: str, criticality: str, skill: str) -> str:
    """Resolve an effort level from the centralized matrix + skill override.

    Looks up ``_EFFORT_MATRIX[(complexity, criticality)]`` for the baseline,
    then applies the skill override: ``review-fix`` and ``integration-recovery``
    get bumped to ``"max"`` (per spec §2). Effort is a behavioral signal capping
    the model's *maximum* reasoning depth — see Anthropic's effort docs and spec
    §1 for the adaptive-thinking framing.

    Args:
        complexity: Complexity tier key ("simple", "moderate", or "complex").
        criticality: Criticality level ("low", "medium", "high", or "critical").
        skill: The dispatching skill name (e.g. "implement", "review-fix").
            Selects the skill override; unknown skills receive the matrix value.

    Returns:
        An effort level string from the closed vocabulary
        ``{"low", "medium", "high", "xhigh", "max"}``.

    Raises:
        ValueError: If complexity or criticality is not a recognized value.

    Note:
        This used to take the resolved model and fail loudly when the cell
        requested an effort that model could not accept (e.g. ``xhigh`` on
        Sonnet). cortex no longer chooses the model, so that guard cannot be
        evaluated here; an unacceptable ``--effort`` is instead caught at the
        CLI boundary and surfaced loudly (clamp to ``max`` on a hard reject, a
        ``dispatch_effort_ignored`` note on a warn-ignore).
    """
    if complexity not in TIER_CONFIG:
        raise ValueError(
            f"Unknown complexity tier {complexity!r}; "
            f"must be one of {sorted(TIER_CONFIG)}"
        )
    if criticality not in _VALID_CRITICALITY:
        raise ValueError(
            f"Unknown criticality {criticality!r}; "
            f"must be one of {sorted(_VALID_CRITICALITY)}"
        )
    if skill in _SKILL_EFFORT_OVERRIDES:
        return _SKILL_EFFORT_OVERRIDES[skill]
    return _EFFORT_MATRIX[(complexity, criticality)]


# Tools available to all dispatched agents
_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DispatchDiagnostics:
    """Captured failure diagnostics from a dispatched agent task.

    Threaded through the result carriers to the brain and onto the
    task_output event the morning report reads. Populated on every failure
    path; None on success.

    Attributes:
        child_stderr: Redacted/capped child stderr, else None.
        exit_code: Process exit code if available, else None.
        cwd: Working directory the agent ran in, else None.
    """

    child_stderr: Optional[str] = None
    exit_code: Optional[int] = None
    cwd: Optional[str] = None


@dataclass
class DispatchResult:
    """Structured result from a dispatched agent task.

    Attributes:
        success: Whether the task completed without error.
        output: Collected text output from the agent.
        error_type: Classification string if the task failed, else None.
            One of: agent_timeout, agent_test_failure, agent_refusal,
            agent_confused, task_failure, infrastructure_failure,
            budget_exhausted, api_rate_limit, api_unavailable,
            effort_unsupported, turn_limit_exhausted, unknown.
        error_detail: Human-readable error detail string, else None.
        cost_usd: Total cost reported by the CLI's result frame, else None.
        diagnostics: Captured failure diagnostics, populated on every
            failure path, else None.
    """

    success: bool
    output: str
    error_type: Optional[str] = None
    error_detail: Optional[str] = None
    cost_usd: Optional[float] = None
    diagnostics: Optional["DispatchDiagnostics"] = None


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

# Recovery path for each error type.  Consumed by retry logic and morning report.
ERROR_RECOVERY: dict[str, str] = {
    "agent_timeout":          "retry",
    # Formerly "escalate": these climbed a haiku -> sonnet -> opus ladder before
    # pausing. cortex no longer selects models, so there is no tier to climb;
    # both now retry with accumulated learnings and pause when attempts run out.
    "agent_test_failure":     "retry",
    "agent_refusal":          "pause_human",
    "agent_confused":         "retry",
    "task_failure":           "retry",
    "infrastructure_failure": "pause_human",
    "budget_exhausted":       "pause_session",
    "api_rate_limit":         "pause_session",
    # An API-wide fault (auth failure, provider error) fails every feature the
    # same way, so the session halts once with the cause named rather than
    # retrying each feature against a dead API.
    "api_unavailable":        "pause_session",
    # #313 R4: a CLI `--effort` hard-rejection is a permanently-invalid flag.
    # Its recovery clamps effort once to `max` (universally accepted) instead of
    # blind-retrying the rejected value; see retry.py's clamp_effort arm.
    "effort_unsupported":     "clamp_effort",
    # The agent ran out of turns mid-tool-use. Retry is right: the work so far
    # is intact and a fresh attempt carries accumulated learnings. Critically,
    # this must NOT be classified "unknown" — the review gate reads an
    # unclassified dispatch failure as a could-not-run ERROR and reverts an
    # already-merged feature (observed: session overnight-2026-07-28-1216 lost
    # #414's merge to a review that stopped at turn 31 of 30).
    "turn_limit_exhausted":   "retry",
    "unknown":                "retry",
}

# Keyword patterns used for content-based subtype detection.
# Checked against lowercased combined text of (assistant text + captured stderr).
_TIMEOUT_PATTERNS = ("timeout", "timed out", "time out")
_TEST_FAILURE_PATTERNS = (
    "test failed", "tests failed", "test failure", "assertion error",
    "assertionerror", "pytest", "failing tests", "failing test",
)
_REFUSAL_PATTERNS = (
    "i cannot", "i can't", "i'm unable", "i am unable",
    "i'm not able", "i am not able", "cannot help", "not able to help",
    "i must refuse", "i will not", "i won't",
)
_CONFUSED_PATTERNS = (
    "i'm not sure", "i am not sure", "i don't understand", "i do not understand",
    "unclear to me", "i'm confused", "i am confused", "don't know how to",
    "do not know how to", "i'm lost", "i am lost",
)
_RATE_LIMIT_PATTERNS = ("rate_limit_error", "rate limit", "too many requests")
_MAX_STDERR_LINES = 100
# Secondary byte cap on a single captured stderr line. The line cap alone lets a
# single pathological multi-megabyte line through into every downstream sink
# (event log, brain prompt, committed report). Bound the post-redaction line by
# total bytes too, truncating tail-anchored so the most-recent (and usually
# most-diagnostic) bytes survive. 64 KiB comfortably holds a real traceback while
# capping a runaway line.
_MAX_STDERR_BYTES = 65536

# ---------------------------------------------------------------------------
# Stderr secret redaction (cue-anchored, value-level — see #309 spec R1)
#
# Each pattern is anchored on a distinguishing prefix or keyword so it cannot
# match arbitrary high-entropy diagnostic text (git SHAs, UUIDs, content
# hashes, base64 fixtures) — the content this feature exists to preserve.
# There is deliberately NO prefixless fixed-length blob matcher: such a rule
# is regex-indistinguishable from those benign blobs and would defeat the
# feature's purpose.
#
# This enumerated allowlist is defense-in-depth, NOT complete: other stably
# cued families (Google `AIza`, GitLab `glpat-`) and all prefixless secrets
# are out of scope and may still reach a downstream sink.
# ---------------------------------------------------------------------------

# Secret-shape floor for keyword-delimiter values: a length floor (≥16 chars)
# over a secret-ish charset, so short benign tokens (parser `RPAREN`, `EOF`,
# `changeme`) and spaced English (`Bearer of bad news`) fall through.
_SECRET_VALUE = r"[A-Za-z0-9_\-./+=]{16,}"

# (i) Prefix-cued shapes — unambiguous distinguishing prefix, near-zero
#     over-redaction risk.
# (ii) Keyword-delimiter shapes — keyword ALSO appears in benign stderr, so
#      the match is constrained to secret-shaped values (a quoted value OR an
#      unquoted run clearing the secret-shape floor).
_REDACTION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # --- Prefix-cued shapes (i) ---
    # Anthropic API keys (kept from the original sk-ant- rule).
    (re.compile(r"sk-ant-[a-zA-Z0-9_-]+"), "sk-ant-<redacted>"),
    # GitHub personal-access / OAuth / server / refresh tokens.
    (re.compile(r"gh[porsu]_[A-Za-z0-9]+"), "<redacted-github-token>"),
    # Slack bot / user tokens.
    (re.compile(r"xox[bp]-[A-Za-z0-9-]+"), "<redacted-slack-token>"),
    # AWS access key IDs: AKIA/ASIA + 16-char tail.
    (re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"), "<redacted-aws-key>"),
    # URL userinfo: scheme://user:pass@host -> keep user, redact password.
    (
        re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s:/@]+:)[^\s@/]+@"),
        r"\g<scheme><redacted>@",
    ),
    # --- Keyword-delimiter shapes (ii), constrained to secret-shaped values ---
    # Bearer <token> — only a secret-shaped value (not spaced English).
    (
        re.compile(r"(?P<cue>Bearer\s+)" + _SECRET_VALUE),
        r"\g<cue><redacted>",
    ),
    # password=/token= delimiters. The value must clear the secret-shape floor
    # (≥16 secret-charset chars), quoted or unquoted, so short benign tokens
    # (`token='EOF'`, `password=changeme`) fall through unredacted.
    (
        re.compile(
            r"(?P<key>\b(?:password|token)\s*=\s*)"
            r"(?P<q>[\"'])(?P<val>" + _SECRET_VALUE + r")(?P=q)"
        ),
        r"\g<key>\g<q><redacted>\g<q>",
    ),
    (
        re.compile(r"(?P<key>\b(?:password|token)\s*=\s*)" + _SECRET_VALUE),
        r"\g<key><redacted>",
    ),
)

# Multi-line-secret cue: a per-line value regex cannot span a PEM block, so on
# a cued line mask conservatively at line level. (Residual gap — a token split
# across stream-buffer flushes — is an accepted defense-in-depth limit.)
_PEM_CUE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")


def _redact(line: str) -> str:
    """Scrub cue-anchored credential shapes from a single stderr line.

    Defense-in-depth: an enumerated allowlist of distinguishing prefixes and
    secret-shaped keyword-delimiter values, never a prefixless blob matcher.
    Benign high-entropy diagnostics (git SHAs, UUIDs, base64 fixtures) survive.
    """
    if _PEM_CUE.search(line):
        return "<redacted-private-key-block>"
    for pattern, replacement in _REDACTION_RULES:
        line = pattern.sub(replacement, line)
    return line


def _is_turn_limit_stop(
    stop_reason: str | None,
    num_turns: int | None,
    max_turns: int | None,
) -> bool:
    """Return True when a dispatch died because it ran out of turns.

    The CLI exits 1 when it hits ``--max-turns`` while the model still wants
    to call a tool, with no child stderr, so the exit code alone is
    indistinguishable from a real crash. The reliable signature is the last
    ``result`` frame:
    ``stop_reason == "tool_use"`` with ``num_turns`` at or past the configured
    ceiling — the CLI reports the turn that could not complete, so ``num_turns``
    is typically ``max_turns + 1``.
    """
    if stop_reason != "tool_use":
        return False
    if num_turns is None or max_turns is None:
        return False
    return num_turns >= max_turns


def _as_int(value: Any) -> Optional[int]:
    """Return ``value`` as an int, or None when it is absent or not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def classify_failure(
    exit_code: Optional[int],
    result: Optional[dict[str, Any]],
    rate_limit: Optional[dict[str, Any]],
    corpus: str,
    max_turns: Optional[int],
) -> Optional[str]:
    """Classify a finished ``claude`` run into a dispatch error type.

    Pure function over what the run left behind. Checks, in order:

    1. Success — ``exit_code == 0`` with a result frame whose ``is_error`` is
       falsy — returns None.
    2. ``subtype == "error_max_budget_usd"`` → ``budget_exhausted``.
    3. Turn-limit signature (:func:`_is_turn_limit_stop`) or
       ``subtype == "error_max_turns"`` → ``turn_limit_exhausted``.
    4. ``api_error_status == 429`` or a rate-limit frame whose status is not
       ``allowed*`` → ``api_rate_limit``.
    5. ``terminal_reason == "api_error"`` or ``api_error_status`` of 401, 403
       or >= 500 → ``api_unavailable``.
    6. Keyword scans → ``agent_timeout`` / ``agent_test_failure`` /
       ``agent_refusal`` / ``agent_confused``, then a rate-limit phrase →
       ``api_rate_limit``; the ``--effort`` hard-reject signature →
       ``effort_unsupported``. The phrase scan runs after the other keywords
       because an assistant merely mentioning "rate limit" must not halt the
       whole session.
    7. Otherwise ``task_failure`` — including a non-zero exit with no result
       frame.

    Args:
        exit_code: The child's exit code (None if it never reported one).
        result: The last ``result`` frame, or None if none arrived.
        rate_limit: The last ``rate_limit_event`` frame, or None.
        corpus: Assistant text plus captured stderr. Only assistant text and
            stderr belong here — system, hook and rate-limit frame text must
            not, or their incidental words trip the keyword scans.
        max_turns: The dispatch's configured turn ceiling.

    Returns:
        None on success, else an ``ERROR_RECOVERY`` key.
    """
    result = result if isinstance(result, dict) else None

    if exit_code == 0 and result is not None and not result.get("is_error"):
        return None

    subtype = result.get("subtype") if result is not None else None
    stop_reason = result.get("stop_reason") if result is not None else None
    num_turns = _as_int(result.get("num_turns")) if result is not None else None
    api_status = _as_int(result.get("api_error_status")) if result is not None else None
    terminal_reason = result.get("terminal_reason") if result is not None else None

    if subtype == "error_max_budget_usd":
        return "budget_exhausted"

    if _is_turn_limit_stop(stop_reason, num_turns, max_turns) or subtype == "error_max_turns":
        return "turn_limit_exhausted"

    corpus = (corpus or "").lower()

    rate_limit_status: Any = None
    if isinstance(rate_limit, dict):
        info = rate_limit.get("rate_limit_info")
        if isinstance(info, dict):
            rate_limit_status = info.get("status")
        if rate_limit_status is None:
            rate_limit_status = rate_limit.get("status")
    if (
        api_status == 429
        or (isinstance(rate_limit_status, str) and not rate_limit_status.startswith("allowed"))
    ):
        return "api_rate_limit"

    if terminal_reason == "api_error" or (
        api_status is not None and (api_status in (401, 403) or api_status >= 500)
    ):
        return "api_unavailable"

    if any(p in corpus for p in _TIMEOUT_PATTERNS):
        return "agent_timeout"
    if any(p in corpus for p in _TEST_FAILURE_PATTERNS):
        return "agent_test_failure"
    if any(p in corpus for p in _REFUSAL_PATTERNS):
        return "agent_refusal"
    if any(p in corpus for p in _CONFUSED_PATTERNS):
        return "agent_confused"
    if any(p in corpus for p in _RATE_LIMIT_PATTERNS):
        return "api_rate_limit"

    # An `--effort` hard-rejection (old claude, e.g. bundled 2.1.69) is a
    # permanently-invalid flag — NOT a transient failure to blind-retry.
    # Classify distinctly so the retry loop clamps once to `max` (#313 R4)
    # rather than re-sending the rejected value until the budget burns. The
    # rejection text reaches `corpus` through the captured child stderr.
    if "option '--effort" in corpus and "is invalid" in corpus:
        return "effort_unsupported"

    return "task_failure"


# ---------------------------------------------------------------------------
# Activity log helper
# ---------------------------------------------------------------------------

async def _write_activity_event(path: Path, event_dict: dict) -> None:
    """Write an activity event to the given JSONL path in a background thread.

    Swallows all exceptions so that activity logging never interrupts the
    main dispatch loop.
    """
    try:
        await asyncio.to_thread(log_event, path, event_dict)
    except Exception as exc:
        logger.warning("activity log write failed: %s", exc)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

async def dispatch_task(
    feature: str,
    task: str,
    worktree_path: Path,
    complexity: str,
    system_prompt: str,
    log_path: Optional[Path] = None,
    criticality: str = "medium",
    activity_log_path: Optional[Path] = None,
    effort_override: Optional[str] = None,
    integration_base_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    *,
    skill: Skill,
    attempt: int = 1,
    cycle: int | None = None,
) -> DispatchResult:
    """Dispatch a task to a Claude agent by spawning the ``claude`` CLI.

    Selects effort, budget, and turn limits based on the task's complexity
    tier and criticality level. Streams progress events to the event log
    and collects output text from assistant messages.

    Does NOT select a model: no ``--model`` is passed, so the dispatched agent
    runs on the CLI's own default. The model it actually ran on is read back
    off the first ``assistant`` frame and reported on the
    ``dispatch_complete`` event.

    Args:
        feature: Feature name (for logging context).
        task: The prompt/task description to send to the agent.
        worktree_path: Working directory for the agent (git worktree).
        complexity: Complexity tier key ("simple", "moderate", or "complex").
        system_prompt: System prompt to configure the agent's behavior.
        log_path: Optional path to JSONL event log. If provided, progress
            events are appended via state.log_event.
        criticality: Criticality level ("low", "medium", "high", or
            "critical"). Defaults to "medium" for backward compatibility.
        activity_log_path: Optional path to per-agent activity JSONL log.
            If provided, tool use and result events are appended via
            _write_activity_event (non-blocking).
        effort_override: If provided, use this effort level directly instead of
            resolving from the complexity/criticality cell via ``_EFFORT_MATRIX``
            and skill-based overrides.  Accepts any value accepted by the
            CLI's ``--effort`` ("low", "medium", "high", "xhigh", "max"); note
            that ``xhigh`` is supported only by Opus 4.7+/Fable. An unsupported
            ``--effort`` is rejected by the *dispatched CLI binary*, not the
            model (#313): old ``claude`` (<=2.1.69) hard-rejects it (exit != 0),
            while modern ``claude`` (>=2.1.186) warn-ignores it (exit 0, runs at
            the default effort) — neither silently downgrades in the sense of
            quietly choosing a lower level. cortex resolves the best-available
            CLI (cli_resolver) and clamps/surfaces an unsupported effort rather
            than depending on the model to absorb it. Effort is a behavioral
            signal capping the maximum reasoning depth — the model adapts
            thinking down for simpler tasks, so higher effort levels do not
            impose a fixed token cost.
        skill: Closed-vocabulary identifier for the dispatch-call site (one of
            the values in the ``Skill`` Literal). Required keyword-only
            argument; emitted on ``dispatch_start`` so downstream aggregators
            can group dispatches by ``(skill, tier)``. New skills must be
            added to the ``Skill`` Literal at module scope before use.
        attempt: 1-based retry attempt number for this dispatch. Defaults to
            ``1`` for the first attempt.
        cycle: Review cycle number for ``review-fix`` dispatches only.
            Must be ``None`` for every other skill; passing a non-None value
            with any other ``skill`` raises ``ValueError``.

    Returns:
        DispatchResult with success status, collected output, error info,
        and cost.

    Raises:
        ValueError: If complexity or criticality is not a recognized value,
            if ``skill`` is not in the ``Skill`` Literal vocabulary, or if
            ``cycle`` is non-None for any skill other than ``review-fix``.
    """
    tier = TIER_CONFIG[complexity] if complexity in TIER_CONFIG else None
    if tier is None:
        raise ValueError(
            f"Unknown complexity tier {complexity!r}; "
            f"must be one of {sorted(TIER_CONFIG)}"
        )
    # Validated here rather than only inside resolve_effort, so the criticality
    # contract holds on the effort_override path too (it used to be enforced by
    # the now-deleted resolve_model, which ran unconditionally).
    if criticality not in _VALID_CRITICALITY:
        raise ValueError(
            f"Unknown criticality {criticality!r}; "
            f"must be one of {sorted(_VALID_CRITICALITY)}"
        )

    if skill not in get_args(Skill):
        raise ValueError(f"unregistered skill {skill!r}; must be one of {sorted(get_args(Skill))}")
    if cycle is not None and skill != "review-fix":
        raise ValueError(f"cycle is only valid for skill='review-fix'; got skill={skill!r} with cycle={cycle!r}")

    effort = effort_override if effort_override is not None else resolve_effort(complexity, criticality, skill)
    # Populated from the first assistant frame; reported on dispatch_complete.
    observed_model: Optional[str] = None

    # Clear CLAUDECODE so the sub-agent doesn't hit the nested-session guard.
    # This is an overlay: claude_stream.build_env lays it over the parent
    # environment (dropping CLAUDECODE). Forward ANTHROPIC_API_KEY if present so
    # the child uses API-key billing rather than falling back to subscription.
    # TMPDIR is locked into the dispatched-agent env per spec Req 5/Req 10 to
    # prevent the unset-fallback to /tmp/ that would land outside the per-feature
    # allowWrite list.
    _env: dict[str, str] = {
        "CLAUDECODE": "",
        "TMPDIR": os.environ.get("TMPDIR") or tempfile.gettempdir(),
    }
    if _api_key := os.environ.get("ANTHROPIC_API_KEY"):
        _env["ANTHROPIC_API_KEY"] = _api_key
    if _oauth_token := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        _env["CLAUDE_CODE_OAUTH_TOKEN"] = _oauth_token
    # Propagate LIFECYCLE_SESSION_ID into the dispatched subprocess so the
    # tool-failure tracker hook (cortex-tool-failure-tracker.sh) can route
    # its output under lifecycle/sessions/<id>/tool-failures/ instead of
    # /tmp (spec R9 of #164).
    if _lifecycle_session_id := os.environ.get("LIFECYCLE_SESSION_ID"):
        _env["LIFECYCLE_SESSION_ID"] = _lifecycle_session_id
    # Pin CORTEX_REPO_ROOT to this dispatch's worktree (#198) so the
    # bin/cortex-log-invocation shim's fast path skips git rev-parse.
    # Sourced from the worktree_path arg, not os.environ — each dispatch
    # knows its own worktree; the orchestrator's parent shell may carry a
    # stale value pointing at a different project.
    _env["CORTEX_REPO_ROOT"] = str(worktree_path)

    # Build the per-dispatch sandbox-settings JSON via the shared layer module
    # (spec Req 5, REVISED 2026-05-05). The per-feature deny-set is intentionally
    # empty: the allow-list narrowly bounds writes to the worktree + the six
    # OUT_OF_WORKTREE_ALLOW_WRITERS, so a deny-set would be redundant. The JSON
    # is written to a per-dispatch tempfile under <session_dir>/sandbox-settings/
    # and passed to the child as `claude --settings <path>` via build_argv.
    # Imports are deferred here to avoid the import cycle described at
    # module top.
    from cortex_command.overnight.sandbox_settings import (
        build_dispatch_allow_paths,
        build_sandbox_settings_dict,
        write_settings_tempfile,
        register_atexit_cleanup,
        read_soft_fail_env,
        record_soft_fail_event,
    )
    from cortex_command.overnight.state import session_dir as _session_dir

    _allow_paths = build_dispatch_allow_paths(
        worktree_path=Path(worktree_path),
        integration_base_path=Path(integration_base_path) if integration_base_path is not None else None,
    )
    _soft_fail = read_soft_fail_env()
    # Per-feature dispatch deny-set is intentionally [] (see comment above);
    # bind to a local so the sidecar-write below records the same value
    # actually passed to build_sandbox_settings_dict (spec R2 of #164).
    deny_paths: list[str] = []
    # Exclude git from the sandbox so feature-worker commits sign cleanly via
    # the host gpg-agent. Without this, `git commit` (with commit.gpgsign=true)
    # fails because the per-spawn sandbox blocks gpg-agent's unix socket and
    # writes to ~/.gnupg/. Web tools deliberately omitted — implementation-phase
    # workers have a spec/plan and shouldn't be reaching for WebFetch/WebSearch.
    _settings_dict = build_sandbox_settings_dict(
        deny_paths=deny_paths,
        allow_paths=_allow_paths,
        soft_fail=_soft_fail,
        excluded_commands=["git:*"],
    )
    _session_id = os.environ.get("LIFECYCLE_SESSION_ID", "manual")
    _dispatch_session_dir = _session_dir(_session_id)
    _settings_tempfile_path = write_settings_tempfile(_dispatch_session_dir, _settings_dict)
    register_atexit_cleanup(_settings_tempfile_path)
    if _soft_fail:
        record_soft_fail_event(_dispatch_session_dir)

    # Mirror runner.py's per-spawn sandbox-deny-list sidecar (spec R2 of #164):
    # write a JSON record of this dispatch's deny-list under
    # lifecycle/sessions/<id>/sandbox-deny-lists/ so the morning-report
    # sandbox-violation classifier can union deny-paths across all spawns and
    # do membership tests for EPERM classification. Per-feature dispatches run
    # in parallel, so the sidecar key embeds (feature, skill, attempt[, cycle])
    # for uniqueness — files are NEVER overwritten. Atomic via tempfile +
    # os.replace. Pre-write structural guard fails fast on #163 shape drift.
    from datetime import datetime, timezone
    from cortex_command.common import slugify as _slugify
    assert isinstance(deny_paths, list) and all(isinstance(p, str) for p in deny_paths), (
        f"deny_paths must be list[str] (#163 shape contract); got {type(deny_paths).__name__} "
        f"with elements {[type(p).__name__ for p in deny_paths] if isinstance(deny_paths, list) else 'n/a'}"
    )
    _feature_slug = _slugify(feature)
    _spawn_id_parts = [f"feature-{_feature_slug}", skill, f"attempt{attempt}"]
    if cycle is not None:
        _spawn_id_parts.append(f"cycle{cycle}")
    _spawn_id = "-".join(_spawn_id_parts)
    _sidecar_dir = _dispatch_session_dir / "sandbox-deny-lists"
    _sidecar_dir.mkdir(parents=True, exist_ok=True)
    _sidecar_payload = {
        "schema_version": 2,
        "written_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "spawn_kind": "feature_dispatch",
        "spawn_id": _spawn_id,
        "deny_paths": deny_paths,
    }
    _sidecar_final_path = _sidecar_dir / f"{_spawn_id}.json"
    _sidecar_tmp_path = _sidecar_dir / f".{_spawn_id}.json.tmp"
    _sidecar_tmp_path.write_text(json.dumps(_sidecar_payload, indent=2, sort_keys=True))
    os.replace(_sidecar_tmp_path, _sidecar_final_path)

    _stderr_lines: list[str] = []

    def _on_stderr(line: str) -> None:
        line = _redact(line)
        # Secondary byte cap (the line cap is the secondary line-count bound).
        # Measure the post-redaction line so the cap reflects what is actually
        # stored. Truncate tail-anchored — keep the most-recent bytes, which are
        # usually the most diagnostic — at a UTF-8 character boundary so the
        # stored slice is never a partial multibyte sequence.
        encoded = line.encode("utf-8", "surrogatepass")
        if len(encoded) > _MAX_STDERR_BYTES:
            line = encoded[-_MAX_STDERR_BYTES:].decode("utf-8", "ignore")
        if len(_stderr_lines) < _MAX_STDERR_LINES:
            _stderr_lines.append(line)

    # Resolve the operator's own claude (PATH, then known install locations).
    # There is no bundled binary to fall back on: None means no claude was
    # found at all.
    cli = resolve_claude_cli()

    if log_path:
        event_dict: dict[str, Any] = {
            "event": "dispatch_start",
            "feature": feature,
            "skill": skill,
            "attempt": attempt,
        }
        if cycle is not None:
            event_dict["cycle"] = cycle
        event_dict["complexity"] = complexity
        event_dict["criticality"] = criticality
        # No "model" key here by design: it is not known until the agent
        # replies. dispatch_complete carries the observed model instead.
        event_dict["effort"] = effort
        event_dict["max_turns"] = tier["max_turns"]
        event_dict["max_budget_usd"] = tier["max_budget_usd"]
        log_event(log_path, event_dict)

    output_parts: list[str] = []
    cost_usd: float | None = None
    _tool_name_map: dict[str, str] = {}
    _last_result: Optional[dict[str, Any]] = None
    _last_rate_limit: Optional[dict[str, Any]] = None
    # Turn accounting from the last result frame; travels with every
    # dispatch_error because an empty child stderr (the CLI's usual case on a
    # turn-limit exit) leaves these as the only evidence of why it exited.
    _last_stop_reason: str | None = None
    _last_num_turns: int | None = None
    _exit_code: Optional[int] = None

    def _fail(error_type: str, error_detail: str) -> DispatchResult:
        """Log dispatch_error and return a failed result carrying diagnostics."""
        child_stderr = "\n".join(_stderr_lines)
        if log_path:
            log_event(log_path, {
                "event": "dispatch_error",
                "feature": feature,
                "error_type": error_type,
                "error_detail": error_detail,
                "child_stderr": child_stderr,
                "exit_code": _exit_code,
                "cwd": str(worktree_path),
                "num_turns": _last_num_turns,
                "max_turns": tier["max_turns"],
                "stop_reason": _last_stop_reason,
            })
        return DispatchResult(
            success=False,
            output="\n".join(output_parts),
            error_type=error_type,
            error_detail=error_detail,
            cost_usd=cost_usd,
            diagnostics=DispatchDiagnostics(
                child_stderr=child_stderr,
                exit_code=_exit_code,
                cwd=str(worktree_path),
            ),
        )

    if cli is None:
        searched = ", ".join(["PATH", *cli_resolver._SYSTEM_FALLBACKS])
        return _fail(
            "infrastructure_failure",
            f"claude CLI not found (searched {searched}); install Claude Code "
            "so `claude` is available to cortex",
        )

    argv = build_argv(
        cli,
        max_turns=tier["max_turns"],
        max_budget_usd=tier["max_budget_usd"],
        permission_mode="bypassPermissions",
        allowed_tools=_ALLOWED_TOOLS,
        system_prompt=system_prompt,
        settings=str(_settings_tempfile_path),
        effort=effort,
    )

    try:
        async with run_claude(
            argv,
            prompt=task,
            cwd=str(worktree_path),
            env=build_env(_env),
            on_stderr=_on_stderr,
        ) as run:
            async for frame in run.frames():
                frame_type = frame.get("type")

                if frame_type == "assistant":
                    message = frame.get("message")
                    if not isinstance(message, dict):
                        message = {}
                    content = message.get("content")
                    blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []

                    # Record what the CLI actually ran on. First non-empty value
                    # wins; the CLI reports it per assistant frame and it does
                    # not change mid-dispatch. Emitted as a one-shot event so the
                    # dashboard can show the model *while* the dispatch runs —
                    # dispatch_start cannot carry it, since nothing has replied yet.
                    if observed_model is None:
                        _model = message.get("model")
                        observed_model = _model if isinstance(_model, str) and _model else None
                        if observed_model and log_path:
                            log_event(log_path, {
                                "event": "dispatch_model_observed",
                                "feature": feature,
                                "skill": skill,
                                "attempt": attempt,
                                "model": observed_model,
                            })

                    texts = [
                        b.get("text") for b in blocks
                        if b.get("type") == "text" and isinstance(b.get("text"), str)
                    ]
                    output_parts.extend(texts)

                    if log_path:
                        progress_event: dict = {
                            "event": "dispatch_progress",
                            "feature": feature,
                            "message_type": "assistant",
                        }
                        first_text = texts[0] if texts else None
                        if first_text:
                            progress_event["content_preview"] = first_text[:200]
                        log_event(log_path, progress_event)

                    if activity_log_path is not None:
                        for block in blocks:
                            if block.get("type") != "tool_use":
                                continue
                            tool_name = str(block.get("name") or "")
                            tool_input = block.get("input")
                            if block.get("id") is not None:
                                _tool_name_map[block.get("id")] = tool_name
                            await _write_activity_event(activity_log_path, {
                                "event": "tool_call",
                                "tool": tool_name,
                                "input_summary": _extract_input_summary(
                                    tool_name,
                                    tool_input if isinstance(tool_input, dict) else {},
                                ),
                            })

                elif frame_type == "user":
                    if activity_log_path is not None:
                        message = frame.get("message")
                        content = message.get("content") if isinstance(message, dict) else None
                        if isinstance(content, list):
                            for block in content:
                                if not isinstance(block, dict) or block.get("type") != "tool_result":
                                    continue
                                await _write_activity_event(activity_log_path, {
                                    "event": "tool_result",
                                    "tool": _tool_name_map.get(block.get("tool_use_id"), ""),
                                    "success": not (block.get("is_error") or False),
                                })

                elif frame_type == "result":
                    # Keep the LAST result frame: frames can follow it, and the
                    # run ends at process exit, not here.
                    _last_result = frame

                elif frame_type == "rate_limit_event":
                    # Structured fields only — its text never enters the corpus.
                    _last_rate_limit = frame

                # Every other frame type (system, hooks, summaries) is ignored.

            _exit_code = run.exit_code

        if _last_result is not None:
            cost_usd = _last_result.get("total_cost_usd")
            _last_stop_reason = _last_result.get("stop_reason")
            _last_num_turns = _last_result.get("num_turns")

            if log_path:
                # Truncation allow-list is intentionally a LOCAL set literal
                # (per spec Edge Cases) so future stop_reason values pass
                # through to dispatch_complete unchanged but do not generate
                # spurious truncation events.
                _truncation_reasons = {
                    "max_tokens",
                    "model_context_window_exceeded",
                }
                if _last_stop_reason in _truncation_reasons:
                    log_event(log_path, {
                        "event": "dispatch_truncation",
                        "feature": feature,
                        "stop_reason": _last_stop_reason,
                        "model": observed_model,
                        "effort": effort,
                    })
                log_event(log_path, {
                    "event": "dispatch_complete",
                    "feature": feature,
                    "cost_usd": cost_usd,
                    "duration_ms": _last_result.get("duration_ms"),
                    "num_turns": _last_num_turns,
                    "stop_reason": _last_stop_reason,
                    # The model the CLI actually ran on (cortex no longer
                    # picks it). None if no assistant frame arrived.
                    "model": observed_model,
                })

            if activity_log_path is not None:
                await _write_activity_event(activity_log_path, {
                    "event": "turn_complete",
                    "turn": _last_num_turns,
                    "cost_usd": cost_usd,
                })

        corpus = "\n".join(output_parts)
        if _stderr_lines:
            corpus += "\n" + "\n".join(_stderr_lines)
        error_type = classify_failure(
            _exit_code, _last_result, _last_rate_limit, corpus.lower(), tier["max_turns"],
        )

        if error_type is not None:
            if _last_result is not None:
                subtype = _last_result.get("subtype")
                if _last_result.get("is_error"):
                    output_parts.append(f"[{error_type}: subtype={subtype}]")
                error_detail = (
                    f"claude exited {_exit_code}; result is_error={_last_result.get('is_error')} "
                    f"subtype={subtype} terminal_reason={_last_result.get('terminal_reason')} "
                    f"api_error_status={_last_result.get('api_error_status')} "
                    f"stop_reason={_last_stop_reason} num_turns={_last_num_turns}"
                )
                _errors = _last_result.get("errors")
                if _errors:
                    error_detail += f" errors={str(_errors)[:500]}"
            else:
                error_detail = f"claude exited {_exit_code} with no result frame"
            return _fail(error_type, error_detail)

        # #313 R5: a modern claude (>=2.1.186) warn-IGNORES an unsupported
        # --effort (exit 0, runs at default) instead of hard-rejecting. The
        # dispatch SUCCEEDED, so it must NOT be failed — but the feature ran
        # degraded, which the no-silent-degradation contract requires
        # surfacing. Detect the warn-ignore signal in captured stderr and record
        # a loud note (the morning report renders dispatch_effort_ignored).
        if log_path:
            for _stderr_line in _stderr_lines:
                _lowered = _stderr_line.lower()
                if "unknown --effort value" in _lowered and "ignoring" in _lowered:
                    log_event(log_path, {
                        "event": "dispatch_effort_ignored",
                        "feature": feature,
                        "model": observed_model,
                        "effort": effort,
                        "stderr_line": _stderr_line,
                    })
                    break

        return DispatchResult(
            success=True,
            output="\n".join(output_parts),
            cost_usd=cost_usd,
        )

    except ClaudeSpawnError as exc:
        return _fail(
            "infrastructure_failure",
            f"could not start claude at {exc.cli_path!r}: {exc.error}; install "
            "Claude Code or fix that binary so cortex can run it",
        )

    except Exception as exc:
        error_detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        return _fail("unknown", error_detail)
