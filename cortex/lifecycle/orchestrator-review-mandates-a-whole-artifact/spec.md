# Specification: orchestrator-review-mandates-a-whole-artifact

## Problem Statement

`skills/build/references/orchestrator-review.md` §3 permits exactly one repair for a flagged artifact when no user input is needed: a fresh subagent rewrites the **entire** artifact. For a flag confined to one requirement — a criterion missing its file path, a run count left unquantified — this dispatches a full rewrite of a 200-line spec to fix one line. On 2026-08-03 a wild-light #432 refine session routed two precision flags through §3's *user-input* branch instead, and the second fix rode along on the first. **State the evidence precisely**: what was observed is that the mandated route was not taken. No whole-artifact rewrite was dispatched and no content was lost, so the route's cost is inferred rather than measured, and one of the two flags was genuinely an operator call — a §2 disposition problem this spec does not address (see Non-Requirements). The frequency of confined-flag repairs is **not measurable today and remains so after this change**, because the event that would count them (`orchestrator_dispatch_fix`) was deleted as dead and is not reintroduced.

The rule's stated justification has also rotted, in two incidental steps that nobody decided. It shipped in the initial commit (`428e54ea`) justified by *"a full rewrite maintains internal coherence across sections that cross-reference each other"* — the only rationale that ever justified rewriting the **entire** artifact. `9e42a82f` deleted that sentence in a prose trim. Separately, §3 claims dispatching *"creates an audit trail"*; that was true when it emitted an `orchestrator_dispatch_fix` event, and `239b080b` deleted the event as dead code while leaving the claim standing. No writer for it exists today in `cortex_command/`, `bin/`, `hooks/`, or `claude/`. So the section now asserts a benefit it does not deliver, and has lost the argument that justified its central mandate.

This bounds the blast radius of a repair to the requirements actually flagged — which is what reduces accidental content loss, since a targeted edit does not retype the artifact — makes out-of-scope edits self-declared rather than assumed absent, and restores the rationale that justifies the unbounded branch that remains.

## Phases

- **Phase 1: Correct the rationale** — remove the false audit-trail claim and restore the coherence justification for whole-artifact rewrite. Correct independent of any routing change.
- **Phase 2: Bound the blast radius** — add the confined-flag routing branch and the `changed_beyond_flag` envelope obligation.

## Requirements

1. **The false audit-trail claim is removed.** §3 no longer asserts that dispatching creates an audit trail, because no mechanism produces one. **Acceptance**: `grep -c "creates an audit trail" skills/build/references/orchestrator-review.md` returns `0`. **Phase**: Correct the rationale

2. **The separation-of-concerns clause survives.** Removing the audit-trail claim must not remove the independent rationale that the orchestrator does not hold the pen. **Acceptance**: `grep -c "does not edit phase artifacts directly" skills/build/references/orchestrator-review.md` returns `1`. **Phase**: Correct the rationale

3. **The coherence rationale is restored on the whole-artifact branch.** The unbounded branch is justified by cross-section coherence — the reason deleted by `9e42a82f` — so it is not left resting on anti-anchoring alone, which argues for a *fresh agent* rather than a *full rewrite*. **Acceptance**: `sed -n '/^## 3\. Fix dispatch/,/^## 4\. Escalation/p' skills/build/references/orchestrator-review.md | grep -ci "coheren"` returns ≥ `1`. **Phase**: Correct the rationale

4. **Fix routing branches on a countable test.** §3 routes on how many requirements the flags touch, not on what kind of defect they are. **Acceptance**: `sed -n '/^## 3\. Fix dispatch/,/^## 4\. Escalation/p' skills/build/references/orchestrator-review.md | grep -ci "confined to a single requirement"` returns ≥ `1`; and `grep -Eci "reasoning-level|expression-only|precision-only|defect (class|type)|substantive versus" skills/build/references/orchestrator-review.md` returns `0`. **Phase**: Bound the blast radius

