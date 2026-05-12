# Research: Homebrew tap as thin wrapper around the curl|sh bootstrap installer (ticket 125)

## Epic Reference

This ticket is part of epic 113 (overnight-layer-distribution). Epic-level research lives at `research/overnight-layer-distribution/research.md`; the load-bearing decision records for this ticket are **DR-4** (Homebrew tap as thin wrapper), **DR-5** (`cortex setup` is canonical `~/.claude/` deployment), and **DR-8** (project.md scope update, deferred). This research scopes only to the brew tap repo, formula contents, caveats, upgrade path, and version strategy — the broader distribution decisions are not reproduced here.

## Codebase Analysis

### Files that will change

**In this repo (`cortex-command`):**
- `docs/setup.md` — add "Alternative: macOS + Homebrew" subsection under the existing Install section (currently lines 20–31). The curl one-liner is the canonical install path; brew sits next to it.
- `README.md` — add a one-line Homebrew alternative in the Quick Start install block (currently lines 74–88).

**In the new tap repo (`charleshall888/homebrew-cortex-command`, separate GitHub repo):**
- `Formula/cortex-command.rb` — the formula itself.
- `README.md` — tap-design README.
- (Optionally) `.github/workflows/audit.yml` — `brew audit --strict --tap charleshall888/cortex-command` on PR.

### Canonical install URL ticket 118 actually published

**Actual URL: `https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh`**

The ticket 125 body uses `https://cortex.sh/install` as a placeholder; ticket 118 explicitly rejected this:
> "Rejected: GitHub Pages (adds publish step, drift risk), custom domain `cortex.sh` (domain + DNS + TLS cost, no forker benefit). Recommended: keep `raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh`." — `lifecycle/ship-curl-sh-bootstrap-installer-for-cortex-command/research.md`

Verified live in:
- `docs/setup.md:27`
- `README.md:80`
- ticket 118's spec.md (R-block §"Changes to Existing Behavior"): "ADDED: `install.sh` at the repo root, served via `https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh`."

The formula must use this URL — not the placeholder.

### GitHub owner

