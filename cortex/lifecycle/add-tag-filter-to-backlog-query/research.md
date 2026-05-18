# Research: Add `--tag` filter to `cortex-backlog-ready`

## Codebase Analysis

### Files that will change

**Primary implementation**:
- `cortex/backlog/ready.py` — canonical CLI script. Add `--tag` to `_parse_args` (line 375-392); thread filter into `_build_result` (line 307); apply filter to `records` (and to ineligible projection — see Open Questions). The `_item_payload` projection (line 139-148) does NOT currently include `tags` — keeping `tags` out of wire output preserves the existing snapshot fixture for non-`--tag` runs.

**Tests**:
- Either extend `tests/test_backlog_ready_render.py` (the only existing CLI integration test for `cortex-backlog-ready`; reusable fixture infrastructure: `_FIXTURE_RECORDS`, `_write_md`, `_build_fixture_backlog`, `_run_script`) or add a new `tests/test_backlog_ready_tag_filter.py` sibling file. See Tradeoffs Axis 5 for the recommendation.

**Upstream spec text edit (DECISION POINT — see Open Questions)**:
- `cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` line 44 — Req 15's literal acceptance grep currently reads `cortex-backlog list --tag phase2-trigger | grep -c "discovery-output-density" ≥ 1`. No `cortex-backlog list` CLI exists today. Two paths:
  1. Update Req 15's grep to reference `cortex-backlog-ready --tag phase2-trigger` (one-line spec amendment; in-spec per the original spec's permissive escape-hatch language).
  2. Create a new `cortex-backlog` umbrella CLI with `list --tag` subcommand (significant new surface — new `[project.scripts]` entry, new bin shim, new mirror).
- `cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md` lines 85-88 already record this gap.

**No changes required (verified)**:
- `cortex_command/backlog/generate_index.py` line 177 already does `"tags": _parse_inline_str_list(fm.get("tags", "[]"))` — `index.json` already carries `tags` for every active item. Confirmed by inspecting `cortex/backlog/index.json` for ticket #232 (`"tags": ["phase2-trigger"]`).
- `bin/cortex-backlog-ready` and `plugins/cortex-core/bin/cortex-backlog-ready` are pass-through bash shims (`exec ... "$@"`); no changes to either.

### Relevant existing patterns

- **Argparse pattern**: `_parse_args` uses `argparse.ArgumentParser` with `action="store_true"` for `--include-blocked`. For `--tag`, the closest in-house precedent is `cortex_command/cli.py:590` (`list_sessions --status`), which uses `action="append"` (repeatable, OR semantics on the status values).
- **Stdlib-only**: `cortex/backlog/ready.py` has no external dependencies; preserve that.
- **Read-only over `index.json`**: the script is described as "a lightweight read-only JSON emitter" (lines 60-65). Filter preserves this; no writes.
- **JSON error contract**: existing pattern uses `_emit_error(reason)` returning exit 1 with `{"error": ..., "schema_version": 1}`. Malformed `--tag` input should route through the same path.
- **Wire-format pruning**: `_item_payload` deliberately projects a narrow subset. Tags are filter-input not output — keeping them out of wire output preserves the existing snapshot.
- **Filter placement**: apply inside `_build_result` (line 307) before `partition_ready`, OR after partition but before `_group_by_priority`. Pre-partition is fewer code touches.

### Integration points and dependencies

- **Downstream consumers of `cortex-backlog-ready`** (all unaffected by an opt-in `--tag` flag — they never pass it):
  - `skills/backlog/SKILL.md` lines 82, 99 (`/cortex-core:backlog pick` and `/cortex-core:backlog ready`).
  - No dashboard, hook, or overnight runner code consumes this script.
- **`bin/cortex-check-parity`**: parity is enforced on the script *name*, not its arg surface. `cortex-backlog-ready` is already wired via `skills/backlog/SKILL.md` inline-code references. No new allowlist entry needed.
- **Dual-source mirror**: `bin/cortex-backlog-ready` is canonical; `plugins/cortex-core/bin/cortex-backlog-ready` is the auto-mirrored copy. Pre-commit hook syncs the mirror. Since the shim is unchanged, no manual mirror edit is needed.

### Conventions to follow

- New events (if any) register in `bin/.events-registry.md`. This change introduces no new events.
- Soft positive-routing phrasing per the MUST-escalation policy — no MUST/CRITICAL escalation without recorded effort=high failure evidence.
- Solution Horizon: a `cortex-backlog` umbrella router for a single flag fails the durability test unless 2+ subcommands are named follow-ups. Currently only one is wanted.

