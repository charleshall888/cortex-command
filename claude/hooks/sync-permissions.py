#!/usr/bin/env python3
"""SessionStart hook: merge global permissions into project settings.local.json.

Works around a Claude Code bug (#17017) where project-level permissions
replace global permissions instead of merging them. Runs once per session
start; skips if already synced (hash match) or if no local permissions exist.
"""

import hashlib
import json
import sys
from pathlib import Path


def get_project_dir() -> Path:
    """Get the project directory from hook stdin JSON, falling back to cwd."""
    try:
        hook_input = json.loads(sys.stdin.read())
        cwd = hook_input.get("cwd")
        if cwd:
            return Path(cwd)
    except Exception:
        pass
    return Path.cwd()


def hash_permissions(perms: dict) -> str:
    """Stable MD5 hash of a permissions dict for change detection."""
    return hashlib.md5(
        json.dumps(perms, sort_keys=True).encode()
    ).hexdigest()


def merge_arrays(local: list, global_: list) -> list:
    """Union of two lists, preserving local order first, deduplicating."""
    seen = set()
    result = []
    for item in local + global_:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def main() -> None:
    project_dir = get_project_dir()
    local_path = project_dir / ".claude" / "settings.local.json"
    global_path = Path.home() / ".claude" / "settings.json"

    # Read global settings
    if not global_path.exists():
        return
    try:
        global_settings = json.loads(global_path.read_text())
    except (json.JSONDecodeError, OSError):
        return
    global_perms = global_settings.get("permissions")
    if not global_perms:
        return

    # Skip if no local settings file — global rules apply natively
    if not local_path.exists():
        return

    try:
        local_settings = json.loads(local_path.read_text())
    except (json.JSONDecodeError, OSError):
        return

    # Skip if local file has no permissions key — global rules apply natively
    if "permissions" not in local_settings:
        return

    local_perms = local_settings["permissions"]

    # Skip if already synced (hash of global perms matches stored marker)
    current_hash = hash_permissions(global_perms)
    if local_settings.get("_globalPermissionsHash") == current_hash:
        return

    # Merge: union of arrays, local entries first
    for key in ("allow", "deny", "ask"):
        local_list = local_perms.get(key, [])
        global_list = global_perms.get(key, [])
        if global_list:
            local_perms[key] = merge_arrays(local_list, global_list)

    # Inherit defaultMode from global if not set locally
    if "defaultMode" not in local_perms and "defaultMode" in global_perms:
        local_perms["defaultMode"] = global_perms["defaultMode"]

    # Write back with hash marker
    local_settings["permissions"] = local_perms
    local_settings["_globalPermissionsHash"] = current_hash

    try:
        local_path.write_text(json.dumps(local_settings, indent=2) + "\n")
    except OSError:
        return


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # Never block a session on hook failure
    sys.exit(0)
