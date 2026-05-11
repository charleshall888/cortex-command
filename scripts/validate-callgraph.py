#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["pyyaml"]
# ///
"""Validate skill call-graph: no programmatic callee may carry disable-model-invocation: true.

Scans one or more skill-root directories. For each SKILL.md or reference-file *.md
inside a skill directory, detects invocation patterns like ``Invoke `/name` ``,
``Delegate to `/name` ``, or ``invoke the `name` skill``. If the invoked skill
exists in any scanned root and has ``disable-model-invocation: true``, that's a
violation.

Rationale: ``disable-model-invocation: true`` also blocks the Skill tool, so a
skill with that flag cannot be invoked programmatically by another skill.

Usage:
    validate-callgraph.py <skill-root> [<skill-root>...]

Exit 0 if clean, 1 if violations found.
"""

import re
import sys
from pathlib import Path

import yaml


INVOCATION_RE = re.compile(
    r"(?:invoke|delegate\s+to|dispatch(?:es|ed)?)"
    r"\s+(?:the\s+)?"
    r"`(?:/)?(?:cortex(?:-core|-overnight)?:)?([a-z][a-z0-9-]+)`",
    re.IGNORECASE,
)


def parse_frontmatter(text: str) -> dict:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}
    try:
        result = yaml.safe_load("\n".join(lines[1:end_idx]))
    except yaml.YAMLError:
        return {}
    return result if isinstance(result, dict) else {}


def collect_skills(roots: list[Path]) -> dict[str, tuple[Path, bool]]:
    """Return {skill_name: (skill_md_path, disable_flag)} across all given roots."""
    skills: dict[str, tuple[Path, bool]] = {}
    for root in roots:
        if not root.exists():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            fm = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            name = fm.get("name") or skill_md.parent.name
            disabled = fm.get("disable-model-invocation") is True
            skills[name] = (skill_md, disabled)
    return skills


def scan_skill_tree(skill_dir: Path, skills: dict[str, tuple[Path, bool]]) -> list[str]:
    """Return a list of violation strings for one skill directory."""
    violations: list[str] = []
    caller_name = skill_dir.name
    for md_path in sorted(skill_dir.rglob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "<!-- callgraph: ignore -->" in line:
                continue
            for match in INVOCATION_RE.finditer(line):
                callee = match.group(1)
                if callee not in skills:
                    continue
                _, disabled = skills[callee]
                if disabled:
                    violations.append(
                        f"{md_path}:{lineno}: /{caller_name} invokes /{callee} "
                        f"but {callee} has disable-model-invocation: true"
                    )
    return violations


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <skill-root> [<skill-root>...]", file=sys.stderr)
        return 2

    roots = [Path(a).resolve() for a in sys.argv[1:]]
    missing = [r for r in roots if not r.exists()]
    if missing:
        for r in missing:
            print(f"[ERROR] path does not exist: {r}")
        return 2

    skills = collect_skills(roots)
    all_violations: list[str] = []
    total_skills = 0
    for root in roots:
        for skill_dir in sorted(root.iterdir()):
            if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
                continue
            total_skills += 1
            all_violations.extend(scan_skill_tree(skill_dir, skills))

    if all_violations:
        print(f"[FAIL] {len(all_violations)} call-graph violation(s) in {total_skills} skills:")
        for v in all_violations:
            print(f"  {v}")
        return 1

    print(f"[OK] {total_skills} skills: no call-graph violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