5. **Both branches stay dispatched.** The targeted branch is performed by a dispatched subagent, not by the orchestrator. The escape hatch governs blast radius, never pen-holding. **Acceptance**: `grep -i "confined to a single requirement" skills/build/references/orchestrator-review.md | grep -ci subagent` returns `1` (the branch naming the flag-count condition also names a subagent as its actor); and `awk '/^## 3\. Fix dispatch/{s=1} /^## 4\. Escalation/{s=0} s && /does not edit phase artifacts directly/ && !d {d=NR} s && /→/ && !a {a=NR} END{exit !(d && a && d<a)}' skills/build/references/orchestrator-review.md` exits `0` (within §3, the separation-of-concerns sentence precedes the first branch arrow). **Phase**: Bound the blast radius

6. **The unverifiable preservation clause is replaced by an observable obligation.** `"while preserving all correct existing content"` cannot be checked without diffing the whole artifact; it is replaced by the §7 reporting duty. **Acceptance**: `grep -c "preserving all correct existing content" skills/build/references/orchestrator-review.md` returns `0`. **Phase**: Bound the blast radius

7. **The envelope reports changes beyond the flag.** The fix agent declares what it altered outside the flagged requirement(s), so **out-of-scope edits** become visible instead of assumed absent. Note the bound: the field is self-reported by the fix agent, so it detects deliberate scope leakage, **not** accidental content loss — an agent that silently drops a paragraph does not know it did. What reduces accidental loss is the blast-radius bound itself (R4), since a targeted edit does not retype the artifact. **Acceptance**: `awk '/^```$/{f=!f; next} f' skills/build/references/orchestrator-review.md | grep -c "changed_beyond_flag"` returns ≥ `1` (the fenced envelope block, not merely the file, contains the field). **Phase**: Bound the blast radius

8. **One envelope serves both branches.** A single envelope definition governs targeted and whole-artifact dispatch, so a second format cannot drift from the first. **Acceptance**: observable state — exactly one fenced block containing `verdict:` exists in the file; `grep -c "^verdict: " skills/build/references/orchestrator-review.md` returns `1`. **Phase**: Bound the blast radius

9. **A targeted repair that cannot stay confined does not proceed silently.** If the fix agent finds the repair requires edits outside the flagged requirement(s), it either names them in `changed_beyond_flag` or returns `verdict: failed` for re-dispatch as a whole-artifact rewrite. **Acceptance**: `sed -n '/^## 3\. Fix dispatch/,/^## 4\. Escalation/p' skills/build/references/orchestrator-review.md | grep -c "changed_beyond_flag"` returns ≥ `1`; and `grep -c "verdict: failed" skills/build/references/orchestrator-review.md` returns ≥ `1` (a prose instance distinct from the `verdict: revised | failed` envelope template, establishing both permitted outcomes are stated). This instance must sit **inline, not at column zero**, or it adds a second `^verdict: ` match and breaks R8 — the two are jointly satisfiable only under that placement. **Phase**: Bound the blast radius

10. **The change lands net-neutral-or-smaller with no pin raise.** `skills/build/references/` sits at exactly its 57870-byte pin, and a compliant §3 measures roughly +180 B, so offsetting cuts are mandatory rather than optional. **Acceptance**: `uv run python -m pytest tests/test_reference_size_ratchet.py -q` exits `0`, **and** `git diff --exit-code skills/build/references/size-pin.txt` exits `0`. **Phase**: Bound the blast radius

10a. **The offsetting bytes come from this file's own header, §1 and §2.** No sibling reference file is edited to pay for this change. **Acceptance**: `git diff --name-only HEAD -- skills/build/references/` lists no path other than `skills/build/references/orchestrator-review.md`; and `awk '/^## 3\. Fix dispatch/{exit} {n+=length($0)+1} END{print (n < 1494)}' skills/build/references/orchestrator-review.md` prints `1` (the pre-§3 region shrank from its current 1494 B). **Phase**: Bound the blast radius

10b. **The trim preserves §1's binary-checkable definition intact.** The three clauses are the routing input for every phase gate and for this spec's own acceptance criteria; the trim must not reach them. **Acceptance**: each of `grep -c "(a) a runnable command"`, `grep -c "(b) an observable state"`, and `grep -c '(c) `Interactive/session-dependent:'` against `skills/build/references/orchestrator-review.md` returns `1`. **Phase**: Bound the blast radius

