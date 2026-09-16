"""A double-clickable macOS app that opens the dashboard.

The app is a compiled AppleScript applet whose whole job is running
``cortex dashboard --open``. Everything else — which projects to track,
whether a running server is stale, opening the browser — lives in that verb,
so the applet never needs rebuilding when the dashboard changes.

Two things are baked in at build time because a clicked app cannot discover
them: the absolute path to ``cortex`` (Finder-launched processes do not get
the shell's ``PATH``) and the builder's ``PATH`` for anything the dashboard
shells out to.

A stamp file in the state directory records what the app was built with. It
does two jobs: a stale stamp rebuilds the app (the ``cortex`` it names is
gone, or the applet script changed), and a stamp with no app means the
operator threw the app away, which is respected rather than undone on the
next launch.

Stdlib only — ``cortex init`` calls :func:`ensure_app` on a base install.
"""

from __future__ import annotations

import importlib.util
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP_NAME = "Cortex Dashboard"

#: Bump when the applet script or its icon changes, so existing apps rebuild.
LAUNCHER_FORMAT = "2"

#: ``CORTEX_DASHBOARD_APP=0`` disables creating or refreshing the app.
OPT_OUT_ENV = "CORTEX_DASHBOARD_APP"

_OSACOMPILE = "/usr/bin/osacompile"

#: 1024px master rendered from ``app_icon/icon.svg``. Shipped as one PNG and
#: cut into an ``.icns`` at build time with the system's ``sips`` and
#: ``iconutil``, which keeps a half-megabyte binary out of the wheel.
ICON_PNG = Path(__file__).parent / "app_icon" / "icon.png"


def app_path() -> Path:
    """Return ``~/Applications/Cortex Dashboard.app``.

    The per-user Applications folder needs no admin rights, and Spotlight and
    Launchpad index it like ``/Applications``.
    """
    return Path.home() / "Applications" / ("%s.app" % APP_NAME)


def _stamp_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME") or str(
        Path.home() / ".local" / "state"
    )
    return Path(state_home) / "cortex-command" / "dashboard-app"


def _quote(value: str) -> str:
    """Render *value* as an AppleScript string literal."""
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')


def applet_source(cortex: str, path_env: str) -> str:
    """Return the AppleScript the app runs."""
    return "\n".join(
        [
            "on run",
            "\tset cortexPath to %s" % _quote(cortex),
            "\ttry",
            '\t\tdo shell script "test -x " & quoted form of cortexPath',
            "\ton error",
            '\t\tdisplay alert "Cortex is not installed" message '
            '"This app needs the cortex command at " & cortexPath & ". '
            'Install cortex-command again, or move this app to the Trash." '
            "as critical",
            "\t\treturn",
            "\tend try",
            "\ttry",
            '\t\tdo shell script "PATH=" & quoted form of %s & " " & '
            'quoted form of cortexPath & " dashboard --open"' % _quote(path_env),
            "\ton error errMsg",
            '\t\tdisplay alert "The Cortex dashboard did not start" '
            "message errMsg as critical",
            "\tend try",
            "end run",
            "",
        ]
    )


def _run(argv: list[str]) -> None:
    subprocess.run(argv, check=True, capture_output=True, timeout=60)


def build_app(out: Path, source: str, scratch: Path) -> None:
    """Compile *source* into an applet at *out*, wearing the Cortex icon.

    The icon swap edits a signed bundle, so the bundle is re-signed ad hoc
    afterwards; an applet with a broken seal does not launch on Apple
    silicon. ``Assets.car`` and ``CFBundleIconName`` go because an asset
    catalog icon outranks ``applet.icns`` on current macOS. Raises on any
    failed step — the caller builds in a scratch directory, so a failure
    leaves the operator's existing app untouched.
    """
    _run([_OSACOMPILE, "-o", str(out), "-e", source])

    iconset = scratch / "AppIcon.iconset"
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale, suffix in ((1, ""), (2, "@2x")):
            px = str(size * scale)
            name = "icon_%dx%d%s.png" % (size, size, suffix)
            _run(["/usr/bin/sips", "-z", px, px, str(ICON_PNG),
                  "--out", str(iconset / name)])
    resources = out / "Contents" / "Resources"
    _run(["/usr/bin/iconutil", "-c", "icns", str(iconset),
          "-o", str(resources / "applet.icns")])
    (resources / "Assets.car").unlink(missing_ok=True)
    info = out / "Contents" / "Info.plist"
    plist = plistlib.loads(info.read_bytes())
    plist.pop("CFBundleIconName", None)
    info.write_bytes(plistlib.dumps(plist))
    _run(["/usr/bin/codesign", "--force", "--sign", "-", str(out)])


def ensure_app() -> str | None:
    """Create or refresh the app when it is wanted; return what happened.

    Returns ``"created"``, ``"updated"``, or ``None`` when nothing changed or
    the app does not apply here — not macOS, no dashboard extra installed, no
    ``cortex`` on ``PATH``, opted out, or removed by the operator. Never
    raises: callers are ``cortex init`` and the dashboard verb, and a missing
    shortcut must not fail either.
    """
    if sys.platform != "darwin" or os.environ.get(OPT_OUT_ENV) == "0":
        return None
    if not Path(_OSACOMPILE).exists():
        return None
    if importlib.util.find_spec("uvicorn") is None:
        return None
    target = app_path()
    stamp_path = _stamp_path()
    try:
        previous = stamp_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        previous = None

    # A built app keeps the cortex it was built with while that still runs.
    # Re-resolving on every call would repoint the app at whichever cortex ran
    # last — a repo checkout's ``uv run cortex`` included.
    kept = previous[1] if previous and len(previous) > 1 else None
    if kept is not None and not os.access(kept, os.X_OK):
        kept = None

    if target.exists():
        if previous and previous[0] == LAUNCHER_FORMAT and kept is not None:
            return None
        action = "updated"
    elif previous is not None:
        return None
    else:
        action = "created"

    cortex = kept or shutil.which("cortex")
    if cortex is None:
        return None
    stamp = "%s\n%s\n" % (LAUNCHER_FORMAT, cortex)

    source = applet_source(cortex, os.environ.get("PATH", ""))
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Compiled beside the target and swapped in, so a failed compile never
        # leaves the operator with half an app or no app.
        with tempfile.TemporaryDirectory(dir=target.parent) as scratch:
            built = Path(scratch) / target.name
            build_app(built, source, Path(scratch))
            if target.exists():
                shutil.rmtree(target)
            built.rename(target)
        stamp_path.parent.mkdir(parents=True, exist_ok=True)
        stamp_path.write_text(stamp, encoding="utf-8")
    except (OSError, subprocess.SubprocessError):
        return None
    return action
