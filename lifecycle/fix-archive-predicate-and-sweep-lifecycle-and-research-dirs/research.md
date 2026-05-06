# Research: Fix archive predicate and sweep lifecycle/ and research/ dirs

## Epic Reference

This lifecycle is decomposed from epic [[165-repo-spring-cleaning]]. Background discovery lives in `research/repo-spring-cleaning/research.md`; this artifact scopes only #169 (predicate fix + lifecycle/research archive sweep). It does not duplicate epic-level content — sibling tickets #166 (docs reorg + README), #167 (consolidated docs cleanup), and #168 (orphan code/script deletion) are out of scope and tracked in their own backlog items.

## Codebase Analysis

### Files that will change

**Direct changes required**:

- `justfile:212` — replace JSON-only predicate with the proposed JSON+YAML alternation regex. The current line reads `grep -q '"feature_complete"' "$events_log" || continue`.
- `bin/cortex-archive-rewrite-paths` — add `--exclude-dir` flag (Mitigation Option 1). Argparse signature is at lines 164–189; walk logic at lines 72–94; exclusion machinery at lines 64–69 (`EXCLUDED_DIR_NAMES = {".git", ".venv"}` and `EXCLUDED_REL_PREFIXES = (Path("lifecycle/archive"), Path("lifecycle/sessions"), Path("retros"), Path(".claude/worktrees"))`). Atomic write at lines 131–136 via tempfile + `os.replace`. JSON output (NDJSON) at lines 201–206.
- `plugins/cortex-core/bin/cortex-archive-rewrite-paths` — auto-mirrored by `.githooks/pre-commit` after canonical change; no manual edit.
- `tests/test_archive_rewrite_paths.py` — extend with `--exclude-dir` flag tests, normalization tests (trailing slash, leading `./`), and a slug-shape-validation guard test.
- New test file (or extension to an existing one) — integration-level "every `lifecycle/<slug>` reference resolves" test (~80 LoC pytest).

**Sweep operations (no source edits, but git-tracked moves)**:

- `git mv lifecycle/<slug>/ lifecycle/archive/<slug>/` for ~30 candidate dirs (predicate-eligible after F-9a fix).
- `git mv lifecycle/<slug>/ lifecycle/archive/<slug>/` for 4 manual-archive dirs that lack `feature_complete` events (named in F-9c scope).
- `rm -rf lifecycle/feat-a/` for the 1 genuine test-detritus dir.
- `mkdir -p research/archive/` then `git mv research/<slug>/ research/archive/<slug>/` for ~30 stale research dirs.

**Cross-reference rewriting** (executed by `bin/cortex-archive-rewrite-paths` after each `git mv`):

- `*.md` files in repo root (excluding `.git/`, `.venv/`, `lifecycle/archive/`, `lifecycle/sessions/`, `retros/`, `.claude/worktrees/`, plus the new exclude-dir set).
- Contains both body-text citations (`lifecycle/<slug>/research.md`) and frontmatter path-form fields (`spec: lifecycle/<slug>/spec.md`, `discovery_source: lifecycle/<slug>/research.md`). Both are rewritten — the helper walks `*.md` text and does not skip frontmatter blocks. Only bare-slug fields like `lifecycle_slug: <slug>` (no `lifecycle/` prefix) are unaffected.

### Dual-source mechanics

- `bin/cortex-archive-rewrite-paths` is canonical; `plugins/cortex-core/bin/cortex-archive-rewrite-paths` is the auto-generated mirror.
- `.githooks/pre-commit` auto-mirrors any `bin/cortex-*` edit to the plugin tree; no manual sync needed.
- `bin/.parity-exceptions.md` (lines 17–21) lists allowlist exemptions. `cortex-archive-rewrite-paths` is **not** exempted; it is currently wired through `justfile:276`, so adding `--exclude-dir` does not require an exemption update.

### Current state counts (verified at research time, 2026-05-05)

- **Top-level lifecycle dirs**: ~39–47 entries depending on what is excluded. The discovery's "37" baseline is stale by 7+ dirs (new in-flight tickets including #166, #167, #168, and this very ticket #169 have created their own lifecycle dirs since the discovery ran). Action: F-9b's table must be re-counted at execution time; the disposition table cannot rely on the discovery's baseline.
- **Already in `lifecycle/archive/`**: 111 dirs.
- **Top-level research dirs**: 33 (discovery said 32; one new dir added since).
- **`research/archive/`**: does not exist; F-10 creates it.

