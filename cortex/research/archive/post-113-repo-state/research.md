# Research: Post-113 cortex-command repo state

> Topic: Audit the cortex-command repo's post-epic-113 distribution-layer state to separate intentional design choices from migration leftovers, surface inconsistencies not already covered by epic #101 children or parked #112, and identify cheap one-shot vs. ticket-worthy fixes — without pre-clustering into an omnibus cleanup epic.
>
> Discovery date: 2026-04-27. Epic #113 closed: 2026-04-27. Scope includes both `cortex-command` and `cortex-command-plugins` repos because plugins moved between them via ticket #144.

## Research Questions

1. **What is the *intended* end-state per spec, and what is the *correct* state that satisfies that intent?** → **Resolved**: end-state captured below as the baseline (Codebase Analysis §"Intended state baseline").

2. **Of the 6 enumerated post-113 observations, which are deliberate design decisions vs. coincidental migration leftovers?** → **Resolved**: 4 of 6 deliberate; 1 housekeeping debt (lifecycle-archive); **1 partially false premise resolved during critical review** (`claude/hooks/` files have mixed reference status — some are referenced only via user-global `~/.claude/settings.json` after `cortex setup`, and 2 appear to be true orphans). See §"Observation classification."

3. **Hook reference coverage — any unreferenced hook files?** → **Resolved**: all 13 files have a documented consumer. 11 are in-repo or user-global wired; 2 (`setup-github-pat.sh`, `bell.ps1`) are documented manual-wire helpers per `docs/agentic-layer.md:206,214` — not orphans. See §"Hook coverage table."

4. **Skill → bin script resolution — broken references?** → **Resolved**: zero direct breakages. Apparent gaps in cortex-overnight-integration are intentional CLI-tier delegations.

5. **Net-new inconsistencies beyond the listed 6?** → **Resolved**: 8 genuine inconsistencies surfaced (N1–N6, N8, N9). N7 resolved during investigation (legitimate manual-wire helpers, not orphans). Three (N8, N9, and the N7-investigation finding) added via critical review when the initial open scan was found to be evidence-thin.

6. **Cross-repo coherence — is the cortex-command/cortex-command-plugins split still load-bearing?** → **Resolved**: DR-9's original premise no longer carries under per-plugin install model. **User decision: Option C — sunset cortex-command-plugins.** Move android-dev-extras + cortex-dev-extras into cortex-command. See DR-1 below.

7. **Second-order effects of the new distribution model?** → **Resolved**: 5 effects identified. S1 promoted in priority because its risk window IS the project's primary use case (multi-hour overnight). See §"Second-order effects."

8. **For each genuine inconsistency, cheapest correct fix and ticket-worthiness?** → **Resolved**: feasibility table in §"Feasibility Assessment." Findings naturally split into ~3 small tickets and ~3 one-shot fixes; no omnibus epic warranted.

## Codebase Analysis

### Intended state baseline (per spec)

Distilled from `backlog/113-*.md`, `backlog/120-*.md`, `backlog/144-*.md`, `backlog/117-*.md`, `research/overnight-layer-distribution/research.md` (DR-1 through DR-10), and `CLAUDE.md`:

**Three-tier distribution model** [`backlog/113-distribute-cortex-command-as-cli-plus-plugin-marketplace.md:30,32-39`]:
- **CLI tier** — `cortex` binary via `uv tool install -e .`; owns runner, dashboard, MCP control-plane, `setup`, `init`, agent scripts.
- **Plugin tier (this repo)** — `cortex-interactive`, `cortex-overnight-integration`; plus vendored `cortex-ui-extras` and `cortex-pr-review` per #144.
- **Optional extras (separate repo)** — `cortex-command-plugins` for "truly optional per-project extras" per DR-9 [`research/overnight-layer-distribution/research.md:311`].

**Hook ownership** — four destinations [`backlog/120-cortex-interactive-plugin.md:32-38`]:
1. Project scope (`cortex-command/.claude/settings.json`): `cortex-skill-edit-advisor.sh` only (verified — see Hook coverage table).
2. cortex-overnight-integration plugin: `cortex-scan-lifecycle.sh`, `cortex-cleanup-session.sh`, `cortex-tool-failure-tracker.sh`, `cortex-permission-audit-log.sh`.
3. Machine-config / user-global (`~/.claude/settings.json` deployed by `cortex setup`): `cortex-sync-permissions.py`, `cortex-output-filter.sh`, `cortex-notify.sh`.
4. Universal/unresolved at spec time: `cortex-output-filter.sh`, `cortex-worktree-*.sh`. `cortex-validate-commit.sh` is named in spec under "Project scope" but R17 places it in the cortex-interactive plugin (current state ships via the plugin only).

