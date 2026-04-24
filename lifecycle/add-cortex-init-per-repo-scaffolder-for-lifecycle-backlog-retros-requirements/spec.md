# Specification: Add `cortex init` per-repo scaffolder

> Epic reference: [`research/overnight-layer-distribution/research.md`](../../research/overnight-layer-distribution/research.md) DR-7 (shadcn-style per-repo scaffolding). See `research.md` for codebase findings, tradeoffs, and adversarial review.

## Problem Statement

cortex-command's `lifecycle/`, `backlog/`, `retros/`, and `requirements/` directories hold content that semantically belongs to the user's project (feature plans, ticket history, retrospectives, project vision). Today, users must hand-create these directories and their templates when onboarding cortex-command into a target repo — there is no verb that materializes the scaffolding. Ticket 117 retired `just setup`'s "create `lifecycle/sessions/` allowWrite entry in `~/.claude/settings.local.json`" step when it collapsed the whole shareable-install scaffolding, and its Non-Requirements handed that responsibility to this ticket. Without a per-repo verb, new cortex-command adopters face manual directory creation and a silent sandbox-write failure mode when they try to use the dashboard or interactive status CLI against overnight session state. `cortex init` closes both gaps: scaffolds the four content directories from shipped templates and additively registers the repo's `lifecycle/sessions/` path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array.

## Architectural Decision Records

**ADR-1 — `cortex init` owns per-repo sandbox allowWrite registration** *(narrow DR-5 exception, drafted here because epic 113 research did not cover this concern)*. The sandbox `allowWrite` entry registered by this ticket is a **per-repo path** that must be resolved from `pwd` (or `--path`) at init time. No machine-scoped verb like a revived `cortex setup` could do this without an explicit per-repo re-invocation — the path is a function of which repo the user is onboarding. Bundling the registration under `cortex init`, where the repo is already the invocation context, is the correct home. DR-5's "cortex setup owns `~/.claude/` deployment" framing was written before ticket 117 inverted scope and retired `cortex setup`; after 117, the surviving architecture is "cortex-command writes nothing to `~/.claude/`" (CLAUDE.md:5). This ADR narrows that claim to: cortex-command writes exactly one additive entry in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array per `cortex init` invocation; no content, no symlinks, no other `~/.claude/` writes.

**ADR-2 — `fcntl.flock` guards the `settings.local.json` read-modify-write** *(closes concurrency lost-update race)*. `cortex_command.common.atomic_write` guarantees byte-level atomicity of the file replacement but not semantic atomicity of the read → mutate → write cycle. Two concurrent `cortex init` (or `--unregister`) invocations against the same `~/.claude/settings.local.json` can each read a pre-state, append/remove their respective entry, and last-writer-wins silently drops one change. Since `--path` makes `cortex init` scriptable across repos and the framework's north-star workload is autonomous multi-hour execution, this race is reachable in the primary workload. The fix: wrap the entire read-mutate-write with `fcntl.flock` on `~/.claude/settings.local.json` (LOCK_EX). `fcntl` is stdlib; no new dependency. Behavior: lock acquired before read, held across jq-equivalent mutation, released after `os.replace` completes. Lock file is `settings.local.json` itself (same inode, `fcntl.flock` semantics); no separate lockfile artifact. Concurrent callers serialize through the kernel's advisory lock; each sees the prior writer's mutation. This applies to both `cortex init` (append) and `cortex init --unregister` (remove).

**ADR-3 — Operation ordering: pre-flight checks → scaffold → marker → settings.local.json** *(closes partial-failure lying-state scenarios)*. The two mutating operations (template scaffolding + marker, and settings.local.json merge) must land in a defined order so partial failure produces a recoverable state. Mandated ordering:
1. All pre-flight gates (git-repo check R2, submodule R3, decline-gate R6/R19, symlink safety R13, malformed-settings R14) run **before any write**. Any gate failure exits 2 with zero filesystem mutation (repo or `~/.claude/`).
2. Templates scaffold into the target repo (all five files).
3. `.cortex-init` marker writes last among repo-side operations.
4. `~/.claude/settings.local.json` merge runs last of all.

