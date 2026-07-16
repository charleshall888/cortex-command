# Specification: lifecycleconfig-template-ships-dormant-skip-specify

## Problem Statement

Cortex's `lifecycle.config.md` template ships two dormant keys live (`skip-specify: false`, `skip-review: false`) while commenting out two others (`default-tier`, `default-criticality`), so every repo scaffolded from it prints "documented but not honored" warnings on essentially every lifecycle/backlog CLI call. The asymmetry has a mundane recorded cause: `447a18ce` (2026-05-18, "Refresh documentation to match current code and CLI surface") commented out the two **enum-valued** keys as part of an enum-hint reformat — `skip-specify`/`skip-review` are booleans, so the sweep skipped them. Nothing drifted past a gate: the keys have been live since the initial commit `428e54ea` (2026-04-01), and `_DORMANT_KEYS` plus its warning arrived three months later in `8d965eb2` (#372), which knowingly recorded these exact lines in its Touch points and fenced them out ("Config work is audit-and-warn only"). This ticket collects that deferral. The cost of leaving it is trained inattention — the same emitter produces genuine `unknown key` / `malformed YAML` warnings, and constant self-inflicted noise teaches operators to ignore all of it. Fix the template, correct the docs that claim these keys work, pin the invariant, and quiet the four already-seeded configs on this machine.

## Phases

- **Phase 1: Template consistency** — comment the dormant keys out of both parity-gated copies with claim-free hints, and pin the invariant with a test.
- **Phase 2: Documentation truth-up** — correct every false claim about the four keys in prose docs.
- **Phase 3: Seeded-config sweep** — quiet the four already-seeded configs under `~/Workspaces`.

## Requirements

1. **Both shipped templates comment out `skip-specify` and `skip-review`** with **claim-free** hints matching `# default-criticality:`'s existing style (key, no value, enum hint only). The `default-tier` hint's `(override auto-assessment)` claim is false and is dropped in the same edit — not as separate scope, but because leaving it would re-create the internal inconsistency this ticket exists to remove. No hint asserts dormancy: that status lives in `_DORMANT_KEYS`, the warning, and the docs, so no new hand-maintained copy of the schema is created (#372's boundary). Target state, applied byte-identically to both copies:
   ```
   # default-tier:           # simple | complex
   # default-criticality:    # low | medium | high | critical
   # skip-specify:           # true | false
   # skip-review:            # true | false
   ```
   Acceptance — must print `[]` for both paths (baseline today prints `['skip-review', 'skip-specify']` for each; `.venv/bin/python3` because `yaml` is absent from system python):
   ```bash
   .venv/bin/python3 -c "
   import yaml, pathlib
   from cortex_command.lifecycle_config import _DORMANT_KEYS, _extract_frontmatter_text
   for p in ['cortex_command/init/templates/cortex/lifecycle.config.md','skills/lifecycle/assets/lifecycle.config.md']:
       print(p, sorted(set(yaml.safe_load(_extract_frontmatter_text(pathlib.Path(p).read_text())) or {}) & _DORMANT_KEYS))
   "
   ```
   Plus: `grep -c 'override auto-assessment' cortex_command/init/templates/cortex/lifecycle.config.md` = 0. **Phase**: Template consistency

2. **No hint text contains `---`.** `tests/test_lifecycle_config_parity.py:56` splits on `raw.split(b"---", 2)` — a naive byte split, not a delimiter-*line* match. A `---` in a comment truncates the compared region (proven: 1752 → 560 bytes) and fails with `missing required option line(s): ['# backend: jira', …]`, naming the `backlog:` block instead of the real cause. Use the repo's em-dash. Acceptance: `grep -c -- '---' cortex_command/init/templates/cortex/lifecycle.config.md` = 2 (the frontmatter delimiters only; baseline 2). **Phase**: Template consistency

3. **The two copies stay byte-identical in their frontmatter region** (ADR-0017). Acceptance: `.venv/bin/pytest tests/test_lifecycle_config_parity.py -q` passes 4/4. **Phase**: Template consistency

4. **The plugin mirror is regenerated, never hand-edited.** Acceptance: `just build-plugin` run and output staged; `git diff --quiet -- plugins/cortex-core/` clean at commit time (pre-commit Phase 2–4 enforces). **Phase**: Template consistency

5. **A regression pin asserts the invariant POSITIVELY**, at `tests/test_lifecycle_config_dormant_template.py`, covering all three paths (init template, asset, plugin mirror). It must assert, per path: (a) the frontmatter region is **non-empty**; (b) no `_DORMANT_KEYS` member is a live key; **and (c) every `_DORMANT_KEYS` member is present as a commented line in the region.** Clause (c) is load-bearing and (a) is not optional — an intersection-emptiness-only pin fails OPEN, verified: `_extract_frontmatter_text('---\n---\n')` → `''` → `yaml.safe_load('')` → `None` → `set(None or {}) & _DORMANT_KEYS` → `set()` → passes on a gutted template. Clause (c) additionally makes the pin fail loudly on (i) **deletion** — the state Non-Requirements forbids and which `yaml.safe_load` cannot otherwise see — and (ii) **activation day**, when a key leaves `_DORMANT_KEYS`: an intersection-only pin silently drops coverage exactly when `lifecycle_config.py:41`'s "activation must be loud and deliberate" guard most needs it. It imports `_DORMANT_KEYS` from `cortex_command.lifecycle_config` rather than restating the key names (#372's "no third hand-maintained copy"). Acceptance — all must hold:
   - `.venv/bin/pytest tests/test_lifecycle_config_dormant_template.py -q` passes, parametrized per path (3 cases visible in `-v` output, one per template).
   - Negative-case sentinels in the same file prove discrimination on synthetic in-memory input: a live key **fails**, a commented key **passes**, an **empty region fails**, and a **deleted (absent) key fails**.
   **Phase**: Template consistency

