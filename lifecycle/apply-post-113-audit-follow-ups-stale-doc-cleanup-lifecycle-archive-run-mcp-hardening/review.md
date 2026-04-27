# Review: apply-post-113-audit-follow-ups-stale-doc-cleanup-lifecycle-archive-run-mcp-hardening (cycle 1)

## Stage 1: Spec Compliance

### S1 — MCP discovery-cache stale-on-CLI-upgrade — PASS

- **S1.1** (`CortexCliMissing(OSError)`): defined at `plugins/cortex-overnight-integration/server.py:202`, parented on `OSError` per spec. Internal-only disambiguator with docstring noting the OSError-parentage rationale (preserves swallow at `_maybe_check_upstream` / `_maybe_run_upgrade`).
- **S1.2** (FNF wrapping): both subprocess-spawning sites for `cortex` are wrapped — `_get_cortex_root_payload` at `server.py:268-278` and `_run_cortex` at `server.py:1403-1413`. Both use `raise CortexCliMissing(exc.errno, exc.strerror, *exc.args[2:]) from exc` so errno/strerror are preserved. `grep -nE 'except FileNotFoundError'` returns exactly 2 matches as expected. `PermissionError` and other OSError subtypes pass through unchanged (verified by test (c)).
- **S1.3** (cache-clear-and-retry): centralized in `_retry_on_cli_missing(budget, func, *args, **kwargs)` at `server.py:1416-1446` — clears `_CORTEX_ROOT_CACHE` on first `CortexCliMissing`, retries once, re-raises on second hit. Caught surface is exactly `CortexCliMissing` (not the broader `OSError`), preventing accidental `PermissionError` absorption (spec edge case explicitly addressed in helper docstring). Per-tool-call retry counter is a single-element mutable list owned by the caller — local scope, not module-global.
- **S1.4** (preserved swallow at upstream/upgrade sites): `CortexCliMissing` inherits from `OSError`, so the existing `except OSError` handlers continue to catch it. Test (f) at `tests/test_mcp_cortex_cli_missing.py:338` asserts `_maybe_check_upstream` returns `None` on `CortexCliMissing`.
- All 8 acceptance tests in `tests/test_mcp_cortex_cli_missing.py` pass (8/8 reported in the prompt's already-verified facts).

### S5 — MCP graceful-degrade for missing CLI — PASS (with documented wire-shape deviation)

- **S5.1** (startup `shutil.which("cortex")` warning): at `server.py:219-223`, prints the canonical missing-CLI message to stderr at module import time if `cortex` is absent from PATH. Does NOT raise — server initialization completes either way. Test (g) covers both branches via `monkeypatch.setattr(shutil, "which", ...)`.
- **S5.2** (canonical error reaches MCP clients): the implementation chose to **return** `_CORTEX_CLI_MISSING_ERROR` from tool bodies on retry-exhaust rather than **raise** `mcp.types.McpError` as the original spec text proposed. This is a deliberate, documented deviation captured in the plan's Veto Surface section: critical review confirmed empirically that FastMCP downgrades both forms to the same `CallToolResult(isError=True, content=[TextContent(text=str(e))])` envelope, so the spec's schema-clash rationale was based on a factual misreading. The chosen string-return pattern is the Anthropic MCP Python reference's prescribed shape and avoids the comprehension trap of an `McpError` raise that "looks structured but isn't on the wire." The spec's underlying *requirement* — that the install-pointer text reaches MCP clients on retry-exhaust — is satisfied.
  - The implementer flagged a residual nuance: for typed-output tools, returning a string triggers a Pydantic ValidationError that wraps the canonical text rather than emitting it byte-equal. The byte-equal assertion in test (h) covers delegate-level invariants (the returned string from a tool body equals the constant), not wire-level (what arrives at the MCP client after FastMCP's typed-output validation). This is a known limitation of the chosen approach but does not violate the spec's intent — the install URL is preserved in the wrapped error text.
- **S5.3** (single helper / shared constant): a single module-level `_CORTEX_CLI_MISSING_ERROR` string at `server.py:195-199` is used at all surfaces (startup stderr branch + every retry-exhaust return). `grep -F '_CORTEX_CLI_MISSING_ERROR'` returns 20 references across the file. Test (h) asserts byte-equal contents across the startup-stderr emission and the retry-exhaust return value.

### N3 — Lifecycle skill description trigger surface — PASS

- **N3.1**: `skills/lifecycle/SKILL.md:3` contains the inclusive trigger surface verbatim. Acceptance greps:
  - `plugins/cortex-pr-review/`: 1 match (≥1 required)
  - `plugins/cortex-ui-extras/`: 1 match (≥1 required)
  - `plugins/cortex-interactive/{skills,hooks,bin}/`: 1 match (= 1 required)
  - `~/.claude/skills`: 0 matches (= 0 required)
- **N3.2**: `git diff --quiet plugins/cortex-interactive/skills/lifecycle/SKILL.md` exits 0 — mirror in sync with canonical post-`just build-plugin`.

### N4 — Diagnose skill illustrative reference — PASS

- **N4.1**: `skills/diagnose/SKILL.md:147-150` rewords the example to use `sandbox.filesystem.allowWrite` with `~/Workspaces/myrepo/lifecycle/sessions/` vs the absolute `/Users/me/...` form. The absolute-vs-tilde pedagogy is preserved (in fact strengthened — the example now ties to a real cortex-init code path rather than the retired `~/.claude/hooks/` path). `grep -F '~/.claude/hooks'` returns 0.
- **N4.2**: `git diff --quiet plugins/cortex-interactive/skills/diagnose/SKILL.md` exits 0 — mirror in sync.

### N6 — lifecycle-archive recipe enhancement + run — PASS

- **N6.1** (`--dry-run`): `justfile:143-266` accepts `--dry-run` and emits `archive candidates:` and `rewrite candidates:` sections without performing `mv` or path rewrites. Dry-run respects the same clean-tree precheck and worktree-skip behavior as the real run.
- **N6.2** (manifest schema): `lifecycle/archive/.archive-manifest.jsonl` exists; 111 lines, matching 111 archived dirs. Per-line schema validation via `jq -e 'has("ts") and has("src") and has("dst") and has("rewritten_files")'` exits 0 on every line. Manifest writes are atomic via tempfile + `mv` under an `mkdir`-based lock (portable substitute for `flock`, which is unavailable on macOS).
- **N6.3** (path rewriting): `bin/cortex-archive-rewrite-paths` implements three citation forms (slash, wikilink, bare) using explicit boundary character classes `[A-Za-z0-9_/-]` rather than `\b`. The character-class form correctly treats hyphens as word-equivalent so `add-foo` does NOT match inside `add-foo-bar` (covered by unit test). Patterns applied in order slash → wikilink → bare to prevent the bare pattern from stealing slash-form matches. Excludes match the spec (`.git/`, `lifecycle/archive/`, `lifecycle/sessions/`, `retros/`) PLUS two additional exclusions added in the c332898 recipe-repair: `.claude/worktrees/` (prevents corruption of in-progress agent work in sibling worktrees) and `.venv/` (prevents rewriting vendored markdown in package installs). The two additions are operationally correct expansions of the spec's intent — the spec lists exclusions as "directories that would be incorrectly modified," and worktrees + venv vendor docs both qualify under that rationale. Atomic writes via `<file>.tmp-archive-rewrite` + `os.replace`; `find . -name '*.tmp-archive-rewrite'` returns 0 (no orphan tempfiles).
- **N6.4** (sample-then-full run): `bin/cortex-archive-sample-select` (Task 14) emits the deterministic sample list with form-coverage enforcement; `.archive-sample.txt` is gitignored. Two distinct commits in history: `beb2cfe Lifecycle-archive sample run: archive 5 representative dirs` and `64c2083 Lifecycle-archive full run: archive 106 dirs across 139 citers`. Final state: 111 dirs under `lifecycle/archive/` (≥100 required). Recipe-repair commits between sample and full are explicitly in-scope per spec.
  - **Commit-subject capitalization**: plan's required regex `^lifecycle-archive` would NOT match the actual commit subjects (`Lifecycle-archive ...`). This is a spec/plan/codebase mismatch — the cortex commit-message hook requires capital first letter, so the lowercase form in the plan was unsatisfiable. The acceptance criteria themselves (≥100 dirs archived, no tmp files, no unrewritten refs, exact subject form modulo capitalization) are met. Recommend a future spec/plan revision to acknowledge the capitalization rule, but this is not a blocker — it is a known-and-accepted quirk introduced by the validation hook.
- **N6.5** (clean-tree precheck + recovery): `justfile:164-167` enforces `git diff --quiet HEAD && git diff --quiet --cached HEAD` on entry to BOTH dry-run and real-run modes; aborts with a clear error pointing to commit/stash. Recovery procedure documented at `docs/overnight-operations.md:550-560` — three-step procedure naming `git checkout -- .` as the sole recovery mechanism and explicitly stating the manifest is audit-only.
- All 24 unit tests in `tests/test_archive_rewrite_paths.py` pass (per prompt's already-verified facts). Zero unrewritten refs across all 111 archived slugs; zero worktree damage.

### N8 — Stale-doc cleanup (`claude/reference/` + context-file-authoring) — PASS

- **N8.1**: `grep -F 'claude/reference' README.md` returns 0.
- **N8.2**: `grep -F 'claude/reference' docs/overnight-operations.md` returns 0; `grep -F 'docs.claude.com/en/docs/agents-and-tools/agent-skills' docs/overnight-operations.md` returns 1 (line 11). Inline three-level loading description present and self-contained.
- **N8.3**: `grep -F 'context-file-authoring' claude/hooks/cortex-skill-edit-advisor.sh` returns 0; `grep -F 'just test-skills'` returns 2 (primary behavior preserved). Hook still parses cleanly (`bash -n` exits 0).

### N9 — setup-github-pat deletion — PASS

- **N9.1**: `claude/hooks/setup-github-pat.sh` is deleted (verified via `test ! -f`).
- **N9.2**: `just --list 2>&1 | grep -E 'setup-github-pat(-org)?'` returns 0.
- **N9.3**: `git grep -F 'setup-github-pat'` (excluding lifecycle/retros/research/backlog) returns 0 — no remaining references in active codebase docs.

## Stage 2: Code Quality (Stage 1 has no FAIL verdicts; Stage 2 runs)

- **Naming**: `_CORTEX_CLI_MISSING_ERROR` constant name is unambiguous and self-documenting; `CortexCliMissing` class name follows the project's existing exception-naming pattern. `_retry_on_cli_missing` helper signature `(budget, func, *args, **kwargs)` is conventional Python; passing a single-element mutable list as the budget container is an idiomatic-but-slightly-unusual pattern, justified inline by the docstring's per-tool-call-counter rationale.
- **Error handling**: catch surface in `_retry_on_cli_missing` is exactly `except CortexCliMissing` (NOT `except OSError`), so `PermissionError` and other OSError subtypes propagate unchanged — exactly as spec §S1.3 requires. The `_get_cortex_root_payload` and `_run_cortex` wrappers preserve original `errno`/`strerror` via `raise CortexCliMissing(exc.errno, exc.strerror, *exc.args[2:]) from exc` (good practice — preserves diagnostic detail and the chained traceback).
- **Test coverage**: 8 S1+S5 acceptance tests cover every spec-enumerated case (a)-(h). 24 path-rewriter tests cover the substring-collision case, all four wikilink terminator variants, slash form, bare form, and slug-with-regex-metacharacters via `re.escape()`. Both test suites pass.
- **Pattern consistency**: the path-rewriter helper follows the project's `bin/cortex-*` convention (Python script with module docstring + argparse + `main()` returning exit code), is `chmod +x`, and ships via the cortex-interactive plugin's `bin/` mirror per CLAUDE.md. The recipe's `set -- {{args}}` workaround for just shebang recipes is idiomatic-but-load-bearing — the inline comment at `justfile:146-150` explicitly documents the destructive-incident motivation, which is an excellent maintainer-hint that prevents future regressions.
- **Recipe robustness**: the manifest write uses `mkdir`-based locking (portable substitute for `flock` on macOS) with bounded busy-wait + cleanup trap. Per-slug rewrite captured via stdout JSON pipe through Python (avoids shell-quoting hazards). Stale-symlink guard `[ -e "$dir" ]` before `realpath` prevents `set -e` aborts on broken symlinks (spec edge case explicitly addressed). Bash 3.2 compatibility (no `declare -A`; uses newline-delimited string membership test) is documented inline.
- **Documentation**: `docs/overnight-operations.md:550-560` recovery section is concise and explicitly disclaims any manifest-driven rollback (matches spec intent). Plan's Veto Surface section is the canonical record of the wire-shape deviation rationale — useful for future maintainers wondering why the implementation chose `return` over `raise McpError`.

## Requirements Drift

**State**: none

**Findings**: The implementation introduces three new operational behaviors:

1. The lifecycle-archive recipe's new `--dry-run` mode, `--from-file <path>` filter, manifest writer, and clean-tree precheck — all mechanics for an existing housekeeping recipe rather than a new project capability.
2. New `docs/overnight-operations.md` section documenting the lifecycle-archive recovery procedure — operational documentation under the existing doc-partitioning convention named in CLAUDE.md.
3. MCP `CortexCliMissing` exception + retry-once + canonical error string — graceful-degrade hardening for an existing component (`plugins/cortex-overnight-integration`) rather than a new system.

None of the three introduce capabilities outside the project's existing scope as defined in `requirements/project.md`:

- Lifecycle housekeeping and archival are part of "AI workflow orchestration (skills, lifecycle, pipeline, discovery, backlog)" (In Scope §1).
- MCP plugin hardening falls under "Overnight execution framework, session management, scheduled launch, and morning reporting" (In Scope §2) and the "Graceful partial failure" quality attribute.
- The recovery-procedure documentation update is mechanics for the existing housekeeping recipe.

The implementation does not introduce any behavior that contradicts existing requirements (file-based state preserved; no new dependencies on a database; per-repo sandbox model unchanged; no PyPI publishing; no machine-config encroachment).

**Update needed**: None.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
