# Research: cortex init scaffolds a versioned nested `cortex/.gitignore` for umbrella transient artifacts

**Lifecycle:** cortex-init-scaffolds-cortex-gitignore-for · **Tier:** complex · **Criticality:** high
**Backlog:** `cortex/backlog/289-cortex-init-scaffolds-cortex-gitignore-for-umbrella-transient-artifacts.md`

**Clarified intent:** Ship a tracked, versioned nested `cortex/.gitignore` template that `cortex init`'s per-repo scaffolder writes/refreshes into every consumer repo, replacing today's binary "commit-the-whole-umbrella or ignore-the-whole-umbrella" `# cortex/` toggle with selective ignoring of umbrella transient artifacts.

Research dispatched 8 agents (complex×high): Codebase, Web, Requirements, Tradeoffs, Template-Content, State-&-Migration, Test-Surface, Adversarial. Findings below; the central design decision and all spec-blocking choices are collected under **## Open Questions**.

---

## Codebase Analysis

**Files that will change:**

| File | Change |
|---|---|
| `cortex_command/init/templates/cortex/.gitignore` | **NEW** — the shipped template bytes. Templates root is `_TEMPLATE_ROOT` (scaffold.py:63). There is NO `.gitignore` template today — this is the gap the ticket fills. |
| `cortex_command/init/scaffold.py` | The writer + (if versioned) a `_CORTEX_GITIGNORE_VERSION` constant + sigil parse; add `"cortex/.gitignore"` to `_HASH_INPUT_TEMPLATES` (line 82). |
| `cortex_command/init/handler.py` | Wire the writer into both `_run` (scaffold step, after `ensure_claude_md_authorization` ~handler.py:523) AND `_run_ensure` (alongside the repo-scope writes at handler.py:246-247). Both call sites needed. |
| `cortex/.gitignore` (repo root umbrella) | The canonical seeded content (commit `6662815a`); becomes the template source. **Has known bugs — see Template Content & Open Questions.** |
| `.gitignore` (repo root) | De-dup the cortex-scoped transient rules the nested file now owns. |
| `skills/lifecycle/references/complete.md` (line ~254) + `post-refine-commit.md` (line ~23) | Trim the stale "un-gitignored residue" wording. **These ARE plugin-mirrored.** |
| `cortex_command/init/tests/test_scaffold.py`, `test_handler_ensure.py`, `tests/test_init_artifacts_hash_inputs.py` | New idempotency / no-clobber / versioned-refresh / consumer-with-existing-file / hash-coverage tests. |

**Closest prior-art pattern — `ensure_claude_md_authorization` (scaffold.py:678-757), NOT a plain template copy.** It is a version-stamped writer: `_CLAUDE_MD_AUTH_VERSION = 1` (scaffold.py:106); replace-on-`fence-version < canonical`, no-op on equal, refuse-downgrade on greater (scaffold.py:730-740); located by a fence regex. Crucially, `claude_md_authorization.md` is **excluded from `_iter_template_files`** (scaffold.py:296-302) because it is spliced, not copied verbatim. **If `cortex/.gitignore` is implemented as a dedicated versioned writer, its template must likewise be excluded from `_iter_template_files`** or `scaffold()` would double-manage it (copy-if-absent AND drift-target). This is the single most important integration subtlety.

**The three factual corrections in the ticket body — ALL CONFIRMED:**
1. **No plugin mirror for the init package.** `plugins/cortex-core/` contains only `bin/`, `hooks/`, `skills/` — no `cortex_command/` tree. `build-plugin` (justfile:597,601,604) rsyncs only `skills/$s/`, `hooks/`, `bin/cortex-*`. The init package ships **only in the CLI wheel** (ADR-0002). The ticket's "mirror the change into the cortex-core plugin per dual-source enforcement" is **wrong for the scaffolder code** — the dual-source obligation applies **only** to the `skills/lifecycle/references/{complete,post-refine-commit}.md` wording edits (those ARE mirrored, verified byte-identical).
2. **Hash extension targets `_HASH_INPUT_TEMPLATES` (scaffold.py:82), not `repr(_GITIGNORE_TARGETS)` (scaffold.py:148).** `_GITIGNORE_TARGETS` is the ROOT-`.gitignore` append list (`.cortex-init`, `.cortex-init-backup/`, `.claude/worktrees/`) — a separate input. The exact change: add `"cortex/.gitignore"` to the tuple. The `"v1:"` prefix (scaffold.py:151) is a hash-*format* version, not a content version — no bump needed for content (template bytes are re-read each run). If a dedicated `_CORTEX_GITIGNORE_VERSION` constant is used, fold `str(_CORTEX_GITIGNORE_VERSION)` into the hash alongside `_CLAUDE_MD_AUTH_VERSION` (scaffold.py:149).
3. **Relocation migration is dead/moot.** `_relocation_migration.py::migrate_residue_json` rglobs `repo_root/"lifecycle"` (line 161) — the pre-#202 bare path, NOT `cortex/lifecycle/`. It has **zero production callers** (only its own test + `__main__`); not wired into init. Its staleness is a pre-existing latent bug (deletion deferred per "spec DR-7"), independent of and untouched by this work.

