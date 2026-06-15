# Research: Add report-only ADR citation auditor (#304)

A report-only `bin/cortex-*` check utility, modeled on the informational `bin/cortex-requirements-parity-audit` (emits findings, never fails a commit), that (1) confirms every ADR reference across the repo resolves to a real `cortex/adr/NNNN-*.md` record, (2) flags numbering gaps, duplicate numbers, and proposed-but-unfiled numbers, and (3) via a `--proposals` sub-mode reconciles specify-phase `### Proposed ADR: <NNNN-slug>` entries against the filed corpus. Folds in one README correction: the area-tagging defer-note at `cortex/adr/README.md:45`.

## Codebase Analysis

### Files that will change

| Purpose | Path | Notes |
|---|---|---|
| New auditor (canonical) | `bin/cortex-adr-citation-audit` | Executable; stdlib-only; model on `bin/cortex-requirements-parity-audit`. Name signals *informational audit* (the `*-audit` family) not a blocking *check* (the `cortex-check-*` family are gates). |
| Mirror (auto-generated) | `plugins/cortex-core/bin/cortex-adr-citation-audit` | NOT hand-written — produced by `just build-plugin` rsync. Commit together with the canonical (drift pre-commit hook + `tests/test_plugin_mirror_parity.py` enforce byte-parity). |
| Justfile recipe | `justfile` (~line 415–417, beside `requirements-parity-audit`) | The recipe body containing `bin/cortex-adr-citation-audit` is *also* the parity-wiring signal (W003). |
| Test file | `tests/test_adr_citation_audit.py` | Model on `tests/test_requirements_parity_audit.py` / `tests/test_check_events_registry.py` — subprocess + `--root <tmp tree>`. |
| README edit | `cortex/adr/README.md:45` | The area-tagging defer-note (see Open Questions: delete vs reword). |
| Smoke-test inventory | `tests/test_phase1_sibling_rewrite_smoke.py:45` | New `bin/cortex-*` scripts must support `--help` exit 0; may need adding to this inventory list. |

### Model auditor shape (`bin/cortex-requirements-parity-audit` — copy this)
- `#!/usr/bin/env python3`, `from __future__ import annotations`, **stdlib-only** (lines 1, 11).
- **log-invocation shim** (lines 13–19): runs before heavy imports — `shutil.which("cortex-log-invocation")` then `subprocess.run([...], check=False, timeout=2)`, swallowing errors to stderr. Copy verbatim (identical block at `cortex-check-events-registry:28–34`).
- **argparse** (lines 308–322): `--root` (default None = cwd). For this auditor add `--proposals` for the sub-mode.
- **No `--staged`/`--audit` split** — single mode + `--root`. (Contrast `cortex-check-events-registry`, which has the two-mode gate.)
- **Output**: JSON to stdout — `print(json.dumps(report, indent=2, sort_keys=True))` (line 331); empty-tree fast path prints zeroed JSON and returns 0 (lines 325–328). Output schema documented in a `# Contract` comment block (lines 29–68).
- **Exit-code discipline**: `return 0` on every path; docstring (line 6) + contract (line 63) state "Informational; never fails the gate. Exit code is 0 regardless." **This is the load-bearing property.**
- **Emits no registry event** — confirmed: `requirements-parity-audit` does not appear in `bin/.events-registry.md`.
- **Discovery is NARROW, not whole-repo**: `iter_review_paths` uses `repo_root.glob("*/review.md")` + an archive glob (lines 249–265), reads with `read_text(encoding="utf-8")` in try/except, extracts via module-level compiled regexes (lines 79–94). (See Adversarial — the whole-repo-scan recommendation diverges from this model.)

### Registry-scanner pattern (`bin/cortex-check-events-registry:473–535`)
The "every reference must back to a real target" loop: load valid targets into a set (`registered = {r.event_name for r in rows}`, line 500); enumerate in-scope files (`gather_scan_files` / staged blob); extract tokens per file via a compiled regex into `(rel, line, name)` tuples; resolve (`if name in registered: continue` else append a finding). The ADR analog: registry = filed ADR numbers/slugs from `cortex/adr/NNNN-*.md`; references = the ADR token grammar (below); report any unresolved.

