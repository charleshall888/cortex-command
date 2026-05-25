# Research: Replace cortex-update-item's positional key=value argparse with --flag value convention

## Epic Reference

This ticket descends from the [`harness-friction-triage`](../../research/harness-friction-triage/research.md) discovery, which catalogued the cortex-* CLI surface area and surfaced ~8 skill-prose-vs-CLI drift signatures. The epic covers the broader skill-prose-to-CLI contract problem; this ticket scopes to one specific symptom — `cortex-update-item`'s outlier positional `key=value` convention vs. every sibling CLI's `--flag value` argparse style. Companion tickets in the same epic: 253 (skill-prose contract lint, future) and 248 (convert embedded `python3 -m` callsites). Both are independent and ship separately. Ticket 254 (unified backlog/lifecycle slug resolver) also modifies `cortex_command/backlog/update_item.py` — coordinate landing order.

## Codebase Analysis

### Current implementation

- **File**: `cortex_command/backlog/update_item.py`
- **`main()` (lines 433-471)** reads `sys.argv[2:]` directly with manual `k=v` parsing — no argparse for field args. The positional slug at `sys.argv[1]` is also parsed manually.
- **Error message** raised at line 454: `"Invalid argument (expected key=value): {arg}"`
- **Distribution**: wheel-only via `pyproject.toml [project.scripts]` line 24 (`cortex-update-item = "cortex_command.backlog.update_item:main"`). No bash wrapper in `bin/` or plugin mirrors.
- **Accepted keys in use across the codebase**: `status`, `complexity`, `criticality`, `areas`, `spec`, `lifecycle_slug`, `lifecycle_phase`, `session_id`, `tags`, `parent`, `blocked-by`, `rework_of`, `priority`.
- **Value coercion**: strings `"null"` / `"none"` / `""` coerce to Python `None` at lines 458-461. List values like `areas=[a,b,c]` stored as literal strings; downstream `_parse_inline_str_list()` does the bracket parse.
- **Telemetry**: `_telemetry.log_invocation("cortex-update-item")` fires at line 434, before parsing — unaffected by argparse layer change.

### Sibling CLI convention (the migration target)

Every other `cortex-*` CLI in `cortex_command/` uses `argparse.ArgumentParser` with per-key `--flag value` style:

- `cortex_command/backlog/create_item.py:151-163` — per-key flags (`--title`, `--status`, `--type`, `--priority`, `--rework-of`, `--parent`, `--body`); hyphenated CLI names map to underscored attributes via `dest=`.
- `cortex_command/lifecycle/complexity_escalator.py:20-70` — per-key flags (`--lifecycle-slug`, `--events-log-path`, `--threshold`).
- `cortex_command/backlog/resolve_item.py:25-28` — argparse with `--help`/`--overwrite-backlog-dir`.

The hyphen-to-underscore convention is well-established; the new `cortex-update-item` should follow it.

### In-repo call-site inventory (migration surface)

**Skill prose callers (executable invocations only — narrative references excluded for brevity):**

| File:Line | Current invocation | Keys |
|---|---|---|
| `skills/morning-review/SKILL.md:104` | `cortex-update-item 078 status=complete` | `status` |
| `skills/morning-review/references/walkthrough.md:537` | `cortex-update-item {backlog_id} status=complete` | `status` |
| `skills/backlog/SKILL.md:79` | `cortex-update-item {{item}} status=complete` | `status` |
| `skills/backlog/SKILL.md:80` | `cortex-update-item {{item}} status=abandoned` | `status` |
| `skills/lifecycle/references/complete.md:203` | `cortex-update-item <slug> status=complete session_id=null` | `status`, `session_id` |
| `skills/lifecycle/references/wontfix.md:44` | `cortex-update-item {backlog-slug} status=wontfix lifecycle_phase=wontfix session_id=null` | 3 keys |
| `skills/lifecycle/references/clarify.md:112` | `cortex-update-item {backlog-filename-slug} complexity={value} criticality={value}` | 2 keys |
| `skills/lifecycle/references/backlog-writeback.md:29` | `cortex-update-item <slug> status=complete lifecycle_phase=complete session_id=null` | 3 keys |
| `skills/lifecycle/references/backlog-writeback.md:80` | `cortex-update-item <path> status=in_progress session_id=$LIFECYCLE_SESSION_ID lifecycle_phase=research` | 3 keys |
| `skills/lifecycle/references/backlog-writeback.md:88` | `cortex-update-item <path> lifecycle_slug={lifecycle-slug}` | 1 key |
| `skills/refine/SKILL.md:84` | `cortex-update-item {backlog-filename-slug} complexity={value} criticality={value}` | 2 keys |
| `skills/refine/SKILL.md:187` | `cortex-update-item {backlog-filename-slug} status=refined spec=cortex/lifecycle/{lifecycle-slug}/spec.md` | 2 keys |
| `skills/refine/SKILL.md:191` | `cortex-update-item {backlog-filename-slug} "areas=[area1,area2]"` | `areas` (list) |
| `skills/refine/SKILL.md:194` | `cortex-update-item {backlog-filename-slug} "areas=[]"` | `areas` (empty list) |

