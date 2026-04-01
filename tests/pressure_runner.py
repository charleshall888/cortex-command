#!/usr/bin/env python3
"""Pressure scenario runner for skill rule compliance testing.

Reads YAML scenario files from tests/scenarios/<skill>/, dispatches each to a
fresh subagent via `claude -p`, evaluates the response against pass/fail signal
patterns, and reports PASS/FAIL/UNCERTAIN per scenario.

Usage:
    python3 tests/pressure_runner.py <skill>

Exit 0 if all scenarios pass, 1 if any fail or are UNCERTAIN.
"""

import json
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Repository root resolution (same pattern as tests/test_lifecycle_state.py)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
SCENARIOS_DIR = REPO_ROOT / "tests" / "scenarios"


# ---------------------------------------------------------------------------
# Minimal YAML parser (same pattern as backlog/close-item.py)
# ---------------------------------------------------------------------------

def _parse_scalar_value(text: str, key: str) -> str | None:
    """Return the value for a simple `key: value` pair (single-line scalar)."""
    for line in text.splitlines():
        m = re.match(rf"^{re.escape(key)}:\s*[\"']?(.+?)[\"']?\s*$", line)
        if m:
            return m.group(1)
    return None


def _parse_int_value(text: str, key: str, default: int = 1) -> int:
    """Return an integer value for `key: N`, or default if not found."""
    val = _parse_scalar_value(text, key)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return default


def _parse_list_value(text: str, key: str) -> list[str]:
    """Return items from a YAML list under `key:`.

    Handles the pattern:
        key:
          - item one
          - item two
    """
    lines = text.splitlines()
    result = []
    in_list = False
    for line in lines:
        if re.match(rf"^{re.escape(key)}:\s*$", line):
            in_list = True
            continue
        if in_list:
            m = re.match(r"^\s+-\s+(.+)$", line)
            if m:
                result.append(m.group(1).strip())
            elif line.strip() == "" or re.match(r"^\S", line):
                # End of list: blank line or new top-level key
                if line.strip() != "":
                    break
    return result


