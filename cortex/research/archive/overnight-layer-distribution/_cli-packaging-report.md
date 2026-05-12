# CLI Packaging for Python+bash — Research Report (April 2026)

## Comparison table

| Format | Handles Python + bash | Deploys files outside prefix | Editable install | Upgrade UX | Example |
|---|---|---|---|---|---|
| **`uv tool install`** | Python native; bash via package_data | No (sandboxed venv); use post-install in CLI | `uv tool install -e .` works | `uv tool upgrade cortex` | aider (2025+), llm |
| **pipx** | Python native; bash via package_data | No | `pipx install -e .` | `pipx upgrade cortex` | pre-commit, llm, mitmproxy (legacy) |
| **Homebrew tap** | virtualenv_install_with_resources + bin.install | `post_install` *can* write anywhere but sandbox/superenv is hostile to $HOME; idiom is `caveats` | No editable | `brew upgrade` re-runs `post_install` (bad for ~/.claude) | llm (`simonw/homebrew-llm`) |
| **npm global** | Wrapper shim only; Python still required | `postinstall` runs as user, $HOME access (no sandbox) | N/A | `npm update -g` | claude-code itself |
| **PyInstaller / shiv / pex** | Freezes Python; bash bundled | Binary can do anything at runtime | Breaks forkability | Replace binary | mitmproxy standalone |
| **Docker** | Anything | Volume-mount; ~/.gitconfig, gh auth, gpg painful | Mount source | `docker pull` | devcontainers, sprout |

## Recommended: `curl | sh` bootstrap + `uv tool install -e .` + optional Homebrew tap

### Rationale

1. **uv is already a hard dependency** — runner shells out to `uv run`. Asking pipx to install it, then telling users to install uv separately, is silly. **aider made this exact switch in Jan 2025** and reported dependency conflicts dropped sharply.
2. **Python version pinning** — `uv tool install --python 3.12` auto-downloads interpreter. pipx can't.
3. **Editability preserved** — `uv tool install -e /path/to/clone` works today. Users `git clone`, then `uv tool install -e .` — `cortex` binary on PATH points back at their editable source. Fork-friendly preserved.
4. **Deploy-to-`~/.claude/` is solved by `cortex setup`**, not the package manager. No installer on this list reliably writes to `$HOME` safely. Homebrew's `post_install` runs on every upgrade = clobbers user edits. Keep it as an explicit CLI subcommand (it's what `just setup` is today).

### The one-liner

```
curl -fsSL https://cortex.sh/install | sh
```

Does:
1. Install `uv` if absent (official `astral.sh/uv/install.sh`)
2. `git clone https://github.com/…/cortex-command ~/.cortex`
3. `uv tool install -e ~/.cortex` → puts `cortex` on PATH
4. Run `cortex setup` → symlinks skills/hooks/bin into `~/.claude/` and `~/.local/bin/`

This is exactly Anthropic's native Claude Code installer pattern. Prior art: `rustup`, `nvm`, `uv` itself, `ollama`, `fnm`.

Homebrew tap as thin wrapper (`brew install charleshall888/cortex/cortex`): wraps same curl script in `install do system "..."` + `caveats` directing users to `cortex setup`. Gives discoverable brew entry without forcing brew into the sandbox-hostile job of writing `~/.claude/`.

### Upgrade path

`cortex upgrade` = `git -C ~/.cortex pull && cortex setup --verify-symlinks`. User edits on forks survive — they're committed to their fork's branch; git pull handles merges normally, not a package manager's blind overwrite.

## Sharp edges

- **`uv tool install` + internal `uv run`**: pipeline calls `uv run` on the *user's* project, not on itself. Tool's own venv is irrelevant to subprocess `uv run` invocations. No collision, but document so users don't `uv tool uninstall uv`.
- **Editable install quirk**: `uv sync` has removed editable installs when `[build-system]` missing ([#9518](https://github.com/astral-sh/uv/issues/9518)). Ensure `pyproject.toml` declares `[build-system]` with hatchling/setuptools.
- **Homebrew `post_install` runs on every `brew upgrade`** — if you deploy symlinks there, upgrades re-deploy + stomp user customizations. Stick to `caveats`.
- **npm postinstall + macOS**: Gatekeeper may flag unsigned bash scripts downloaded via npm. Relevant only if shipping platform binaries.
- **PyInstaller kills forkability** — wrong shape for clone/fork/edit north star.
- **Docker for overnight runner**: mounting `~/.gitconfig`, `~/.ssh`, `~/.config/gh`, `~/.gnupg` is painful; GPG signing via container especially. Skip.
- **PATH setup**: `uv tool update-shell` handles automatically; pipx requires manual `~/.local/bin` on many distros.

## Bottom line

Ship `curl | sh` bootstrap that installs `uv`, `git clone`s the repo, runs `uv tool install -e .`, executes `cortex setup`. Homebrew tap as thin wrapper for discoverability.

Fallback: `uv tool install cortex-command` on PyPI with mandatory first-run `cortex setup` that clones source to `~/.cortex` for editability.

## Sources
- [uv tool concepts](https://docs.astral.sh/uv/concepts/tools/)
- [uvx vs pipx 2026 — bswen](https://docs.bswen.com/blog/2026-03-05-uvx-vs-pipx/)
- [aider: Using uv as an installer (Jan 2025)](https://aider.chat/2025/01/15/uv.html)
- [aider installation](https://aider.chat/docs/install.html)
- [Claude Code native installer](https://claudefa.st/blog/guide/native-installer)
- [uv editable install — #5436](https://github.com/astral-sh/uv/issues/5436)
- [Homebrew Formula Cookbook](https://docs.brew.sh/Formula-Cookbook)
- [mitmproxy installation (PyInstaller)](https://docs.mitmproxy.org/stable/overview/installation/)
