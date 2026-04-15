#!/usr/bin/env python3
"""Evaluate a skill's precondition_checks and report pass/fail per check.

Reads the named skill's SKILL.md directly (registry.json is not required).
Runs each shell command listed in precondition_checks via sh -c and prints a
per-check result line.

Usage: python3 validate-preconditions.py <skill-name>

Exit 0 if all checks pass (or no checks are defined); exit 1 if any check
fails or cannot be executed.
"""

import subprocess
import sys
from pathlib import Path

import yaml


def parse_frontmatter(text: str) -> tuple[dict, str, "str | None"]:
    """Parse YAML frontmatter from a SKILL.md file.

    Returns (frontmatter_dict, body, error) where:
    - frontmatter_dict is the parsed YAML dict (empty on failure)
    - body is everything after the closing --- fence (full text if no fences)
    - error is a human-readable error string if YAML parsing failed, else None

    Delegates to yaml.safe_load for parsing.
    """
    lines = text.split("\n")

    # Find opening ---
    if not lines or lines[0].strip() != "---":
        return {}, text, None

    # Find closing ---
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, text, None

    yaml_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :])

    try:
        result = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        location = f"line {mark.line + 1}" if mark is not None else "unknown location"
        problem = getattr(e, "problem", str(e))
        return {}, body, f"YAML parse error at {location}: {problem}"

    if not isinstance(result, dict):
        return {}, body, None

    return result, body, None


def find_skill_md(skill_name: str) -> "Path | None":
    """Locate SKILL.md for the given skill name.

    Searches in order:
    1. skills/<skill-name>/SKILL.md  (when run from repo root)
    2. <skill-name>/SKILL.md         (when run from skills/ dir)
    """
    candidates = [
        Path("skills") / skill_name / "SKILL.md",
        Path(skill_name) / "SKILL.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def run_checks(checks: list[str]) -> int:
    """Run each shell command in checks and print a per-check report.

    Returns 0 if all checks pass, 1 if any fail or cannot be executed.
    """
    all_passed = True

    for cmd in checks:
        try:
            result = subprocess.run(
                ["sh", "-c", cmd],
                capture_output=True,
                text=True,
            )
        except OSError as e:
            print(f"  [ERROR] {cmd!r}: execution error: {e}")
            all_passed = False
            continue

        if result.returncode == 0:
            print(f"  [PASS]  {cmd}")
        else:
            print(f"  [FAIL]  {cmd}")
            all_passed = False

    return 0 if all_passed else 1


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <skill-name>", file=sys.stderr)
        return 2

    skill_name = sys.argv[1]

    skill_md_path = find_skill_md(skill_name)
    if skill_md_path is None:
        print(f"[ERROR] {skill_name}: SKILL.md not found", file=sys.stderr)
        return 1

    try:
        text = skill_md_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[ERROR] {skill_name}: could not read SKILL.md: {e}", file=sys.stderr)
        return 1

    frontmatter, _body, yaml_error = parse_frontmatter(text)

    if yaml_error:
        print(f"[ERROR] {skill_name}: {yaml_error}", file=sys.stderr)
        return 1

    if not frontmatter:
        print(f"[ERROR] {skill_name}: no frontmatter found (missing --- fences)", file=sys.stderr)
        return 1

    checks = frontmatter.get("precondition_checks")

    if not checks:
        print(f"{skill_name}: no checks defined")
        return 0

    if not isinstance(checks, list):
        print(
            f"[ERROR] {skill_name}: precondition_checks must be a list",
            file=sys.stderr,
        )
        return 1

    print(f"{skill_name}: running {len(checks)} precondition check(s)")
    exit_code = run_checks(checks)

    if exit_code == 0:
        print(f"{skill_name}: all checks passed")
    else:
        print(f"{skill_name}: one or more checks failed")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
