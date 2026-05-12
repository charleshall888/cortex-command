# Prior Art: Distribution Models for AI Coding Frameworks — Research (April 2026)

## Summary table

| Project | Install | Modularity | Upgrade UX | Long-running story |
|---|---|---|---|---|
| **aider** | `aider-install`, `pipx`, `uv`; discourages OS package managers | Monolithic; no plugin system | `pip install -U aider-chat` | None native |
| **Continue.dev** | VSCode/JetBrains ext + Continue Hub account | Highly modular "blocks" YAML: slugs like `continue/python-expert@latest` | Hub pins by slug+version, syncs across IDEs | N/A — IDE-resident |
| **opencode (sst)** | `curl \| bash`, npm, Homebrew, Scoop, AUR; Go binary | Plugins from npm; `.opencode/plugins/` local or `~/.config/opencode/plugins/` global; MCP tools | Built-in auto-update on startup | Background tasks in TUI; no unattended runner |
| **Goose (Block)** | `curl \| bash` CLI + native desktop app | Extensions = MCP servers; "Custom Distributions" lets orgs ship preconfigured goose binaries with bundled extensions | GitHub releases; desktop app self-updates | "recipe-scanner" service + headless/server modes |
| **Cline / Roo / Kilo** | VSCode Marketplace | `.clinerules` file; Roo Mode Gallery; Kilo MCP marketplace | VSCode auto-update | IDE only |
| **Superpowers (obra)** | `/plugin install superpowers@claude-plugins-official`, or `npm i -g prpm` for Cursor | 14 discrete skills auto-trigger by context | Often automatic; reinstall pulls latest | Claims 2+ hr autonomous — but as Claude Code sessions, not a daemon |
| **Antigravity Awesome Skills** | `npx antigravity-awesome-skills` — shallow clone into `~/.gemini/antigravity/skills` | 1,400+ skills, filterable by `--category`, `--risk`, `--claude/--cursor/--gemini` | Re-run installer | N/A |
| **Claude Code plugins** | `/plugin install <name>@<marketplace>`; marketplaces = git repos with `marketplace.json` | Plugin = skills + hooks + MCP + agents | **No auto-update; reinstall pulls latest** (cited as gap) | Out of scope |
| **shadcn/ui** (cultural precedent) | `npx shadcn add <component>` — writes source into your repo | Per-component; `registry:base` ships entire design system | **You own the code** — no upgrade pressure | N/A |

## Three most instructive cases

### 1. Continue.dev — hub + local YAML blocks

Closest analogue to cortex-command's desired shape. Users sign in to Continue Hub, browse assistants/rules/prompts/tools as **versioned blocks**, compose in local `config.yaml` using slugs like `continue/python-expert@latest`. Hub edits sync; local files git-friendly.

Cleanly separates three concerns cortex conflates today:
- **Identity** (marketplace slug)
- **Composition** (the YAML)
- **Materialization** (what lands on disk)

Gap: hub "reflects immediately" — no proper version pinning ceremony. Enterprises dislike this.

### 2. Goose — "custom distributions" as first-class

Most transferable idea: **third parties can build their own preconfigured Goose distro** — a binary shipped with curated providers, extensions, branding. MCP is the extension ABI (3,000+ servers in registry by early 2026). One-liner install (`curl | bash`) or native desktop app; Desktop Extensions Manager closes discovery loop.

Splits cleanly:
- Core runtime (binary)
- Capabilities (MCP servers, dynamic)
- "Opinionated wrapper" (the distro)

### 3. shadcn/ui — "you own the code"

`npx shadcn add button` writes `components/ui/button.tsx` into your repo; **not a runtime dependency**. Trade-offs: *pro* — zero lock-in, 100% override-able; *con* — users own maintenance, no automatic bug fixes.

Claude Code's plugin marketplace is implicitly copying this: marketplaces are git repos with `marketplace.json`; "reinstalling pulls latest" — **no `npm update` equivalent**. Superpowers and Antigravity Skills both use this shape.

## Cross-cutting patterns

