# Research: harness-friction-triage

## Research Questions

1. **Distribution channel inventory: how many distinct surfaces exist today, and where does each chain break for which install method?**
   → **Five surfaces, not four.** (a) Python entry points in `pyproject.toml [project.scripts]` → `~/.local/bin/` via `uv tool install`; (b) canonical bash scripts in `bin/` (25 scripts) → never on PATH for any installed user; (c) mirrored bash scripts in `plugins/cortex-core/bin/` → `~/.claude/plugins/cache/cortex-command/cortex-core/<sha>/bin/`, **NOT on PATH** because the SessionStart bootstrap hook adds only `~/.local/bin` and not `CLAUDE_PLUGIN_ROOT/bin` [`plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh:29`]; (d) module imports (`python3 -m cortex_command.X`) → require uv-tool venv's python or a sys-installed `cortex_command`; (e) **install-version skew** — `pyproject.toml` adds new entry points (e.g. `cortex-lifecycle-event` at `pyproject.toml:43`) but existing uv-tool installs don't auto-refresh, so the installed venv lags the repo. 24 of 25 bash scripts in `bin/` have **no** corresponding `pyproject.toml` entry point.

2. **Skill-author contract: how many skills reference binaries/flags/modules that don't exist on the active install?**
   → **8 distinct drift signatures across ≥9 skill files**, against a total skill-file count of N (see §Codebase Analysis for the per-skill enumeration). Catalogued in §Codebase Analysis below. Includes a required-arg drift (`cortex-create-backlog-item --title --body` with no `--status`/`--type`) that fires from `skills/morning-review/SKILL.md:91`, `skills/morning-review/references/walkthrough.md:416`, and `skills/discovery/SKILL.md:87` against the argparse contract at `cortex_command/backlog/create_item.py:155-157`. The drift is observable in skills authored on different dates against multiple distinct CLI surfaces — not a single skill-author's idiosyncrasy. "Pervasive" here means "spans multiple unrelated authoring contexts," not "majority of skills" (no falsifiability threshold was pre-registered; the denominator-based prevalence claim is deliberately not asserted).

3. **Slug-space bridge: which CLIs accept which slug forms, and is unification safe?**
   → **Safe to unify, with the caveat that unification *will* change observable behavior for inputs that currently fail-fast under one tool.** Four slug forms in circulation (numeric ID, filename slug, lifecycle slug, UUID). Zero collisions across 110 backlog items with `lifecycle_slug:` set. No structural signal embedded in slug strings — numeric prefix is display-only; epic membership lives in `parent:` frontmatter [`cortex_command/backlog/build_epic_map.py:54-84`]. **User's framing was inverted**: `cortex-resolve-backlog-item` accepts lifecycle slugs (via substring) and rejects filename slugs; `cortex-update-item` does the opposite [`bin/cortex-resolve-backlog-item:147-152`, `cortex_command/backlog/update_item.py:128-145`]. A deterministic resolution order (UUID prefix → numeric ID → exact filename stem → exact `lifecycle_slug` → ranked substring) unifies safely — but the new order necessarily *adds* accepted inputs to each CLI. Regression sample required: every (CLI, input) pair where the current behavior is fail-fast must be evaluated under the new order before the resolver ships.

4. **Gate-policy taxonomy: how cleanly do existing gates split into security vs. hygiene?**
   → **Partially clean.** 8 gates audited in `cortex_command/critical_review.py`. **0 pure security, 5 hygiene, 3 mixed.** The 3 mixed are: the candidate-symlink check (mechanically broken — see Q5), and the two sentinel-verifier gates (`verify_reviewer_output`, `verify_synth_output`). The verifiers are "bypassable hygiene masquerading as integrity gates" — a stub file containing only `READ_OK: <path> <correct-sha>` satisfies them, because the verifier validates only the SHA appears in a sentinel line, not that the reviewer actually engaged the artifact [`cortex_command/critical_review.py:227-271`, `:499-554`]. A third tag — "advisory" — is needed alongside security/hygiene to honestly label them.