**Other executable callers:**
- `justfile:131` — `cortex-update-item {{ feature }} status=complete`
- `cortex_command/backlog/update_item.py:9-14` — module docstring shows old syntax; must rewrite
- `cortex_command/backlog/update_item.py:437` — `Usage:` error string hardcodes old syntax; remove when argparse takes over

**Tests:**
- `tests/test_morning_review_status_close_ordering.py:22` — `CLOSE_ARG = "status=complete"` literal; assert at line 74 (`assert CLOSE_ARG in close_line_text`) requires `CLOSE_ARG` to match the exact new prose form (with or without `=` after the flag). **Spec must pin the canonical form first; test follows.**
- No dedicated CLI argparse unit tests for `update_item.py` exist today — this is a gap to address.

**User-facing docs:**
- `docs/backlog.md:104-197` — ~7 worked `cortex-update-item key=value` examples. Agent 1 (Codebase) missed this; Adversarial agent caught it. Must migrate.

**Unaffected (by argparse layer change):**
- `cortex_command/overnight/outcome_router.py:320-321,416` — imports `update_item()` and `_find_item` as Python functions and passes a dict. Bypasses CLI.
- `tests/test_backlog_worktree_routing.py` — tests internal `update_item()` API.
- `.githooks/pre-commit` and other hooks — confirmed: no `cortex-update-item` invocations. **The "migration commit fails to commit" risk is defused.**

**Historical artifacts (do NOT migrate):**
- `cortex/lifecycle/**/spec.md, plan.md, research.md` (8+ in-progress lifecycle artifacts) contain `cortex-update-item key=value` examples in prose. These are append-only historical context. The argv pre-flight migration hint (see Open Questions) is the safety net for resumed sessions that read this prose and emit the old form.
- `cortex/lifecycle/**/events.log` — append-only NDJSON; never re-executed.

### Parity infrastructure

- `bin/cortex-check-parity` (`cortex_command/parity_check.py`) scans skill prose for `cortex-*` references. Will surface any prose still using old syntax post-migration if extended to catch the shape.
- `bin/cortex-check-prescriptive-prose` is orthogonal (validates prose style, not CLI surface).
- No skill-prose-to-CLI argparse contract lint exists today; ticket 253 proposes one. This work removes one categorical exception that 253 would otherwise need to special-case.

### Plugin mirror regeneration

`just build-plugin` uses `rsync -a --delete` to copy `skills/` to `plugins/cortex-core/skills/` and `plugins/cortex-overnight/skills/`. The pre-commit hook regenerates mirrors on staged paths matching the trigger pattern (typically `skills/`). If the migration commit stages only canonical sources and the hook fires correctly, mirrors update automatically — but the spec should mandate explicit `just build-plugin` invocation as a verification prerequisite to defuse the "hook didn't fire" failure mode.

### Recommended new signature shape

