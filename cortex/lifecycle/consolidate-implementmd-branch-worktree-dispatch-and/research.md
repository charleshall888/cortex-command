# Research: Consolidate implement.md branch/worktree dispatch + remove the inline Python heredoc (item 332, epic 336)

**Clarified intent (scope anchor):** Consolidate `skills/lifecycle/references/implement.md`'s §1/§1a branch/worktree dispatch so it routes on the outputs of the CLI verbs that already resolve the branch-mode / picker / worktree decision, instead of re-narrating each branch; and remove the 33-line inline `python3 - <<'EOF'` heredoc (an "is the worktree path inside the repo" check, exit-0/2) by folding it into a CLI verb. Trim token bloat from the largest lifecycle reference file while preserving the structural authorization gate, the sidecar mechanics, and the inside-repo contract.

---

## Codebase Analysis

**Target file:** `skills/lifecycle/references/implement.md` (329 lines / 25,666 bytes — the largest lifecycle reference). §1 = lines 7–103 (Pre-Flight Check); §1a = lines 105–207 (Interactive Worktree Creation). Mirror at `plugins/cortex-core/skills/lifecycle/references/implement.md` is byte-identical today and **must never be hand-edited** — regenerate via `just build-plugin` and commit canonical+mirror together.

**What the cited verbs actually resolve (stdout / exit codes):**

| Verb | Module | stdout | Exit |
|---|---|---|---|
| `cortex-lifecycle-dispatch-choice --feature <slug>` | `lifecycle/dispatch_choice_cli.py` → `lifecycle_implement.read_dispatch_choice` | line-position-last `plan_approved` event's `dispatch_choice`, or empty | always 0 |
| `cortex-lifecycle-branch-mode <path>` | `lifecycle/branch_mode_cli.py` → `lifecycle_config.read_branch_mode` | branch-mode token or empty | always 0 |
| `cortex-lifecycle-picker-decision <path> <slug> [<mode>]` | `lifecycle/picker_decision_cli.py` → `lifecycle_implement.should_fire_picker` | `{"fire": <bool>, "reason": "<token>"}` | always 0 |
| `cortex-worktree-create --feature <name> --base-branch <b>` | `pipeline/worktree_create_cli.py` → `pipeline/worktree.create_worktree` | absolute worktree path | 0 ok, 1 create-fail (`repr(exc)`), 2 usage |
| `cortex-worktree-resolve <feature-name>` | `pipeline/worktree_resolve_cli.py` → `pipeline/worktree.resolve_worktree_root` | resolved path | 0 ok, 2 usage |
| `cortex-worktree-precondition` (zero args) | `worktree_precondition.py` | none | **0 = NOT in worktree, 1 = IS in worktree**, 2 usage |