11. **The 2-cycle cap is untouched.** A cheaper repair must not become a licence for more iteration. **Acceptance**: `git diff HEAD -- skills/build/references/orchestrator-review.md` shows no changed line within §4; `grep -c "Max \*\*2 review cycles per phase\*\*" skills/build/references/orchestrator-review.md` returns `1`. **Phase**: Bound the blast radius

12. **The plugin mirror matches the canonical source.** The mirror is regenerated by the pre-commit hook from staged blobs, never hand-edited. **Acceptance**: `diff skills/build/references/orchestrator-review.md plugins/cortex-core/skills/build/references/orchestrator-review.md` produces no output after commit. **Phase**: Bound the blast radius

13. **Routing is identical with no user present.** The user-input branch is unavailable overnight, so the new branch must not become an overnight-only shortcut with different semantics. **Acceptance**: `grep -ci "confined to a single requirement" skills/build/references/orchestrator-review.md` returns ≥ `1` (the branch condition is the flag count, unqualified); and `grep -Eci "overnight|interactive[- ]only" skills/build/references/orchestrator-review.md` returns `0` (no session-dependent qualifier is attached to it). **Phase**: Bound the blast radius

## Non-Requirements

- **§2's verdict scheme is not changed.** Orchestrator-review remains binary Pass/Flag with no Dismiss-with-rationale disposition. `cortex/research/archive/refine-load-epic-context/research.md:92` identified this as a live gap for C3 (deliberate-descope) cases, and adversarial review argued it may be where the friction actually lives. Deliberately out of scope: it is a §2 change with no evidence of its own beyond a prior research note, and folding it in would make this two changes to two sections. **Acknowledged cost of that exclusion**: roughly half the motivating incident is attributable to this gap — one of the two #432 flags was an operator call on the acceptance bar, and Phase 2's branch would not have changed how it was handled, since it already used the in-place path.
- **The §1 review-anchoring finding is recorded, not fixed.** §1 rates the artifact in the main conversation, by the agent that authored it — so the *review* is anchored today while only the *repair* is insulated. Fixing this means dispatching the rating itself, materially larger than this ticket.
- **Event logging is not reintroduced.** R1 deletes a false claim; it does not restore the `orchestrator_dispatch_fix` event, which was removed as dead with no consumers.
- **§1's binary-checkable definition is unchanged.** Research established it describes how a rule is *verified*, not what defect triggered a flag — so it is not a routing input.
- **No new lint or test enforces the routing branch.** Per the enforcement-gates constraint, a gate enters only with named evidence; there is none here.

## Edge Cases

- **Flags spanning two or more requirements**: the whole-artifact branch applies. This is the default, not the exception.
- **A confined repair that would contradict another requirement**: the fix agent must surface it via R9 rather than silently editing both or silently editing neither. Grounded case — `cortex/lifecycle/add-path-hardcoding-parity-gate-to-prevent-cortex-root-drift/spec.md` Req 4 names no fixture path, and the obvious repair falsifies Req 7 in the same spec.
- **A targeted repair that satisfies the rule's form while testing nothing**: a patcher need only make one line pass, whereas a whole-artifact rewriter must re-derive the criterion from its requirement. This risk is **bounded, not eliminated** — §1 re-review rates the repaired criterion against the same rules and a vacuous criterion is "materially weak", flagging again and consuming cycle 2 before escalation. The shipped precedent is `cortex/lifecycle/sweep-provisional-tail-critical-review-cluster/spec.md:45` Req 12, a grep satisfied before any work is done.
- **`changed_beyond_flag` with nothing to report**: the field is present with an explicit empty value, so a silent omission is distinguishable from a genuine none.
- **The header/§1/§2 trim cannot reach 180 B without cutting control flow or §1's definition**: halt and surface rather than raising the pin or reaching into a sibling file. `size-pin.txt` was already raised on 2026-08-03 for lifecycle-id 433; a second raise the same week is the ratchet erosion the pin exists to prevent, and this ticket is framed on reducing cost.
- **Zero flags**: §2 passes and §3 is not entered; the branch is unreachable on a clean review.