```
cortex-update-item <slug-or-uuid> [--status STATUS] [--lifecycle-phase PHASE] [--session-id ID] [--complexity VALUE] [--criticality VALUE] [--spec PATH] [--areas A [A ...]] [--tags T [T ...]] [--lifecycle-slug SLUG] [--priority VALUE] [--parent PARENT] [--blocked-by B] [--rework-of R]
```

- All scalar fields: per-key flags, all optional (no-flag = no-op, current behavior preserved).
- List fields (`areas`, `tags`): see Open Questions for shape decision.
- Pass `allow_abbrev=False` to `ArgumentParser` to disable prefix-matching (prevents `--sess` from silently matching `--session-id`; future-proofs against ambiguity from new flags).

## Web Research

### Prior art surveyed

- **kubectl label / annotate**: positional `key=value` (matches current cortex-update-item), trailing-dash deletion (`key-`), `--overwrite` gating. K8s-specific convention; not portable.
- **gh issue edit / pr edit**: per-field flags with paired add/remove for lists (`--add-label`, `--remove-label`); comma-separated or repeated invocations. Closest precedent for the new shape.
- **terraform**: `-var=k=v` repeating flag; HCL/JSON for complex types.
- **Azure CLI**: `--set k=v` space-separated; quoting-fragile for JSON values (Microsoft maintains a dedicated troubleshooting page).
- **Salesforce sf CLI**: explicit guidance — "use `multiple:true` flag property... encourage users to specify the flag multiple times" over comma-separated; "flags over positional."
- **clig.dev (Command Line Interface Guidelines)**: "Prefer flags to args. Sometimes when using args, it's impossible to add new input without breaking existing behavior."

### Idiomatic Python argparse patterns

- `action='append'` accumulates into a list on repeat: `--tag a --tag b` → `['a', 'b']`.
- `nargs='+'` consumes multiple tokens after one flag occurrence: `--areas a b c` → `['a', 'b', 'c']`.
- `nargs='*'` is the same but allows zero tokens: `--areas` → `[]`. This is the cleanest empty-list semantic.

### Breaking-change policy for internal CLIs

- Azure CLI's bi-annual, 30-day-pre-announcement breaking-change policy applies to **public** CLIs with unknown external callers. It explicitly does not apply to internal-only tools.
- Shopify CLI 4.0 case study: real-world prior art for skipping deprecation on a closed-callsite migration — completed atomically in one engineering day for a single-app team.
- Cortex-command's installation surface (per `docs/setup.md`) is `uv tool install git+https://github.com/charleshall888/cortex-command.git@<tag>` — anyone following published install instructions has the wheel on PATH. The auto-update flow at `docs/internals/auto-update.md` re-installs on version mismatch, so external operators *do* get the breaking change on next overnight run. **This contradicts a naive "internal-only" framing** — see Open Questions.

### Web sources

