"""Frontmatter byte-slice parity gate for the two lifecycle.config.md sources.

Rationale and design decision: cortex/adr/0017-reconcile-and-gate-lifecycle-
config-sources.md (ADR-0017). The lifecycle config schema lives in two
independently-maintained files in different distribution channels — the
cortex-core plugin asset ``skills/lifecycle/assets/lifecycle.config.md`` and the
CLI init template ``cortex_command/init/templates/cortex/lifecycle.config.md``.
This test fails ``just test`` / CI if their **frontmatter regions** diverge, or
if the asset loses one of the load-bearing ``backlog:`` option lines.

Why a byte-slice and not the production parser: the comparison reads raw bytes
and slices the region **between** the two ``---`` delimiters. It deliberately
does NOT route through ``cortex_command.lifecycle_config._extract_frontmatter_text``,
whose ``splitlines()`` + ``"\\n".join()`` normalizes line endings and would mask
a CRLF / trailing-newline divergence. Comparing the frontmatter region only means
the asset's body-only "Copy this file to your project root…" sentence is tolerated
for free, with no allowlist.

Two gaps a bare two-file byte compare leaves, both closed here:
  - vacuous pass if extraction returned empty for both files — the positive
    content assertion requires a non-empty region carrying the option lines;
  - convergent drift where a documenting line is deleted from *both* files at
    once (regions stay equal) — caught by the positive content assertion, and
    exercised by ``test_convergent_loss_sentinel``.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
ASSET = REPO_ROOT / "skills" / "lifecycle" / "assets" / "lifecycle.config.md"
TEMPLATE = REPO_ROOT / "cortex_command" / "init" / "templates" / "cortex" / "lifecycle.config.md"

# Load-bearing option lines the asset frontmatter must carry. Checked as
# byte-substrings (line-integrity, not bare tokens): ``# backend: none`` rather
# than a generic ``none``, and the documenting comment prose (incl. the #318
# cross-reference) so convergent comment loss from both files is caught.
_REQUIRED_OPTION_LINES = (
    b"backend: cortex-backlog",
    b"# backend: github-issues",
    b"# backend: jira",
    b"# backend: none",
    b"# instructions:",
    b"# Freeform prose hint",
    b"harden in #318",
)


def _frontmatter_region(raw: bytes) -> bytes:
    """Return the raw bytes between the opening and closing ``---`` delimiters.

    Operates on raw bytes (no line-ending normalization), so the comparison
    stays CRLF / trailing-newline sensitive. Neither file's body contains a
    ``---`` line, so the first two markers bound the frontmatter exactly.
    """
    parts = raw.split(b"---", 2)
    if len(parts) < 3:
        raise AssertionError(
            f"could not locate two '---' frontmatter delimiters (found {len(parts) - 1})"
        )
    return parts[1]


def _assert_regions_equal(asset_region: bytes, template_region: bytes) -> None:
    """Pure helper: raise AssertionError if the two byte regions differ."""
    if asset_region != template_region:
        raise AssertionError(
            f"frontmatter byte-parity mismatch: asset={len(asset_region)} bytes, "
            f"template={len(template_region)} bytes — reconcile the asset up to "
            "cortex_command/init/templates/cortex/lifecycle.config.md"
        )


def _assert_options_present(region: bytes) -> None:
    """Pure helper: raise AssertionError if the region is empty or missing a
    required ``backlog:`` option line. Shared by the positive-content test and
    the convergent-loss sentinel so the sentinel exercises the production check.
    """
    if not region.strip():
        raise AssertionError("frontmatter region is empty")
    missing = [line.decode() for line in _REQUIRED_OPTION_LINES if line not in region]
    if missing:
        raise AssertionError(f"asset frontmatter missing required option line(s): {missing}")


def test_frontmatter_byte_parity() -> None:
    """Asset and init-template frontmatter regions are byte-identical."""
    assert ASSET.is_file(), f"asset missing: {ASSET}"
    assert TEMPLATE.is_file(), f"template missing: {TEMPLATE}"
    _assert_regions_equal(_frontmatter_region(ASSET.read_bytes()), _frontmatter_region(TEMPLATE.read_bytes()))


def test_asset_frontmatter_carries_options() -> None:
    """Asset frontmatter is non-empty and carries the load-bearing option lines."""
    _assert_options_present(_frontmatter_region(ASSET.read_bytes()))


def test_divergence_sentinel() -> None:
    """Single-file divergence: mutating one region in memory fails byte-parity."""
    region = _frontmatter_region(ASSET.read_bytes())
    mutated = region + b"drift\n"
    with pytest.raises(AssertionError):
        _assert_regions_equal(mutated, region)


def test_convergent_loss_sentinel() -> None:
    """Convergent loss: deleting an option line from BOTH regions keeps them
    byte-equal (a pure two-file diff stays green) but fails the positive-content
    check — proving this is the residual case the diff misses.
    """
    asset_region = _frontmatter_region(ASSET.read_bytes())
    template_region = _frontmatter_region(TEMPLATE.read_bytes())

    def _drop_github_issues(region: bytes) -> bytes:
        return b"\n".join(line for line in region.split(b"\n") if b"# backend: github-issues" not in line)

    mutated_asset = _drop_github_issues(asset_region)
    mutated_template = _drop_github_issues(template_region)

    # (i) the positive-content check catches the convergent deletion
    with pytest.raises(AssertionError):
        _assert_options_present(mutated_asset)

    # (ii) byte-parity still PASSES on the mutated regions — the residual case
    # a pure two-file diff cannot see
    _assert_regions_equal(mutated_asset, mutated_template)
