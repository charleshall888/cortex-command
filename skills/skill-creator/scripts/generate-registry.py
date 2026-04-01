#!/usr/bin/env python3
"""Generate skills/registry.json from all skills/*/SKILL.md frontmatter.

Scans the given skills directory for subdirectories containing SKILL.md,
parses each file's YAML frontmatter, and writes a registry.json with each
skill's name, description, inputs, outputs, preconditions, and
precondition_checks.

Usage: python3 generate-registry.py <skills-dir>

Exit 0 on success; non-zero if the registry could not be written.
"""

import json
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


def build_registry(skills_dir: Path) -> tuple[list[dict], list[str]]:
    """Scan skills_dir for SKILL.md files and build registry entries.

    Returns (entries, errors) where:
    - entries is a list of skill dicts
    - errors is a list of human-readable error strings for skipped skills
    """
    entries = []
    errors = []

    skill_dirs = sorted(
        child for child in skills_dir.iterdir()
        if child.is_dir() and (child / "SKILL.md").exists()
    )

    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError as e:
            errors.append(f"{skill_dir.name}: could not read SKILL.md: {e}")
            continue

        frontmatter, _body, yaml_error = parse_frontmatter(text)

        if yaml_error:
            errors.append(f"{skill_dir.name}: {yaml_error}")
            continue

        if not frontmatter:
            errors.append(f"{skill_dir.name}: no frontmatter found (missing --- fences)")
            continue

        entry = {
            "name": frontmatter.get("name") or skill_dir.name,
            "description": frontmatter.get("description") or "",
            "inputs": frontmatter.get("inputs") or [],
            "outputs": frontmatter.get("outputs") or [],
            "preconditions": frontmatter.get("preconditions") or [],
            "precondition_checks": frontmatter.get("precondition_checks") or [],
        }
        entries.append(entry)

    return entries, errors


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <skills-dir>", file=sys.stderr)
        return 2

    skills_dir = Path(sys.argv[1]).resolve()

    if not skills_dir.is_dir():
        print(f"[ERROR] {skills_dir}: not a directory", file=sys.stderr)
        return 1

    entries, errors = build_registry(skills_dir)

    for err in errors:
        print(f"[WARN] {err}", file=sys.stderr)

    registry = {"skills": entries}
    output_path = skills_dir / "registry.json"

    try:
        output_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        print(f"[ERROR] could not write {output_path}: {e}", file=sys.stderr)
        return 1

    print(f"Wrote {len(entries)} skill(s) to {output_path}")
    if errors:
        print(f"{len(errors)} skill(s) skipped due to errors (see stderr)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