### Parity wiring (`cortex_command/parity_check.py`, `bin/.parity-exceptions.md`)
- Every deployed `bin/cortex-*` script is in `gather_deployed` (parity_check.py:251–279). No wiring signal → **W003 orphan warning, which fails the commit** unless `--lenient` (lines 791–825, 1687–1694).
- In-scope files = `SCAN_GLOBS` (parity_check.py:69–79): `CLAUDE.md`, `claude/hooks/cortex-*.sh`, `docs/**/*.md`, `hooks/cortex-*.sh`, `justfile`, `cortex/requirements/**/*.md`, `skills/**/*.md`, `tests/**/*.py`, `tests/**/*.sh`. **The plugin mirror is NOT scanned for parity.**
- A valid signal (parity_check.py:584–603): path-qualified `bin/cortex-X`, inline-code `` `cortex-X` ``, fenced token, or shell invocation. Flat table-only mentions are insufficient (R6).
- **Concrete need**: a justfile recipe whose body contains `bin/cortex-adr-citation-audit` (exactly how `requirements-parity-audit:` at justfile:417 wires the model — that recipe is its only non-test wiring). The test file referencing the script in inline code also counts. **Wire it, do not allowlist** (allowlisting a wired script triggers W005).

### Dual-source mirror (`just build-plugin`, `.githooks/pre-commit`)
- `build-plugin` (justfile:585/615): `rsync -a --delete --include='cortex-*' --exclude='*' bin/ "plugins/cortex-core/bin/"`. Mandatory and auto-generated.
- `.githooks/pre-commit` detects a staged `bin/cortex-` source, runs `just build-plugin`, then `git diff --quiet plugins/...` — **drift fails the commit**. Independent CI catch in `tests/test_plugin_mirror_parity.py`.
- **Commit canonical + mirror together** (memory `feedback_drift_hook_shared_checkout_coupling`): on `main`, run build-plugin with the canonical-edit commit.

### ADR corpus + template
- Corpus: `0001`–`0010`, all `^[0-9]{4}-[a-z0-9-]+\.md$`, contiguous, no gaps/dupes today. `README.md` has no frontmatter and is the only non-conforming file (clean exclusion of the README as a *target*). **`0006` is `status: superseded`, `superseded_by: 0008`** — file still present.
- Frontmatter schema (README:29–49): `status: <proposed|accepted|deprecated|superseded>`, optional `superseded_by: NNNN`.
- Proposed-ADR template (`skills/lifecycle/references/specify.md:149–155`): `## Proposed ADR` / default body `None considered.` / commented `### Proposed ADR: <NNNN-slug>` sub-entries. **Mirror copy exists at `plugins/cortex-core/skills/lifecycle/references/specify.md:153`** (double-count risk — see Adversarial).

### Conventions
Stdlib-only python; log-invocation shim verbatim; argparse with `--root` + `--proposals`; `--help` exit 0; JSON-to-stdout + `# Contract` docblock; **exit 0 always**; no events-registry entry; wire via justfile recipe; commit canonical+mirror together; test via subprocess + `--root`. Editing `bin/cortex-*` requires the lifecycle — the README/justfile/test edits ride along in the same lifecycle.

## Web Research

