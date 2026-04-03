#!/usr/bin/env python3
"""Setup-merge helper: detect symlink inventory and classify status."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def get_repo_root(repo_root_arg: str) -> Path:
    """Resolve the repo root from the argument, using git rev-parse."""
    if repo_root_arg:
        # Use git rev-parse from the given directory to get the absolute root
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repo_root_arg,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error: could not determine repo root: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        return Path(result.stdout.strip())
    # Fallback: git rev-parse from subprocess default cwd
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error: could not determine repo root: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return Path(result.stdout.strip())


def classify(source: Path, target: Path) -> str:
    """Classify the status of a symlink target path.

    Returns one of: new, update, conflict-broken, conflict-wrong-target, conflict-file.
    """
    resolved_source = source.resolve()

    if not target.exists() and not target.is_symlink():
        return "new"

    if target.is_symlink():
        resolved_target = target.resolve()
        if not target.exists():
            # Symlink exists but is broken
            return "conflict-broken"
        if resolved_target == resolved_source:
            return "update"
        return "conflict-wrong-target"

    # exists and is not a symlink — it's a regular file (or dir)
    if target.is_file() or target.is_dir():
        return "conflict-file"

    # Fallback (shouldn't happen)
    return "conflict-file"


def discover_symlinks(repo_root: Path) -> list[dict]:
    """Discover all symlink pairs from the repo layout at runtime."""
    home = Path.home()
    entries = []

    # 1. bin/ -> ~/.local/bin/<filename> (all files; ln -sf)
    bin_dir = repo_root / "bin"
    if bin_dir.is_dir():
        for item in sorted(bin_dir.iterdir()):
            if item.is_file():
                source = item
                target = home / ".local" / "bin" / item.name
                entries.append({
                    "source": str(source),
                    "target": str(target),
                    "ln_flag": "-sf",
                    "status": classify(source, target),
                })

    # 2. claude/reference/*.md -> ~/.claude/reference/<filename> (ln -sf)
    ref_dir = repo_root / "claude" / "reference"
    if ref_dir.is_dir():
        for item in sorted(ref_dir.glob("*.md")):
            if item.is_file():
                source = item
                target = home / ".claude" / "reference" / item.name
                entries.append({
                    "source": str(source),
                    "target": str(target),
                    "ln_flag": "-sf",
                    "status": classify(source, target),
                })

    # 3. skills/<name>/ -> ~/.claude/skills/<name> (all subdirs with SKILL.md; ln -sfn)
    skills_dir = repo_root / "skills"
    if skills_dir.is_dir():
        for item in sorted(skills_dir.iterdir()):
            if item.is_dir() and (item / "SKILL.md").exists():
                source = item
                target = home / ".claude" / "skills" / item.name
                entries.append({
                    "source": str(source),
                    "target": str(target),
                    "ln_flag": "-sfn",
                    "status": classify(source, target),
                })

    # 4. hooks/cortex-* -> ~/.claude/hooks/<filename> (all files matching cortex-*; ln -sf)
    #    Special case: hooks/cortex-notify.sh -> ~/.claude/notify.sh (hardcoded)
    hooks_dir = repo_root / "hooks"
    if hooks_dir.is_dir():
        for item in sorted(hooks_dir.glob("cortex-*")):
            if item.is_file():
                source = item
                if item.name == "cortex-notify.sh":
                    # Hardcoded: cortex-notify.sh -> ~/.claude/notify.sh
                    target = home / ".claude" / "notify.sh"
                else:
                    target = home / ".claude" / "hooks" / item.name
                entries.append({
                    "source": str(source),
                    "target": str(target),
                    "ln_flag": "-sf",
                    "status": classify(source, target),
                })

    # 5. claude/rules/*.md -> ~/.claude/rules/<filename> (ln -sf)
    rules_dir = repo_root / "claude" / "rules"
    if rules_dir.is_dir():
        for item in sorted(rules_dir.glob("*.md")):
            if item.is_file():
                source = item
                target = home / ".claude" / "rules" / item.name
                entries.append({
                    "source": str(source),
                    "target": str(target),
                    "ln_flag": "-sf",
                    "status": classify(source, target),
                })

    # 6. Hardcoded: claude/statusline.sh -> ~/.claude/statusline.sh (ln -sf)
    statusline = repo_root / "claude" / "statusline.sh"
    if statusline.is_file():
        target = home / ".claude" / "statusline.sh"
        entries.append({
            "source": str(statusline),
            "target": str(target),
            "ln_flag": "-sf",
            "status": classify(statusline, target),
        })

    return entries


def cmd_detect(args: argparse.Namespace) -> None:
    """Run the detect subcommand: discover symlinks and write JSON to tempfile."""
    repo_root = get_repo_root(args.repo_root)
    symlinks = discover_symlinks(repo_root)

    output = {"symlinks": symlinks}

    # Write to tempfile at $TMPDIR/setup-merge-detect.json
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    outpath = Path(tmpdir) / "setup-merge-detect.json"
    outpath.write_text(json.dumps(output, indent=2) + "\n")

    # Print the tempfile path to stdout for SKILL.md to capture
    print(str(outpath))


def main() -> None:
    parser = argparse.ArgumentParser(description="Setup-merge helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_parser = subparsers.add_parser("detect", help="Detect symlink inventory")
    detect_parser.add_argument(
        "--repo-root",
        default=None,
        help="Path to the repo root (default: uses git rev-parse)",
    )

    args = parser.parse_args()

    if args.command == "detect":
        cmd_detect(args)


if __name__ == "__main__":
    main()