### Predicate-eligible vs. predicate-skipped — current state

- Under the **legacy** predicate (`grep -q '"feature_complete"' "$events_log"`): ~19 dirs eligible (JSON-form events).
- Under the **proposed** predicate (`grep -qE '"event":[[:space:]]*"feature_complete"|^[[:space:]]*event:[[:space:]]*feature_complete[[:space:]]*$'`): ~30 dirs eligible (adds ~11 YAML-form-only dirs).
- The legacy predicate's blind spot is the dir set that emits events.log entries in YAML block format (e.g., `extend-setup-merge-with-dynamic-per-component-opt-in-for-skills-and-hooks/events.log:182`); these accumulated post-2026-04-29 with the YAML-style emitter rollout.

### Cross-reference inventory (live, at-risk during sweep)

Confirmed grep results:

- `research/repo-spring-cleaning/research.md` — ~16 `lifecycle/<slug>/...` body-text citations + the discovery's mitigation-options discussion that names `research/repo-spring-cleaning/` and `research/opus-4-7-harness-adaptation/` explicitly.
- `research/repo-spring-cleaning/decomposed.md` — sequencing notes referencing `lifecycle/archive/` paths.
- `research/opus-4-7-harness-adaptation/research.md` — 4 lifecycle citations (alive epic #82 per CLAUDE.md).
- `backlog/029-add-playwright-mcp-for-dashboard-visual-evaluation.md:59` — cites `lifecycle/add-playwright-htmx-test-patterns-to-dev-toolchain/research.md` as research source.
- **21+ backlog tickets** with frontmatter `spec: lifecycle/<slug>/spec.md` and `discovery_source: lifecycle/<slug>/research.md` paths. **These ARE rewritten** by the helper — frontmatter is inside `*.md` files and the helper walks all `*.md` content, not just body. The ticket body's claim at line 73 ("backlog frontmatter `lifecycle_slug:` fields use bare slugs without prefix, so frontmatter is safe") is only true for the `lifecycle_slug:` field; `spec:` and `discovery_source:` fields use full path form and are rewritten.
- Multiple secondary research artifacts (e.g., `research/competing-plan-synthesis/research.md`, `research/overnight-plan-building/research.md`) contain bare `lifecycle/` references.
- **No in-flight `lifecycle/*166*` or `lifecycle/*168*` dirs** currently exist in the repo (verified via `ls lifecycle/` — sibling tickets have not yet started or have not yet produced lifecycle artifacts visible to #169's sweep).

### `cortex_command/cli.py:268`

Verified verbatim — line 268 currently reads `"see docs/mcp-contract.md."` (period included). #166 has not yet updated this to `docs/internals/mcp-contract.md`. Per the ticket's "Code-reference paired update" requirement, #169 must run after #166 has updated this line, OR #169 must verify the current state matches what the rewrite-paths recipe will encounter.

### Active worktrees

`git worktree list` reports 5 active worktrees. Per `justfile:198–209`, the recipe skips active-worktree slugs. F-9b's disposition table must cross-check against `git worktree list` output at execution time, not just the predicate match.

### Sandbox / write permissions

Per `requirements/project.md:26`, `cortex init` registers only the repo's `lifecycle/` path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array. **`research/archive/` is brand new** — it is not in any registered allow-list. F-10 may hit a sandbox-write prompt the first time it runs `mkdir research/archive`. Local sandbox state should be inspected before F-10 executes.

## Web Research

### Archive sweep patterns in monorepos

Two competing OSS conventions:

- **Stable path + status label** (Rust RFCs — [rust-lang/rfcs](https://github.com/rust-lang/rfcs)): never move accepted/postponed RFCs; signal lifecycle via PR labels and external boards. Minimizes link breakage. Quote: "An RFC closed with 'postponed' is marked as such because we want neither to think about evaluating the proposal nor about implementing the described feature until some time in the future."
- **Explicit `archive/` or `legacy/` subdir** ([Animesh Sahu — Mono-Repos to the Rescue](https://animeshz.github.io/site/blogs/mono-repos-archiving-github-projects.html)): move stale work into a subdir; leave a one-line redirect stub. Mitigation pattern across all sources: leave a redirect or only move things nothing live points at.

The most-cited risk is broken cross-references when files move. Cortex's chosen direction (subdir + path-rewrite recipe) is consistent with the second convention.

### Bulk-rewrite cross-references safely

- `git mv` does **not** auto-rewrite content references — it is functionally `rm + add` ([git-mv docs](https://git-scm.com/docs/git-mv)).
- Structural rewrite tools: [Comby](https://github.com/comby-tools/comby) (template holes; understands code blocks/strings/comments), `sd`, [rg-sed](https://github.com/hauntsaninja/rg-sed). Cortex's helper is a custom Python implementation in this family.
- Anti-patterns explicitly called out:
  - `sed -i` recursive without `--exclude` corrupts `.git/`/binaries.
  - macOS BSD `sed` differs from GNU `sed` (`sed -i ''` vs `sed -i`); cortex runs on macOS.
  - Two-step preview pattern ("generate `mv`/replace commands as text, eyeball them, pipe to `bash`") is the consensus safe path.
- The cortex helper already uses atomic writes via tempfile + `os.replace` — strong recovery posture if a write crashes mid-run.

### Robust grep predicates over JSON-lines + YAML-mixed files

- The strongest cited anti-pattern is using `grep` on heterogeneous structured logs at all when `jq` would suffice ([Rich Seymour — JSON, JSONlines, and jq as a better grep](https://zxvf.org/post/jq-as-grep/)). However, `jq` does not parse YAML, and cortex's events.log mixes both formats, so `grep -E` with anchored alternation is the appropriate choice.
- Anti-patterns to avoid:
  - **Over-broad alternation** matching prose that mentions the token (mitigation: anchor each branch to format-specific punctuation).
  - **Unanchored patterns** without `\b` word boundaries or `^`/`$` line anchors.
  - **Multi-line pretty-printed JSON** that breaks line-by-line `grep` (cortex events.log is line-oriented NDJSON or YAML-block — verified, no pretty-print spanning lines).
- macOS BSD `grep -E` portability soft-spot: `\b` works in some BSD builds but is documented as POSIX ERE which lacks it. The trailing-anchor form `feature_complete[[:space:]]*$` is safer than `feature_complete\b`. The cortex helper at `bin/cortex-archive-rewrite-paths:14–19` explicitly avoids `\b` in adjacent regex contexts for this reason.

### GitHub repo-render polish for installer-audience repos

Top installable CLI tools verified (`uv`, `ruff`, `gh`, `tldr-pages`):

- **None expose `lifecycle/` or `research/` at repo root.** Working state lives in `docs/`, GitHub Issues, or `.github/` — never the root listing.
- README + immediate root listing IS the installer-evaluator first-impression surface. Forkers traverse deeper.
- Sources confirming the README+root-listing as a single first-impression surface: [DEV — How to create the perfect README](https://dev.to/github/how-to-create-the-perfect-readme-for-your-open-source-project-1k69), [PyOpenSci README guidelines](https://www.pyopensci.org/python-package-guide/documentation/repository-files/readme-file-best-practices.html), [OSSF Concise Guide for Evaluating OSS](https://github.com/ossf/wg-best-practices-os-developers/blob/main/docs/Concise-Guide-for-Evaluating-Open-Source-Software.md).

The qualitative case is strong; no source measured the specific impact of working-state subdirectories at repo root on installer abandonment rates.

## Requirements & Constraints

### From `requirements/project.md`

- **File-based state** (line 25): lifecycle artifacts use plain files (markdown, JSON, YAML frontmatter); no database. The archive sweep operates inside this constraint.
- **Dual-source enforcement** (line 27): `bin/cortex-*` scripts must be wired through SKILL.md/requirements/docs/hooks/justfile/tests references. `bin/cortex-check-parity` is the static gate. `bin/.parity-exceptions.md` lists allowlist exceptions.
- **Sandbox preflight gate** (line 28): not directly applicable to #169 (#169 doesn't touch sandbox-source files).
- **CLI distribution** (line 6, 56): `uv tool install git+<url>@<tag>`; cloning/forking is secondary.

### From `CLAUDE.md`

- **Dual-source convention** (line 18, 48): `bin/` mirrors to `plugins/cortex-core/bin/`. The pre-commit hook handles the mirror.
- **MUST-escalation policy** (post-Opus 4.7): default to soft positive-routing; new MUSTs require an evidence-artifact link. #169 introduces no new MUST language.
- **CLAUDE.md 100-line cap**: currently below 100. #169 does not edit CLAUDE.md, so the cap is not implicated. (Caveat: if a sequencing-rebase against #166 changes line counts, watch for accidental cap breach.)
- **Doc ownership rule** (line 50): not directly applicable.

### From `requirements/pipeline.md`

- **Metrics from `feature_complete` events** (lines 103–107): per-feature complexity tier, task count, batch count, rework cycles, review verdicts, phase durations are computed from these events. The predicate fix in F-9a directly affects which dirs contribute to metrics; YAML-form dirs currently silently skip metrics.
- `pipeline.md:130` references retired `claude/reference/output-floors.md`. Sibling #166 fixes this stale reference under its F-5 scope before #169 runs.

### `bin/.parity-exceptions.md` allowlist

Lines 17–21:

| script | category | rationale |
|---|---|---|
| `cortex-archive-sample-select` | maintainer-only-tool | manually invoked when archiving a session |
| `cortex-batch-runner` | library-internal | spawned by Python source via subprocess |

`cortex-archive-rewrite-paths` is **not** in the allowlist. It must remain wired through justfile/SKILL.md/tests.

### Sibling-ticket couplings

- **#166** moves `docs/{pipeline,sdk,mcp-contract}.md` → `docs/internals/`; updates `CLAUDE.md:50` cross-refs; updates `cortex_command/cli.py:268` runtime stderr message; updates `bin/cortex-check-parity:59` script comment + plugin mirror.
- **#168** deletes `plugins/cortex-overnight-integration/`, 4 one-shot scripts, and paired tests; DR-4 deletes-or-retains `claude/hooks/cortex-output-filter.sh` + `cortex-sync-permissions.py` paired with `requirements/project.md:36` retirement.
- **#169 must land after both #166 and #168 commit** (in-prose sequencing constraint; not encoded in `blocked-by:` frontmatter).
- **`cortex_command/cli.py:268` paired update**: the `"see docs/mcp-contract.md."` message must be updated by #166 before #169's path-rewrite crosses any `docs/internals/` reference.

### Existing tests

- `tests/test_archive_rewrite_paths.py` (~14978 bytes) — covers helper correctness for slash/wikilink/bare-slug citation forms, substring collision detection, regex metacharacter escaping, atomic writes, directory exclusions, dry-run mode, NDJSON stdout protocol.
- `tests/test_lifecycle_phase_parity.py` — three-layer parity test (hook glue, statusline ladder, hook E2E vs. canonical Python detector).
- `tests/test_events.py` — regression tests for log_event string-literal registration.
- **Gap**: no integration-level test asserts that every `lifecycle/<slug>` reference in tracked `*.md` resolves to either `lifecycle/<slug>/` or `lifecycle/archive/<slug>/`. This is the test most worth adding under #169.

### DR-2 framing

Discovery decision: DR-2 = Option C (leave lifecycle/research dir top-level visibility alone post-archive-run). The visibility cleanup is deferred until post-archive observation. F-10's `research/archive/` subdir creation is consistent with this decision and leaves the door open for a later DR-2 epic to gitignore-hide or relocate to `.cortex/` if desired.

## Tradeoffs & Alternatives

### Mitigation options for the `cortex-archive-rewrite-paths` blast radius

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| **Option 1 — `--exclude-dir` flag** | Durable; future archive sweeps inherit protection. Symmetric with existing `EXCLUDED_REL_PREFIXES` design (lines 64–69). Test scaffolding already exists. | Touches dual-sourced helper; requires coordinated `justfile` change. Pre-commit hook regenerates the mirror. | **Recommended.** |
| Option 2 — Sequence-and-accept | Zero code change. Forces clean-tree precondition via existing precheck (justfile:160–163). | Asymmetric protection by accident. Live research artifacts read as if their referents are already archived (tense mismatch). Couples discipline into operator memory. Doesn't scale to future sweeps. | Reject. |
| Alt C — Temp-stash | No code change. | Stashed live artifact retains pre-rewrite citations after restore — defeats the goal. Citations stay stale. | Reject. |
| Alt D — Hardcoded allowlist in helper | Smallest diff. | Couples ephemeral knowledge into a shared utility; entries become stale when those research dirs are themselves archived. | Reject. |
| Alt E — Wrapper script | Zero touch on the helper. | Parallel naming hierarchy violates `cortex-archive-*` single-purpose convention. Reimplements boundary logic. | Reject. |
| Alt F — Predicate-scoped rewrite (`--files-list`) | Most surgical. | Refactor of helper signature; invalidates ~16 unit tests; weakens helper's "guarantees correctness across all repo `*.md`" invariant. | Reject (too large for the value). |
| Alt G — Defer rewrite entirely | Trivial. | Breaks the load-bearing acceptance signal (`backlog/029` citation). | Reject (consistent with ticket). |
| Alt H — Pre-flight detector + abort | Defense-in-depth; composable with Option 1; uses existing dry-run output. | Doesn't solve the problem alone; signals only. | Optional add-on. |
| Alt I — `.archive-rewrite-ignore` dotfile | Per-repo, survives across sweeps. | New config surface; cortex tends toward "config in justfile/CLAUDE.md, not new dotfiles". Failure mode is silent (empty/absent file). | Reject. |

**Recommended**: Option 1 + Alt H (preflight detector as optional add-on). Alt H can ship as a follow-up if Option 1's `--exclude-dir` proves insufficient in practice.

### F-9a regex alternatives

Proposed regex (from ticket): `'"event":[[:space:]]*"feature_complete"|^[[:space:]]*event:[[:space:]]*feature_complete[[:space:]]*$'`

- **Drop quoting alone** — line-noise fragile (any prose mentioning the token trips archive). Reject.
- **Two grep invocations OR'd** — readable; two file reads per candidate. Acceptable, not preferred.
- **Python script in `bin/`** — overkill for a one-line predicate; new bin/ entry pays dual-source overhead. Reject.
- **jq-based** — doesn't help YAML form (events.log mixes both). Reject.
- **`\b` word boundary instead of full anchors** — macOS BSD `grep -E` portability soft-spot; the existing helper at `bin/cortex-archive-rewrite-paths:14–19` already avoids `\b` for related reasons. **Reject; use the trailing-anchor form (`feature_complete[[:space:]]*$`) per the ticket spec.**

The proposed regex is correct. Add an inline justfile comment documenting the two formats it covers.

### F-10 clutter-reduction alternatives

- **`research/archive/` subdir** — recommended. Mirrors `lifecycle/archive/`. Smallest move; leaves DR-2 free for a later epic.
- Gitignore-hide stale dirs — wrong tool (only affects untracked files; tracked dirs stay rendered).
- Relocate to `.cortex/research-archive/` — forces a `.cortex/` namespace decision; bigger commitment than a sibling subdir.
- Dotfile-prefix individual dirs — breaks `research/[a-z]*` glob patterns.
- Move to a sibling repo or branch — loses `git log` traversal across the move; major operator overhead.

When `research/archive/` is created, **add it to `EXCLUDED_REL_PREFIXES` in the helper** as a paired change. Otherwise future rewrites would recurse into archived research and rewrite citations inside archived artifacts.

### Sequencing strategy

Three logical pieces in #169:

- (a) Predicate fix in `justfile:212`.
- (b) `--exclude-dir` flag in helper + `research/archive/` paired exclusion + tests.
- (c) Lifecycle sweep (predicate-eligible + 4 manual + delete `feat-a/`).
- (d) Research sweep (`mkdir research/archive/` + `git mv` + `bin/cortex-archive-rewrite-paths` rewrite pass).

Recommended: **3 commits**:

- **Commit 1** — (a) + (b) + tests + integration-test scaffold. Pure code; bisect-friendly; pre-commit-validated.
- **Commit 2** — (c) lifecycle sweep with manifest.
- **Commit 3** — (d) research sweep with `research/archive/` creation + manifest.

Rationale: code changes deserve their own pre-commit-validated commit; sweeps are bulk data moves that revert cleanly if a regression appears.

### Verification strategy

- **Spot-check** (current acceptance signal) — low coverage, brittle to line-number drift.
- **Comprehensive grep + visual diff** — medium coverage; catches rewrites done wrong but not rewrites missed.
- **Integration test (recommended)** — high coverage. ~80 LoC pytest:
  1. Walk every tracked `*.md`.
  2. Match three citation forms: `lifecycle/<slug>` (slash-form body text and frontmatter path-form like `spec: lifecycle/<slug>/...`), `[[lifecycle/<slug>` (wikilinks), and bare-slug frontmatter fields (`lifecycle_slug: <slug>`).
  3. For each citation, assert the slug exists at either `lifecycle/<slug>/` or `lifecycle/archive/<slug>/`.

This test is the single artifact that converts future sweep-anxiety into a CI gate.

## Adversarial Review

### Failure modes and edge cases

- **Disposition baseline drift**: discovery's "37 dirs" is stale by 7+ entries; current count is ~44 disposition-eligible. F-9b's table must be re-counted at execution time, not from the discovery's baseline. Cross-check against `git worktree list` to skip active-worktree slugs.
- **Web agent's recommended regex shape lacks the `[[:space:]]*` prefix** before `event:`; copying it verbatim would match zero real YAML events (every YAML-form line is 2-space indented inside a YAML sequence). Use the ticket's proposed regex, not the web agent's.
- **`\b` after `feature_complete` is fragile across grep variants on macOS BSD**. The trailing-anchor form `feature_complete[[:space:]]*$` (per the ticket's exact spec text) is portable and rejects inline trailing comments. Do not substitute `\b` in implementation.
- **Helper has zero slug-shape validation**. A typo (`--slug ../etc`) would write literal `../etc` rewrites into every matching `*.md`. Add `re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug)` guard in commit 1.
- **Backlog frontmatter `spec:` and `discovery_source:` ARE rewritten by the helper** — they live inside `*.md` files in path form. The ticket's "frontmatter is safe" claim (line 73) is only true for bare-slug `lifecycle_slug:` fields. The integration test must therefore handle three matchers: slash-path, wikilink, and bare-slug-frontmatter — not two.
- **`research/archive/` is not in any sandbox `allowWrite` registration**. `cortex init` registers only `lifecycle/`. F-10 may hit a sandbox-write prompt when it runs `mkdir research/archive/`. Either extend `cortex init` to register `research/`, or document a manual `~/.claude/settings.local.json` precondition before F-10 executes.
- **Acceptance-signal canary `backlog/029-...md:59` is line-number-anchored** and will drift if the ticket body is edited. Replace with a content-grep canary: `grep -q 'lifecycle/archive/add-playwright-htmx-test-patterns-to-dev-toolchain' backlog/029-*.md`.
- **No re-validation step exists between F-9b table commit and F-9c execution**. If a new lifecycle dir starts during the implementation window, the table is stale. Bake a `just lifecycle-archive --dry-run` re-validation into the F-9c protocol; abort if the candidate set diverges from the table.
- **Option 1's exclude-list named in the ticket is too narrow** (`research/repo-spring-cleaning research/opus-4-7-harness-adaptation` only). Under F-10, rewriting citations inside research dirs that are themselves about to be archived turns archived research artifacts into back-dated documents — silent integrity loss. Consider expanding the exclude-list to cover all research dirs being archived in F-10 (preserve their original citations as historical record).
- **Cross-reference rewriting at the live↔dead boundary**: under Option 1, citations to archived slugs in the protected research artifacts STAY pointing at `lifecycle/<slug>/` — but those top-level dirs are now empty (moved to archive). The live artifact's citations are now broken. The design implicitly assumes the operator manually updates the live artifact post-sweep, but the verification step is not specified. Solution: include the live research artifacts in a post-sweep audit pass (e.g., the integration test), not just exclude them from the helper's walk.
- **Pre-commit hook auto-mirror failure mid-sweep**: commit 1 modifies `bin/cortex-archive-rewrite-paths`; the hook regenerates the plugin mirror. If the mirror regen fails, commit 1 fails, and a partial state could collide on retry. No rollback story is documented; rely on the hook's atomicity and add a manual mirror-checksum check to the spec.
- **Sequencing-rebase trap**: #166 + #168 must commit before #169. The `blocked-by:` frontmatter is empty; the constraint is in prose only. Encode it as a precondition in the spec; if the overnight runner queues these tickets concurrently, nothing prevents simultaneous start.

### Security concerns

- **No input validation on `--slug`**: argparse currently accepts any string. A typoed or hostile slug (`../etc`) would write `lifecycle/../etc` literals into every matching `*.md`. Add a `re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug)` guard to the helper as part of commit 1. No agent suggested this.

### Assumptions that may not hold

- **GitHub-render reaches installer-evaluators**: qualitatively well-supported (multiple README/first-impression sources confirm the README + root-listing is the first-impression surface) but unmeasured quantitatively for the specific case of working-state subdirectories at repo root. The sweep's value to installers is directional, not measured.
- **Forker affordance trade-off**: `requirements/project.md` lists "clone or fork" as a secondary audience; lifecycle/ at root demonstrates active development to forkers. The sweep delivers cleanup-for-installers with a small institutional-memory cost for forkers. The ticket frames this as zero-downside; it is small-downside (resolved by the visible `lifecycle/archive/` subdir, but slightly less visible than top-level entries).
- **Static disposition table is correct at execution time**: the discovery's table is already stale; assume the F-9b table will also be stale by F-9c execution unless re-validated.

### Recommended mitigations

- Add slug-shape validation to the helper in commit 1.
- Use the trailing-anchor form (`feature_complete[[:space:]]*$`), not `\b`, in the implementation.
- Replace the line-number canary in acceptance signals with a content-grep canary.
- Pre-register `research/archive/` in sandbox `allowWrite` before F-10 runs.
- Add a `just lifecycle-archive --dry-run` re-validation step between F-9b and F-9c.
- Make `--exclude-dir` paths normalize to root-relative (handle trailing slash, leading `./`) and reject out-of-root paths.
- Consider expanding the exclude-list to all F-10-archived research dirs (preserves historical record).
- Include live research artifacts in a post-sweep audit pass to catch citations broken at the live↔dead boundary.

## Open Questions

1. **Exclude-list scope (Option 1)**: should `--exclude-dir` only protect the 2 currently-named live research dirs (`research/repo-spring-cleaning`, `research/opus-4-7-harness-adaptation`), or expand to cover all research dirs being archived in F-10 to preserve their original citations as historical record? Deferred: will be resolved in Spec — affects scope of the exclude-list flag's invocation, not the flag's existence.

2. **Slug-shape validation in the helper**: should `bin/cortex-archive-rewrite-paths` gain `re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug)` input validation as part of #169's commit 1, or should this scope out to a separate ticket? Deferred: will be resolved in Spec — small bin/ scope expansion vs. ticket-discipline tradeoff. Recommended in-scope here because the helper edit is already in #169.

3. **F-9c re-validation step**: should the implementation include a `just lifecycle-archive --dry-run` re-validation between F-9b table commit and F-9c execution, with an abort-and-refresh protocol if the candidate set diverges? Deferred: will be resolved in Spec — the answer is almost certainly yes (the discovery baseline is already stale), but the abort/refresh protocol details belong in spec.

4. **Sandbox `allowWrite` for `research/archive/`**: should `cortex init` be extended to register `research/` (parent of `research/archive/`), or should the spec document a manual `~/.claude/settings.local.json` precondition? Deferred: will be resolved in Spec — `cortex init` extension is a small change but might be out of scope; manual precondition is cheaper but more brittle.

## Considerations Addressed

- **Validate that the GitHub-repo-render impact of sweeping lifecycle and research dirs reaches installer-evaluator visibility (people browsing the repo to decide whether to install cortex), not only forker-facing surface**: Web Research found qualitative support — top installable CLIs (`uv`, `ruff`, `gh`, `tldr-pages`) all keep working state out of repo root, and multiple README/first-impression sources confirm the README + root listing is a single first-impression surface for installer-evaluators. No quantitative measurement was found that isolates working-state subdirectories at root as an adoption deterrent. Counter-finding from Adversarial Review: forkers benefit from visible lifecycle artifacts (per `requirements/project.md`'s secondary "clone or fork" audience), so the sweep delivers cleanup-for-installers with a small institutional-memory cost for forkers — directionally correct, but the value-to-cost ratio is not measured. Net: the consideration is supported enough to motivate the sweep, but the spec should state explicitly that the installer-evaluator value is directional, not measured, and that DR-2 (further visibility cleanup) is deferred for post-archive observation.
