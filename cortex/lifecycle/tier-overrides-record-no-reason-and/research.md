# Research: Give `--tier-reason` its first caller without forking the clause vocabulary

**Clarified intent** — Append `--tier-reason "{tag}: {why}"` to `skills/refine/SKILL.md` Step 4's `reconcile-clarify` invocation using the four already-shipped clause tags, and fix the two defects that become reachable when it ships: the `or` short-circuit at `cortex_command/refine.py:353`, and the `is not None` emit guard that lets an empty reason be written and then counted as absent.

**Tier** moderate · **Criticality** high · **Requirements alignment** partial

## Scoping note — this is deliberately narrower than ticket #471

#471 as filed asks for a **§5.2-derived tier clause vocabulary**, and its Edges reject reuse explicitly: *"Reopening it needs the §5.2-derived set, not a second free-text field."* That fork was **declined by the user** after a Clarify critic pass, in favour of shipping the caller plus the defect fixes first. Both the Requirements and Adversarial angles independently flagged the divergence; it is a decision, not an oversight.

The sequencing rationale: there is **zero production evidence** that wiring a reason flag into skill prose causes anyone to fill it. `--criticality-reason`'s wiring shipped in `v4.6.0`, tagged `2026-08-07T17:23:31Z`, and every `gate=clarify_reconcile` row in both corpora predates it. Designing a second vocabulary before the first mechanism has executed once would be building on an untested assumption. This slice generates that evidence at the cost of one prose line and three code lines.

**This does not close #471.** A tier author reaching for `design-fork:` is still rejected. See Open Question 1 for the caveat that must travel with the resulting data.

## Corrections to the ticket body

Re-measured today with ADR-0036's recipe across both corpora, per the executable-claims rule:

| Ticket claim | Status |
|---|---|
| 54 / 99 reason-less `complexity_override` rows | cortex-command 54 ✓; wild-light now **103** (corpus grew) |
| 72 / 79 reason-less `criticality_override` rows | cortex-command 72 ✓; wild-light now **82** |
| "the manual-verb path … fills at 39% (21 of 54 rows)" | **Wrong for this axis.** Tier manual fill is 9/101 + 13/88 = **22/189 = 11.6%**. The contrast stat that makes the intervention look like it pays is off by >3x against the relevant population. |
| "`criticality_override` (closed by #452)" | **Unsupported.** The mechanism has had zero exercised opportunities (see above). 0% fill measures a window in which it could not have applied. |
| "ADR-0036's re-open trigger … Tier reasoning is the evidence that decision will be made against" | **Inference, not text.** The trigger is *"when the `tier == complex` share falls materially, or when the criticality-only cell exceeds 10%"* — both computable from `from`/`to` alone, no reason tags. §Decision's data requirement is scoped by "that axis" to **criticality**. |
| "contiguous-substring pins in `tests/test_refine_reconcile_clarify.py:333-339`" | Actual pins are at **`:357-368`**. `:333-339` is the §3b state-field assertion block. |
| "unreachable today (zero callers on `--tier-reason`)" | Reachable by hand — the ticket itself says "tested by hand," and #452's review records running it. Only *skill-prose* callers are zero. |
| Rename ruled out as "cosmetics" | #452's review called it *"a deliberate rename sweep, not a revert"* — a ratified-glossary mismatch. Still out of scope, but on accurate grounds. |

## Codebase

### The three edits

**1. `cortex_command/refine.py:353-356`** — de-short-circuit. Verified by execution: with both flags carrying bad tags, only the tier diagnostic prints; swapping which is bad flips which single message appears, never both.

```python
tier_ok = _reason_clause_ok("--tier-reason", tier_reason)
criticality_ok = _reason_clause_ok("--criticality-reason", criticality_reason)
if not tier_ok or not criticality_ok:
    return 2
```

`_reason_clause_ok` already prints to stderr and returns a bool, so this is pure de-short-circuiting — no signature change.

