#!/usr/bin/env python3
"""Setup-merge helper: detect symlink inventory and settings diff."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# Required hooks: script filename -> True. These are merged unconditionally.
REQUIRED_HOOK_SCRIPTS = {
    "cortex-sync-permissions.py",
    "cortex-scan-lifecycle.sh",
    "cortex-cleanup-session.sh",
    "cortex-validate-commit.sh",
    "cortex-tool-failure-tracker.sh",
    "cortex-skill-edit-advisor.sh",
    "cortex-permission-audit-log.sh",
    "cortex-worktree-create.sh",
    "cortex-worktree-remove.sh",
}

# Optional hooks: script filename. These are prompted individually.
OPTIONAL_HOOK_SCRIPTS = {
    "cortex-setup-gpg-sandbox-home.sh",
    "cortex-notify.sh",
    "cortex-notify-remote.sh",
}

# Plugin keys to check
REQUIRED_PLUGIN_KEYS = [
    "context7@claude-plugins-official",
    "claude-md-management@claude-plugins-official",
]


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


def read_json_file(path: Path) -> dict | None:
    """Read and parse a JSON file, returning None on any error."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def extract_script_filename(command: str) -> tuple[str, str] | None:
    """Extract the script filename from a hook command string.

    Returns (canonical_name, command_substring) or None.

    canonical_name: the cortex-prefixed name used for REQUIRED/OPTIONAL classification.
    command_substring: the actual string to search for in command fields for presence detection.

    Special case: ~/.claude/notify.sh is the deployed name of cortex-notify.sh
    (hardcoded symlink mapping), so "notify.sh" maps to canonical "cortex-notify.sh"
    but the command_substring remains "notify.sh" for presence matching.
    """
    for part in command.split():
        # Get the basename of any path-like token, stripping quotes
        basename = part.rsplit("/", 1)[-1].strip("'\"")
        if basename.startswith("cortex-"):
            return (basename, basename)
        # notify.sh is the deployed name of cortex-notify.sh
        if basename == "notify.sh":
            return ("cortex-notify.sh", "notify.sh")
    return None


def extract_hooks_from_repo_settings(repo_settings: dict) -> list[dict]:
    """Extract all hook specs from the repo's settings.json.

    Returns a list of dicts with: event_type, matcher, command, timeout (optional),
    script_filename (canonical name for classification), and command_substring
    (for presence detection in user settings).
    """
    hooks_config = repo_settings.get("hooks", {})
    result = []

    for event_type, entries in hooks_config.items():
        for entry in entries:
            matcher = entry.get("matcher", "")
            for hook in entry.get("hooks", []):
                command = hook.get("command", "")
                extracted = extract_script_filename(command)
                if not extracted:
                    continue
                canonical_name, command_substring = extracted
                spec = {
                    "event_type": event_type,
                    "matcher": matcher,
                    "command": command,
                    "script_filename": canonical_name,
                    "command_substring": command_substring,
                }
                if "timeout" in hook:
                    spec["timeout"] = hook["timeout"]
                result.append(spec)

    return result


def is_hook_present(spec: dict, user_settings: dict) -> bool:
    """Check if a hook is present in user settings using the triple match.

    Match on (event_type, matcher, command-substring) where command-substring
    is the script filename appearing anywhere in the command string.
    """
    hooks_config = user_settings.get("hooks", {})
    event_entries = hooks_config.get(spec["event_type"], [])
    # Use command_substring for presence matching (handles notify.sh -> cortex-notify.sh)
    substring = spec.get("command_substring", spec["script_filename"])

    for entry in event_entries:
        entry_matcher = entry.get("matcher", "")
        if entry_matcher != spec["matcher"]:
            continue
        for hook in entry.get("hooks", []):
            command = hook.get("command", "")
            if substring in command:
                return True

    return False


def detect_hooks(repo_settings: dict, user_settings: dict) -> dict:
    """Detect required and optional hooks: present vs absent.

    Returns dict with hooks_required and hooks_optional, each containing
    present (list of script filenames) and absent (list of full hook objects).
    """
    all_specs = extract_hooks_from_repo_settings(repo_settings)

    required_present = []
    required_absent = []
    optional_present = []
    optional_absent = []

    # Track which script filenames we've already recorded as present
    # (a script may appear in multiple event types, e.g. cortex-notify.sh in Notification + Stop)
    required_present_seen = set()
    optional_present_seen = set()

    for spec in all_specs:
        filename = spec["script_filename"]
        present = is_hook_present(spec, user_settings)

        # Build the output object (without script_filename — that's internal)
        hook_obj = {
            "event_type": spec["event_type"],
            "matcher": spec["matcher"],
            "command": spec["command"],
        }
        if "timeout" in spec:
            hook_obj["timeout"] = spec["timeout"]

        if filename in REQUIRED_HOOK_SCRIPTS:
            if present:
                if filename not in required_present_seen:
                    required_present.append(filename)
                    required_present_seen.add(filename)
            else:
                required_absent.append(hook_obj)
        elif filename in OPTIONAL_HOOK_SCRIPTS:
            if present:
                if filename not in optional_present_seen:
                    optional_present.append(filename)
                    optional_present_seen.add(filename)
            else:
                optional_absent.append(hook_obj)

    return {
        "hooks_required": {
            "present": required_present,
            "absent": required_absent,
        },
        "hooks_optional": {
            "present": optional_present,
            "absent": optional_absent,
        },
    }


