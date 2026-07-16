# Research: Stop cortex seeding and carrying live dormant config keys

**Backlog**: #380 · **Tier**: complex · **Criticality**: high (see *Criticality reassessment*)
**Clarified intent**: Comment `skip-specify`/`skip-review` out of both parity-gated shipped `lifecycle.config.md` templates so fresh inits are consistent and quiet, correct the docs that falsely claim the four dormant keys are honored, pin the invariant with a regression test, and directly fix the already-seeded configs under `~/Workspaces` — so the config-warning surface signals only genuine problems again.

**Scope fence**: the "wire the keys up to real consumers" arm is **closed**, not deferred by this ticket. `cortex_command/lifecycle/transition_table.py:148` records that `skip-specify`/`skip-review` "select NO parameter"; #372 (`cortex/backlog/372-*.md:32`) bounded its own config work to "audit-and-warn only: no field semantics change"; the arm was explicitly deferred three times in the record. No skill prose reads any of the four keys (verified by grep across `skills/lifecycle/**`, `skills/refine/**`).

## Codebase Analysis

### Files that change

| Path | Change | Gate |
|---|---|---|
| `cortex_command/init/templates/cortex/lifecycle.config.md:12-13` | Comment out `skip-specify` / `skip-review` | Init-artifacts hash input |
| `skills/lifecycle/assets/lifecycle.config.md:12-13` | **Byte-identical** same edit | ADR-0017 parity; lifecycle-gated (`skills/`) |
| `plugins/cortex-core/skills/lifecycle/assets/lifecycle.config.md` | **Regenerate via `just build-plugin`** — never hand-edit | Pre-commit Phase 2–4 drift loop |
| `docs/overnight.md:57` | Delete the false field bullet, link to the owning doc | — |
| `docs/overnight-operations.md:706`, `:715` | Correct the false consumer claim | Owning doc per `docs/policies.md:35-37` |
| `docs/setup.md:120` | Correct; split `type` (live-in-prose) from the dormant four | — |
| `tests/test_lifecycle_config_dormant_template.py` | New regression pin | Only runs under `just test` — see *CI enforcement* |

Two copies exist because there are two distribution channels (ADR-0017:9-17): the plugin asset reaches plugin-only users without the CLI; the init template is what `cortex init` drops. No runtime consumer reads the **asset** (ADR-0017:24-26) — only the project-root copy seeded from the template is live.

### Comment convention (resolved)

The existing style retains **no value** and aligns the trailing hint at column 26:

```
# default-tier:           # simple | complex (override auto-assessment)
# default-criticality:    # low | medium | high | critical
```

Match it: `# skip-specify:` + column-26 hint. The competing proposal to retain `false` was justified on safety grounds ("an uncommented valueless key is inert") — **that rationale is false and was disproven by execution**: an uncommented valueless key parses to `None` and warns identically. Both styles are warning-free when commented and warn when uncommented; there is no byte-parity difference either. The choice rests on convention alone.

**Constraint**: the hint text must never contain `---`. `tests/test_lifecycle_config_parity.py:56` splits on `raw.split(b"---", 2)` — a naive byte split, not a delimiter-*line* match. A `---` inside comment prose truncates the compared region (proven: 1752 → 560 bytes) and surfaces as `missing required option line(s): ['# backend: jira', ...]`, an error naming the `backlog:` block with no hint of the real cause. Use the repo's existing em-dash (`—`).

### Comment-out vs delete vs de-classify (resolved)

- **Delete the keys**: wrong. `docs/setup.md:118` designates the annotated asset as the schema's single source of truth; deleting removes the documentation the docs point at.
- **Remove from `_DORMANT_KEYS`**: strictly worse. Proven identical noise volume, and the message degrades to `unknown lifecycle.config.md key 'skip-specify' — ignored`, which is *false* — the key is known and reserved. It also destroys epic #371's activation tripwire.
- **Comment out**: correct. The Web angle's "one uniform machine-checkable marker" (Cargo's `cargo-features`, Ruff's Preview tier) already exists here — it is `_DORMANT_KEYS`, which lives in code and stays. Commenting the template stops cortex tripping **its own** wire while leaving it armed for user-set keys. That is precisely npm#8071's distinction: warn on keys you don't own, not on your own scaffolding.