- **The gap is real.** The authoritative ADR tooling catalog (https://adr.github.io/adr-tooling/) confirms **no** listed tool (adr-tools, log4brains, adr-manager, pyadr, adr-log, Backstage ADR plugin, …) does cross-reference resolution, broken-link detection, or numbering gap/dup detection — they focus on *creation/rendering*, not integrity auditing. The proposed auditor fills a genuine niche.
- **adr-tools (npryce)** sets the conventions to parse (zero-padded `NNNN`, `NNNN-kebab.md`, `→ ADR-NNN` supersession back-refs). Its resolver (`_adr_file` → `adr-list | grep | head -1`) is an **anti-pattern**: silently picks first-of-multiple and returns empty on no-match. Do the opposite — surface ambiguous and no-match as findings. Concurrent-PR duplicate-number breakage is documented (npryce#102, MADR#28) — real-world evidence that duplicate detection catches an actual failure mode.
- **lychee** (link checker): borrow structured output (`--format json/junit`), `--dump` (list extracted tokens without checking — a useful debug mode), and the `--exclude`/`.lycheeignore`/`--exclude-path` allowlist triad. Its exit `2` on "links failed" is exactly what a report-only tool must **not** do.
- **Sphinx** is the best conceptual model: build a registry of canonical targets, extract reference tokens, resolve against the registry, report unresolved. `nitpicky` (`-n`, escalated to error by `-W`) is the clean "same engine, severity is a flag" design — report-only by default, blocking opt-in. `nitpick_ignore`/`nitpick_ignore_regex` is the allowlist for known-not-a-reference tokens.
- **Token extraction best practice**: prefer an AST/structural pass to a flat regex; strip code spans/fences first (lookalike tokens in code are the dominant false-positive source); word-boundary anchoring + lookaround; normalize all variants to one canonical key before lookup; distinguish document-local labels from cross-document references (a separate namespace, per Sphinx).
- **Report-only design**: always exit 0, severity-driven output. The "warnings get ignored" anti-pattern (ESLint community) is the main risk; mitigate with (a) structured output for PR annotation and (b) a clean future `--strict` escalation path. Report-only is the correct *initial* stance for a repo with pre-existing legacy references.
- **Gap/dup detection** is mature in audit/forensics (sequence + uniqueness checks). The "unaccounted gap" framing fits report-only: a gap is not necessarily an error, so surface it as informational.

## Requirements & Constraints

- **SKILL.md-to-bin parity** (`project.md:33`): blocking W003 gate — the new script must wire through an in-scope reference (justfile recipe is the cleanest). Not an exceptions-table entry (ticket commits to the wiring path).
- **Events-registry** (`project.md:35`): new events register in `bin/.events-registry.md`. The model auditor emits none → this auditor likely emits none → the ticket's "any event it emits registers" (304:26,41) is satisfied **vacuously**. Confirm no event is emitted rather than asserting no interaction.
- **Complexity must earn its place / Solution horizon** (`project.md:19,21`; CLAUDE.md:63): backs the ticket's cut of the next-free-number helper (304:32 — "solves a problem that has not occurred"). **Tension** (see Adversarial): the gap/dup *detectors* are the read-side twin of that cut; "current knowledge, not prediction" cuts both ways.
- **`cortex/adr/README.md` is the ratified bounding policy**:
  - Prose-only enforcement rationale (README:11–17) → **the auditor must be report-only**, never a blocking gate (304 Edge, line 30). Out of scope to make it blocking unless a maintainer overturns the README.
  - Consumer rules (README:64–70): **MUST NOT treat a `proposed` or `deprecated` ADR as binding.** The `--proposals` sub-mode reads proposed entries — it must operate **surface-only** (flag, never auto-file, never block). This is the **SHOULD surface** behavior.
  - Bounded to reference-resolution + numbering (304 Edge line 29): **does NOT validate content, status transitions, or supersession chains** — those stay human-reviewed. (Bears on the supersession question below: surfacing supersession is out of scope per the ticket.)
  - Area-tagging defer-note (README:45): *"No `area:` field is defined at v1. Area tagging is intentionally deferred to a backfill ticket; do not invent one ad hoc."* **Verified: the `area:` field has no consumer anywhere in `cortex_command/` or `tests/`** — the only occurrence of the concept is this note. Epic 303 records the backfill as deliberately "Not filed… folded into the auditor as a README correction."
- **CLAUDE.md**: dual-source bin-mirror rule (commit canonical+mirror together); MUST-escalation policy (any SKILL.md/doc wording defaults to soft positive-routing, not MUST); prescribe What/Why not How (spec should state what is checked + output shape, not procedure).
- **L201 / SP001-2**: target *skill corpus files*, **not** the bin script's internals. But the in-scope reference (if it lives in a SKILL.md) must invoke the auditor as a console-script / path, not via a bare-Python import, and must use an absolute (not bare-relative) path.
- **Requirements scope**: tag `cortex-core-tooling-gaps` matches no area doc; governing surfaces are `project.md`, `cortex/adr/README.md`, `CLAUDE.md`. (`cortex/requirements/glossary.md` listed in Global Context is **absent on disk** — recorded as skipped.)

## Tradeoffs & Alternatives

- **Structural home — RECOMMEND (A) standalone stdlib-only `bin/` script** (the ticket's suggestion, validated). Both existing report-only auditors are standalone, stdlib-only, not `[project.scripts]`. Rejected: (B) extending `cortex-check-events-registry` (it's a blocking gate; posture mismatch); (C) a `cortex_command/` console-script module (that convention is for skill-dispatched helpers, not operator-on-demand audits; it imports the wheel-vs-working-tree invocation tax for no benefit).
- **Token strategy — RECOMMEND STRICT resolution** (canonical zero-padded `ADR-NNNN` + `cortex/adr/NNNN[-slug]` path forms) over BROAD-with-exclusion-list (the exclusion list is an ongoing maintenance burden against a moving corpus). A separate "non-canonical-form advisory" (reporting `ADR 0007` space-form etc. as a style finding without resolving) is the **lowest-value slice** — only one archived file's worth of evidence — and is the first thing to cut at the value gate.
- **`--proposals` packaging — RECOMMEND a single auditor with a `--proposals` flag** (shares the one expensive thing: the `cortex/adr/` index). Rejected two-tools (duplicates index/parse logic) and always-on (couples two different scan surfaces with different output shapes). Report-only means the tool cannot know intent — classify mechanically (RESOLVED / unresolved) and let a human adjudicate; never assert negligence. (See Adversarial for the immutability problem with this sub-mode.)
- **Scope/value MVP**: proven friction = dangling-reference resolution (the consumer-repo incident, 304 Why) + proposals reconciliation (3 real non-resolving entries today). Bundled near-zero-cost = README:45 fix. Contested = gap/dup detectors (no occurrence today) and the non-canonical advisory (cut candidate).

## Token-Grammar & Reference-Resolution Design

**The 4-digit zero-padding discriminator is the load-bearing insight.** Requiring exactly `[0-9]{4}` for the prefix/space/path forms cleanly separates canonical references (always 4-digit — every filed ADR is `NNNN-slug.md`) from the document-local `ADR-1/2/3` proposal labels (always 1 digit) **without any directory exclusion**. This matters because `ADR-1/2/3` (56 occurrences) appear not only in `cortex/lifecycle/archive/add-cortex-init-…/{spec,plan}.md` but also in **shipped code**: `cortex_command/init/settings_merge.py` (lines 6,8,14,219,430), `handler.py` (1,6,425), `tests/test_settings_merge.py` (13×) — so directory-based exclusion would NOT have solved the false-positive, but the digit-count rule does, directory-independently.

Recommended regexes (case-sensitive `ADR`, case-insensitive `adr/` path):
```
# Prefix + space + bracketed canonical (4-digit ONLY):
(?<![0-9A-Za-z])\[?ADR[- ](?P<num>[0-9]{4})\]?(?![0-9A-Za-z])
# Path form (optional slug):
(?<![0-9A-Za-z])adr/(?P<num>[0-9]{4})(?:-(?P<slug>[a-z0-9-]+?))?(?=\.md|[^a-z0-9-]|$)
# Proposals sub-mode (lifecycle spec.md only), captured separately:
^###\s+Proposed ADR:\s+(?P<entry>NNNN-\S+|[0-9]{4}-\S+|None)\s*$
```
> NOTE: the right-side boundary was tightened to `(?![0-9A-Za-z])` per Adversarial — the originally-proposed `(?![0-9])` lets `ADR-0001x` match (forbids only a trailing digit, not a letter).

**Resolution** = numeric-prefix match for slug-less forms; **exact `NNNN-slug` filename match** for path-with-slug and proposals entries (a slug mismatch is a meaningful signal, not noise).

**Per-shape classification** (verified against the real corpus):

| Token | Class | Why |
|---|---|---|
| `ADR-0003`, `[ADR-0006]`, `ADR 0007` | RESOLVE by prefix | 4-digit; all in 0001–0010 |
| `adr/0004-multi-step-…` | RESOLVE by prefix+slug | slug matches filed file |
| `adr/0009` (bare path) | RESOLVE by prefix | no slug to check |
| `ADR-1`, `ADR-2`, `ADR-3` | IGNORE | 1 digit → fails `[0-9]{4}`; doc-local labels |
| `ADR-000N` | IGNORE | 3 digits + literal `N` |
| `NNNN-slug` placeholder | EXCLUDE | matched only by the proposals regex, routed to skip |

**Proposals sub-mode** — scan `### Proposed ADR: <entry>` in lifecycle `*/spec.md` (12 real entries). `None`/`NNNN-…` → skip. `NNNN-slug` → exact-match `cortex/adr/<NNNN-slug>.md`; no match → flag. Verified resolving (5): `0006-cortex-init-consumer-…`, `0007-decompose-groups-…`, `0010-task-id-…`, `0005-repo-relative-worktree-placement`, `0009-skill-path-…`. Verified non-resolving (3): `0005-canonical-adhoc-scratch-directory`, `0007-scheduled-fire-detach-via-start-new-session`, `0010-lifecycle-state-reads-tolerate-torn-lines-and-fail-safe` — each is a number whose slot was filed under a *different* slug. Exact-slug matching is required to detect them (prefix-only would falsely resolve all three). The `NNNN-multi-step-…` placeholder entry was in fact filed as `0004-multi-step-…` — a fuzzy-slug hint can avoid misreporting it as unfiled.

## Adversarial Review

The following are confirmed problems with the naive synthesis; several reshape the design.

1. **Whole-repo scan contradicts the cited model.** `cortex-requirements-parity-audit` globs narrow named paths (`*/review.md` + archive), not a `.md/.py/.sh` walk. A whole-repo walk hits **12,502 files** including generated/vendored content.
2. **Mirror double-counting is REAL and confirmed.** `plugins/cortex-core/**` holds exact mirror copies — e.g. both `skills/lifecycle/references/specify.md:153` and `plugins/cortex-core/skills/lifecycle/references/specify.md:153` carry `### Proposed ADR: <NNNN-slug>`. A whole-repo scan double-counts every canonical reference and proposed-ADR entry. **The mirror tree must be excluded from the scan.**
3. **Self-reference / bootstrap.** The auditor's own test fixtures, plus this lifecycle's `spec.md`/`research.md` and the auditor's contract docblock, contain `ADR-NNNN`-shaped tokens. `tests/test_lifecycle_step_v_ordering.py` and `tests/test_create_worktree_bypass.py` **already** contain such tokens. Fixtures must live in an excluded path (e.g. `tests/fixtures/cortex-adr-citation-audit/`) by construction.
4. **README example refs as sources.** `cortex/adr/README.md:53` (`→ ADR-0001`) and `:66` ("If ADR-0002 says…") are illustrative, not citations. The filename test excludes README as a *target*, not as a *source* of tokens. They resolve today (so no false finding), but are noise and would read as dangling if 0001/0002 were ever renamed.
5. **Supersession is undefined.** `0006` is superseded (122 refs). Resolution rule "prefix-match against existing file" resolves them (file present). But: should refs to a superseded ADR be clean, or surfaced as stale? And the gap detector encodes "numbers are never retired" — a future deliberate deletion of a superseded file would trip a false "gap." (Per ticket Edge line 29, supersession-chain validation is **out of scope** — so refs to a superseded-but-present ADR should simply resolve; see Open Questions.)
6. **`--proposals` permanent-noise.** The 3 non-resolving entries are **renumbered-during-review proposals** (correctly filed under a different final number), living in **immutable** spec.md history. Every run re-flags the same 3 forever — the "warnings that can never be cleared" anti-pattern. "Number collision" is the wrong label. The fuzzy-slug hint does not help (different decisions, not renames).
7. **README:45 — the ticket says DELETE, three times.** Edges (line 33): "the broken promise is **removed**"; Touch points (line 41): "the area-tagging defer-note **to delete**"; epic 303: "**deleting** the README's never-honored… defer-note." The tradeoffs agent's "reword" was a unilateral scope expansion. The "don't invent `area:` ad hoc" guardrail is entangled in the same sentence as the broken promise — surface the entanglement as a maintainer decision; default to the mandate (delete).
8. **`.py` string-literal matches**: scanning `.py` risks matching `ADR-NNNN` inside example/docstring string literals that are not references.

**Recommended mitigations**: scope the scan (exclude `plugins/cortex-core/**`, `tests/fixtures/**`, the auditor's own files, `.git`); isolate fixtures by construction; tighten the right-side regex boundary; document supersession semantics (resolve clean per ticket scope); reconsider `--proposals` against immutability (reconcile only active/non-archived lifecycles, or add a suppression/acknowledgement mechanism, or one-time-informational); honor the delete mandate for README:45.

## Open Questions

1. **README:45 — delete vs reword.** *Deferred: resolved in Spec by asking the user.* The ticket and epic say "delete" three times (the authorized default), but the "do not invent `area:` ad hoc" guardrail is entangled in the same sentence as the never-filed-backfill promise. Spec should confirm: delete the whole note (mandate), or delete only the broken-promise clause and keep the guardrail. Research recommendation: default to delete per the explicit mandate; offer keep-the-guardrail as the alternative.

2. **`--proposals` sub-mode vs immutability — keep, reshape, or cut.** *Deferred: resolved in Spec by asking the user.* The 3 non-resolving entries are immutable historical artifacts; a naive sub-mode re-flags them every run forever (ignored-warning anti-pattern). Options for Spec: (a) reconcile only **active (non-archived)** lifecycle spec.md, treating archived proposals as historical; (b) add a suppression/acknowledgement file; (c) drop the sub-mode. Research recommendation: (a) — it preserves the proven forward-looking value (catch a *new* lifecycle that negotiates an ADR and never files it) without permanent noise from settled history.

3. **Gap/duplicate detectors — keep or cut (value-earns-place).** *Deferred: resolved at the Spec §4 complexity/value gate.* The filed corpus is contiguous 0001–0010 with no gap/dup; the detectors guard a not-yet-occurred condition and are the read-side twin of the cut next-free-number helper. Tradeoffs argues near-zero marginal cost over the required index; Adversarial argues "current knowledge, not prediction" cuts them. The §4 gate is the designated home for this scope decision.

4. **Scan scope** — *Resolved.* Do NOT whole-repo scan. Mirror the model auditor's posture: scan source trees only, **excluding** `plugins/cortex-core/**` (generated mirror — double-counts), `tests/fixtures/**` and the auditor's own files (self-reference), and `.git`. Whether to include `.py`/`.sh` at all (vs `.md`-only) is an implementation choice for the plan; `.py` string-literal example tokens are a known minor false-positive source.

5. **Supersession semantics** — *Resolved.* Per ticket Edge line 29 (supersession-chain validation is out of scope), a reference to a superseded-but-present ADR (0006) **resolves cleanly**. The gap detector keys on file presence, not status, so a superseded-but-present file is not a gap. Surfacing "resolves to a superseded ADR" as a separate advisory is out of scope for this ticket.

6. **Regex right-boundary** — *Resolved.* Use `(?![0-9A-Za-z])` (not `(?![0-9])`) so `ADR-0001x` does not match.

7. **Auditor name** — *Resolved.* `cortex-adr-citation-audit` (the informational `*-audit` family, matching the model `cortex-requirements-parity-audit`), not the `cortex-check-*` blocking-gate family.

8. **Events registry** — *Resolved.* The auditor emits no event (matches the model); no `bin/.events-registry.md` entry needed. The ticket's "any event it emits registers" is satisfied vacuously.