**Conventions:** atomic writes via `atomic_write` (scaffold.py:61); template resolution via `importlib.resources` not hardcoded paths; What/Why-not-How for the prose trims (no new MUST language).

---

## Web Research

Three prior-art families for "ship and keep-updated a managed file in someone else's repo without clobbering their edits":

**1. Managed-block / sigil-fence** (Ansible `blockinfile` BEGIN/END markers; NVIDIA AI Workbench's tool-managed `.gitignore` *section* — the closest direct analog; pre-commit `autoupdate`'s managed `rev:` field). Mechanism: replace the fenced interior wholesale each run, preserve lines outside. **Dominant failure mode: missing trailing newline → the tool fails to recognize its own block and appends a DUPLICATE** (ansible#45848, #72055). Second failure: user deletes a marker → tool re-inserts a fresh block. Version string goes *inside* the block body, not in the fence.

**2. Versioned whole-file with 3-way merge** (copier, cruft). Copier persists `.copier-answers.yml` with `_commit` (the exact version that produced current state), regenerates pristine-at-old + pristine-at-new, diffs, re-applies user edits, falls back to conflict markers / `.rej`. **Sharpest lesson: "Never hand-edit the version stamp" — if the stamp claims version N but disk isn't what N writes, the merge silently misbehaves.** Requires clean git tree + tagged template. Heavyweight.

**3. Copy-if-absent** (`eslint --init`, github/gitignore templates, editorconfig). Lay down once, never touch. Zero clobber risk, dead simple — **gives up upstream propagation entirely; the file goes stale and the maintainer must say "add X yourself."**

**Nested-`.gitignore` mechanics (directly load-bearing):** patterns are relative to the file's own directory (so a `cortex/.gitignore` should write `lifecycle/...` not `cortex/lifecycle/...`); deeper `.gitignore` overrides shallower; **but you CANNOT re-include (`!path`) anything whose parent directory is already ignored** — git stops scanning inside an ignored dir. So `!` negations in `cortex/.gitignore` are inert once a consumer toggles `# cortex/` on. Ignore *contents* (`dir/*`) not the *directory* (`dir/`) if re-inclusion is ever needed.

**Synthesis:** for a file the consumer rarely edits and that cortex owns, the managed-block fence is heavier than needed unless consumers co-author; copy-if-absent is simplest but cannot refresh; the version-stamped-header approach gives copier's safety without copier's machinery.

---

## Requirements & Constraints

**The ticket binds the design explicitly** (Integration clause): *"Add an idempotent, versioned write of `cortex/.gitignore` to the scaffold step, mirroring the CLAUDE.md-fence pattern (version-stamped, replace-on-version-bump, do not clobber a consumer's hand-edits). Source the bytes from a template under the init package rather than hardcoding."*

**ADR-0006 (accepted)** establishes the versioned-no-clobber discipline to mirror: replacement gated on `fence-version < canonical-version` ("latest writer wins, no in-fence user edits respected"); stale predicate is version-comparison, NOT byte-equality; users customize *outside* the managed region. It "mirrors `ensure_gitignore()`'s additive-idempotent shape."

**Init-state hash contract** (project.md + scaffold.py:120-151): `_compute_init_artifacts_hash` produces `"v1:<sha256>"` over `_HASH_INPUT_TEMPLATES` + serialized literals. In-code comment binds: *"Update this tuple when a template is added or removed."* Purpose: let `cortex init --ensure` detect drift across CLI releases. `CORTEX_AUTO_ENSURE=0` suppresses `--ensure`.

**Dual-source scope — init package is OUTSIDE it.** The `.githooks/pre-commit` drift hook regenerates plugin mirrors from `skills/`, `bin/cortex-*`, `hooks/cortex-*` only. The init package is wheel-only (ADR-0002). Only the two skills/*.md wording trims incur a mirror obligation (run `just build-plugin`, commit canonical+mirror together).

**Scope: IN SCOPE.** `cortex init` per-repo scaffolding is established in-scope infrastructure (ADR-0003 per-repo sandbox registration, ADR-0006 consumer CLAUDE.md). The Out-of-Scope "setup automation for new machines — belong in machine-config" line is NOT triggered: this is per-repo init writing inside the repo's own `cortex/` tree (the in-scope side of ADR-0003's own-tree boundary), not machine-level setup.

**Authoring constraints:** prescribe What/Why not How; no new MUST without an evidence artifact + recorded effort=high attempt; durable version-stamped writer is the right altitude (Solution Horizon); prefer structural enforcement (the stale-predicate in control flow) over prose.

**Destructive-operations quality attribute** ("preserve uncommitted state") anchors the no-clobber requirement: a consumer's hand-edited `cortex/.gitignore` is user-visible state the writer must not overwrite.

---

## Tradeoffs & Alternatives

Three candidate mechanisms (the Tradeoffs agent recommended C; the State and Adversarial agents found C structurally broken — see contradiction in Open Questions):

**A. Sigil/fence-delimited managed block inside `cortex/.gitignore`** — `# >>> cortex-managed (version=N) >>>` … block, replace-on-bump, preserve consumer lines outside. `#`-prefixed markers mandatory (every gitignore line is a live pattern). ~80-120 new LOC cloning the auth-fence machinery with a *new* `#`-comment regex (the `<!-- -->` regex can't be reused). Protects consumer lines outside the fence; silently overwrites edits inside on bump. **Imports the fence pattern's justification (protect a file cortex doesn't own) which barely applies to a file inside cortex's own `cortex/` tree.**

**B. Versioned whole-file writer** — `# cortex-template version: N` header; replace whole file on bump, skip-and-warn if on-disk diverges from previously-shipped version. **Hidden cost: needs a record of last-shipped bytes** — the `.cortex-init` marker stores one aggregate hash, not per-file hashes, so B forces either a marker-schema change or a new sidecar (a state surface #202/#273 have been consolidating away). "Refuse on any consumer edit" freezes all future cortex rules until manual reconcile.

**C. Additive copy-if-absent** — drop under `templates/cortex/`, let `scaffold()` lay it down once. Near-zero new code; reuses the dominant template path; perfect no-clobber. **BUT gives up refresh entirely** — and the State agent proved `--ensure`'s `scaffold(overwrite=False)` NEVER updates an existing file while advancing the stored hash, creating permanent silent desync (see Open Questions).

**Tradeoffs agent's recommendation: C**, invoking "simpler wins," arguing refresh-on-bump is low-value for a slowly-changing file and the fence imports the wrong justification. **The Adversarial agent overturned this:** C cannot satisfy the ticket's binding "replace-on-version-bump," and the refresh need is *real* (the seeded file already has a glob bug → v2 is inevitable → a v2 that can't reach existing consumers is useless). **A fourth option emerged** — whole-file managed keyed off the aggregate hash, refreshed through the post-dispatch `ensure_*` slot (which always runs in the terminal `--update`/`--force` path) rather than `scaffold(overwrite=False)`, with "on-disk == any previously-shipped version's bytes → overwrite; else hand-edited → preserve + report." Avoids inventing a gitignore `#`-sigil; cost is shipping a small set of historical-version hashes.

---

## Template Content & Scope

**Confirmed transient artifacts (writer → reader off-disk, never via git → ship-safe to ignore):** `critical-review-residue.json` (critical_review/write_residue_cli.py → overnight/report.py glob); `.session`/`.session-owner`/`.lock` (hooks/_session_state.py → scan_lifecycle.py); `agent-activity.jsonl` (overnight/feature_executor.py → dashboard/data.py); `metrics.json` (pipeline/metrics.py → dashboard); `learnings/recovery-log.md` (pipeline/merge_recovery.py); `backlog/*.events.jsonl` (backlog/update_item.py); `_adhoc/` (pruned by clean.py); `lifecycle/sessions/`.

**Content bugs / decisions in the seeded file (must fix before wiring — once shipped, changing the body requires a version bump):**
- **`lifecycle/*/.dispatching` — NO writer exists** in the codebase (every match is the English word). The root `.gitignore` carries it as forward-coverage. → Keep for root/nested parity (harmless) OR drop as dead; minor.
- **`overnight-events-*.log` MISSES the canonical `overnight-events.log`** (no hyphen suffix). The Adversarial agent corrected the Content agent: it's a **real file (4130 bytes), not a symlink, and currently git-TRACKED** (committed incidentally in 9323efea). It's read off-disk by the dashboard/reporter. → Widen to `overnight-events*.log` AND decide whether the tracked copy should be `git rm --cached`'d.
- **`backlog/index.json` + `index.md`** are derived build artifacts (regenerated by `cortex-generate-backlog-index`; this repo untracked them in `9875226c`). → Recommended to ship the ignore (derived, matches this repo's resolved position), but flagged as a ship-to-arbitrary-consumers decision since `index.md` is human-readable.

**Must-track directories the template must NEVER ignore (verified tracked):** `backlog/*.md` tickets, `lifecycle/*/research.md|spec.md|plan.md`, `requirements/`, `adr/`, `retros/`, `research/`, `README.md`, `lifecycle.config.md`. **Critical narrowness constraint:** `learnings/` is a MIXED dir — `recovery-log.md` is transient (ignore) but `outline.md`, `retros-mining.md`, `verification.md` are TRACKED work-products. The rule must stay the narrow `learnings/recovery-log.md`; a whole-`learnings/` ignore would drop real lifecycle output.

**Path-relativity:** the seeded rules are correctly relative to `cortex/` (no `cortex/`-prefixed leakage). **`# cortex/` toggle:** when uncommented, git ignores the whole umbrella incl. the nested file itself (inert, not conflicting) — behaviorally moot as the ticket claims, but the two are mutually-exclusive modes, not composable layers.

---

## State & Migration Interactions

**Exact hash extension:** add `"cortex/.gitignore"` to `_HASH_INPUT_TEMPLATES` (scaffold.py:82). No `"v1:"` prefix bump for content. If a dedicated version constant is used, also fold `str(_CORTEX_GITIGNORE_VERSION)` into `_compute_init_artifacts_hash` (scaffold.py:149) so a version bump with unchanged body still moves the hash.

**`--ensure` flow (handler.py:129-249, five-case dispatch):** prior hash stored in `cortex/.cortex-init` JSON field `init_artifacts_hash`. Case (i) `marker_hash == installed_hash` → no-op return 0 (handler.py:178). Case (ii) mismatch → `scaffold(overwrite=False)` + `write_marker(refresh=True)` + drift report (handler.py:183-187). `CORTEX_AUTO_ENSURE=0` short-circuits first.

**The copy-if-absent desync trap (HIGH severity):** `atomic_write` does unconditional `os.replace` — no content-compare; idempotency must come from a caller guard. `scaffold()` guards via existence-skip (scaffold.py:360) → so on `--ensure` case (ii), an EXISTING `cortex/.gitignore` is skipped while `write_marker(refresh=True)` advances the stored hash to vN. **Result: hash claims vN, disk has vN-1, case (i) no-ops forever — permanent silent desync.** `drift_files` detects it but only emits stderr (invisible in the in-session `--ensure` path). This disqualifies a plain template. A dedicated post-dispatch `ensure_cortex_gitignore` (called unconditionally like `ensure_claude_md_authorization` at handler.py:247/523) avoids the desync because its rewrite decision is independent of `scaffold(overwrite=False)`.

**Consumer-with-existing-file:** the version-stamped writer distinguishes in-file `version < N` (older cortex → rewrite) / `== N` (no-op) / **sigil absent** (consumer hand-authored → preserve, do not clobber). The seeded canonical file has **no version sigil today** — to ship it versioned, a version comment must be prepended.

**Root de-dup safe ordering:** the only hazard is un-ignore — never remove a root rule before the nested file covering it exists. No double-ignore hazard (idempotent). `.claude/worktrees/` and the `.cortex-init*` markers must STAY at root (outside `cortex/` scope). **Gate interactions LOW:** `cortex-check-parity` and `cortex-check-path-hardcoding` don't scan `.gitignore` or the init package. (Adversarial note: `overnight/runner.py:730` hard-codes a stale `".gitignore:41"` line reference in a docstring that de-dup will invalidate — fix the comment.)

---

## Test & Verification Surface

**Two test homes:** `cortex_command/init/tests/` (run by `just test-init`) and `tests/test_init_artifacts_hash_inputs.py` (top-level pytest). Conventions: `_git_init` real tmp repo, `_isolate_home` sandboxes `~/.claude`, `_make_args`→`init_main`, assert on int return code; gitignore idempotence via `lines.count(pattern) == 1`; no-clobber via sentinel survival; no-churn via `st_mtime` stability; drift via monkeypatched `_compute_init_artifacts_hash` + `capsys` stderr.

**Built-in enforcement:** `test_hash_input_templates_covers_all_template_files` (tests/test_init_artifacts_hash_inputs.py:140) walks `templates/cortex/**` and diffs against `_HASH_INPUT_TEMPLATES` — **auto-fails the moment you add the template but forget the tuple entry.** (`os.walk`/`iterdir` DO return dotfiles — confirmed.)

**Required test cases:** fresh-write; idempotent re-run (mtime stable); versioned refresh (mismatch hash → rewrite, mechanism-dependent); consumer-with-existing-file no-clobber (assertion depends on chosen mechanism — copy-if-absent: sentinel survives + `--force` backs up; versioned: stale→rewrite/current→no-op/no-sigil→preserve; fence: lines outside survive); hash participation (coverage contract); `# cortex/` toggle singularity (no existing test asserts the toggle line).

**Gates that fire:** the **dual-source drift hook FIRES** for the two `skills/lifecycle/references/*.md` edits — must run `just build-plugin` and stage the regenerated `plugins/cortex-core/skills/lifecycle/...` mirror in the same commit (`lifecycle` is in the cortex-core SKILLS list). `cortex-check-parity`, `test_install_state_path_parity.py`, `test_lifecycle_references_resolve.py` are unaffected by the substance (but the mirror copy must be byte-clean). The init/template/hash edits trigger NO mirror gate.

**Wording-trim verification:** no test asserts the specific prose; correctness is semantic (confirm every artifact named as "un-gitignored" is actually covered by the template); mirror regen is enforced by the drift hook only.

---

## Adversarial Review

**Dotfile packaging — DEFINITIVELY NOT A BLOCKER.** The Adversarial agent built the actual wheel (`uv build --wheel`) AND sdist with a real `templates/cortex/.gitignore`, installed and walked it: all three layers include it. This repo uses **hatchling** (pyproject.toml), which includes everything under the package tree by default — the setuptools/`MANIFEST.in` dotfile-drop worry does not apply. `importlib.resources.files(...).iterdir()` surfaces the dotfile and does NOT skip it. The feature will not ship broken on this axis.

**NEW HIGH-SEVERITY CONTENT BUG (missed by all other agents):** the seeded `lifecycle/*/critical-review-residue.json` is a **single-level glob** that does NOT match archived residue at `cortex/lifecycle/archive/<slug>/critical-review-residue.json` (the `*` consumes `archive/`, leaving `<slug>/file` unmatched — verified with `git check-ignore`). This repo's **43 archived residue files + 3 archived `.session` files are exactly the population the seeded pattern fails to cover.** The seeded file is buggy as-is. Fix: widen residue (and `.session`/`.lock`/`agent-activity.jsonl`) to `lifecycle/**/...` or add `lifecycle/archive/*/...` companions. **This is the single most important content correction** and forces the "v2 is inevitable" argument that makes refreshability load-bearing.

**Mechanism position:** C is genuinely broken (proven desync), not merely conservative — the Tradeoffs agent's "C wins" is indefensible. The versioned writer is required; refresh is load-bearing precisely because the seeded file is already wrong. The fourth option (whole-file managed via aggregate hash + post-dispatch slot + historical-bytes recognition) may be cleaner than inventing a gitignore `#`-comment sigil.

**Assumptions challenged:** (1) "cortex owns cortex/, so no-clobber barely matters" is partially false — the ticket's own Edge anticipates consumers authoring `cortex/.gitignore` (e.g., ignoring project-specific scratch under `cortex/`); copy-if-absent strands them on stale rules, whole-file clobber destroys their additions, so the writer DOES need unmodified-vs-hand-edited discrimination. (2) `overnight-events.log` is a tracked real file, not a symlink. (3) `.dispatching`: keep for root/nested parity. (4) `# cortex/` modes are mutually-exclusive, not composable.

**Pre-existing self-heal gap (inherited, not new):** `--ensure` case (i) returns at handler.py:178 BEFORE the post-dispatch `ensure_*` slot (handler.py:246-247), so a hand-deleted `cortex/.gitignore` whose marker hash still matches won't be self-healed by `--ensure` — same as the existing CLAUDE.md fence (only terminal `cortex init --update` self-heals). Spec should explicitly accept this parity or fix both.

**Prose-trim precision:** `complete.md:254` names "`critical-review-residue.json` and `learnings/*`" — only the residue half becomes stale (and only at active-feature depth, only if the glob is widened); `learnings/*` is NOT stale (the narrow rule leaves `learnings/outline.md` etc. swept by a dir-add). Trim only the residue half; keep the `learnings/*` rationale.

---

## Open Questions

The factual corrections (no plugin mirror; hash via `_HASH_INPUT_TEMPLATES`; relocation migration moot) are **RESOLVED** by research — they are confirmed, not open. The items below are genuine design/content decisions for the **Spec phase**; each is explicitly deferred with rationale so the Spec interview resolves it with the user.

1. **[CENTRAL — mechanism] Which writer mechanism?** Copy-if-absent (C) is **disqualified** — research proved it cannot refresh and creates permanent hash/disk desync. The real choice is between **(A/B) a dedicated `ensure_cortex_gitignore` versioned writer with an in-file `#`-comment sigil** (CLAUDE.md-fence analog, ~80-120 LOC, new sigil convention) versus **the fourth option — whole-file managed keyed off the aggregate `init_artifacts_hash`, refreshed via the post-dispatch `ensure_*` slot, recognizing "on-disk == a previously-shipped version's bytes → overwrite; else hand-edited → preserve+report"** (no new sigil; ships a small set of historical hashes). Both refresh correctly and both must run in the post-dispatch slot (NOT via `scaffold(overwrite=False)`) to avoid desync. *Deferred: resolved in Spec — this is the load-bearing design decision and likely warrants surfacing to the user given the complexity/value tradeoff.* **Contradiction logged:** Tradeoffs agent recommended C; State + Adversarial agents disproved it.

2. **[HIGH — content] Glob depth for residue/session/activity rules.** The seeded `lifecycle/*/...` single-level globs miss archived artifacts at `lifecycle/archive/<slug>/...` (43 archived residue + 3 archived `.session` already leak). Widen to `lifecycle/**/...` or add `lifecycle/archive/*/...` companions? *Deferred: resolved in Spec — the template body must be content-final before wiring (changing it later forces a version bump).*

3. **[content] `overnight-events*.log` glob + tracked-copy disposition.** Widen `overnight-events-*.log` → `overnight-events*.log` to catch the canonical `overnight-events.log`. Separately: that file is currently git-tracked in this repo (read off-disk, never via git) — decide whether to `git rm --cached` it. *Deferred: resolved in Spec; the `git rm --cached` decision parallels the ticket's deferred 78-file decision.*

4. **[content] Ship `backlog/index.json` + `index.md` ignore to arbitrary consumers?** Derived build artifacts (this repo untracked them); but `index.md` is human-readable and some consumers may want it tracked. *Deferred: resolved in Spec.*

5. **[content] `lifecycle/*/.dispatching` — keep for root/nested parity or drop as dead?** No writer exists; root `.gitignore` carries it as forward-coverage. *Deferred: resolved in Spec (low-stakes; lean keep-for-parity).*

6. **[design] Desync / self-heal acceptance.** Confirm the writer runs in a slot that never strands the stored hash ahead of disk. Decide whether to accept the existing `--ensure` case-(i) early-return self-heal gap (parity with the CLAUDE.md fence) or fix both. *Deferred: resolved in Spec.*

7. **[scope-confirm] Prose-trim precision.** Trim only the residue half of `complete.md:254`; KEEP `learnings/*` (still valid — narrow rule). Review `post-refine-commit.md:23` similarly (`.session`/`.lock`/`critical-review-residue.json` become ignored). Fix the stale `overnight/runner.py:730` `.gitignore:41` docstring reference invalidated by root de-dup. *Deferred: resolved in Spec/Plan as mechanical edits.*

8. **[out of scope — confirmed]** Untracking the 78 already-tracked residue files (`git rm --cached`) is explicitly deferred by the ticket and is NOT part of this work. *Resolved: out of scope.*

9. **[design — no-clobber]** Consumers CAN append to `cortex/.gitignore` (ticket Edge confirms). The chosen writer must preserve consumer additions while refreshing cortex-owned rules. The fence (A) preserves lines outside the block; the fourth option preserves a wholly-hand-edited file but cannot merge a partially-edited one (overwrite-if-recognized-else-preserve). *Deferred: resolved in Spec alongside #1 — the mechanism choice determines the no-clobber semantics.*
