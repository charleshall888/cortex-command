# Research: What orchestrator-review §3's dispatch mandate protects, and how fix-routing should be scoped

Backlog item: `cortex/backlog/430-orchestrator-review-mandates-a-whole-artifact-rewrite-for-precision-only-flags-so-practitioners-route-around-it.md`
Tier `moderate` / criticality `high`. Angles dispatched: Codebase, Prior Deliberation & Precedent, Adversarial (last).

## Codebase

**The mechanism.** `skills/build/references/orchestrator-review.md` is 2756 bytes, 37 lines, the sole canonical copy; `plugins/cortex-core/skills/build/references/orchestrator-review.md` is a byte-identical auto-regenerated mirror and must never be hand-edited (CLAUDE.md dual-source rule). Structure: §1 Execute (per-rule pass/flag, run in main conversation, defines *binary-checkable*), §2 Handle the verdict (Pass → proceed; Flag → Fix Dispatch or Escalation), §3 Fix dispatch (934 bytes — the section in scope), §4 Escalation (2-cycle cap).

**§3 already contains an in-place branch.** Line 30: *"Rework needing user input (preference decides) → explain the issue, gather input, revise in place."* A second condition would extend an existing pattern, not introduce an unprecedented one. This is also the branch ticket #430 records the wild-light #432 session routing through.

**The audit-trail claim is vestigial — verified, not inferred.** The current file contains no JSONL emit instruction, no `events.log` reference, and no event name anywhere. Repo-wide search for `orchestrator_review` / `orchestrator_dispatch_fix` / `orchestrator_escalate` across `cortex_command/`, `bin/`, `hooks/`, `claude/` returns exactly one hit, and it is a comment, not a writer (`cortex_command/overnight/prompts/orchestrator-round.md:255`). Spot-checks across 192 `cortex/lifecycle/*/events.log` dirs found zero orchestrator events. The only occurrence of these names anywhere is `tests/fixtures/discovery-brief/complex-topic/research.md` — a synthetic fixture that itself marks all three `dead — 0 consumers` against a path (`skills/lifecycle/references/…`) that does not exist in this repo.

By contrast, every *real* "audit trail" in this repo is a durable file written by explicit instruction: `skills/discovery/SKILL.md:16`, `skills/discovery/SKILL.md:50`, `skills/discovery/references/decompose.md:15`. §3's claim corresponds to no file at all. A fix dispatch today leaves no persisted record; the return envelope is transient conversation prose.

**Byte budget — zero headroom, and the figure is direction-dependent.** `skills/build/references/` measures exactly 57870 against a pin of 57870 (`scripts/ratchet_refs.py:measure()` sums all regular files except `size-pin.txt`; the plugin mirror is content-hash deduped and does not double-count). `tests/test_reference_size_ratchet.py` fails on any growth.

Available bytes differ by direction, and this was initially misreported in-session as a single figure:

| Deletion scope | Bytes freed | Available under |
|---|---|---|
| `" and creates an audit trail"` only | 27 | B, C |
| Whole rationale clause after the em-dash | 77 | B, C |
| All of line 19 (stem becomes false if the orchestrator may edit) | 134 | A, D |
| `" while preserving all correct existing content"` | 46 | any |
| §3 briefing prose + envelope block (297 + 88) | 385 | D |

§3 totals 934 bytes, so a direction that collapses the dispatch ceremony lands comfortably net-negative; one that only trims the rationale has 27–77 bytes and will likely need offsetting cuts elsewhere in the directory.

**The proposed binary-checkable boundary anchor leaks — this is a hard negative result.** The candidate test ("the flagged rule is the binary-checkable rule, and the artifact's substance is unchallenged") conflates *how a rule is verified* with *what kind of defect triggered the flag*. Counterexample from `cortex/lifecycle/add-the-triage-board-panel-and/spec.md` item 17: five acceptance claims that were well-formed and fully checkable ("170 of 177 top-level lifecycle dirs", "morning-report flooding", "no standing sweep") turned out to be **factually false** on independent verification — not malformed, not unmeasurable, simply wrong. Item 16 in the same spec shows the ambiguity prospectively: a grep-based criterion can be flagged either for its pattern's wording (expression) or for whether the pattern measures the claimed property at all (reasoning) — same rule, same binary-checkable form, two different flag characters.