- **`curl | bash` is the default terminal install** (opencode, goose, aider alternate). pipx/uv secondary for Python. **No one ships primarily via Homebrew.**
- **MCP is winning as the extension ABI** for non-IDE agents (goose, opencode, Claude Code) — replacing bespoke plugin APIs.
- **"Marketplace = git repo with a manifest"** is the dominant content-distribution shape (Claude Code, Roo Mode Gallery, Antigravity, shadcn registries). Binary/runtime separate from content.
- **Auto-update split-brain**: binaries self-update (opencode, goose desktop); **content (skills, rules, plugin packs) usually does NOT** — users must reinstall. Near-universally cited as friction.
- **Modularity via named, composable units** — Continue blocks, Goose extensions, Superpowers skills, shadcn components. None ship as monolithic tarball.
- **Configuration is hierarchical and merged** — opencode: org → user → project; Continue: hub → local. Git-checkable project config is standard.

## What no one has solved well

1. **Content upgrade UX** — every git-repo-marketplace has same problem: tags move, commits don't, `reinstall` is only upgrade verb.
2. **Long-running / unattended runners as shippable artifacts** — no surveyed project packages an autonomous overnight runner. Superpowers' "2-hour runs" = Claude Code sessions, not daemons. Goose recipe-scanner closest but not "overnight mode."
3. **Bundled web dashboard** — none ships FastAPI-style dashboard. Goose has desktop UI, Continue has cloud Mission Control. No "localhost admin pane" pattern.
4. **File-state in user's own git repo** — shadcn is only one treating user's repo as destination. Every AI-agent system writes to `~/.claude/`, `~/.continue/`, `~/.config/opencode/`. **cortex-command's lifecycle/backlog/retros in-repo has essentially no prior art.**
5. **Selective sub-install** ("lifecycle skills without overnight runner") — Antigravity's `--category` is closest; still installs everything then filters. Clean "A not B" install tree is unsolved.

## Direct applicability to cortex-command

**Best-fit: Goose's "core runtime + MCP extensions + custom distributions" + Continue's hub-slug composition + shadcn's copy-paste for content layer.**

- **Skills/hooks** → shadcn/Claude-Code-plugin pattern: CLI materializes files into `~/.claude/skills/`, `~/.claude/hooks/`. User owns copies. cortex's `just setup` symlinks already do this — missing piece: package-level manifest so users pick skill packs (`cortex lifecycle`, `cortex backlog`) independently.
- **Overnight Python runner** → no prior-art match. Goose's "custom distribution" is only analogue — ship standalone installable (pipx/uv tool entry point) with own lifecycle. **Should NOT live in user's repo.**
- **FastAPI dashboard** → genuine novelty. Bundle *with* the runner, not with skills — one runtime artifact.
- **Lifecycle/backlog/retros** → in-repo content = shadcn pattern. A `cortex init` that scaffolds directories into target repo (like `npx shadcn init`) fits naturally.

**Does not map:**
- Continue Hub's cloud-sync → cortex's value is local files user controls; contradicts. Borrow the *slug* concept, not the sync.
- VSCode-marketplace-style single-extension → cortex isn't IDE extension.
- Single monolithic `curl | bash` → goose is one Go binary. cortex has 3 artifact classes (skills, Python runner, dashboard) with different lifecycles.

**Suggested three-tier shape:**
1. Claude Code plugin / skill pack for skills+hooks (shadcn-style, per-pack selectable)
2. `pipx`/`uv tool` install for overnight runner + dashboard (goose-style standalone binary lifecycle)
3. `cortex init` scaffolder that writes `lifecycle/`, `backlog/`, `retros/` templates into user's target repo (shadcn init-style)

Each tier has its own upgrade verb.

## Sources
- [aider install](https://aider.chat/docs/install.html)
- [Continue understanding configs](https://docs.continue.dev/guides/understanding-configs)
- [Continue YAML blocks](https://deepwiki.com/continuedev/continue/5.2-yaml-blocks-and-composition)
- [opencode install](https://deepwiki.com/sst/opencode/1.3-installation-and-setup)
- [Goose GitHub](https://github.com/block/goose)
- [Superpowers](https://github.com/obra/superpowers)
- [Antigravity Awesome Skills](https://github.com/sickn33/antigravity-awesome-skills)
- [shadcn/ui philosophy](https://dev.to/mechcloud_academy/shadcnui-the-component-library-that-isnt-a-library-5b94)
- [mpt.solutions plugin marketplace critique](https://www.mpt.solutions/your-claude-plugin-marketplace-needs-more-than-a-git-repo/)
