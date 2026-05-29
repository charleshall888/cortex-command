# Gap 3: First-contact path frequency

How do new adopters first encounter cortex-command, and at what point do they hit cortex-init's write surface? The bootstrap-from-session case (a `/lifecycle` invocation in a brand-new repo, before terminal `cortex init` has run) is the failure mode at issue. Its severity is set by how often a real new adopter takes that path, not by whether the docs in the project root tell them not to.

There is **no telemetry** in this repo to ground a frequency claim. (`NOT_FOUND` for files containing adopter funnel data, install analytics, marketplace install counts, etc.) The findings below assemble *circumstantial* evidence — what the project tells users, what comparable tools' users actually do, what the plugin install UX surfaces — then reason about scenarios.

## Direct evidence from cortex-command docs

The project ships **two materially different canonical paths**, and they disagree about whether `cortex init` is mandatory before slash-command use:

1. **`README.md:16-31`** — Quickstart: three numbered steps. Step 3 (`cortex init`) is explicitly labeled `# 3. OPTIONAL - In each project where you want cortex active.` The README treats `cortex init` as optional.
2. **`docs/setup.md:20-22`** — Setup guide opening: *"Installation has three steps: install the CLI from a tag-pinned git URL, install the plugins from inside Claude, and run `cortex init` once per repo."* Setup.md treats `cortex init` as a required third step, not optional, and `docs/setup.md:96` calls the host-scope `allowWrite` registration *"required for any cortex workflow (lifecycle, refine, backlog, overnight, dashboard)."*
3. **`docs/index.html:6659-6671`** (deployed landing page at `charleshall888.github.io/cortex-command/`) — the "Start here" card under `cortex-core` says `/plugin install cortex-core@cortex-command` and instructs *"Run /lifecycle on a real ticket to feel the gates with you in the loop."* `cortex init` is mentioned only on the `cortex-overnight` (explicitly "optional") card with the wording *"in each repo: cortex init."*

Within cortex-core's own surfaces, the lifecycle skill has a `precondition_checks: test -d cortex/lifecycle` ([`plugins/cortex-core/skills/lifecycle/SKILL.md:15`](plugins/cortex-core/skills/lifecycle/SKILL.md)), and Step 2 invokes `cortex-lifecycle-init-ensure` ([SKILL.md:128](plugins/cortex-core/skills/lifecycle/SKILL.md)) which delegates to `cortex init --ensure` ([`cortex_command/lifecycle/init_ensure.py:124-135`](cortex_command/lifecycle/init_ensure.py)). The intent is clearly "if the user hasn't run terminal init, auto-recover" — but the auto-recover path attempts a host-scope write that the post-Feb-2026 sandbox forbids in-session ([`research.md:73`](cortex/research/cortex-init-scope-reduction/research.md), [`research.md:138`](cortex/research/cortex-init-scope-reduction/research.md)).

**The project's own canonical paths are inconsistent.** If the README and landing page win (the surfaces most adopters see first), terminal `cortex init` is *not* the canonical first action. If `docs/setup.md` wins, it is.

## Comparable-tool first-contact patterns

Surveyed in the prior research artifact ([`comparator.md:23-37`](cortex/research/cortex-init-scope-reduction/comparator.md)) and extended here:

