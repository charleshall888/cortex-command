# Research: `cortex-load-requirements` selection verb (offload the load-requirements.md algorithm)

**Scope anchor (clarified intent):** Extract the deterministic requirements-file *selection* algorithm narrated in `skills/lifecycle/references/load-requirements.md` into a `cortex-load-requirements` CLI verb that prints the resolved file **list** (paths only, never contents): `project.md` + always-load Global Context paths + tag-matched area docs, with absent files annotated `(skipped: file absent)` and the no-match fallback noted. The shared reference collapses to "run it, read what it lists, inject the list." Preserve the *selection set* exactly. Part of epic 336. Tier: complex · Criticality: high.

---

## Codebase Analysis

**New files**
- `cortex_command/lifecycle/load_requirements_cli.py` — the verb module (sits beside `backlog_backend_cli.py`, `state_cli.py`). Wheel-only — **not** mirrored.
- `bin/cortex-load-requirements` — dual-channel bash wrapper (auto-mirrored to `plugins/cortex-core/bin/` by `just build-plugin`).
- Verb unit + golden test (new `cortex_command/lifecycle/tests/test_load_requirements_cli.py`, or extend `tests/test_load_requirements_protocol.py`).

**Modified files**
- `pyproject.toml` `[project.scripts]` (~line 52, alphabetical with the `cortex-lifecycle-*` / `cortex-load-parent-epic` rows): `cortex-load-requirements = "cortex_command.lifecycle.load_requirements_cli:main"`.
- `skills/lifecycle/references/load-requirements.md` — collapse (the ~55–65% offload).
- 5 consumer one-liners (see Migration).
- `tests/test_load_requirements_protocol.py` — **breaks; must be reworked** (see Behavioral Parity + Migration).
- `plugins/cortex-core/**` mirrors regenerate automatically — never hand-edit.

**Templates to model**
- Read-only print verb: `cortex_command/lifecycle/backlog_backend_cli.py` (argless argparse, resolves project via `cortex_command.common._resolve_user_project_root()`, one line to stdout, returns 0).
- Pure-fn + CLI-shim split, golden-pinnable: `cortex_command/backlog/resolve_item.py` (`resolve(...) -> ResolutionResult` + thin `main()`).
- Dual-channel wrapper: `bin/cortex-read-backlog-backend` (branches a→d: `CORTEX_COMMAND_FORCE_SOURCE` → wheel-probe → working-tree `PYTHONPATH` → fail-open).
- **Closest analog:** `cortex-load-parent-epic` (`cortex_command/backlog/load_parent_epic.py` + `bin/` + `tests/test_cortex_load_parent_epic_parity.py`) — a "load" verb that takes a slug and **parses YAML frontmatter itself**.

