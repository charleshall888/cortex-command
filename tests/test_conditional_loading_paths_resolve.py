"""Lint: every ``## Conditional Loading`` path in project.md must exist on disk.

Spec: cortex/lifecycle/no-lifecycle-area-requirements-doc-so/spec.md (R9).

``cortex/requirements/project.md`` routes area docs with bullets of the form
``<trigger> → <path>``. The loader
(``cortex_command.lifecycle.load_requirements_cli``) splits each bullet on the
FIRST U+2192 and existence-checks **all** the text to the right of the arrow,
verbatim. A row whose path carries any trailing decoration — an editorial
parenthetical, a note, a stray comment — therefore never resolves; the loader
silently emits it with the ``(skipped: file absent)`` suffix and the area doc is
never read.

Named failure this gate prevents: #454 shipped the routing row
``... → cortex/requirements/lifecycle.md (NOT YET WRITTEN — ...)``. The path
could never resolve, and no test could see it.

The helper deliberately calls the loader's own ``_parse_conditional_loading``
rather than re-implementing the split. Parser parity is what makes the defect
catchable: a lint with its own lenient regex could strip a trailing annotation
that the loader keeps, pass, and miss exactly the failure it exists to prevent.

``## Global Context`` is out of scope by design — ``skills/requirements/SKILL.md``
states that listing a Global Context path before its file exists is valid, so
asserting existence on those paths would be wrong.

Self-tests at the bottom exercise the helper against ``tmp_path`` fixtures (one
positive, one negative). The terminal
``test_live_project_md_conditional_loading_paths_resolve`` runs the lint against
the repo's real ``project.md`` and is the load-bearing regression guard: a
``tmp_path`` fixture cannot catch a defect in the live routing table.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.lifecycle.load_requirements_cli import (
    _parse_conditional_loading,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_MD = REPO_ROOT / "cortex" / "requirements" / "project.md"


def _find_unresolvable_conditional_paths(
    project_md_text: str,
    root: Path,
) -> list[str]:
    """Return diagnostics for Conditional Loading rows whose path is not a file.

    Each returned string is the operator-facing failure message:
    ``UNRESOLVABLE_AREA_DOC_PATH: trigger "<trigger>" routes to "<path>" ...``
    """
    diagnostics: list[str] = []
    for trigger, path in _parse_conditional_loading(project_md_text):
        if (root / path).is_file():
            continue
        diagnostics.append(
            f'UNRESOLVABLE_AREA_DOC_PATH: trigger "{trigger}" routes to '
            f'"{path}", which is not a file under {root}'
        )
    return diagnostics


# ---------------------------------------------------------------------------
# Self-tests against tmp_path fixtures
# ---------------------------------------------------------------------------


def _seed_project_md(tmp_path: Path, conditional_rows: str) -> str:
    """Return a minimal project.md body with the given Conditional Loading rows."""
    (tmp_path / "cortex" / "requirements").mkdir(parents=True, exist_ok=True)
    return (
        "# Requirements: project\n\n"
        "## Conditional Loading\n\n"
        f"{conditional_rows}\n"
        "## Global Context\n\n"
        "- cortex/requirements/glossary.md\n"
    )


def test_fixture_positive_existing_area_doc_passes_lint(tmp_path: Path) -> None:
    """A routing row whose bare path exists on disk passes."""
    text = _seed_project_md(
        tmp_path,
        "- lifecycle state machine → cortex/requirements/lifecycle.md\n",
    )
    (tmp_path / "cortex" / "requirements" / "lifecycle.md").write_text(
        "# Requirements: lifecycle\n", encoding="utf-8"
    )

    assert _find_unresolvable_conditional_paths(text, tmp_path) == []


def test_fixture_negative_annotated_path_fails_lint(tmp_path: Path) -> None:
    """A trailing parenthetical makes the path unresolvable and is reported.

    This is the #454 shape verbatim: the file exists, but the annotated row
    still cannot resolve because the loader keeps everything right of the arrow.
    """
    text = _seed_project_md(
        tmp_path,
        "- lifecycle state machine → cortex/requirements/lifecycle.md "
        "(NOT YET WRITTEN — see #469)\n",
    )
    (tmp_path / "cortex" / "requirements" / "lifecycle.md").write_text(
        "# Requirements: lifecycle\n", encoding="utf-8"
    )

    diagnostics = _find_unresolvable_conditional_paths(text, tmp_path)

    assert len(diagnostics) == 1, diagnostics
    msg = diagnostics[0]
    assert "UNRESOLVABLE_AREA_DOC_PATH" in msg
    assert "lifecycle state machine" in msg
    assert "NOT YET WRITTEN" in msg


# ---------------------------------------------------------------------------
# Live-corpus assertion: load-bearing regression guard against #454-style
# unresolvable routing rows. A tmp_path fixture cannot catch this defect.
# ---------------------------------------------------------------------------


def test_live_project_md_conditional_loading_paths_resolve() -> None:
    """Every ``## Conditional Loading`` path in the real project.md must exist."""
    diagnostics = _find_unresolvable_conditional_paths(
        PROJECT_MD.read_text(encoding="utf-8"),
        REPO_ROOT,
    )
    assert diagnostics == [], "\n".join(diagnostics)