def _parse_block_scalar(text: str, key: str) -> str | None:
    """Return the content of a `key: |` block scalar (literal block).

    Collects indented lines following the `key: |` marker until a line with
    equal or lesser indentation (or end of file) is encountered.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}:\s*\|\s*$", line):
            # Determine the indentation level from the first non-empty line
            block_lines = []
            indent = None
            for subsequent in lines[i + 1:]:
                if subsequent.strip() == "":
                    block_lines.append("")
                    continue
                current_indent = len(subsequent) - len(subsequent.lstrip())
                if indent is None:
                    indent = current_indent
                if current_indent < indent:
                    break
                block_lines.append(subsequent[indent:])
            # Strip trailing blank lines
            while block_lines and block_lines[-1] == "":
                block_lines.pop()
            return "\n".join(block_lines)
    return None


def parse_scenario(path: Path) -> dict:
    """Parse a scenario YAML file into a dictionary."""
    text = path.read_text()

    skill = _parse_scalar_value(text, "skill") or ""
    name = _parse_scalar_value(text, "name") or ""
    description = _parse_scalar_value(text, "description") or ""
    pass_threshold = _parse_int_value(text, "pass_threshold", default=1)

    # `task` is a block scalar (`|`)
    task = _parse_block_scalar(text, "task") or ""

    pass_signals = _parse_list_value(text, "pass_signals")
    fail_signals = _parse_list_value(text, "fail_signals")

    return {
        "skill": skill,
        "name": name,
        "description": description,
        "task": task,
        "pass_threshold": pass_threshold,
        "pass_signals": pass_signals,
        "fail_signals": fail_signals,
    }


# ---------------------------------------------------------------------------
# Subagent dispatch
# ---------------------------------------------------------------------------

class DispatchError(Exception):
    """Raised when the subagent process fails to run or returns a non-zero exit."""


def dispatch_subagent(prompt: str) -> tuple[str, float | None]:
    """Run claude -p with the given prompt and return (output_text, cost_usd).

    Raises DispatchError on non-zero exit or missing binary.
    """
    result = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--max-budget-usd",
            "0.50",
            "--no-session-persistence",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        stderr_snippet = result.stderr.strip()[:200]
        raise DispatchError(f"exit {result.returncode}: {stderr_snippet}")

    raw = result.stdout.strip()
    if not raw:
        return ("", None)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat raw stdout as plain text
        return (raw, None)

    # Extract text response
    text_response = ""
    if isinstance(data, dict):
        # Claude JSON output formats vary; try common keys
        text_response = (
            data.get("result")
            or data.get("text")
            or data.get("content")
            or ""
        )
        if not isinstance(text_response, str):
            text_response = str(text_response)

    # Extract cost
    cost: float | None = None
    if isinstance(data, dict):
        cost_raw = data.get("cost_usd") or data.get("cost")
        if cost_raw is not None:
            try:
                cost = float(cost_raw)
            except (TypeError, ValueError):
                pass

    return (text_response, cost)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_run(output: str, pass_signals: list[str], fail_signals: list[str]) -> tuple[str, str]:
    """Evaluate a single run's output.

    Returns (verdict, detail) where verdict is "PASS", "FAIL", or "UNCERTAIN"
    and detail is a human-readable explanation (empty string for PASS).
    """
    # Check fail signals first (immediate failure)
    for pattern in fail_signals:
        if re.search(pattern, output, re.IGNORECASE):
            return ("FAIL", f'fail_signal matched: \'{pattern}\'')

    # Check pass signals
    for pattern in pass_signals:
        if re.search(pattern, output, re.IGNORECASE):
            return ("PASS", "")

    return ("UNCERTAIN", "no pass or fail signal matched")


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def run_scenario(scenario: dict) -> tuple[str, str, float | None]:
    """Run a single scenario (possibly multiple times if pass_threshold > 1).

    Returns (verdict, detail, total_cost_usd).
    """
    skill = scenario["skill"]
    name = scenario["name"]
    task = scenario["task"]
    pass_threshold = scenario["pass_threshold"]
    pass_signals = scenario["pass_signals"]
    fail_signals = scenario["fail_signals"]

    label = f"{skill}/{name}"
    total_cost: float | None = None

    for run_num in range(1, pass_threshold + 1):
        if pass_threshold > 1:
            print(f"  run {run_num}/{pass_threshold} ...", flush=True)

        try:
            output, cost = dispatch_subagent(task)
        except subprocess.TimeoutExpired:
            return ("FAIL", "subagent timed out after 120s", total_cost)
        except FileNotFoundError:
            return ("FAIL", "claude binary not found", total_cost)
        except DispatchError as exc:
            return ("FAIL", f"dispatch failed: {exc}", total_cost)

        if cost is not None:
            total_cost = (total_cost or 0.0) + cost

        verdict, detail = evaluate_run(output, pass_signals, fail_signals)

        if verdict != "PASS":
            # Any non-passing run ends the scenario immediately
            return (verdict, detail, total_cost)

    return ("PASS", "", total_cost)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 tests/pressure_runner.py <skill>", file=sys.stderr)
        sys.exit(1)

    skill = sys.argv[1]
    skill_dir = SCENARIOS_DIR / skill

    if not skill_dir.is_dir():
        print(f"SKIP {skill}: no scenario directory at {skill_dir}")
        sys.exit(0)

    scenario_files = sorted(skill_dir.glob("*.yaml"))
    if not scenario_files:
        print(f"SKIP {skill}: no scenario files in {skill_dir}")
        sys.exit(0)

    passed = 0
    failed = 0
    total = 0

    for scenario_path in scenario_files:
        scenario = parse_scenario(scenario_path)
        label = f"{scenario['skill']}/{scenario['name']}"
        total += 1

        verdict, detail, cost = run_scenario(scenario)
        cost_str = f" (cost: ~${cost:.2f})" if cost is not None else ""

        if verdict == "PASS":
            print(f"PASS {label}{cost_str}")
            passed += 1
        elif verdict == "FAIL":
            print(f"FAIL {label}: {detail}{cost_str}")
            failed += 1
        else:
            # UNCERTAIN treated as failure
            print(f"UNCERTAIN {label}: {detail}{cost_str}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed (out of {total})")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
