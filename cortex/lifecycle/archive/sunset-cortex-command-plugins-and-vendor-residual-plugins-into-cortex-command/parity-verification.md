# Parity Verification — sunset-cortex-command-plugins

Captured at HEAD = origin/main of cortex-command (local main in sync with origin/main) on 2026-04-27, after PR-A (G1) and PR-B (G2) merged and chickfila-android consumer migrated. Each section below shows the literal command and its actual recorded output, with exit code captured.

### Section: R3 NOTICE

```bash
$ grep -c 'Google' plugins/android-dev-extras/NOTICE
1
# exit code: 0
```

Expected: count >= 1. Recorded: `1`. PASS.

### Section: R4 HOW-TO-SYNC

```bash
$ grep -c 'cortex-command-plugins.git' plugins/android-dev-extras/HOW-TO-SYNC.md
0
# exit code: 1
```

Expected: count == 0 (grep exits 1 on zero matches). Recorded: `0`. PASS.

### Section: R7 README

```bash
$ grep -c 'cortex-command-plugins' README.md
0
# exit code: 1
```

Expected: count == 0 (grep exits 1 on zero matches). Recorded: `0`. PASS.

### Section: R11 workflow file

```bash
$ test -f .github/workflows/validate.yml
# exit code: 0
```

Expected: exit code 0. Recorded: `0`. PASS.

### Section: R11 first-post-merge run

Per orchestrator note: `--branch main` filter returns empty inconsistently; the form below (without `--branch`) is the supported form. The most recent run on `main` is captured directly by `--limit 1`.

```bash
$ gh run list --workflow validate.yml --limit 1 --json conclusion -q '.[0].conclusion'
success
# exit code: 0
```

