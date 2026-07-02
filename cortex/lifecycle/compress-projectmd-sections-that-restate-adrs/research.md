# Research: Compress project.md sections that restate ADRs, CLAUDE.md, and tests

Backlog: `351-compress-projectmd-sections-that-restate-adrs-claudemd-and-tests` · Epic parent: #347 · Complexity: complex · Criticality: high

## Epic Reference

Primary research for this ticket is the epic **skill-value-scorecard** audit (`cortex/research/skill-value-scorecard/report.html`, verdict source `cortex/research/skill-value-scorecard/master_candidates.json`). The epic scored every always-loaded / frequently-loaded prose surface in the repo for value-vs-duplication; this ticket executes only the eight `project.md` verdicts. Epic content is **not** reproduced here — the audit's per-section keep-lists are cited by ID and the cut-safety claims were independently re-verified locally (below).

## Clarified Intent

Compress eight audit-verified line-ranges of `cortex/requirements/project.md` that restate content already living in an ADR body, in always-loaded `CLAUDE.md`, in a test docstring, or in enforcement-site documentation — dropping the duplicated prose while preserving, verbatim where named, the clauses the audit found have **no other home**. Also fix the stale pointer at L27. The *keep-set* is audit-determined; the *compression magnitude* (how short each bullet becomes) is a user editorial judgment reconciled at spec/PR review, not an audit-fixed target.

### Scoping precision (do not use bare candidate IDs)

`s4`…`s15` are **`master_candidates.json` candidate IDs, file-scoped to `file == cortex/requirements/project.md`**. They are *not* H2 sections — five of them (s6–s10) are consecutive line-ranges carved out of the single `## Architectural Constraints` H2. The same numeric IDs collide with the **concurrently-live #350 session** (which is editing `skills/research/SKILL.md` and has its own s4/s6/s15 with different meanings). Always resolve an ID through the project.md scope; never act on a bare `s6`.

## The eight verdicts (all `verified_survives` / `COMPRESS`)