## Changes to Existing Behavior

- **MODIFIED** — `skills/build/references/orchestrator-review.md` §3: the no-user-input path gains a second branch keyed on flag confinement; the default whole-artifact branch is retained and re-justified.
- **MODIFIED** — the fix-agent envelope gains `changed_beyond_flag`.
- **REMOVED** — the audit-trail claim (false) and the `"preserving all correct existing content"` clause (unverifiable).
- **ADDED** — the coherence rationale on the whole-artifact branch, restoring text deleted by `9e42a82f`.
- **MODIFIED** — the file's header, §1 and §2 are compressed by roughly 180 B to fund §3's growth under the zero-headroom pin. This is a disclosed consequence of R10, not incidental scope: a compliant §3 cannot be paid for out of §3's own deletions. §1's three-clause binary-checkable definition is protected by R10b; §4 is protected by R11.
- Unchanged: §4, and all five callsites, which propagate a path rather than rule text.

## Expected Net Effect

`cortex/requirements/project.md`'s front-door bar requires an efficiency-framed ticket to state its expected net effect on the surface it claims to shrink. Stated plainly, with the uncertainty intact:

- **Reference prose**: net **zero bytes**. R10 makes this binary and CI-enforced, not an estimate.
- **Repair cost**: one avoided whole-artifact re-emission per confined-flag repair. For a 200-line spec that is roughly the artifact's own token count, once per repair — the saving is real but single-digit-turns, not order-of-magnitude, because `cortex_command/pipeline/dispatch.py`'s 150/200/300 turn ceilings are nowhere near binding.
- **Frequency**: **unknown and unmeasurable**, before or after. No telemetry is added, so this change cannot be evaluated after the fact by counting. That is a deliberate consequence of not reintroducing the deleted event, and it means the ticket's central premise stays unfalsifiable.
- **Net**: the byte claim is verified; the cost claim is directionally sound but unquantified; the frequency claim is unsupported. A reader deciding whether to build Phase 2 should weigh it on the rationale-rot findings and the structural argument, not on a measured saving.

## Technical Constraints

- `skills/build/references/` measures exactly 57870 bytes against a 57870 pin — zero headroom. `scripts/ratchet_refs.py:measure()` sums every regular file except `size-pin.txt`; the plugin mirror is content-hash deduped and does not double-count. Deletions available inside §3 total 73 B (`" and creates an audit trail"` 27 B, `" while preserving all correct existing content"` 46 B). **Measured**: a §3 redraft satisfying R1–R9 and R13 comes to ~1114 B against the current 934 B — roughly **+180 B net**, confirmed by two independent drafts. The shortfall is funded from the file's header + §1 + §2 (currently 1494 B) per R10a, subject to R10b.
- Canonical source is `skills/build/references/orchestrator-review.md` only; `plugins/cortex-core/…` is rebuilt from staged blobs by `.githooks/pre-commit` and must never be staged by hand.
- Consumers (`skills/refine/SKILL.md:72`, `skills/refine/references/specify.md:82`, `skills/build/references/plan.md:80`, `skills/discovery/SKILL.md:31`, `skills/discovery/references/research.md:69`) resolve a path, so none needs editing. Note `skills/build/references/review.md` is **not** a consumer, contrary to the ticket's Integration section.
- Existing surgical-redispatch precedent to follow: `skills/build/references/review.md:33` and `:43` — *"append it in the correct format, modifying nothing else"*.
- Overnight turn ceilings are 150/200/300 (`cortex_command/pipeline/dispatch.py`), so dispatch count is not turn-constrained. (`cortex/requirements/project.md` states these as 15/20/30 and is stale by 10x — out of scope here, worth a separate correction.)
- Editing this file is lifecycle-gated per CLAUDE.md; commits go through `/cortex-core:commit`.

## Open Decisions

None.

## Proposed ADR

None considered. The ADR three-criteria gate in `cortex/adr/README.md` fails at criterion 1 — *"A decision that can be unwound by editing one file in one PR does not clear this bar"* — and this is one file in one PR.
