# Research: Add `cortex init` per-repo scaffolder for lifecycle/backlog/retros/requirements

> Implementation-level research for backlog item [[119-cortex-init-per-repo-scaffolder]].
> Clarified intent: Add a `cortex init` CLI subcommand that scaffolds `lifecycle/`, `backlog/`, `retros/`, `requirements/` template directories into the user's git repo (shadcn-style). Hard-fails outside a git repo. `--update` is strictly additive (writes missing files, preserves existing, reports template drift). `--force` overwrites all with confirmation. Also registers `$(pwd)/lifecycle/sessions/` in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array (additive, idempotent).

## Epic Reference

Parent epic research: [`research/overnight-layer-distribution/research.md`](../../research/overnight-layer-distribution/research.md) — DR-5 (cortex setup owns `~/.claude/` deployment, superseded in practice by ticket 117's scope inversion which retired cortex setup entirely) and DR-7 (lifecycle/backlog/retros = shadcn-style scaffolding). The epic decomposed distribution work across tickets 114–124; this ticket (119) is Wave 2, size M, and solely owns the per-repo scaffolding verb. Epic research does **not** address the sandbox `allowWrite` registration — that introduction is new to ticket 119 scope and surfaced here as architectural drift warranting an explicit decision record in `spec.md`.

## Codebase Analysis

### Files that will change

**Modified**:
- `cortex_command/cli.py:63-68` — replace the `init` subparser's `_make_stub("init")` handler with a real handler; wire `--update`, `--force`, `--path` flags.
- `CLAUDE.md:5` — narrow the "nothing is deployed into `~/.claude/` by this repo" claim to reflect the new `settings.local.json` write (see H2 in Adversarial Review).

**New implementation (recommended subpackage layout, mirrors `cortex_command/overnight/` and `cortex_command/pipeline/`)**:
- `cortex_command/init/__init__.py`
- `cortex_command/init/handler.py` — argparse handler entry point
- `cortex_command/init/scaffold.py` — directory/template materialization + decline-gate + drift detection
- `cortex_command/init/settings_merge.py` — `~/.claude/settings.local.json` `allowWrite` append
- `cortex_command/init/templates/lifecycle/README.md`
- `cortex_command/init/templates/backlog/README.md`
- `cortex_command/init/templates/retros/README.md`
- `cortex_command/init/templates/requirements/project.md`
- `cortex_command/init/templates/lifecycle.config.md`

**New tests**:
- `cortex_command/init/tests/test_scaffold.py`
- `cortex_command/init/tests/test_settings_merge.py`

### Reusable patterns to inherit

- **Atomic file write**: `cortex_command.common.atomic_write(path, content)` at `cortex_command/common.py:366-406` — uses `tempfile.mkstemp` in the same dir, `durable_fsync` (F_FULLFSYNC on macOS), `os.replace`. Canonical pattern; reuse verbatim for both template materialization and settings.local.json write.
- **Git-repo detection / target-root resolution**: `cortex_command/pipeline/worktree.py:34-42` defines `_repo_root()` via `subprocess.run(["git", "rev-parse", "--show-toplevel"], ..., check=True)`. For this ticket, call with `check=False` + inspect `returncode` to produce a clear user-facing error on non-zero (the hard-fail path). `--show-toplevel` handles worktrees and submodules correctly.
- **Template asset convention (package-local prompts)**: `cortex_command/overnight/prompts/` loaded via `Path(__file__).resolve().parent / "prompts/batch-brain.md"` (overnight/brain.py:103); `cortex_command/pipeline/prompts/` loaded via `Path(__file__).resolve().parent / "prompts" / "review.md"` (pipeline/review_dispatch.py:86). No use of `importlib.resources` anywhere in the codebase. Hatch's default wheel build (`[tool.hatch.build.targets.wheel] packages = ["cortex_command"]`, `pyproject.toml:20-21`) already ships non-Python files inside `cortex_command/` — no `MANIFEST.in` or `package_data` wiring needed.
- **CLI subparser wiring**: `cortex_command/cli.py:47-77` — `argparse` subparsers; handlers are simple callables set via `.set_defaults(func=…)`; exit via `int` return or `sys.exit(2)` for user-error, `sys.exit(1)` for runtime failures.
- **HOME-mocking for tests**: `tests/test_runner_signal.py:95` uses `env["HOME"] = str(tmp_path)` / `monkeypatch.setenv("HOME", str(tmp_path))`. Reuse for settings.local.json merge tests.
- **Standalone sibling-verb precedent (for `--unregister` if added)**: `backlog/update_item.py`, `backlog/create_item.py` are argparse-style scripts with `int` exit codes, stderr for errors, `common.atomic_write` for writes.

### Pre-117 reference implementation (retrieved from git history)

The `just setup-force` recipe at `justfile:390-408` (pre-117, retrieved via `git show 4f96491^:justfile`):

```bash
LOCAL_SETTINGS="$HOME/.claude/settings.local.json"
ALLOW_PATH="$(pwd)/lifecycle/sessions/"
if [ -f "$LOCAL_SETTINGS" ]; then
    if command -v jq &>/dev/null; then
        jq --arg path "$ALLOW_PATH" '
            .sandbox.filesystem.allowWrite = (
                (.sandbox.filesystem.allowWrite // []) + [$path] | unique
            )
        ' "$LOCAL_SETTINGS" > "$LOCAL_SETTINGS.tmp"
        mv "$LOCAL_SETTINGS.tmp" "$LOCAL_SETTINGS"
    else
        printf '{\n  "sandbox": {\n    "filesystem": {\n      "allowWrite": ["%s"]\n    }\n  }\n}\n' "$ALLOW_PATH" > "$LOCAL_SETTINGS"
    fi
else
    printf '{\n  "sandbox": {\n    "filesystem": {\n      "allowWrite": ["%s"]\n    }\n  }\n}\n' "$ALLOW_PATH" > "$LOCAL_SETTINGS"
fi
```

The jq expression `.sandbox.filesystem.allowWrite = ((.sandbox.filesystem.allowWrite // []) + [$path] | unique)` is the reference — it does **not** clobber sibling keys like `sandbox.network.allowUnixSockets` (verified during adversarial review). Pitfalls that the pre-117 version has and this ticket must fix:
1. `| unique` lexicographically reorders the array — should be order-preserving `if any(. == $path) then . else . + [$path] end`.
2. No pre-validation that `.sandbox` / `.sandbox.filesystem` are objects — a stringified value causes jq exit 5 with an opaque error.
3. Silent printf-overwrite on missing jq — the ticket explicitly requires a stricter hard-fail.

The closest living safety-rigor exemplar is the `just setup-tmux-socket` recipe at `justfile:114-150` (jq hard-fail, idempotence pre-check, atomic temp+rename) — but it writes a different key (`allowUnixSockets`) and uses a "self-contained array replacing parent" pattern per `observability.md` not a deep-path assignment. Structurally similar; semantically different.

### Package-data loading and `uv tool install -e .`

Hatch's default wheel build picks up all non-Python files inside `cortex_command/` (no `package_data` wiring needed). For editable installs (`uv tool install -e .`), `Path(__file__).parent / "templates"` points at the actual source tree — edits to templates in the repo are picked up live without reinstall. This matches every existing prompts-loading call site.

### Absent patterns (gaps this ticket introduces)

- **No existing Python code writes to `~/.claude/settings.local.json`.** The only callers today are the shell-based `just setup-tmux-socket` recipe and docs. Ticket 119 is the first Python-side writer. This is one reason the adversarial review (H2, M2) elevates the architectural-review concern.
- **No existing scaffolder or template-materialization code**. `backlog/{create_item,update_item}.py` write single files; nothing walks a directory tree into a user repo.
- **No existing drift-detection helper**. Neither cruft-style state files nor shadcn-style marker files are present.

## Web Research

### shadcn init behavior (primary prior art per DR-7)

From [shadcn init source](https://raw.githubusercontent.com/shadcn-ui/ui/main/packages/shadcn/src/commands/init.ts) and [shadcn docs](https://ui.shadcn.com/docs/cli):

- `init` is a full project bootstrap, heavier than what this ticket proposes (deps, `components.json`, `tailwind.css`, `utils.ts`).
- **Already-initialized guard**: `fsExtra.existsSync(path.resolve(cwd, "components.json"))`. If present and `--force` not set, prompts "A components.json file already exists. Would you like to overwrite it?" with `initial: false`; declining exits 1 with "To start over, remove the components.json file and run init again." `--force` skips the prompt.
- **No `--update` equivalent in `init`.** Drift lives in a separate `shadcn diff` command (now folded into `shadcn add [component] --diff`) — walks already-installed components, fetches registry versions, prints `diffLines` patches, **does not auto-apply**. This is the "report drift, let the user act" pattern the ticket adopts.
- **Per-file backup-and-restore on unexpected exit**: shadcn creates `components.json.backup` before mutating and registers `process.on("exit", restoreBackupOnExit)`. Worth borrowing for the `--force` overwrite path.

### `--force` UX convention ([clig.dev](https://clig.dev/))

> *"Confirm before doing anything dangerous. A common convention is to prompt for the user to type y or yes if running interactively, or requiring them to pass -f or --force otherwise."*

Severity ladder: mild → confirm, no `--force` needed; moderate → confirm + offer dry-run, `--force` to skip; severe → type the resource name or pass `--confirm="<name>"`. Industry examples:
- `rm -f`: suppresses confirmation; silent on missing files.
- `git clean -f`: `-f` is *required* to clean, no further prompt.
- shadcn `init --force`: skips the prompt.
- kubectl `delete --force`: bypasses graceful termination; `-i/--interactive` is the confirmation flag.

### Python CLI scaffolder prior art

- **[cruft](https://cruft.github.io/cruft/)** (closest to this ticket's intent): wraps cookiecutter with a `.cruft.json` state file holding template commit hash + variables. `cruft check` → exit 1 on drift; `cruft diff` → git-diff-style output; `cruft update` → prompts before applying. **State file on disk.**
- **[copier](https://copier.readthedocs.io/)**: 3-way smart merge between original template, user's current project, new template. **Anti-pattern for this ticket's "strictly additive" decision.**
- **cookiecutter**: one-shot rendering only; no update story.

### jq canonical idempotent-append pattern

```bash
jq --arg v "$PATH" '
  if (.sandbox.filesystem.allowWrite // []) | index($v)
  then .
  else .sandbox.filesystem.allowWrite += [$v]
  end' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
```

Preserves array order (unlike `| unique`). Pitfalls:
- Trailing newline: jq emits one by default; benign for settings files.
- Autovivification: `jq 'a.b.c = []'` doesn't autovivify in strict mode — use `// []` fallback or `setpath`.
- Atomic rename: always tmp + `mv`, never `>` directly into `$f`.
- `index()` vs `contains()`: use `index()` for exact-match semantics on path strings.

### Python `json` module alternative (strong case)

For a Python CLI, shelling out to jq is not idiomatic:

```python
import json, os
p = Path.home() / ".claude/settings.local.json"
data = json.loads(p.read_text()) if p.exists() else {}
arr = data.setdefault("sandbox", {}).setdefault("filesystem", {}).setdefault("allowWrite", [])
target = str((repo_root / "lifecycle/sessions/").resolve()) + "/"
if target not in arr:
    arr.append(target)
atomic_write(p, json.dumps(data, indent=2) + "\n")
```

- No jq dependency (jq is not in macOS default install or Linux minimal images like Debian-slim/Alpine).
- No shell-quoting fragility.
- Testable with pytest + `monkeypatch.setenv("HOME", str(tmp_path))`.
- Uses the existing `cortex_command.common.atomic_write`.
- `os.replace()` maps to POSIX `rename(2)` — atomic on same filesystem.

### Git-repo hard-fail conventions

- Canonical check: `git rev-parse --show-toplevel` (returncode 0 + stdout = path; non-zero + empty = not a git repo). Handles worktrees, submodules, `$GIT_DIR` overrides. Matches `pipeline/worktree.py:34` convention.
- Exit code: non-zero, typically 1 (git itself uses 128 for its own "not a repo").
- Error message style (pre-commit, shadcn, gitleaks): one sentence identifying the condition, optional remediation hint. Example: `cortex init: not inside a git repository. Run 'git init' first, or pass --path <repo-root>.`

### Drift-report prior art

- **[cruft check / diff](https://cruft.github.io/cruft/)**: the canonical Python prior art. Exit 1 on drift; git-diff-style output; separates "detect" from "apply".
- **shadcn diff**: lists changed files, prints per-file diffs, never applies.
- **terraform plan**: archetypal drift report — shows what *would* change; `apply` is separate.

Common shape across these: **read-only drift detection + separate apply path**.

### Notable anti-patterns to avoid

- Don't check `.git/` existence — breaks on worktrees/submodules.
- Don't auto-merge user edits during `--update` (Copier's approach); report drift, let the user act.
- Don't redirect `>` directly into settings file from jq output (shell truncates before jq finishes).
- Don't persist a drift-state file unless the detection algorithm actually needs it — "currently-shipped package content" is already available at runtime from the installed package.

### Key sources

- shadcn init: https://raw.githubusercontent.com/shadcn-ui/ui/main/packages/shadcn/src/commands/init.ts
- shadcn diff: https://raw.githubusercontent.com/shadcn-ui/ui/main/packages/shadcn/src/commands/diff.ts
- clig.dev: https://clig.dev/
- cruft: https://cruft.github.io/cruft/
- `importlib.resources`: https://docs.python.org/3/library/importlib.resources.html
- jq idempotent append: https://salferrarello.com/add-element-to-array-if-it-does-not-already-exist-with-jq/
- git rev-parse: https://git-scm.com/docs/git-rev-parse

## Requirements & Constraints

### From `requirements/project.md`

- **File-based state** (line 25): "Lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files (markdown, JSON, YAML frontmatter). No database or server."
- **Defense-in-depth for permissions** (line 32): "The global `settings.json` template ships conservative defaults — minimal allow list, comprehensive deny list, sandbox enabled. For sandbox-excluded commands (git, gh, WebFetch), the permission allow/deny list is the sole enforcement layer; keep global allows read-only and let write operations fall through to prompt. The overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`), making **sandbox configuration the critical security surface for autonomous execution**."
- **Complexity philosophy** (line 19): "Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."
- **Distribution** (line 52): `cortex` CLI "ships as a local editable install (`uv tool install -e .`) for self-hosted use." (Per DR-8 this line is flagged for a deferred update but not yet applied.)

### From `requirements/pipeline.md`

- **Atomicity** (line 125): "All session state writes use tempfile + `os.replace()` — no partial-write corruption."
- `lifecycle/` tree is a load-bearing dependency substrate for the overnight runner (Dependencies section, lines 140-147).

### From `requirements/multi-agent.md`

- **Overnight bypasses permissions** (line 23): "Permission mode is always `bypassPermissions` for overnight agents." Implication: `sandbox.filesystem.allowWrite` only affects **interactive** (non-overnight) Claude Code sessions. Overnight workers write freely to `lifecycle/sessions/` regardless of the allowWrite array — so the allowWrite entry this ticket adds primarily unblocks *interactive* sessions (for dashboard invocation, status CLI, etc.), not the overnight runner itself. This is the load-bearing motivation the ticket body doesn't state explicitly.

### From `requirements/observability.md` (highly relevant — analogous pattern)

- **Sandbox Socket Access** (lines 68-79, the closest existing analogue): updated `~/.claude/settings.local.json` with combined `allowUnixSockets` array; "Existing `sandbox.filesystem.allowWrite` entries in `settings.local.json` are preserved (arrays replace, not merge)"; idempotent.
- **Edge case** (line 111): "`settings.local.json` array clobber: Adding `allowUnixSockets` via naive jq write could destroy `filesystem.allowWrite`; setup recipe uses deep merge to preserve sibling keys."
- **Important**: this edge case describes `just setup-tmux-socket`'s technique (read from `settings.json`, write self-contained combined array into `settings.local.json`). Ticket 119's use of `.sandbox.filesystem.allowWrite = <expr>` at a specific deep path does **not** clobber siblings — jq's `=` assignment only replaces the leaf; intermediate objects are preserved. Verified empirically during adversarial review.

### From `CLAUDE.md`

- **Distribution** (line 22): "Cortex-command ships as a CLI installed via `uv tool install -e .` plus plugins installed via `/plugin install`. It no longer deploys symlinks into `~/.claude/`."
- **"Nothing is deployed into `~/.claude/` by this repo"** (line 5): *in direct tension* with ticket 119's sandbox allowWrite write. Must be reconciled as part of this ticket (see Adversarial H2).
- **Conventions** (line 45): "Settings JSON must remain valid JSON."
- **Commit discipline**: always commit via `/commit`.

### Epic 113 DR-5 (verbatim)

> `cortex setup` is the canonical `~/.claude/` deployment, not a package manager hook. All `~/.claude/{skills,hooks,rules,reference,notify.sh,statusline.sh}` and `~/.local/bin/*` deployment happens in an explicit `cortex setup` subcommand.

**Status**: ticket 117 inverted scope and retired cortex setup entirely along with the shareable-install scaffolding. Nothing in cortex-command writes to `~/.claude/` today. Ticket 119's `settings.local.json` write would be the **sole path in the whole codebase that writes under `~/.claude/`**. This is not nominally a DR-5 violation (DR-5 was about deployment symlinks and binaries, not sandbox config), but it is architectural drift from the post-117 state of "nothing writes there."

### Epic 113 DR-7 (verbatim)

> Lifecycle/backlog/retros in the user's repo = shadcn-style scaffolding. Add a `cortex init` subcommand that scaffolds these directories (with templates) into the user's target repo — like `npx shadcn init`. Users can re-run `cortex init --update` to pull new templates. Keeps the "user owns the code" model for content that's semantically part of their project. Avoids conflating machine-config deployment with project-content scaffolding.

DR-7 does **not** mention the sandbox allowWrite registration. The ticket's bundling of that responsibility under `cortex init` is a post-research procedural handoff (117 Non-Requirements → 119) without a DR behind it. See Open Questions.

### From ticket 117 (the adjacent just-completed ticket)

117 retired `cortex setup`, `~/.claude/rules/`, `~/.claude/reference/`, `just deploy-*`, `/setup-merge`, `claude/settings.json`, and `hooks/cortex-notify.sh`. Its Non-Requirements explicitly hand the per-repo sandbox allowWrite responsibility to ticket 119. After 117, `cortex-command` ships as a CLI + plugins and writes nothing to `~/.claude/`.

### From `lifecycle.config.md` at project root (today's shape — exemplar for the template)

```yaml
---
type: other
test-command: just test
skip-specify: false
skip-review: false
commit-artifacts: true
demo-commands:
  - label: "Dashboard"
    command: "just dashboard"
---

# Lifecycle Configuration

## Review Criteria
...
```

The shipped template should adopt this shape but with `type: other`, `test-command: echo "TODO: set test-command"`, and a commented-out `demo-commands` example.

## Tradeoffs & Alternatives

### D1: Template packaging approach

**Recommended**: inside-package templates dir with `Path(__file__)` pattern — `cortex_command/init/templates/` loaded via `_TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"`. This matches `cortex_command/overnight/prompts/` and `cortex_command/pipeline/prompts/` exactly. No `importlib.resources` (zero prior art in this codebase; pattern mismatch for no gain).

### D2: jq vs pure-Python for the settings.local.json merge

**Ticket specifies jq; adversarial review recommends Python json.** Decision is an Open Question (see OQ1 below). Research finding: the Python path is strictly simpler — no external dep, no shell quoting, uses `cortex_command.common.atomic_write`, testable without subprocess harness. The "use jq" directive appears to be cargo-culted from pre-117 bash; cortex has no other Python-side settings writer to maintain consistency with.

If jq is chosen: use order-preserving `if any(. == $path) then . else . + [$path] end` instead of `| unique` (avoids lexicographic reorder), pre-validate `.sandbox` and `.sandbox.filesystem` are objects before the merge filter, and hard-fail if jq absent.

### D3: Drift detection algorithm for `--update`

**Recommended**: read shipped template bytes, read on-disk file bytes, normalize line endings (`\r\n` → `\n`) only at compare time, and compare via `==`. Noisy drift is acceptable — users can `--force` to reset. No persisted manifest needed because "currently-shipped package content" is available at runtime. `drift_files(target_root: Path) -> list[Path]` returning paths where on-disk differs from shipped.

### D4: Decline-gate predicate when directories already exist

**Adversarial review flipped the earlier recommendation.** Filename-based detection (`lifecycle.config.md`, `backlog/README.md`, `lifecycle/README.md`) has real false-positive risk (`backlog/` is a generic term) and a footgun in the cortex-command repo itself. Instead, use a hidden marker file `.cortex-init` at repo root (contains package version + timestamp). If marker absent and any target dir exists non-empty → decline with an error directing the user to `--update` or `--force`. shadcn's `components.json` pattern.

### D5: Target repo root resolution

**Recommended**: `--path` flag defaults to `$(pwd)`; resolve via `git rev-parse --show-toplevel` inside that path. Non-zero returncode → clear error, exit 2. Matches `cortex_command/pipeline/worktree.py:34` exactly. `--show-toplevel` correctly handles worktrees. **Submodule caveat** (see OQ3): `--show-toplevel` returns the submodule's root, not the parent repo's — the ticket should detect and warn/refuse.

### D6: Template files content (minimum viable)

- **`requirements/project.md`**: stub with `## Overview`, `## Philosophy of Work`, `## Architectural Constraints`, `## Quality Attributes`, `## Project Boundaries` (In Scope / Out of Scope / Deferred), `## Conditional Loading` — matching this repo's structure. TODO placeholders under each. No YAML frontmatter.
- **`backlog/README.md`**: explain schema fields, status vocabulary, link to `backlog/index.md` auto-generated overview. ~30 lines.
- **`lifecycle/README.md`**: explain phases (research → specify → plan → implement → review → complete), artifact layout, `lifecycle.config.md`. ~25 lines.
- **`retros/README.md`**: explain filename convention + problem-only log convention from `/retro`. ~15 lines.
- **`lifecycle.config.md`**: YAML frontmatter shape from this repo's file, populated with `type: other`, `test-command: echo "TODO: set test-command"`, commented-out `demo-commands`, `## Review Criteria` with a TODO bullet.

### D7: `--force` confirmation behavior

**Adversarial review overturned the tradeoffs-agent recommendation.** Bare `--force` without confirmation is unsafe here: `cortex init --force` can silently overwrite an uncommitted, user-hand-crafted `requirements/project.md`. Unlike `git worktree remove --force` (operates on cortex-managed worktrees recoverable from git), `--force` here destroys user authorship that may never have been git-tracked.

**Options for the spec (user decision in OQ2)**:
- (a) Require a second flag (`--force --yes`) — clig.dev pattern.
- (b) Refuse if `git status --porcelain` shows target files as untracked or modified, unless `--yes-really` is also passed.
- (c) Write a backup to `.cortex-init-backup/<timestamp>/` before overwriting (cheap, recoverable).
- (d) Prompt via `input()` when isatty, fall through without prompt when non-interactive.

### D8: Drift-report output format

**Recommended**: bulleted list + hint line to stderr.

```
3 templates differ from shipped versions:
  - backlog/README.md
  - lifecycle/README.md
  - lifecycle.config.md

Overwrite all with shipped: cortex init --force
```

Matches existing `cortex` stderr idiom (`cli.py:33`). JSON output deferred behind a future `--json` flag.

### Cross-cutting: subpackage layout

Follow existing `cortex_command/overnight/` and `cortex_command/pipeline/` layout: `cortex_command/init/{__init__.py, handler.py, scaffold.py, settings_merge.py, drift.py, templates/, tests/}`. Wire `handler.main(args) -> int` into `cli.py:63-68` replacing the stub.

## Adversarial Review

The adversarial agent challenged the synthesized plan and surfaced several real problems. Findings classified by severity:

### HIGH

**H1 — jq expression pitfalls (beyond the ticket body's intent):**
- `| unique` lexicographically reorders the array — use order-preserving `if any(. == $path) then . else . + [$path] end` instead.
- Malformed `.sandbox` / `.sandbox.filesystem` (non-object) causes jq exit 5 with an opaque error — pre-validate before merging and translate to a user-facing diagnostic.
- **Sibling-clobber claim (from `observability.md:111`) does not apply** — that edge case was about `just setup-tmux-socket`'s self-contained-array pattern; ticket 119's deep-path assignment preserves siblings.

**H2 — CLAUDE.md contradiction** (`CLAUDE.md:5` says "nothing is deployed into `~/.claude/` by this repo"; ticket 119 writes to `~/.claude/settings.local.json`). Must be resolved as part of this ticket — the "rules-only" auto-memory and line-5 absolute statement actively misinform future work if left unreconciled. See OQ4.

**H3 — `--force` without prompt is dangerous here**. `cortex init --force` can overwrite uncommitted user authorship (`requirements/project.md`). Unlike `git worktree remove --force`, this destroys work with no reconstruction path. See OQ2.

**H4 — Filename-based decline-gate is fragile**: generic filename `backlog/README.md` has real false-positive risk; the cortex-command repo itself has all three proposed marker files. Use a hidden `.cortex-init` marker file (version + timestamp) instead. See OQ2.

### MEDIUM

**M1 — jq-hard-fail is a poor first-run UX**. jq is absent on default macOS and most minimal Linux images. Python `json` handles this trivially with zero new deps. The "use jq" directive is worth reversing. See OQ1.

**M2 — Architectural drift: the allowWrite registration has no DR behind it**. DR-5/DR-7 are silent on it; the handoff from 117 was procedural. `spec.md` should include a new DR ("cortex init owns per-repo sandbox allowWrite — narrow exception because the path is per-repo and resolved from pwd at init time") to avoid implicit decisions. This is a spec-phase action, not an open question.

**M3 — Unregister / GC gap**. The ticket has no cleanup path. Repos that are deleted or moved leak allowWrite entries; registering across many repos causes unbounded array growth. See OQ5.

**M4 — `cortex upgrade` relationship undefined**. Future verb; unclear whether it propagates template updates across registered repos. Post-install message should clarify: "cortex upgrade updates the CLI; run `cortex init --update` per-repo to refresh templates."

**M5 — Test infrastructure precedent exists but tradeoffs agent missed it**: `tests/test_runner_signal.py:95` uses `monkeypatch.setenv("HOME", str(tmp_path))`. No new harness needed.

### LOW

**L1 — Drift `==` compare is fine.** Trailing whitespace / BOM / CRLF are bounded edge cases; noisy drift is recoverable via `--force`.
**L2 — `atomic_write` with `durable_fsync` is safe for settings.local.json.**
**L3 — `--show-toplevel` is the right git check** (slightly stronger than `--is-inside-work-tree` — returns the canonical path + repo-ness in one call).

### Security

**S1 — Submodule context is subtle**. `git rev-parse --show-toplevel` inside a submodule returns the submodule's root, not the parent's. Overnight sessions inside a submodule is unusual. Detect via `git rev-parse --show-superproject-working-tree`; refuse or warn before registering. See OQ3.

**S2 — Symlink traversal at registration time**. If `lifecycle/sessions/` is a pre-existing symlink pointing outside the repo, registering allowWrite for that path grants the sandbox write access to wherever the symlink resolves. Before writing the allowWrite entry, `Path.resolve(strict=False)` on `lifecycle/sessions/` (if it exists) and compare to the repo root; refuse if resolution escapes the repo.

**S3 — PATH-influenced jq execution**. Another reason to prefer Python `json`.

## Open Questions

These are spec-level decisions the Specify phase's structured interview is designed to resolve. Each is tagged **Deferred: will be resolved in Spec by asking the user** — research cannot resolve them by reading more code. Several overlap: OQ1 (jq/json) influences OQ6 (DR wording), and OQ2 (force safety) is tightly coupled to OQ3 (decline-gate marker).

1. **jq vs Python `json` for the settings.local.json merge**: ticket body says "use jq, fall back to a clear error if jq is absent"; adversarial case for Python `json` is strong (no external dep, no shell-quoting, simpler tests, uses existing `atomic_write`). Options: Python json, keep jq, or jq-preferred-with-Python-fallback.
   *Deferred: will be resolved in Spec by asking the user — this is a user-facing direction change from the ticket body, warrants explicit sign-off.*

2. **`--force` destructive-overwrite guard**: bare `--force` risks destroying uncommitted user authorship in `requirements/project.md`. Options: (a) `--force --yes` required; (b) refuse on dirty git status unless `--yes-really`; (c) `.cortex-init-backup/<timestamp>/` before overwriting; (d) `input()` prompt when isatty.
   *Deferred: will be resolved in Spec by asking the user — preference-level UX decision.*

3. **Decline-gate predicate**: filename-based detection (`lifecycle.config.md`, `backlog/README.md`, …) has real false-positive risk and misfires inside the cortex-command repo. Recommended alternative: hidden `.cortex-init` marker file at repo root (package version + init timestamp), shadcn's `components.json` pattern.
   *Deferred: will be resolved in Spec by asking the user — introduces a new artifact the user must accept.*

4. **CLAUDE.md reconciliation**: `CLAUDE.md:5` says "nothing is deployed into `~/.claude/` by this repo"; ticket 119 contradicts this. Does the ticket include the CLAUDE.md edit in-scope, or is it a separate ticket?
   *Deferred: will be resolved in Spec by asking the user — scope-expansion call.*

5. **Unregister / GC verb**: should this ticket include `cortex init --unregister` (removes `$(pwd)/lifecycle/sessions/` from `allowWrite`), or is leaking stale entries acceptable? Small additional subcommand reusing the settings-merge path in reverse.
   *Deferred: will be resolved in Spec by asking the user — scope-expansion call.*

6. **Retroactive DR for allowWrite registration**: `spec.md` should codify "`cortex init` owns per-repo sandbox allowWrite — narrow DR-5 exception because the path is per-repo and resolved from pwd at init time." Agreement on framing before Specify writes it?
   *Deferred: will be resolved in Spec by asking the user — DR framing benefits from user review before being committed to spec.*

7. **Submodule handling**: `cortex init` inside a git submodule registers the submodule path, not the parent repo's. Refuse, warn, or allow silently?
   *Deferred: will be resolved in Spec by asking the user — depends on whether submodule use is in-scope for cortex.*

8. **Symlink safety for `lifecycle/sessions/`**: before writing the allowWrite entry, resolve `lifecycle/sessions/` (if it exists) and refuse if it escapes the repo root? Small safety guard.
   *Deferred: will be resolved in Spec by asking the user — adds one more constraint the user should see before it lands.*