def detect_allow_delta(repo_settings: dict, user_settings: dict) -> list[str]:
    """Compute set difference for permissions.allow."""
    user_allow = set(user_settings.get("permissions", {}).get("allow", []))
    # Preserve repo ordering for the delta
    return [
        entry for entry in repo_settings.get("permissions", {}).get("allow", [])
        if entry not in user_allow
    ]


def detect_deny_delta(repo_settings: dict, user_settings: dict) -> list[str]:
    """Compute set difference for permissions.deny."""
    user_deny = set(user_settings.get("permissions", {}).get("deny", []))
    return [
        entry for entry in repo_settings.get("permissions", {}).get("deny", [])
        if entry not in user_deny
    ]


def detect_sandbox_delta(repo_settings: dict, user_settings: dict) -> dict:
    """Compare sandbox config arrays and scalar."""
    repo_sandbox = repo_settings.get("sandbox", {})
    user_sandbox = user_settings.get("sandbox", {})

    delta = {}

    # network.allowedDomains
    user_domains = set(user_sandbox.get("network", {}).get("allowedDomains", []))
    missing_domains = [
        d for d in repo_sandbox.get("network", {}).get("allowedDomains", [])
        if d not in user_domains
    ]
    if missing_domains:
        delta["allowedDomains"] = missing_domains

    # network.allowUnixSockets
    user_sockets = set(user_sandbox.get("network", {}).get("allowUnixSockets", []))
    missing_sockets = [
        s for s in repo_sandbox.get("network", {}).get("allowUnixSockets", [])
        if s not in user_sockets
    ]
    if missing_sockets:
        delta["allowUnixSockets"] = missing_sockets

    # excludedCommands
    user_excluded = set(user_sandbox.get("excludedCommands", []))
    missing_excluded = [
        e for e in repo_sandbox.get("excludedCommands", [])
        if e not in user_excluded
    ]
    if missing_excluded:
        delta["excludedCommands"] = missing_excluded

    # autoAllowBashIfSandboxed scalar
    repo_auto = repo_sandbox.get("autoAllowBashIfSandboxed")
    user_auto = user_sandbox.get("autoAllowBashIfSandboxed")
    if repo_auto is not None and user_auto != repo_auto:
        delta["autoAllowBashIfSandboxed"] = repo_auto

    return delta


def detect_statusline_delta(repo_settings: dict, user_settings: dict) -> dict | None:
    """Compare statusLine config. Returns the full cortex object if absent/different."""
    repo_statusline = repo_settings.get("statusLine")
    user_statusline = user_settings.get("statusLine")

    if repo_statusline is None:
        return None

    # Compare command field specifically
    if user_statusline is None:
        return repo_statusline

    if user_statusline.get("command") != repo_statusline.get("command"):
        return repo_statusline

    return None


def detect_plugins_delta(repo_settings: dict, user_settings: dict) -> dict:
    """Check plugin keys individually. Returns dict of missing plugin entries."""
    repo_plugins = repo_settings.get("enabledPlugins", {})
    user_plugins = user_settings.get("enabledPlugins", {})

    delta = {}
    for key in REQUIRED_PLUGIN_KEYS:
        if key in repo_plugins and key not in user_plugins:
            delta[key] = repo_plugins[key]

    return delta


def detect_apikey_helper(
    repo_settings: dict,
    user_settings: dict,
    settings_local: dict | None,
) -> dict:
    """Check apiKeyHelper presence in both settings.json and settings.local.json."""
    repo_value = repo_settings.get("apiKeyHelper")
    if repo_value is None:
        return {"status": "not_in_repo"}

    # Check settings.local.json first
    if settings_local is not None and "apiKeyHelper" in settings_local:
        return {"status": "present_in_local", "value": settings_local["apiKeyHelper"]}

    # Check user's settings.json
    if "apiKeyHelper" in user_settings:
        return {"status": "present", "value": user_settings["apiKeyHelper"]}

    return {"status": "absent", "value": repo_value}


