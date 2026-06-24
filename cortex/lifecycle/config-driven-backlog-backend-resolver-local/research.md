# Research: Config-driven backlog backend (resolver, local/none routing, overnight safety) — #317

## Epic Reference

Parent epic [[315-optional-backlog-plugin-configurable-backend]]; authoritative spec `cortex/requirements/backlog.md` (gathered 2026-06-23); epic decomposition `cortex/research/backlog-optional-plugin/research.md` + `decomposed.md`. The epic makes the backlog an optional, backend-configurable capability. #317 delivers **everything that makes a config-respecting, opt-out-able, overnight-safe backlog work without any external tracker**: pieces P4 (resolver), P5 (config scaffold), P6 (consumer routing — local/none arms only), P8 (overnight refusal guard), P9 (none-backend + structural-consumer degrade), P10 (ADR-0015). Siblings: #316 (plugin extraction P1–P3, **barely started — not merged**), #318 (external GitHub-Issues best-effort arm, P7).

**Scope deltas vs the ticket body (user-decided this session):**
- The `/cortex-core:backlog` → `/cortex-backlog:backlog` **slash-rename is deferred to #316** (where the plugin that owns the new namespace is actually created). Consumer routing in #317 keeps the current `/cortex-core:backlog` namespace. Rename is cleanly separable — routing branches key on the resolved backend value, not the namespace (verified).
- The **external best-effort arm is out of scope** (#318). #317 wires only the local (`cortex-backlog`, unchanged) and `none` (skip/advisory) arms, leaving a clear placeholder for the external arm.

## Codebase Analysis

### P4 — Resolver (`cortex_command/lifecycle_config.py`)
- Reuse `_extract_frontmatter_text(text) -> str | None` (`lifecycle_config.py:29-46`). Mirror the reader shape of `read_branch_mode` (`:49-88`, returns raw string or `None`) and the default-handling of `read_commit_artifacts` (`:91-140`, scalar with sane default).
- New `resolve_backlog_backend(repo_root) -> str`: read `cortex/lifecycle.config.md` frontmatter, descend the **nested** `backlog:` mapping to `backend`, default `"cortex-backlog"` when the block/key is absent. **Net-new vs precedent:** `read_branch_mode` reads a *flat* top-level key and only guards `isinstance(parsed, dict)` at the top level (`:81`). The nested descent needs an explicit `isinstance(backlog_block, dict)` guard before `.get("backend")` or a scalar `backlog: cortex-backlog` raises `AttributeError`. (Adversarial Finding 2.)
- The existing `_main` (`:143-156`) is hardcoded to commit-artifacts — **do not reuse it**. Add a dedicated CLI module `cortex_command/lifecycle/backlog_backend_cli.py` mirroring `cortex_command/lifecycle/branch_mode_cli.py:1-52` (argparse, `_telemetry.log_invocation`, stdout = value + newline, return 0).
- Register `cortex-read-backlog-backend = "cortex_command.lifecycle.backlog_backend_cli:main"` in `pyproject.toml [project.scripts]` (pattern at `pyproject.toml:52`).
- Binstub `bin/cortex-read-backlog-backend` + mirror `plugins/cortex-core/bin/cortex-read-backlog-backend`, four-branch dual-channel wrapper (force-source → wheel-import → working-tree pyproject probe → exit 2 remediation), modeled on `cortex-read-commit-artifacts`. `chmod +x`; depends on `cortex-log-invocation` (already mirrored). **See Open Questions for the failure-contract decision (exit-2 binstub vs exit-0 console-script).**

### P5 — Config scaffold (`cortex_command/init/templates/cortex/lifecycle.config.md`)
- Current frontmatter holds flat flags (`skip-specify`, `skip-review`, `commit-artifacts`, `synthesizer_overnight_enabled`). Append a `backlog:` mapping block: `backend: cortex-backlog` (default) + commented `# backend: github-issues|jira|none` alternatives + optional freeform `instructions:` string (with a documented `github-issues` example).
- The template path is **already** in `_HASH_INPUT_TEMPLATES` (`scaffold.py:69`); editing its content auto-recomputes the init-artifacts hash via `_compute_init_artifacts_hash` (`:80-109`). No manual constant bump. `tests/test_init_artifacts_hash_inputs.py` enforces template-coverage + determinism (no edit needed unless a *new file* is added).

### Files that will change
| File | Change |
|------|--------|
| `cortex_command/lifecycle_config.py` | `+resolve_backlog_backend()` (nested-dict guarded) |
| `cortex_command/lifecycle/backlog_backend_cli.py` | new CLI module |
| `pyproject.toml` | `+[project.scripts]` entry |
| `bin/cortex-read-backlog-backend` + `plugins/cortex-core/bin/…` | new binstub + auto-swept mirror |
| `cortex_command/init/templates/cortex/lifecycle.config.md` | `+backlog:` block |
| `cortex_command/overnight/cli_handler.py` | guard helper + first-checks in `handle_prepare`/`handle_launch` |
| `cortex_command/refine.py` | `_read_backlog_frontmatter` degrade (`:34-57`) |
| `skills/lifecycle/references/backlog-writeback.md`, `skills/discovery/references/decompose.md`, `skills/discovery/SKILL.md`, `skills/refine/SKILL.md`, `skills/refine/references/clarify-critic.md`, `skills/dev/SKILL.md`, `skills/morning-review/references/walkthrough.md` (+ SKILL.md) | soft routing/degrade prose |
| `cortex/adr/0015-*.md` | new ADR |

## Web Research

Prior art converges on a clean shape (sources: OpenFeature provider model, "Provider Model = Factory+Strategy", Python registry pattern, .NET `ValidateOnStart`, the openclaw#50644 fail-closed-guard-bypass postmortem):
- **Config string → adapter via a dumb registry/factory**; keep backend-selection logic out of the registry (a resolver outputs the key, the lookup is O(1)).
- **Absent config → silent sane default; present-but-unrecognized → loud error.** Do not conflate the two (the canonical pitfall). Directly informs the resolver's malformed-case handling.
- **`none`/disabled → clean, reason-tagged no-op, never an error, never silent** (OpenFeature defines `DISABLED` as a *reason*, not an error).
- **Fail-closed guards must be fail-fast, first-check, and not satisfiable by an empty/degenerate value** — the openclaw#50644 anti-pattern: a `mode=none` made a bootstrap "succeed empty" and silently disabled an auth guard. Validate config eagerly up front.
- The Web agent argued for a **structured, observable** refusal signal over a stdout-prose advisory in unattended contexts. The adversarial pass refined this into the JSON-envelope resolution below (neither silent prose nor a registered event).

## Requirements & Constraints

From `cortex/requirements/backlog.md` (all #317 FRs):
- **Configurable backend in config** (`:28-36`, must) — `backlog:` block, `cortex-backlog` default + commented alternatives + documented external example.
- **Backend resolution config-authoritative** (`:38-46`, must) — answered by `backlog.backend`, default `cortex-backlog`; **never introspect installed plugins**; absent block ⇒ today's behavior.
- **Consumer backend routing at skill layer** (`:48-58`, must) — branch lives in skills, not CLI tools; CLI tools stay cortex-backlog-only; prose-driven, no per-tool code adapter.
- **Overnight requires `cortex-backlog`** (`:70-79`, must) — refuse non-local backend naming the configured backend; never perform external writes.
- **`none` backend behavior** (`:81-89`, should) — incidental consumers skip with one-line advisory; discovery surfaces composed bodies inline rather than failing.
- Terminology: name the local backend `cortex-backlog` consistently (not `local`) (`:104`). ADR required (`:105`).

From `cortex/requirements/project.md` / `CLAUDE.md`:
- **MUST-escalation policy** — routing prose must be soft positive-routing (no MUST/REQUIRED) absent an evidence artifact. The overnight guard is **structural control-flow**, not routing prose, so it is exempt from the prose-escalation policy (structural-separation-over-prose is the *preferred* form per CLAUDE.md).
- **Prescribe What/Why not How**; **structural separation over prose** for gates.
- **Events-registry dual-gate** (`bin/.events-registry.md` + `cortex_command/overnight/events.py:EVENT_TYPES`) fires only if a new event name is introduced — avoided by the JSON-envelope decision.
- **L1 surface ratchet** (`tests/test_l1_surface_ratchet.py`) measures frontmatter only (`description`+`when_to_use`); **body routing prose does not count** — no ratchet risk. SKILL 500-line cap applies (extract to references if a body grows).
- **ADR three-criteria gate** (`cortex/adr/README.md:19-27`) — ADR-0015 clears all three.
- **`${CLAUDE_SKILL_DIR}` invariant** — any new reference file must receive resolved absolute paths from the body.

## Overnight Safety Guard (P8) — verified

**Selection-coverage claim VERIFIED by independent trace** (adversarial Finding 1): the only two callers of `select_overnight_batch` are `handle_prepare` (`cli_handler.py:2013`) and `handle_launch` (`:2087`).
- The **runner does not re-select** — `handle_start` reads a pre-built `overnight-plan.md` (`:690`) into `runner.run(...)` (`:280-291`); `runner.py:604-608` reads `cortex/backlog/` only to *write* follow-up items, never to select.
- `handle_schedule` bootstraps a launchd job against an existing state file (`:1793-1852`); the fired job runs `start --launchd` on the already-built plan. Recovery/guardian (`recovery.py:476`) only pause/reap/report — no selection.
- **The MCP server exposes no `prepare`/`launch` tool** — `plugins/cortex-overnight/server.py:2444-2528` exposes exactly start/schedule/status/logs/cancel/list-sessions. The unattended MCP surface can only `start` a session a human already built (and guarded) via the attended `/overnight` skill.

**Reframe (correct the threat model in spec/ADR):** the guard fires on the **human-attended** `/overnight` path (the only path to selection: `skills/overnight/SKILL.md:65-68` → prepare; `references/new-session-flow.md:141-144` → launch). It prevents a human who has configured an external/`none` backend from selecting cortex-backlog items — overnight then literally cannot proceed because prepare refuses. "Fail-closed first-check" is right; "blocks a 2am autonomous external write" is not the actual mechanism.

**Implementation:** a shared first-check helper called at the top of `handle_prepare` and `handle_launch`, before `select_overnight_batch`. Resolve via `resolve_backlog_backend(repo_root)`; refuse anything not exactly `cortex-backlog`. Name the resolved variable **`backlog_backend`** — `backend` is taken by the macOS scheduler LaunchAgent at `cli_handler.py:1125` and `:1756`.

**Refusal mechanism (resolves the event-vs-prose contradiction — adversarial Finding 4):** emit a **structured JSON error envelope on stdout + non-zero exit**, matching the existing prepare/launch failure envelopes (`selection_failed`, `invalid_target_repos`, `nothing_ready` at `cli_handler.py:2098-2126`). Rationale: the guard fires *before* `bootstrap_session` creates the session dir, so no `overnight-events.log` exists yet; and `log_event` raises `ValueError` for any name not in `EVENT_TYPES` (`events.py:222-225`). The envelope is already discriminated by `overnight_start_run` (`server.py:1965-1986`) and the `/overnight` skill (`new-session-flow.md:65`) — observable on both paths without touching the events registry. This sidesteps both the prose-invisibility complaint and the no-session-log timing wall.

**Test:** new `tests/test_overnight_backlog_backend_guard.py` asserting `handle_prepare`/`handle_launch` refuse a non-cortex-backlog backend (with a JSON error envelope + non-zero exit) **before** any `select_overnight_batch`/subprocess/`gh` call; pattern in `tests/test_cortex_overnight_security.py`.

## Consumer Routing & Degrade (P6 local/none + P9)

Each consumer reads the backend by shelling `cortex-read-backlog-backend` from prose, then branches: `cortex-backlog` → existing local behavior unchanged; `none` → skip with a one-line advisory; external → placeholder noting #318. Soft positive-routing prose (no MUST). Edit points:
- **lifecycle write-back** — `skills/lifecycle/references/backlog-writeback.md:44-54` (status/phase/slug write-backs); under `none`, skip the three `cortex-update-item` calls with an advisory.
- **discovery create** — `skills/discovery/references/decompose.md:138` (+ SKILL.md); under `none`, surface composed ticket bodies inline in `decomposed.md` rather than failing (the FR's explicit requirement).
- **refine** — `skills/refine/SKILL.md:79` and the **structural** read `cortex_command/refine.py:34` `_read_backlog_frontmatter` (corrected path — *not* `skills/refine/refine.py`); plus parent-epic loading in `skills/refine/references/clarify-critic.md` (guard the section off under non-local backends).
- **dev** — `skills/dev/SKILL.md:137-166` epic-map/triage (structural; reads `cortex/backlog/index.{md,json}` + `cortex-build-epic-map`); under external/`none`, skip triage with an advisory routing the user to `/cortex-core:lifecycle`/`/cortex-core:discovery`.
- **morning-review** — `skills/morning-review/references/walkthrough.md:537-562` auto-close; under `none`, skip with a per-feature advisory. **Wrinkle:** `skills/morning-review/` mirrors to **`plugins/cortex-overnight/`** (not cortex-core) — this edit lands in a different plugin tree (adversarial Finding 7).

**CLI tools stay local-only** — `cortex-create-backlog-item`, `cortex-update-item`, `cortex-backlog-ready`, `cortex-resolve-backlog-item`, `cortex-generate-backlog-index`, `cortex-load-parent-epic`, `cortex-build-epic-map` are the local engine and gain no backend awareness.

**Structural-degrade must fail TOWARD the critical-review gate (adversarial Finding 5 — strongest):** `_read_backlog_frontmatter` already returns `("simple","medium")` when the slug is absent (`refine.py:51-57`). Reusing that default under none/external is **not a cosmetic downgrade** — the critical-review auto-trigger fires only when `tier=complex AND criticality∈{medium,high,critical}` and is skip-silent when `tier=simple` (`critical-review-gate.md:16-18`, `plan.md:263`). Defaulting to `simple` silently bypasses a safety gate. The codebase's own corrupted-state precedent (`criticality-matrix.md:34`) says unknowable tier should force review. So under none/external, refine should **fail toward review** (treat as complex/requires-review, or require the human to supply tier/criticality on the attended refine path) — not silently default to simple/medium.

## Config Scaffold, ADR & Distribution Gates (P5/P10)

- **ADR-0015** is the next free number (0014 is latest; no in-flight lifecycle claims 0015 — re-confirm at write time given parallel sessions). Clears the three-criteria gate (hard-to-reverse: config schema + per-consumer routing; surprising: why LLM-as-adapter not per-tool code; real trade-off: per-tool code adapters rejected for zero-per-tool-maintenance). `status: proposed` → `accepted` at merge. Back-pointers from `cortex/requirements/backlog.md:105` and each routing consumer (link by number, no rationale duplication).
- **Dual-source (adversarial Finding 7):** `build-plugin` auto-mirrors `bin/cortex-*` to `plugins/cortex-core/bin/` via an rsync wildcard (`justfile:619`); no array edit. The pre-commit drift gate requires **canonical + mirror to co-land in the same commit** (matches the known drift-hook/shared-checkout coupling). `test_dual_source_reference_parity.py` globs only `SKILL.md`/`references`/`assets` — no bin enumeration to update. The `pyproject.toml [project.scripts]` entry *is* required.
- **Grep-targets / events-registry tests** (`tests/test_backlog_grep_targets_resolve.py`, events-registry parity) bite only if #317 introduces a new event name in a `grep -c` Done-When or a skill-prompt event emission. The JSON-envelope decision means **no new event** → neither test is triggered.

## Open Questions

These are design decisions best made with the user in the Spec phase. Each is **Deferred: resolved in Spec** with the noted recommendation.

- **Resolver/binstub failure contract.** Should `cortex-read-backlog-backend` follow the graceful console-script pattern (`branch_mode_cli`: exit 0, empty-means-default, `command -v` probe) or the bash-binstub pattern (`cortex-read-commit-artifacts`: exit 2, empty stdout when wheel not found)? The exit-2 path breaks the "zero behavior change" claim: a consumer in a repo where the wheel resolution fails gets empty+exit2 → under `set -euo pipefail` may abort, or `""` ≠ cortex-backlog → interactive goes best-effort and overnight refuses — a regression for users who configured nothing (adversarial Finding 6). *Deferred: resolved in Spec. Recommendation:* every interactive consumer treats unresolvable-backend (empty/non-zero) as the **cortex-backlog default**, while the overnight guard treats unresolvable as **refuse**; pick the wrapper pattern that cleanly supports those two directions (favor the console-script graceful shape).
- **Present-but-unrecognized backend value.** A typo of a known value (`cortx-backlog`, `Cortex-Backlog`, `None`) should not silently become "external best-effort." *Deferred: resolved in Spec. Recommendation:* distinguish a known set (`cortex-backlog`, `none`, the external family) from an unknown value; emit a loud diagnostic (stderr interactive / JSON error overnight) for present-but-unrecognized, distinct from absent→default (per the Web + adversarial convergence).
- **refine structural-degrade direction under none/external.** *Deferred: resolved in Spec. Recommendation:* fail toward the critical-review gate (treat as complex/requires-review) rather than defaulting to simple/medium; confirm whether to require human-supplied tier/criticality on the attended path instead.
- **Overnight refusal envelope error code name.** *Deferred: resolved in Spec. Recommendation:* a versioned JSON envelope `error: "backend_not_supported"` (or similar) consistent with `selection_failed`/`nothing_ready` naming at `cli_handler.py:2098-2126`.

*(The event-vs-prose contradiction between the Web agent and the codebase/overnight agents is **resolved**, not open — the structured JSON error-envelope (Overnight Safety Guard section) satisfies both camps and is the only mechanism available at the pre-session-dir guard site.)*

## Considerations Addressed

- **Slash-rename deferred to #316; routing keeps `/cortex-core:backlog`** — Addressed: confirmed cleanly separable (routing branches on the resolved backend value, not the namespace); `cortex_command/refine.py` is a Python module and is *not* in #316's slash-rename blast radius, so no double-churn there; the prose `.md` edits are the only #316/#317 overlap and are sequenced rename-last.
- **Event vs prose for resolution/refusal** — Addressed and **upgraded**: neither — a structured JSON error envelope + non-zero exit, because the guard fires before any session log exists and `EVENT_TYPES` rejects unregistered names; observable on both attended and MCP paths. Avoids the events-registry dual-gate entirely.
- **Overnight entry points reaching `select_overnight_batch` + variable collision** — Addressed: independently verified only `handle_prepare` (`:2013`) and `handle_launch` (`:2087`) reach selection (runner/schedule/recovery/MCP do not); use variable name `backlog_backend` to avoid the scheduler `backend` at `cli_handler.py:1125,1756`.