- [Command Line Interface Guidelines (clig.dev)](https://clig.dev/)
- [Python argparse documentation](https://docs.python.org/3/library/argparse.html)
- [gh issue edit manual](https://cli.github.com/manual/gh_issue_edit)
- [Salesforce CLI Flags and Arguments guide](https://developer.salesforce.com/docs/platform/salesforce-cli-plugin/guide/flags.html)
- [Azure CLI breaking-change policy](https://github.com/Azure/azure-cli/blob/dev/doc/how_to_introduce_breaking_changes.md)
- [Shopify CLI 4.0 engineering migration case study](https://no7software.co.uk/blog/shopify-cli-4-engineering-migration-2026)
- [kubectl label reference](https://www.mankier.com/1/kubectl-label)

## Requirements & Constraints

### Load-bearing constraints from cortex/requirements/project.md

- **Skill-helper modules pattern (line 35)**: `cortex_command/<skill>.py` subcommands exposing `[project.scripts]` console-script entries. `cortex-update-item` is the canonical instance of this pattern; the migration preserves it.
- **SKILL.md-to-bin parity enforcement (lines 33-34)**: `bin/cortex-check-parity` blocks drift between skill prose and CLI surface. Post-migration, skill prose using the old syntax is detectable via grep (and ticket 253's future lint).
- **Wheel-binstub vs working-tree invocation (line 38)**: edits to `cortex_command/*.py` do not affect binstub behavior until `uv tool install --reinstall` runs. Concrete prior art exists at `cortex/lifecycle/remove-daytime-autonomous-pipeline-and-cancel/plan.md:199-231` — the implementer must use either `--reinstall --refresh-package cortex-command .` or `python3 -m cortex_command.backlog.update_item` for verification.
- **Solution horizon (lines 19-21)**: "Long-term project — fixes reflect that. ... A deliberately-scoped phase is not a stop-gap." The "replace outright" choice is durable; the deprecation-window alternative is the stop-gap pattern this principle warns against.
- **CLAUDE.md "prescribe What and Why, not How"**: applies to skill prose, not to CLI design. The new CLI's argparse signature *is* the contract — prescriptive is correct here.

### ADR-0002 (CLI wheel + plugin distribution)

Two-channel split with compatibility envelope. Wheel-first, no symlinks. CLI and plugins evolve at independent cadences. This ticket changes only the wheel-tier CLI surface; no plugin-tier change required.

### No pre-existing argparse-convention ADR

No requirements file or ADR mandates a specific argparse style. This ticket establishes the convention by precedent. Future tickets (e.g., 253's contract lint) will be authored against the convention this ticket lands.

### Distribution surface implications

- `pyproject.toml:24` — `cortex-update-item` is a wheel-tier entry point, installed via `uv tool install` on every operator's machine.
- The MCP server's auto-update flow (`docs/internals/auto-update.md`) re-installs the wheel on version pin drift — external operators get the breaking change automatically on their next session start.
- This means the migration reaches beyond this repo's source tree to every machine running the wheel. The breaking change is real, not just internal.

### Companion-ticket context

- **Ticket 248**: convert embedded `python3 -m cortex_command.*` callsites in bin/ scripts and skill prose to use the corresponding `cortex-*` console-script entry. Independent — ships separately.
- **Ticket 253**: skill-prose-to-CLI argparse contract lint. Future; will be made simpler by this work.
- **Ticket 254 (also `status: refined`)**: modifies the same file (`cortex_command/backlog/update_item.py:128-152`, the `_find_item` function). **Likely merge conflict if both land independently.** Sequence: 257 (this ticket, CLI-surface change) lands first; 254 (resolver internals) rebases on top — the `_find_item` changes are agnostic to the argparse layer.

## Tradeoffs & Alternatives

### Approach A — Replace outright (no alias) — recommended; user's selection

`cortex-update-item <slug> --status complete --session-id null`. All in-repo skill prose, the justfile, the module docstring, and the test fixture migrate atomically in one PR. Old `key=value` calls produce an argparse error.

**Pros**: smallest long-term maintenance surface; aligns with all sibling CLIs; makes ticket 253's contract lint strictly simpler (one schema, not two); fail-loud failure mode; forecloses no future option.

**Cons**: one-shot migration must touch all call sites in one PR; muscle-memory operators get a hard error rather than a warning (the source ticket frames this as intended behavior — fail-loud, not fail-silent).

### Approach B — Deprecation window (parallel support)

Accept both syntaxes; emit `DeprecationWarning` on old form; follow-up ticket removes the alias.

**Pros**: zero-risk staged migration; lower coordination cost.

**Cons**: worst-of-both-worlds risk — dual-syntax code path lingers if cleanup ticket is deprioritized; argparse doesn't natively support both forms (requires a custom action subclass or two-pass parse); deprecation warning is **invisible to skill-authoring agents** that don't read stderr — they will bake deprecated syntax into new skill prose during the window. Contract lint must special-case the deprecation then un-special-case it during cleanup.

### Approach C — Permanent dual-syntax alias

Accept both forever; no removal plan.

**Pros**: zero migration cost; never breaks any caller.

**Cons**: permanently entrenches the inconsistency the ticket exists to fix; future drift between forms guaranteed; effectively closes #257 by negating its premise. Implementation complexity is the same as B without the cleanup payoff.

### Approach D — Single `--set key=value` flag (repeatable)

`cortex-update-item <slug> --set status=refined --set "areas=[a,b]"`.

**Pros**: minimal implementation diff (just shift `field_args = sys.argv[2:]` to `args.set`); extensible without per-field declarations.

**Cons**: doesn't solve the ergonomic problem — operators were typing `--status complete` because every sibling CLI uses that shape; `--set status=complete` is a third syntax matching neither old form nor sibling CLIs. Contract lint can validate the flag but not the field names.

### Approach E — Click rewrite

Switch from argparse to `click`.

**Pros**: long-term ergonomics (better `--help`, shell completion via `Choice([...])`).

**Cons**: out of scope; adds `click` as a new project dependency; would force ~15 sibling modules into the same migration; ticket 253's introspection layer is being designed against argparse parsers.

### Approach F — JSON patch input

`cortex-update-item <slug> --patch '{"status":"refined"}'`.

**Pros**: structured input; one argument shape; machine-friendly.

**Cons**: hostile to interactive operators and skill-prose authoring agents; brittle quoting; diverges from every sibling CLI; doesn't solve the muscle-memory failure.

### Recommended approach: A

Approach A aligns with sibling CLI convention, fails loud, has bounded blast radius, and forecloses no future option. The user explicitly selected A during Clarify. Research confirms this is the right call. The one decision the spec must pin is **list-value shape** — see Open Questions.

## Adversarial Review

### Verified argparse behavior

Empirical testing of argparse against the proposed shape produced concrete findings:

1. **Prefix abbreviation is a footgun.** Default `ArgumentParser` accepts unambiguous prefixes (`--stat`, `--sess`, `--lif`). Mitigation: `allow_abbrev=False`.
2. **Repeated scalar flags silently last-wins.** `--status complete --status refined` → `status='refined'` with no error. The old form had the same implicit behavior; this is regression-neutral. Decision needed: explicit reject or document last-wins?
3. **Empty-string flag values pass through.** `--status ''` → `status=''`. The new layer must preserve the existing `"" → None` coercion (lines 458-461) or YAML frontmatter gets corrupted.
4. **`null` semantic preservation.** `--status null` must coerce to Python `None`, matching current `status=null` behavior.
5. **Bare `cortex-update-item 257 status=complete`** produces `error: unrecognized arguments: status=complete` — does NOT explain migration. Operators will be confused for one debugging cycle without a custom error handler.

### List-value shape — third option surfaced

Agent 4 framed the choice as binary: repeating flags vs bracket-string. Empirical testing surfaced a third option:

- `nargs='*'` cleanly handles empty-list (`--areas` → `[]`), single-element (`--areas a` → `['a']`), and multi-element (`--areas a b c` → `['a','b','c']`) without bracket-parsing quirks. Drops backward-compat hack of `_parse_inline_str_list()` for new CLI input.

### Concurrent ticket 254 collision

Both 257 and 254 modify `cortex_command/backlog/update_item.py`. 254 changes `_find_item` internals (resolver logic); 257 changes `main()` and argparse setup. Likely merge conflict if both land independently. Recommended sequence: 257 first (this ticket), then 254 rebases on top — 254's changes are agnostic to argparse layer.

### Resumed in-progress lifecycle risk

Multiple in-progress lifecycle artifacts contain `cortex-update-item key=value` examples in cached prose (research/spec/plan files). On resume after this PR merges, the agent reads cached prose and may emit the old form, which hard-fails. Mitigation: argv pre-flight hint converts hard-fail-and-stop into fail-loud-with-actionable-message — the agent retries with the new form on next iteration.

### External-caller surface is non-trivial

`cortex-update-item` ships via wheel installed by `uv tool install`. Any operator with shell aliases, dotfile snippets, scripts in `~/bin/`, or CI on a fork has callsites outside this repo. The auto-update flow at `docs/internals/auto-update.md` pushes the breaking change to them automatically. **The argv pre-flight hint is the only mitigation that reaches external callers without requiring them to read docs.**

### Wheel-vs-working-tree mismatch during verification

Per project.md line 38 and concrete prior art at `cortex/lifecycle/remove-daytime-autonomous-pipeline-and-cancel/plan.md:199-231`: editing `cortex_command/backlog/update_item.py` does NOT change binstub behavior until `uv tool install --reinstall --refresh-package cortex-command .` runs. The implementer must either reinstall or use `python3 -m cortex_command.backlog.update_item` for verification — otherwise they'll get the old behavior and think the patch didn't land.

### Plugin mirror regeneration trigger verification

`just build-plugin` regenerates mirrors via `rsync -a --delete`. The pre-commit hook trigger pattern includes `skills/`. If the migration PR stages only canonical sources matching the trigger, mirrors update automatically. Recommended: spec mandates explicit `just build-plugin` invocation as a verification prerequisite.

### Recommended mitigations (from Adversarial)

1. **Argv pre-flight migration hint** — detect bare `k=v` after the slug, emit migration message, exit 2. Highest-leverage mitigation; reaches every caller surface.
2. **`allow_abbrev=False`** on `ArgumentParser`.
3. **Pin list-value shape** to `nargs='*'` (recommended); drop bracket-string support for new CLI input.
4. **Reject or document duplicate-scalar-flag behavior.**
5. **CHANGELOG `### Breaking` entry** linking back to the migration hint message text.
6. **Spec must require `uv tool install --reinstall ...` or `python3 -m ...`** for implementer verification.
7. **Coordinate landing with ticket 254** — this ticket first.
8. **Do not rewrite historical lifecycle artifact prose** — they're append-only history. The argv pre-flight is the catch-net.
9. **Verify `.githooks/pre-commit` Phase 2 trigger** covers staged paths in the migration PR.

### Correction to other agents' findings

- Agent 4's binary framing of list-value shape (repeating vs bracket) missed `nargs='*'` as the better third option.
- Agent 2's claim that positional `k=v` is K8s-specific overstates: `make VAR=val`, `env VAR=val cmd`, `ssh -o Option=value` use it idiomatically. The argument for `--flag value` is internal sibling-CLI consistency, not categorical positional-`k=v` rejection.

## Open Questions

All open questions are preference / scope decisions, not research-investigable. Each carries a recommended answer; all are **Deferred to Spec**: the Specify phase's structured interview is the natural place to pin them down with the user, and resolving them inline at the Research Exit Gate would create a redundant second Q&A round before Spec.

1. **List-value flag shape** (Deferred to Spec). Recommended: `nargs='*'` — cleanest empty-list semantics, matches clig.dev/Salesforce guidance, drops the bracket-string parsing quirk for new CLI input. Alternatives: `action='append'` (requires repeated `--areas a --areas b`); bracket-string `--areas '[a,b]'` (smallest diff but perpetuates quirk).
2. **Duplicate scalar flag behavior** (Deferred to Spec). Recommended: reject duplicates with a custom action. Agentic template substitution can accidentally double-substitute; silent last-wins is the harder failure mode to debug. Alternative: document last-wins as intentional.
3. **Argv pre-flight migration hint** (Deferred to Spec). Recommended: include. ~10 lines of pre-argparse sys.argv scanning converts a confusing argparse error into an actionable migration message for every caller surface (operators, resumed cached sessions, fork users). Operator-experience payoff is large for small implementation cost.
4. **`allow_abbrev=False`** (Deferred to Spec). Recommended: include. Prevents prefix-matching footguns and future-proofs against ambiguity from new flags. Zero downside.
5. **Ticket 254 coordination** (Deferred to Spec). Recommended landing order: 257 first (this ticket, CLI surface), then 254 rebases on top — 254's `_find_item` changes are argparse-layer-agnostic. If 254 lands first, this ticket's `_find_item` callsites need rebase.
6. **In-progress lifecycle artifact prose** (Deferred to Spec). Recommended: do nothing — they're append-only history; the argv pre-flight hint (Q3) is the safety net. Alternative: rewrite the ~8 affected files (high churn, noisy diff).
7. **Plugin mirror regeneration verification** (Deferred to Spec). Recommended: explicit `just build-plugin` step in plan as a verification prerequisite, defusing the "pre-commit hook didn't fire" failure mode. Alternative: rely solely on pre-commit hook auto-trigger.
