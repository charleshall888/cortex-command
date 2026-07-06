# Release-type markers

The auto-release workflow runs on every push to `main` and invokes `cortex-auto-bump-version` to pick the next semver tag. Default: **patch**. Override by placing a marker token on its own line in the commit body:

- `[release-type: major]` — breaking change.
- `[release-type: minor]` — new, backward-compatible feature.

The marker must be alone on its own line (modulo whitespace), or it's ignored. Matched via:

```
(?im)^\s*\[release-type:\s*(major|minor)\s*\]\s*$
```

**Precedence** across commits since the last tag: `major` > `minor` > `patch`.

**`BREAKING:` fallback**: a column-0 `BREAKING:` or `BREAKING CHANGE:` token (matching `(?im)^BREAKING(?:\s+CHANGE)?:`) forces major even over an explicit `minor` marker; indented mentions don't fire. The explicit marker is preferred — this is a backstop.

**Pre-merge check**: `cortex-auto-bump-version --dry-run` against the PR branch previews the tag the workflow will produce — read-only, exits 0 even on `no-bump`.
