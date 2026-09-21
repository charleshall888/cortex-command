"""cortex-validate-requirements-doc — mechanical acceptance gate for a
just-written cortex/requirements/{project|area}.md.

the requirements skill's templates state two acceptance properties in
prose and previously relied on the model to self-report conformance: every
canonical H2 section must be present (verbatim — "downstream consumers grep
section names"), and (project scope only) the `## Optional` section's token
budget must stay ≤1,200 estimated tokens. This verb turns both into a
mechanical check the skill runs instead of self-reporting; judgment about
where a given answer belongs, or how to fix a failing doc, stays with the
model.

Canonical H2 names (verbatim from the requirements skill's Project/Area
templates — a downstream-grep contract; do not rename these strings without
updating both the templates and this module together):
  Project (8): Overview, Philosophy of Work, Architectural Constraints,
    Quality Attributes, Project Boundaries, Conditional Loading,
    Global Context, Optional.
  Area (7): Overview, Functional Requirements, Non-Functional Requirements,
    Architectural Constraints, Dependencies, Edge Cases, Open Questions.

The presence check is H2-level only (a top-level `## <Name>` line, exact
match after stripping trailing whitespace) — it does not additionally
verify the H3 substructure the templates also prescribe (e.g. Project
Boundaries' `### In Scope`/`### Out of Scope`/`### Deferred`), since only
the H2 names are documented as the downstream-grep contract.

Token counting uses a stdlib chars/token heuristic (`_estimate_tokens`,
~4 chars/token) — no tokenizer dependency. This is a soft authoring
guardrail, not an exact accounting: Claude's tokenizer is not publicly
available, so any local count is approximate anyway, and the estimate is
network-free and deterministic (the properties this gate requires). It
deliberately does NOT reuse `bin/cortex-count-tokens`: that script counts
via the Anthropic SDK's `messages.count_tokens` API, which requires network
access and a resolved API key — unsuitable for a mechanical acceptance gate
that must run offline and deterministically. The same 4-chars/token basis
backs `cortex_command/backlog/load_parent_epic.py`'s `_truncate` char cap
(2000 chars ≈ 500 tokens); each site keeps its own small helper (that one
truncates for prompt injection; this validates against a budget).

States:
  pass            — every check passed.
  fail            — at least one check failed; `checks` names which and why.
  file-not-found  — `path` does not exist.
  error           — an unexpected exception (I/O failure, unknown --scope,
                   ...) escaped `validate_requirements_doc`; `main` catches
                   it here so the CLI always emits a JSON struct and exits 0
                   rather than a traceback.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.lifecycle import requirements_budget

KNOWN_STATES = ("pass", "fail", "file-not-found", "error")

PROJECT_SECTIONS: tuple = (
    "Overview",
    "Philosophy of Work",
    "Architectural Constraints",
    "Quality Attributes",
    "Project Boundaries",
    "Conditional Loading",
    "Global Context",
    "Optional",
)

AREA_SECTIONS: tuple = (
    "Overview",
    "Functional Requirements",
    "Non-Functional Requirements",
    "Architectural Constraints",
    "Dependencies",
    "Edge Cases",
    "Open Questions",
)

OPTIONAL_HEADING = "## Optional"
OPTIONAL_TOKEN_BUDGET = 1200


def _h2_names(text: str) -> set:
    names = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            names.add(stripped[3:].strip())
    return names


def _section_text(text: str, heading: str) -> str:
    """Return the raw text under H2 `heading`, up to the next H2/H1/EOF."""
    out: List[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == heading:
            in_section = True
            continue
        if in_section:
            if stripped.startswith("## ") or stripped.startswith("# "):
                break
            out.append(line)
    return "\n".join(out)


def _estimate_tokens(text: str) -> int:
    """Estimate token count via a 4-chars-per-token heuristic.

    Network-free and deterministic; approximate by design (see module
    docstring) — sufficient for a soft ≤``OPTIONAL_TOKEN_BUDGET`` guardrail.
    """
    return math.ceil(len(text) / 4)


_HEADING_LINE = re.compile(r"^#{1,3}\s+\S.*$")
_RULE_LEAD = re.compile(r"^\s*(?:[-*]\s+)?\*\*([^*]+)\*\*")
_IDENTIFIER = re.compile(r"`([^`\n]+)`")
_STATE_TAG = "**State:**"


def _base_text(path: Path, rev: str) -> str:
    """The doc's text at ``rev``, read through git from the doc's own directory."""
    proc = subprocess.run(
        ["git", "show", f"{rev}:./{path.name}"],
        cwd=str(path.resolve().parent),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ValueError(f"git show {rev}:./{path.name} failed: {proc.stderr.strip()}")
    return proc.stdout


def compact_check(base: str, new: str) -> dict:
    """Compare a compacted doc to its base: what must survive, and what went.

    Headings are cited from code comments and grepped by consumers, and
    ``**State:**`` tags carry a rule's status, so losing either fails. A dropped
    bold rule lead or backticked identifier is only *reported*: compaction
    drops restated rules and history on purpose, so these are for the person
    reading the diff to account for, not for the verb to forbid.
    """

    def headings(text: str) -> List[str]:
        return [l.strip() for l in text.splitlines() if _HEADING_LINE.match(l.strip())]

    def leads(text: str) -> List[str]:
        found = (_RULE_LEAD.match(l) for l in text.splitlines())
        return [m.group(1).strip() for m in found if m]

    new_headings = set(headings(new))
    new_leads = set(leads(new))
    new_ids = set(_IDENTIFIER.findall(new))
    missing_headings = [h for h in headings(base) if h not in new_headings]
    base_tags, new_tags = base.count(_STATE_TAG), new.count(_STATE_TAG)
    return {
        "name": "compact-preserves",
        "pass": not missing_headings and base_tags == new_tags,
        "missing_headings": missing_headings,
        "state_tags": {"base": base_tags, "new": new_tags},
        "dropped_rule_leads": sorted({l for l in leads(base) if l not in new_leads}),
        "dropped_identifiers": sorted(set(_IDENTIFIER.findall(base)) - new_ids),
        "bytes": {"base": len(base.encode("utf-8")), "new": len(new.encode("utf-8"))},
    }


def validate_requirements_doc(
    path: Path, scope: str, compact_base: Optional[str] = None
) -> dict:
    """Run the required-sections + (project-only) Optional-budget checks.

    Raises `ValueError` for an unknown `scope` — `main` converts this to an
    `"error"` state rather than letting it escape as a bare traceback.
    """
    if scope not in ("project", "area"):
        raise ValueError(f"unknown scope {scope!r} — expected 'project' or 'area'")

    if not path.is_file():
        return {"state": "file-not-found", "path": str(path)}

    text = path.read_text(encoding="utf-8")
    canonical = PROJECT_SECTIONS if scope == "project" else AREA_SECTIONS
    present = _h2_names(text)
    missing = [name for name in canonical if name not in present]

    checks: List[dict] = [
        {
            "name": "required-sections",
            "pass": not missing,
            "expected": list(canonical),
            "missing": missing,
        }
    ]

    if scope == "project":
        optional_text = _section_text(text, OPTIONAL_HEADING)
        token_count = _estimate_tokens(optional_text)
        checks.append(
            {
                "name": "optional-token-budget",
                "applicable": True,
                "pass": token_count <= OPTIONAL_TOKEN_BUDGET,
                "token_count": token_count,
                "budget": OPTIONAL_TOKEN_BUDGET,
            }
        )
    else:
        checks.append(
            {"name": "optional-token-budget", "applicable": False, "pass": True}
        )

    size, ceiling = requirements_budget.measure(text)
    checks.append(
        {
            "name": "size-budget",
            "pass": size <= ceiling,
            "size_bytes": size,
            "ceiling_bytes": ceiling,
        }
    )

    if compact_base:
        checks.append(compact_check(_base_text(path, compact_base), text))

    overall = all(c["pass"] for c in checks)
    return {
        "state": "pass" if overall else "fail",
        "path": str(path),
        "checks": checks,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-validate-requirements-doc",
        description=(
            "Run the requirements skill's mechanical acceptance checks (required "
            "H2 sections; project-scope ## Optional token budget) against a "
            "written requirements doc, emitting a {state, checks} JSON "
            "struct on stdout (always exit 0)."
        ),
    )
    parser.add_argument(
        "--path", required=True, help="Path to the written requirements doc."
    )
    parser.add_argument(
        "--scope",
        required=True,
        choices=("project", "area"),
        help="Which template's canonical H2 set to check against.",
    )
    parser.add_argument(
        "--compact-base",
        default=None,
        metavar="REV",
        help=(
            "Git revision holding the pre-compact doc. Adds a compact-preserves "
            "check: every H1-H3 heading and the **State:** tag count must "
            "survive; dropped bold rule leads and backticked identifiers are "
            "listed for review."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-validate-requirements-doc")
    args = _build_parser().parse_args(argv)
    try:
        result = validate_requirements_doc(
            Path(args.path), args.scope, args.compact_base
        )
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
