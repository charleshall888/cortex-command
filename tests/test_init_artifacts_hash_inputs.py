"""Contract test: init artifacts hash inputs (Task 3, Phase 1).

Enforces the spec's F10 principle: "every input that affects user-visible init
outputs must be in the hash inputs."

(a) Determinism: ``_compute_init_artifacts_hash()`` returns identical output
    across two consecutive in-process invocations AND across two subprocess
    invocations (PYTHONHASHSEED independence).
(b) Template coverage: ``_HASH_INPUT_TEMPLATES`` enumerates EVERY file under
    ``cortex_command/init/templates/cortex/**`` plus ``claude_md_authorization.md``
    — verified by ``os.walk``-ing the templates directory. Adding a new template
    without updating ``_HASH_INPUT_TEMPLATES`` fails this test.
(c) BOM-strip and trailing-newline normalization: the helper produces the same
    hash for BOM-present vs BOM-absent variants of a template.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from cortex_command.init import scaffold  # noqa: F401  (side-effect: populate _TEMPLATE_ROOT)
from cortex_command.init.scaffold import (
    _HASH_INPUT_TEMPLATES,
    _compute_init_artifacts_hash,
)

# ---------------------------------------------------------------------------
# Repository / template anchors
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATES_CORTEX_DIR = _REPO_ROOT / "cortex_command" / "init" / "templates" / "cortex"
_FENCE_TEMPLATE_NAME = "claude_md_authorization.md"


# ---------------------------------------------------------------------------
# (a) Determinism tests
# ---------------------------------------------------------------------------


def test_hash_deterministic_in_process() -> None:
    """Two consecutive in-process calls return the same hash string."""
    first = _compute_init_artifacts_hash()
    second = _compute_init_artifacts_hash()
    assert first == second, (
        f"In-process non-determinism: first={first!r}, second={second!r}"
    )


def test_hash_starts_with_v1_prefix() -> None:
    """Hash result has the documented 'v1:<hex>' shape."""
    result = _compute_init_artifacts_hash()
    assert result.startswith("v1:"), f"Expected 'v1:' prefix, got {result!r}"
    hex_part = result[3:]
    assert len(hex_part) == 64, f"Expected 64-char SHA-256 hex, got {len(hex_part)}"
    assert all(c in "0123456789abcdef" for c in hex_part), (
        f"Non-hex characters in hash: {hex_part!r}"
    )


def test_hash_deterministic_cross_process() -> None:
    """Two subprocess invocations return the same hash (PYTHONHASHSEED independence).

    Uses distinct PYTHONHASHSEED values to stress-test that the hash is not
    sensitive to Python's hash-randomization (which would indicate a set/dict
    iteration order dependency).
    """
    script = (
        "from cortex_command.init.scaffold import _compute_init_artifacts_hash; "
        "print(_compute_init_artifacts_hash())"
    )

    env_seed1 = os.environ.copy()
    env_seed1["PYTHONHASHSEED"] = "1"
    env_seed2 = os.environ.copy()
    env_seed2["PYTHONHASHSEED"] = "42"

    import subprocess

    proc1 = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env_seed1,
    )
    proc2 = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env_seed2,
    )

    assert proc1.returncode == 0, f"Subprocess 1 failed: {proc1.stderr}"
    assert proc2.returncode == 0, f"Subprocess 2 failed: {proc2.stderr}"

    hash1 = proc1.stdout.strip()
    hash2 = proc2.stdout.strip()

    assert hash1 == hash2, (
        f"Cross-process non-determinism (PYTHONHASHSEED 1 vs 42): "
        f"hash1={hash1!r}, hash2={hash2!r}"
    )


# ---------------------------------------------------------------------------
# (b) Template-coverage contract (F10 enforcement)
# ---------------------------------------------------------------------------


def _discover_template_files() -> set[str]:
    """os.walk cortex_command/init/templates/cortex/ and return POSIX-relative paths.

    The returned paths are relative to the templates/ root (i.e., prefixed
    with ``cortex/``), matching the convention in ``_HASH_INPUT_TEMPLATES``.
    Also includes the fence template (``claude_md_authorization.md``) which
    lives at the templates root, not under ``cortex/``.
    """
    templates_root = _TEMPLATES_CORTEX_DIR.parent  # cortex_command/init/templates/
    discovered: set[str] = set()

    # Walk the cortex/ subdirectory.
    for dirpath, _dirnames, filenames in os.walk(_TEMPLATES_CORTEX_DIR):
        for filename in filenames:
            abs_path = Path(dirpath) / filename
            rel = abs_path.relative_to(templates_root)
            discovered.add(rel.as_posix())

    # Add the fence template that lives at the templates/ root.
    fence_path = templates_root / _FENCE_TEMPLATE_NAME
    if fence_path.exists():
        discovered.add(_FENCE_TEMPLATE_NAME)

    return discovered


def test_hash_input_templates_covers_all_template_files() -> None:
    """_HASH_INPUT_TEMPLATES enumerates every file under templates/cortex/** + fence.

    Fails with a named diagnostic when the sets diverge — either because a new
    template was added without updating _HASH_INPUT_TEMPLATES (F10 enforcement),
    or because _HASH_INPUT_TEMPLATES lists a path that no longer exists.
    """
    discovered = _discover_template_files()
    declared = set(_HASH_INPUT_TEMPLATES)

    missing_from_declared = discovered - declared
    extra_in_declared = declared - discovered

    diagnostics: list[str] = []
    if missing_from_declared:
        diagnostics.append(
            "Templates present on disk but MISSING from _HASH_INPUT_TEMPLATES "
            "(add them to the tuple and recheck the hash):\n"
            + "\n".join(f"  - {p}" for p in sorted(missing_from_declared))
        )
    if extra_in_declared:
        diagnostics.append(
            "Paths in _HASH_INPUT_TEMPLATES that do NOT exist on disk "
            "(remove stale entries):\n"
            + "\n".join(f"  - {p}" for p in sorted(extra_in_declared))
        )

    assert not diagnostics, "\n\n".join(diagnostics)


def test_hash_input_templates_is_a_tuple() -> None:
    """_HASH_INPUT_TEMPLATES is a tuple (not a set/list) to preserve declaration order."""
    assert isinstance(_HASH_INPUT_TEMPLATES, tuple), (
        f"Expected tuple, got {type(_HASH_INPUT_TEMPLATES).__name__}"
    )


# ---------------------------------------------------------------------------
# (c) BOM-strip and trailing-newline normalization
# ---------------------------------------------------------------------------


def test_bom_strip_produces_identical_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """BOM-present and BOM-absent variants of a template produce the same hash.

    Monkeypatches the internal read path used by ``_compute_init_artifacts_hash``
    so that one template is served with a leading UTF-8 BOM (b'\\xef\\xbb\\xbf')
    and the rest are served normally.  The resulting hash must equal the hash
    produced when the same template is served without the BOM.
    """
    # Choose the first template in the list as the injection target.
    assert _HASH_INPUT_TEMPLATES, "_HASH_INPUT_TEMPLATES is unexpectedly empty"
    target_rel = _HASH_INPUT_TEMPLATES[0]

    # Read the real bytes for the target template so we can produce a BOM variant.
    from importlib.resources import files

    template_root = files("cortex_command.init.templates")
    real_bytes = template_root.joinpath(target_rel).read_bytes()
    bom_bytes = b"\xef\xbb\xbf" + real_bytes

    # Build a fake Traversable that returns BOM-prefixed bytes for the target
    # path and delegates to the real _TEMPLATE_ROOT for everything else.
    import cortex_command.init.scaffold as scaffold_mod

    original_template_root = scaffold_mod._TEMPLATE_ROOT

    class _BomTraversable:
        """Minimal Traversable wrapper that injects a BOM for one template."""

        def __init__(self, inner, inject_path: str, inject_bytes: bytes) -> None:
            self._inner = inner
            self._inject_path = inject_path
            self._inject_bytes = inject_bytes

        def joinpath(self, rel: str):
            if rel == self._inject_path:
                return _BytesLeaf(self._inject_bytes)
            return self._inner.joinpath(rel)

        # Pass-through for any other attribute access.
        def __getattr__(self, name: str):
            return getattr(self._inner, name)

    class _BytesLeaf:
        """Minimal leaf node that returns fixed bytes from read_bytes()."""

        def __init__(self, data: bytes) -> None:
            self._data = data

        def read_bytes(self) -> bytes:
            return self._data

    bom_root = _BomTraversable(original_template_root, target_rel, bom_bytes)
    monkeypatch.setattr(scaffold_mod, "_TEMPLATE_ROOT", bom_root)
    hash_with_bom = _compute_init_artifacts_hash()

    # Restore and compute hash without BOM.
    monkeypatch.setattr(scaffold_mod, "_TEMPLATE_ROOT", original_template_root)
    hash_without_bom = _compute_init_artifacts_hash()

    assert hash_with_bom == hash_without_bom, (
        f"BOM-present hash ({hash_with_bom!r}) differs from BOM-absent hash "
        f"({hash_without_bom!r}) for template {target_rel!r}. "
        f"The BOM-strip normalization is not working correctly."
    )


def test_trailing_newline_normalize_produces_identical_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extra trailing newlines are normalized to a single trailing newline.

    Serves one template with extra trailing whitespace/newlines and verifies
    the hash equals the hash produced from the same template with exactly one
    trailing newline.
    """
    assert _HASH_INPUT_TEMPLATES, "_HASH_INPUT_TEMPLATES is unexpectedly empty"
    target_rel = _HASH_INPUT_TEMPLATES[0]

    from importlib.resources import files

    template_root = files("cortex_command.init.templates")
    real_bytes = template_root.joinpath(target_rel).read_bytes()

    # Produce a variant with extra trailing newlines.
    stripped = real_bytes.rstrip(b"\n")
    extra_trailing_bytes = stripped + b"\n\n\n"

    import cortex_command.init.scaffold as scaffold_mod

    original_template_root = scaffold_mod._TEMPLATE_ROOT

    class _LeafOverride:
        def __init__(self, inner, inject_path: str, inject_bytes: bytes) -> None:
            self._inner = inner
            self._inject_path = inject_path
            self._inject_bytes = inject_bytes

        def joinpath(self, rel: str):
            if rel == self._inject_path:
                return _BytesLeaf(self._inject_bytes)
            return self._inner.joinpath(rel)

        def __getattr__(self, name: str):
            return getattr(self._inner, name)

    class _BytesLeaf:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read_bytes(self) -> bytes:
            return self._data

    extra_root = _LeafOverride(original_template_root, target_rel, extra_trailing_bytes)
    monkeypatch.setattr(scaffold_mod, "_TEMPLATE_ROOT", extra_root)
    hash_with_extra = _compute_init_artifacts_hash()

    monkeypatch.setattr(scaffold_mod, "_TEMPLATE_ROOT", original_template_root)
    hash_without_extra = _compute_init_artifacts_hash()

    assert hash_with_extra == hash_without_extra, (
        f"Hash with extra trailing newlines ({hash_with_extra!r}) differs from "
        f"canonical hash ({hash_without_extra!r}) for template {target_rel!r}. "
        f"The trailing-newline normalization is not working correctly."
    )
