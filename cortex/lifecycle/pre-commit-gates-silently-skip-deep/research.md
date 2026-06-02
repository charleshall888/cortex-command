# Research: Fix silent under-scan in pre-commit checkers (`Path.match("**")` + `full_match` 3.12 break)

**Lifecycle:** pre-commit-gates-silently-skip-deep · **Backlog:** #282 · **Tier:** complex · **Criticality:** high

**Clarified intent:** Make the `--staged` corpus-membership tests in `cortex-check-parity`, `cortex-check-prescriptive-prose`, and `cortex-check-events-registry` correctly match deep-nested in-scope files (fixing the `Path.match("**")` single-segment under-scan that produces silent false-greens), and make `cortex-check-bare-python-import`'s `full_match` usage run on Python 3.12 — so every gate actually scans the files it claims to cover, on every supported Python.

> **Note on the ticket's prescribed fix.** The ticket prescribes `fnmatch.fnmatch` (mirroring #279's R8). Research **disconfirms** this as written — bare `fnmatch` and the `fnmatch(...) or fnmatch(..., pat.replace('/**/','/'))` variant both mis-match real corpus paths. The correct mechanism is an inlined `re`-only glob→regex translator (details in `## Matcher Mechanism`). #279's R8 itself is unlanded spec prose and prescribes the same incorrect `fnmatch` — see `## Open Questions`.

---

## Codebase Analysis

### Bug loci (exact paths/lines — verified)

