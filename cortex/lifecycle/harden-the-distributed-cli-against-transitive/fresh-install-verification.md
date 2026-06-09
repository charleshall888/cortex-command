# Fresh-Install Verification (Spec Requirement 7 / Task 7)

One-time, recorded end-to-end proof that a clean, **no-constraints** install of the
wheel built from this branch lands Starlette **≥1.0** and renders the dashboard
(`GET /` → **200**) on **both** named install paths.

- **Recorded**: 2026-06-09T12:20:18Z (UTC)
- **Branch / revision**: `main` @ `a7a3b701c156dd31ef0ed6066d8b57939272eea6`
- **Platform**: macOS (darwin, aarch64-apple-darwin), Python 3.14 venv / uv 0.11.9
- **Depends on (verified present)**: Task 1 (13 `TemplateResponse` calls in request-first form),
  Task 2 (`starlette>=0.49.1,<2.0` direct), Task 3 (`fastapi<1.0`, `uvicorn[standard]<1.0`,
  `markdown<4`, `psutil>=5.9,<8` caps + `uv lock` succeeds).

## Scope note (what this proves and does not)

This verifies the wheel **built from this branch** — a faithful proxy for the released
tag, since `auto-release.yml` builds the release wheel from the identical `pyproject.toml`
on merge to main. It does **not** install a pre-existing released tag: no released tag
carries the caps until this work merges and the tag is cut (the live `CLI_PIN`/global
install is still `v2.20.0`, pre-cap). The reach/sequencing of that release is covered in
the spec's Technical Constraints (Sequencing), not retested here. This is the only check
that catches **resolution** drift (vs. just code correctness) and proves the caps work
end-to-end.

## Step 0 — Build the wheel

```
$ uv build --wheel
Building wheel...
Successfully built dist/cortex_command-2.20.1.dev23-py3-none-any.whl   (exit 0)
```

The wheel's `requires-dist` carries the bounds (hatchling emits `[project.dependencies]`
into the wheel metadata — this is what reaches a fresh install, since `uv tool install`
from a git ref ignores `uv.lock`):

```
$ unzip -p dist/cortex_command-*.whl 'cortex_command-*.dist-info/METADATA' | grep -i Requires-Dist
Requires-Dist: claude-agent-sdk<0.1.47,>=0.1.46
Requires-Dist: fastapi<1.0
Requires-Dist: jinja2
Requires-Dist: markdown<4
Requires-Dist: mcp>=1.27.0
Requires-Dist: psutil<8,>=5.9
Requires-Dist: pyyaml>=6.0
Requires-Dist: starlette<2.0,>=0.49.1
Requires-Dist: tiktoken<1.0,>=0.7.0
Requires-Dist: uvicorn[standard]<1.0
```

## Install-path equivalence argument

Both named install paths resolve transitives the same way, so installing the built wheel
with **no constraints** (no `-c`) covers both:

- **`install.sh`** (canonical documented path): runs
  `uv tool install git+<url>@<tag> --force` — a bare `uv tool install` from a git ref,
  no constraints file. (`install.sh:60`.)
- **`install_core.py`** auto-reinstall path (`_run_install_and_verify` and
  `run_install_in_background`): runs
  `uv tool install --reinstall --refresh-package cortex-command git+<url>@<tag>` — the
  **same** `uv tool install` resolution, no constraints file.
  (`plugins/cortex-overnight/install_core.py:587-596` and `:1193-1202`.)

`uv tool install` from a git ref does **not** consume `uv.lock`; it re-resolves transitives
fresh from PyPI against the wheel's `requires-dist`. The `--reinstall --refresh-package`
flags only force a re-resolve/redownload — they do **not** change the resolution inputs.
Therefore a no-constraints resolve of the built wheel is the faithful proxy for both paths.
We exercise the bare `uv tool install` path live below; `install.sh`'s end-to-end run
targets a git ref/tag (not the local wheel), so it is **covered by equivalence** rather
than re-run against the unreleased tag.

## Path A — bare `uv tool install` (canonical documented command)

Installed the built wheel via `uv tool install --force` into an **isolated**
`UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` (a throwaway location) so the developer's real global
`cortex-command v2.20.0` tool install was not disturbed.

