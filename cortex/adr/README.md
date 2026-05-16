# Architecture Decision Records (ADRs)

This directory holds the project's Architecture Decision Records. ADRs are short, immutable notes that capture a load-bearing design decision, the context that forced it, and the alternatives that were rejected. The format and posture below are inlined here so that skill authors, reviewers, and overnight runs do not need to fetch anything external to apply them.

## Purpose

The purpose of `cortex/adr/` is to give the project a stable record of decisions that are **hard to reverse**, **surprising without context**, and **the result of a real trade-off** — so that future contributors (human or agentic) can act on the decision without re-deriving it, and can challenge it on the original grounds rather than rediscovering them from scratch.

The format is adapted from Matt Pocock's `ADR-FORMAT.md` discovery work; the load-bearing parts (three-criteria gate, frontmatter shape, consumer-rule discipline) are inlined in this README so the policy is self-contained.

**Why prose-only enforcement.** CLAUDE.md:58 reads: *"Prose-only enforcement is appropriate only for guidelines where the cost of occasional deviation is low."* That carve-out applies here, on three grounds:

- **Stray ADRs are recoverable via `status: deprecated`.** An ADR that should not have been written can be marked `status: deprecated` (optionally with `superseded_by:`) without rewriting history or invalidating consumers. The blast radius of a wrongly-emitted ADR is bounded.
- **New ADRs are individually PR-reviewable.** Every new ADR enters via a pull request; reviewers can challenge whether the three-criteria gate was actually met before the file lands on `main`. The gate has a human checkpoint.
- **This README surfaces on PRs touching `cortex/adr/`.** Any PR that adds or modifies a file under `cortex/adr/` will display this README in the GitHub diff view (as a sibling file), so the policy is in front of the reviewer at the exact moment they are evaluating an ADR change. The discipline rule is not buried.

Together, the three properties above keep the cost of occasional deviation low, which is the precondition CLAUDE.md:58 requires before prose-only enforcement is acceptable.

## Three-criteria emission gate

An ADR is emitted only when **all three** of the following hold for the decision in question:

1. **Hard to reverse** — reversing the decision later would require coordinated changes across multiple call sites, data migrations, or external contracts. A decision that can be unwound by editing one file in one PR does not clear this bar.
2. **Surprising without context** — a reasonable contributor encountering the code or configuration for the first time would not predict the decision from the surrounding conventions, and would likely propose changing it back unless they knew why.
3. **Result of a real trade-off** — at least one credible alternative was considered and rejected for stated reasons. A decision with no rejected alternative is a convention, not an ADR.

**All three required.** If any one of the three is missing, the decision does not become an ADR. Write it up as documentation, a code comment, or a backlog ticket instead. The gate is intentionally strict: ADRs are a scarce, high-signal artifact, and dilution erodes their value as a lookup surface.

## Frontmatter convention

Every ADR file (but not this README — see below) begins with a YAML frontmatter block of the following shape:

```yaml
---
status: <proposed|accepted|deprecated|superseded>
superseded_by: NNNN  # optional; required only when status is "superseded"
---
```

Fields:

- `status` — one of `proposed`, `accepted`, `deprecated`, or `superseded`. New ADRs land as `proposed` and promote to `accepted` at PR merge (see promotion gate below). `deprecated` marks an ADR whose decision no longer applies but is preserved for history. `superseded` marks an ADR replaced by a newer one and **must** be paired with `superseded_by: NNNN` pointing at the replacement's four-digit number.
- `superseded_by` — optional; the zero-padded four-digit number of the superseding ADR. Omit unless `status: superseded`.

No `area:` field is defined at v1. Area tagging is intentionally deferred to a backfill ticket; do not invent one ad hoc.

**Promotion gate.** An ADR with `status: proposed` is promoted to `status: accepted` at the moment its PR is merged into `main`. The promotion is a single-field edit and is expected to occur in the same PR that introduces the ADR (so the merged file lands as `accepted`), unless the ADR is deliberately landed as `proposed` to invite further discussion before acceptance.

**This README has no frontmatter.** This file is the policy doc, not an ADR. Only files numbered `NNNN-*.md` under this directory carry frontmatter and count as ADRs.

## No-content-duplication discipline rule

ADRs are the canonical home for the decisions they record. Other documents — `cortex/requirements/project.md`, skill READMEs, spec phases, research notes — **must not** restate the decision body. They link to the ADR by number (e.g., `→ ADR-0001`) and let the ADR carry the substance.

The discipline runs in both directions:

- **Source documents back-pointer to the ADR**, rather than inlining the decision narrative. When a passage of prose elsewhere in the repo would otherwise re-derive an ADR's rationale, replace that passage with a one-line back-pointer.
- **ADRs do not restate context owned by other documents.** An ADR may quote a short fragment of project requirements or a skill contract for grounding, but the bulk of the surrounding context lives in its owning document and is referenced, not copied.

The reason is maintenance cost: duplicated decision text drifts. A single canonical home for each decision keeps drift out of the system and makes "what is the current call?" a one-lookup question.

## Consumer-rule prose

Skills, hooks, and overnight-runner code that touch ADR content fall into three behavioral categories. The three behaviors below are the consumer contract for ADRs:

- **MUST automatic.** A skill or hook **MUST automatic**-ally honor any constraint that an `accepted` ADR encodes when the skill operates inside the scope the ADR governs. If ADR-0002 says the project ships as a CLI plus plugins (no symlink deploy), a release skill must not propose a symlink-deploy path; honoring the ADR is non-optional and requires no human prompt.
- **MUST NOT automatic.** A skill **MUST NOT automatic**-ally treat a `proposed` or `deprecated` ADR as binding. `proposed` ADRs are still under review and may be rejected; `deprecated` ADRs no longer reflect the current decision. Acting on either without human confirmation would propagate stale or unratified guidance into downstream artifacts.
- **SHOULD surface.** A skill **SHOULD surface** the relevant ADR(s) to the user at decision points the ADR speaks to — by linking the ADR number in spec output, plan output, or review output — so the human can confirm the ADR still applies before the work proceeds. Surfacing is the observability hook that makes the other two rules auditable from the approval surface.

Together: automatic compliance for accepted decisions, automatic abstention from non-accepted ones, visible surfacing so the discipline is reviewable.