## Web Research

### Argparse repeatable list patterns

- Canonical Python idiom for `--tag X --tag Y` is `action="append"` with `default=None` (then `args.tag = args.tag or []` in code). Avoid `default=[]` — per [Python bug 16399](https://bugs.python.org/issue16399), parsed values append after the default, and a mutable default is shared across parser instances.
- `nargs="+"` collects multiple values in one invocation (`--tag X Y Z`) but cannot be repeated cleanly. Subtle bug magnet: `--tag phase2-trigger --include-blocked` would consume `--include-blocked` as a tag value.
- `action="extend"` (Python 3.8+) with `nargs="+"` flattens but does not support the repeat-the-flag idiom on its own.

### AND vs OR semantics across comparable tools

| Tool | Multi-value behavior | Default |
|---|---|---|
| `gh issue list --label foo --label bar` | AND | AND |
| `docker ps --filter label=a --filter label=b` | AND (mostly) | AND |
| Taskwarrior `+tag1 +tag2` | AND; explicit `or` keyword for disjunction | AND |
| Jira JQL `labels = a AND labels = b` | Explicit boolean | n/a |
| Pytest `-m "slow and db"` / `-m "slow or db"` | Boolean expression language | explicit |

**External convention**: AND prevails in modern CLIs (gh, docker, taskwarrior) for repeated `--label`/`--tag`/`--filter` flags. OR is offered via comma-delimited single value, separate search surface, or explicit boolean syntax.

**In-house convention**: `cortex_command/cli.py:590` (`list_sessions --status`) uses **OR** semantics for a repeatable filter. This contradicts the external convention and is the closest in-house precedent. See Open Questions.

### Case sensitivity

[Jekyll #2977](https://github.com/jekyll/jekyll/issues/2977) and [jekyll-archives #43](https://github.com/jekyll/jekyll-archives/issues/43) document real data-loss bugs from case-sensitive tag matching in user-authored YAML frontmatter. Case-insensitive matching is the safer default for human-authored tags.

### Exit code on zero results

GNU grep convention: exit 0 = matches, exit 1 = no matches, exit 2 = error. ripgrep/fd follow this. Modern list tools (`gh issue list`, `kubectl get`) instead exit 0 with empty output. Choice depends on whether the CLI is grep-style (filter pipeline) or list-style (data inspection).

### Key takeaways

1. Use `action="append"` with `default=None`.
2. AND is the dominant external default; OR is the in-house default in the one analogous precedent — surface this contradiction.
3. Case-insensitive matching is the safer default for human-authored tags.
4. Pick exit-code-on-empty deliberately; reserve exit 2 for actual errors.

### Sources

- [Python argparse docs](https://docs.python.org/3/library/argparse.html), [bug 16399](https://bugs.python.org/issue16399), [Real Python argparse guide](https://realpython.com/command-line-interfaces-python-argparse/)
- [cli/cli #419](https://github.com/cli/cli/issues/419), [discussion #6138](https://github.com/cli/cli/discussions/6138), [discussion #10752](https://github.com/cli/cli/discussions/10752)
- [Docker filter docs](https://docs.docker.com/engine/cli/filter/), [Docker forum AND/OR](https://forums.docker.com/t/do-multiple-docker-filter-options-perform-a-local-and-or-or-operation/61793)
- [Taskwarrior filter](https://taskwarrior.org/docs/filter/), [tags](https://taskwarrior.org/docs/tags/)
- [Atlassian JQL multiple labels](https://community.atlassian.com/forums/Jira-questions/jql-AND-multiple-labels/qaq-p/1012889)
- [GNU grep exit status](https://www.gnu.org/software/grep/manual/html_node/Exit-Status.html), [ripgrep #1159](https://github.com/BurntSushi/ripgrep/issues/1159), [fd #303](https://github.com/sharkdp/fd/issues/303)
- [jekyll #2977](https://github.com/jekyll/jekyll/issues/2977), [jekyll-archives #43](https://github.com/jekyll/jekyll-archives/issues/43)
- [pytest custom markers](https://docs.pytest.org/en/stable/example/markers.html), [pytest #1608](https://github.com/pytest-dev/pytest/issues/1608)

## Requirements & Constraints

### Relevant requirements

`cortex/requirements/project.md` is the only requirements file that materially constrains this work (observability/pipeline/multi-agent/remote-access contain no backlog-CLI mentions):

- **Skill-helper module pattern** (line 31): promoted modules expose a `[project.scripts]` console-script entry. `cortex-backlog-ready` is currently a bash shim with no console-script entry; this ticket does not require promoting it.
- **SKILL.md-to-bin parity enforcement** (line 29): `cortex-backlog-ready` is already wired through `skills/backlog/SKILL.md` lines 82, 99. No new parity action required for an arg-surface addition.
- **Backlog `grep -c` resolution** (line 34): tickets with `grep -c "<token>"` acceptance checks must reference tokens that appear in `bin/.events-registry.md` or as literal strings under `cortex_command/`. Spec Req 15's pipe-to-grep is not bound by this rule.
- **File-based state** (→ ADR-0001): backlog state lives as markdown files; the CLI reads `index.json` (read-only emitter). Filter preserves this.
- **In Scope** (line 48): "Discovery and backlog are documented inline (no area docs)" — there is no `cortex/requirements/backlog.md`; project.md is authoritative.
- **MUST-escalation policy**: default to soft positive-routing phrasing; no MUST/CRITICAL escalation without recorded effort=high failure evidence.

### Architectural constraints

- **CLI/plugin two-channel distribution** (ADR-0002): the bash shim is mirrored to `plugins/cortex-core/bin/`. No manual mirror edit required since the shim content is unchanged.
- **Three-branch shim pattern**: branch (a) of the shim invokes `python3 -m cortex_command.backlog.ready` — currently dead because only `cortex_command/backlog/readiness.py` (pure predicate) and `cortex/backlog/ready.py` (CLI script) exist. Execution always falls through to branch (b). Adding `--tag` does not change this.
- **`pyproject.toml [project.scripts]`** has no `cortex-backlog` or `cortex-backlog-ready` entry today. Only `cortex-update-item`, `cortex-create-backlog-item`, `cortex-generate-backlog-index`, `cortex-build-epic-map` are registered. Adding `--tag` does not require a new entry.
- **No `cortex-backlog list` command exists** — confirmed across pyproject.toml, bin/, and plugins/cortex-core/bin/.
- **`generate_index.py` propagates `tags`** (line 177) — `cortex/backlog/index.json` records already carry a `tags` array per item.
- **Reason-string contract** (`cortex_command/backlog/readiness.py:12-28`): canonical wire format for `--include-blocked` reason strings is fixed. A `--tag` filter is scope-narrowing, not blocker-classification — do not invent new reason strings.

### Scope boundaries

- **In scope**: backlog tooling is in scope per project.md ("AI workflow orchestration").
- **Out of scope**: published packages or reusable modules for others — the `--tag` filter is for cortex alone.
- **Test-home location**: `tests/test_backlog_ready_render.py` is the canonical CLI integration test home; `tests/test_backlog_readiness.py` covers the pure predicate. `pyproject.toml [tool.pytest.ini_options]` `testpaths` includes both `tests/` and `cortex_command/backlog/tests/`.
- **Solution Horizon**: this ticket is a *follow-up already planned* by spec Req 15's escape-hatch clause — adding `--tag` is the durable, not stop-gap, version of arming the Phase 2 trigger.

## Tradeoffs & Alternatives

### Axis 1 — CLI surface

- **A. Extend only `cortex-backlog-ready --tag`** (recommended). 1-script change; reuses existing entry, shim, mirror. Upstream spec Req 15 is *already permissive* about the name (escape-hatch language quoted in ticket #233). Update Req 15's grep to `cortex-backlog-ready --tag phase2-trigger` as part of this ticket.
- **B. Add `cortex-backlog` umbrella with `list --tag` subcommand**. Matches language already used in spec/review.md; establishes a future home for `cortex-backlog show`, `cortex-backlog blockers`, etc. Cost: new `[project.scripts]` entry, new bin shim, new mirror, subcommand router. Solution Horizon fails for a single flag without named follow-up subcommands.
- **C. `cortex-backlog-ready --tag` plus a `cortex-backlog-list` alias wrapper**. Two names for one thing — strict negative-value over A.

**Recommendation: A.** Promote A → B later when ≥2 named follow-up subcommands materialize.

### Axis 2 — Multi-tag semantics (AND vs OR)

- The driving use case is **single-tag** (`--tag phase2-trigger`). Both semantics produce identical output for single-tag — the acceptance criteria don't exercise >1 tag.
- **Ticket #233 says AND.** External convention says AND (gh, docker, taskwarrior).
- **In-house precedent (`cortex_command/cli.py:590 --status`) says OR.**

**Recommendation: surface for user decision in Spec** — see Open Questions.

### Axis 3 — Filter argument shape

- `--tag X --tag Y` (`action="append"`) (recommended) — matches in-house `--status` precedent, no nargs-adjacency bug.
- `--tag X,Y` (comma-separated) — client-side split, no in-house precedent.
- `--tag X Y` (`nargs="+"`) — subtle bug: `--tag phase2-trigger --include-blocked` would consume `--include-blocked` as a tag value.

**Recommendation: `action="append"`** with `default=None` then coerce to `[]`.

### Axis 4 — Output filtering scope

- **Filter `groups` only** — surprising mode where `--include-blocked --tag X` ignores the tag for the blocked subset.
- **Filter both `groups` and `ineligible`** (recommended) — composes orthogonally with `--include-blocked`; one filter applied at projection time regardless of which arrays are emitted.

**Recommendation: filter both arrays.** Tag is an *output filter*, not a *readiness modifier*.

### Axis 5 — Test surface

- **Extend `tests/test_backlog_ready_render.py`** — snapshot test pinning the wire contract; mixing behavior tests forces snapshot regeneration for orthogonal reasons.
- **Add `tests/test_backlog_ready_tag_filter.py`** (recommended) — behavior-focused, lean fixture (~5 records covering: no-tag-match, single-tag-match, multi-tag overlap, blocked-tagged-item interaction with `--include-blocked`). Keeps snapshot test's purpose intact.

### Cross-axis recommendation

Implement `cortex-backlog-ready --tag X [--tag Y ...]` (Axis 1=A, Axis 3=append), filtering both `groups` and `ineligible` (Axis 4), tested via new `tests/test_backlog_ready_tag_filter.py` (Axis 5). Update upstream spec Req 15's grep to reference `cortex-backlog-ready --tag` as part of the same wiring ticket. **Axis 2 (AND vs OR semantics) is unresolved** and must be settled in Spec.

## Open Questions

1. **Multi-tag semantics: AND or OR?** Ticket #233 specifies AND ("contains all specified tags"). External convention (gh, docker, taskwarrior) is AND. In-house precedent (`cortex_command/cli.py:590` `list_sessions --status`) is OR. The single-tag acceptance test passes either way. Settle in Spec.
2. **Case sensitivity**: Match tags case-sensitively (current YAML frontmatter is lowercase by convention) or case-insensitively (Jekyll-style defensive default)? Settle in Spec — recommend case-sensitive for now since existing tags are uniformly lowercase, but document the choice.
3. **Exit code when `--tag` matches zero items**: Exit 0 with empty groups (list-style) or exit 1 (grep-style, scriptable)? Settle in Spec. Recommend exit 0 with empty groups — consistent with current no-`--tag` behavior when the ready set happens to be empty.
4. **CLI-surface decision** (Axis 1): Research recommends Alternative A (extend `cortex-backlog-ready --tag` only and amend upstream spec Req 15's grep one-line). User must approve in Spec since this is a scope decision the Clarify phase deferred to Research.

## Considerations Addressed

- **`cortex-backlog` / `cortex-backlog list` entry point existence**: No such CLI exists in `pyproject.toml [project.scripts]`, `bin/`, or `plugins/cortex-core/bin/`. Only `cortex-backlog-ready` (bash shim) is registered. Research recommends amending upstream spec Req 15's grep rather than building a new umbrella CLI.
- **`generate_index.py` tags propagation**: Verified — line 177 (`"tags": _parse_inline_str_list(fm.get("tags", "[]"))`) propagates `tags` into `index.json` for every item. Sampled index.json confirms `tags` array is present (e.g., ticket #232 has `"tags": ["phase2-trigger"]`).
- **Canonical test home for `cortex-backlog-ready`**: `tests/test_backlog_ready_render.py` is the only existing CLI integration test (snapshot-style); `tests/test_backlog_readiness.py` covers the pure predicate. Research recommends a new sibling `tests/test_backlog_ready_tag_filter.py` rather than extending the snapshot test, to keep behavior tests separate from wire-contract pinning.
