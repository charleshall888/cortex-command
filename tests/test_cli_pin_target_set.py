"""Target-set invariant for ``bin/cortex-rewrite-cli-pin`` (spec 378 req-11c).

The durability guard for the two-plugin CLI_PIN convergence is NOT a
point-in-time equality check between the two pins. As spec 378 req-11(c)
and the "Release race" edge case spell out, an equality check passes green
the moment both pins are converged (req-10) yet re-drifts on the very next
overnight-only release if the rewriter was left single-target. Both pins
being equal *now* tells you nothing about whether they will *stay* equal.

The load-bearing invariant is therefore structural: the rewriter's target
set MUST contain **both** pin files, so a coordinated release bumps both in
one pass. This file binds that invariant three ways:

  (i)   ``DEFAULT_TARGETS`` contains both pin paths — the req-11(i)
        membership assertion, which fails if a future edit drops a pin back
        to single-target.
  (iii) a target set with a pin absent fails the guard predicate — proving
        the guard discriminates single-target from multi-target rather than
        passing vacuously (req-11(iii)).
  behavioural: running the rewriter over its default target set against a
        fixture rewrites BOTH pin files' tags — structurally binding
        multi-targetness end-to-end, so a regression to single-target
        leaves one file unchanged and reds this test.

This is membership, not equality: the assertions stay green across future
*coordinated* bumps (both pins move to a new tag together) because they
only ever check which files are targeted, never the tag values.

Cross-refs: spec 378 req-10/req-11; ``tests/test_release_artifact_invariants.py``
(the present-tree "reads both paths" companion check).
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-rewrite-cli-pin"

#: The two plugin pin files the rewriter MUST target together. These are the
#: canonical relative paths (matched against ``DEFAULT_TARGETS`` and
#: materialized as fixtures under a tmp cwd).
OVERNIGHT_PIN = "plugins/cortex-overnight/cli_pin.py"
CORE_PIN = "plugins/cortex-core/install_core.py"

#: The target-set invariant: both pins must be members of the rewriter's
#: target set. A ``set`` (not a list) because the invariant is membership,
#: order-independent (the rewriter documents its list order as incidental).
REQUIRED_PINS = frozenset({OVERNIGHT_PIN, CORE_PIN})


def _load_script_module():
    """Load ``bin/cortex-rewrite-cli-pin`` as an importable module.

    The script has no ``.py`` extension (it is a deployed bin/ command), so
    instantiate the source-file loader explicitly — the same pattern used by
    ``tests/test_cortex_rewrite_cli_pin.py``.
    """
    loader = importlib.machinery.SourceFileLoader(
        "cortex_rewrite_cli_pin_target_set", str(SCRIPT_PATH)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


MOD = _load_script_module()


def _missing_from_target_set(targets) -> set[str]:
    """Return the required pins absent from ``targets`` (the guard predicate).

    An empty set means the target set satisfies the invariant. A non-empty
    set means the guard fails and names the un-targeted pin(s). This is the
    single decision function both the pass-case and the single-target
    fail-case assert against, so the guard's discriminating power is testable
    rather than asserted only against the happy path.
    """
    return set(REQUIRED_PINS) - set(targets)


# ---------------------------------------------------------------------------
# (i) + (iii): static target-set membership / guard discrimination
# ---------------------------------------------------------------------------


def test_default_targets_contains_both_pin_files() -> None:
    """req-11(i): the rewriter's default target set contains BOTH pin files.

    Fails if a future edit drops either pin back to single-target — the
    exact regression req-11(c) binds against.
    """
    missing = _missing_from_target_set(MOD.DEFAULT_TARGETS)
    assert missing == set(), (
        f"cortex-rewrite-cli-pin DEFAULT_TARGETS is missing required pin "
        f"file(s): {sorted(missing)!r}; the target-set invariant (spec 378 "
        f"req-11c) requires both {sorted(REQUIRED_PINS)!r}. Got "
        f"{list(MOD.DEFAULT_TARGETS)!r}."
    )


def test_single_target_set_fails_the_guard() -> None:
    """req-11(iii): a target set with a pin absent fails the guard predicate.

    Proves the guard discriminates: a single-target set (the pre-req-11(a)
    regression shape) is reported as failing, naming the un-targeted pin.
    If this ever passed for a single-target set, the guard would be vacuous.
    """
    # Overnight-only: the core pin is the one absent from the target set.
    assert _missing_from_target_set([OVERNIGHT_PIN]) == {CORE_PIN}
    # Core-only: symmetrically, the overnight pin is absent.
    assert _missing_from_target_set([CORE_PIN]) == {OVERNIGHT_PIN}
    # An empty target set fails against both.
    assert _missing_from_target_set([]) == set(REQUIRED_PINS)


# ---------------------------------------------------------------------------
# Behavioural: running the rewriter over its default set rewrites both pins
# ---------------------------------------------------------------------------


def _git_env() -> dict[str, str]:
    return {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }


def _init_repo_with_both_pins(
    tmp_path: Path, overnight_tag: str, core_tag: str
) -> None:
    """Init a tmp git repo carrying both pin fixtures, then commit them.

    ``overnight_tag`` / ``core_tag`` seed each pin's ``CLI_PIN[0]`` — passed
    distinct so that a rewrite to a third tag is observable in BOTH files
    independently (if only one file were targeted, the other keeps its seed).
    """
    env = _git_env()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)], check=True, env=env
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "commit.gpgsign", "false"],
        check=True,
        env=env,
    )
    # Overnight pin: standalone tuple module.
    overnight = tmp_path / OVERNIGHT_PIN
    overnight.parent.mkdir(parents=True, exist_ok=True)
    overnight.write_text(
        f'#: CLI pin for the overnight plugin.\nCLI_PIN = ("{overnight_tag}", "2.0")\n',
        encoding="utf-8",
    )
    # Core pin: inlined amid surrounding code (mirrors install_core.py shape).
    core = tmp_path / CORE_PIN
    core.parent.mkdir(parents=True, exist_ok=True)
    core.write_text(
        "import sys\n\n"
        "# The CLI tag this plugin installs/heals to.\n"
        f'CLI_PIN = ("{core_tag}", "2.0")\n\n'
        "def _noop():\n    return None\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "-A"], check=True, env=env
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "seed pins"],
        check=True,
        env=env,
    )


def test_rewriter_rewrites_both_pin_files(tmp_path: Path) -> None:
    """Behavioural target-set binding: default-set run rewrites BOTH pins.

    Materializes both pin files at their canonical relative paths under a tmp
    git repo, seeds them with DISTINCT tags, then runs the rewriter with NO
    ``--path`` override (so it walks ``DEFAULT_TARGETS``). Asserts both files
    now carry the new tag and neither retains its seed tag. A regression that
    dropped either file from the target set would leave that file's seed tag
    in place and red this assertion — binding multi-targetness end-to-end
    rather than only via the static membership check above.
    """
    overnight_seed = "v0.1.0"
    core_seed = "v0.2.0"
    new_tag = "v2.0.0"
    _init_repo_with_both_pins(tmp_path, overnight_seed, core_seed)

    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    env.pop("LIFECYCLE_SESSION_ID", None)
    result = subprocess.run(
        [str(SCRIPT_PATH), new_tag],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"rewriter over the default target set failed: rc={result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    overnight_after = (tmp_path / OVERNIGHT_PIN).read_text(encoding="utf-8")
    core_after = (tmp_path / CORE_PIN).read_text(encoding="utf-8")

    assert f'CLI_PIN = ("{new_tag}", "2.0")' in overnight_after, overnight_after
    assert overnight_seed not in overnight_after, (
        f"overnight pin still carries its seed tag {overnight_seed!r}: "
        f"{overnight_after!r}"
    )
    assert f'CLI_PIN = ("{new_tag}", "2.0")' in core_after, core_after
    assert core_seed not in core_after, (
        f"core pin ({CORE_PIN}) was NOT rewritten — it still carries its seed "
        f"tag {core_seed!r}, which means it was not in the rewriter's target "
        f"set (single-target regression): {core_after!r}"
    )