def detect_settings(repo_root: Path, user_settings_path: Path) -> dict:
    """Detect settings.json differences and hook specs.

    Returns a dict with mtime, hook detection results, and per-category deltas.
    """
    home = Path.home()

    # Read repo's settings.json (canonical source)
    repo_settings_path = repo_root / "claude" / "settings.json"
    repo_settings = read_json_file(repo_settings_path)
    if repo_settings is None:
        return {"error": "Could not read repo settings.json"}

    # Read user's settings.json
    user_settings = read_json_file(user_settings_path)
    if user_settings is None:
        # If user has no settings.json, everything is absent
        user_settings = {}

    # Capture mtime immediately after reading
    try:
        mtime = os.stat(str(user_settings_path)).st_mtime
    except OSError:
        mtime = None

    # Read settings.local.json (read-only, for apiKeyHelper check)
    settings_local_path = home / ".claude" / "settings.local.json"
    settings_local = read_json_file(settings_local_path)

    # Detect hooks
    hooks = detect_hooks(repo_settings, user_settings)

    # Detect per-category deltas
    allow_delta = detect_allow_delta(repo_settings, user_settings)
    deny_delta = detect_deny_delta(repo_settings, user_settings)
    sandbox_delta = detect_sandbox_delta(repo_settings, user_settings)
    statusline_delta = detect_statusline_delta(repo_settings, user_settings)
    plugins_delta = detect_plugins_delta(repo_settings, user_settings)
    apikey_helper = detect_apikey_helper(repo_settings, user_settings, settings_local)

    return {
        "mtime": mtime,
        "user_settings_path": str(user_settings_path),
        "hooks_required": hooks["hooks_required"],
        "hooks_optional": hooks["hooks_optional"],
        "allow": {"absent": allow_delta},
        "deny": {"absent": deny_delta},
        "sandbox": {"absent": sandbox_delta},
        "statusLine": {"absent": statusline_delta},
        "plugins": {"absent": plugins_delta},
        "apiKeyHelper": apikey_helper,
    }


def apply_hooks(settings: dict, hooks_to_add: list[dict]) -> dict:
    """Apply hook insertion algorithm for each hook spec.

    For each hook spec in hooks_to_add:
    1. Get or create the event_type array in settings["hooks"]
    2. Find first entry whose matcher matches spec's matcher
    3. If found: append the hook command to that entry's hooks array
    4. If not found: create a new entry and append to the event_type array

    Mutates settings in place and returns it for chaining.
    """
    for spec in hooks_to_add:
        event_arr = settings.setdefault("hooks", {}).setdefault(spec["event_type"], [])

        # Build the hook object to insert
        hook_obj = {"type": "command", "command": spec["command"]}
        if "timeout" in spec:
            hook_obj["timeout"] = spec["timeout"]

        # Find first entry with matching matcher
        matcher = spec.get("matcher", "")
        matched_entry = None
        for entry in event_arr:
            if entry.get("matcher", "") == matcher:
                matched_entry = entry
                break

        if matched_entry is not None:
            # Check for duplicates: don't add if command already present
            existing_commands = [
                h.get("command", "") for h in matched_entry.get("hooks", [])
            ]
            if spec["command"] not in existing_commands:
                matched_entry.setdefault("hooks", []).append(hook_obj)
        else:
            # Create new entry
            new_entry = {"hooks": [hook_obj]}
            if matcher:
                new_entry["matcher"] = matcher
            event_arr.append(new_entry)

    return settings