**`should_fire_picker` (lifecycle_implement.py:106) is the decision tree §1 re-narrates.** Returns `(False,"suppressed")` or `(True, reason)`, `reason ∈ {branch_mode_unset_or_invalid, branch_mode_prompt, dirty_tree, live_interactive_worktree_session, suppressed}`. It internally runs `git status --porcelain` (`_is_dirty_tree`) and the PID liveness check (`_has_live_interactive_session`) — these **overlap** the §1 uncommitted-changes guard (L59) and §1a.i liveness check (L109–114). **Caveat (see Adversarial #3):** it is first-match-wins, so the overlap is partial, not total.

**Prose classification (the trim target):**
- *Genuinely redundant with a verb output (route on result, drop narration):* L28–48 (branch-mode preflight narration of the `{fire,reason}` JSON + jq), L19–20 + L50–57 (two overlapping routing tables over the same closed-set tokens), L124–132 (§1a.iii re-describes what `create_worktree` does), L109–114 (liveness duplicates the verb).
- *Agent-owned orchestration that MUST survive:* L22–26 (3-option AskUserQuestion menu text), L59 (uncommitted-guard menu *mutation* — demote/strip-recommended/warn-prefix, distinct from the `dirty_tree` fire decision), L61–73 (runtime probe: `command -v` exit→menu disposition), L75–99 (Step A overnight-rejection sidecar + Step B `cortex-interactive-lock acquire`), L107 + step v (the `selected`/`suppressed` structural branch + cd-shim + `EnterWorktree`), L116–122, L205–207.

**The heredoc (L136–171, opener `python3 - <<'EOF'`):** three checks, fail-closed to **exit 2**, success **exit 0** — (1) `cortex-worktree-resolve interactive-{slug}` subprocess; (2) `git rev-parse --show-toplevel`; (3) `Path(worktree).resolve().relative_to(repo_root.resolve())`. So the verb to build is: resolve worktree path → repo root → assert containment, exit 0/2 (note **2, not 1**). It shells to `cortex-worktree-resolve` + `git rev-parse`.

**Latent path-arg inconsistency to reconcile (see Adversarial #2):** the heredoc resolves `interactive-{slug}` (dash, L142) but step v's cd-shim/`EnterWorktree`/fallback resolve `interactive/{slug}` (slash, L181/191/201). `resolve_worktree_root(name)` returns `<repo>/.claude/worktrees/<name>`, so the slash form yields a *different, nested* phantom path. `create_worktree` already computes `repo` (worktree.py:199) and `worktree_path` (worktree.py:201); step iii captures the correct path into `$worktree_path` (L127). The consolidation should propagate that single captured value to verify + cd-shim + `EnterWorktree`.

**Console-script wiring:** `pyproject.toml [project.scripts]` — worktree verbs at L69–71. Sibling pattern: thin CLI wrapper over a pure `worktree.py` function (stdout clean for `$(...)`, diagnostics to stderr).

**#330-owned event sites (leave untouched):** L228 raw `batch_dispatch`, L293/L320 raw `phase_transition`. L196 (`interactive_worktree_entered`) is **already** a clean verb call and is the only event site in 332's region.

## Web Research

- **Canonical "is path inside directory" idiom (OpenStack security guideline):** canonicalize first, then `os.path.commonpath((base, target))` — **not** `startswith`/`commonprefix` (the `/repo` vs `/repo-evil` false positive is a recurring CVE class; pip CVE-2026-1703, Open WebUI CVE-2026-54014). `pathlib.Path.is_relative_to` (3.9+) is purely lexical — safe only as `Path(target).resolve().is_relative_to(Path(base).resolve())`, i.e. **resolve both operands**.
- **`realpath`/`resolve()` is a deliberate tradeoff, not a pure win:** you generally *want* canonicalization here (git linked worktrees and macOS `/tmp`→`/private/tmp` are symlink-heavy), but you must canonicalize **both** sides consistently — which directly predicts the Adversarial #1 bug.
- **Git worktree gotchas:** a linked worktree's top level holds a `.git` *file* (gitdir pointer), not a directory; `git rev-parse --show-toplevel` resolves symlinks but can disagree with a symlinked shell `PWD`; prefer `git rev-parse --git-path`. (Live Claude Code issue #17927 is in this exact problem space.)
- **Exit-code contract (clig.dev):** zero on success, non-zero on failure, map distinct non-zero codes to distinct failure modes, be consistent across subcommands. The exit-0/2 contract is conventional.
- **Anti-pattern being removed:** inline scripts printing to stdout in-context are hard to test and "firmly integrated in their context of use"; extracting into a first-class subcommand is the idiomatic, unit-testable fix (Rust CLI book, Click `CliRunner`). Direct prior-art support for the heredoc→verb fold.
- **Byte-identical mechanism:** Golden Master / characterization testing (Feathers) — capture current emitted bytes, assert equality post-change. The right harness for the epic's byte-identical invariant.

## Requirements & Constraints

**Applies:**
- **Skill-helper modules (project.md):** the new check must be an atomic `cortex_command` subcommand exposing a `[project.scripts]` console-script entry, matching the existing `cortex-worktree-*` siblings.
- **SKILL.md-to-bin parity (`cortex-check-parity`):** a new/extended verb must wire through an in-scope reference (implement.md) + a test, or it trips W003 "orphan".
- **Dual-source mirror + drift hook:** regenerate the implement.md mirror in the **same commit** (`just build-plugin`; commit canonical+mirror together).
- **ADR-0008 (structural authorization gate):** the `selected`/`suppressed` entry-mode branch is a carried control-flow marker, **not** a runtime-declined `EnterWorktree`; MUST stay structural. ADR-0009 sanctions the CLI-offload mechanism for toolchain-coupled skills (the lifecycle skill qualifies).
- **SP001/SP002 (`cortex-check-skill-path`):** the existing `${CLAUDE_SKILL_DIR}/...` sidecar form is lint-clean and must be preserved.
- **Epic 336 byte-identical-output invariant** (binding on every child): events.log rows must not silently change. For 332 the exposed row is `interactive_worktree_entered` (schema `{schema_version:1, ts, event, feature, worktree_path}`).

**Does NOT apply (explicit):**
- **SKILL.md 500-line size cap** and the **L1 surface ratchet** — both target SKILL.md/frontmatter, **not** reference files. implement.md is a reference file; trimming it is a clarity/token win, not a cap obligation.
- **L201 bare-python prohibition** — the heredoc imports only `subprocess/sys/pathlib` (no `cortex_command` import), so it does **not** trip L201 today. L201's role is **forward-only**: the replacement must not introduce an `import cortex_command` into implement.md.

**Tests that constrain the trim (keep green / update in lockstep):** `test_lifecycle_step_v_ordering.py`, `test_lifecycle_enterworktree_callsites.py`, `test_implement_worktree_interactive_contract.py`, `test_lifecycle_implement_branch_mode.py`, `test_dispatch_choice_resolver.py`, `test_lifecycle_references_resolve.py`, `test_lifecycle_kept_pauses_parity.py` (+ `kept-pauses.md:19`).

## Tradeoffs & Alternatives

The fork is *where the inside-repo check lives* once the heredoc is removed.

- **Option A — postcondition INSIDE `cortex-worktree-create`.** Insert a conditional assertion after worktree.py:201 (`if not cross_repo: <inside-repo helper>`), delete step iv entirely. **Pros:** single insertion covers all create return paths; zero extra subprocess (reuses already-computed `repo`+`worktree_path`); deletes the most prose (heredoc + redundant re-resolve + whole verify step); "the function that chooses the location guarantees its placement"; same-repo-only conditioning falls out of the existing `cross_repo` flag. **Cons / the bet:** changes create's exit surface from 0/2 to 0/1 (a `ValueError` postcondition → CLI wrapper exit 1) — behaviorally identical (halt + surface stderr is how the skill already treats both step-iii and step-iv failures) but **not literally** the "exit 0/2" the ticket Edge names.
- **Option C — new `cortex-worktree-verify` verb.** Thin wrapper over a `worktree.py` helper, preserves exit-0/2 verbatim; heredoc collapses to one line. **Pros:** single responsibility; literal-Edge-compliant; best fit for the thin-wrapper idiom. **Cons:** new `[project.scripts]` entry + module + test; re-resolves work create just did; reintroduces an E101/E103 contract-prose surface (a new verb mention in prose needs argv/flags).
- **Option B — extend `cortex-worktree-precondition`.** **Ruled out:** wrong semantic axis (CWD-relative "am I in a worktree" vs path-validation "is this path under the repo"); hard exit-code collision (precondition exit 2 = usage error vs inside-repo exit 2 = escaped); breaks `test_main_rejects_extra_args`.

**Recommended:** **Option A, but with the inside-repo check extracted as a reusable helper in `worktree.py`** — simplest, cheapest, deletes the most, matches the postcondition idiom and the ticket's stated "fold into create" preference; the helper extraction makes a later pivot to Option C a ~5-line wrapper rather than a re-derivation (durable without gold-plating, no no-create verify path is currently planned). The exit-2→exit-1 collapse is the key bet and is safe today (failures route identically; no test pins the 0/2 surface).

**Picker-options verb (`cortex-lifecycle-picker-options`): do NOT ship in 332.** The option-array string assembly *looks* offloadable, but the value-dense part is the two **probes** — the runtime `command -v` probe and the overnight-rejection sidecar — which gate on what the agent's **own Bash tool** sees (PATH/sandbox/harness execution failure), a signal a child-process verb cannot faithfully reproduce. Low-ROI split that adds a JSON options-array contract for little token savings; belongs in a separate ticket if pursued at all.

## Dependency & Coordination (#330)

- **Event-site inventory:** L196 `interactive_worktree_entered` (already a verb call, natively-supported fields, **not** #330 scope); L228 `batch_dispatch`, L293/L320 `phase_transition` (raw JSON, **#330's** "implement extras"). The three raw sites are in §2/§3/§4 — **disjoint** from 332's §1/§1a region.
- **The epic's "#332 Depends on #330 for its event sites" is over-stated for 332's actual edit region.** L196 needs nothing from #330's `--field` extension. The real relationship is **disjoint-region file-overlap** on the same mirror-backed file — not a logical dependency. **332 can land in any order.**
- **Recommended scope: Option (a)** — trim §1/§1a prose + heredoc→verb, leave L196 byte-identical, leave §2/§3/§4 untouched. Option (b) (route L196 through `--field`) is moot (L196 carries no extra fields) and would violate the epic's scope-split.
- **Byte-identical invariant for 332** reduces to: (1) keep L196 verbatim **and** emitted from inside the worktree CWD (the `EnterWorktree`/cd-shim rooting is load-bearing for `_resolve_user_project_root_from_cwd()`); (2) the heredoc→verb swap must preserve the exit-0/2 contract's **gating of the emit** (exit 2 → halt, don't cd/emit; exit 0 → emit) — else a row fires spuriously or is skipped. The **"staged-path set"** half of the invariant does **not** apply to implement.md (no "Step 2 Commit Lifecycle Artifacts" here — that's complete.md / a #331/#326 concern).
- **Mirror is the reconciliation surface:** disjoint git hunks auto-merge, but the second lander of {330, 332} must run `build-plugin` and commit canonical+mirror together.

## Trim-Safety & Guardrail Preservation

**The ticket's "overnight-pinned headings" guardrail is STALE and wrong for implement.md.** All 5 named headings (`### 1a. Check Criticality`, `### 1b. Competing Plans`, `### 4a. Auto-Apply Requirements Drift`, `### 5. Transition`, `### Step 2 — Commit Lifecycle Artifacts`) live in **plan.md / review.md / complete.md** (pinned by `tests/test_skill_section_citations.py`); none are in implement.md. `overnight/prompts/orchestrator-round.md` cites no implement.md heading. Overnight's `feature_executor.py:71` renders a **different file** (`cortex_command/pipeline/prompts/implement.md`), not this skill reference. The guardrail is a copy-paste from sibling tickets 329–335. **Taking it literally (renaming `### 1a. Interactive Worktree Creation` → `Check Criticality`) would corrupt the file.** implement.md's real headings: `### 1. Pre-Flight Check`, `### 1a. Interactive Worktree Creation (Alternate Path)`, `### 2. Task Dispatch`, `### 3. Rework`, `### 4. Transition`.

**The REAL must-preserve locks (with the test that pins each):**
- **§1a Step-v block** — anchor `**Step v — Auto-enter sequence**`, 4 tokens in order (`_origin_pwd` → `cortex-worktree-precondition` → `EnterWorktree(` → `interactive_worktree_entered`), literal `EnterWorktree skipped: suppressed-picker`, absence of `verify-worktree-auth`; the regex extracts to the next `**`-boundary (`**Fallback —`). → `test_lifecycle_step_v_ordering.py` (incl. `test_step_v_pins_suppressed_picker_skip` — the ADR-0008 structural-gate pin).
- **EnterWorktree call-site proximity** — within ±60 lines of `EnterWorktree(` need the **literal `create_worktree` token** (Python fn name, only at L130) + a precondition token (`show-toplevel`/`git-common-dir`/`EnterWorktree skipped`). → `test_lifecycle_enterworktree_callsites.py`. **Trap:** L130↔L188 is 58/60; removing the heredoc shrinks the gap (safe) **but paraphrasing L130 and dropping the `create_worktree` token breaks the test** — the single most likely silent regression.
- **Sidecar form** — `cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "<msg>" "<root>"` at L81/L119; SP002 catches a dropped `${CLAUDE_SKILL_DIR}/` prefix; **dropping `-s --` breaks arg-passing with NO lint coverage**; `test_overnight_guard_sidecar_called_at_least_twice` requires ≥2 sidecar refs (do not merge the two guards into one).
- **§1/§1a contract** — `### 1. Pre-Flight Check`, `### 1a.`, `**iii.`/`**iv.` markers, `cortex-interactive-lock acquire`, and **gate↔gated same binary** (`command -v cortex-worktree-create` in §1 == `cortex-worktree-create --feature interactive-` in §1a) → `test_implement_worktree_interactive_contract.py`.
- **§1 branch-mode wiring** — `read_branch_mode` + `should_fire_picker` present, invocation before the §1 picker AskUserQuestion, 4 closed-set values within ±10 of `should_fire_picker` → `test_lifecycle_implement_branch_mode.py`.
- **Picker label** — `**Branch selection**` block + worktree-bearing label (the label *is* the ADR-0008 authorization) → `test_lifecycle_picker_label_pins_worktree.py`.
- **kept-pauses parity** — `kept-pauses.md:19` pins `implement.md:50`; bidirectional ±35-line tolerance requires an `AskUserQuestion` ref + a branch-mode marker within ±35 of the pause. The §1 trim is exactly this blast radius — this is a **line-number** lock, not just content; update `kept-pauses.md:19` in the same change.

**Guardrail GAPS with no automated coverage:**
1. **The inside-repo exit-0/2 contract has NO test today** — it exists only as the heredoc; `create_worktree` has no inside-repo postcondition. Folding to a verb requires a **net-new test** (no existing guard to inherit).
2. **`bash -s --` arg passing is unguarded** — silent break if dropped.
3. **The `create_worktree` literal token** is only "guarded" by the ±60 proximity test — one paraphrase from breaking.
4. The stale ticket guardrail itself misleads — the implementer should rewrite that GUARDRAIL line to name the real locks before starting.

## Adversarial Review

**1. Option A's naive helper has a symlink-asymmetry false-positive bug (high-confidence, NEW).** `worktree_path` (worktree.py:201 → `resolve_worktree_root`) is `.resolve()`'d, but `repo` (worktree.py:199 → `_repo_root()` L56) returns `Path(result.stdout.strip())` with **no `.resolve()`**. The original heredoc resolved **both** sides (L150, L159). A naive `worktree_path.relative_to(repo)` reusing create's unresolved `repo` raises `ValueError` ("escapes repo") on any symlinked repo root (macOS `/var/folders`, `/tmp`, symlinked parent) — failing **precisely in the same-repo case it should pass**. **Mitigation: the folded helper must `.resolve()` the repo side too** (converges with the Web agent's canonicalize-both-sides finding).

**2. A live dash/slash path bug sits inside 332's edit region, and Option A as scoped entrenches it (confirmed empirically).** `cortex-worktree-resolve interactive-myslug` → `.../worktrees/interactive-myslug` (real dir); `cortex-worktree-resolve interactive/myslug` → `.../worktrees/interactive/myslug` (phantom nested path). Step iii captures the correct dash path into `$worktree_path` (L127), but step v throws it away and re-resolves the **slash** form at L181/191/201 → `EnterWorktree(phantom)` errors → fallback `cd phantom` also fails. The heredoc (step iv, L142) is the **only** §1a site using the correct dash form. **Deleting the heredoc without re-pointing step v removes the only correct resolution while leaving the bug.** 332's own "route on the verbs' outputs" thesis *fixes* this if step v routes on create's captured `$worktree_path`. → see Open Questions.

**3. "Route on verb outputs" risks silently dropping agent-owned menu mutation (confirmed).** `should_fire_picker` returns only `(bool, reason)` — no option-array. The §1 uncommitted-guard demotion (L59) and runtime-probe hide (L61–73) are agent-Bash-observed mutations the verb cannot reproduce. **First-match-wins subtlety:** in the common case (`branch_mode` unset) `should_fire_picker` returns `branch_mode_unset_or_invalid` and **never reaches its `dirty_tree` branch** — so the prose's dirty-tree menu demotion is the *only* uncommitted-changes warning on the common path. A trim that removes it "because the verb checks `dirty_tree`" loses user-facing behavior with no test catching it. (Confirms the "don't ship picker-options verb" call.)

**Other:** TOCTOU slightly improved by folding (shorter create→check→enter window); no design handles cleanup of a dangling worktree if the postcondition fails after creation (heredoc had the same gap — no regression, but a deliberate decision). Option C's new verb mention must carry argv/flags or trip E101/E103. `worktree_precondition.py:5` ("§1a step v") and `worktree_create_cli.py` docstrings reference implement.md sections — update if sub-steps renumber.

## Open Questions

- **Verb shape — Option A (postcondition in `cortex-worktree-create`) vs Option C (new `cortex-worktree-verify`).** Hinges on whether the ticket Edge "keep the exact inside-repo contract (exit 0/2)" is read **literally** (a standalone 0/2 surface must survive → Option C) or **behaviorally** (halt-on-escape preserved → Option A's exit-0/1 collapse is fine). **Deferred to Spec.** Research recommendation: **Option A with the check extracted as a reusable `worktree.py` helper** (lowest-regret — a pivot to C is then a ~5-line wrapper). The user/spec resolves the literalism at the §4 approval surface.
- **Dash/slash latent bug — fold the fix into 332 or file separately?** The fix (re-point step v's `EnterWorktree`/cd-shim/fallback at create's captured `$worktree_path` + a regression test that the step-v entry path equals create's directory) is squarely in 332's edit region and is the natural consequence of 332's "route on verb outputs" thesis; deleting the heredoc otherwise removes the only correct resolution. **Counter-weight:** epic 336 explicitly keeps correctness bugs (#329, #335) *out* of the offload tickets. **Deferred to Spec** (genuine scope decision). Research recommendation: **fold the step-v re-point into 332** because the heredoc removal is what exposes/entrenches it — but surface both options at approval.
- **Net-new exit-contract test.** The inside-repo exit-0/2 (or exit-0/1, per the verb-shape decision) contract has no test today; whichever option is chosen, a net-new parametrized test (inside-repo→pass; resolver-fail / not-git / `CORTEX_WORKTREE_ROOT`-escape → fail; **with negative controls**) is required, plus a Golden-Master assertion that the `interactive_worktree_entered` row stays byte-identical. **Resolved** — this is a spec acceptance criterion, not an open ambiguity.
- **Ticket guardrail correction.** The 5 "overnight-pinned headings" named in the ticket are not in implement.md. **Resolved** — the spec must replace that guardrail with the real locks enumerated under Trim-Safety; no further investigation needed.

## Considerations Addressed

- **Byte-identical-output invariant (events.log rows + staged-path sets):** Addressed and **scoped down for 332**. The staged-path-set half does **not** apply to implement.md (no commit-artifacts section here — that's complete.md). The events.log half reduces to a single concrete obligation: keep the L196 `interactive_worktree_entered` emission verbatim and emitted from inside the worktree CWD, and preserve the heredoc→verb swap's exit-contract **gating** of that emit so no row fires spuriously or is skipped. The recommended pin is a Golden-Master / round-trip assertion on the `interactive_worktree_entered` row plus a parametrized exit-contract test with negative controls — closing the gap that the ticket's Edges (which pin only the exit-0/2 contract) leave open.