5. **Plugin-cache staleness: did it cause the missing `cortex-critical-review` in batch 2?**
   → **No — wheel-install skew, not plugin cache.** `cortex-critical-review` is a Python console-script entry point [`pyproject.toml:30`] shipped via the wheel installed by `uv tool install`. It is **not** present in `plugins/cortex-core/bin/` (only 2 files there: `cortex-morning-review-*` per the rsync rules at `justfile:543-575`). The friction was a category misunderstanding — the user's other session expected a plugin-tier bash wrapper, but the binary is wheel-tier. Root cause: existing uv-tool installs don't auto-refresh against new `[project.scripts]` entries (the 5th fragmentation axis from Q1). The active backlog owner of this remediation direction is **ticket 235 (`trigger-cortex-cli-reinstall-at-sessionstart-on-cli-pin-drift`, `status: refined`)** which already proposes the SessionStart-hook approach for CLI/version pin drift. Ticket 213's Gap C remediation has shipped (`status: complete`); the residual scope sits with 235.

## Codebase Analysis

### Distribution channel fragmentation
- **Five surfaces enumerated** in Q1 with concrete file citations.
- **Bash → entry-point parity gap**: 24 of 25 bash scripts in `bin/` lack a `pyproject.toml [project.scripts]` entry. Only `cortex-morning-review-complete-session` is dual-channel. Specific gap binaries the user has hit: `cortex-lifecycle-state` [`bin/cortex-lifecycle-state`], `cortex-check-prescriptive-prose` [`bin/cortex-check-prescriptive-prose`], `cortex-resolve-backlog-item` [`bin/cortex-resolve-backlog-item`], `cortex-commit-preflight`, `cortex-backlog-ready`, `cortex-complexity-escalator`, `cortex-load-parent-epic`.
- **PATH-exposure gap**: `plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh:29` prepends `~/.local/bin` only. No `CLAUDE_PLUGIN_ROOT/bin` append — plugin-tier bash bins never reach Bash-tool PATH.
- **Existing lint scope is too narrow**: `bin/cortex-check-parity:243-293` unions `bin/` with `[project.scripts]` to validate *references*, but doesn't enforce "every bash script has an entry point" or "every entry point reaches PATH."

### Skill-vs-CLI contract drift (8 signatures, ≥9 files affected)
1. `skills/discovery/SKILL.md:77` invokes `python3 -m cortex_command.discovery generate-brief` — works only when system python resolves the module. The binary `cortex-discovery generate-brief` exists [`cortex_command/discovery.py:686`]. **Note: this drift signature is NOT enumerated in ticket 248's closed four-callsite Problem section** — 248 names exactly `bin/cortex-backlog-ready`, `bin/cortex-morning-review-complete-session`, `skills/critical-review/references/residue-write.md:13,28`, `skills/lifecycle/references/implement.md:27`. The discovery callsite must be added to 248 (reopen + amend) or assigned to a sibling ticket.
2. `skills/morning-review/SKILL.md:91`, `skills/morning-review/references/walkthrough.md:416`, `skills/discovery/SKILL.md:87` invoke `cortex-create-backlog-item --title ... --body ...` with no `--status` and no `--type` — both required at `cortex_command/backlog/create_item.py:155-157`. **Active failure mode** in 3 skills.
3. `skills/lifecycle/SKILL.md:53,56`; `skills/lifecycle/references/clarify.md:12`; `skills/lifecycle/references/orchestrator-review.md:7`; `skills/lifecycle/references/specify.md:169-170`; `skills/lifecycle/references/plan.md:21,271-272`; `skills/lifecycle/references/implement.md:314`; `skills/dev/SKILL.md:126`; `skills/refine/SKILL.md:30,165` — all call `cortex-lifecycle-state` / `cortex-resolve-backlog-item`. Neither has a `pyproject.toml` entry. Plugin-only install → `command not found`. **9 skill files affected.**
4. `skills/commit/SKILL.md:12` calls `cortex-commit-preflight` — same gap.
5. `skills/backlog/SKILL.md:92,109` calls `cortex-backlog-ready` — same gap.
6. `skills/refine/references/clarify-critic.md:16,65,198` hardcodes path-qualified `bin/cortex-load-parent-epic` — breaks outside repo cwd.
7. `skills/lifecycle/references/complexity-escalation.md:3,7,15` calls `cortex-complexity-escalator` — same gap.
8. `skills/lifecycle/SKILL.md:56`; `skills/discovery/references/decompose.md:32,36,77` reference path-qualified `bin/cortex-resolve-backlog-item` and `bin/cortex-lifecycle-state` — same cwd-dependency.