| Checker | File | `--staged` membership site | Bug |
|---|---|---|---|
| `cortex-check-parity` | `cortex_command/parity_check.py` | `_matches_scan_glob` L685–695; call **L693** `p.match(glob)` | `**` under-scan |
| `cortex-check-prescriptive-prose` | `cortex_command/lint/prescriptive_prose.py` | `_matches_scan_glob` L243–248; call **L246** `p.match(glob)` | `**` under-scan |
| `cortex-check-events-registry` | `bin/cortex-check-events-registry` | `_matches_scan_glob` L390–395; call **L393** `p.match(glob)` | `**` under-scan |
| `cortex-check-bare-python-import` | `cortex_command/lint/bare_python_import.py` | `_matches_scan_glob` L453–462; call **L460** `p.full_match(glob)` | **AttributeError on 3.12** |
| `cortex-check-contract` (#279, **not in #282 scope**) | `cortex_command/lint/contract.py` | `_scan_staged` L1377–1380; call **L1378** `rel_path.match(glob)` | `**` under-scan (5th named site) |

> **Touch-point path correction:** the ticket lists `cortex_command/lint/parity_check.py`; the file is actually at `cortex_command/parity_check.py` (top of package, **not** under `lint/`). The other two `lint/` paths are correct.

### SCAN_GLOBS per checker (verified contents)

- **parity** (`SCAN_GLOBS`, public, L67): `CLAUDE.md`, `claude/hooks/cortex-*.sh`, `docs/**/*.md`, `hooks/cortex-*.sh`, `justfile`, `cortex/requirements/**/*.md`, `skills/**/*.md`, `tests/**/*.py`, `tests/**/*.sh` — **5 `**`-globs**
- **prescriptive-prose** (`SCAN_GLOBS`, public, L42): `skills/**/*.md`, `cortex/backlog/*.md` — 1 `**`-glob; the backlog glob is single-`*`
- **events-registry** (`SCAN_GLOBS`, public, L52): `skills/**/*.md`, `cortex_command/overnight/prompts/*.md` — 1 `**`-glob
- **bare-python** (`_SCAN_GLOBS`, private, L57): `skills/**/*.md`, `hooks/**`, `justfile`, `docs/**/*.md`, `tests/**/*.md`, `CLAUDE.md`, `cortex/requirements/**/*.md` (comment: "mirrors contract.py's `_SCAN_GLOBS`")
- **contract** (`_SCAN_GLOBS`, L419): identical tuple to bare-python's

### `--audit` vs `--staged` corpus mechanism (the bug surface)

Every checker has **two** corpus enumerators that diverge:
- **Audit / working-tree path** uses `root.glob(glob)` via `_expand_glob` (`parity_check.py:204`/`gather_scan_files:212`; `prescriptive_prose.py:222/229`; `events-registry:369/376`; `bare_python_import.py:407`/`discover_files`; `contract.py:_gather_corpus_paths:478`). `root.glob` matches depth-1/2/3+ correctly. **This is the ground-truth corpus.**
- **Staged path** uses `_matches_scan_glob` → `Path.match(glob)` (or `full_match`). This is the broken membership test.

**Staged call-chain subtleties (load-bearing for testing):**
- prose & events-registry: under a `--root` override they route to `gather_scan_files` (the **correct** `root.glob` path); only the **real-git `--staged`** path (no `--root`) reaches the buggy `_matches_scan_glob`. **Tests using `--root` do not exercise the bug.** (Confirmed by adversarial agent.)
- parity: no `--root` flag; in `--staged` it always scans all files via `root.glob` AND builds a `staged_overlay` from `_gather_staged_inscope_texts`→`_matches_scan_glob` (buggy). So parity's bug drops only the **staged-blob overlay** for deep files (it scans stale working-tree content instead of the staged edit) — not the file entirely.
- bare-python & contract: always real-git `_staged_paths` → membership (no `--root` bypass).

### Hard-exclusion divergence (verified)

| Checker | Hard-exclusion? | Excludes |
|---|---|---|
| contract | **YES** — `_is_hard_excluded` (L463), `_HARD_EXCLUDE_PREFIXES`/`_EXACT`/`_GLOBS` | `cortex/research/archive/`, `cortex/lifecycle/`, `tests/fixtures/contract/`, `CHANGELOG.md`, `bin/.audit-*-allowlist.md`, `bin/.parity-exceptions.md` |
| bare-python | **YES** — `_is_hard_excluded` (L399), prefix-only | `cortex/lifecycle/archive/`, `cortex/research/archive/`, `tests/fixtures/bare_python_import/`, `tests/fixtures/contract/` |
| parity | **NO** (uses `bin/.parity-exceptions.md` allowlist for W003, a different mechanism) | — |
| prescriptive-prose | **NO** | — |
| events-registry | **NO** | — |

**"Hard-exclusions still apply" means: preserve each checker's *existing* exclusion behavior** — do **not** import contract's exclusion prefixes into the three checkers that never had them. Note bare-python's `_matches_scan_glob` does *not* itself call `_is_hard_excluded` — exclusion is layered separately at the call site.

### Shared helper: none today

There is **no** shared membership helper. Four private `_matches_scan_glob` copies exist (parity L685, prose L243, bare-python L453, events-registry L390) plus contract's inline loop. They have **already drifted into 3 different implementations** (literal-fast-path+`match`; bare `match`; `full_match`), two buggy. `cortex_command/common.py` has no glob helper. `cortex_command/lint/__init__.py` is a docstring-only package.

### Dual-source / mirror obligations

- The four `cortex_command/` Python modules are **wheel-only** — **no plugin mirror** (`plugins/cortex-core/bin/` vendors only the bash wrappers). Editing them needs no paired mirror edit. A new `cortex_command/lint/_globs.py` needs **no mirror**.
- `bin/cortex-check-events-registry` is a **standalone 620-line `#!/usr/bin/env python3` script** (no `cortex_command` import, no `[project.scripts]` entry) and **is** byte-mirrored to `plugins/cortex-core/bin/cortex-check-events-registry`. Editing it requires `just build-plugin` to regenerate the mirror; the `.githooks/pre-commit` hook fails closed on drift. **Do not hand-edit the mirror.** Run `just setup-githooks` before committing.

### Test fixtures & a critical test gap

- Fixtures: `tests/test_check_parity.py` (+ `tests/fixtures/parity/`), `tests/test_check_prescriptive_prose.py`, `tests/test_check_events_registry.py`, `tests/test_bare_python_import_lint.py`, `tests/test_check_contract.py`. Convention: per-checker fixture dirs, prefix-keyed (`valid-`/`invalid-`/`exclude-`); tests invoke `python3 -m cortex_command.<module>` (working-tree, not the binstub).
- **Test gap:** no existing test exercises the buggy `_matches_scan_glob` staged path with deep files — every `--root`-based test routes through the correct `gather_scan_files`. `tests/test_bare_python_import_lint.py:254` (`test_staged_glob_matches_deep_skills_path`) calls `_matches_scan_glob` directly but (a) doesn't cover depth-1-within-`**`, and (b) calls `full_match`, so it would itself **AttributeError on 3.12**. A faithful regression test must build a real git repo, stage depth-1 + depth-3 in-scope files, and run `--staged` **without** `--root`.

### Conventions

- `requires-python = ">=3.12"` (`pyproject.toml:8`). All four checkers are **stdlib-only** (per their docstrings). No `full_match` / `glob.translate` (both 3.13+).
- Editing `bin/cortex-*` / `cortex_command/common.py` / `skills/` requires the lifecycle skill (CLAUDE.md). Commit via `/cortex-core:commit`.

---

## Web Research

### Version-availability table (with CPython doc citations)

| API | Python 3.12 | Python 3.13+ |
|---|---|---|
| `PurePath.full_match(pattern)` | **Does NOT exist → AttributeError** | **Added in 3.13** (gh-73435); recursive `**` |
| `PurePath.match(pattern)` `**` | `**` "acts like non-recursive `*`" (single segment); right-anchored | **Unchanged** — still acts like `*` |
| `fnmatch.fnmatch` / `translate` | **NOT path-aware** — `*`→`.*` (crosses `/`); "filename separator is not special" | Same |
| `glob.translate(pattern, recursive=, include_hidden=, seps=)` | **Does NOT exist** | **Added in 3.13** |

Docs: [pathlib `full_match`](https://docs.python.org/3/library/pathlib.html#pathlib.PurePath.full_match) ("Added in version 3.13"), [pathlib `match` 3.12](https://docs.python.org/3.12/library/pathlib.html#pathlib.PurePath.match), [What's New 3.13](https://docs.python.org/3/whatsnew/3.13.html), [glob.translate](https://docs.python.org/3/library/glob.html#glob.translate), [fnmatch](https://docs.python.org/3/library/fnmatch.html). History of the `Path.match`-treats-`**`-as-`*` gotcha: cpython gh-73435, gh-118701, discuss.python.org/t/9052.

Empirically verified (3.13+ semantics):
- `fnmatch('cortex/backlog/backlog/index.md', 'cortex/backlog/*.md')` → **True** (over-match — `*` crossed `/`)
- `fnmatch('docs/c.md', 'docs/**/*.md')` → **False** (under-match — literal `**/` needs a `/`)
- `PurePath('docs/c.md').match('docs/**/*.md')` → False; `.full_match(...)` → True

### Portable matcher options (stdlib-only preferred)

- **(a) `glob.translate(pat, recursive=True) + re.fullmatch`** — most faithful to `Path.glob`, but **3.13+ only** → fails `>=3.12` without a fallback.
- **(b) `full_match` with a `match` fallback** — two code paths, divergent semantics; not recommended for a deterministic lint gate.
- **(c) manual glob→regex translation (`re`+`fnmatch`, stdlib-only)** — **RECOMMENDED**: `**`→ segment-spanning group, `*`→`[^/]*`, anchored with `re.fullmatch`. Verified equivalent to `glob.translate` with 0 mismatches across a 9-path × 3-pattern matrix. Single code path, identical on 3.12 and 3.13+.
- **(d) `wcmatch`/`pathspec`** — third-party; **rejected** (project is stdlib-only for checkers).

**Key gotchas** (refined by the adversarial agent below): `glob.translate`'s default `include_hidden=False` injects `(?!\.)` guards that exclude dotfiles — but `Path.glob` is actually `include_hidden=True`-equivalent on all supported versions, so faithfully matching `root.glob` requires `include_hidden=True`. Trailing-bare-`**` semantics changed across 3.13 (gh-70303 / gh-73435) — relevant to `hooks/**`.

---

## Requirements & Constraints

- **Two-mode gate pattern** (`project.md:92`, Optional): gates pair `--staged` (diff schema) with `--audit` (repo-wide). The bug is in the `--staged` half; the `--audit`/`root.glob` half is correct. Fix must preserve this shape.
- **`requires-python = ">=3.12"`** (`pyproject.toml:8`) — the binding constraint. Rules out `full_match` and `glob.translate` at runtime.
- **stdlib-only for checkers** — each module docstring asserts it; a shared helper must be stdlib-only.
- **Solution horizon** (CLAUDE.md / `project.md:21`): a patch that "applies in multiple known places you can name" → propose the durable version. Trigger met verbatim: the same membership bug is named-identical across 5 sites (4 + contract.py), and the copies have already drifted. This argues **for** the shared helper.
- **Dual-source mirror**: only `bin/` bash wrappers are mirrored; a new `cortex_command/` module needs no mirror. Editing `bin/cortex-check-events-registry` triggers the drift hook.
- **Where a shared helper lives**: `cortex_command/lint/_globs.py` (or a fn in `lint/__init__.py`) is the natural home — 3 of the 4 importable checkers live under `cortex_command/lint/`. parity_check (top-level) and events-registry (standalone) are the outliers; events-registry **cannot import the package** (see Tradeoffs).
- **Bare-Python prohibition (L201)**: applies to `skills/**/*.md`-style corpus files, not to `cortex_command/**/*.py` — a new `_globs.py` is not scanned by bare-python's own rule (confirmed). No gate trips from adding it.
- **Install-state parity precedent** (`project.md:42`, `tests/test_install_state_path_parity.py`): the established pattern for keeping a vendor-duplicated implementation in sync via a parity test — directly applicable to the events-registry inline copy.

---

## Matcher Mechanism (Truth Table)

Ground truth = `Path(root).glob(pattern)` membership (a relative path is in-scope iff it appears in the `root.glob` expansion). Candidate matchers tested over the real corpus and synthetic edges:

| Matcher | Result vs `root.glob` | Fatal flaw |
|---|---|---|
| **A** `Path.match` (current) | 268 under-matches (parity corpus) | `**` non-recursive + unanchored tail (over-matches `claude/hooks/x.sh` vs `hooks/cortex-*.sh`) |
| **B** `full_match` | exact on 3.13+ | **AttributeError on 3.12**; over-matches dotfiles |
| **C** `fnmatch` (ticket's fix) | over+under | `*` crosses `/` (over-match single-`*`); literal `**/` under-matches depth-1 |
| **D** `fnmatch or fnmatch(.replace('/**/','/'))` | over-matches | over-matches single-`*` deeper paths (`cortex/backlog/sub/x.md`) **and** dotfiles |
| **E/F** inlined `re` translator / `glob.translate` | **exact** (with corrections below) | `glob.translate` is 3.13+ only — must inline |

**Concrete breaking pairs:** C/D over-scan `('cortex/backlog/sub/x.md','cortex/backlog/*.md')`; A/C under-scan `('docs/setup.md','docs/**/*.md')`, `('skills/foo.md','skills/**/*.md')`.

### RECOMMENDED matcher (with adversarial corrections folded in)

An **inlined `re`-only glob→regex translator** — one code path, no version branch, 3.12 + 3.13 identical, stdlib-only. Per-segment: `**`→ segment-spanning group; `*`→`[^/]*`; `?`→`[^/]`; literals `re.escape`d; anchored with `re.fullmatch`. **Do NOT call `glob.translate` at runtime** (3.13+ only — would relocate the same 3.12 crash).

**Two load-bearing corrections to the first-pass design (adversarial-verified on real 3.12/3.13/3.14):**

1. **`include_hidden=True`, NOT `False`.** `Path.glob` matches hidden files and descends hidden directories on *all* supported versions (it is `include_hidden=True`-equivalent). The first-pass `(?!\.)` hidden-skips produced **5 real divergences** (the `.parity-exceptions.md`/`.contract-lint-exceptions.md` fixtures under `tests/**/*.md`). Drop all `(?!\.)` guards. With this correction: **0 divergences across all 13 globs × 3,409 files on 3.13/3.14.**

2. **Trailing bare `**` needs an explicit basename group.** The rule `**`→`(?:[^/.][^/]*/)*` matches only *directories* — so `hooks/**` would match no files (`match('hooks/cortex-cleanup-session.sh','hooks/**')` = False), re-introducing a skip in bare-python and contract. A trailing `**` must emit `(?:[^/]+/)*(?:[^/]+)?`. See `## Open Questions` for the `hooks/**` semantics decision.

**Input normalization:** all four checkers feed git `--name-only` output (posix `/`, no `./`, no trailing slash) into the matcher — no normalization hazard found. The matcher must receive the **raw posix string**, not `str(Path(rel))` (platform-stable).

---

## Per-Checker Corpus Impact

Measured on the live repo (Python 3.14). Ground truth = `root.glob`; "skipped" = ground-truth files the buggy matcher fails to accept.

| checker | #globs | #`**` | matcher | ground-truth files | skipped | skip% | depth histogram (skipped) |
|---|---|---|---|---|---|---|---|
| **parity** | 9 | 5 | `Path.match` | 308 | 268 | **87%** | d1:210, d2:5, d3:45, d4:8 |
| **prescriptive-prose** | 2 | 1 | `Path.match` | 338 | 44 | **13%** | d3:44 |
| **events-registry** | 2 | 1 | `Path.match` | 65 | 44 | **68%** | d3:44 |
| **bare-python** | 7 | 5 | `full_match` | 168 | 0 on 3.13+ / **crash on 3.12** | — | n/a |

**The "~72%" figure was contract-specific and does NOT transfer:** parity is worst (87%), prose is least (13%, all depth-3 `skills/*/references/*.md` — its 277 single-`*` `cortex/backlog/*.md` files are unaffected), events-registry coincidentally near (68%) for small-corpus reasons, bare-python is version-gated (0 or crash, not a graded skip).

**Adversarial nuance on parity's 87%:** parity *always* scans all 308 files via `root.glob` even in `--staged`; the buggy matcher only gates the staged-blob **overlay**. So "268 skipped" = "268 files whose staged-blob overlay is dropped (stale working-tree content scanned instead)," not "268 files never scanned." Real misread occurs only when staged content differs from working-tree.

**prescriptive-prose single-`*` backlog glob confirmed unaffected:** `Path('cortex/backlog/123-foo.md').match('cortex/backlog/*.md')` = True; the one nested file `cortex/backlog/backlog/index.md` is not enumerated by the single-`*` glob anyway, so `root.glob` and `Path.match` agree. (Note: matcher variant D would *wrongly* include it — another reason to use the full translator.)

---

## Surfaced Latent Findings (Blast Radius)

**Conclusion: the fix lands GREEN on the current repo** — all four corrected matchers produce **zero** new violations on the present tree. No clearing / hard-exclusion / deferral work is required to merge. Independently re-verified for events-registry (134 registry rows, 0 schema errors; 33 event emissions across 15 names in newly-scanned `skills/*/references/*.md` — all 15 registered) and prescriptive-prose (0 violations on the deep skills files). The ticket's anticipated "follow-up to clear real findings" does **not** materialize here.

**Methodology caveat (adversarial).** The blast-radius probe used `--staged --root .` as a stand-in for missing audit modes — but `--root` routes through the **correct** `root.glob` path, **not** the buggy `_matches_scan_glob`, so it does not exercise the bug for prose/events-registry/parity. The lands-green conclusion holds for the **static current tree** (verified by directly scanning the deep files), but it is **not proven for arbitrary commits**: a future commit that stages content differing from working-tree (e.g. parity's overlay, or staging the removal of the last `cortex-foo` wiring reference from a deep file) could legitimately fire a finding under the corrected matcher — which is the intended behavior, not a regression. Faithful tests must stage deep files in a real temp git repo, not use `--root`.

---

## Tradeoffs & Alternatives (Shared Helper vs In-Place)

**Approach A — shared helper** (`cortex_command/lint/_globs.py`, `matches_any_glob(rel, globs)`): one correct 3.12-safe implementation imported by the 3 importable checkers; eliminates the proven 3-way drift; needs no mirror; satisfies Solution-horizon. **Con:** doesn't reach the standalone events-registry script.

**Approach B — four in-place edits:** no new module/wiring; each edit local. **Con:** re-establishes the exact duplicate-and-drift that *caused* this bug (4 copies, soon 5); a future correctness fix must land in 4–5 places.

**The events-registry asymmetry (the hard constraint):** `bin/cortex-check-events-registry` is a standalone script with no `cortex_command` import and no `sys.path` injection — it genuinely **cannot** import a shared helper without an out-of-scope refactor. The other three run as `python3 -m cortex_command...` (inside the package), so importing a sibling `cortex_command.lint._globs` is safe (confirmed — no import-path or self-lint hazard).

**RECOMMENDED — hybrid:** shared `cortex_command/lint/_globs.py` imported by `parity_check`, `prescriptive_prose`, `bare_python_import`; **inline-vendored** copy in `bin/cortex-check-events-registry` guarded by a new `tests/test_*_parity.py` (the install-state precedent: ~25 `*_parity.py` tests already exist, including for these checkers). This maps exactly onto the importable/standalone boundary — it is the architecturally-correct shape, not a compromise. Solution-horizon argues decisively for consolidation given 5 named sites already drifted. (This adds a new module + 2 tests — flag for the §4 complexity/value gate in Spec.)

---

## Adversarial Review

The adversarial agent re-ran everything on **real Python 3.12, 3.13, and 3.14** over all 3,409 tracked files and broke several first-pass claims. Net-corrected findings are already folded into the sections above; the load-bearing breaks:

- **Bare `hooks/**` under-scans** with the naive `**` rule (matches dirs only) — corrected by the trailing-basename group. `root.glob('hooks/**')` is itself **version-split**: 0 files on 3.12, 5 on 3.13+. So "congruent with `root.glob`" is **ill-defined** for bare `hooks/**`, and bare-python's *full-corpus* path also under-scans `hooks/` on 3.12.
- **`include_hidden=False` was the wrong oracle flag** — `Path.glob` is `include_hidden=True`-equivalent; corrected to 0 divergences.
- **`glob.translate` doesn't exist on 3.12** — inlining is mandatory; calling it at runtime relocates the crash.
- **`--root` is not a faithful `--staged` substitute** — the lands-green evidence tested the wrong code path for 3 of 4 checkers (conclusion still holds for the static tree).
- **CI hazard:** `.github/workflows/validate.yml` + `auto-release.yml` pin Python 3.12, but **validate.yml does not run the test suite or the pre-commit checkers** — so neither the current bare-python `full_match` crash nor a future `glob.translate` crash is caught by CI today. (This is the subject of related ticket #283.)
- **#279's `fnmatch` is wrong, not merely different** — independently proven to **under-match depth-1 by 18 files** (e.g. `docs/agentic-layer.md` vs `docs/**/*.md`). Shipping #279 with `fnmatch` and #282 with the translator would leave contract.py with a depth-1 silent skip *and* two different "correct" matchers in the tree.

---

## Open Questions

- **[Resolved] Matcher mechanism = inlined `re`-only translator with `include_hidden=True` (no dotfile-skip) and a trailing-bare-`**` basename group.** The ticket's `fnmatch` (and variant D) are disconfirmed; `glob.translate`/`full_match` are 3.13+ only and must not be called at runtime. Adversarial-verified at 0 divergences vs `root.glob` across 3,409 files on 3.13/3.14 once the two corrections are applied. Spec should specify this matcher precisely (including a named `hooks/cortex-cleanup-session.sh` vs `hooks/**` test case).
- **[Resolved] Tests must use a real `--staged` git-diff harness, not `--root`.** `--root` routes through the already-correct `root.glob` path and would not catch the regression. Each checker needs a fixture that stages depth-1 and depth-≥3 in-scope files in a temp git repo (or calls `_matches_scan_glob` directly), and the 3.12 path must be exercised (the existing `full_match`-based test AttributeErrors on 3.12).
- **[Defer to Spec] `hooks/**` semantics + full-corpus scope.** `root.glob('hooks/**')` is version-split (0 vs 5 files). Decide: (a) rewrite `hooks/**`→`hooks/**/*` in bare-python's/contract's glob lists (version-stable, simplest) vs special-case the matcher's trailing-`**`; and (b) whether #282 also fixes the **full-corpus** `_expand_glob` under-scan of `hooks/` on 3.12 (bare-python/contract), or scopes itself to `--staged` membership only. *Rationale for deferral: this is a scope-boundary decision (does the ticket expand to the audit path?) best made with the user at the Spec approval gate; the version-split makes "congruent with root.glob" the wrong target — Spec should target intended semantics.*
- **[Defer to Spec] Coordination with #279 (in Plan).** #279's R8 prescribes the disconfirmed `fnmatch`. Options: (a) **#282 owns the shared `_globs` helper and #279's contract.py:1378 adopts it** (5 sites consolidated, one correct matcher) — Solution-horizon-preferred; (b) sequence #282 after #279 and re-fix contract.py; (c) keep contract.py entirely out of #282. *Rationale for deferral: cross-ticket sequencing is a planning decision the user/orchestrator must make; it also affects whether #279's spec needs amending.*
- **[Defer to Spec / §4 gate] Structure: hybrid shared helper vs four in-place edits.** Recommended hybrid (shared `cortex_command/lint/_globs.py` for 3 importable checkers + inline-vendored-with-parity-test for events-registry) adds a new module + 2 tests — a new maintained surface. *Rationale for deferral: this is the proportionality decision the Spec §4 complexity/value gate exists to surface to the user.*