- **Superpowers** ([`obra/superpowers`](https://github.com/obra/superpowers), verified via WebFetch): no CLI setup step. The README's "Basic Workflow" section *"jumps straight to usage, starting with the brainstorming phase when you begin a coding task,"* and the project's own statement is *"your coding agent just has Superpowers"* after `/plugin install`. First action after install is a slash command, not a terminal step.
- **ccstatusline** ([`comparator.md:27`](cortex/research/cortex-init-scope-reduction/comparator.md)): npx-launched TUI installer. Install IS the configuration step; no "run another command after install" gap.
- **ccusage** ([`comparator.md:31`](cortex/research/cortex-init-scope-reduction/comparator.md)): read-only by default; no settings write unless user opts in via a separate config step.
- **cc-statusline** ([`comparator.md:29`](cortex/research/cortex-init-scope-reduction/comparator.md)): `init` command does the config write in one step.

The cross-tool pattern: **Claude Code helpers with a "first install does CLI, then run a separate command before you can use it" gap are rare**. The dominant pattern is either (a) install IS the configuration (TUI installer), (b) install configures nothing and the tool just works (Superpowers), or (c) install and configure are bundled into one entrypoint (`init` does both). Cortex-command is in a relatively unusual position: a two-stage install (CLI + plugins) where a third stage (`cortex init`) does host-scope writes that the in-session helper cannot replicate.

WebSearch for `"Claude Code" "Superpowers" first run install discovery` surfaced multiple tutorials/blogs ([MindStudio](https://www.mindstudio.ai/blog/how-to-use-superpowers-plugin-claude-code), [Builder.io](https://www.builder.io/blog/claude-code-superpowers-plugin), [DeepWiki](https://deepwiki.com/obra/superpowers/2.1-installing-on-claude-code), [step1-install](http://superpowers-skills.com/en-us/2026/01/24/step1-install.html)) — discovery channels for comparable tools are *word-of-mouth / blog post / tutorial → /plugin install → first slash command*, with no terminal step between install and first use. Builder.io and MindStudio both report Superpowers spread via developer word-of-mouth; there is no evidence of users encountering it docs-first.

## Plugin marketplace UX

Verified live at [https://code.claude.com/docs/en/discover-plugins](https://code.claude.com/docs/en/discover-plugins) via WebFetch (2026-05-29 cache):

- `/plugin install <name>@<marketplace>` shows a **"Will install"** preview listing skills/commands/agents/hooks/MCP servers (v2.1.145+) and **"Context cost"** (v2.1.143+) before confirmation.
- The plugin manifest schema has **no field for prerequisite CLI installs or post-install setup commands**. The "Next steps" the docs show after install is to run `/<plugin-name>:<command>` — a slash command. The worked example after `/plugin install commit-commands@claude-code-plugins` is: *"Try it out by making a change to a file and running /commit-commands:commit."*
- **PostInstall lifecycle hooks are not implemented.** [Issue #11240](https://github.com/anthropics/claude-code/issues/11240) is closed as duplicate; only `SessionStart` hooks exist currently. There is no mechanism for `cortex-core` to print "now run `cortex init`" at install time.
- Trust gate is the install confirmation itself ([`comparator.md:11`](cortex/research/cortex-init-scope-reduction/comparator.md)): *"Plugins and marketplaces are highly trusted components that can execute arbitrary code on your machine."*

The cortex-core plugin manifest ([`plugins/cortex-core/.claude-plugin/plugin.json`](plugins/cortex-core/.claude-plugin/plugin.json)) is a minimal 8-line file: name, description, author. No prerequisites declared, no README pointer. The plugin does have a `SessionStart` hook ([`plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh`](plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh)) that exits silently if `cortex/lifecycle/` doesn't exist (line 25) — so a user in a brand-new repo gets **no notification at all** that they need to run `cortex init`. Discovery happens later, when `/cortex-core:lifecycle` itself fires.

**Conclusion:** Claude Code's plugin install UX gives the user zero guidance to run a terminal-init step before invoking a slash command from a freshly-installed plugin. Users who follow the marketplace's documented next-action will type `/cortex-core:lifecycle <feature>` first.

## Adopter scenarios

### (a) Power-user developer who reads `docs/setup.md` before installing

Hits `docs/setup.md:20-22` and `:94-96`. Runs the three steps in order: CLI install, `/plugin install`, `cortex init`. Terminal `cortex init` runs in a shell, outside Claude Code's sandbox, with no contradiction. First `/lifecycle` invocation lands on a fully-initialized repo. **Bootstrap-from-session does not fire for this user.** This is the documented happy path.

Plausible share of new adopters: small-but-real. Open-source helper-tool research consistently shows most adopters do NOT read setup docs end-to-end before trying the tool. ([Anecdotal — no citation; named as unknown.])

### (b) Casual user who runs `/plugin install` after seeing a tweet/blog/recommendation

Reads "install cortex-core, run `/lifecycle`" — which is literally what the deployed landing page ([`docs/index.html:6659`](docs/index.html)) and README quickstart say (`cortex init` flagged "OPTIONAL" at README.md:27). Adds the marketplace, installs cortex-core. Plugin's `SessionStart` hook ([`plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh:25`](plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh)) exits silently because no `cortex/lifecycle/` exists. They type `/cortex-core:lifecycle my-feature` in their current repo. **The lifecycle skill's `precondition_checks: test -d cortex/lifecycle` ([`SKILL.md:15`](plugins/cortex-core/skills/lifecycle/SKILL.md)) fails**, then Step 2 invokes `cortex-lifecycle-init-ensure` which delegates to `cortex init --ensure` ([`init_ensure.py:124`](cortex_command/lifecycle/init_ensure.py)) — attempting a host-scope write the sandbox now denies ([`research.md:73`](cortex/research/cortex-init-scope-reduction/research.md)). **Bootstrap-from-session fires.**

This is the user the critical review's broken-degradation argument targets.

### (c) Team member who clones a repo that already uses cortex

The repo already has `cortex/` scaffolded, `cortex/.cortex-init` marker present, `.gitignore` updated, and (if the team committed `.claude/settings.json`) project-scope marketplace entries. The host-scope `~/.claude/settings.local.json` allowWrite registration is **not committed** (it's user-local), so this user's host scope is unregistered. First `/cortex-core:lifecycle` invocation: `precondition_checks` passes (cortex/lifecycle/ exists), but `cortex-lifecycle-init-ensure` still fires per Step 2 — and detects a hash-drift (their host allowWrite is missing) and attempts the host write. **Bootstrap-from-session-equivalent fires** — same broken path as (b), with a slightly different starting state.

Per `docs/setup.md:96` the host-scope `allowWrite` is *"required for any cortex workflow"* — so this user genuinely needs the write and the project never told them to run `cortex init`. Plausibly the dominant pattern for teams adopting cortex at scale.

### (d) Someone who reads cortex-command's GitHub README and follows the quickstart

README.md:27 says `# 3. OPTIONAL - In each project where you want cortex active.` Many users will skip optional steps. After CLI install + plugin install, they jump into Claude Code and try `/lifecycle`. **Same bootstrap-from-session firing as (b).** Note the README's wording disagrees with setup.md's "required for any cortex workflow."

### Bonus: people who arrive via the deployed landing page

The landing page ([`docs/index.html`](docs/index.html)) is the largest discovery surface (linked from the README's hero badge). Its "Start here" card prescribes `/plugin install cortex-core` and "Run /lifecycle on a real ticket." `cortex init` appears only on the cortex-overnight card. A user following the landing page's prescribed sequence will hit bootstrap-from-session.

## Verdict

**Best estimate of distribution (no telemetry available; reasoned from documented paths):**

- **Docs-first adopters running terminal `cortex init` before any slash command: likely a minority.** They exist (scenario a) but the project's two highest-visibility surfaces (deployed landing page, README quickstart) do not put them on this path.
- **Plugin-install-then-slash-command adopters: likely the plurality.** Scenarios (b), (c), and (d) all converge here. The deployed landing page and the README explicitly flag `cortex init` as optional or relegate it to the overnight plugin's card.
- **Clone-existing-repo adopters: a real cohort, especially for teams adopting cortex internally.** Their `cortex/` exists but their host scope doesn't — same broken degradation path.

**The bootstrap-from-session case is not an edge case** — it is the path the deployed landing page, the README, and the lifecycle skill's own structure (precondition + `init-ensure` step) all funnel users toward. The critical review's finding (Approach D's degradation can't write host-scope but the skill's Step 2 demands the host-scope write to succeed) is a headline failure, not a corner case. The contradiction will fire on the **most common** first-contact path, not the rarest.

The size of the failure surface is amplified by the docs/landing-page/README inconsistency: setup.md says `cortex init` is required, README says optional, landing page omits it from the core path. Unless one of those is corrected as part of any rescoping work, even users who *want* to do the right thing have to pick which doc to trust.

## Open questions

1. **No marketplace install telemetry.** Anthropic's plugin marketplace does not (publicly) report install counts per plugin, much less first-action telemetry. (`NOT_FOUND` for cortex-command install counts, plugin telemetry, or adopter funnel data.)
2. **No cortex-command-side telemetry.** The repo has no analytics, no opt-in funnel events, no install ping. (`NOT_FOUND` for telemetry/analytics modules in `cortex_command/`.)
3. **No new-adopter trial data.** The auto-init-and-update spec was not validated against real new-adopter reactions ([`research.md:184`](cortex/research/cortex-init-scope-reduction/research.md) explicitly flags this as an open question).
4. **Unknown share of users who read `docs/setup.md` before installing.** This determines (a)'s share but is not measurable from inside this repo.
5. **Unknown rate at which clones (scenario c) hit the host-scope drift case.** Depends on team adoption velocity, which is unobservable.
6. **`SessionStart` hook does not surface a "run cortex init" prompt today** ([`cortex-session-start-path-bootstrap.sh:25`](plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh) silent-exits in non-cortex repos). Should a future iteration use this hook to notify users? Out of scope for this gap but worth noting as a potential mitigation.
7. **Whether the README's "OPTIONAL" framing of `cortex init` predates or postdates the auto-init-and-update spec.** If the spec promised "auto-bootstrap on first /lifecycle" and that motivated the README's OPTIONAL framing, the docs are now lying — the auto-bootstrap is broken by the post-Feb-2026 sandbox lockdown. Doc + spec audit needed.
