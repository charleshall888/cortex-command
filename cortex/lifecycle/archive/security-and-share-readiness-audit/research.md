# Research: Security & Share-Readiness Audit

## Methodology

Three parallel research streams:
1. Code execution & unsafe pattern audit (all .sh and .py files)
2. Secrets, credentials, and sensitive data scan
3. Share-readiness assessment (docs, setup, onboarding)

---

## Security Findings

### Critical

**1. Shell variable injection in scan-lifecycle.sh:10**

```bash
echo "export LIFECYCLE_SESSION_ID=$SESSION_ID" >> "$CLAUDE_ENV_FILE"
```

SESSION_ID comes from JSON input via jq and is written unquoted to the env file. Shell metacharacters (`$(cmd)`, backticks, `;`) would execute when the env file is sourced. SessionStart hooks run before sandbox initialization.

Fix: Quote the variable — `echo "export LIFECYCLE_SESSION_ID='$SESSION_ID'" >> "$CLAUDE_ENV_FILE"`

**2. eval with user-supplied command in runner.sh:829**

```bash
( cd "$WORKTREE_PATH" && eval "$TEST_COMMAND" )
```

TEST_COMMAND arrives via `--test-command` CLI argument and is passed directly to `eval`. Arbitrary shell command injection.

Fix: Replace `eval "$TEST_COMMAND"` with `bash -c "$TEST_COMMAND"` or avoid eval entirely.

**3. shell=True with user-controlled input in merge.py:53-87**

```python
result = subprocess.run(
    test_command,
    shell=True,
    capture_output=True,
    text=True,
    cwd=cwd,
)
```

test_command is user-supplied (from `--test-command` argument) and passed to subprocess with shell=True.

Fix: Use `["sh", "-c", test_command]` without shell=True.

### High

**4. Path injection in runner.sh Python -c calls (~line 350)**

STATE_PATH is embedded directly in Python code executed via `python3 -c`. While partially mitigated by realpath() normalization, paths with quote characters could break the Python string literal context.

Fix: Pass as environment variable — `os.environ['STATE_PATH']`.

### Medium

**5. Unquoted variable in notify-remote.sh:27** — SESSION used in curl headers could break logging.

### Informational

- Git branch deletion in cleanup-session.sh properly quotes variables (safe).
- Sed operations in backlog scripts operate on local files only (low risk).

---

## Secrets & Credentials Findings

**All clear.** No hardcoded secrets found:

- API keys use environment variables (ANTHROPIC_API_KEY) throughout
- No Base64 credentials, embedded tokens, or user:pass@ URLs
- .gitignore covers: .env/.env.*, .venv/, __pycache__/, *.pyc, .DS_Store, node_modules/, session artifacts, logs
- No machine-specific `/Users/charlie.hall` paths in committed files
- No .pem, .key, .pfx, credentials.json, or SSH keys committed
- Git remote uses HTTPS (no embedded SSH credentials)

**Sandbox configuration is excellent:**
- Dangerous commands denied (sudo, rm -rf, force push, chmod 777, curl|bash)
- Sensitive files protected (env, secrets, pem, key, aws, ssh, kube, gnupg, docker, npm, pypirc, gem, azure, keychains)
- Network restricted to approved domains
- Shell profile editing denied

---

## Share-Readiness Findings

### Documentation

| Item | Status | Notes |
|------|--------|-------|
| README.md | Good | 143 lines, clear structure, prerequisites, quick start, backup warning |
| docs/ (8 files) | Excellent | All referenced docs exist and are current |
| Skills count ("29 skills") | Accurate | Verified all 29 directories exist |
| Hook inventory | Complete | All 14 hooks accounted for, no stale references |
| LICENSE | Present | MIT, Charlie Hall, 2026 |
| Command reference | Accurate | All documented `just` commands verified |

### Setup Experience

**Strengths:**
- `just setup` is comprehensive and well-ordered (deploy-bin → reference → skills → hooks → config → python-setup)
- `python-setup` checks for `uv` with helpful error
- `deploy-config` prompts before overwriting non-symlink files
- `deploy-bin` refuses to run from worktrees

**Issues:**

| # | Issue | Severity | Detail |
|---|-------|----------|--------|
| S1 | Hardcoded `~/cortex-command` in settings.json line 360 | High | `allowWrite` sandbox path assumes clone location; fails silently elsewhere |
| S2 | CORTEX_COMMAND_ROOT requires manual shell config | High | Must manually add `export` to .zshrc/.bashrc; no auto-detection |
| S3 | No `just` availability check | Medium | `python-setup` checks for `uv`, but nothing checks for `just` itself |
| S4 | No post-setup verification | Medium | No way to confirm everything worked after `just setup` |
| S5 | README assumes macOS | Medium | References zsh, brew, launchd; Windows/Linux buried in docs/setup.md |
| S6 | terminal-notifier not checked | Low | Notifications silently fail without it; documented only in docs/setup.md |
| S7 | No quick health check | Low | No `just verify-setup` to confirm working state |
| S8 | Symlink check can't auto-fix | Low | `just check-symlinks` reports but can't repair |

### Onboarding Gaps

1. **Claude Code installation assumed** — no verification step
2. **Git signing config (GPG, PAT hooks)** — unclear which users need them
3. **macOS vs. Linux vs. Windows** — not surfaced in README, only in docs/setup.md
4. **tmux for overnight** — required for `just overnight-start` but only checked at runtime
5. **Backup flow is manual** — README lists files to back up but no automation

---

## Open Questions

- Should the settings.json path be templatized during setup (e.g., `just setup` rewrites the path based on clone location)?
- Should CORTEX_COMMAND_ROOT auto-detection be added to `jcc` and other tools, or is the env var approach correct?
- What's the minimum viable onboarding for non-macOS users — should the README branch by OS or keep it macOS-primary?
- For the `eval`/`shell=True` findings: these commands run test suites specified by the operator — is the threat model "malicious operator" or just "accidental injection"? (Changes severity assessment for some findings.)