**Bin ownership**:
- Top-level `bin/cortex-*` is canonical; mirrored into `plugins/cortex-interactive/bin/` via `just build-plugin` [`CLAUDE.md:18`, `justfile:447`].
- Top-level `bin/overnight-schedule` and `bin/validate-spec` are runner-tier; ship via the CLI, not a plugin [#101 epic, #112 parked].
- cortex-overnight-integration `BIN=()` is deliberate — its skills shell out to globally-installed runner scripts [`justfile:430`].

**Dual-source enforcement** — `.githooks/pre-commit` enforces a per-plugin policy: `BUILD_OUTPUT_PLUGINS={cortex-interactive, cortex-overnight-integration}` are regenerated and rebuilt-then-diffed; `HAND_MAINTAINED_PLUGINS={cortex-pr-review, cortex-ui-extras}` are excluded [`.githooks/pre-commit:99-124`, `justfile:403-404`, `backlog/144-*.md:35-37`]. **Implication for fixing N3/N4**: edits must land at canonical `skills/{lifecycle,diagnose}/SKILL.md`, not at the plugin built-output copies, or pre-commit reverts them.

**Distribution flow** — `cortex setup` deploys host-level config (including some hooks into `~/.claude/hooks/`); `cortex init` registers per-repo `lifecycle/` paths in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array; symlink-based deploy was retired in #117 [`requirements/project.md:26`, `backlog/117-*.md`].

### Observation classification

For the 6 observations enumerated in the topic:

| Observation | Classification | Rationale |
|---|---|---|
| `lifecycle/` flat with 130 dirs, no `archive/` | **Housekeeping debt** | `lifecycle-archive` recipe at `justfile:229-248` exists but has never been run. |
| `.claude/worktrees/` contains ~12 `agent-*` dirs | **Deliberate** | Created by WorktreeCreate/Remove hooks; orphans normal between sessions. |
| `claude/` reduced to `hooks/`, `statusline.sh`, `statusline.ps1` | **Deliberate** | Post-117 cleanup. (See N8 — `claude/reference/` removal not fully propagated to docs.) |
| Top-level `hooks/` AND `claude/hooks/` both as plugin source dirs | **Deliberate but unobvious** | Soft convention rather than load-bearing distinction. |
| `claude/hooks/` files some referenced, some not | **Premise was too generous** | Initial reading classified this as "False premise" based on a fabricated coverage table. Critical review found: 11/13 referenced via in-repo manifests OR user-global `~/.claude/settings.json`; 2 (`setup-github-pat.sh`, `bell.ps1`) are documented manual-wire helpers per `docs/agentic-layer.md:206,214`. All hooks have a documented consumer; the table just needed correcting. |
| `bin/` has 2 un-prefixed scripts plus `cortex-*` | **Deliberate** | Un-prefixed scripts intentionally excluded from `--include='cortex-*'` filter. |
| cortex-overnight-integration `BIN=()` empty | **Deliberate** | Skills delegate to globally-installed runner scripts. |

### Hook coverage table (corrected)

Reference categories:
- **In-repo project**: bound by `cortex-command/.claude/settings.json` (fires only when working in this repo).
- **In-repo plugin**: bound by `plugins/*/hooks/hooks.json` (ships to anyone who installs the plugin).
- **User-global**: bound by `~/.claude/settings.json` deployed by `cortex setup` (machine-config-style global hooks; verified via `~/.claude/settings.json:230,242`).
- **Data**: data file consumed at runtime by another hook script.
- **No consumer found**: post-117 orphan candidate.

| File | Reference category | Notes |
|---|---|---|
| `hooks/cortex-validate-commit.sh` | In-repo plugin | `plugins/cortex-interactive/hooks/hooks.json:9`, `justfile:426` |
| `hooks/cortex-scan-lifecycle.sh` | In-repo plugin | `plugins/cortex-overnight-integration/hooks/hooks.json:8`, `justfile:432` |
| `hooks/cortex-cleanup-session.sh` | In-repo plugin | `plugins/cortex-overnight-integration/hooks/hooks.json:18`, `justfile:432` |
| `claude/hooks/cortex-worktree-create.sh` | In-repo plugin | `plugins/cortex-interactive/hooks/hooks.json:19`, `justfile:426` |
| `claude/hooks/cortex-worktree-remove.sh` | In-repo plugin | `plugins/cortex-interactive/hooks/hooks.json:29`, `justfile:426` |
| `claude/hooks/cortex-tool-failure-tracker.sh` | In-repo plugin | overnight-plugin manifest, `justfile:432` |
| `claude/hooks/cortex-permission-audit-log.sh` | In-repo plugin | overnight-plugin manifest, `justfile:432` |
| `claude/hooks/cortex-skill-edit-advisor.sh` | In-repo project | `.claude/settings.json` PostToolUse |
| `claude/hooks/cortex-output-filter.sh` | User-global | `~/.claude/settings.json:242` PreToolUse Bash; deployed by `cortex setup`. No in-repo binding. |
| `claude/hooks/cortex-sync-permissions.py` | User-global | `~/.claude/settings.json:230` SessionStart; deployed by `cortex setup`. No in-repo binding. |
| `claude/hooks/setup-github-pat.sh` | Manual-wire helper | Documented at `docs/agentic-layer.md:206`; user wires manually per `justfile:26-62` recipe. Not auto-deployed. |
| `claude/hooks/bell.ps1` | Manual-wire helper | Documented at `docs/agentic-layer.md:214`; Windows-only visual bell. User wires manually if desired. |
| `claude/hooks/output-filters.conf` | Data | Consumed at runtime by `cortex-output-filter.sh`. |

### Skill→bin resolution

`bin/` actual contents: `cortex-audit-doc`, `cortex-count-tokens`, `cortex-create-backlog-item`, `cortex-generate-backlog-index`, `cortex-git-sync-rebase`, `cortex-jcc`, `cortex-update-item`, `overnight-schedule`, `validate-spec`. The `cortex-*` filter ships 7 into `plugins/cortex-interactive/bin/`. The 2 un-prefixed are CLI-tier (intentional).

All `cortex-*` references in cortex-interactive skills resolve via plugin-shipped binaries. `overnight-schedule` / `cortex-update-item` / `cortex-generate-backlog-index` referenced from cortex-overnight-integration's overnight skill resolve via globally-installed scripts (CLI tier prerequisite per `cortex setup`); not breakage but **not signaled** in skill docs as a prerequisite.

### Net-new inconsistencies

**N1. Orphan entries in cortex-command-plugins marketplace.json + sibling README install block**
- *Severity*: medium. Affected population is small (primarily the maintainer dogfooding); fix is cheap.
- `cortex-command-plugins/.claude-plugin/marketplace.json:8-9` lists `cortex-ui-extras` and `cortex-pr-review`; directories vendored out per #144.
- `cortex-command-plugins/README.md` (lines ~7-8 and ~27-34) advertises both plugins and includes a copy-pasteable `enabledPlugins` block — anyone following the README hits the same orphan failure mode through a different surface. (Critical-review extension.)

**N2. CI workflow validates non-existent directories**
- *Severity*: depends on CI observability — see calibration note. If CI is watched (notifications/blocked merges), high; if red badge sits unobserved, medium-cosmetic.
- `cortex-command-plugins/.github/workflows/validate.yml:22-26,31-36` runs `validate-skill.py` and call-graph guard against `plugins/cortex-ui-extras/skills` and `plugins/cortex-pr-review/skills`. Every push fails CI.

**N3. Stale `~/.claude/skills/` reference in lifecycle skill (agent-guardrail breakage)**
- *Severity*: high *for autonomous-agent decision logic*. Lifecycle SKILL.md description acts as a guardrail Claude reads when deciding whether to enter the lifecycle flow. Pointing the guardrail at a non-existent path effectively disables it for the post-113 install model.
- **Fix target**: canonical `skills/lifecycle/SKILL.md:3` (not the built-output copy at `plugins/cortex-interactive/skills/...`). Pre-commit drift enforcement reverts edits to the plugin copy. The same stale string exists at both locations under dual-source mirroring.

**N4. Stale `~/.claude/hooks/` reference in diagnose skill (cosmetic)**
- *Severity*: low. Illustrative context in human-readable docs; not consumed programmatically.
- **Fix target**: canonical `skills/diagnose/SKILL.md:148` (same dual-source caveat as N3).

**N5. Marketplace.json schema drift between repos**
- *Severity*: low (cosmetic + maintenance signal).
- `cortex-command/.claude-plugin/marketplace.json` is on the modern schema; `cortex-command-plugins/.claude-plugin/marketplace.json` is on the older minimal format. Commit `320941c` modernized cortex-command but the sibling repo wasn't updated.

**N6. lifecycle-archive recipe never run**
- *Severity*: low (housekeeping).
- `justfile:229-248` defines the recipe; `lifecycle/archive/` doesn't exist; 130 dirs at top level. Recipe works but unused.

**N7. (Investigated — RESOLVED)** Initial review flagged `setup-github-pat.sh` and `bell.ps1` as orphan candidates. Investigation found both are documented at `docs/agentic-layer.md:206,214` as legitimate manual-wire helpers (PAT setup hook + Windows visual bell). Not orphans. Folded into N9 — the only stale artifact is the symlink-based wiring instruction in `justfile:62`, not the hooks themselves.

**N8. Stale `claude/reference/` references in README and docs**
- *Severity*: low (cosmetic, but external-facing).
- `README.md:152` lists `claude/reference/` in the "What's Inside" table; `docs/overnight-operations.md:11` opens by citing `claude/reference/claude-skills.md` as the source of its progressive-disclosure model. Directory was retired in #117.
- Surfaced during critical-review.

**N9. justfile recipe still instructs users to symlink into `~/.claude/hooks/`**
- *Severity*: medium. Live operational instruction in main command runner contradicts CLAUDE.md's post-113 "no longer deploys symlinks into `~/.claude/`" invariant.
- `justfile:62` (in the `setup-github-pat` recipe) prints `ln -s $(pwd)/claude/hooks/setup-github-pat.sh ~/.claude/hooks/setup-github-pat.sh` as a follow-up step. Compounds with N7 — both involve `setup-github-pat.sh`, suggesting that hook's lifecycle is the most stale post-117.
- Surfaced during critical-review.

### DR-9 boundary check (re-examined)

DR-9 [`research/overnight-layer-distribution/research.md:311`] decided to keep cortex-command-plugins separate to host "truly optional per-project extras." DR-9's load-bearing premise was: *"absorbing extras into this repo would force global install of truly orthogonal skills (like `android-dev-extras`) on users who don't work on Android."*

**Premise check post-#144**: Claude Code plugins install per-plugin via `/plugin install <name>@<marketplace>`, not per-marketplace. A single cortex-command marketplace can list `android-dev-extras` without forcing it on anyone — exactly the model already demonstrated for `cortex-pr-review` and `cortex-ui-extras` after #144. **DR-9's original justification no longer carries** under the per-plugin install model.

This doesn't mean the split is wrong, but it means the *reason* for the split needs to be re-stated rather than assumed. Possible alternative reasons (Maintainer to validate): clearer audience signaling at marketplace level; smaller cortex-command marketplace surface for new users; preserving `cortex-command-plugins` as a third-party-friendly contribution surface. The decision and its post-#144 rationale are surfaced as DR-1 below.

### Second-order effects

**S1. MCP discovery-cache staleness across CLI upgrades — promoted**
- *Severity*: **HIGH for the project's primary use case** (multi-hour autonomous overnight runs). The cache's risk window — "MCP server runs continuously across a `cortex` CLI upgrade" — IS the operating mode the project optimizes for. Treating long-running overnight as the edge case inverted priority.
- Verified: `plugins/cortex-overnight-integration/server.py:30-32` — discovery cache populated from `cortex --print-root` on first tool call, never expires for MCP-server lifetime. Server validates `__file__` under `${CLAUDE_PLUGIN_ROOT}` at startup [`server.py:50-82`] but doesn't re-validate cached `cortex_root` on subsequent calls.
- Bounded blast radius (subprocess error, not corrupt state) per `server.py:12-14`'s zero-import architectural invariant — but mid-overnight subprocess failures kill tool calls the orchestrator depends on, with no human to triage.

**S2. Plugin-bin PATH ordering undocumented (cosmetic)**
- Low risk of collision today (cortex- prefix); no documented contract for future cases.

**S3. Cross-repo issue triage gap (process)**
- Mitigated for maintainer; relevant if/when outside contributors exist.

**S4. Marketplace versioning absent (process)**
- No plugin-version pinning; rollback is git-checkout-only.

**S5. MCP graceful-degrade — DECIDED: graceful with clear error**
- *Severity*: **medium**. The plugin ships via public marketplace; install path is one slash command. There is no "advanced user" gate.
- **Decision**: add a startup check in `plugins/cortex-overnight-integration/server.py` that detects missing `cortex` on PATH and emits a clear error pointing to install docs. Plugin should install cleanly even without the CLI tier; runtime should fail informatively when invoked, not silently with `command not found`.

## Feasibility Assessment

| # | Finding | Effort | Risks | Cheapest fix |
|---|---|---|---|---|
| N1 | cortex-command-plugins marketplace orphans + README install block | S | none | Remove the two stale entries from marketplace.json + clean the sibling README's enabledPlugins example |
| N2 | cortex-command-plugins CI validates ghost dirs | S | none | Drop the two validation steps and the call-graph step's stale args from `validate.yml` |
| N3 | Stale guardrail in lifecycle SKILL.md | S | low — must edit canonical `skills/lifecycle/SKILL.md:3`, not plugin copy | Update guardrail text to reference the actual editing surface or generalize away from `~/.claude/` |
| N4 | Stale example in diagnose SKILL.md | XS | same dual-source caveat | Edit canonical `skills/diagnose/SKILL.md:148` |
| N5 | Marketplace.json schema drift | S | none | Port modern schema to `cortex-command-plugins/.claude-plugin/marketplace.json` |
| N6 | lifecycle-archive recipe unused | S–M | medium — running across 130 dirs without dry-run could lose context | Audit recipe behavior, dry-run, archive completed-and-stale dirs; or formalize "archive on completion" lifecycle hook |
| N8 | `claude/reference/` refs in README + docs | XS | none | Two-line edit: README.md:152 and docs/overnight-operations.md:11 |
| N9 | justfile:62 still suggests symlink into ~/.claude/hooks/ | XS | none | Replace symlink instruction with the post-113 wiring guidance (direct settings.json edit or skip-if-not-wanted) |
| S1 | MCP discovery-cache staleness across CLI upgrades | M | medium for overnight workloads | Add path-existence check on cached `cortex_root` before reuse, or invalidate cache on subprocess `FileNotFoundError`. Priority HIGH given this is the primary use case. |
| S5 | MCP graceful-degrade missing | M | medium | Add a startup check in MCP server: if `cortex` not on PATH, emit a clear error pointing to install docs |
| DR-1 | DR-9 boundary — premise no longer carries | discussion | none | User decision — see Open Questions §3 |

**Groupings (emergent, post-decision)**:

- **Epic: Sunset cortex-command-plugins (DR-1 = C)** — moves android-dev-extras + cortex-dev-extras into cortex-command, then archives the sibling repo. Children:
  - Vendor android-dev-extras into `cortex-command/plugins/android-dev-extras/` (preserves Android-team upstream sync procedure)
  - Vendor cortex-dev-extras into `cortex-command/plugins/cortex-dev-extras/`
  - Add both to `cortex-command/.claude-plugin/marketplace.json` with modern schema fields
  - Verify pre-commit dual-source classification (likely `HAND_MAINTAINED_PLUGINS`, since they're externally authored or hand-maintained)
  - Archive `cortex-command-plugins` repo (or delete) once parity verified
  - This dissolves N1, N2, and N5 — they don't need separate tickets
- **One-shot cleanup in cortex-command** (no ticket needed): N3, N4, N8, N9. Small documentation/string edits; total effort < 1 hour. Edit canonical sources.
- **Standalone housekeeping (cortex-command)**: N6 (lifecycle-archive). Run it once and observe; redesign only if pain manifests (DR-2 = A).
- **High-priority fix ticket (cortex-command)**: S1 (MCP discovery-cache). Promoted; bites the primary use case.
- **Standalone ticket (cortex-command)**: S5 (MCP graceful-degrade — startup check + clear error pointing to install docs).

No omnibus epic warranted.

## Decision Records

### DR-1: Sunset cortex-command-plugins — **Decided (Option C)**

**Context**: DR-9's load-bearing premise ("absorbing extras would force global install of truly orthogonal skills") no longer carries because Claude Code plugins are install-per-plugin, not per-marketplace. After #144, `cortex-command-plugins` hosts:
- `android-dev-extras` — genuinely orthogonal to cortex-command's agentic workflow (Android-specific). #144's own scope note says it "[has a] sync-from-upstream procedure and out-of-scope Android tooling [that] don't fit cortex-command's framing."
- `cortex-dev-extras` — meta-tools (`devils-advocate`, `skill-creator`) for cortex-command development itself. Borderline whether this fits the "extras" charter.

**Decision**: Sunset cortex-command-plugins. Move both residual plugins into cortex-command and archive the sibling repo.

**Rationale**:
- DR-9's premise (per-marketplace install) was incorrect for the GA Claude Code plugin model — install is per-plugin via `/plugin install <name>@<marketplace>`.
- The recurring sync cost (N1, N2, N5, plus future drift) is the cost of *staying* split, not the cost of fixing problems that exist independent of the split.
- #144 already moved cortex-pr-review and cortex-ui-extras into cortex-command without forcing them on uninterested users — Option C just completes that trajectory.
- Single-marketplace simplifies issue triage (S3) and gives one schema/CI surface to maintain.

**Implementation outline** (becomes the "Sunset cortex-command-plugins" epic in Decompose):
1. Vendor `android-dev-extras` into `cortex-command/plugins/android-dev-extras/`. Preserve its upstream sync procedure (`HOW-TO-SYNC.md`) — this stays a hand-maintained plugin.
2. Vendor `cortex-dev-extras` into `cortex-command/plugins/cortex-dev-extras/`. Hand-maintained or build-output classification per the existing pre-commit policy.
3. Add both to `cortex-command/.claude-plugin/marketplace.json` with modern schema (`description`, `category`).
4. Add both plugin names to `HAND_MAINTAINED_PLUGINS` in `justfile:404` (or `BUILD_OUTPUT_PLUGINS` if appropriate after inspection).
5. Update `cortex-command-plugins/README.md` with a redirect notice.
6. Archive (or delete) the `cortex-command-plugins` repo on GitHub once parity is verified.
7. Update `cortex-command/README.md` plugin list to reflect the unified marketplace.

**Trade-offs accepted**:
- Loses the "third-party contribution surface" framing — but cortex-command-plugins had no third-party contributors, so this is theoretical loss only.
- One-time migration cost (~1 hour) replaces forever recurring sync cost.
- Anyone with cortex-command-plugins enabled today must re-enable from cortex-command's marketplace post-migration. Migration note in the redirect README handles this.

**Resolves**: N1, N2, N5 dissolve with the repo. DR-1 closed.

### DR-2: Should `lifecycle-archive` be promoted to a routine maintenance step?

**Context**: 130 lifecycle dirs at flat top level; archive recipe exists but unused.

**Options**:
- **A. Run it manually on completed lifecycles, periodically.** Cheapest.
- **B. Wire archival into the lifecycle "complete" phase.** Auto-move on completion + staleness threshold.
- **C. Leave alone, accept flat 130 dirs.** No value loss until 300+.

**Recommendation**: **A as a one-shot to surface whether the recipe is correct; defer B if A reveals real pain.**

## Open Questions

Only one item genuinely remains open after user decisions on DR-1, S5, and N7:

1. **`cortex-output-filter.sh` placement (deferred)** — 120 spec says "decide during spec phase" [`backlog/120-*.md:36`]. Currently deployed via user-global `~/.claude/settings.json` after `cortex setup`. Not blocking any other finding; can be revisited if/when machine-config separation becomes a priority. Out of scope for this discovery.

### Resolved during orchestrator review

- *critical-review/morning-review module-import check* → pure-markdown skills; placement already settled.
- *MCP server stale-cache risk* → verified at `server.py:30-32`; promoted to S1.
- *worktree-hook double-fire* → no double-fire risk.
- *cortex-validate-commit.sh ownership ambiguity* → current state works.

### Resolved during user decisions (this session)

- *DR-1 charter* → Option C (sunset cortex-command-plugins).
- *S5 graceful-degrade philosophy* → Graceful with clear error.
- *N7 orphan candidates* → Investigated; both files are documented manual-wire helpers per `docs/agentic-layer.md:206,214`. Not orphans. Folded into N9 cleanup.
- *N2 severity gating* → moot: under DR-1=C, the cortex-command-plugins CI workflow is deleted with the repo; severity question dissolves.

## Web & Documentation Research

Skipped — purely internal topic.

## Domain & Prior Art

Skipped — narrow tactical audit.
