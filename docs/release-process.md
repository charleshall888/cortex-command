[← Back to README](../README.md)

# Release Process

**For:** Maintainers cutting a new tagged release of the `cortex` CLI. **Assumes:** You have push access to `charleshall888/cortex-command`, `gh` CLI configured, and a working `uv` install.

This document covers the version-bump, tag-push, and release-publish workflow, plus the **tag-before-coupling** discipline that keeps the plugin/CLI version coupling safe.

---

## Versioning scheme

Cortex uses [SemVer](https://semver.org/):

- **Patch** (`0.1.0 → 0.1.1`): bug fixes, no behavior changes for users.
- **Minor** (`0.1.x → 0.2.0`): new features, backward-compatible behavior changes.
- **Major** (`0.x.x → 1.0.0`): breaking changes (CLI flag removals, JSON envelope shape changes that break existing consumers, etc.).

Three distinct version numbers exist in the codebase — keep them straight:

1. **`pyproject.toml` `version`** — the package version. This is what `uv tool install` resolves and what `cortex --version` reports.
2. **CLI tag** (`v0.1.0`) — the git tag that pins the wheel build. Always `v` + `pyproject.toml` version. This is what `uv tool install git+<url>@<tag>` and the plugin's `CLI_PIN[0]` reference.
3. **Schema version** (`CLI_PIN[1]`, `MCP_REQUIRED_CLI_VERSION`) — the major schema version of the print-root JSON envelope. Bumps independently of the package version; bumps when the envelope shape changes incompatibly. Currently `"1.0"` (matched by the envelope's own `"version": "1.1"` field — note the envelope-version is independent of `CLI_PIN[1]` for additive-only changes).

---

## Cut a new release

### 1. Bump `pyproject.toml`

Edit `pyproject.toml` and change the `version` field:

```toml
version = "0.2.0"
```

### 2. Add a `CHANGELOG.md` entry

Add a new entry at the top of `CHANGELOG.md` (under `## [Unreleased]` or directly above the previous release entry):

```markdown
## [v0.2.0] - 2026-MM-DD

### Added
- Brief bullet describing each new feature.

### Changed
- Brief bullet describing each behavior change.

### Fixed
- Brief bullet describing each bug fix.
```

Follow the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

### 3. Commit the version bump

Use the cortex-core commit skill:

```
/cortex-core:commit
```

Suggested commit message: `Bump version to v0.2.0` (or similar — imperative mood, capitalized, no trailing period, ≤ 72 chars).

### 4. Tag the commit

```bash
git tag -a v0.2.0 -m "Release v0.2.0"
```

Use `-a` (annotated tag) so the tag has its own metadata. The message can be brief — the `CHANGELOG.md` entry is the canonical release notes.

### 5. Push the commit and tag

```bash
git push origin main
git push --tags
```

(Or `git push origin v0.2.0` to push just that tag.)

### 6. Watch the release workflow

Pushing a tag matching `v[0-9]+.[0-9]+.[0-9]+` triggers `.github/workflows/release.yml`, which runs `uv build --wheel` and creates a GitHub Release with the wheel as a release asset.

```bash
gh run watch $(gh run list --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh release view v0.2.0
```

The release should have at least one asset — `cortex_command-0.2.0-py3-none-any.whl`. Confirm with:

```bash
gh release view v0.2.0 --json assets -q '.assets[].name'
```

### 7. (Conditional) Bump the plugin's `CLI_PIN`

**Post-fix flow (normal path)**: as of ticket #213's auto-release workflow, you do **not** manually bump `CLI_PIN[0]` for routine releases. Push to `main` triggers `.github/workflows/auto-release.yml`, which invokes `bin/cortex-auto-bump-version` to determine the next tag and `bin/cortex-rewrite-cli-pin` to update the `CLI_PIN` literal in `plugins/cortex-overnight/server.py`, then commits `Release vX.Y.Z`, creates and pushes the tag using the `AUTO_RELEASE_PAT` so `release.yml` fires normally on the tag push. See the "Auto-release PAT setup (one-time)" section below for the one-time setup the maintainer performs.

**Manual edit only on emergency tags**: if the auto-release workflow is disabled or you push a tag manually (PAT revoked, transient failure, emergency release), edit the `cortex-overnight` plugin's `CLI_PIN` constant in `plugins/cortex-overnight/server.py` directly:

```python
CLI_PIN: tuple[str, str] = ("v0.2.0", "2.0")
```

The CI lint in `.github/workflows/release.yml` (per #213 R18) hard-fails the release-tag push when `CLI_PIN[0]` does not match the pushed tag, catching drift in this emergency path.

If the schema major did not change, the second tuple element stays at the current schema floor. If the print-root JSON envelope shape changed in a breaking way, bump it alongside.

Commit the bump:

```
/cortex-core:commit
```

Suggested commit message: `Bump plugin CLI_PIN to v0.2.0`.

This is the moment the plugin starts requiring the new CLI tag. Until you bump the plugin, users running plugin auto-update remain on the old `CLI_PIN`, which still works because the old CLI tag is still installed for them.

---

## Auto-release PAT setup (one-time)

The auto-release workflow at `.github/workflows/auto-release.yml` runs on every push to `main`. It needs to push a release commit and tag back to `main` in a way that **retriggers** `release.yml`. GitHub's default `GITHUB_TOKEN` cannot retrigger other workflows by design (anti-loop protection), so the auto-release workflow uses a Personal Access Token stored as the repo secret `AUTO_RELEASE_PAT`.

This is a one-time interactive setup the maintainer performs manually. **The PAT MUST be configured BEFORE the implement-PR for ticket #213 lands on `main`** — the merge to main is the first auto-release workflow invocation; without the PAT, the workflow fails on its first run.

### Create the PAT

1. Go to GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
2. Scope it to **this single repository** (`charleshall888/cortex-command`). Do not grant org-wide or all-repo access.
3. Set permissions:
   - **Contents**: **Read and write** (required to push the release commit + tag).
4. Set expiry. A 90-day expiry is the recommended cadence (see "Rotation" below).
5. Generate and **copy the token immediately** — GitHub shows it once.

### Store as repo secret

```bash
gh secret set AUTO_RELEASE_PAT --body '<paste-token-here>'
```

Verify presence (does **not** reveal the value):

```bash
gh secret list | grep AUTO_RELEASE_PAT
```

### Pre-merge gate

Before merging the #213 implement-PR (or any future PR that depends on the auto-release workflow being functional), confirm `AUTO_RELEASE_PAT` is set:

```bash
gh secret list | grep AUTO_RELEASE_PAT
```

If the secret is missing, configure it first, then merge.

### Rotation

Rotate the PAT every 90 days, or whenever GitHub emails you about pending expiry. Workflow:

1. Generate a new fine-grained PAT with the same `contents: write` scope on this repo.
2. `gh secret set AUTO_RELEASE_PAT --body '<new-token>'` (overwrites the old value).
3. The next push to `main` exercises the new token; if it fails, follow the failure-recovery runbook below.

**Set a calendar reminder for T+80 days** from PAT issuance so you have a ~10-day window to rotate before the in-workflow probe (described below) starts warning.

### Expiry monitoring

`auto-release.yml` runs a scheduled weekly probe (cron-triggered) that checks whether `AUTO_RELEASE_PAT` is present and posts a workflow annotation if the secret is missing. This catches the case where the secret was deleted or never configured; it does **not** detect token-expiry directly (GitHub's API surfaces PAT expiry only to the token's owner, not via repo-secret introspection). The calendar reminder at T+80 days is the primary pre-expiry signal; the weekly probe is the post-expiry detection net.

If you see a missing-secret annotation in the weekly probe, follow the failure-recovery runbook.

### Failure-recovery runbook

If the auto-release workflow fails because the PAT is missing, expired, or revoked:

1. Generate a new fine-grained PAT (see "Create the PAT" above).
2. Update the secret:

   ```bash
   gh secret set AUTO_RELEASE_PAT --body '<new-token>'
   ```

3. Retry the workflow on the current `main`:

   ```bash
   gh workflow run auto-release.yml --ref main
   ```

   The `workflow_dispatch` trigger declared in `auto-release.yml` (per #213 R19) enables this manual retry path without needing to push another commit.

4. Watch the run:

   ```bash
   gh run watch $(gh run list --workflow=auto-release.yml --limit 1 --json databaseId -q '.[0].databaseId')
   ```

### Runaway-workflow recovery

If the auto-release workflow misfires repeatedly (e.g., a commit-message parse bug, an infinite-retry loop, or runaway queued runs), disable the workflow and drain the queue:

1. Disable the workflow so no new runs start:

   ```bash
   gh workflow disable auto-release.yml
   ```

2. Cancel each queued run, iterating until the queue is empty:

   ```bash
   gh run list --workflow auto-release.yml --status queued --json databaseId --jq '.[].databaseId' \
     | xargs -I{} gh run cancel {}
   ```

   Or, one-by-one:

   ```bash
   gh run list --workflow auto-release.yml --status queued --json databaseId
   gh run cancel <id>
   ```

3. Verify the queue is empty:

   ```bash
   gh run list --workflow auto-release.yml --status queued | wc -l
   ```

   Should return `0` (header-only output stripped, or no rows at all depending on `gh` version).

4. Fix the underlying issue (commit-message marker bug, rewriter regression, etc.). Land the fix on `main` while the workflow is still disabled.

5. Re-enable the workflow:

   ```bash
   gh workflow enable auto-release.yml
   ```

6. Trigger a fresh run on the now-fixed `main`:

   ```bash
   gh workflow run auto-release.yml --ref main
   ```

### Recommended one-time setup: tag protection

In addition to the CI lint (#213 R18) that hard-fails on `CLI_PIN[0]` drift, enable GitHub branch/tag protection on the `v*` tag namespace as a complementary safety net against force-pushed tags overwriting published releases:

1. GitHub → Settings → **Tags** → **Add rule**.
2. Pattern: `v*`.
3. Enable **Restrict force-pushes**.

This is a recommended one-time setup. The CI lint catches `CLI_PIN[0]` drift on tag-push events; tag protection prevents anyone (including the maintainer mid-mistake) from force-pushing over an existing `v*` tag. Together they cover both the drift-at-creation and the drift-after-creation failure modes.

---

## Tag-before-coupling discipline (why)

The plugin's `CLI_PIN[0]` is a literal git tag string. When the plugin's MCP server runs `_ensure_cortex_installed()` and the literal references a tag that does not yet exist at the remote, `uv tool install` fails with "ref not found", the sentinel + last-error.log capture the failure, and users see "cortex CLI install failed: tag vX.Y.Z not found at <url>. Plugin may be ahead of cortex repo; check that all required cortex tags are pushed."

To prevent this dangling-pointer window:

1. **CLI tag is pushed FIRST.** `pyproject.toml` bumped, `CHANGELOG.md` entry added, commit pushed, tag pushed, GitHub Release published — all before the plugin references the new tag.
2. **Plugin `CLI_PIN[0]` is bumped SECOND.** Only after step 1 is fully done does the plugin commit referencing the new tag land.

This ordering keeps every plugin commit on main referring to a tag that exists at the remote. If you ever need to roll back a release, the rollback ordering is the reverse: revert the plugin `CLI_PIN` bump first, then delete the tag.

The same discipline applies to the initial `v0.1.0` release: the tag was pushed before the plugin's `CLI_PIN`, `install.sh`, and documentation literals were updated to reference it.

---

## Release workflow internals

`.github/workflows/release.yml` triggers on tag push and:

1. Checks out the tagged commit.
2. Sets up `uv` via `astral-sh/setup-uv@v3`.
3. Runs `uv build --wheel`. Output: `dist/cortex_command-X.Y.Z-py3-none-any.whl`.
4. Creates a GitHub Release with the wheel as an asset (via `softprops/action-gh-release@v2` or `gh release create`).

The workflow needs `permissions: contents: write` for release creation. Tag-trigger pattern: `tags: ['v[0-9]+.[0-9]+.[0-9]+']` — matches stable semver tags only.

The local-test equivalent of the workflow is `tests/test_no_clone_install.py::test_target_state`, which builds the wheel via `uv build`, installs in a tmpdir-isolated env, and asserts the wheel-installed CLI works correctly. This test runs on every PR; the actual tag-trigger workflow only fires on tag push.

---

## Rollback

If a release publishes a broken build:

1. **Delete the remote tag**: `git push --delete origin vX.Y.Z` (single-maintainer repo; safe if no users have installed against it yet — but unsafe once they have, because deletion orphans their `CLI_PIN[0]` references).
2. **Delete the local tag**: `git tag -d vX.Y.Z`.
3. **Delete the GitHub Release**: `gh release delete vX.Y.Z --yes`.
4. Fix the underlying issue.
5. Cut a new patch release with the fix.

In practice, prefer cutting a new patch release (`vX.Y.Z+1`) over deleting the broken tag — deleting tags that may have been picked up by external users is risky. Delete only when you are confident no installs have happened against the broken tag.