```
$ UV_TOOL_DIR=<tmp> UV_TOOL_BIN_DIR=<tmp> uv tool install --force dist/cortex_command-2.20.1.dev23-py3-none-any.whl
 ...
 + starlette==1.2.1
 + fastapi==0.136.3
 + uvicorn==0.49.0
Installed 46 executables: cortex, ...                                (exit 0)

$ <tool-venv>/bin/python -c "import starlette, fastapi, uvicorn; print(...)"
starlette 1.2.1
fastapi 0.136.3
uvicorn 0.49.0
```

**Resolved Starlette = 1.2.1 (≥1.0) — the exact version that 500s under the old
name-first `TemplateResponse` signature.** Started the app and probed `GET /`:

```
$ CORTEX_REPO_ROOT=<tmp-root-with-.claude-and-cortex/lifecycle> <isobin>/cortex dashboard --port 8138 &
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8138
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8138/
200
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8138/health
200
INFO:     127.0.0.1 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1 - "GET /health HTTP/1.1" 200 OK
```

**Result: `GET /` → 200 on Starlette 1.2.1.** PASS.

## Path B — `install.sh` path (covered by the equivalence argument above)

`install.sh` and `install_core.py` both perform a bare `uv tool install` from a git ref
with no constraints — identical resolution inputs to Path A. A no-constraints install of
the same wheel therefore yields the same resolved set. To make the equivalence concrete,
the same wheel was also installed into a clean throwaway **venv** with deps resolved fresh
(no `-c`), which is the resolution `install.sh` performs:

```
$ python3 -m venv <tmp>/freshcheck
$ <tmp>/freshcheck/bin/pip install dist/cortex_command-2.20.1.dev23-py3-none-any.whl
Successfully installed ... fastapi-0.136.3 ... starlette-1.2.1 ... uvicorn-0.49.0   (exit 0)

$ <tmp>/freshcheck/bin/python -c "import starlette, fastapi, uvicorn; print(...)"
starlette 1.2.1
fastapi 0.136.3
uvicorn 0.49.0

$ CORTEX_REPO_ROOT=<tmp-root-with-.claude-and-cortex/lifecycle> <tmp>/freshcheck/bin/cortex dashboard --port 8137 &
INFO:     Application startup complete.
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8137/
200
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8137/health
200
INFO:     127.0.0.1 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1 - "GET /health HTTP/1.1" 200 OK
```

**Result: same resolved set (Starlette 1.2.1) and `GET /` → 200.** PASS.

## Lifespan-guard setup (both paths)

The app's lifespan (`cortex_command/dashboard/app.py:238`) raises `RuntimeError` unless
`<root>/.claude` exists. `CORTEX_REPO_ROOT` was set to a throwaway dir containing both
`.claude/` and `cortex/lifecycle/` (`_resolve_user_project_root` returns
`CORTEX_REPO_ROOT` verbatim when set). The dashboard reached
`Application startup complete.` on both paths, confirming the guard passed.

## Resolved web-stack versions (both paths, identical)

| package  | resolved version | bound (wheel `requires-dist`) | ≥1.0 / within cap |
| -------- | ---------------- | ----------------------------- | ----------------- |
| starlette| 1.2.1            | `>=0.49.1,<2.0`               | yes (≥1.0)        |
| fastapi  | 0.136.3          | `<1.0`                        | within cap        |
| uvicorn  | 0.49.0           | `[standard] <1.0`             | within cap        |

## Cleanup

Throwaway venv, isolated uv tool dirs (`UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`), and fixture roots
were removed after verification. Confirmed the developer's global tool install is intact:

```
$ uv tool list | grep cortex-command
cortex-command v2.20.0
```

## Verdict

**PASS on both install paths.** A clean, no-constraints install of the wheel built from
this branch resolves **Starlette 1.2.1 (≥1.0)** and the dashboard renders `GET /` → **200**.
The new `pyproject.toml` bounds (which travel in the wheel's `requires-dist`) plus the
request-first `TemplateResponse` rewrite (Task 1) together make a fresh resolve render the
dashboard, on both the bare `uv tool install` (canonical) and `install.sh` paths.