6. **`docs/overnight.md:57`'s false bullet is removed**, deferring to the owning doc — `docs/overnight-operations.md:728` already forbids enumerating scaffolded fields in more than one doc, and `overnight.md:15` already defers mechanics there. Acceptance: `grep -c 'skip-specify' docs/overnight.md` = 0. **Phase**: Documentation truth-up

7. **`docs/overnight-operations.md:715`'s false consumer claim is corrected** to state the four keys are scaffolded but dormant and that specify/plan always run; `:706`'s flattened list distinguishes live from dormant. Acceptance: `grep -c 'reads optional defaults' docs/overnight-operations.md` = 0. **Phase**: Documentation truth-up

8. **`docs/setup.md:120` is corrected**, separating `type` (live-in-prose, genuinely read by skill prose) from the four dormant keys and dropping the claim that the dormant keys are "read only as optional overrides". Acceptance: `grep -c 'advisory or read only as optional overrides' docs/setup.md` = 0. **Phase**: Documentation truth-up

9. **The three "CI parity gate" claims are corrected downward to match reality.** `docs/setup.md:118`, `docs/overnight-operations.md:706`, and `cortex/adr/0017-*.md:72` ("Enforcement is CI-time (`just test` / CI gates merge)") are **false**: no workflow runs `just test`, `validate.yml`'s allowlist excludes the parity test, and `main` has no branch protection (`GET /branches/main/protection` → 404; ruleset = `deletion` + `non_fast_forward` only), so nothing gates merge. Correct them to say a parity test checks byte-identity under developer-run `just test`. Do **not** claim CI enforcement. Acceptance: `grep -rc 'CI parity gate' docs/setup.md docs/overnight-operations.md` = 0 for both. **Phase**: Documentation truth-up