### Slug-space inventory
| Form | Authored at | Canonical store | Input-accepting CLIs | Output-emitting CLIs |
|---|---|---|---|---|
| Numeric ID | `cortex-create-backlog-item` next-free allocation [`cortex_command/backlog/create_item.py:36-45`] | Filename prefix `^\d+-` | `cortex-resolve-backlog-item` [`bin/cortex-resolve-backlog-item:130-144`]; `cortex-update-item._find_item` [`update_item.py:137-140`] | `cortex-generate-backlog-index`; `build_epic_map` |
| Filename slug | `{NNN}-{slugify(title)[:6 words]}.md` at create-time | Filesystem path | `cortex-update-item` (exact stem + substring); `cortex-resolve-backlog-item` (exact-stem after `^\d+-` strip ONLY — rejects with prefix) | `cortex-resolve-backlog-item` JSON `filename` field [`:186-195`] |
| Lifecycle slug | Frontmatter `lifecycle_slug:` or derived [`cortex_command/overnight/backlog.py:104-130`] | Frontmatter + `cortex/lifecycle/{slug}/` dir | `/cortex-core:lifecycle`; NOT `cortex-update-item` (verified user report); accepted by `cortex-resolve-backlog-item` via substring | `cortex-resolve-backlog-item` JSON `lifecycle_slug` field [`:194`] |
| UUID | `cortex-create-backlog-item` (uuid4) | Frontmatter `uuid:` | `cortex-update-item` UUID prefix [`update_item.py:147-152`]; NOT `cortex-resolve-backlog-item` | None |

Pre-existing footgun: `update_item.py:142-145` does unranked substring matching — `"add"` matches 29 items, returns first-sorted hit silently. Independent of unification but in the same code path.

### Gate policy audit
| Gate | Location | Classification |
|---|---|---|
| symlink check on candidate | `cortex_command/critical_review.py:84-89` | **Mixed (mechanically broken)** — `realpath(candidate) != abspath(candidate)` triggers on ancestor symlinks (macOS `/tmp` → `/private/tmp`) even when the artifact file itself is not a symlink |
| symlink check on root | `:103-111` | Hygiene |
| strict-prefix check | `:113-120` | Hygiene — but skill prose at `skills/critical-review/SKILL.md:29` promises "use conversation context" with no off-switch in CLI |
| feature-narrowing | `:122-129` | Hygiene |
| is_file check | `:132-135` | Security-adjacent hygiene |
| `verify_reviewer_output` | `:227-271`, `:499-554` | **Advisory** — validates SHA appears in sentinel line; stub files with correct SHA pass; cannot detect reviewer hallucination |
| `verify_synth_output` | `:195-216`, `:449-496` | **Advisory** — same family |
| `record-exclusion` | `:557-578` | Hygiene (telemetry) |

Verifier-gate architectural drift: the gate was designed assuming reviewers write to disk; reality is reviewers emit via the Agent-tool result stream, and the orchestrator-LLM constructs the input file. The SHA-stability property (artifact unchanged between dispatch and synth) is real and cheap; the reviewer-engagement property is the gate's stated intent but cannot be enforced structurally in the current architecture (see DR2 for the implications).

### Brief-gen validator: same anti-pattern, broken-by-default

`cortex_command/discovery.py:validate_brief` (lines 532-580) is structurally a sibling of `verify-reviewer-output`: a hygiene check (substring presence) dressed as a semantic gate (decision-content fidelity). It requires three case-insensitive substrings — `decided`/`decide`, `alternative`/`options`, `tradeoff`/`cost` — against the sub-agent's prose output.

**Empirical: 0/7 success rate** across all `gate_brief_generated` events in `cortex/research/*/events.log` and `cortex/lifecycle/*/events.log`. Every observed brief-gen invocation has emitted `status: "validation_failed"`. Production behavior is the dense-Architecture fallback; the brief.md path is dead by default.

