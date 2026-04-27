# Plan: apply-post-113-audit-follow-ups-stale-doc-cleanup-lifecycle-archive-run-mcp-hardening

## Overview

Land seven post-#117 audit follow-ups in research-recommended order: S5 first (establishes JSON-RPC error envelope), S1 second (reuses that envelope on FNF retry-exhaust), N3/N4/N8/N9 stale-doc batch (independent text edits), and N6 last (largest blast radius — recipe enhancements then sample-then-full archive runs). MCP hardening is consolidated in `plugins/cortex-overnight-integration/server.py` as one cohesive change set; archive-recipe path-rewriting is decomposed so each algorithmic concern (slash, wikilink, word-boundary regex) can be verified independently before the destructive run.

## Tasks

### Task 1: Define `CortexCliMissing(OSError)` + S5 startup check + shared error helper
- **Files**: `plugins/cortex-overnight-integration/server.py`
- **What**: Foundation for S1+S5. Adds the typed exception, the module-import-time `shutil.which("cortex")` warning, and a helper that constructs the `mcp.types.McpError` envelope used by retry-exhaust and any other surface needing identical envelope contents.
- **Depends on**: none
- **Complexity**: simple
- **Context**: New class `CortexCliMissing(OSError)` near top of `server.py` (after imports, before `_CORTEX_ROOT_CACHE` declaration at line 191). Helper signature: `def _raise_cortex_cli_missing() -> NoReturn` raises `mcp.types.McpError(code=-32000, message=..., data={"reason": "cortex_cli_missing", "install_url": "https://github.com/charleshall888/cortex-command#install", "message": "..."})`. Startup branch added at module scope after imports: if `shutil.which("cortex") is None`, log a structured stderr line containing `"cortex CLI not found"` and the install URL; do NOT raise. Confirm `mcp.types.McpError` is the actual class exported by the installed mcp SDK before wiring (acceptance includes import sanity check). Plugin invariant preserved: no `cortex_command.*` import. Reference style: existing stderr NDJSON logging at e.g. `_resolve_cortex_argv` sites.
- **Verification**: `python -c "import sys; sys.path.insert(0, 'plugins/cortex-overnight-integration'); import server; assert issubclass(server.CortexCliMissing, OSError); assert callable(getattr(server, '_raise_cortex_cli_missing', None))"` — pass if exit 0. Plus `grep -F 'class CortexCliMissing(OSError)' plugins/cortex-overnight-integration/server.py | wc -l` = 1.
- **Status**: [ ] pending

### Task 2: Wrap `subprocess.run` in `_get_cortex_root_payload` AND `_run_cortex` (S1.2)
- **Files**: `plugins/cortex-overnight-integration/server.py`
- **What**: Catch `FileNotFoundError` at both subprocess-spawning sites for the `cortex` binary, re-raising as `CortexCliMissing` so downstream handlers can disambiguate. PermissionError and other OSError subtypes pass through unchanged.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Two sites — `_get_cortex_root_payload` body (`subprocess.run` at server.py:217-222) and `_run_cortex` body (`subprocess.run` at server.py:1347). Wrap each in `try/except FileNotFoundError` that re-raises `CortexCliMissing` with the original errno/strerror preserved (use `raise CortexCliMissing(...) from exc`). Spec edge case "S1.2 shebang-interpreter missing": accept conflation — do NOT inspect errno to distinguish missing-cortex from missing-#!-interpreter. The other existing handlers in `_get_cortex_root_payload` (`RuntimeError` for non-zero exit, `json.JSONDecodeError` for parse failure) remain unchanged.
- **Verification**: `grep -nE 'except FileNotFoundError' plugins/cortex-overnight-integration/server.py | wc -l` ≥ 2 — pass if count ≥ 2.
- **Status**: [ ] pending