10. **All four seeded configs under `~/Workspaces` stop emitting dormant-key warnings**, using the same claim-free commented form as R1. Manifest: `cortex-command` (2 live keys), `gaggimate-barista` (2), `Team-Builder-Bot` (2), `wild-light` (**4** — including hand-authored `default-tier: simple` / `default-criticality: medium`, commented not deleted, preserving the intent in-file per the user's decision). Acceptance — every repo must report `0` (measured baseline: 2 / 2 / 2 / 4). `read_branch_mode` takes a `Path`; passing a `str` raises a `TypeError` that `grep -c` swallows as a false `0`:
    ```bash
    for r in cortex-command gaggimate-barista Team-Builder-Bot wild-light; do
      n=$(.venv/bin/python3 -c "
    import pathlib
    from cortex_command.lifecycle_config import read_branch_mode
    read_branch_mode(pathlib.Path('/Users/charliehall/Workspaces/$r'))
    " 2>&1 | grep -c 'no effect')
      echo "$r: $n"
    done
    ```
    `Interactive/session-dependent:` the paths are machine-local by nature — the target repos exist only on this workstation, so no CI job, fresh agent, or overnight runner can verify this requirement. It is the one requirement in this spec that does not meet project.md:13's "agent-verifiable from zero context" bar, and it is accepted as such rather than dressed up. **Phase**: Seeded-config sweep

11. **Each external repo's edit lands as its own focused single-file commit in that repo** (`gaggimate-barista`, `Team-Builder-Bot`, `wild-light`); `cortex-command`'s own config rides this feature's PR normally. Committing rather than leaving the edit unstaged is required, not stylistic: `wild-light` is on `main` with 9 dirty entries **all under `cortex/`** — the same directory as the edit target — so an unstaged edit sits in the repo's highest-collision path, where the next `git add cortex/` absorbs it into an unrelated commit or `git checkout .` destroys it. Each commit touches `cortex/lifecycle.config.md` only; no unrelated dirty file is staged. Acceptance: `Interactive/session-dependent: for each external repo, git show --stat HEAD lists exactly one file (cortex/lifecycle.config.md), and git status --short is unchanged for every pre-existing dirty entry.` **Phase**: Seeded-config sweep

## Non-Requirements

- **Does not wire the four keys up to any consumer.** For `skip-specify`/`skip-review` this is closed by the record: `transition_table.py:148` names them among keys **absent** from `CONFIG_KEY_TO_PARAM` that "select NO parameter", and #372 bounded its config work to "no field semantics change". For `default-tier`/`default-criticality` the position is weaker and worth stating accurately: both **are** mapped in `CONFIG_KEY_TO_PARAM` with enums and defaults, parked awaiting a caller — `resolve_parameters` has no production caller today. They are dormant in effect, not unbuilt.
- **Does not change the warning mechanism.** `_warn_config_keys` stays fail-open and loud; the tripwire stays armed for user-set keys. This ticket stops cortex tripping its own wire.
- **Does not touch `validate.yml` or the CI/merge-gating story.** Research found CI red on every push to main since 2026-07-13 (4 runs, aborting at `validate.yml:45` so later steps are `skipped`) and `main` unprotected. That is a real and larger problem than #380, it predates it, and wiring a step below line 45 would produce a test that never runs. → **follow-up ticket**.
- **Does not correct `cortex/research/archive/user-configurable-setup/research.md:110-111`** despite its false "Active" rows. No convention governs archived research; nothing cites it as a live source; #372 cited only its accurate rows (`:112-113`). The repo's ethos is preserve-don't-rewrite.
- **Does not fix the missing `.cortex-init` markers** in `gaggimate-barista` / `Team-Builder-Bot`, where `--ensure` raises via `check_content_decline`. Pre-existing. → **follow-up ticket**.
- **Does not reconcile the two frontmatter definitions** — the parity test's byte-split vs production's `line.strip() == "---"`. Latent trap. → **follow-up ticket**.
- **Does not build a migration/lint verb for consumer repos.** The Solution-horizon triggers do fire here (the patch applies in four named places), so this is a surfaced fork, not an assumed one: the durable option is a verb; the chosen option is four hand-edits committed per repo, because the user is the only consumer and the existing warning already names the file and key. Revisit if a second consumer ever appears.

Design alternatives rejected during research, recorded so they are not re-litigated: removing the keys from `_DORMANT_KEYS` (identical noise, and the message degrades to a false `unknown key`); deleting the keys from the templates (`docs/setup.md:118` designates the annotated asset as the schema's source of truth).

## Edge Cases

- **`---` inside a hint**: truncates the parity test's compared region and misreports the cause. Pinned by R2.
- **Editing only one template copy**: `test_frontmatter_byte_parity` fails with `frontmatter byte-parity mismatch: asset=N bytes, template=M bytes`.
- **Hand-editing the plugin mirror**: pre-commit regenerates via `just build-plugin` and blocks on a dirty `plugins/` tree.
- **A user uncomments a key later**: warns again — correct and intended. The two comment styles are behaviorally identical: an uncommented valueless `skip-specify:` parses to `None` and warns the same as `skip-specify: false`, so the style choice carries no safety implication and rests on convention alone.
- **Activation day** (a key leaves `_DORMANT_KEYS`): R5's clause (c) fails loudly because the newly-live key is still commented in the template. This is the intended tripwire, not a nuisance failure — the failing test is the signal to uncomment the key and update the docs in the same change.
- **Next lifecycle entry in `cortex-command` and `wild-light`**: the init-artifacts hash moves (both markers currently read `e13159b2`), so each prints a **one-time** drift report ending `Overwrite all with shipped: cortex init --force`. Nothing is rewritten — `scaffold(overwrite=False)` creates missing files only. **Do not run `--force`**: in wild-light it would overwrite a customized `cortex/requirements/project.md` and `.gitignore` (backed up, but destructive). ADR-0017:75-76 anticipated this. All template edits land in one commit (R1 and the hint fix are both Phase 1), so the report fires once, not per phase.
- **`gaggimate-barista` / `Team-Builder-Bot` have no `.cortex-init` marker**: they never drift-report; `--ensure` raises via `check_content_decline` (`handler.py:224`), so lifecycle entry is dead there regardless. Their configs are hand-fixed anyway — the backlog half of the benefit is real (`resolve_backlog_backend` warns independently of `--ensure`), the lifecycle half is not.
- **Nested `backlog:` keys**: unaffected — `_warn_config_keys` iterates `for key in parsed`, top-level only.
- **Dormant ≠ inert to a model**: `_LIVE_PROSE_KEYS` proves this file is model-read, and an archived transcript shows an agent reading `skip-review: false` and reasoning "full lifecycle review will gate this change". All four repos set `false` (the default), so commenting is behaviorally safe — but by luck.

## Changes to Existing Behavior

- **MODIFIED**: fresh `cortex init` seeds a config emitting **2** dormant-key warnings → **0** (verified: every remaining live key is `_LIVE_CODE_KEYS` or `_LIVE_PROSE_KEYS`; zero unknown keys across all four repos).
- **MODIFIED**: template hints claim `(override auto-assessment)` → claim-free enum hints; all four dormant keys commented symmetrically.
- **MODIFIED**: `docs/overnight.md:57`, `docs/overnight-operations.md:706`/`:715`, `docs/setup.md:120` assert the four keys are honored → state they are reserved and dormant.
- **MODIFIED**: `docs/setup.md:118`, `docs/overnight-operations.md:706`, `cortex/adr/0017-*.md:72` claim CI enforcement → state developer-run `just test`.
- **MODIFIED**: the init-artifacts hash changes, firing a one-time `.cortex-init` drift report in `cortex-command` and `wild-light`.
- **ADDED**: `tests/test_lifecycle_config_dormant_template.py` (runs under `just test`; **not** CI-blocking — see Non-Requirements).
- **REMOVED**: `docs/overnight.md`'s duplicate scaffolded-field enumeration.

## Technical Constraints

- **ADR-0017** gates the entire frontmatter region byte-identical between asset and init template; reconcile direction is asset ← template ("up"), never reverse. This change moves both symmetrically, so the directional rule does not trigger.
- **#372 boundary**: "no third hand-maintained copy of the config schema" → the pin imports `_DORMANT_KEYS`, and R1's hints assert no dormancy status.
- **CLAUDE.md**: `skills/lifecycle/assets/` is lifecycle-gated (prose-only; no hook enforces it). `docs/`, `tests/`, `cortex_command/init/templates/` are not gated, but the parity gate forces the whole edit through the gate anyway.
- **No new ADR** — fails `cortex/adr/README.md:23`'s first criterion. Falls inside ADR-0017; ADR-0017:72's edit is a factual correction, not a new decision.
- **Pytest, not a `bin/cortex-check-*` gate** — ADR-0017 chose CI-time over commit-time for this file pair; a bin script would require SKILL.md-to-bin parity registration or a `.parity-exceptions.md` entry.
- **Local-green ≠ CI-green in this repo.** `tests/test_lifecycle_references_resolve.py` reports `4 passed` in the working tree and `1 failed, 3 passed` in a fresh clone — it enumerates via `git ls-files` but resolves via filesystem `is_dir()`, and `cortex/lifecycle/sessions` is gitignored while `cortex/lifecycle/feat` is untracked. Not this ticket's to fix, but do not read a green `just test` as evidence CI is green.
- **Landing sequence**: edit both templates → `just build-plugin` → `.venv/bin/pytest tests/test_lifecycle_config_parity.py tests/test_lifecycle_config.py tests/test_lifecycle_config_dormant_template.py` → `just check-contract` (baseline exit 0) → commit via `/cortex-core:commit`. External-repo commits are made separately, one file each.

## Open Decisions

- **Phase 3 is untrackable by this lifecycle's own machinery, and that is accepted, not solved.** `stage_artifacts.py`'s `collect_paths(phase, slug, root)` runs `git add` with `cwd=<this repo>`, so Complete structurally cannot stage a foreign repo's file, and `feature_complete` carries no field for external work. R11's per-repo commits are the mitigation — the work lands in each repo's own history rather than as orphaned dirt — but this feature's PR will not contain it and `feature_complete` will not reference it. Recorded here so "Done" is not read as covering the three external repos.

## Proposed ADR

None considered.