**Mechanism**: the rubric `GATE_BRIEF_RUBRIC` at `discovery.py:285-322` explicitly instructs the sub-agent to "Use ordinary words" and uses `settled on` as its own example verb (line 296) — both fail the validator's substring check. The rubric and validator are in structural contradiction: the rubric asks semantic questions and invites paraphrase; the validator demands lexical conformity to a narrow morphological set. A retry path at `discovery.py:783-810` escalates to literal-token instruction, but the `harness-friction-triage` brief generated during this very discovery (439 words, validation_failed at the retry) demonstrates the retry is empirically insufficient on natural-prose inputs.

**Unlike `verify-reviewer-output`**, the underlying semantic property here *is* enforceable — the sub-agent IS producing prose that answers the three questions; the bug is that the validator measures the wrong proxy. So the DR2-style "abandon the gate" remedy doesn't apply; instead, broaden the anchor sets to cover the natural English paraphrase pool and resolve the rubric/validator contradiction. See new ticket in §Reconciliation matrix.

### Plugin-cache vs. wheel skew
- Plugin cache is Layer 1 (Claude Code-owned) per `docs/internals/auto-update.md:25-29`. Cortex doesn't own its refresh.
- `cortex-critical-review` is wheel-tier (`pyproject.toml:30`); `justfile:543-575` only mirrors top-level `bin/cortex-*` into plugin tree.
- Active backlog owner of remediation: **ticket 235 (`status: refined`)** — proposes SessionStart-hook detection of CLI/version pin drift. Ticket 213 (`status: complete`) previously closed three related gaps; the wheel-install-skew remediation now sits with 235.

### Reconciliation matrix

| Friction item | Existing ticket(s) | Coverage | Disposition |
|---|---|---|---|
| B1.1 brief-gen failure | 206, 227, 236 | Partial (output-density focus) | Comment on 227; **NEW ticket** below covers the validator root cause |
| **B1.1-root validate_brief substring anchors reject natural prose** | none | None — 0/7 corpus success rate | **New ticket** `fix-validate-brief-substring-anchors-reject-natural-prose` (S effort) |
| B1.2 macOS `/tmp` symlink rejection | none | None | **New ticket** |
| B1.3 misleading "decision anchor" error text | none | None | **New ticket** (error-text UX) |
| B1.4 `python3 -m cortex_command.discovery` in skill prose | 248 (`status: backlog`) | None — 248's enumeration excludes this callsite | Reopen 248 OR new ticket |
| B1.5 `cortex-check-prescriptive-prose` not on PATH | 208 [F3] | Partial | Comment on 208 |
| B1.6 discovery Step 2 phase gap | none | None | **New ticket** |
| B1.7 `verify-reviewer-output` architectural drift | 229 | Full | No action |
| B1.8 critical-review "no lifecycle" mode rejects paths | none | None | **New ticket** (folds with B1.2 + gate taxonomy work) |
| B1.9 reviewer prompts cite outside artifact | none | None | **New ticket** (low priority; synth corrects today) |
| OF1 / B2.5 backlog-index race | 135 | Full | No action; elevate 135 priority |
| B2.1 critical-review binary missing in plugin install | 235 (`status: refined`) | Partial | Comment on 235 |
| B2.2 `cortex-resolve-backlog-item` slug-form acceptance | none | None | **New ticket** (folds into slug-resolver piece) |
| B2.3 `cortex-update-item` slug-form acceptance | none | None | **New ticket** (folds into slug-resolver piece) |
| B2.4 `cortex-create-backlog-item --tags` | 233 (query-side only) | Partial | Comment on 233 with write-side counterpart |
| B2.6 PATH split user-bin vs plugin-cache | 208, 235 | Partial | Comment on 235 |
| B2.7 `cortex-lifecycle-counters` undercounts `[partial]` | none | None | Policy decision deferred |
| B2.8 reviewer agent vs strict Requirements schema | none | None | **New ticket** (forgiving parser path per CLAUDE.md MUST-escalation policy) |
| B2.9 worktree-dispatch silent fallback | 208 [F1+F2+F3] | Full | No action |
| B2.10 lifecycle-event helper vs printf inconsistency | 248 | Partial | Comment on 248 |
| OF2 stale palette_editor processes | n/a (user app) | n/a | Out of scope |

