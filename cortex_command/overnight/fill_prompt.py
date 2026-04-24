"""Orchestrator-round prompt template filler.

Python port of ``fill_prompt()`` from ``runner.sh:362-376``. Loads the
``orchestrator-round.md`` template via ``importlib.resources`` (package-internal
resource) and performs six single-brace ``str.replace`` substitutions.

Dual-layer substitution contract (per ``requirements/multi-agent.md:50``):
single-brace ``{token}`` substitutions happen here; double-brace
``{{feature_X}}`` tokens are preserved verbatim because ``str.replace`` on
single-brace keys does not match doubled braces.
"""

from importlib.resources import files
from pathlib import Path


def fill_prompt(
    round_number: int,
    state_path: Path,
    plan_path: Path,
    events_path: Path,
    session_dir: Path,
    tier: str,
) -> str:
    """Return the orchestrator-round prompt with six tokens substituted.

    Byte-identical to the bash ``sed``-based substitution in
    ``runner.sh:369-374``.
    """
    template = (
        files("cortex_command.overnight.prompts")
        .joinpath("orchestrator-round.md")
        .read_text(encoding="utf-8")
    )
    template = template.replace("{state_path}", str(state_path))
    template = template.replace("{session_plan_path}", str(plan_path))
    template = template.replace("{events_path}", str(events_path))
    template = template.replace("{session_dir}", str(session_dir))
    template = template.replace("{round_number}", str(round_number))
    template = template.replace("{tier}", tier)
    return template
