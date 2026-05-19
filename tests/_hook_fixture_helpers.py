"""Fixture-staging helpers for the cortex-scan-lifecycle hook test suite.

Provides a small toolkit for staging a temporary repo with arbitrary
lifecycle state (incomplete features, pipeline-state JSON, Morning Review
fixtures, session-id files, etc.), then running the SessionStart hook
against it and capturing the emitted ``hookSpecificOutput.additionalContext``
substring.

The same staging primitives are reused across:
  - golden-file fixtures captured from the legacy bash hook (Task 1)
  - the Python subcommand's golden replay (Task 14)
  - mutation-path tests against the Python port (Task 15)
  - wrapper-shape tests (Task 16)
  - concurrency tests (Task 17)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
BASH_HOOK = REPO_ROOT / "hooks" / "cortex-scan-lifecycle.sh"
DEV_VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python3"


@dataclass
class FeatureSpec:
    """Declarative spec for a single lifecycle feature directory.

    Each field maps to a file that determines the phase detected by
    :func:`cortex_command.common.detect_lifecycle_phase`. Setting a
    field to ``None`` (the default) omits the file; set to a string to
    write that string as the file's contents.
    """

    name: str
    research_md: str | None = None
    spec_md: str | None = None
    plan_md: str | None = None
    review_md: str | None = None
    events_log: str | None = None
    session: str | None = None
    session_owner: str | None = None
    extra_files: dict[str, str] = field(default_factory=dict)


@dataclass
class StageSpec:
    """Top-level declarative spec for a staged lifecycle test repo."""

    features: list[FeatureSpec] = field(default_factory=list)
    pipeline_state: dict[str, Any] | None = None
    metrics_json: dict[str, Any] | None = None
    create_lifecycle_dir: bool = True


def stage_lifecycle(tmp_path: Path, spec: StageSpec) -> Path:
    """Materialize a StageSpec under ``tmp_path`` and return the repo root.

    The returned path is the value to feed as ``cwd`` in the hook input
    JSON. Layout::

        <tmp_path>/repo/
          cortex/lifecycle/
            overnight-state.json     (if pipeline_state set)
            metrics.json             (if metrics_json set)
            <feature>/               (one per FeatureSpec)
              research.md / spec.md / plan.md / review.md / events.log
              .session / .session-owner
              <any extra files>
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    if not spec.create_lifecycle_dir:
        return repo
    lifecycle = repo / "cortex" / "lifecycle"
    lifecycle.mkdir(parents=True, exist_ok=True)

    if spec.pipeline_state is not None:
        (lifecycle / "overnight-state.json").write_text(
            json.dumps(spec.pipeline_state, indent=2),
            encoding="utf-8",
        )
    if spec.metrics_json is not None:
        (lifecycle / "metrics.json").write_text(
            json.dumps(spec.metrics_json, indent=2),
            encoding="utf-8",
        )

    for feat in spec.features:
        fdir = lifecycle / feat.name
        fdir.mkdir(parents=True, exist_ok=True)
        for filename, content in (
            ("research.md", feat.research_md),
            ("spec.md", feat.spec_md),
            ("plan.md", feat.plan_md),
            ("review.md", feat.review_md),
            ("events.log", feat.events_log),
            (".session", feat.session),
            (".session-owner", feat.session_owner),
        ):
            if content is not None:
                (fdir / filename).write_text(content, encoding="utf-8")
        for rel, content in feat.extra_files.items():
            target = fdir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    return repo


def run_bash_hook(
    repo: Path,
    session_id: str,
    *,
    lifecycle_session_id: str | None = None,
    extra_env: dict[str, str] | None = None,
    python_for_hook: Path = DEV_VENV_PYTHON,
) -> subprocess.CompletedProcess:
    """Run the legacy bash hook against a staged repo and capture output.

    The bash hook resolves ``python3`` from ``PATH``. To make bare
    ``python3 -c "import cortex_command"`` succeed (the working install
    topology described in Task 1), we prepend the dev-venv's bin
    directory to ``PATH`` for the subprocess.
    """
    env = os.environ.copy()
    venv_bin = str(python_for_hook.parent)
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    # CLAUDE_ENV_FILE is consumed by the hook to inject env exports; route
    # it to a tmp file under the repo so we don't pollute the user's env.
    claude_env = repo / ".claude-env"
    claude_env.write_text("", encoding="utf-8")
    env["CLAUDE_ENV_FILE"] = str(claude_env)
    if lifecycle_session_id is not None:
        env["LIFECYCLE_SESSION_ID"] = lifecycle_session_id
    else:
        env.pop("LIFECYCLE_SESSION_ID", None)
    if extra_env:
        env.update(extra_env)

    payload = {
        "hook_event_name": "SessionStart",
        "session_id": session_id,
        "cwd": str(repo),
    }
    return subprocess.run(
        ["bash", str(BASH_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def extract_additional_context(stdout: str) -> str:
    """Parse the hook's JSON stdout and return ``hookSpecificOutput.additionalContext``.

    Returns an empty string if stdout is empty (hook chose to emit nothing).
    Raises ``ValueError`` if stdout is non-empty but does not parse as the
    expected envelope shape — surfaces malformed captures early.
    """
    text = stdout.strip()
    if not text:
        return ""
    try:
        envelope = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"hook stdout is not valid JSON: {text!r}") from exc
    hso = envelope.get("hookSpecificOutput")
    if not isinstance(hso, dict):
        raise ValueError(
            f"hook stdout missing hookSpecificOutput dict: {envelope!r}"
        )
    ctx = hso.get("additionalContext", "")
    if not isinstance(ctx, str):
        raise ValueError(
            f"hookSpecificOutput.additionalContext is not a string: {ctx!r}"
        )
    return ctx


def fixture_dir() -> Path:
    """Directory holding the golden fixture pairs."""
    return REPO_ROOT / "tests" / "fixtures" / "hooks" / "scan_lifecycle"


def fixture_input_path(case: str) -> Path:
    return fixture_dir() / f"{case}.in.json"


def fixture_expected_path(case: str) -> Path:
    return fixture_dir() / f"{case}.expected.additionalContext.txt"