**Count: 9 new tickets, 9 fold-into-existing (comment), 2 policy decisions, 1 out-of-scope.**

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A. Bash → entry-point migration** (promote every referenced bash script to a Python entry point or thin shim) | **L** — 24 scripts, three risk classes | Shell-isms (`set -euo pipefail`, pipes) don't translate one-to-one; JSON-emit contracts must be preserved; `install_guard` boundary [`bin/cortex-resolve-backlog-item:32-36`] constrains which scripts can become Python entry points without crossing into wheel-tier | Inventory of 24 unregistered scripts + dependency map onto `[project.scripts]` namespace |
| **B. Skill-prose ↔ CLI contract lint** (parse skill prose; verify against argparse introspection) | M | Skill prose isn't a structured DSL — regex parsing could miss patterns; false-positive cost for over-strict matchers. **Not an extension of `cortex-check-parity` (which is closed at reference-existence altitude per ticket 102 `complete`); this is a new lint at argument-level altitude, complementary to 102's deployed linter.** | Argparse parsers exposed in importable form per module |
| **C. PATH self-test on SessionStart** | S | Adds startup noise if not gated by severity; users may ignore warnings. | Top-N referenced binary list (deterministic via grep of skill files — see Approach B output) |
| **D. Install-version pin probe** | S–M | **Ticket 235 (`status: refined`) already proposes the SessionStart-hook approach for this gap. Approach D should attach to 235's lifecycle, not be specced independently.** | Comparison logic between installed venv's `[project.scripts]` and current `pyproject.toml` |
| **E. Unified slug resolver** in `cortex_command/backlog/resolver.py` | M | **109 (`complete`) and 176 (`complete`) already shipped `cortex-resolve-backlog-item` AND adopted it into lifecycle's clarify §1. The new work is the `cortex-update-item._find_item` consumer only.** Replacing silent substring with ranked candidates is a behavior change. | Tests in `tests/test_resolve_backlog_item.py` extended for ambiguity cases + regression sample for newly-accepted inputs (per Q3) |
| **F. Gate-classifier tag in source** | S | Annotations only — no behavior change. Pure source-discoverability. | Convention agreed across `critical_review.py` and lifecycle CLIs |
| **G. Hygiene auto-resolve helper** for `prepare-dispatch` ad-hoc input | S–M | Adds an "_adhoc" canonical location convention; downstream consumers (reviewer prompts, events.log) need to know it's a scratch dir; lifecycle (retention, cleanup, copy-vs-live staleness) must be specified | Convention for `cortex/lifecycle/_adhoc/<sha-prefix>/` + cleanup policy |
| **H. Symlink check: under-root scoping** | S | Need to update `tests/test_critical_review_path_validation.py:43-79` invariants; small risk of relaxing too much | Decision: which path elements are user-controllable inside the artifact root |
| **I. Verifier rename + rescope** (`verify-reviewer-output` → `check-artifact-stable`; drop reviewer-engagement intent entirely) | M | Skill prose at `skills/critical-review/SKILL.md:70` references current name — must update; downstream consumers may pin the name. **Reviewer-engagement check is not migrated to synth prompt** — see DR2 for why prose-only enforcement was rejected. | Skill-prose audit for verifier-name references |

## Architecture

### Pieces

- **Installation integrity layer (EPIC).** Three sub-tickets, not one piece: (1) bash↔entry-point migration via Approach A (L effort, 24 scripts); (2) PATH self-test at SessionStart via Approach C (S effort); (3) install-version pin probe via Approach D, **attaches to ticket 235** (S–M effort). Subsumes Approaches A, C, D. Catches the three install-time failure modes (missing bash bin, missing PATH exposure, stale venv) as a coherent enforcement surface — but ships as three tickets, not one.