| ID | project.md lines | Cut (duplicated → its verified other-home) | Must-survive keeps (load-bearing residue) |
|----|------|--------------------------------------------|-------------------------------------------|
| **s4** | 25, 27 (Philosophy of Work) | Finalization mechanics (Steps 9–11a, flag-gated stage-first, three-path enumeration, idempotent routing) → **ADR-0004** (+ #339 amendments); ADR-README forbids restating | Multi-step-with-reinvocation contract; **merge-not-PR-open is terminal** + `merge_anchor:"merge"`; two-kind pause taxonomy + parity-test cite. **Side-fix L27**: pointer `skills/lifecycle/SKILL.md` → `skills/lifecycle/references/kept-pauses.md` |
| **s6** ⚠︎med | 37, 38 (L36 stays) | Shim docstring-retitle wording → `pipeline/metrics.py:367,396` (`_DAYTIME_DISPATCH_FIELDS`) | L37 one-line shim **policy** sentence (sole guard — no test); L38 gotcha + 3 facts: binstubs read installed wheel not tree, `python3 -m` runs tree, **`CORTEX_COMMAND_FORCE_SOURCE=1`** remedy (primary prose home; else only bin-wrapper comments) |
| **s7** | 41, 42, 43 | L41 EnterWorktree → **ADR-0008**; L42 install-state rationale → `install_core.py:763-768` + `install_state.py:7` | L42 keep: `test_install_state_path_parity.py` cite + dependency-direction ("wheel never imports from `plugins/cortex-overnight/`"); L43 AUTO_ENSURE already near-minimal |
| **s8** | 44, 45, 46 | L46 skill-dir paragraph → **CLAUDE.md** skill-dir principle + **ADR-0009** + `skill_path.py`; detector self-docs → lint modules | Literal tokens `cortex-check-bare-python-import`, `cortex-check-skill-path`, both `<!-- …-lint:ignore-next -->` sentinels, `tests/test_backlog_grep_targets_resolve.py`, ADR-0009 pointer; L44 one-clause WHY (no other prose home) |
| **s9** | 47, 48 | L47 starlette example → `pyproject.toml:18-19`; L48 budget rows / ≤400 default / cluster membership / completeness gate → `test_l1_surface_ratchet.py:53-56,130-160,169` + `ROUTING_PRESSURE_CLUSTER` | L47 two prose-only policies (uv-tool-install-ignores-lock ⇒ requires-dist is the only universal governance; promote-transitive-capped); L48 **heading token "SKILL.md L1 surface ratchet" verbatim** + cluster-exemption + re-cap-with-rationale-+-lifecycle-id rules (**CLAUDE.md:44 cites this section BY NAME for exactly these two policies**) |
| **s10** | 49, 50 | L49 supervision body → **ADR-0011**; L50 code-internals narration → `test_worktree.py:659-816` (`test_containment_*`) + `worktree.py:230-231` | L50 **same-repo-overnight-is-NOT-exempt** clause (counter-intuitive matrix cell; only prose home — no ADR for containment) |
| **s11** | 58 only (Quality Attributes; L54-57,59 untouched) | Cue-family enumeration (`sk-ant-`/`gh?_`/`xox[bp]-`/`AKIA`/`ASIA`; `Bearer`/`password=`/`token=`/URL-userinfo; PEM) → `pipeline/dispatch.py:_redact` + `test_dispatch.py` | Three policy clauses with no other home (no ADR covers redaction): scrubbed-at-source before brain/report; **deliberately-incomplete** defense-in-depth; **no prefixless fixed-length blob matcher** + benign-high-entropy rationale + `→ #309` |
| **s15** | 98, 99 (Optional; L96,100 untouched) | Preflight detail → `docs/overnight-operations.md` + `auto-update.md` + cortex-check-parity contract block; two-mode-gate → `contract.py:_in_scan_scope` + tests | `## Optional` H2, the first-line prunability-convention sentence, bold-led bullet form, the `Workflow trimming` bullet (all pinned by requirements-write schema) |

Locally re-verified: ADR-0004/0008/0009/0011 all exist; `cortex/adr/README.md` §"No-content-duplication discipline rule" (L51-60) explicitly forbids project.md restating an ADR body and requires a one-line back-pointer — this grounds every `→ ADR-NNNN` cut (s4/s7/s10). CLAUDE.md:44 confirms the by-name pointer to "SKILL.md L1 surface ratchet" for the cluster-exemption + re-cap rule (s9 keep). CLAUDE.md:57 confirms the canonical kept-pauses path is `references/kept-pauses.md` (validates s4's L27 fix).

## Cross-cutting constraints (apply to every edit)

1. **Contract lint (E101/E103) — `project.md` IS in scan scope** (`tests/test_check_contract.py:162` → `True`). Compressing a bullet to "gate-name + pointer" naturally tempts a bare inline-code `cortex-check-*` mention, which the contract lint **rejects** unless it carries required flags/subcommand. Mitigation: keep the currently-passing token forms, or drop the `cortex-` prefix in prose, or include the flag. Run `cortex-check-contract` as a gate. (Directly relevant to s8, s9, s15.)
2. **requirements-write schema** (`skills/requirements-write/SKILL.md:26-35`) pins: all **eight H2s in order** (Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries, Conditional Loading, Global Context, Optional), bold-led bullets, the Optional section's first-line convention, and a ≤1,200-token (`cl100k_base`) budget. Never drop or reorder an H2; keep bold-led bullet form.
3. **CLAUDE.md verbatim pointers**: keep the "SKILL.md L1 surface ratchet" heading token (s9) and the Philosophy-of-Work Solution-horizon home (untouched by s4). Do not rename these headings.
4. **Test content-pins**: the only test asserting on project.md *body text* is `tests/test_load_requirements_cli.py`, which pins the **Conditional Loading** format and the project.md-first / Global-Context ordering — none of the eight compressed ranges. `test_l1_surface_ratchet.py` pins only the s9 heading token.

## Verification strategy (shaped by the critic's sharpest finding)

The load-bearing residue is precisely the prose **nothing enforces** — the verdicts repeatedly confirm "No test greps project.md for …". This asymmetry defines the verification approach:

- **Cuts are gate-verifiable**: each dropped clause's content demonstrably lives in its named other-home (ADR / test / CLAUDE.md / code docstring / pyproject). Verify by presence-grep at the other-home + absence-grep in project.md.
- **Keeps are NOT gate-verifiable**: no grep proves the surviving residue is *sufficient*. The plan pins presence-greps for the specific must-survive tokens (necessary, not sufficient), and **the user-review gate (spec §4 approval + PR diff review) is the load-bearing check on keep-sufficiency** — not ceremonial.

## Risks

- **s6 is the lone medium-confidence verdict**, and its keeps (shim policy sentence, `FORCE_SOURCE` remedy) are exactly the clauses with no test backstop. Treat s6 with the most editorial care; over-cutting it fails silently.
- **Silent-failure region**: an over-cut of any "only prose home" clause (s6 shim/FORCE_SOURCE, s10 same-repo-not-exempt, s11 redaction rationale, s4 pause taxonomy, s8 L44 WHY) passes all automation. This is why criticality is `high` despite the prose being inert — plus project.md is the always-loaded constitution consulted by lifecycle/refine/discovery.
- **Concurrent #350 session** is live-editing `skills/research/SKILL.md` on `main`. #351 touches only `cortex/requirements/project.md` (disjoint file set), but commits must use explicit pathspec to avoid capturing the other session's staged work.

## Open Questions

- **Compression magnitude / authored voice** — how aggressively to cut, and whether the user wants to keep any duplicative phrasing in their own voice. *Deferred: resolved at Spec §4 approval and PR review, per the ticket's Integration note (this is a user editorial call, not a research question).*
- No unresolved investigation questions remain — all cut-safety and structural claims were verified locally above.