### Task 3: Cache-clear-and-retry-once at verb-dispatch sites + raise McpError on exhaust (S1.3 + S5.2)
- **Files**: `plugins/cortex-overnight-integration/server.py`
- **What**: At each `_run_cortex` call site that drives a tool body (lines 1417, 1493, 1586, 1666, 1739) plus the standalone `_get_cortex_root_payload` call at line 1485, add a per-tool-call retry counter (local variable, not module-global) that on `CortexCliMissing` clears `_CORTEX_ROOT_CACHE` and retries once. Second `CortexCliMissing` invokes `_raise_cortex_cli_missing()` from Task 1 to surface the McpError envelope.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: Six tool-body sites identified by `grep -n -E '_run_cortex\(|_get_cortex_root_payload\(\)' server.py`: 1417, 1485, 1493, 1586, 1666, 1739. Existing `_maybe_check_upstream` (line 466) and `_maybe_run_upgrade` (line 975, 1077, 1151) are EXCLUDED — they retain swallow-and-skip via their pre-existing `except OSError` clauses (CortexCliMissing inherits from OSError, so the existing handlers fire automatically). Concurrency model: FastMCP's stdio transport runs tool handlers on a single asyncio event loop, and the existing `_delegate_*` helpers call sync `subprocess.run` with no `await` between cache-read and cache-write inside `_get_cortex_root_payload`. The event loop therefore serializes tool calls at the subprocess boundary — two coroutines cannot interleave mid-discovery under the current architecture. The "per-tool-call retry counter (local variable, not module-global)" enforces retry-bound (one cache-clear-and-retry per tool call); it is NOT a cross-coroutine synchronization mechanism. Add a one-line code comment near `_CORTEX_ROOT_CACHE` noting that any future move to `asyncio.to_thread` or thread-pool dispatch will require a lock around the check-then-act in `_get_cortex_root_payload`. Pattern: extract a small `_retry_on_cli_missing(func, *args)` helper if it cleans up the call sites, otherwise inline the try/except at each site (pick the form that keeps each call site under ~10 lines added). Catch surface MUST be exactly `except CortexCliMissing` — never `except OSError`, which would silently absorb `PermissionError` and contradict Task 4 case (c).
- **Verification**: (a) `grep -n -B1 -A6 'except CortexCliMissing' plugins/cortex-overnight-integration/server.py | grep -c '_CORTEX_ROOT_CACHE'` ≥ 1 (cache clear present in retry handler) — pass if count ≥ 1. (b) `grep -nE '(_raise_cortex_cli_missing\(\)|raise CortexCliMissing)' plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 4: Tests for S1+S5 (FNF paths, retry semantics, concurrency, OSError preservation, startup branches, envelope)
- **Files**: `tests/test_mcp_cortex_cli_missing.py` (new file)
- **What**: Single new pytest module covering the eight S1+S5 acceptance behaviors enumerated in the spec.
- **Depends on**: [1, 2, 3]
- **Complexity**: complex
- **Context**: Cases (one test function per case): (a) FNF in `_get_cortex_root_payload` raises `CortexCliMissing` (monkeypatch `subprocess.run` to raise `FileNotFoundError`); (b) FNF in `_run_cortex` raises `CortexCliMissing` (same pattern); (c) `PermissionError` is NOT converted to `CortexCliMissing` (negative test — assert `pytest.raises(PermissionError)`); (d) cache-then-FNF-then-recovery succeeds with one retry (prime cache, monkeypatch `subprocess.run` to raise FNF on first call and succeed on second, verify the dispatched tool call returns success and `_CORTEX_ROOT_CACHE` is repopulated). Single-coroutine test only — under FastMCP's current sync-blocking-subprocess model, asyncio cannot interleave two coroutines mid-cache-clear, so a multi-coroutine test would tautologically pass via cooperative serialization rather than verifying the cache logic; cross-coroutine concurrency safety is documented as out-of-scope until a future refactor introduces real async (see Task 3 Context); (e) **PENDING S5.2 architectural decision** — assertion shape on retry-exhaust depends on the answer to the Veto Surface's S5.2 question (string-return vs raise-McpError vs custom-handler). Test case skeleton is written; final assertion form (text-content vs `error.data.reason` vs raised-exception class) lands once the design is settled; (f) `_maybe_check_upstream` returns its existing sentinel (`None` or equivalent) on `CortexCliMissing` (asserts OSError parentage preserves swallow); (g) startup `shutil.which` returning None emits the expected stderr line (capsys check); (h) byte-equal envelope contents from two different propagation paths — assertion shape also pending S5.2 decision (see (e)). Use `pytest.MonkeyPatch` and `unittest.mock.patch` per existing test patterns in `tests/test_mcp_subprocess_contract.py`.
- **Verification**: `uv run pytest tests/test_mcp_cortex_cli_missing.py -v` — pass if exit 0, all tests pass.
- **Status**: [ ] pending

### Task 5: Update lifecycle skill description (N3.1) and rebuild plugin mirror (N3.2)
- **Files**: `skills/lifecycle/SKILL.md`, `plugins/cortex-interactive/skills/lifecycle/SKILL.md` (auto-regenerated by pre-commit `just build-plugin`)
- **What**: Replace the SKILL.md `description` field at line 3 with the inclusive trigger surface text from spec §N3.1.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Exact replacement string from spec §N3.1: `"Required before editing any file in `skills/`, `hooks/`, `claude/hooks/`, `bin/cortex-*`, `claude/common.py`, `plugins/cortex-pr-review/`, or `plugins/cortex-ui-extras/` — canonical sources for skills, hooks, shared helpers, and hand-maintained plugins. Auto-generated mirrors at `plugins/cortex-interactive/{skills,hooks,bin}/` are regenerated by the pre-commit hook from canonical sources; edit the canonical sources only. Skip only if the user explicitly says to."`. The mirror at `plugins/cortex-interactive/skills/lifecycle/SKILL.md` must NOT be edited directly — the pre-commit hook runs `just build-plugin` and rejects drift. The first commit covering this task triggers the regeneration. Spec §N3.1 acknowledges that `claude/statusline.py` is intentionally excluded from this list (B-class residue, accepted scope).
- **Verification**: After `just build-plugin`, `grep -F 'plugins/cortex-pr-review/' skills/lifecycle/SKILL.md | wc -l` ≥ 1 AND `grep -F '~/.claude/skills' skills/lifecycle/SKILL.md | wc -l` = 0 AND `git diff --quiet plugins/cortex-interactive/skills/lifecycle/SKILL.md` (exit 0, mirror in sync) — pass if all three hold.
- **Status**: [ ] pending

### Task 6: Update diagnose skill illustrative reference + rephrase pedagogy (N4.1, N4.2)
- **Files**: `skills/diagnose/SKILL.md`, `plugins/cortex-interactive/skills/diagnose/SKILL.md` (auto-regenerated)
- **What**: Replace `~/.claude/hooks/` reference at line 148 with `claude/hooks/` AND rephrase the surrounding example so the pedagogy still conveys the absolute-vs-tilde lesson if the original example depends on it.
- **Depends on**: none
- **Complexity**: simple
- **Context**: B-class residue addressed: spec §"Changes to Existing Behavior" notes the surrounding sentence is about absolute-vs-tilde paths in sandbox allowlists; a flat path swap may invalidate the example's teaching point. Read the surrounding 6-10 lines of context at `skills/diagnose/SKILL.md:140-160` and choose either: (a) replace example with a different absolute-vs-tilde case that still uses post-#117-canonical paths, or (b) use a different file unrelated to N4 (e.g., a sandbox allowlist example using `~/.config/...`) so the lesson lands without referencing the retired path. Mirror regeneration follows N3.2 model.
- **Verification**: `grep -F '~/.claude/hooks' skills/diagnose/SKILL.md | wc -l` = 0 AND `git diff --quiet plugins/cortex-interactive/skills/diagnose/SKILL.md` after build (exit 0) — pass if both hold.
- **Status**: [ ] pending

### Task 7: Remove `claude/reference/` row from README "What's Inside" table (N8.1)
- **Files**: `README.md`
- **What**: Delete the table row at line 152 referencing the retired `claude/reference/` directory. No replacement row.
- **Depends on**: none
- **Complexity**: simple
- **Context**: README.md line 152 — the row is part of a markdown table. Verify table rendering still parses after the row is removed (no orphaned column separator).
- **Verification**: `grep -F 'claude/reference' README.md | wc -l` = 0 — pass if count = 0.
- **Status**: [ ] pending

### Task 8: Replace `claude/reference/claude-skills.md` citation in overnight-operations.md (N8.2)
- **Files**: `docs/overnight-operations.md`
- **What**: Swap the citation at line 11 for the upstream Anthropic Agent Skills overview URL plus a brief inline self-contained description of the three-level loading model (so the doc remains readable if the URL moves).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Replacement URL: `https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview`. Inline description: 1-2 sentences naming the three loading levels (Level 1 metadata, Level 2 instructions, Level 3 resources/code) and the progressive-disclosure principle. Research caveat noted: docs.claude.com URLs may shift; the inline description is the durable form.
- **Verification**: `grep -F 'claude/reference' docs/overnight-operations.md | wc -l` = 0 AND `grep -F 'docs.claude.com/en/docs/agents-and-tools/agent-skills' docs/overnight-operations.md | wc -l` ≥ 1 — pass if both hold.
- **Status**: [ ] pending

### Task 9: Remove context-file-authoring reminders from cortex-skill-edit-advisor.sh (N8.3)
- **Files**: `claude/hooks/cortex-skill-edit-advisor.sh`
- **What**: Delete the four reminder lines (current lines 30, 37, 55, 63 — all contain `context-file-authoring.md`). The hook's primary behavior (running `just test-skills` and reporting pass/fail) is unchanged.
- **Depends on**: none
- **Complexity**: simple
- **Context**: This hook is NOT mirrored into `plugins/cortex-interactive/hooks/` (verified: only `cortex-validate-commit.sh`, `cortex-worktree-create.sh`, `cortex-worktree-remove.sh`, `hooks.json` are mirrored), so no plugin-side regeneration is required. After deletion, the four sites will print only the surrounding `just test-skills` reporting; double-check that no surrounding control-flow logic depends on the deleted lines.
- **Verification**: `grep -F 'context-file-authoring' claude/hooks/cortex-skill-edit-advisor.sh | wc -l` = 0 AND `grep -F 'just test-skills' claude/hooks/cortex-skill-edit-advisor.sh | wc -l` ≥ 1 AND `bash -n claude/hooks/cortex-skill-edit-advisor.sh` (syntax check, exit 0) — pass if all three hold.
- **Status**: [ ] pending

### Task 10: Delete setup-github-pat assets across script, justfile, docs (N9.1, N9.2, N9.3)
- **Files**: `claude/hooks/setup-github-pat.sh` (delete), `justfile` (modify), `docs/agentic-layer.md` (modify)
- **What**: Remove the manual-wire helper script and all its callers in three coordinated edits.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Caller enumeration (verified via `git grep -lF 'setup-github-pat'` excluding lifecycle/retros/research/backlog): (1) `claude/hooks/setup-github-pat.sh` — entire file deleted; (2) `justfile` — both `setup-github-pat:` and `setup-github-pat-org:` recipes removed; (3) `docs/agentic-layer.md` line 206 — table row referencing the hook removed. README.md and docs/setup.md were verified to NOT reference setup-github-pat (so no edits there). The acceptance-grep exclusion list (`':!lifecycle/**' ':!retros/**' ':!research/**' ':!backlog/**'`) is intentional: history/audit dirs may legitimately reference the prior name.
- **Verification**: `test ! -f claude/hooks/setup-github-pat.sh` (exit 0) AND `just --list 2>&1 | grep -E 'setup-github-pat(-org)?' | wc -l` = 0 AND `git grep -F 'setup-github-pat' -- ':!lifecycle/**' ':!retros/**' ':!research/**' ':!backlog/**' | wc -l` = 0 — pass if all three hold.
- **Status**: [ ] pending

### Task 11: lifecycle-archive recipe — add --dry-run mode + manifest writer + clean-tree precheck (N6.1, N6.2, N6.5 precheck)
- **Files**: `justfile`
- **What**: Augment the `lifecycle-archive` recipe (currently lines 228-259) with three orthogonal capabilities: a `--dry-run` flag (or sibling `lifecycle-archive-dry-run` recipe) that prints "archive candidates" and "rewrite candidates" sections without performing `mv` or `sed`; manifest writing at `lifecycle/archive/.archive-manifest.jsonl` with NDJSON entries `{"ts", "src", "dst", "rewritten_files"}` written atomically (tempfile + `mv`) before each `mv`; clean-tree precheck (`git diff --quiet HEAD && git diff --quiet --cached HEAD`) at the top of the recipe.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Existing recipe behavior: idempotent, `set -euo pipefail`, iterates `lifecycle/*/events.log` and skips `lifecycle/archive/*`, `lifecycle/sessions/*`, active worktrees. New behavior: dry-run gates the destructive operations behind a single conditional; manifest writing is per-slug, written **after** the rewrite step for that slug completes (so `rewritten_files` reflects on-disk reality, not pre-rewrite grep matches) — append form is `printf '%s\n' "$line" >> "$manifest"` with the recipe holding a flock on the manifest path during the append (guards against concurrent dry-run-then-real interleave). Precheck aborts with a clear error pointing the user to commit/stash. Spec edge case: dry-run also requires clean tree (consistency for downstream consumers). Stale-symlink guard: add `[ -e "$dir" ]` before `realpath` to skip broken symlinks gracefully (spec edge case "N6 stale symlinks"). Dry-run mode does NOT run the rewrite step at all — the "rewrite candidates" section is computed via the same boundary-anchored `grep -lE` that the real run uses for `rewritten_files`, but no in-place edits occur and no backup files are created.
- **Verification**: `just lifecycle-archive --dry-run 2>&1 | grep -E '^(archive candidates|rewrite candidates):' | wc -l` ≥ 2 AND `just lifecycle-archive --dry-run >/dev/null 2>&1; test ! -d lifecycle/archive || test -f lifecycle/archive/.archive-manifest.jsonl || true; ! ls lifecycle/archive/*/events.log 2>/dev/null | head -1` (exit 0; dry-run did not move anything new) AND `grep -F 'git diff --quiet' justfile | wc -l` ≥ 1 — pass if all three hold.
- **Status**: [ ] pending

### Task 12: lifecycle-archive recipe — path-rewriting via Python helper (N6.3)
- **Files**: `bin/cortex-archive-rewrite-paths` (new file), `justfile` (recipe wires the helper into the archive flow)
- **What**: Add post-`mv` path-rewriting for three citation forms across all `*.md` under repo root excluding `.git/`, `lifecycle/archive/`, `lifecycle/sessions/`, and `retros/`. Implemented as a Python helper invoked by the recipe — Python is portable across BSD and GNU regex environments (BSD sed silently no-ops on `\b`, which is the project's stated platform per CLAUDE.md), uses native `re` with explicit lookbehind/lookahead, and emits the `rewritten_files` list as JSON to stdout for the recipe to splice into the manifest. The script does NOT create `.bak` files (Python edits are write-through atomic via tempfile-and-replace), eliminating the trap-and-cleanup machinery and the unscoped-trap user-data hazard.
- **Depends on**: [11]
- **Complexity**: complex
- **Context**: Helper signature: `cortex-archive-rewrite-paths --slug <slug> [--slug <slug>...] [--dry-run]` reads stdin nothing, walks `*.md` under repo root with the four exclusions, applies the three regex forms per slug, writes files in place atomically, prints JSON `{"slug": <slug>, "rewritten_files": [<paths>]}` (one line per slug) to stdout. Slug values are regex-escaped via `re.escape()` before insertion into pattern templates. Three regex forms — anchored on explicit boundary character classes (NOT `\b`, which BSD sed doesn't honor and which incorrectly accepts hyphens as word boundaries):
  - **Slash form**: `(?P<L>(?:^|[^A-Za-z0-9_/-]))lifecycle/{slug_re}/` → `\g<L>lifecycle/archive/{slug}/`
  - **Wikilink form**: `(?P<L>\[\[)lifecycle/{slug_re}(?P<T>[/\]|])` → `\g<L>lifecycle/archive/{slug}\g<T>`
  - **Bare form** (no trailing slash): `(?P<L>(?:^|[^A-Za-z0-9_/-]))lifecycle/{slug_re}(?P<T>(?:[^A-Za-z0-9_/-]|$))` → `\g<L>lifecycle/archive/{slug}\g<T>`
  Boundary character class `[A-Za-z0-9_/-]` treats hyphens AND slashes as "word characters" so `add-foo` does not match inside `add-foo-bar`. Apply patterns in order slash → wikilink → bare for each file (avoids the bare pattern stealing slash-form matches). Use `re.sub` with the named-group replacement. Atomic write: write to `<file>.tmp-archive-rewrite` in same dir, then `os.replace` to original path. After all rewrites for the slug-set complete, the recipe captures stdout JSON and merges into the per-slug manifest entries written in Task 11. Spec edge cases handled: substring collision (`add-foo` vs `add-foo-bar`) — boundary char class treats `-` as word-equivalent so `add-foo` does NOT match inside `add-foo-bar` (verified by unit test on the helper); nested slug references — slash-form rewrites `lifecycle/add-foo/research.md` to `lifecycle/archive/add-foo/research.md`; wikilink variants `[[lifecycle/foo]]`, `[[lifecycle/foo/]]`, `[[lifecycle/foo|x]]`, `[[lifecycle/foo/index]]` — wikilink anchor `(?P<T>[/\]|])` catches `/`, `]`, `|`. Rewrite scope: `*.md` only — non-md citers (`bin/cortex-*`, `claude/hooks/*.sh`, `tests/*.py`, `plugins/**/server.py`) are out of scope and may break post-archive (acknowledged scope limitation; Task 16 verification grep confirms). Place the helper in `bin/` so it ships via the cortex-interactive plugin's `bin/` mirror per CLAUDE.md conventions; mirror auto-regenerated by pre-commit.
- **Verification**: (a) Unit test on the helper logic via `python3 -m pytest bin/cortex-archive-rewrite-paths --doctest-modules` OR a sibling test file `tests/test_archive_rewrite_paths.py` covering: substring collision (`add-foo` does not match inside `add-foo-bar`), all four wikilink terminator variants, slash form, bare form, and slug-with-regex-metacharacters via `re.escape()`. (b) After full run on the sample (verified in Task 15), `grep -rn -E "lifecycle/(slug-1|slug-2|slug-3)/" --include='*.md' . --exclude-dir=.git --exclude-dir=archive --exclude-dir=sessions --exclude-dir=retros | grep -v 'archive/' | wc -l` = 0 (no unrewritten references remain). (c) `find . -name '*.tmp-archive-rewrite' | wc -l` = 0 (atomic write left no temp files). — pass if all three hold.
- **Status**: [ ] pending

### Task 13: Document lifecycle-archive recovery procedure in overnight-operations.md (N6.5 docs)
- **Files**: `docs/overnight-operations.md`
- **What**: Add a section describing the recipe's recovery model: clean-tree precheck on entry, `git checkout -- .` for any mid-run abort, manifest-as-audit-record (NOT rollback mechanism).
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: Section appended to `docs/overnight-operations.md` (the doc-partitioning rule from CLAUDE.md says this doc owns the round loop and operational procedures). Content: the three-step recovery procedure (1. confirm precheck error or mid-run abort; 2. `git checkout -- .` from main repo CWD to revert all uncommitted moves and rewrites; 3. manifest under `lifecycle/archive/.archive-manifest.jsonl` is for audit/inspection only; do NOT script a manifest-driven rollback). One sentence linking to N6.4's two-phase run pattern.
- **Verification**: `grep -F 'lifecycle-archive' docs/overnight-operations.md | wc -l` ≥ 1 AND `grep -F 'git checkout -- .' docs/overnight-operations.md | wc -l` ≥ 1 — pass if both hold.
- **Status**: [ ] pending

### Task 14: Deterministic sample-selection script for N6.4 phase a
- **Files**: `bin/cortex-archive-sample-select` (new file)
- **What**: A small script that emits exactly 5 candidate slugs by deterministic criteria: (1) the dir with the highest cross-reference count; (2) one with zero cross-references; (3) one with only `feature_complete` in events.log and no other artifacts (out-of-band closed); (4) the most-recently-modified eligible dir; (5) the oldest-by-mtime eligible dir.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Inputs: scan `lifecycle/*/events.log` for the `feature_complete` marker (excluding `lifecycle/archive/`, `lifecycle/sessions/`, active worktrees per the existing recipe filters). Cross-reference count: `grep -rln "lifecycle/{slug}\b" --include='*.md' . | wc -l` for each candidate (outside archived/sessions/retros). Out-of-band-closed criterion: eligible dir whose `events.log` has only the `feature_complete` event AND directory contents are limited to `events.log` + `index.md` (no research/spec/plan). Output: 5 slugs, newline-separated, on stdout. Place in `bin/` so it ships via the cortex-interactive plugin's `bin/` mirror per CLAUDE.md conventions; the dual-source pre-commit hook regenerates the mirror. Make the script executable (`chmod +x`).
- **Verification**: `bin/cortex-archive-sample-select | wc -l` = 5 AND `bin/cortex-archive-sample-select | sort -u | wc -l` = 5 (no duplicates) AND `bin/cortex-archive-sample-select | head -1 | xargs -I{} test -d lifecycle/{}` (each slug names a real dir, exit 0) — pass if all three hold.
- **Status**: [ ] pending

### Task 15: Run lifecycle-archive on the 5-dir sample + commit (N6.4 phase a)
- **Files**: `lifecycle/archive/` (created), `lifecycle/{5 sample slugs}/` (moved), `lifecycle/archive/.archive-manifest.jsonl` (written), citing `*.md` files (rewritten by sed)
- **What**: Execute the sample run end-to-end. Use `bin/cortex-archive-sample-select` to choose 5 slugs, archive them via the recipe (constrained to the sample list, e.g. via env var or recipe parameter passing the slug list), verify manifest + path rewriting, commit explicitly labeled "lifecycle-archive sample run".
- **Depends on**: [11, 12, 13, 14]
- **Complexity**: complex
- **Context**: Mechanism: either (a) extend the recipe in Task 11 to accept a `--only-slugs` arg that limits the iteration to the supplied slugs, or (b) temporarily move non-sample slugs out of consideration by running the recipe with `LIFECYCLE_SAMPLE=$(bin/cortex-archive-sample-select)` and an `if` guard. Recipe-repair commits between sample and full ARE explicitly in-scope per spec §N6.4 (user-confirmed during clarify) — if the sample run surfaces bugs in Tasks 11 or 12, fix the recipe with a clearly-labeled "lifecycle-archive recipe repair (post-sample)" commit before proceeding to Task 16. Commit message: `lifecycle-archive sample run: archive {N} representative dirs` per cortex-command commit conventions. Use `/cortex-interactive:commit` for the commit. After the run, manually spot-check one slug from each form (slash/wikilink/word-boundary) by grepping for residual unrewritten refs.
- **Verification**: `git log --oneline -20 | grep -F 'lifecycle-archive sample run' | wc -l` ≥ 1 AND `wc -l < lifecycle/archive/.archive-manifest.jsonl` ≥ 5 AND `while read l; do echo "$l" | jq -e 'has("ts") and has("src") and has("dst") and has("rewritten_files")' >/dev/null || exit 1; done < lifecycle/archive/.archive-manifest.jsonl` (exit 0) AND `grep -rn -E "lifecycle/(slug1|slug2|slug3|slug4|slug5)/" --include='*.md' . --exclude-dir=.git --exclude-dir=archive --exclude-dir=sessions --exclude-dir=retros | grep -v 'archive/' | wc -l` = 0 (substituting actual sample slugs) — pass if all four hold.
- **Status**: [ ] pending

### Task 16: Run lifecycle-archive on remaining ~124 dirs + commit (N6.4 phase b)
- **Files**: `lifecycle/archive/` (more dirs added), `lifecycle/archive/.archive-manifest.jsonl` (appended), citing `*.md` files (rewritten)
- **What**: Run the full archive on all remaining `feature_complete`-marked dirs (post-sample). Commit explicitly labeled "lifecycle-archive full run".
- **Depends on**: [15]
- **Complexity**: complex
- **Context**: Pre-flight: `just lifecycle-archive --dry-run` and review the candidate list + cross-reference list. If anything looks off (e.g., active in-progress slug accidentally marked `feature_complete`), fix the source data before running. Real run: `just lifecycle-archive` (no flag) on the full eligible set. Spec §N6.4 acceptance: ≥100 directory moves under `lifecycle/archive/` compared to pre-run state. After the run: sweep the repo for any remaining unrewritten references by listing all `*.md.bak` files (must be 0) and grepping for `lifecycle/{any-archived-slug}\b` outside the archive. Commit using `/cortex-interactive:commit` with message `lifecycle-archive full run: archive {N} dirs across {M} citers`.
- **Verification**: `git log --oneline -10 | grep -F 'lifecycle-archive full run' | wc -l` ≥ 1 AND `find lifecycle/archive -mindepth 1 -maxdepth 1 -type d | wc -l` ≥ 100 AND `find . -name '*.md.bak' | wc -l` = 0 — pass if all three hold.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification covers four layers:

1. **MCP server hardening (S1+S5)** — Task 4's pytest suite is the primary verification surface. Additionally, after Tasks 1-3 land, manually start the MCP server with `cortex` removed from PATH and confirm: (a) startup stderr line appears; (b) any tool call returns a JSON-RPC error envelope with `data.reason == "cortex_cli_missing"` and the install URL. Restore `cortex` and confirm tools recover on the next call (cache clear-and-retry).
2. **Stale-doc cleanup (N3, N4, N8, N9)** — Each task's individual acceptance grep is sufficient. After all five tasks land, run `git grep -F '~/.claude/skills' :!lifecycle :!retros :!research :!backlog`, `git grep -F '~/.claude/hooks' :!lifecycle :!retros :!research :!backlog`, `git grep -F 'claude/reference' :!lifecycle :!retros :!research :!backlog`, and `git grep -F 'setup-github-pat' :!lifecycle :!retros :!research :!backlog` — all should return 0 lines.
3. **lifecycle-archive recipe** — The dry-run output (Task 11) is the primary correctness surface; Tasks 12-13 add behavior verified by Task 15's sample run.
4. **Archive runs (Tasks 15, 16)** — Verified by manifest validity, commit log, no `.md.bak` residue, no unrewritten references outside the four excluded dirs. Morning postmortem after the next overnight run will confirm that archived references resolve correctly through downstream consumers (overnight orchestrator, lifecycle navigation, morning report).

## Veto Surface

- **MCP error shape: `mcp.types.McpError` raise vs `"Error: ..."` string return**. Spec §S5.2 chose the typed-error raise over the MCP Python reference's prescribed `str` return values. Trade-off: typed McpError lands as a JSON-RPC `response.error` envelope (correct semantically, doesn't clash with Pydantic output schemas via `extra="ignore"` requiring fields), but it deviates from Anthropic's MCP reference pattern. If the user prefers reference-compliance over schema-cleanliness, plan can be re-pointed to a string-return approach with associated rework in Task 1+3+4. Spec rationale: schema clash with each tool's declared Pydantic output is the deciding factor.
- **Sample size of 5 dirs (N6.4 phase a)**. Research §N6 strategy table noted C2 (medium 20-dir sample) as an alternative with better edge-case coverage. Spec §N6.4 selected 5 with deterministic representative-criterion selection. Trade-off: smaller sample = faster cycle to full run; larger sample = more chances to surface ref-graph bugs before the destructive 124-dir run. The deterministic selection script (Task 14) mitigates the "tiny sample misses edge cases" concern by guaranteeing structural coverage (highest cross-ref + zero cross-ref + minimal-content edge cases).
- **FNF errno disambiguation for missing `#!` interpreter** (Task 2). Spec edge case "S1.2 shebang-interpreter missing" elects to accept conflation: a missing `python3` produces a CortexCliMissing whose error message points at install docs (somewhat misleading). Alternative: inspect `errno`/`strerror` of the original FNF to distinguish missing-cortex from missing-python3 and surface a different remediation. Spec rationale: low frequency, simpler code path. If the user wants the disambiguated form, Task 2 adds ~15 lines.
- **Archive-and-leave-cited treatment of `feature_complete`-marked dirs** (Task 15/16). A directory may have `feature_complete` and ALSO be actively cited by an in-progress lifecycle's research/spec/plan. The spec accepts this: archive the dir, rewrite the citers; archived path becomes canonical. Alternative: skip archival of dirs with active citers. Spec rationale: completion is binary (events.log has the marker), and the path-rewrite makes citers continue to work. If the user prefers the active-citer skip, Tasks 11+15+16 grow non-trivially (a citer-count check before each `mv`).
- **N9 deletion without inline replacement instructions**. Task 10 deletes the setup-github-pat assets entirely. Research §N9 noted alternative: inline manual-wire instructions for editing `~/.claude/settings.json`. Spec rationale: deletion is the simplest path; users who need the helper can revive it from git history. If the maintainer hits this on a new machine and wants inline-wire instructions added to `docs/agentic-layer.md` as part of this ticket, Task 10 grows by one short doc edit.
- **Class-B residue items NOT applied to spec/plan**: B6 (claude/statusline.py and non-cortex-prefix bin scripts excluded from N3.1 trigger surface), B7 (gate-fire volume increase with no overnight escape hatch). Both flagged as accepted scope. If the user wants either addressed, that's a spec edit before plan execution.

## Scope Boundaries

Per spec §Non-Requirements:

- **Not in scope**: DR-1 sunset of cortex-command-plugins (#147). S2 plugin-bin PATH ordering. S3 cross-repo triage docs. S4 marketplace versioning.
- **Not addressed in this ticket**: Validation of `CORTEX_COMMAND_ROOT` env var at startup (a related but distinct missing-config case surfaced by adversarial review). If users hit it after S5 ships, file a follow-up ticket.
- **Not implementing**: A Pre-ToolUse gate for skill/hook editing. The N3 description is advisory text consumed by Claude's skill discovery; programmatic enforcement is out of scope.
- **Not implementing**: Cross-process cache invalidation for S1. Single MCP-server-process model is assumed.
- **Not introducing**: TTL-based caching, periodic re-checks, or eager re-detection patterns for S1. Exception-driven invalidation is the chosen mechanism.
- **Not introducing**: Manifest-driven rollback for N6. `git checkout -- .` is the recovery mechanism; the manifest is audit-only.