- **Skill-author contract lint.** Parses every `cortex-*` invocation in skill prose against the argparse surface of the named binary; catches drift like the active `--status`/`--type` failure in 3 skills and the `python3 -m cortex_command.discovery` invocation that no longer matches the binary. **Complementary to `cortex-check-parity` (ticket 102 `complete`, validates reference existence); this is a new lint at argparse-level altitude.** Approach B. M effort.

- **Unified backlog/lifecycle slug resolver.** Extends the shipped resolver (109 + 176 `complete`) to the `cortex-update-item._find_item` consumer. The new work is the single missing consumer + the resolver's deterministic ordering across all forms. **Behavior change**: each CLI will accept inputs it currently rejects; regression sample required per Q3. Approach E. M effort (down from prior estimate — most consolidation already shipped).

- **Gate-policy taxonomy + targeted fixes (4 sub-fixes).** Four orthogonal changes touching `critical_review.py`: (1) `# gate-class:` annotations across gates (Approach F, S); (2) hygiene auto-resolve helper for ad-hoc input (Approach G, S–M); (3) under-root symlink scoping (Approach H, S); (4) verifier rename + rescope (Approach I, M). Total: 4 sub-tickets summing to M+. Subsumes Approaches F, G, H, I.

- **Brief-gen validator anchor fix.** Single-file fix to `cortex_command/discovery.py:validate_brief` (and its rubric) that broadens the three substring anchor sets to cover natural English paraphrases (`decided|decision|chose|chosen|concluded|settled|selected` for the decision anchor, similar broadenings for alternatives + tradeoff), and resolves the rubric/validator contradiction where the rubric instructs "Use ordinary words" while the validator demands narrow morphological tokens. Empirical motivation: 0/7 success rate across observed `gate_brief_generated` events; the production behavior is the dense-Architecture fallback. Structural sibling of the Gate-policy taxonomy piece but lives in `discovery.py` rather than `critical_review.py`. S effort.

### How they connect

The four pieces are independent enforcement layers operating at different lifecycle moments. They share one explicit input surface:

**The skill-prose grep enumeration is canonically owned by the Skill-author contract lint piece.** Both the PATH self-test (inside Installation integrity) and any future tool needing a list of referenced binaries consume the contract lint's output as a derived artifact, rather than each piece grep-ing skill prose independently. This ownership is structural, not coincidental — the contract lint already has to parse skill prose for argparse-conformity, so it's the natural source of truth for "the set of `cortex-*` invocations across skills."

**Installation integrity** runs at install/session-start time — before any skill executes. It guarantees the binary surface present in `~/.local/bin/` + plugin PATH matches what the repo declares. **Skill-author contract lint** runs at pre-commit time — before any change ships. It guarantees skill prose invocations match the argparse surface of the binaries they reference. Together these two close the contract loop: install integrity ensures binaries are present; contract lint ensures skills reference them correctly.

**Slug resolver** runs at every backlog/lifecycle CLI invocation. It is the boundary normalizer — accepts any slug form, emits canonical references, surfaces ambiguity explicitly. Removes the input-shape-determines-tool friction.

**Gate-policy taxonomy + targeted fixes** runs at every gate-protected operation. The taxonomy makes gate policy auditable; the targeted fixes (symlink scoping, verifier rename) are the immediate corrections.

The pieces don't depend on each other for *correctness* — each can ship in any order — but they share the skill-grep input surface above. Ignoring that shared input would force every consumer to re-grep, defeating the contract lint's role as canonical source.

## Decision Records

**DR1: Lint-driven parity over manifest-driven generation.** The bash↔entry-point gap could be closed by a build-time generator that emits entry points from a manifest of bash scripts, OR by a pre-commit lint that requires manual entry-point declarations to match the `bin/` listing. We pick the lint. **The tradeoff cuts both ways: the generator would mechanically close all 24 current gaps in one step, but introduces a second source of truth that must itself be kept in sync; the lint preserves `pyproject.toml [project.scripts]` as canonical but relies on developer discipline that has demonstrably already failed (24 of 25 bash scripts unregistered).** The lint wins on canonical-source preservation; loses on retroactive coverage. A one-time bulk migration is required regardless of which approach ships — neither approach repairs the 24 existing gaps automatically without a separate migration pass.

