"""cortex-morning-review-resolve-demo-config — composes morning-review
walkthrough §2a Guard 1's demo-config resolution into one call.

Before this consolidation, walkthrough.md §2a Guard 1 narrated the
``demo-commands:`` (list) vs. ``demo-command:`` (single-string fallback)
resolution as hand-parsed prose: find the bare key, read its indented
entries line-by-line, split each on the first ``:`` into label/command,
and reject empty/control-character values — all written for an agent
reading the raw file text without a YAML library.

This verb performs the equivalent resolution properly: ``cortex/lifecycle.config.md``
is frontmatter-delimited YAML (the same file ``cortex_command.lifecycle_config``
already parses this way for ``branch-mode``/``commit-artifacts``/``backlog.backend``),
so ``_extract_frontmatter_text`` + ``yaml.safe_load`` replace the line-based
scan entirely — a colon inside an unquoted scalar (e.g. ``res://main.tscn``)
is not mistaken for a YAML mapping separator the way naive text-splitting
could be tempted to treat it. The per-entry validation rules (reject an
empty/whitespace-only or control-character-bearing ``command:``) are
preserved exactly, since those are a content contract, not a parsing
mechanism.

Guards 2 (remote session) and 3 (overnight branch presence + merged-feature
count) stay in skill prose — they read ``$SSH_CONNECTION`` and
``overnight-state.json``, neither of which this verb touches. Likewise the
Agent Reasoning (picking the best-matching list entry) and the demo
offer/worktree-creation steps stay in prose — this verb only answers
"what demo config is configured, if any."

States:
  list    — ``demo-commands:`` had at least one entry surviving validation;
            ``entries`` is a list of ``{"path": "list", "label": ..., "command": ...}``.
  single  — the list path had zero valid entries (or was absent/malformed)
            and ``demo-command:`` resolved to a valid single string;
            ``entries`` is ``[{"path": "single", "command": ...}]``.
  none    — no config file, no frontmatter, malformed YAML, neither key
            present, or neither form produced a valid value. ``entries`` is
            empty. Silent per the walkthrough's Guard 1 (no error surfaced
            to the user) — a stderr warning is emitted only for malformed
            YAML, mirroring ``lifecycle_config.read_branch_mode``.
  error   — an unexpected exception (e.g. project root unresolvable)
            escaped ``resolve_demo_config`` itself; ``main`` catches it here
            so the CLI always emits a JSON struct and exits 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

import yaml

from cortex_command.backlog import _telemetry
from cortex_command.common import _resolve_user_project_root_from_cwd
from cortex_command.lifecycle_config import _extract_frontmatter_text

KNOWN_STATES = ("list", "single", "none", "error")

# Control characters below 0x20 are rejected in a command value, except tab
# (0x09) — mirrors the walkthrough's "byte < 0x20 except \t" rule.
_ALLOWED_CONTROL_CHARS = {"\t"}


def _is_valid_command(value: object) -> bool:
    """True iff *value* is a non-empty string with no rejected control char."""
    if not isinstance(value, str):
        return False
    if not value.strip():
        return False
    return not any(
        ord(ch) < 0x20 and ch not in _ALLOWED_CONTROL_CHARS for ch in value
    )


def resolve_demo_config(config_path: Path) -> dict:
    """Resolve the active demo-config entries from *config_path*.

    Never raises for a missing file, malformed YAML, or absent/invalid
    keys — every one of those degrades to ``{"state": "none", "entries": []}``,
    matching the walkthrough's "skip Section 2a silently" contract.
    """
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return {"state": "none", "entries": []}

    frontmatter_text = _extract_frontmatter_text(text)
    if frontmatter_text is None:
        return {"state": "none", "entries": []}

    try:
        parsed = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        print(
            f"cortex-morning-review-resolve-demo-config: warning: failed to "
            f"parse YAML frontmatter in {config_path}: {exc}",
            file=sys.stderr,
        )
        return {"state": "none", "entries": []}

    if not isinstance(parsed, dict):
        return {"state": "none", "entries": []}

    raw_list = parsed.get("demo-commands")
    if isinstance(raw_list, list):
        entries = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            command = item.get("command")
            if not _is_valid_command(command):
                continue
            label = item.get("label")
            entries.append(
                {
                    "path": "list",
                    "label": str(label) if label is not None else "",
                    "command": command,
                }
            )
        if entries:
            return {"state": "list", "entries": entries}

    raw_single = parsed.get("demo-command")
    if raw_single is not None:
        candidate = str(raw_single).strip()
        if _is_valid_command(candidate):
            return {
                "state": "single",
                "entries": [{"path": "single", "command": candidate}],
            }

    return {"state": "none", "entries": []}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-morning-review-resolve-demo-config",
        description=(
            "Resolve morning-review walkthrough §2a Guard 1's demo config "
            "(demo-commands list, falling back to demo-command single "
            "string) from cortex/lifecycle.config.md. Emits a single "
            "{state, entries} struct on stdout (always exit 0)."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-morning-review-resolve-demo-config")
    _build_parser().parse_args(argv)
    try:
        root = _resolve_user_project_root_from_cwd()
        result = resolve_demo_config(root / "cortex" / "lifecycle.config.md")
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