- `git config user.name`: `charleshall888`
- `git remote -v`: `https://github.com/charleshall888/cortex-command.git`
- Tap repo per Homebrew naming requirement: `charleshall888/homebrew-cortex-command` (the `homebrew-` prefix is mandatory for the one-argument `brew tap` form per [docs.brew.sh/Taps](https://docs.brew.sh/Taps)).

### Version-surfacing patterns

- `pyproject.toml` `[project]` `version = "0.1.0"` is the single source of truth.
- Runtime version resolution: `importlib.metadata.version("cortex-command")` (used in `cortex_command.init.scaffold`).
- The CLI does not currently expose a `--version` flag (ticket 118 did not add one).
- The bootstrap installer (`install.sh`) does not embed a version — it does `git clone … && uv tool install -e --force`, so the installed CLI version is whatever's on `main` at install time.

### `install.sh` invariants from ticket 118 (relevant to formula design)

Quoted from `lifecycle/ship-curl-sh-bootstrap-installer-for-cortex-command/spec.md`:
- **R1**: POSIX sh, `set -eu`, shellcheck-clean.
- **R4**: Clone destination `${CORTEX_COMMAND_ROOT:-$HOME/.cortex}`.
- **R5**: `CORTEX_REPO_URL` env var honored; defaults to GitHub `charleshall888/cortex-command`.
- **R6**: Clone-or-pull safety: byte-identity check; abort on mismatch with remediation message; **no `rm -rf` ever**.
- **R8**: `uv tool install -e "$target" --force` (force regenerates entry points).
- **R10**: **Idempotent** — safe to re-run; `--force` on `uv tool install` is the mechanism.
- **R13**: `cortex upgrade` does `git -C cortex_root pull --ff-only` + `uv tool install -e --force`; refuses dirty trees.

The R10 idempotency guarantee is the load-bearing assumption that makes "`brew upgrade` re-runs the curl script" architecturally sound.

### Existing install documentation to update

- `docs/setup.md` (canonical install guide) lines 20–31 are the "Install" section. Currently three-step: clone, install CLI, enable plugins. Need to add brew as an alternative to step 1.
- `README.md` lines 74–88 are the Quick Start. Brew slots in next to the existing curl one-liner.

### Project.md current state and update ownership

`requirements/project.md` Out-of-Scope (lines 49–55) still reads:
> Published packages or reusable modules for others — the `cortex` CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope.

DR-8 (epic research) proposed an update to remove this clause and add an In-Scope clause for plugin + curl-installable distribution, but the update is "deferred to the epic that implements this." None of the completed sibling tickets in epic 113 (114, 115, 117, 118, 119, 120) updated project.md. **There is no specifically-scoped ticket owning the DR-8 update; this is a Spec-phase decision** (see Open Questions §6).

### Conventions to follow

- **URL stability**: the formula references the `main`-branch raw URL, matching ticket 118's deliberate non-versioning choice.
- **No `post_install` block**: explicitly avoided per DR-4 sharp edges (post_install re-runs on every brew upgrade and would clobber user customizations).
- **No `~/.claude/` writes**: the formula does not deploy any agentic config. By construction.
- **Caveats target `/plugin install` and `cortex init`** (NOT `cortex setup`): see "Ticket 117 scope-inversion correction" below. The brew formula's caveats should point users at the plugin marketplace install (skills + hooks + bin utilities) and at `cortex init` for per-repo scaffolding.

### Ticket 117 scope-inversion correction (load-bearing for caveats and tap UX)

The DR-5 framing in epic research describes `cortex setup` as the canonical `~/.claude/` deployment subcommand. **That subcommand does not exist.** Ticket 117's spec.md (`lifecycle/archive/build-cortex-setup-subcommand-and-retire-shareable-install-scaffolding/spec.md`) records an explicit "Scope inversion note": the planned `cortex setup` was found unnecessary and the ticket shipped pure retirement. Verified by inspection of `cortex_command/cli.py` — only `overnight`, `mcp-server`, `init`, `upgrade` subcommands are registered; no `setup` subparser exists. `cortex upgrade` is `git pull --ff-only && uv tool install -e --force` only — it does not touch `~/.claude/`.

The post-117 architecture is:
1. **CLI binary** — `curl | sh`, `brew install`, or `uv tool install -e .` puts `cortex` on PATH.
2. **Skills + hooks + bin utilities** — Claude Code plugins (`cortex-interactive` shipped in #120; `cortex-overnight-integration` pending in #121). User installs via `/plugin install` from inside Claude Code.
3. **Per-repo scaffolding** — `cortex init` (#119, complete) materializes `lifecycle/`, `backlog/`, `retros/`, `requirements/` into the user's working repo.

`~/.claude/{settings.json, notify.sh}` are machine-config's responsibility (separate repo). `claude/statusline.sh` stays in cortex-command but is not symlinked anywhere; users point `settings.json`'s `statusLine.command` at the absolute path. `~/.claude/CLAUDE.md` was never cortex's to manage.

**Implication for ticket 125 caveats**: do not direct users to `cortex setup` (it does not exist). Direct them at `/plugin install` (inside Claude Code) for skills/hooks, and at `cortex init` (in their working repo) for per-project scaffolding.

### Integration points

1. The formula's install block delegates entirely to `install.sh`. The formula does not implement any clone, env-var, or tool-install logic.
2. `brew upgrade` re-runs `install do`, which re-runs the curl script, which is idempotent (118 R10).
3. The formula does NOT deploy `~/.claude/`; that lives in `cortex setup` (DR-5).
4. The CLI's own `cortex upgrade` (118 R13) remains the canonical upgrade verb for fork-based or non-brew installs.

## Web Research

### Two concrete curl-wrapper tap exemplars

**1. `BenSimpsonVF/homebrew-kiro-cli-standalone`** ([repo](https://github.com/BenSimpsonVF/homebrew-kiro-cli-standalone), [formula source](https://raw.githubusercontent.com/BenSimpsonVF/homebrew-kiro-cli-standalone/main/Formula/kiro-cli-standalone.rb)) — the closest direct exemplar. Wraps the AWS-provided Kiro CLI install script. Key shape:

```ruby
class KiroCliStandalone < Formula
  desc "AI-powered CLI chat and agents (non-cask install)"
  homepage "https://kiro.dev/docs/cli/"
  license "Proprietary"
  version "latest"
  url "https://cli.kiro.dev/install-macos", using: BrowserCurlDownloadStrategy

  livecheck do
    skip "Installer endpoint is not versioned"
  end

  def install
    installer = buildpath/"install-macos"
    chmod 0755, installer
    system "bash", installer, "--prefix", prefix.to_s, "--no-shell-edit"
    # then bin.install hardlinks the binary into prefix/bin
  end

  def caveats
    <<~MSG
      Installed as 'kiro-cli-standalone'; binary remains 'kiro-cli'.
      Login: `kiro-cli login`
    MSG
  end

  test do
    system "#{bin}/kiro-cli", "--help"
  end
end
```

Critical pattern: passes `--prefix #{prefix}` so the install script lands files into the formula's keg. This is how the kiro-cli tap avoids the "Empty installation" error (see Q6 below).

**2. `Homebrew/homebrew-core` rustup formula** ([source](https://raw.githubusercontent.com/Homebrew/homebrew-core/master/Formula/r/rustup.rb)) — not a curl-wrapper (homebrew-core deliberately compiles rustup from source rather than wrapping `rustup-init.sh`), but provides the canonical `caveats` formatting reference. Confirms that **the wrapper pattern is third-party-tap territory only**; homebrew-core forbids it.

**3. Counter-exemplar — `nvm` formula in homebrew-core** is officially discouraged by nvm maintainers ([nvm#469](https://github.com/nvm-sh/nvm/issues/469), [nvm#850](https://github.com/nvm-sh/nvm/issues/850)) — cautionary tale for "tools with their own bootstrap installer also shipped via brew."

The cortex-command epic research's claim "no surveyed project ships primarily via Homebrew" is corroborated: this is a legitimate-but-uncommon pattern.

### Answers to load-bearing questions

**`brew audit` posture for taps vs core**: Tap formulae run `brew audit` with ordinary style/structure checks (RuboCop, URL format, `class Foo < Formula`). The homebrew-core-only rules — "[Acceptable Formulae](https://docs.brew.sh/Acceptable-Formulae)" — that forbid "install scripts that download unversioned things" and "tools that upgrade themselves" do **not** apply to taps. Recommended pre-release gate: `brew audit --strict --tap charleshall888/cortex-command` (no `--new-formula` flag — that's for homebrew-core submissions only).

**Pinned-version vs always-latest** ([docs.brew.sh/Versions](https://docs.brew.sh/Versions)):
| | Pinned tag | Always-latest |
|---|---|---|
| `brew upgrade` re-runs `install do` | Yes, on version/revision bump | **No** — version unchanged → upgrade skips the formula |
| sha256 verification | Required | `:no_check` or omitted |
| Maintenance | Bump per release | Zero |
| Exemplar | rustup, most core | kiro-cli-standalone |

[Versions docs](https://docs.brew.sh/Versions) state that `version :latest` casks "are excluded from automatic upgrade tracking, because there is no way to track their installed version"; the same applies to formulas using `version "latest"`.

**`brew upgrade` mechanics ([FAQ](https://docs.brew.sh/FAQ))**: brew compares installed `PkgVersion` against the available `PkgVersion` from the tap; on a version diff, the install pipeline re-runs (`install do` re-executes). If `version` doesn't change, `brew upgrade` no-ops. Revision bumps (`revision 1`) also trigger upgrade and are useful when the script changes without a semantic version bump.

**"Empty installation" error**: Homebrew checks the keg after `install do` via `Keg.new(formula.prefix).empty_installation?` and raises `Error: Empty installation` if nothing landed in the formula's prefix ([brew#2238](https://github.com/Homebrew/brew/issues/2238), [discussions#4144](https://github.com/orgs/Homebrew/discussions/4144)). If the install block runs `curl | sh` whose `uv tool install` lands the binary in `~/.local/bin/cortex` (outside the formula's prefix), the keg is empty and brew errors. Three mitigation patterns:
1. **Best (kiro-cli pattern)**: pass `--prefix #{prefix}` into `install.sh` so the script lands files into the keg. This requires `install.sh` to support a `--prefix` flag (it currently does NOT — see Open Questions §1).
2. **Placeholder file**: `(prefix/"README.brew").write "..."` writes a single file to satisfy the empty-installation check. Minimum viable hack.
3. **Shim wrapper**: write a small shell script to `#{bin}/cortex-command` that forwards to `~/.local/bin/cortex`. Brew owns the shim; the real binary is owned by `uv tool`.

**`brew uninstall` semantics**: removes the keg directory and brew-owned symlinks only. Does NOT remove files installed outside the prefix (e.g., `~/.local/bin/cortex` placed by `uv tool install`). The formula's caveats must call this out.

**`caveats` block conventions** ([Formula Cookbook](https://docs.brew.sh/Formula-Cookbook)): "In case there are specific issues with the Homebrew packaging (compared to how the software is installed from other sources) a `caveats` block can be added." Caveats display on install, on `brew info <formula>`, and (importantly) on `brew upgrade`. Anti-pattern called out in docs: "anything that is definable in documentation is not supposed to be in caveats." `cortex setup` directive fits — it's brew-packaging-specific because `~/.claude/` deployment is split out as a separate user action.

**`test do` block**: not strictly required at install time, but `brew audit --strict` flags missing tests. For a wrapper formula whose binary may live outside the Cellar, a viable test is:
```ruby
test do
  assert_match "cortex", shell_output("cortex --version 2>&1", 0)
end
```
Note: this requires the CLI to expose `--version` (currently it does not — see Open Questions §3).

**Tap repo naming** ([docs.brew.sh/Taps](https://docs.brew.sh/Taps)): "On GitHub, your repository must be named `homebrew-something` to use the one-argument form of `brew tap`. The prefix `homebrew-` is not optional." So `brew tap charleshall888/cortex-command` resolves to `https://github.com/charleshall888/homebrew-cortex-command`.

### Source URLs

- [docs.brew.sh/Taps](https://docs.brew.sh/Taps), [Formula-Cookbook](https://docs.brew.sh/Formula-Cookbook), [Acceptable-Formulae](https://docs.brew.sh/Acceptable-Formulae), [Versions](https://docs.brew.sh/Versions), [Manpage](https://docs.brew.sh/Manpage), [Brew-Livecheck](https://docs.brew.sh/Brew-Livecheck), [FAQ](https://docs.brew.sh/FAQ), [How-to-Create-and-Maintain-a-Tap](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)
- [BenSimpsonVF/homebrew-kiro-cli-standalone](https://github.com/BenSimpsonVF/homebrew-kiro-cli-standalone) — direct curl-wrapper exemplar
- [Homebrew rustup formula](https://raw.githubusercontent.com/Homebrew/homebrew-core/master/Formula/r/rustup.rb) — caveats reference
- [brew#2238](https://github.com/Homebrew/brew/issues/2238), [homebrew/discussions#4144](https://github.com/orgs/Homebrew/discussions/4144) — Empty installation error mechanics

## Requirements & Constraints

### `requirements/project.md` Out-of-Scope clause (verbatim, lines 53–54)

> Published packages or reusable modules for others — the `cortex` CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope.

This clause has not been updated; DR-8 acknowledges the conflict and proposes (deferred) removal.

### Other relevant `requirements/project.md` sections

- **Architectural Constraints**: file-based state only; per-repo sandbox registration via `cortex init` is the only write into `~/.claude/`, serialized with `fcntl.flock`.
- **Quality Attributes**: defense-in-depth for permissions; sandbox-enabled by default; conservative allow/deny lists.
- **Philosophy**: complexity must earn its place; simpler solution preferred.

`requirements/{multi-agent,observability,pipeline,remote-access}.md` — none bear directly on distribution / install paths.

### Epic 113 sibling tickets (status as of 2026-04-24)

| Ticket | Title | Status |
|---|---|---|
| 114 | Build cortex CLI skeleton with uv tool install entry point | complete |
| 115 | Rebuild overnight runner under cortex CLI | complete |
| 116 | Build MCP control-plane server with versioned runner IPC contract | in_progress |
| 117 | Build cortex setup subcommand and retire shareable-install scaffolding | complete |
| 118 | Ship curl|sh bootstrap installer for cortex-command | complete |
| 119 | Add cortex init per-repo scaffolder | complete |
| 120 | Publish cortex-interactive plugin | complete |
| 121 | Publish cortex-overnight-integration plugin | backlog |
| 122 | Publish plugin marketplace manifest | backlog |
| 123 | Lifecycle skill graceful degradation | in_progress |
| 124 | Migration guide + script for symlink-based installs | backlog |
| **125** | **Homebrew tap as thin wrapper around the curl installer** | **in_progress (this ticket)** |

Note on ticket 117 naming: 117 *built* `cortex setup` and *retired only the old `just deploy-*` scaffolding*. The `cortex setup` subcommand itself is current and canonical (DR-5).

### DR-4 (epic research, lines 274–279)

> Recommendation: **(b) `uv tool install`** wrapped in a `curl | sh` bootstrap (like `rustup`, `nvm`, `uv` itself). Homebrew tap as thin wrapper for discoverability (wraps the same curl script); Homebrew **does not own `~/.claude/` deployment**.

### DR-5 (epic research, lines 281–287) — SUPERSEDED BY TICKET 117 IMPLEMENTATION

DR-5 originally read:
> All `~/.claude/{skills,hooks,rules,reference,notify.sh,statusline.sh}` and `~/.local/bin/*` deployment happens in an explicit `cortex setup` subcommand. Separates *install the tool* (package manager's job) from *deploy config into my home* (explicit user action).

**What actually shipped**: ticket 117's spec underwent a documented scope inversion (see "Ticket 117 scope-inversion correction" in Codebase Analysis above). `cortex setup` was not built; the entire `~/.claude/` deployment surface was retired. Skills, hooks, and bin utilities ship via Claude Code plugins (`cortex-interactive` #120 complete; `cortex-overnight-integration` #121 pending). `~/.claude/{settings.json, notify.sh}` migrated to machine-config. Rules and reference files were deleted (rule content inlined into per-skill SKILL.md; reference files re-emerge as plugin references). `claude/statusline.sh` stays in this repo but is not deployed.

The architectural intent of DR-5 (separate "install tool" from "deploy config") is preserved — but the deployment now happens in three orthogonal places (CLI install / `/plugin install` / `cortex init`) rather than in a single `cortex setup` subcommand. **For ticket 125, this means caveats target `/plugin install` and `cortex init`, not `cortex setup`.**

### DR-8 (epic research, lines 299–307)

Proposed (deferred) project.md update:
- Remove "Published packages or reusable modules for others" from Out of Scope.
- Add to In Scope: "Plugin-based distribution of skills, hooks, and CLI utilities via Claude Code's plugin marketplace; `curl | sh`-installable runner CLI."
- "Deferred to the epic that implements this."

No completed sibling ticket has executed this update. Ownership is open (see Open Questions §6).

### Constraints from ticket 118 (URL contract for the brew tap)

- The bootstrap installer URL is `https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh` (stable, served from `main`).
- The script honors `CORTEX_COMMAND_ROOT` and `CORTEX_REPO_URL` env vars.
- The script is idempotent (R10) — re-running on `brew upgrade` is the supported path.
- The script does **not** accept a `--prefix` flag today (relevant to Open Questions §1).

### Architectural constraints applicable to ticket 125

1. **Formula does not own `~/.claude/`** (DR-4, DR-5). Hard constraint.
2. **No `post_install` hook** — explicitly rejected per DR-4 sharp edges.
3. **Idempotent install** via 118 R10 makes `brew upgrade` re-run safe.
4. **Three-upgrade-verb tradeoff** is acknowledged: `cortex upgrade`, `/plugin update`, `cortex init --update`. Brew upgrade is a fourth — caveats should clarify which is canonical.

## Tradeoffs & Alternatives

This ticket is simple/medium per Clarify; alternative exploration is encouraged but not required. The ticket prescribes a thin-wrapper formula in a separate repo. Research validates that prescription on most dimensions and surfaces two genuine design questions (Cellar contents, version strategy) where the ticket's framing is under-specified.

### Q1: Tap repo location

| Alt | Pros | Cons |
|---|---|---|
| **A. Separate repo `homebrew-cortex-command`** (ticket's suggestion) | Matches every surveyed analogue; unlocks short `brew tap charleshall888/cortex-command` form; `brew search` surfaces it. | Second repo to maintain; cross-repo coordination on URL changes. |
| B. Subdirectory of cortex-command | Single repo, single CI, no drift. Brew supports two-arg `brew tap user/name <git-url>` form. | Loses the short-form `brew tap` UX; users expect `homebrew-<tapname>` muscle memory. Discoverability degrades. |
| C. Submission to homebrew-core | Maximum discoverability. | Forbidden by core's "no unversioned download" / "no self-update" rules. Out of scope per ticket. |

**Recommended: A.** Convention is strong; thin wrapper has bounded maintenance cost.

### Q2: Version strategy (substantive contradiction surfaced — see Open Questions §2)

| Alt | Pros | Cons |
|---|---|---|
| A. Always-latest (`version "latest"`, no sha256) | Zero maintenance; matches ticket 118's "served from main" choice. | **`brew upgrade` no-ops** — no version diff signal. Defeats ticket scope's "brew upgrade re-runs the curl script" assumption. |
| **B. Pinned tag, bump per release** | `brew upgrade` reliably triggers re-run; brew-conventional shape. | Requires release cadence; every release needs a formula PR; defeats the "thin wrapper" framing somewhat. |
| C. Hybrid (pinned bootstrap, latest tool) | Audit-clean version metadata. | Confusing — version number doesn't mean what users expect. |

**Tradeoffs agent recommended A.** **Web agent's evidence (docs.brew.sh/Versions, FAQ) shows A breaks the upgrade contract.** This must be resolved at Spec.

### Q3: What the formula installs into the Cellar (substantive contradiction — see Open Questions §1)

| Alt | Pros | Cons |
|---|---|---|
| A. Empty Cellar | Maximally faithful to "thin wrapper." | **brew raises `Error: Empty installation`** ([brew#2238](https://github.com/Homebrew/brew/issues/2238)). Will not install. |
| B. Stub wrapper script in `bin/` | Audit-clean; brew owns a real file; uninstall removes the wrapper. | Two binaries on PATH (brew wrapper + `uv tool` real); UX friction. |
| **C. Pass `--prefix` so `install.sh` lands files into the keg** (kiro-cli pattern) | Brew owns the real binary; uninstall cleans up. Audit-clean. | Requires teaching `install.sh` to accept a `--prefix` flag (not yet implemented). |
| D. Placeholder file (`(prefix/"README.brew").write "..."`) | One-line mitigation; passes empty-installation check. | `brew uninstall` doesn't remove the real binary; surprise factor. |

Tradeoffs agent recommended A; Web agent's evidence rules A out at the brew runtime level. The viable options are B, C, D. **Resolution belongs in Spec.**

### Q4: Upgrade-path strategy

| Alt | Pros | Cons |
|---|---|---|
| **A. `brew upgrade` re-runs the curl script** (ticket's suggestion) | 118 R10 idempotency makes this safe; intuitive. | Requires version-bump signal to actually fire (see Q2). |
| B. `brew upgrade` is a no-op; users use `cortex upgrade` | Honest about the architecture. | Surprises brew-first users. |
| C. Two-step: brew upgrade shells out to `cortex upgrade` | Aligns brew with cortex semantics. | Brew sandbox may block the network/`$HOME` writes that `cortex upgrade` does — re-introduces post_install-style friction. |

**Recommended: A**, with caveats noting `cortex upgrade` is canonical for fork-based installs. Conditional on Q2 resolution.

### Q5: Caveats content depth

| Alt | Pros | Cons |
|---|---|---|
| A. One-liner | Minimal noise on every `brew install`/`upgrade`/`info`. | Misses uninstall/upgrade gotchas. |
| B. Verbose architectural lecture | Onboards brew-first users. | Noise on every upgrade. |
| **B-lite (4 lines)** | Surfaces the two real gotchas (uninstall is partial; canonical upgrade is `cortex upgrade`); links to docs for the rest. | Slight noise on repeated runs. |

**Recommended: B-lite, corrected for the post-117 architecture.** Four lines:
1. Verify install: `cortex --help`
2. To enable cortex skills + hooks: `/plugin install` from inside Claude Code (cortex-command marketplace)
3. To scaffold a project: `cortex init` in your working repo
4. Canonical CLI upgrade verb: `cortex upgrade`. Note: `brew uninstall` removes the Homebrew entry only; the cortex CLI is installed by `uv tool install` (run `uv tool uninstall cortex-command` to remove).

(Earlier draft of this research file recommended directing users at `cortex setup` — that subcommand does not exist post-117. The corrected target is `/plugin install` plus `cortex init`.)

### Q6: README scope for the tap repo

| Alt | Pros | Cons |
|---|---|---|
| A. Minimal pointer | No rot. | Dead-end for users who arrived via `brew search`. |
| B. Duplicated install instructions | Self-contained. | High rot risk; ticket explicitly disallows. |
| **C. Tap-design README (~30 lines)** | Self-contained for brew-first arrivers; explains the curl-wrapper design and uninstall gotcha. | Slightly more maintenance, but bounded. |

**Recommended: C.** Static post-launch.

### Cross-cutting recommendation

Ship as a separate repo (A1) containing a single formula whose version strategy is **TBD-Spec** (A2 vs B2 — must be decided to honor ticket scope's upgrade assumption), whose Cellar contents strategy is **TBD-Spec** (B3/C3/D3 — must mitigate empty-installation), `brew upgrade` re-runs the curl script (A4 conditional on Q2), four-line caveats (B-lite/A5) targeting `/plugin install` + `cortex init` (NOT the non-existent `cortex setup`), and a tap-design README (C6).

## Open Questions

These are the genuine open design questions that survived research. Items 1, 2, and 6 are consequential for spec; items 3, 4, 5 are smaller-scope.

- **Cellar contents (Q3)**: How does the formula avoid `Error: Empty installation`? Three viable mitigations: (B) ship a shim wrapper in `bin/`, (C) teach `install.sh` to accept a `--prefix` flag and pass `--prefix #{prefix}` from the formula, or (D) write a single placeholder file to `prefix`. C is cleanest but requires modifying `install.sh` (touches ticket 118 territory). D is the minimum-viable hack. **Deferred: will be resolved in Spec by asking the user.**

- **Version strategy (Q2)**: Always-latest (`version "latest"`) means `brew upgrade` no-ops — directly contradicts the ticket scope line "Upgrade path: `brew upgrade` re-runs the curl script." Pinned-tag fixes the contract but requires a release cadence cortex-command does not yet have. Options: (A) accept the no-op semantics and document `cortex upgrade` as the only working upgrade verb, (B) pin to a tag and bump on releases, (C) revision-bump approach (zero-version-change formula edits trigger upgrade). **Deferred: will be resolved in Spec by asking the user.**

- **CLI version flag**: The CLI does not currently expose `--version`. A `test do` block typically calls `<binary> --version`. Either (a) add `--version` to the CLI as part of this ticket's scope, (b) test something else (e.g., `cortex --help`), or (c) skip `test do` entirely and accept the audit warning. **Deferred: will be resolved in Spec by asking the user.**

- **`install.sh` URL pinning**: Ticket scope says wrap `https://cortex.sh/install`; ticket 118 actually shipped `https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh`. **Resolved**: use `https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh` per evidence in `docs/setup.md:27`, `README.md:80`, and ticket 118 spec.md.

- **Tap repo placement**: **Resolved**: separate repo at `https://github.com/charleshall888/homebrew-cortex-command` per Homebrew's mandatory `homebrew-<tapname>` naming convention.

- **Project.md DR-8 update ownership**: The Out-of-Scope clause "Published packages or reusable modules for others" still reads as before. DR-8 proposed (deferred) removal. None of the completed sibling tickets in epic 113 executed it. Options: (a) include the project.md update in this ticket's scope (one-paragraph diff), (b) defer to a separate ticket (which doesn't exist yet — would require backlog creation), (c) leave the textual conflict in place and accept the documentation drift. **Deferred: will be resolved in Spec by asking the user.**