Cross-check with full row context (databaseId + headBranch confirms it's the post-merge run on main):

```bash
$ gh run list --workflow validate.yml --limit 1 --json conclusion,databaseId,headBranch -q '.[0]'
{"conclusion":"success","databaseId":25015230071,"headBranch":"main"}
# exit code: 0
```

Expected: literal string `success`. Recorded: `success` (databaseId 25015230071, headBranch main). PASS.

### Section: claude plugin validate

claude CLI version: 2.1.119 (Claude Code) — supports `claude plugin validate` subcommand per orchestrator confirmation.

```bash
$ claude plugin validate plugins/android-dev-extras
Validating plugin manifest: /Users/charlie.hall/Workspaces/cortex-command/plugins/android-dev-extras/.claude-plugin/plugin.json

⚠ Found 3 warnings:

  ❯ version: No version specified. Consider adding a version following semver (e.g., "1.0.0")
  ❯ description: No description provided. Adding a description helps users understand what your plugin does
  ❯ author: No author information provided. Consider adding author details for plugin attribution

✔ Validation passed with warnings
# exit code: 0
```

```bash
$ claude plugin validate plugins/cortex-dev-extras
Validating plugin manifest: /Users/charlie.hall/Workspaces/cortex-command/plugins/cortex-dev-extras/.claude-plugin/plugin.json

⚠ Found 3 warnings:

  ❯ version: No version specified. Consider adding a version following semver (e.g., "1.0.0")
  ❯ description: No description provided. Adding a description helps users understand what your plugin does
  ❯ author: No author information provided. Consider adding author details for plugin attribution

✔ Validation passed with warnings
# exit code: 0
```

Expected: both validations exit 0 with `Validation passed`. Recorded: both exit 0 with `✔ Validation passed with warnings`. PASS. The three warnings (version/description/author missing) are non-blocking advisories present in source on cortex-command-plugins as well; out of scope for this sunset ticket.

### Section: skill invocation evidence

Marketplace add (already on disk from prior session — message confirms marketplace resolves):

```bash
$ claude plugin marketplace add /Users/charlie.hall/Workspaces/cortex-command
Adding marketplace…✔ Marketplace 'cortex-command' already on disk — declared in user settings
# exit code: 0
```

Plugin install (both new `@cortex-command` entries resolve and install successfully under user scope):

```bash
$ claude plugin install android-dev-extras@cortex-command
Installing plugin "android-dev-extras@cortex-command"...✔ Successfully installed plugin: android-dev-extras@cortex-command (scope: user)
# exit code: 0
```

```bash
$ claude plugin install cortex-dev-extras@cortex-command
Installing plugin "cortex-dev-extras@cortex-command"...✔ Successfully installed plugin: cortex-dev-extras@cortex-command (scope: user)
# exit code: 0
```

Skill invocation — `/r8-analyzer` from `android-dev-extras@cortex-command` (headless `claude -p`, output truncated to first 30 lines):

```bash
$ claude -p '/r8-analyzer help' 2>&1 | head -30
The `/android-dev-extras:r8-analyzer` skill analyzes Android R8/ProGuard keep rules to identify redundant, overly broad, or library-specific rules that can be removed or refined for better app optimization.

## What it does

Walks your Android project's R8 configuration and produces an `R8_Configuration_Analysis.md` report covering:

1. **R8 configuration** — Reads `build.gradle`, `build.gradle.kts`, and `gradle.properties` to assess current setup
2. **AGP version check** — Recommends AGP 9.0+ for built-in optimizations
3. **Library keep rules** — Flags rules targeting Google/AndroidX/Kotlin/Room/Gson/Retrofit (libraries already ship consumer keep rules)
4. **Impact analysis** — Evaluates remaining rules against an impact hierarchy
5. **Subsuming rules** — Identifies broad rules that swallow narrower ones
6. **Per-rule recommendations** — For each remaining rule, examines the affected code (including reflection usage) and suggests either removal or refinement to a narrower rule
7. **Test guidance** — Advises running UI Automator tests on affected packages to validate changes

## How to use

Run `/android-dev-extras:r8-analyzer` (without `help`) inside an Android project directory. The skill is read-only — it won't modify your keep rule files; it only produces the analysis report so you can apply changes deliberately.

## Caveat

This repo (`cortex-command`) is a Python/Claude Code framework, not an Android project — running the skill here would have nothing to analyze. Point it at an Android codebase to get useful output.
# exit code: 0
```

The model resolved the skill via its qualified name `/android-dev-extras:r8-analyzer`, confirming the install path `android-dev-extras@cortex-command` routes correctly.

Skill invocation — `/devils-advocate` from `cortex-dev-extras@cortex-command` (headless `claude -p`, output truncated to first 30 lines):

```bash
$ claude -p '/devils-advocate help' 2>&1 | head -30
# Devil's Advocate — Help

Inline single-agent critic that argues against your current direction. Stays in the current agent's context (no sub-agents dispatched), so it's lightweight and fast.

## When to use

- "Challenge this", "poke holes", "argue against this", "what could go wrong", "stress-test this"
- Any phase — no lifecycle required
- Solo deliberation when you want a sanity check before committing

## How to invoke

```
/cortex-dev-extras:devils-advocate
```

Optionally followed by the direction to argue against, e.g.:

```
/cortex-dev-extras:devils-advocate replacing Kafka with HTTP webhooks
```

If a lifecycle is active, the skill auto-reads `plan.md` → `spec.md` → `research.md` and argues against whatever is freshest. Otherwise it works from conversation context, or asks you to specify the direction.

## What you get back

Four sections of substantive prose:
1. **Strongest Failure Mode** — most likely way it breaks
# exit code: 0
```

The skill responded with its help content, including the qualified invocation form `/cortex-dev-extras:devils-advocate`, confirming the install path `cortex-dev-extras@cortex-command` routes correctly.

## Summary

All seven required sections recorded above. Recorded values match expected gate states:
- R3 (Google in NOTICE): 1 (>= 1) — PASS
- R4 (cortex-command-plugins.git in HOW-TO-SYNC): 0 — PASS
- R7 (cortex-command-plugins in README): 0 — PASS
- R11 workflow file present: exit 0 — PASS
- R11 first-post-merge run: success — PASS
- claude plugin validate (both plugins): exit 0 — PASS
- skill invocation (one from each plugin): both routed and responded — PASS

The sunset migration's parity is verified end-to-end on origin/main. Task 14 (gh repo archive) is now unblocked.