**Callsites confirmed, exactly five, all propagating a path and never rule text:** `skills/refine/SKILL.md:72`, `skills/refine/references/specify.md:82`, `skills/build/references/plan.md:80`, `skills/discovery/SKILL.md:31`, `skills/discovery/references/research.md:69`. `skills/build/references/review.md` is **not** a consumer (contra the ticket's Integration section). Blast radius is one file.

**Precedent for targeted repair exists.** `skills/build/references/review.md:33` and `:43` already prescribe targeted re-dispatch — *"read the existing file and append it in the correct format, modifying nothing else"*, *"append it in the §2 format without touching anything else"*. So targeted-vs-full framing is not novel in this harness; what is novel in §3 would be who holds the pen.

## Prior Deliberation & Precedent

**The mandate was never a considered decision.** "Rewrite the ENTIRE artifact… Do not patch individual sections" shipped in the initial commit `428e54ea` at the predecessor path `skills/lifecycle/references/orchestrator-review.md:95-96`, alongside the entire framework. Its only stated rationale was one sentence: *"Fix agents rewrite the full artifact, not section patches. A full rewrite maintains internal coherence across sections that cross-reference each other."* No evidence, no measurement, no proportionality discussion. No ADR governs it — all 34 in `cortex/adr/` were checked, none rule on orchestrator-review, fix dispatch, orchestrator/subagent separation, or artifact authorship. No commit has ever revisited the scope question.

**The rationale mutated, and both erosions were incidental byproducts of unrelated cleanups.** The original §3 carried four rationales; today's carries three, and it is the wrong three:

| Original rationale | Justifies | Status today |
|---|---|---|
| internal coherence across cross-referencing sections | rewriting the **entire** artifact | **deleted** by `9e42a82f` ("Trim orchestrator-review; extract fix-agent template") |
| audit trail **via event logging** (`orchestrator_dispatch_fix` → `events.log`) | dispatching | mechanism **deleted** by `239b080b` ("Remove **dead-event** emission blocks"); the words survived, "via event logging" stripped |
| avoids anchoring to the flawed artifact | using a **fresh agent** | retained |
| separation of concerns | **not the orchestrator** holding the pen | retained |

Net: the only rationale that ever justified rewriting the *entire* artifact is gone from the text, and the only one that was mechanically backed had its mechanism deleted. The two that remain justify *who* repairs, not *how much* they rewrite. The mandate now rests on a strictly weaker argument than the one it shipped with, and nobody decided that — two trim passes did it silently. This is the same decay mode #430 is reporting from the other end.

**Subsequent commits refined the envelope, never the scope.** `f5d746ee` added a one-line report format; `f5ff1ad8` replaced it with the `verdict/files_changed/rationale` YAML envelope; `4fc01480` made the orchestrator absorb the envelope and relay only pass/fail. `9bce456d` made acceptance criteria binary-checkable — a deliberate, well-reasoned change that *generates* the precision-flag class #430 complains about. #430 does not question `9bce456d`; it questions the repair cost once such a flag fires.

**An adjacent gap, already identified and never fixed.** `cortex/research/archive/refine-load-epic-context/research.md:92` (restated at :134 as DR-5) ruled: *"Binary pass/flag + full-rewrite fix-dispatch + 2-cycle cap has no workable disposition for C3 cases — either rewrites the spec away from intentional descope or escalates unnecessarily."* C3 = **deliberate descope**, an intentional authoring move. The critique targets §2's binary verdict scheme, not §3's rewrite scope: orchestrator-review has **no dismiss-with-rationale disposition**, so a defensible authoring choice is either force-rewritten away or escalated. That research explicitly named critical-review's per-objection Apply/Dismiss/Ask as the mechanism that handles it.

**Requirements bearing on cost.** `cortex/requirements/project.md:21`: *"the levers are session length, turn count, and fan-out width."* A fresh dispatch for a one-line repair is one extra turn boundary, one fan-out unit, and a full artifact re-read. `project.md:39` classifies the fix-agent as input-bounded (no turn cap), so it does not trip the cap policy — but the cost lens still applies. `project.md:23` **Deletion bias** puts the burden of proof on *keeping*, and `project.md:25` extends it symmetrically: *"a defense retained without named evidence is complexity too."*

**Retros.** Two mention orchestrator-review friction (`cortex/retros/archive/2026-04-10-2304-refine-065-scope-expansion.md:11` — a structural flaw, appropriately whole-rewrite-sized; and a 2026-04-13 GPG-signing retro, unrelated). No retro records the disproportionate-rewrite complaint before #430. This is its first recorded instance.

**Direction standing.** A: nothing formal blocks it; needs a consistency obligation answering the original coherence rationale. B: extends a live mechanism cheaply, but makes content loss *visible* without making rewrites *cheaper* — it solves verifiability, not the cost #430 names. C: **no prior ruling ever defended the mandate**; choosing C is establishing a first-time ruling, not upholding precedent, and Deletion bias cuts against it.

## Adversarial

> ⚠️ **Coverage gap — this angle returned nothing.** The dispatched adversarial agent idled three times without delivering a report despite three chases. Per the fan-out returned-nothing branch this is recorded as partial coverage. The findings below were produced by the orchestrator directly and carry correspondingly less independence; treat them as unreviewed by a fresh perspective. **The decidability question this angle was primarily dispatched to attack is recorded unresolved in Open Questions.**

**The harness already contains a ratified answer to this exact problem, at a higher-stakes gate.** `skills/critical-review/SKILL.md:54-58` — critical-review runs on the spec for complex + medium/high/critical features, i.e. *more* adversarial and *higher* stakes than orchestrator-review. Its protocol:

> *"work through each objection independently, without waiting for the user: **Apply** when the fix is unambiguous and confidence is high, **Dismiss** when the artifact already addresses it or it misreads a stated constraint, **Ask** when it turns on user preference… Then re-read the artifact in full, **write the updated version** with every Apply incorporated and everything else preserved"*

The orchestrator applies the fixes **itself, in the main context, with no dispatch**. Two gates in the same harness, facing the same problem, resolve it oppositely — and the stricter gate is the one that lets the orchestrator hold the pen. §3 is the outlier, not the norm.

This also dissolves the boundary problem rather than solving it. Critical-review needs no reasoning-vs-expression test because it does not route by flag class at all: every finding gets a disposition, and the artifact is rewritten in full by the agent that holds the context. The context/blast-radius mismatch in §3 — least-informed agent performing the largest edit — does not arise, because a full rewrite is safe precisely when the rewriter has the context.

**Where the anti-anchoring rationale actually lands.** §1 already runs the rating *in the main conversation* ("the artifact is already in context"), by the same agent that authored the artifact. So orchestrator-review's *review* is already anchored today; only its *repair* is insulated. That is backwards — anchoring damages judgment about what is wrong far more than it damages the mechanical act of fixing it. Critical-review gets this right by dispatching the *reviewers* and letting the orchestrator apply. Adopting that shape would move the fresh perspective to where it does work.

**Residual risks not eliminated.** (a) Under any orchestrator-applies model, §1 re-review is performed by the agent that just wrote the fix — though this is already true today, since the orchestrator authored the original and rated it. (b) The overnight path has no user to escalate to; `cortex_command/overnight/prompts/orchestrator-round.md:255` marks the orchestrator-review gate as the *interactive*-context rule, with the morning report as the overnight analog — a change here must state its overnight behavior explicitly. (c) The original coherence rationale is real for cross-referencing artifacts; any direction that permits narrower edits still owes an observable consistency obligation.

## Open Questions

- **Is a reasoning-vs-expression boundary decidable by an agent with no user present?** *Unresolved — the adversarial angle dispatched to attack this returned nothing.* The Codebase angle established that anchoring it on §1's binary-checkable definition **leaks** (`add-the-triage-board-panel-and/spec.md` item 17: well-formed, checkable, factually false). A candidate repair — have the orchestrator classify each flag's character at §1 when it writes the flag, rather than inferring it later — is untested and unattacked. **Note that this question only binds if Spec selects a direction that routes by flag class; the critical-review-alignment direction does not, which is a substantive argument in its favour.** Spec must either resolve it with evidence or select a direction that does not depend on it.
- **Does aligning §2 with critical-review's Apply/Dismiss/Ask fix the C3 gap as a side effect, and is that in scope for #430?** `refine-load-epic-context/research.md:92` identified the missing dismiss-with-rationale disposition as a live defect one level up in the protocol. It is plausibly the *same* fix, but #430 is scoped to §3. Spec must decide whether to take §2 in scope or leave a known gap adjacent to a section it is already editing.
- **What is the overnight behaviour?** `orchestrator-round.md:255` frames the gate as interactive-context; the overnight analog is the morning report. Any direction must state what happens with no user present, since the "rework needing user input → revise in place" branch that #432 routed through is unavailable there.
- **Deferred — not investigated:** whether any consumer repo or external workflow depends on §3's current wording. Out of reach from this repo; judged low risk since all five callsites propagate a path rather than rule text.