`CONFIG_KEY_TO_PARAM` (`transition_table.py:155-161`) gives `default-tier`/`default-criticality` a mapped landing spot; `skip-specify`/`skip-review` have no entry at all — a strictly lower tier of dormancy. Commenting (not deleting) keeps all four symmetric.

## Verified behavior

- **Fresh init is warning-free, not merely quieter.** Today a fresh `cortex init` config emits exactly **2** warnings; with the keys commented, **zero**. Every remaining live key checks out: `commit-artifacts`, `branch-mode`, `backlog`, `synthesizer_overnight_enabled` are `_LIVE_CODE_KEYS`; `type`, `test-command` are `_LIVE_PROSE_KEYS`. All four seeded repos have zero unknown keys.
- **The `backlog:` block is unaffected.** `_warn_config_keys` iterates `for key in parsed` — **top-level only**; nested keys are never inspected. (Latent, out of scope: a typo'd nested `bakend:` warns nothing and silently falls back to the default backend.)
- **No test breaks.** Every test touching these keys builds synthetic frontmatter in memory (`tests/test_lifecycle_config.py:188`, `cortex_command/lifecycle/tests/test_transition_table.py:145-162`); none reads a real template. The parity gate's `_REQUIRED_OPTION_LINES` does not include either key.

## Init-hash and consumer drift

`cortex/lifecycle.config.md` is a hash input (`scaffold.py:69`). The edit moves the hash **`v1:e13159b2…` → `v1:7197fdfe…`** (computed).

`--ensure` on hash mismatch (`handler.py:171-178`) calls `scaffold(overwrite=False)` — **create-missing-only**, never rewrites an existing file (`scaffold.py:308-314`), pinned by `test_cortex_gitignore_ensure_preserves_hand_edit`. It then silently refreshes `.cortex-init` and prints a one-time stderr drift report. **No clobber risk.** ADR-0017:75-76 anticipated exactly this: editing the template "would change the init-artifacts hash and fire a one-time `.cortex-init` drift report into every initialized repo." Auto-invoked only from lifecycle entry (`enter.py:178`), not a SessionStart hook.

**Footgun to surface, not to fix**: the drift report ends with `Overwrite all with shipped: cortex init --force`. In wild-light that report lists 4 drifted files including its heavily-customized `cortex/requirements/project.md`; `--force` would overwrite them (backed up, but destructive). A ticket justified as noise reduction emits a one-time noise burst recommending a destructive command. Bounded and anticipated — but it should be stated.

**Marker inventory** (drives the manual sweep):

| Repo | Live dormant keys | `.cortex-init` marker |
|---|---|---|
| `cortex-command` | `skip-specify`, `skip-review` | `e13159b2` → will drift-report |
| `wild-light` | **all four** (`default-tier: simple`, `default-criticality: medium` too) | `e13159b2` → will drift-report |
| `gaggimate-barista` | `skip-specify`, `skip-review` | **absent** |
| `Team-Builder-Bot` | `skip-specify`, `skip-review` | **absent** |

The two marker-less repos never auto-scaffold and never drift-report — `--ensure` there hits `handler.py:224` `check_content_decline`, which **raises**. This supports hand-fixing them, and flags a pre-existing condition (lifecycle entry may error in those repos) that is **not this ticket's to fix**.

## Requirements & Constraints

- **ADR-0017** gates the entire frontmatter region byte-identical. Reconcile direction is asset ← template ("up"), never the reverse; this change touches both symmetrically, so it does not trigger.
- **No new ADR warranted** — fails the three-criteria gate's first test ("unwound by editing one file in one PR", `cortex/adr/README.md:23`). This falls inside ADR-0017; touched docs should back-point rather than re-derive.
- **#372's boundary — "no third hand-maintained copy of the config schema"** — requires the pin to import `_DORMANT_KEYS` rather than restate the four key names.
- **Test, not pre-commit gate.** ADR-0017 chose CI-time over commit-time for this file pair. A new `bin/cortex-check-*` would additionally require SKILL.md-to-bin parity registration or a `.parity-exceptions.md` entry — avoidable overhead for a fixed three-path content check.
- `skip-specify`/`skip-review` are **not** kept-pause suppressors (`kept-pauses-data.toml` uses only `branch-mode`, `test-command`, `backlog.backend`, `judgment`), so nothing there interacts.
- **`docs/` is not lifecycle-gated**; only the `skills/` asset drags this edit through the gate. That gate is prose-only — no hook blocks it (the one wired hook early-exits unless basename == `SKILL.md`).

## Docs accuracy

| Location | Claim | Verdict |
|---|---|---|
| `docs/overnight.md:57` | "Skip lifecycle phases when they don't add value" | **FALSE** |
| `docs/overnight-operations.md:715` | "lifecycle specify/plan: reads optional defaults…" | **FALSE** |
| `docs/overnight-operations.md:706` | Flattens live + dormant into one list | MISLEADING |
| `docs/setup.md:120` | "advisory or read only as optional overrides"; lumps `type` (live-in-prose) with the dormant four | **FALSE** |
| `docs/setup.md:118`, `docs/overnight-operations.md:706` | "a CI parity gate keeps its frontmatter byte-identical" | **FALSE** — see *CI enforcement* |
| `cortex/adr/0017-*.md:72` | "Enforcement is CI-time (`just test` / CI gates merge)" | **FALSE** — see *CI enforcement* |
| Template hints (both copies) | `default-tier` "(override auto-assessment)" | **FALSE since authorship** |
| `cortex/requirements/backlog.md:105` | "refine (tier/criticality seeding)" | ACCURATE — describes Clarify's real auto-assessment; unrelated |

`docs/overnight-operations.md:728` states "do not enumerate the scaffolded fields in more than one doc" — and `:706` in that same doc violates its own rule; four enumerations exist. So `overnight.md:57` and `setup.md:120` were **duplication violations before they were also wrong**; the fix is to delete and link, not reword. `setup.md:120` also contradicts its own `:118`, which says the asset is "the single place to read the scaffolded schema rather than re-listing it here" — then re-lists it.

**The template's own hint was never true.** `git log --all -S"default-tier"` across `skills/lifecycle/references/` returns **zero commits, ever**. "(override auto-assessment)" advertises a capability that has never existed. This is not documentation that drifted.

## CI enforcement (load-bearing)

`.github/workflows/validate.yml:38-51` runs an **allowlist of five** pytest files plus a dashboard smoke test. No workflow runs `just test`; no pre-commit hook runs pytest. Neither `test_lifecycle_config.py` nor `test_lifecycle_config_parity.py` is on the allowlist.

Consequences:
1. A new regression pin under `tests/` would run **only when a developer manually types `just test`** — false confidence, the exact failure this ticket exists to correct.
2. **ADR-0017's own enforcement claim is already false**, and two shipped docs repeat it. These are false claims of precisely the species #380 targets, sitting in the same sentences being edited.

Recommendation: ship the pin **and** its `validate.yml` wiring, or ship neither. One line beside the existing five blocking steps makes it real. Prefer *making the CI-gate claim true* (add `test_lifecycle_config_parity.py` to the allowlist) over correcting it downward.

## Dormancy is Python-centric — a caveat

"Dormant = no effect" holds for Python consumers. But `_LIVE_PROSE_KEYS` proves this file is **model-read**, and `cortex/lifecycle/archive/devils-advocate-smart-feedback-application/research.md:145` shows an agent reading `skip-review: false` and reasoning *"full lifecycle review will gate this change"*. The keys are **quasi-live via the LLM**. All four repos set `false` (the default), so commenting them is behaviorally safe — **but only by luck**. This strengthens the case for commenting them out: a key a model might read and act on, that no code honors, is worse than no key.

## Landing sequence

1. Edit `cortex_command/init/templates/cortex/lifecycle.config.md:12-13` (no `---` in hints).
2. Apply the byte-identical edit to `skills/lifecycle/assets/lifecycle.config.md:12-13`.
3. `just build-plugin` — regenerates the mirror; stage it.
4. `.venv/bin/pytest tests/test_lifecycle_config_parity.py tests/test_lifecycle_config.py` (baseline: 23 passed).
5. `just check-contract` (baseline: exit 0; fires on `docs/*` and `tests/*` edits).
6. Commit via `/cortex-core:commit` only.

## Open Questions

1. **Does the regression pin get CI wiring?** — *Resolved: yes, or drop the pin.* A pin outside `validate.yml`'s allowlist never runs. Ship pin + allowlist entry together. Spec to confirm scope.
2. **Do we correct or make-true the false "CI parity gate" claim** at `docs/setup.md:118`, `docs/overnight-operations.md:706`, and `cortex/adr/0017-*.md:72`? — **Resolved (user, 2026-07-16): make it true.** Add both `test_lifecycle_config_parity.py` and the new dormancy pin to `validate.yml`'s blocking allowlist (~1 line each). This closes a real enforcement gap, makes the three existing claims honest without rewriting them, and is what makes the new pin real rather than manual-only. Q1 folds into this.
3. **wild-light's hand-authored `default-tier: simple` / `default-criticality: medium`** — **Resolved (user, 2026-07-16): comment out all four.** `git blame` → `bbe59833` (charleshall888, 2026-03-21); `git log --all -S"default-tier: simple"` on the templates returns zero commits, so these were **never seeded — hand-written in the belief they worked**. They are also one call site from live (`resolve_parameters` has no production caller today, but `transition_table.py:159-160` wires both to real parameters). Commenting (not deleting) leaves the intent visible in-file for whenever tier/criticality overrides get wired up. wild-light goes fully silent.
4. **Regression-pin location** — *Resolved: new file* `tests/test_lifecycle_config_dormant_template.py`. Two agents disagreed (extend `test_lifecycle_config_parity.py` vs new file). New file wins: the dormancy check is a *single-file content policy* over **three** paths, whereas the parity gate is a *two-file byte-equality* check scoped by ADR-0017's charter; merging them makes "why did this fail" ambiguous. Collection is automatic; cost is zero.
5. **Should the plugin mirror be in the pin's file set?** — *Resolved: yes.* The drift hook is procedural (bypassable via `--no-verify`), not a content invariant. One extra dict entry.
6. **The two `---`-vs-line-match frontmatter definitions** (`parity test` byte-split vs production `line.strip() == "---"`) are unpinned and diverge beyond the CRLF rationale the docstring gives. — *Deferred: out of scope.* Latent trap; worth a follow-up ticket, not this one.
7. **`gaggimate-barista` / `Team-Builder-Bot` have no `.cortex-init` marker**, so `--ensure` raises via `check_content_decline`. — *Deferred: out of scope, pre-existing.* Worth a follow-up ticket.

## Criticality reassessment

Clarify rated this **high**, resting partly on the init-hash reaching every seeded consumer's drift detection. Research narrows that: the honest reach is a **one-time stderr notice**, no clobber, anticipated by ADR-0017. What survives is that the template is shipped infrastructure every future repo copies, inside a byte-parity-gated pair where a malformed edit (e.g. a `---` in a hint) fails with an error pointing at the wrong file. Spec should re-rate with this evidence rather than inheriting the Clarify default.
