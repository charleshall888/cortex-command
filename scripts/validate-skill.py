#!/usr/bin/env python3
"""Validate SKILL.md frontmatter against the prompt contract schema.

Accepts a skill directory path (containing SKILL.md) or a parent directory
to scan all subdirectories. Validates required fields, notes present
contract fields, and checks {{variable}} consistency.

Exit 0 if no errors; non-zero if any skill has errors.
Warnings (variable mismatches) do not cause non-zero exit.
Info notes (contract fields declared) are informational only.
"""

import re
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


def extract_input_varnames(inputs: list[str]) -> set[str]:
    """Extract variable names from inputs list entries.

    Each input follows the pattern: "name: type (qualifier) — description"
    The variable name is the part before the first colon.
    """
    names = set()
    for entry in inputs:
        # Take the part before the first colon
        if ":" in entry:
            name = entry.split(":")[0].strip()
            if name:
                names.add(name)
    return names


def extract_body_variables(body: str) -> set[str]:
    """Extract all {{varname}} patterns from the SKILL.md body."""
    return set(re.findall(r"\{\{(\w+)\}\}", body))


def validate_skill(skill_dir: Path) -> tuple[list[str], list[str], list[str]]:
    """Validate a single skill directory.

    Returns (errors, warnings, infos) as lists of message strings.
    """
    errors = []
    warnings = []
    infos = []

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        errors.append("SKILL.md not found")
        return errors, warnings, infos

    text = skill_md.read_text(encoding="utf-8")
    frontmatter, body, yaml_error = parse_frontmatter(text)

    if yaml_error:
        errors.append(yaml_error)
        return errors, warnings, infos

    if not frontmatter:
        errors.append("no frontmatter found (missing --- fences)")
        return errors, warnings, infos

    # Required fields
    required = ["name", "description"]
    missing_required = [f for f in required if f not in frontmatter or not frontmatter[f]]
    if missing_required:
        errors.append(f"missing required fields: {', '.join(missing_required)}")
    else:
        # All required fields present — no message needed, we report OK at the caller level
        pass

    # Contract fields (info note if present)
    contract_fields = ["inputs", "outputs", "preconditions"]
    present_contracts = [f for f in contract_fields if f in frontmatter]
    if present_contracts:
        infos.append(f"contract fields declared: {', '.join(present_contracts)}")

    # Body length check (warn if >500 non-blank lines)
    if "# noqa: body-length" not in text:
        non_blank_lines = sum(1 for line in body.splitlines() if line.strip())
        if non_blank_lines > 500:
            warnings.append(
                f"body is {non_blank_lines} non-blank lines (>500); "
                "consider splitting content into reference files "
                "(suppress with '# noqa: body-length')"
            )

    # Variable mismatch check (only if inputs are declared)
    if "inputs" in frontmatter and isinstance(frontmatter["inputs"], list):
        input_vars = extract_input_varnames(frontmatter["inputs"])
        body_vars = extract_body_variables(body)

        # Also check variables in frontmatter output paths
        if "outputs" in frontmatter and isinstance(frontmatter["outputs"], list):
            for output_entry in frontmatter["outputs"]:
                body_vars.update(re.findall(r"\{\{(\w+)\}\}", output_entry))

        # Variables used in body but not declared in inputs
        undeclared = body_vars - input_vars
        if undeclared:
            warnings.append(
                f"body uses undeclared variables: {', '.join(sorted(undeclared))}"
            )

        # Variables declared in inputs but not used in body
        unused = input_vars - body_vars
        if unused:
            warnings.append(
                f"inputs declares unused variables: {', '.join(sorted(unused))}"
            )

    return errors, warnings, infos


def find_skill_dirs(path: Path) -> list[Path]:
    """Find skill directories under the given path.

    If path contains a SKILL.md, treat it as a single skill directory.
    Otherwise, scan immediate subdirectories for SKILL.md files.
    """
    path = path.resolve()

    if (path / "SKILL.md").exists():
        return [path]

    # Scan subdirectories
    dirs = []
    for child in sorted(path.iterdir()):
        if child.is_dir() and (child / "SKILL.md").exists():
            dirs.append(child)
    return dirs


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <skill-dir-or-parent> [...]", file=sys.stderr)
        return 2

    total_errors = 0
    total_warnings = 0
    total_infos = 0
    total_clean = 0
    total_skills = 0

    for arg in sys.argv[1:]:
        target = Path(arg)
        if not target.exists():
            print(f"[ERROR] {arg}: path does not exist")
            total_errors += 1
            total_skills += 1
            continue

        skill_dirs = find_skill_dirs(target)
        if not skill_dirs:
            print(f"[WARN] {arg}: no SKILL.md files found")
            total_warnings += 1
            total_skills += 1
            continue

        for skill_dir in skill_dirs:
            skill_name = skill_dir.name
            total_skills += 1

            errors, warnings, infos = validate_skill(skill_dir)

            has_errors = len(errors) > 0
            has_warnings = len(warnings) > 0

            for err in errors:
                print(f"[ERROR] {skill_name}: {err}")
                total_errors += 1

            for warn in warnings:
                print(f"[WARN] {skill_name}: {warn}")
                total_warnings += 1

            for info in infos:
                print(f"[INFO] {skill_name}: {info}")
                total_infos += 1

            if not has_errors:
                print(f"[OK] {skill_name}: name and description present")
                if not has_warnings:
                    total_clean += 1

    print(
        f"\n{total_skills} skills: {total_errors} errors, "
        f"{total_warnings} warnings, {total_infos} infos, {total_clean} clean"
    )

    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
