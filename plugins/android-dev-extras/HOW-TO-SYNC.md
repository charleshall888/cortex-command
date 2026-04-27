# HOW-TO-SYNC

How to refresh the skills vendored in this plugin against their upstream source.

## Why this plugin exists

Android-repo projects (like this plugin's consumer, `chickfila-android`) need Android-specific Claude skills, but shared overnight-runner infrastructure and non-Android projects shouldn't carry them. This plugin is a **per-project-toggle** capsule — enable it via marketplace registration on a per-project basis (see the marketplace README at the repo root for the mechanics); projects that don't need it simply don't enable it.

The **curation bar** for what gets vendored here is three-part: (i) **non-destructive** — no file-rewriting or destructive subcommand flows by default; (ii) **non-version-coupled** — the skill's value doesn't hinge on a specific AGP/Compose/gradle version; (iii) **cross-project-applicable** — useful to more than one Android project, not scoped to CFA-specific code paths. Skills that fail any of the three land in `### Deferred candidates` with rationale.

## Upstream source

- **Authoritative primary**: `dl.google.com/dac/dac_skills.zip` — the Developer Asset Content (DAC) bundle. This URL is undocumented by Google (not listed at [developer.android.com/tools/agents/android-skills](https://developer.android.com/tools/agents/android-skills)) but is the source of truth referenced by the `android` CLI's own update workflow (`~/.android/cli/skills/.github/workflows/update-skills.yml`). License: Apache 2.0 (copied verbatim as `./LICENSE`).
- **Convenience mirror**: [github.com/android/skills](https://github.com/android/skills) — publicly-attested tags (v0.0.1, v0.0.2 at the time of initial vendoring), useful for browsing diffs and tactical fetches. Its `main` branch is a merge of DAC content + a `github-skills` branch overlay; its release zip at `v*.*.*` is byte-equivalent to the DAC bundle at the same release (DAC zip omits `README.md`; otherwise identical content tree).
- **Fallback**: if the DAC URL becomes unreachable on a future refresh, fetch the GitHub release zip at the matching tag (`https://github.com/android/skills/archive/refs/tags/v*.*.*.zip`) as a substitute.
- **Skills NOT distributed through either channel** (e.g., `android-cli`, which ships only with the `android` CLI binary's install): see `### Accepted divergences` for the source and re-sync policy.
- Contributions: upstream does not accept public PRs. Curate locally; open issues upstream if you want changes.

## Path mapping (normative)

Upstream uses a category taxonomy; this plugin flattens it. Category prefix is dropped:

| Upstream | Vendored here |
|----------|---------------|
| `performance/r8-analyzer/SKILL.md` | `skills/r8-analyzer/SKILL.md` |
| `performance/r8-analyzer/references/**` | `skills/r8-analyzer/references/**` |
| `system/edge-to-edge/SKILL.md` | `skills/edge-to-edge/SKILL.md` |
| `<category>/<skill>/SKILL.md` | `skills/<skill>/SKILL.md` (for any future-added skill) |
| `<category>/<skill>/references/**` | `skills/<skill>/references/**` |

If two upstream skills ever collide on skill name after the category prefix is dropped, stop and resolve by keeping the category prefix in the vendored name (e.g., `skills/performance-x/` vs `skills/navigation-x/`). This has not occurred as of the initial vendoring (2026-04-17).

## Sync procedure

This is an AI-guided workflow, not an automated script. Next time you want to refresh:

1. Open a Claude Code session in this plugin directory.
2. Ask Claude: "sync android skills per HOW-TO-SYNC.md."
3. Claude should:
   - Fetch the upstream tree: `gh api "repos/android/skills/git/trees/main?recursive=1"` (for DAC/GitHub-sourced skills) OR run `android init` to refresh `~/.android/cli/skills/` (for CLI-bundled skills listed in `### Accepted divergences`).
   - For each currently-vendored skill, fetch upstream SKILL.md and `references/**`, compare against vendored copy.
   - **Divergence preservation** (for every file listed in `### Accepted divergences`): BEFORE the verbatim overwrite, snapshot the vendored copy's divergence content (the CFA-PATCH marker, the guard block, and any inline markers cited in the entry). AFTER the overwrite, reapply the divergence content per the entry's placement rule — reapply at the position relative to the post-pull frontmatter/first-heading boundaries, NOT at literal pre-pull byte offsets. The `### Accepted divergences` section is the authoritative re-sync contract; consult it for each listed file.
   - Surface a diff summary: unchanged / content-modified / references added/removed / skill removed upstream.
   - For new skills in upstream that are NOT vendored here: list them and ask whether to curate any in. Do not add them silently.
   - Update `LICENSE` if upstream `LICENSE.txt` has changed (verbatim copy).
   - Update `NOTICE` if the upstream copyright year or attribution has changed.
   - **Post-update safety check** (for every file listed in `### Accepted divergences`): verify the `CFA-PATCH` marker is present in the post-update file AND positioned inside the frontmatter→first-heading window (between the closing frontmatter `---` and the first `#` heading). A marker that is absent OR present-but-mispositioned fails the sync; investigate before proceeding.
4. Run `android skills list` and reconcile its output against the union of `### Covered skills` + `### Deferred candidates`. Any skill in the CLI output that is absent from both lists surfaces a new curation decision — the curator must decide whether to cover or defer before completing sync; do NOT silently skip unlisted skills.
5. Run validation locally: `python3 scripts/validate-skill.py plugins/android-dev-extras/skills` (from the cortex-command-plugins repo root). Must exit 0 with no warnings.
6. Commit via the `/commit` skill. Never use raw `git commit` or `git -C`.
7. Push to GitHub remote — the marketplace source is `https://github.com/charleshall888/cortex-command-plugins.git`, so pushing is required for other project sessions to pick up changes.

## Apache 2.0 attribution obligation

Apache 2.0 § 4 requires distributing derivative works with:
- The original license text (→ `LICENSE` here).
- The original NOTICE file if one exists upstream (→ `NOTICE` here — authored when upstream ships no NOTICE; update verbatim if upstream adds one).
- Retention of copyright headers in modified files (only modify SKILL.md content if strictly necessary — prefer verbatim vendoring).

## Curation decisions worth revisiting

### Covered skills

- `r8-analyzer` — analyzes R8 keep rules and identifies redundancies; read-only.
- `edge-to-edge` — migrates Jetpack Compose apps to adaptive edge-to-edge; read-only analysis + targeted edits.
- `android-cli` — interacts with Android devices and emulators via the `android` CLI; see `### Accepted divergences` for source and guard patch.

### Accepted divergences

- **`skills/android-cli/SKILL.md`** — first accepted divergence from the verbatim-mirror policy. Two related divergences:
  - **Source channel**: android-cli is absent from both documented upstreams (`dl.google.com/dac/dac_skills.zip` and `github.com/android/skills` at any tag or branch). It ships only with the `android` CLI binary's install at `~/.android/cli/skills/android-cli/`. Initial vendoring source: local install at CLI version `0.7.15232955`. Re-sync requires running `android init` on the curator's machine to refresh the local copy before diffing; diff against public upstream is not possible.
  - **Content patch**: a Claude-specific detect-then-load guard is added at the top of the vendored SKILL.md — a `<!-- CFA-PATCH: ... -->` HTML comment marker followed by `` !`command -v android || echo NOT_INSTALLED` `` dynamic context injection plus a prose abort instruction. Rationale: per-project toggle for Claude Code users on machines without the Android CLI installed; the dynamic injection provides a runtime signal so Claude can abort `android`/`adb` flows when the binary is absent. The guard is advisory (relies on Claude reading the injected marker and honoring the adjacent abort instruction, not loader-level enforcement).
  - **Placement rule (durable re-sync guidance)**: the `CFA-PATCH` marker and guard block sit inside the body between the closing frontmatter `---` and the first `#` heading. On re-sync, reapply at that position relative to the post-pull frontmatter/first-heading boundaries — do NOT paste at literal byte offsets from the pre-pull file, and do NOT place the marker or guard below the first `#` heading (that violates the Apache 2.0 §4(b) "prominent notice" requirement).
  - **Post-update check**: after reapplying the guard, verify the `CFA-PATCH` marker is present AND positioned inside the frontmatter→first-heading window. A marker that is present but mispositioned fails the sync.

### Deferred candidates

- `agp-9-upgrade` — destructive (modifies gradle files); only relevant when upgrading AGP major version.
- `migrate-xml-views-to-jetpack-compose` — destructive, large cross-file edits.
- `navigation-3` — only relevant if actively migrating to Nav3.
- `play-billing-library-version-upgrade` — not applicable for CFA (no in-app billing).

To promote a deferred candidate to `### Covered skills`, run the sync procedure above and ask Claude to curate the specific skill in. Evaluate against the three-part curation bar (non-destructive, non-version-coupled, cross-project-applicable) documented in `## Why this plugin exists`.
