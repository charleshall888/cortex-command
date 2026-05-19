"""Structural pin test: implement.md must not contain daytime-pipeline tokens.

Guards against sibling-PR revert of the daytime-autonomous-pipeline removal
(#246). If any future change re-introduces "cortex-daytime" or
"Daytime Dispatch" into skills/lifecycle/references/implement.md, this test
fails immediately — Adversarial F15 mitigation.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
IMPLEMENT_MD = REPO_ROOT / "skills" / "lifecycle" / "references" / "implement.md"


def test_implement_md_is_daytime_free() -> None:
    """implement.md contains neither "cortex-daytime" nor "Daytime Dispatch"."""
    content = IMPLEMENT_MD.read_text(encoding="utf-8")
    assert "cortex-daytime" not in content, (
        f"{IMPLEMENT_MD.relative_to(REPO_ROOT)} contains 'cortex-daytime'; "
        "the daytime-autonomous-pipeline removal has been reverted"
    )
    assert "Daytime Dispatch" not in content, (
        f"{IMPLEMENT_MD.relative_to(REPO_ROOT)} contains 'Daytime Dispatch'; "
        "the daytime-autonomous-pipeline removal has been reverted"
    )