def run_merge(
    detect_file_path: str,
    approved_optional_hooks: list[str],
    approvals_dict: dict,
) -> dict:
    """Run merge mode: read detect tempfile, apply hooks, return modified settings.

    Args:
        detect_file_path: path to the detect tempfile JSON
        approved_optional_hooks: list of approved optional hook script filenames
        approvals_dict: dict of category -> bool for non-hook categories (used in Task 5)

    Returns:
        dict with the modified settings after hook insertion
    """
    # Read detect tempfile
    detect_path = Path(detect_file_path)
    if not detect_path.exists():
        return {"error": f"detect file not found: {detect_file_path}"}

    try:
        detect_data = json.loads(detect_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return {"error": f"could not read detect file: {e}"}

    settings_data = detect_data.get("settings", {})
    if "error" in settings_data:
        return {"error": f"detect reported error: {settings_data['error']}"}

    # Read the user's current settings.json
    user_settings_path = settings_data.get("user_settings_path")
    if not user_settings_path:
        return {"error": "no user_settings_path in detect data"}

    user_settings_file = Path(user_settings_path)
    if user_settings_file.exists():
        try:
            settings = json.loads(user_settings_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            return {"error": f"could not read user settings: {e}"}
    else:
        settings = {}

    # Collect hooks to add: required hooks (always) + approved optional hooks
    hooks_to_add = []

    # Required hooks from absent list — always merged
    required_absent = settings_data.get("hooks_required", {}).get("absent", [])
    hooks_to_add.extend(required_absent)

    # Optional hooks — only approved ones
    optional_absent = settings_data.get("hooks_optional", {}).get("absent", [])
    for hook_spec in optional_absent:
        # Match by script filename if present, otherwise by command substring
        # The detect output absent list contains full hook objects with command field
        # We need to check if this hook's script was approved
        script_name = _extract_script_from_command(hook_spec.get("command", ""))
        if script_name in approved_optional_hooks:
            hooks_to_add.append(hook_spec)

    # Apply hook insertion
    apply_hooks(settings, hooks_to_add)

    # Non-hook categories will be applied in Task 5
    return {
        "settings": settings,
        "mtime": detect_data.get("mtime"),
        "user_settings_path": user_settings_path,
        "approvals": approvals_dict,
        "detect_data": detect_data,
    }


def _extract_script_from_command(command: str) -> str | None:
    """Extract the canonical script filename from a command string.

    Returns the canonical name (cortex-prefixed) or None.
    """
    result = extract_script_filename(command)
    if result:
        return result[0]  # canonical_name
    return None


def cmd_detect(args: argparse.Namespace) -> None:
    """Run the detect subcommand: discover symlinks and settings diffs."""
    repo_root = get_repo_root(args.repo_root)
    symlinks = discover_symlinks(repo_root)

    output = {"symlinks": symlinks}

    # Detect settings.json differences
    user_settings_path = Path(args.settings).expanduser()
    settings_result = detect_settings(repo_root, user_settings_path)
    output["settings"] = settings_result
    if "mtime" in settings_result:
        output["mtime"] = settings_result["mtime"]

    # Write to tempfile at $TMPDIR/setup-merge-detect.json
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    outpath = Path(tmpdir) / "setup-merge-detect.json"
    outpath.write_text(json.dumps(output, indent=2) + "\n")

    # Print the tempfile path to stdout for SKILL.md to capture
    print(str(outpath))


def cmd_merge(args: argparse.Namespace) -> None:
    """Run the merge subcommand: apply hooks and approved categories."""
    # Parse optional hooks JSON array
    try:
        optional_hooks = json.loads(args.optional_hooks) if args.optional_hooks else []
    except json.JSONDecodeError:
        print(json.dumps({"error": f"invalid --optional-hooks JSON: {args.optional_hooks}"}))
        sys.exit(1)

    # Build approvals dict from CLI flags
    approvals = {
        "allow": args.approve_allow,
        "deny": args.approve_deny,
        "sandbox": args.approve_sandbox,
        "statusLine": args.approve_statusline,
        "plugins": args.approve_plugins,
        "apiKeyHelper": args.approve_apikey,
    }

    result = run_merge(args.detect_file, optional_hooks, approvals)

    # Output result as JSON
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Setup-merge helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_parser = subparsers.add_parser("detect", help="Detect symlink inventory and settings diffs")
    detect_parser.add_argument(
        "--repo-root",
        default=None,
        help="Path to the repo root (default: uses git rev-parse)",
    )
    detect_parser.add_argument(
        "--settings",
        default="~/.claude/settings.json",
        help="Path to user's settings.json (default: ~/.claude/settings.json)",
    )

    merge_parser = subparsers.add_parser("merge", help="Merge approved categories into settings")
    merge_parser.add_argument(
        "--detect-file",
        required=True,
        help="Path to detect output tempfile",
    )
    merge_parser.add_argument(
        "--optional-hooks",
        default="[]",
        help="JSON array of approved optional hook script filenames",
    )
    merge_parser.add_argument(
        "--approve-allow",
        type=lambda x: x.lower() == "true",
        default=False,
        help="Approve allow list merge (true/false)",
    )
    merge_parser.add_argument(
        "--approve-deny",
        type=lambda x: x.lower() == "true",
        default=False,
        help="Approve deny list merge (true/false)",
    )
    merge_parser.add_argument(
        "--approve-sandbox",
        type=lambda x: x.lower() == "true",
        default=False,
        help="Approve sandbox config merge (true/false)",
    )
    merge_parser.add_argument(
        "--approve-statusline",
        type=lambda x: x.lower() == "true",
        default=False,
        help="Approve statusLine merge (true/false)",
    )
    merge_parser.add_argument(
        "--approve-plugins",
        type=lambda x: x.lower() == "true",
        default=False,
        help="Approve plugins merge (true/false)",
    )
    merge_parser.add_argument(
        "--approve-apikey",
        type=lambda x: x.lower() == "true",
        default=False,
        help="Approve apiKeyHelper merge (true/false)",
    )

    args = parser.parse_args()

    if args.command == "detect":
        cmd_detect(args)
    elif args.command == "merge":
        cmd_merge(args)


if __name__ == "__main__":
    main()