**2. `cortex_command/refine.py:404` and the symmetric criticality guard at `:420-424`** — `is not None` → truthiness. Verified by execution that **`--criticality-reason ""` already writes `"reason": ""` on shipped code** — the bug is not tier-specific and is already live. `_reason_clause_ok` accepts `""` (no colon → no tag claimed), so only the emit guard controls whether the key lands, and an empty string is falsy under ADR-0036's tally: such a row is counted as reason-less by the very tally the flag exists to populate.

Fits the module: `refine.py` overwhelmingly favours plain truthiness (9+ instances), reserving `is not None` for `choices=`-constrained flags where `""` can never occur.

**3. `skills/refine/SKILL.md:69-70`** — append to **both** arms, after `--criticality-reason`. A Context A tier reason justifies the same Clarify assessment as Context B's, replayed through the Step 2 frontmatter write-back rather than passed inline; there is no basis to give one arm the flag and withhold it from the other.

### Patterns to follow

`_reason_clause_ok` (`:299-320`) and `_UNSAFE_SLUG_MSG` (`:37-39`, used at `:344-346`) both follow "print one formatted line to stderr, return 2" — the short-circuit fix keeps that shape.

### Out of scope, with cost stated

`lifecycle_event.py`'s `complexity-override --reason` is a second, entirely unvalidated tier-reason writer (declared plain `_STR` at `:320-323`), holding 24 free-prose rows across both corpora. Validating it means either a per-field validator hook or a branch in `_emit_subcommand`, a generic dispatcher shared by every event kind — a separately-sized change. Past rows are unaffected either way (validation runs at write time). See Open Question 3.

## Requirements & Constraints

- **`project.md:64` does not fire.** Its co-edit trigger is *"adding a tag"*, which this does not do. Had the #471 fork been built, all three sites — including ADR-0036 — would be edited.
- **Wheel-before-prose is already satisfied.** Both flags landed in `2d8e2575` (2026-08-07T10:49:19-04:00), confirmed an ancestor of `v4.6.0`. No version floor, no wheel bump. `PROTOCOL_VERSION` is not implicated — `refine.py` contains no protocol references; that machinery governs the served `next`/`advance` loop only.
- **ADR-0036 needs neither amendment nor successor.** Its §Decision data requirement is criticality-scoped by its own text; its re-open trigger needs no reason tags; and its "Reading the clause distribution" section already documents this flag as a corpus-reading caveat.
- **Deletion-bias discharge requires the test, not the prose.** `project.md:23` demands *"a consumer that turns a build or gate red when the surface is removed — not a report-only or manually-invoked script."* Skill prose is not executed in CI: delete `--tier-reason` and the SKILL.md line silently references a flag that no longer exists until someone runs the skill interactively. **A functional verb test asserting the emitted `reason` field is what discharges the presumption**; the prose caller is what gives the surface a purpose. Both are required.
- **Budgets are not implicated.** `skills/refine/SKILL.md` is 94/500 lines. The L1 ratchet measures frontmatter only (568B against a 624B budget). `skills/refine/references/` is at **zero** ratchet headroom (20568/20568) but is not touched — `enumerate_reference_dirs` globs `skills/*/references` and never measures `SKILL.md`.
- **Gates on landing.** `skills/` is lifecycle-gated (this lifecycle satisfies it); `cortex_command/refine.py` is not. The `plugins/cortex-core/` mirror is rebuilt from the staged blob by the pre-commit hook — never hand-stage it. Commit via `/cortex-core:commit`.

## Adversarial

**The four tags genuinely do not fit the tier axis.** I classified all 24 existing free-prose tier reasons against `{reversibility, exposure, consequence, other}`:

- **~12 of 24 land on `other`.** Tier's defining language — "competing designs", "a precedent others follow", "whether the next tier down was considered" — has no corresponding tag. At least four reasons literally say *"design judgment calls between competing approaches"* or *"design fork"*, the single most common real pattern, and no tag names it.
- **~9 of 24 land on `exposure`, coincidentally.** Tier authors write "touches shared infrastructure" to describe design-uncertainty scope, not the downstream-breakage risk `exposure` means in §5.3. An author reaching for the closest-sounding tag is pattern-matching to the only options available, not self-classifying accurately.
- `reversibility` and `consequence` each take one forced, ambiguous hit.

Expect a corpus that is roughly half `other` and 40% coincidental-`exposure`. **Reading that as "a tier-specific fork isn't needed" would be exactly backwards** — the supportable read is the opposite. This caveat must travel with the data.

**A comment becomes false on landing.** `refine.py:399-404` justifies the current guard by claiming parity: *"omission drops the key entirely rather than writing a null, matching that module's optional-field handling."* `lifecycle_event.py:364` uses the identical `is not None` guard and is out of scope, so after this lands `reconcile-clarify --criticality-reason ""` omits the key while `cortex-lifecycle-event criticality-override --reason ""` still writes `""`. Fix the comment in the same diff. No reader observes the difference today — dashboard, report, and overnight readers all use `.get()`/truthy access, not `"reason" in row` — so this is latent inconsistency, not an active bug.

**The noop silent drop was never actually decided for this case.** Validation of both reasons happens unconditionally up front, but each reason only reaches a row inside its own rank-comparison block; a reason for an already-ranked field is never referenced again — no row, no stderr, nothing in the `noop` payload. The R3 guard is well-justified for *field* state, but it was written when no caller supplied reason text. Calling the drop "intentional" retroactively assigns a decision nobody made for this case. Measured: **24/78 (cortex-command) and 14/117 (wild-light) lifecycles fire a criticality row with no tier row at this gate** — so once Step 4 composes a tier reason on every invocation, that is the share of calls where the author pays the composition cost and gets nothing, in the same invocation that writes the sibling reason successfully, with no signal distinguishing them. This biases the very fill data the change exists to collect.

**No existing test exercises both flags bad simultaneously**, so the short-circuit fix is safe against the suite — but without a new test asserting both stderr messages, a future refactor can silently reintroduce it.

## Open Questions

1. **Will the resulting clause distribution be interpretable?** — **Deferred with rationale.** Not resolvable before the data exists; that is the point of the slice. Mitigation is carried into the spec instead: the commit body states an explicit re-measure trigger (ADR-0036's own pattern), and records that a distribution dominated by `other` is evidence *for* a tier-specific vocabulary, not against it. Without that caveat a null result reads as a positive one.

2. **Should the noop arm emit a diagnostic when it discards a supplied reason?** — **Resolved: yes, in scope.** Both core angles waved this off as documented-intentional; the Adversarial angle showed that documentation was written for a zero-caller flag and does not bind the case this change creates. A one-line stderr note on noop-with-supplied-reason is cheap, needs no vocabulary fork, and directly protects the fill data from a ~20% silent-loss channel.

3. **Does `lifecycle_event.py`'s unvalidated `--reason` come in scope?** — **Resolved: no, deferred.** It requires a validator hook in a dispatcher shared by every event kind, and #452's plan already frames it as an accepted gap. It is the correct subject of a follow-up ticket, together with the `is not None` parity noted above.

4. **How is the SKILL.md edit tested without violating the no-prose-pins convention?** — **Resolved.** The two angles contradicted; `docs/policies.md:43` settles it: existing pins *"hold no standing … do not cite an existing pin as precedent for a new one."* So do **not** extend the pins at `:357-368`. Appending the flag after them leaves them matching, since they are prefix substrings. Add a separate bare-existence assertion (`assert "--tier-reason" in body`) with a docstring naming the silent failure — permitted by `CLAUDE.md`'s machine-token carve-out, since the flag defaults to `None` and its absence surfaces nowhere. Functional verb tests are ungoverned by the rule and are what discharges deletion-bias.