**Data formats the verb parses** (`cortex/requirements/project.md`)
- `## Conditional Loading` bullets: `- <trigger phrase> → <repo-relative path>` (separator is ` → `, U+2192). Paths are already full (`cortex/requirements/observability.md`).
- `## Global Context` bullets: currently `- glossary.md` (**bare filename** — a data bug; see Adversarial #1). Authoring contract (`requirements-write/SKILL.md:34`) requires full paths.
- `index.md` tags: `tags: [worktree-interactive, concurrency, lifecycle]`.

**Conventions**
- Console-script entry is canonical; `python3 -m cortex_command.lifecycle.load_requirements_cli` is the working-tree fallback (`CORTEX_COMMAND_FORCE_SOURCE=1` for dogfooding).
- **Events-registry: NOT required** — read-only, paths-to-stdout, emits nothing to `events.log`. (`_telemetry.log_invocation` invocation telemetry is optional.)
- Dual-source: `just build-plugin` rsyncs `skills/`, `bin/cortex-*` → `plugins/cortex-core/`; `.githooks/pre-commit` runs build-plugin + `git diff --quiet plugins/$p/` on staged source → commit canonical + mirror **together**.
- The in-Python `_simulate_loader` (`tests/test_load_requirements_protocol.py:218`) is the de-facto algorithm spec — promote it into the real implementation + golden (but fix its empty-tag bug; see Adversarial #3).

## Web Research

Strong, directly transferable prior art:
- **"Resolve-and-print-paths" family**: `git ls-files` (newline default; `-z` NUL; **`-t` = `<status> <path>` inline annotation** — the established idiom for "list the path but flag its state"); `git check-ignore`; **ESLint `--print-config`** ("no work performed; only the resolved result is output" — the canonical *show-what-would-be-selected* pattern); Prettier `--list-different`. Output convention: newline-delimited paths is the default; JSON only when structured per-path metadata is needed.
- **"Narration → tool" refactor** is endorsed across sources: an algorithm narrated in a prompt is *advisory* ("business rules in prose become suggestions, not constraints"); moving it to a deterministic tool makes it *enforced* and saves tokens. Anti-drift answer is structural: make code the single source of truth and **delete** the duplicated narration rather than keep a paraphrase beside it; pin behavior with a golden test.
- **Golden/snapshot testing** (Python: **Syrupy** — fails on missing baseline; `pytest-snapshot`): serialize the *entire* output (paths + status + fallback note) into one formatted string and snapshot it whole; include the literal fallback sentence in a no-match fixture so the canonical string is pinned byte-for-byte.
- **Substring-match hazard** (Microsoft "Old New Thing"): case-insensitive substring over-matches whole tokens (`"destructible"` ⊂ `"indestructible"`); ASCII-only `lower()` is non-ASCII-unsafe. Pin both a substring near-miss and a whole-tag hit in tests.
- **Absent-entry annotation** has two lineages: *annotate-and-continue* (`git ls-files -t`) vs *fail-loud* (`git --error-unmatch`, compiler unresolved-reference errors). The spec wants annotate-and-continue — a defensible, prior-art-backed choice for advisory-input-to-a-model, but a conscious one.
- Web cannot resolve the two internal questions (which fallback string is canonical; residual-content fate) — those are codebase/judgment calls.

## Requirements & Constraints

- **Epic 336 shared discipline** (from `cortex/backlog/336-*.md` and siblings #326/#330): "pin the **byte-identical-output invariant** (events.log rows, staged-path **sets**) so consolidation cannot silently change behavior." For #333 the invariant lives on the **selection set + the emitted fallback string**, pinned by a golden test. The epic's "reuse resolve-once backend routing" clause is **N/A** here (the verb never touches the backlog backend).
- **Skill-helper modules** (`project.md:35`): collapse dispatch ceremony into a `cortex_command` subcommand exposing a `[project.scripts]` entry. This verb is a **degenerate (read-only, paths-only) case** — it does *not* fuse mutation+telemetry and registers **no** event; the console-script-entry half applies, the events-registry half does not. `cortex-read-backlog-backend` / `cortex-lifecycle-state` are existing read-only console scripts in the family, so the pattern admits read-only verbs.
- **SKILL-to-bin parity** (`cortex-check-parity`): the `bin/` wrapper must be referenced by an in-scope file — the collapsed `load-requirements.md` naming the verb wires it; **no `.parity-exceptions.md` row needed**. Model a `tests/test_cortex_load_requirements_parity.py` on the sibling parity tests.
- **SP001/SP002** (`cortex-check-skill-path`): a **bare-name console-script** invocation (`cortex-load-requirements …`) is PATH-resolved → does **not** trip D1/D2. The offload **removes** a `${CLAUDE_SKILL_DIR}/../lifecycle/references/load-requirements.md` propagated-path consult from each consumer → net SP-surface *simplification*. (ADR-0009: the CLI mechanism is reserved for exactly this — executable steps in cortex-coupled skills.)
- **L201 bare-Python prohibition**: consumers must invoke the console-script name, never `python3 -m` / `import cortex_command`.
- **Wheel-binstub vs working-tree** (`project.md:38`): make `bin/cortex-load-requirements` a dual-channel wrapper (working-tree fallback) so it runs before a wheel rebuild. Editing the `cortex_command` package ⇒ **sequential dispatch, not worktree** (`just test` runs the editable install, so a worktree verifies stale code — per project memory).
- **L1 surface ratchet: unaffected** — `bin/cortex-measure-l1-surface` measures only `description`+`when_to_use` frontmatter; all edits here are reference/body text. No budget row changes.
- **`grep -c` target-resolution gate**: only fires on `[a-z_]+`-shaped tokens in `grep -c "..."` Done-When checks. The verb name has dashes and emits no event — don't introduce an event token; pin the fallback **string** as a literal under `cortex_command/` (the "literal string under cortex_command/" arm).
- **Scope boundaries** (`project.md`): in scope (skills/lifecycle/CLI); reading/concatenating requirements file *contents* is **out of scope** (paths only — the model still reads them).

## Interface & Boundary Design *(mandated alternative-exploration; ticket suggested `--tags`)*

**Recommendation: `cortex-load-requirements [--feature <slug>]` (Option B), reject the ticket's `--tags`-only interface.** Keep `--tags` (and a future `--backlog-slug`) shelved as escape hatches — unjustified by any current consumer.

**Per-consumer call-site availability** (5 live call sites; 3 skills):

| Call site | Context | `index.md` + tags at load time? | Today's outcome |
|---|---|---|---|
| `refine/references/clarify.md` §2 | **under `/lifecycle`** | **YES** (seeded by `discovery-bootstrap.md`, lifecycle Step 2, before delegation) | tag-match |
| `refine/references/clarify.md` §2 | **standalone refine** (A or B) | **NO** (standalone refine emits only `lifecycle_start`; no index yet at clarify) | fallback |
| `refine/references/specify.md` §1 | any | load **skipped** ("skip redundant requirements loading") | (no live load) |
| `lifecycle/references/review.md` §1 | under `/lifecycle` | **YES** | tag-match |
| `discovery/references/clarify.md` §2 | always ad-hoc | **NO** (discovery uses `cortex/research/{topic}/`, never a lifecycle index) | fallback |
| `discovery/references/research.md` §1a | always ad-hoc | NO | fallback |

**Why Option B:**
- House convention: every read/load/state verb is a **thick, slug-input verb that does its own I/O + YAML parse** — `cortex-load-parent-epic` parses backlog frontmatter itself; `cortex-lifecycle-state --feature` hardcodes `cortex/lifecycle/{feature}/events.log`. A pure tags-in verb would be the lone exception.
- **Faithfulness (the decisive argument):** the ticket's `--tags` would have the caller pass backlog tags in standalone-refine clarify → area-doc match → **over-loads vs today's fallback**, silently changing behavior. Option B preserves today's fallback there. (Note the weaker "re-introduces YAML parsing" framing is partly wrong — in *clarify* the model already read the backlog frontmatter in §1; the YAML-parse objection only bites in specify/review.)

**Corrected invocation rule (per Adversarial #4/#5):** `refine/clarify.md` is **one static file** used in both lifecycle (index present) and standalone (index absent) contexts and cannot branch on entry point. Therefore: **lifecycle/refine consumers always pass `--feature {slug}`; the verb degrades to fallback (project.md + Global Context + note) when `index.md` is absent/tag-less** — one behavior serves both. Discovery is the **sole** no-`--feature` case (its slug maps to `cortex/research/`, not a lifecycle index). `--feature`-on-absent-index **must equal** no-feature output (define this explicitly — it's currently unspecified).

**Output (recommended): newline-delimited paths, `project.md` first, absent entries suffixed ` (skipped: file absent)`** — matching the existing `load-requirements.md:9` notation. Reject JSON and the git-`-t` `<status> <path>` prefix: both invent a schema/token absent from the prose and add reformatting burden with no machine consumer (none parses the output).

## Behavioral Parity & Fallback Reconciliation

**Output contract the verb must reproduce (selection set):** `project.md` (always, first) ∪ every `## Global Context` path (file order; resolved literally against repo root; absent → ` (skipped: file absent)`) ∪ matched area docs (Conditional Loading order; deduped, "loaded once"). Step 4's "project.md + matched area docs" **undercounts** — step 1 routes Global Context into the list. Ordering is implicit in the prose → **fix it explicitly** in the verb.

**Three divergent fallback strings (verified; none is parsed by any code — `grep` across `tests/ hooks/ bin/ cortex_command/ claude/` is empty, so all dependence is *semantic*):**
1. `load-requirements.md:17` — `…; loaded project.md only` (optional/advisory, no consumer).
2. `review.md:12` — `…; drift check covers project.md only` (injected into the reviewer prompt; semantic-only).
3. `review.md:31` — `only project.md loaded — no area docs matched tags` (a **competing** instruction for the *same* injection point as #2).

**Recommendation — emit the GENERIC string from the verb, overriding the ticket's literal directive:** `no area docs matched for tags: {tags}; loaded project.md only`, `{tags}` interpolated by the verb as `[t1, t2, …]` (unquoted, comma-space; empty → `[]`). The verb is shared by 5 consumers but **only review has a drift check** — emitting review.md:12's "drift check covers…" leaks review vocabulary into clarify/specify/discovery. Let `review.md` keep its own drift-check phrasing as a thin wrapper around the verb's path list, and reconcile `review.md:31` to defer to the verb output. **This deviates from the ticket's Integration line ("preserve it [review.md:12] (emit it from the verb)") → flagged for Spec sign-off** (see Open Questions).

**Two invariants, kept separate (per Adversarial):**
- **Set-fidelity** (epic 336 / ticket "reproduce the current prose exactly"): the verb's selection set == the prose algorithm. Pin via an oracle-parity test + a real-`project.md`-format test. *Do not* let "output was already non-deterministic" license set drift.
- **String-determinism**: the verb's stdout is deterministic going forward. The "current LLM output is already non-deterministic (4 forms observed in real artifacts), so we pin from here" reframe is legitimate **for the string only**.

**Golden-test design:** synthetic fixtures (**not** live `project.md` — `glossary.md` is absent today so a live golden would flip skipped→loaded if #223's lazy file lands); full-string stdout equality (incl. trailing-newline); 3 scenarios (match; no-match/`[]`/absent with `{tags}` variants; dedup/multi-tag-one-phrase/unmatched-tag-dropped); shared fallback-string module constant imported by verb + test; **plus one test against the real `project.md`** to avoid the synthetic-fixture blind spot. The parity-**replay** harness (`test_cortex_load_parent_epic_parity.py`) does **not** apply — there is no original bin script (the "original" is LLM prose).

## Migration & Touch-Point Reach

**Reach (corrected): ~7 mirrored canonical files + their mirrors** (the `cortex_command` module is wheel-only, not mirrored; the earlier "10+10=20" over-counted):

- **MUST-CHANGE — 5 consumer one-liners + the protocol file (6 skill files, each mirrored):** `refine/references/clarify.md`, `refine/references/specify.md`, `lifecycle/references/review.md` (also owns the fallback-note injection), `discovery/references/clarify.md`, `discovery/references/research.md`, and `lifecycle/references/load-requirements.md` itself.
- **+ `bin/cortex-load-requirements` (mirrored).**
- **KEEP unchanged — 3 SKILL.md path-propagation manifest entries** (`lifecycle/SKILL.md:133`, `refine/SKILL.md:68`, `discovery/SKILL.md:74`): they map the protocol name → an absolute path for a *thin* `load-requirements.md` that still exists, so they stay valid. They change only if the reference file were deleted entirely (not recommended).
- **Non-adopter:** `requirements-write/SKILL.md` (it *authors* the schema; descriptive mention only).

**Gate-by-gate:** parity → land verb module + `[project.scripts]` + bin wrapper + mirror **in the same commit** as the first reference that names the verb (else E002 unresolved / W003 orphan); skill-path → net simplifies (bare PATH command); bare-python → console-script name only; L1 ratchet → unaffected; events-registry → no event; `grep -c` → low risk (pin the fallback string as a `cortex_command/` literal).

**Inherited #328 test debt (verified pre-existing red):** `tests/test_load_requirements_protocol.py` fails **2/10** (`test_six_consumer_references_cite_shared_protocol`, `test_rule_carriers_carry_consumer_rule_prose`) — its `CONSUMER_REFS`/`RULE_CARRIERS` still point at `skills/lifecycle/references/{clarify,specify}.md`, relocated to `refine/references/` by #328 (commit `8c2ec8ce`). The same relocated paths are also cited in `tests/test_check_skill_path.py`, `tests/test_critical_review_gate_nonlocal_failsafe.py`, and fixtures (`skill_path/{positive,negative}.md`, `discovery-brief/complex-topic/research.md`) — sweep these too, but distinguish **stale assertions** (fix) from **intentional fixture content** (leave). Flag as #328 cleanup coupled into #333, not #333 scope creep.

**Rollout sequencing (no gate red mid-change):** (1) verb module + `[project.scripts]` + bin wrapper + mirror + unit/golden test, fully wired, one commit; (2) reinstall editable wheel before any invocation / `just test` (sequential dispatch, not worktree); (3) collapse `load-requirements.md` + migrate the 5 consumers, regen + commit mirrors **with each** canonical edit; (4) fix `test_load_requirements_protocol.py` (stale paths + migrate the protocol-shape assertions to the verb test) and sweep the #328 debt. Ship the **bin wrapper** (working-tree fallback, drift-resilient — consumers already call `cortex-read-backlog-backend` in the same paths).

## Residual Content & Reference Collapse

Classification of `load-requirements.md` (31 lines): steps 1–5 + `## Matching Semantics` → **into the verb**; "read the listed files + inject the list" → **remains** (the irreducible model residue — a verb printing paths cannot load contents into the model's context); the glossary-surfacing line → **judgment, remains**; `## Why this protocol` → **rationale, relocate**.

- **Glossary-surfacing instruction (line 19) — keep verbatim.** It is model judgment (a path-printer can't detect "a concept *you need* is undefined"), and it is **test-enforced**: `test_rule_carriers_carry_consumer_rule_prose` lists `load-requirements.md` as a `RULE_CARRIER` (regex `absence as a signal|surface the term`). `cortex/requirements/glossary.md` does not exist on disk (lazy per #223). De-duplicating its 4 copies is a *separate* concern, **out of scope**.
- **`## Why this protocol` — drop from the reference; relocate** to the verb module docstring or an ADR, keeping a one-line intent pointer ("the verb selects the minimal tag-relevant set, avoiding under/over-loading"). Consistent with `project.md:40` ("Skills back-point to ADRs rather than restating rationale") and CLAUDE.md's "What/Why-not-How."
- **`## Matching Semantics` — moves entirely into the verb**; the verb's `--help` is the human-readable home. Its bullets become verb behavior (and the verb's tests).

**Collapsed reference ≈ 12 lines.** Surviving headings: `# Tag-Based Requirements Loading`, `## Protocol` (run `cortex-load-requirements --feature {slug}`; read every listed non-skipped path; inject the printed list verbatim downstream + relay any fallback note) + the glossary-surfacing line. **Verb/model boundary:** verb = deterministic selection (read project.md + Global Context + index.md tags → match → emit annotated path list + fallback note); model = read file contents + glossary-surfacing judgment + injection.

## Adversarial Review

1. **Global Context normalization is an invented heuristic masking a data bug.** Live `project.md` has `- glossary.md` (bare filename) but `load-requirements.md:9/26` say "resolve against repo root" and `requirements-write/SKILL.md:34` (the authoring contract) requires full paths — **the live data violates its own contract**. A "prepend `cortex/requirements/`" rule in the verb is nowhere in the prose and would mis-handle a future genuinely-repo-root bullet (e.g. `docs/foo.md`). **Durable fix: change the data** to `- cortex/requirements/glossary.md` and resolve literally. Safe today (glossary absent → "skipped" either way); corrects future behavior. This is a **set-fidelity** point, not "non-deterministic anyway."
2. **Trigger-only vs whole-line matching — silent over-load.** Match must be scoped to the trigger *left of `→`* (as `_simulate_loader` does). Whole-line substring-matching lets a tag like `requirements` match the *path* `cortex/requirements/*.md` on every line → loads all area docs.
3. **Empty-string tag → loads everything.** `"" in trigger` is `True`; `tags: ["", …]` or a trailing comma matches every trigger. **`_simulate_loader` has this exact bug** (no empty guard) — reusing it as the oracle would propagate the defect. Verb must strip empty/whitespace tags; add a negative-control test.
4. **`--feature` on absent `index.md` is unspecified; standalone refine hits it.** Must fall back to project.md + Global Context (= no-feature output), or standalone-refine clarify breaks.
5. **"Omit `--feature` for discovery AND standalone-refine" is unrealizable** — `refine/clarify.md` is one static file in both contexts. Resolution: always pass `--feature`; verb degrades on absent index. Discovery is the sole genuine no-feature case (folded into the Interface section above).
6. **Fallback string — the ticket's instruction is wrong for a shared verb** (drift-check vocab leaks to 4 non-review consumers). Emit the generic form; review keeps its wrapper (folded into Behavioral Parity).
7. **Test traps:** the parity-replay harness doesn't apply (no original script); synthetic-only fixtures can agree while both wrong about the real format (the oracle uses comma-prose triggers; live `project.md` uses slash-bulleted triggers) → add a real-`project.md` test; the #328 debt spans multiple test files, not one.
8. **Whole-tag-not-partial:** don't split `harness-adaptation` into `harness`+`adaptation` (the tag word is the match unit).

## Open Questions

- **Fallback string emitted by the verb — deviates from the ticket.** *Resolved (recommendation, pending Spec sign-off):* emit the generic `no area docs matched for tags: {tags}; loaded project.md only`; `review.md` retains its own "drift check covers…" wrapper; reconcile `review.md:31` to defer to the verb output. This **overrides** the ticket's Integration directive ("preserve [review.md:12] … emit it from the verb"), so it must be confirmed at Spec §4 before implementation. Rationale: the verb is shared by 5 consumers, only review has a drift check; no code parses the string (semantic-only).
- **Global Context data fix (project.md `- glossary.md` → `- cortex/requirements/glossary.md`).** *Resolved (recommendation):* fix the data to conform to `requirements-write/SKILL.md:34` and have the verb resolve literally against repo root (no bare-filename heuristic). Behavior-neutral today (glossary absent → "skipped"). Touches `project.md` (just outside the verb) — confirm at Spec whether to bundle into #333 (recommended: yes, one-line coupled correctness fix) or split to a follow-up.
- **Verb input/output shape.** *Resolved:* `cortex-load-requirements [--feature <slug>]`; lifecycle/refine always pass `--feature` with graceful fallback on absent/tag-less index; discovery omits `--feature`; `--feature`-on-absent-index ≡ no-feature output. Output: newline-delimited paths, `project.md` first, absent suffixed ` (skipped: file absent)`. `--tags`/`--backlog-slug` shelved.
- **Pre-existing #328 test debt scope.** *Resolved:* fix the 2/10 red in `test_load_requirements_protocol.py` (stale `lifecycle/references/{clarify,specify}.md` → `refine/references/`) and migrate its protocol-shape assertions to the verb test; sweep the other citing files (`test_check_skill_path.py`, `test_critical_review_gate_nonlocal_failsafe.py`, fixtures), fixing stale assertions and leaving intentional fixtures. Treat as #328 cleanup coupled in, not new scope.
- **Algorithm edge cases to pin (no open decision — implementation requirements):** trigger-only matching; strip empty/whitespace tags; whole-tag-not-partial; ASCII case-insensitive substring; dedup; Global Context list-of-paths (no tag gating) in file order; `[]` ≡ absent ≡ missing-field → fallback. Fix `_simulate_loader`'s empty-tag bug if reused as the oracle.

## Considerations Addressed

- **Pin byte-identical output with a golden test + resolve the canonical fallback string.** Addressed: split into two invariants — *set-fidelity* (oracle-parity + real-`project.md` test) and *string-determinism* (full-stdout golden snapshot on synthetic fixtures + a shared module constant for the fallback string). Canonical string resolved to the **generic** form (`…; loaded project.md only`), overriding the ticket's review.md:12 directive (pending Spec sign-off), because no code parses it and "drift check" vocab is wrong for the 4 non-review consumers.
- **Decide whether residual model-judgment content stays or is removed.** Addressed: the glossary-surfacing instruction **stays** verbatim (model judgment, and test-enforced as a `RULE_CARRIER`); `## Why this protocol` **relocates** to the verb docstring/ADR with a one-line pointer; `## Matching Semantics` **moves into the verb** (its `--help` is the human-readable home) — consistent with epic 336's "extract purely deterministic narration" framing.
