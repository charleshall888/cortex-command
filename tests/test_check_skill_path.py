"""Tests for cortex_command.lint.skill_path (SP001 / SP002).

Coverage:
  - test_positive_fixture_flagged_nonzero: positive.md yields ≥1 violation
    (the literal pre-fix production forms from the eight Req-5 files + three
    Class-1 files all flag).
  - test_negative_fixture_yields_zero: negative.md yields 0 — including the
    `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md`-in-Read-context
    case, proving the D2 exemption.
  - Individual D1 cases (raw token + bare *.md consult-ref inside a prompt
    fence; *-prompt.md whole-file scope; body token NOT flagged).
  - Individual D2 cases (Read / cat|bash bare-relative targets flag; the
    precise ${CLAUDE_SKILL_DIR}/-prefixed exemption is load-bearing and NOT
    broadened to "any line mentioning the token").
  - Sentinel suppression.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.lint.skill_path import scan_text

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "skill_path"
POSITIVE_MD = FIXTURES / "positive.md"
NEGATIVE_MD = FIXTURES / "negative.md"


# ---------------------------------------------------------------------------
# Fixture-based tests
# ---------------------------------------------------------------------------


def test_positive_fixture_flagged_nonzero() -> None:
    """positive.md should yield ≥1 violation — every literal pre-fix form flags.

    The fixture carries the real pre-fix production literals (raw skill-dir
    tokens and bare *.md consult-refs inside subagent-prompt fences for D1;
    bare-relative Read / cat|bash targets for D2). It must be flagged non-zero.
    """
    text = POSITIVE_MD.read_text(encoding="utf-8")
    violations = scan_text(text, POSITIVE_MD)
    assert len(violations) >= 1, "positive.md must produce ≥1 violation, got 0"
    codes = {v.code for v in violations}
    assert "SP001" in codes, f"expected ≥1 SP001 (D1) hit; got codes {codes}"
    assert "SP002" in codes, f"expected ≥1 SP002 (D2) hit; got codes {codes}"
    for v in violations:
        assert v.code in {"SP001", "SP002"}, f"Unexpected code {v.code!r}: {v}"


def test_negative_fixture_yields_zero() -> None:
    """negative.md should yield 0 violations.

    Includes the dedicated false-positive fixture
    ``Read ${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md`` (the
    ``${CLAUDE_SKILL_DIR}/../`` body form in a Read context) — it MUST pass,
    proving the D2 exemption — plus a correct body token, a "do not load"
    citation, and a ``:-$TMPDIR`` cache path.
    """
    text = NEGATIVE_MD.read_text(encoding="utf-8")
    violations = scan_text(text, NEGATIVE_MD)
    assert violations == [], (
        f"Expected 0 violations from negative.md, got {len(violations)}:\n"
        + "\n".join(v.format_text() for v in violations)
    )


# ---------------------------------------------------------------------------
# D1 — subagent-prompt-scoped raw token / bare *.md consult-ref
# ---------------------------------------------------------------------------


def test_d1_raw_token_inside_prompt_fence_flags() -> None:
    """A raw ${CLAUDE_SKILL_DIR} token inside a BEGIN/END prompt fence flags SP001."""
    text = (
        "<!-- BEGIN SUBAGENT PROMPT -->\n"
        "Apply the rubric in `${CLAUDE_SKILL_DIR}/references/a-to-b-downgrade-rubric.md`.\n"
        "<!-- END SUBAGENT PROMPT -->\n"
    )
    violations = scan_text(text, Path("test.md"))
    assert any(v.code == "SP001" for v in violations), (
        f"raw token inside prompt fence should flag SP001, got: {violations}"
    )


def test_d1_bare_md_consult_ref_inside_prompt_fence_flags() -> None:
    """A bare `rubric.md` consult-ref inside a prompt fence flags SP001."""
    text = (
        "<!-- BEGIN SUBAGENT PROMPT -->\n"
        "Score each finding along the axes defined in `rubric.md`:\n"
        "<!-- END SUBAGENT PROMPT -->\n"
    )
    violations = scan_text(text, Path("test.md"))
    assert any(v.code == "SP001" for v in violations), (
        f"bare *.md consult-ref inside prompt fence should flag SP001, got: {violations}"
    )


def test_d1_whole_file_prompt_md_flags_everywhere() -> None:
    """A *-prompt.md whole-file prompt flags a raw token with no fence needed."""
    text = (
        "# Opus Synthesizer Prompt Template\n"
        "apply the A→B downgrade rubric in `${CLAUDE_SKILL_DIR}/references/a-to-b-downgrade-rubric.md`.\n"
    )
    violations = scan_text(text, Path("synthesizer-prompt.md"))
    assert any(v.code == "SP001" for v in violations), (
        f"raw token in a *-prompt.md whole-file prompt should flag SP001, got: {violations}"
    )


def test_d1_body_token_outside_prompt_not_flagged() -> None:
    """A raw ${CLAUDE_SKILL_DIR} token in an ordinary (non-prompt) body must NOT flag.

    D1 is fence/`*-prompt.md`-scoped; a SKILL.md-body reference token is
    legitimate and must pass.
    """
    text = (
        "# pr-review SKILL body\n"
        "The skill directory is `${CLAUDE_SKILL_DIR}`; every reference path uses\n"
        "`${CLAUDE_SKILL_DIR}/references/foo.md`.\n"
    )
    violations = scan_text(text, Path("SKILL.md"))
    assert violations == [], (
        f"body skill-dir token outside a prompt must not flag, got: {violations}"
    )


# ---------------------------------------------------------------------------
# D2 — bare-relative Read/execute target + precise exemption
# ---------------------------------------------------------------------------


def test_d2_read_bare_relative_flags() -> None:
    """`Read ../lifecycle/references/clarify.md` flags SP002."""
    text = "Read `../lifecycle/references/clarify.md` and follow its full protocol.\n"
    violations = scan_text(text, Path("SKILL.md"))
    assert any(v.code == "SP002" for v in violations), (
        f"bare-relative Read target should flag SP002, got: {violations}"
    )


def test_d2_cat_bash_bare_relative_flags() -> None:
    """`cat skills/.../check.sh | bash` flags SP002."""
    text = "cat skills/lifecycle/references/_interactive_overnight_check.sh | bash -s -- x\n"
    violations = scan_text(text, Path("implement.md"))
    assert any(v.code == "SP002" for v in violations), (
        f"bare-relative cat|bash target should flag SP002, got: {violations}"
    )


def test_d2_exemption_resolved_sibling_prefix_passes() -> None:
    """`Read ${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` must PASS.

    The bare `../lifecycle/...` segment is carried by a resolved
    `${CLAUDE_SKILL_DIR}/../` prefix — the correct body form — so the D2
    exemption applies.
    """
    text = "Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` and follow it.\n"
    violations = scan_text(text, Path("SKILL.md"))
    assert violations == [], (
        f"${{CLAUDE_SKILL_DIR}}/../ Read form must be exempt, got: {violations}"
    )


def test_d2_exemption_resolved_owndir_prefix_passes() -> None:
    """`cat ${CLAUDE_SKILL_DIR}/references/x.sh | bash` (own-dir resolved) must PASS."""
    text = "cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- x\n"
    violations = scan_text(text, Path("implement.md"))
    assert violations == [], (
        f"${{CLAUDE_SKILL_DIR}}/ own-dir cat|bash form must be exempt, got: {violations}"
    )


def test_d2_exemption_is_precise_not_line_wide() -> None:
    """The exemption is precise: a bare ../ target on a line that merely *mentions*
    ${CLAUDE_SKILL_DIR} elsewhere is still flagged (no token-less Class-2 escape).
    """
    # The ${CLAUDE_SKILL_DIR} mention does NOT immediately prefix the bare path.
    text = "Read `../lifecycle/references/clarify.md`; the body sets `${CLAUDE_SKILL_DIR}` elsewhere.\n"
    violations = scan_text(text, Path("SKILL.md"))
    assert any(v.code == "SP002" for v in violations), (
        "a bare ../ target must still flag even when ${CLAUDE_SKILL_DIR} appears "
        f"elsewhere on the line (precise exemption), got: {violations}"
    )


# ---------------------------------------------------------------------------
# Exemptions / sentinel
# ---------------------------------------------------------------------------


def test_do_not_load_citation_not_flagged() -> None:
    """A 'do not load' markdown citation is exempt from both detectors."""
    text = (
        "The prior convention lived at `claude/reference/claude-skills.md` "
        "(do not load — historical citation, not a Read target).\n"
    )
    violations = scan_text(text, Path("SKILL.md"))
    assert violations == [], (
        f"'do not load' citation must not flag, got: {violations}"
    )


def test_tmpdir_cache_fallback_not_flagged() -> None:
    """A `:-$TMPDIR` cache fallback path in main-agent shell must NOT flag."""
    text = 'bash "${CLAUDE_SKILL_DIR:-$TMPDIR}/scripts/evidence-ground.sh" 2>/dev/null\n'
    violations = scan_text(text, Path("protocol.md"))
    assert violations == [], (
        f":-$TMPDIR cache fallback must not flag, got: {violations}"
    )


def test_sentinel_suppresses_next_content_line() -> None:
    """`<!-- skill-path-lint:ignore-next -->` suppresses the next content line."""
    text = (
        "<!-- skill-path-lint:ignore-next -->\n"
        "Read `../lifecycle/references/clarify.md` and follow it.\n"
    )
    violations = scan_text(text, Path("SKILL.md"))
    assert violations == [], (
        f"sentinel should suppress the next content line, got: {violations}"
    )


def test_sentinel_suppresses_across_blank_line() -> None:
    """Sentinel with an intervening blank line still suppresses (prev_nonblank)."""
    text = (
        "<!-- skill-path-lint:ignore-next -->\n"
        "\n"
        "Read `../lifecycle/references/clarify.md` and follow it.\n"
    )
    violations = scan_text(text, Path("SKILL.md"))
    assert violations == [], (
        f"sentinel should suppress across a blank line, got: {violations}"
    )