**DR2: Salvage `verify-reviewer-output` for SHA-drift only; do not migrate reviewer-engagement checking to a prose-only synthesizer rubric.** The gate's stated purpose (verify reviewer engagement) is structurally unenforceable in the current architecture — reviewers emit via the Agent-tool result stream and the orchestrator constructs the input file, so no SHA-able artifact captures the reviewer's actual engagement. **The earlier draft proposed migrating the engagement check into the synthesizer prompt, but that is prose-only enforcement, which CLAUDE.md's "Prefer structural separation over prose-only enforcement for sequential gates" principle explicitly rejects.** We instead acknowledge the engagement check as currently unsolvable structurally, rename the gate to `check-artifact-stable` (SHA-drift detection only, which it can honestly enforce), and document that reviewer-engagement *quality* depends on the reviewer's prompt fidelity — not on a downstream gate. Tradeoff accepted: the system loses a check it previously claimed to have but never actually delivered. **A future ticket could re-introduce reviewer-engagement structurally if reviewers move to disk-based output, but that is out of scope for this discovery.**

**DR3: Auto-resolve ad-hoc input into `_adhoc/` rather than relax allowed-dirs — with explicit lifecycle.** The skill prose at `skills/critical-review/SKILL.md:29` promises "use conversation context if no lifecycle"; the CLI must honor that. Two options: (a) relax the CLI to accept paths outside `cortex/lifecycle|research`, or (b) copy the artifact into a canonical `_adhoc` location and proceed. We pick (b). Downstream consumers depend on artifacts living somewhere predictable. **Lifecycle of `_adhoc/` directories**: `cortex/lifecycle/_adhoc/<sha-prefix>/` is gitignored; pruned by a scheduled `cortex clean --adhoc` recipe (default retention: 7 days); events.log entries link `_adhoc` artifacts back to the live source path via a `source_path:` field; copy-vs-live staleness is documented but not auto-detected (a snapshot is what the review pinned). Tradeoff: relaxing allowed-dirs would scatter artifacts across the filesystem and break downstream path assumptions; auto-resolve adds a copy step and introduces the `_adhoc` retention surface, but contains both behind a single convention.

**DR4: Promote `bin/cortex-resolve-backlog-item` to a Python entry point; the shared resolver module lives wheel-side, the bash side disappears.** Earlier framing of "shared resolver callable from both sides of the install_guard boundary" was internally inconsistent — `bin/cortex-resolve-backlog-item:32-36` deliberately avoids importing wheel-side Python, which is why duplication exists today. The honest mechanism is to eliminate the boundary for this specific resolver by promoting the bash side to a Python entry point. **Scope implication**: Approach A absorbs `cortex-resolve-backlog-item` as one of the 24 scripts being migrated; the resolver consolidation work in Approach E becomes "build the shared module + retrofit `cortex-update-item._find_item` to consume it." Alternatives rejected: maintaining duplication with parity tests (preserves the boundary at the cost of abandoning consolidation) and a subprocess bridge (preserves bash-side install_guard avoidance at the cost of per-call subprocess latency) were considered; the entry-point promotion was selected because the project's stated direction is "ship CLI-first as a non-editable wheel" (project.md Overview) — preserving a bash-only resolver is design drift, not a load-bearing boundary.

## Open Questions

- **Decomposition shape**: should the 4 pieces be one epic with 8 tickets (3+1+1+4), or independent? Installation integrity warrants explicit epic structure (now also containing the `cortex-resolve-backlog-item` Python promotion per DR4); Gate taxonomy could ship as 4 independent tickets or as one bundle.
- **`[partial]` task counter semantics (batch 2 item #7)**: lifecycle-policy decision deferred outside this discovery.
- **Reviewer schema mismatch (batch 2 item #8)**: per CLAUDE.md MUST-escalation policy, the prescriptive-prompt fix requires evidence + effort=high trials before escalating. The forgiving-parser route is cheaper-by-policy but needs deciding before decompose.
- **Existing-ticket comment/amendment routing**: 9 friction items fold-via-comment into existing tickets per the reconciliation matrix; does this discovery emit the comment text inline, or hand off to a separate skill? (Discovery convention is new tickets only; amendments may belong elsewhere.)
