# Release-type markers

The auto-release workflow runs on every push to `main` and invokes `cortex-auto-bump-version` to determine the next semver tag. The default is a **patch** bump. To override, place a marker token on its own line in the commit message body:

- `[release-type: major]` — bump major version (breaking change).
- `[release-type: minor]` — bump minor version (new feature, backward-compatible).

**Positional anchor**: the marker must appear as the entire content of its own line, modulo surrounding whitespace. The auto-bump helper matches:

```
(?im)^\s*\[release-type:\s*(major|minor)\s*\]\s*$
```

A marker embedded mid-line or inside prose is ignored.

**Precedence** when multiple commits since the last tag carry markers: `major` > `minor` > `patch`.

**`BREAKING:` fallback**: if any commit body contains a column-0 `BREAKING:` or `BREAKING CHANGE:` token (case-insensitive, matching `(?im)^BREAKING(?:\s+CHANGE)?:`), the helper treats the range as a major-bump even if the explicit marker says `minor`. Indented mentions (e.g., bullet continuations describing the fallback) do not fire. Prefer the explicit marker; `BREAKING:` is a backstop.

**Pre-merge verification**: before merging a PR, run `cortex-auto-bump-version --dry-run` locally against the PR branch to confirm the tag the auto-release workflow will produce. The flag performs the same parsing with no filesystem mutations and exits 0 even on `no-bump`.

## Examples

Major bump:

```
Migrate envelope schema to v2.0

The state file format is now incompatible with v1.x consumers.

[release-type: major]
```

Minor bump:

```
Add --dry-run flag to cortex-auto-bump-version

Read-only mode for pre-merge verification of the next tag.

[release-type: minor]
```