Rationale: pre-flight checks that inspect the target repo (symlink safety) must run before scaffolding so they reflect pre-invocation state, not post-scaffold state. Settings merge runs last because its pre-flight check (R14 malformed settings) inspects a file the user owns; if the check fires after scaffold, the repo is dirty. By ordering settings-last, if the settings merge fails (disk full, `~/.claude` permission, malformed settings, SIGINT mid-write), the repo is fully scaffolded (with marker) but missing only the sandbox registration. Recovery contract: `cortex init --update` re-attempts the settings merge idempotently (R11's `in` check) and does not rescaffold files that exist — making `--update` the canonical recovery verb for post-scaffold failures. No rollback semantic is required: scaffold completes atomically (each file via `atomic_write`), marker writes atomically, settings merge is protected by ADR-2's lock + atomic write. There is no in-between state that needs cleanup.

## Requirements

1. **Subcommand exists and wires into the CLI** — `cortex init --help` prints usage including `--path`, `--update`, `--force`, `--unregister` flags.
   *Acceptance*: `cortex init --help | grep -E -- '(--path|--update|--force|--unregister)' | wc -l` = 4; exit 0.

2. **Hard-fail outside a git repo** — when invoked in a directory whose `git rev-parse --show-toplevel` returns non-zero, `cortex init` prints a clear stderr message and exits 2.
   *Acceptance*: in a `tmp_path` that is not a git repo, `cortex init` exit code = 2; stderr contains `not inside a git repository`.

3. **Hard-fail inside a git submodule** — when `git rev-parse --show-superproject-working-tree` returns a non-empty path (indicating submodule context), `cortex init` prints a clear stderr message ("cortex init should run at the top-level repo, not inside a submodule") and exits 2.
   *Acceptance*: in a fixture submodule, `cortex init` exit code = 2; stderr contains `submodule`.

4. **Default invocation scaffolds all five templates into the repo root** — `cortex init` in a fresh git repo creates `lifecycle/README.md`, `backlog/README.md`, `retros/README.md`, `requirements/project.md`, and `lifecycle.config.md`, plus an `.cortex-init` marker file at the repo root. The scaffolder also appends `.cortex-init` and `.cortex-init-backup/` to the repo's `.gitignore` (creating the file if absent), so the marker is treated as per-machine onboarding state and does not ship to teammates via VCS.
   *Acceptance*: after `cortex init` in `tmp_path` (git-init'd), all six files exist with non-zero size; `.gitignore` exists and contains both `.cortex-init` and `.cortex-init-backup/` as separate lines.

5. **`.cortex-init` marker file contains package version and ISO-8601 timestamp** — the marker is a JSON object with `cortex_version` (from the installed package) and `initialized_at` fields.
   *Acceptance*: `python3 -c "import json; d=json.load(open('.cortex-init')); assert 'cortex_version' in d and 'initialized_at' in d"` exits 0.

6. **Default invocation declines when `.cortex-init` marker is present** — re-running `cortex init` (no flags) in a repo where `.cortex-init` already exists prints a clear stderr message directing the user to `--update` or `--force`, and exits 2.
   *Acceptance*: after two consecutive `cortex init` invocations, the second exit code = 2; stderr contains `already initialized`.

7. **`--path <dir>` retargets the invocation** — `cortex init --path <absolute-path-to-git-repo>` behaves identically to running `cortex init` from inside that directory.
   *Acceptance*: `cortex init --path <tmp_repo>` from an unrelated cwd produces the five template files + marker at `<tmp_repo>`; exit 0.

8. **`cortex init --update` writes missing template files and leaves existing files untouched** — for each shipped template, if the corresponding file is absent from the repo it is written; if present it is not modified, even if its content differs from the shipped template.
   *Acceptance*: after `cortex init`, editing `requirements/project.md` to contain the literal string `USER-EDIT-SENTINEL`, deleting `retros/README.md`, and running `cortex init --update`: `grep -c USER-EDIT-SENTINEL requirements/project.md` = 1, and `retros/README.md` is recreated; exit 0.

9. **`cortex init --update` prints a drift report to stderr** — after the update completes, `cortex init` lists files whose on-disk content (with line-ending normalization) differs from the currently-shipped template. Output format: one bullet per drifted file (path relative to repo root) + a hint line recommending `--force` to reset. Stdout remains empty; drift report goes to stderr.
   *Acceptance*: after editing `lifecycle/README.md` to contain `DRIFT-TEST`, `cortex init --update` stderr contains `lifecycle/README.md`; stderr contains `--force` in the hint line.

10. **`cortex init --force` backs up existing files before overwriting** — for each existing file in the five template paths, `cortex init --force` copies the current content to `.cortex-init-backup/<UTC-timestamp>/<relative-path>` before writing the shipped template. R4's `.gitignore` append already covers `.cortex-init-backup/`, so `--force` does not need to re-mutate `.gitignore` — it verifies the pattern is present and appends with newline-safety if not (same logic as R4).
   *Acceptance*: after editing `requirements/project.md` to contain `FORCE-BACKUP-SENTINEL` and running `cortex init --force`: file exists at `.cortex-init-backup/<timestamp>/requirements/project.md` containing `FORCE-BACKUP-SENTINEL`; `.gitignore` contains `.cortex-init-backup/` on its own line; final byte of `.gitignore` is `\n`.

11. **`cortex init` additively registers `$(repo-root)/lifecycle/sessions/` in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array** — the path appended is `<repo-root-resolved>/lifecycle/sessions/` with trailing slash. The merge uses Python's `json` module (not jq) and is serialized across concurrent callers via `fcntl.flock(settings_fd, LOCK_EX)` held for the full read-mutate-write window (see ADR-2). If `~/.claude/settings.local.json` does not exist, it is created with a minimal `{"sandbox": {"filesystem": {"allowWrite": [<path>]}}}` object. If it exists, existing keys (including `sandbox.network.allowUnixSockets`, `permissions.allow`, etc.) are preserved; only the `sandbox.filesystem.allowWrite` array is mutated. Insertion order is preserved — no lexicographic reorder. The path is not duplicated if already present (idempotent).
    *Acceptance*: in a fixture with `HOME` pointed at `tmp_path`, after `cortex init`: `python3 -c "import json; d=json.load(open('$tmp_path/.claude/settings.local.json')); assert '$repo/lifecycle/sessions/' in d['sandbox']['filesystem']['allowWrite']"` exits 0. Running `cortex init` twice does not duplicate the entry (array length unchanged after second run). If the fixture pre-populates `permissions.allow` or `sandbox.network.allowUnixSockets`, those keys exist unchanged after `cortex init`.

12. **Atomic settings.local.json write** — the merge uses `cortex_command.common.atomic_write` (or equivalent tempfile + `os.replace()` pattern on the same filesystem).
    *Acceptance*: `grep -n 'atomic_write\|os.replace\|tempfile.mkstemp' cortex_command/init/settings_merge.py | wc -l` ≥ 1.

13. **Refuse to register allowWrite if `lifecycle/sessions/` resolves outside the repo** — if `lifecycle/sessions/` already exists as a symlink (or a directory containing symlink components) and `Path(lifecycle/sessions/).resolve(strict=False)` is not a subpath of the repo root, `cortex init` prints a clear stderr message and exits 2 before any settings.local.json write.
    *Acceptance*: in a fixture where `lifecycle/sessions/` is symlinked to `$TMPDIR/escape/`, `cortex init` exit code = 2; stderr contains `escape` or `outside the repo`; `$HOME/.claude/settings.local.json` is unchanged (compare byte-for-byte to pre-invocation snapshot).

14. **Malformed `sandbox` / `sandbox.filesystem` translated to user-facing diagnostic** — if `~/.claude/settings.local.json` exists but `.sandbox` or `.sandbox.filesystem` is a non-object type (string, number, null, array), `cortex init` prints a clear stderr message ("`~/.claude/settings.local.json`: expected `sandbox.filesystem` to be an object, got `<type>`") and exits 2 without mutating the file.
    *Acceptance*: in a fixture with `{"sandbox": "broken"}` in settings.local.json, `cortex init` exit code = 2; stderr contains `expected`; file is unchanged byte-for-byte.

15. **`cortex init --unregister` removes the current repo's `lifecycle/sessions/` entry from allowWrite** — idempotent: removing an absent entry is a no-op success. Other allowWrite entries are preserved. Like R11, the read-mutate-write cycle is serialized via `fcntl.flock(settings_fd, LOCK_EX)` (ADR-2) so concurrent `init`/`--unregister` calls do not lose unrelated entries.
    *Acceptance*: after `cortex init` followed by `cortex init --unregister`: `python3 -c "import json; d=json.load(open('$HOME/.claude/settings.local.json')); assert '$repo/lifecycle/sessions/' not in d.get('sandbox', {}).get('filesystem', {}).get('allowWrite', [])"` exits 0. Running `--unregister` twice does not error.

16. **CLAUDE.md line 5 updated** — the project CLAUDE.md's "What This Repo Is" section (line 5) no longer asserts an absolute "nothing is deployed into `~/.claude/`" claim; it reflects the narrow additive `settings.local.json` write registered by `cortex init`.
    *Acceptance*: `grep -c 'settings.local.json' CLAUDE.md` ≥ 1; `grep -c 'nothing is deployed' CLAUDE.md` = 0; `grep -c 'sandbox.filesystem.allowWrite\|allowWrite array' CLAUDE.md` ≥ 1 (verifies the narrowed claim names the specific write surface rather than vague wording).

17. **Bootstrap post-install message mentions `cortex init`** — the bootstrap installer's post-install output (wherever it lives today — `docs/setup.md`, `README.md`, or the eventual bootstrap script) documents that `cortex init` must be run once per target repo.
    *Acceptance*: `grep -l 'cortex init' docs/ README.md 2>/dev/null | wc -l` ≥ 1; the referenced location is non-empty when grepped for `cortex init`.

18. **Tests cover the happy path, update path, force path, decline gate (marker + content-aware), allowWrite merge (pre-existing + fresh), unregister, symlink refusal, submodule refusal, malformed settings.local.json, concurrency (flock), partial failure (settings write raises after scaffold; `--update` recovers), and SIGINT mid-merge (lock released)** — automated tests under `cortex_command/init/tests/` exercise each requirement above.
    *Acceptance*: `just test` exits 0. `grep -l 'test_' cortex_command/init/tests/*.py | wc -l` ≥ 2. Concurrency test uses `multiprocessing` or `threading` to launch two merges against the same fixture HOME and asserts both entries are present after both complete. Partial-failure test forces `settings_merge` to raise after scaffold, asserts scaffold + marker present but settings unchanged, then runs `cortex init --update` and asserts the settings entry lands.

19. **Content-aware decline: default invocation refuses on populated non-marker repos** — when `.cortex-init` marker is absent AND any of the five scaffold target paths already exists (directory non-empty OR file present), `cortex init` (no flags) prints a clear stderr message ("`cortex init`: one or more target paths exist with pre-existing content (no `.cortex-init` marker). Run `cortex init --update` to add missing templates without overwriting, or `cortex init --force` to overwrite with backup.") and exits 2. This prevents default invocation from clobbering content in repos that predate `cortex init` or that happen to have cortex-shaped directories (e.g., cortex-command's own repo during maintainer work).
    *Acceptance*: in a `tmp_path` git-init'd with a pre-existing `lifecycle/` directory containing `unrelated.md`, `cortex init` exit code = 2; stderr contains `pre-existing content`; no scaffold files are written; `~/.claude/settings.local.json` unchanged byte-for-byte.

20. **`cortex init --update` refreshes marker fields** — when `.cortex-init` is already present at invocation time, `--update` rewrites it with the current package's `cortex_version` and a fresh `initialized_at` timestamp. This prevents marker staleness after `cortex upgrade` + `cortex init --update` cycles.
    *Acceptance*: after `cortex init` at cortex version v0.1.0 (fixture-injected), mocking the installed version to v0.2.0 and running `cortex init --update`: `python3 -c "import json; d=json.load(open('.cortex-init')); assert d['cortex_version'] == '0.2.0'"` exits 0. If `.cortex-init` is absent at `--update` time, it is created (per existing `--update` edge case) with the current version.

21. **Operation ordering and failure ordering** — per ADR-3, `cortex init` executes in this order and halts on the first failure: (1) pre-flight gates (R2, R3, R6, R19, R13, R14) — if any fires, exit 2 with zero filesystem mutation; (2) template scaffolding (R4's five files via `atomic_write`); (3) `.gitignore` mutation (R4's append); (4) marker write (R4, R5 via `atomic_write`); (5) `settings.local.json` merge (R11, R12 under `fcntl.flock`). No rollback on (2)–(5) failure; recovery is via `cortex init --update` per R20 and R11's idempotence.
    *Acceptance*: Simulate settings-merge failure (fixture forces `atomic_write` in `settings_merge.py` to raise `OSError("disk full")`) and verify: scaffold files exist (steps 2–3 completed), `.cortex-init` exists with correct fields (step 4 completed), `~/.claude/settings.local.json` byte-unchanged (step 5 failed), `cortex init` exit code ≠ 0 with clear stderr naming the failed operation. Follow-up: run `cortex init --update` (fixture restores normal behavior), assert `settings.local.json` now contains the entry and exit 0.

## Non-Requirements

- **Opinionated project-type tailoring** (`--type library`, `--type app`) — deferred per ticket 119 out-of-scope; a later enhancement.
- **Migration from existing non-cortex layouts** — if the user has a pre-existing `backlog/` with unrelated content, `cortex init` declines; there is no merge or import verb for legacy content.
- **Drift auto-merge on `--update`** — `--update` is strictly additive. 3-way merge (copier-style) is explicitly out of scope; the drift report is a read-only signal.
- **`cortex upgrade` integration** — whether `cortex upgrade` propagates template updates across registered repos is out of scope for this ticket. Post-install docs must note that users run `cortex init --update` per-repo.
- **Interactive confirmation prompts** — `cortex init` never prompts via `input()`. `--force` is the only destructive verb; its safety net is the timestamped backup, not a prompt.
- **Structured drift output (table, JSON)** — the drift report is a bulleted stderr list. Machine-readable output is deferred behind a future `--json` flag.
- **jq-based merge path** — ruled out during Specify in favor of Python `json`. This is a deliberate departure from the ticket body's "use jq" directive.
- **`--dry-run` mode** — out of scope; the drift report provides read-only visibility for the update case.
- **Revalidating the registered path after the fact** — `cortex init` registers `$(repo-root)/lifecycle/sessions/` once per invocation; it does not later detect stale entries for deleted repos (use `--unregister` manually before removing a repo).

## Edge Cases

- **`cortex init` run from a subdirectory of the repo**: `git rev-parse --show-toplevel` returns the repo root; scaffolding lands at the root, not the subdirectory. No warning.
- **`~/.claude/` does not exist**: `cortex init` creates `~/.claude/` (`mkdir -p`) before writing `settings.local.json`.
- **`~/.claude/settings.local.json` exists but is not valid JSON**: `cortex init` prints a clear stderr error (`settings.local.json: invalid JSON at line X:Y`) and exits 2 without mutating the file.
- **`.cortex-init` marker exists but target directories are empty**: `cortex init` (no flags) still declines — the marker is the authoritative signal. User must `--update` or `--force`.
- **`.gitignore` does not exist when `--force` runs**: `cortex init --force` creates `.gitignore` with the single line `.cortex-init-backup/`.
- **`.gitignore` already contains `.cortex-init-backup/` or `.cortex-init-backup/**` or equivalent**: do not add a duplicate line; idempotent append.
- **`--force` in a repo where templates already match shipped content**: `cortex init --force` still backs up (backup contains identical content) before overwriting. The backup is harmless; no special-casing.
- **`--update` in a repo with no prior `cortex init`**: `--update` does not gate on the marker. It writes missing template files and reports drift. If `.cortex-init` does not exist, `--update` writes it (same content as a fresh default invocation); if `.cortex-init` already exists, it is preserved unchanged.

- **User deletes repo without running `cortex init --unregister`**: the stale allowWrite entry is harmless (allow for nonexistent path is a no-op). A *distinct* failure — concurrency-loss producing an on-disk state identical to "never registered" — is prevented by ADR-2's lock, not by this edge case's framing.
- **`cortex init --unregister` run in a repo that was never initialized**: exits 0 silently after verifying the target entry is absent from allowWrite.
- **Concurrent `cortex init` invocations** (e.g., two worktrees, parallel scripted onboarding, fan-out from a future `cortex upgrade`): the `settings.local.json` read-mutate-write is serialized under `fcntl.flock(settings_fd, LOCK_EX)` per R11/R15 and ADR-2. Both entries land; no lost-update race. Kernel advisory lock provides ordering; each caller observes the prior caller's mutation before acquiring the lock itself.
- **Concurrent `cortex init --unregister` racing an `init`**: same flock protection — the unregister reads a post-init pre-state, removes only the specified entry, and writes back. Unrelated entries survive.
- **Settings.local.json with `sandbox.filesystem` present but `allowWrite` absent**: the merge creates the `allowWrite` array with the single entry; sibling keys under `sandbox.filesystem` are preserved.
- **`lifecycle/sessions/` exists as a regular directory (not a symlink)**: symlink safety check passes (resolved path equals the literal path). Registration proceeds.
- **`lifecycle/sessions/` does not exist yet**: symlink safety check is skipped (nothing to resolve). Registration proceeds. `cortex init` does not create `lifecycle/sessions/` — the overnight runner creates it on demand.
- **CLAUDE.md does not exist at the repo root**: CLAUDE.md edit requirement (R16) applies only to cortex-command's own CLAUDE.md (the repo where `cortex init` is being developed, not the target scaffolded repo). This is a one-time edit to THIS repository's CLAUDE.md as part of landing the ticket, not a per-invocation behavior.
- **`.cortex-init` accidentally committed to a shared repo**: prevented by R4's `.gitignore` append (adds `.cortex-init` at init time). If a teammate does commit the marker manually, a subsequent clone + `cortex init` by another user hits R6's decline. User's recovery: `rm .cortex-init && cortex init`. Non-goal: automatic recovery from committed markers.
- **Partial failure: settings merge fails after scaffold + marker land** (disk full on `$HOME` filesystem, PermissionError on `~/.claude/`, malformed-settings check fires after ordering bug-fix — it no longer does, since R14 runs in pre-flight): ordering per ADR-3 + R21 guarantees scaffold and marker complete before settings merge attempts. On failure, user sees stderr naming the failed operation + exit ≠ 0. Recovery: `cortex init --update` (R20 refreshes marker; R11 idempotence re-attempts settings merge).
- **`cortex init` invoked in cortex-command's own repo** (all four scaffold target dirs populated with canonical content, no `.cortex-init` marker): R19 content-aware decline fires; default invocation exits 2. Maintainers who need to regenerate specific files inside cortex-command use `--force` (backs up canonical content to `.cortex-init-backup/` first) or hand-copy from `cortex_command/init/templates/`. `cortex init --update` is also safe (strictly additive) but degenerate (everything already exists; drift report lists all five files because cortex-command's own files are the source-of-truth, not drift).
- **SIGINT / SIGTERM mid-settings-merge**: the flock is process-scoped; kernel releases it on process exit. Next `cortex init` or `--update` acquires the lock cleanly. Since the write is atomic (`atomic_write`'s tempfile + `os.replace()`), either the old bytes or the new bytes are on disk — no torn file. The allowWrite entry may or may not have landed depending on when the signal arrived; `cortex init --update` safely re-attempts.

## Changes to Existing Behavior

- **MODIFIED**: `cortex_command/cli.py:63-68` — the `init` subparser's stub handler (`_make_stub("init")`) is replaced with a real handler dispatching to `cortex_command/init/handler.py`. The stub exit code 2 is preserved for error paths.
- **MODIFIED**: `CLAUDE.md:5` — the "nothing is deployed into `~/.claude/` by this repo" claim is narrowed to reflect the single additive `settings.local.json` write registered by `cortex init`.
- **ADDED**: new subpackage `cortex_command/init/` with `handler.py`, `scaffold.py`, `settings_merge.py`, `templates/`, `tests/`.
- **ADDED**: CLI flags `--path <dir>`, `--update`, `--force`, `--unregister` on the `init` subcommand.
- **ADDED**: `.cortex-init` marker file as the decline-gate signal in scaffolded repos; added to `.gitignore` on scaffold (per-machine onboarding state).
- **ADDED**: `.cortex-init-backup/` as a `--force`-only backup location in scaffolded repos; added to `.gitignore` on scaffold.
- **ADDED**: content-aware decline gate (R19) closes the clobber footgun in populated non-marker repos.
- **ADDED**: `fcntl.flock`-serialized `settings.local.json` merge (R11, R15, ADR-2) closes the read-modify-write race.
- **ADDED**: explicit operation ordering contract (R21, ADR-3) closes partial-failure lying-state scenarios.
- **ADDED (indirect)**: cortex-command now writes to `~/.claude/settings.local.json` during `cortex init` — the first and only `~/.claude/` write after ticket 117's retirement of `cortex setup`.

## Technical Constraints

- **Python 3.12+** (per `pyproject.toml:6`).
- **No new runtime dependencies** — use standard library (`json`, `pathlib`, `subprocess`, `shutil`, `os`, `hashlib`, `datetime`, `fcntl`). Specifically: do not add jq as a dependency; the merge uses Python `json` (see ADR-1). `fcntl.flock` is stdlib on POSIX (macOS, Linux); no Windows support is needed because cortex-command is POSIX-only today.
- **Template packaging** via `Path(__file__).resolve().parent / "templates"` — matches `cortex_command/overnight/prompts/` and `cortex_command/pipeline/prompts/` convention. Hatch's wheel build already ships non-Python files inside `cortex_command/`; no `MANIFEST.in` / `package_data` wiring needed.
- **Atomic writes** via `cortex_command.common.atomic_write(path, content)` for all file mutations (both template materialization and settings.local.json). Reuses existing `tempfile.mkstemp` + `durable_fsync` + `os.replace` pattern at `cortex_command/common.py:366-406`.
- **Git-repo detection** via `subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path, check=False, capture_output=True, text=True)`; non-zero returncode is the hard-fail signal. Matches `cortex_command/pipeline/worktree.py:34-42` exactly.
- **Submodule detection** via `subprocess.run(["git", "rev-parse", "--show-superproject-working-tree"], ...)`; non-empty stdout = inside a submodule.
- **Tests use `monkeypatch.setenv("HOME", str(tmp_path))`** for settings.local.json merge tests — existing pattern from `tests/test_runner_signal.py:95`. No new HOME-mocking harness needed.
- **Tests must use `pytest` with `tmp_path` fixture** for repo and HOME isolation; no real mutation of the developer's `~/.claude/settings.local.json` during test runs.
- **Drift comparison** uses simple byte-level `==` after line-ending normalization (`\r\n` → `\n`). No hashing; no similarity ratio; no persisted manifest.
- **Array dedup** in the allowWrite merge uses order-preserving `in` check (not `set()` or sort-based uniqueness). The existing user's `allowWrite` ordering is preserved exactly; the new entry appends if absent.
- **Backup directory naming** uses ISO-8601 UTC timestamp with filesystem-safe characters: `.cortex-init-backup/2026-04-24T14-30-00Z/` (colons replaced with hyphens for Windows-friendliness, though Windows is not in-scope for cortex-command today).
- **Sensitive-path resolution** for symlink safety uses `Path.resolve(strict=False)` then string-prefix comparison against the repo root resolved the same way. Both sides resolved for correctness.
- **Commit discipline**: all code ships via `/commit` (CLAUDE.md convention); the commit hook validates subject-line format.
- **Backlog integration**: on completion, the backlog item's `status` transitions to `complete` and `lifecycle_phase` becomes `complete` via the existing write-back mechanism.

## Open Decisions

*None at spec time.* All research open questions were resolved via the §2 interview and critical thinking per user direction.
