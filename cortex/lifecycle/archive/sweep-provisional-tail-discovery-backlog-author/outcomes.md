# Provisional-tail sweep outcomes — discovery + backlog-author child

Full-roster record of every in-scope candidate for the deferred #357 reconciliation.
The in-scope set is the 43 `(file, id)` pairs re-derived from
`cortex/research/skill-value-scorecard/master_candidates.json` via the Task 1 filter
(`status == "unverified"`, `file` under `skills/discovery/` or `skills/backlog-author/`,
no `overlaps_ticket`, no `reproposal_of`). Both outcomes are recorded — not the refuted
subset alone. This child does NOT touch the ledger; the reconciliation transcribes
`REFUTED → status: verified_refuted` / `survive_votes: 0` and `APPLIED → survives/applied`.

Totals: 31 APPLIED, 12 REFUTED, 43 in-scope.

## skills/discovery/references/orchestrator-review.md

- APPLIED s1 skills/discovery/references/orchestrator-review.md — deleted verbatim-duplicate purpose paragraph (commit: Dedupe discovery orchestrator-review purpose paragraph (#359))
- REFUTED s4 skills/discovery/references/orchestrator-review.md — cross-file MERGE_DEDUP whose destination lifecycle canonical has no Constraints table; extractive-only cannot perform it (pinned by: lifecycle canonical destination lacks a Constraints table)

## skills/backlog-author/SKILL.md

- APPLIED s1 skills/backlog-author/SKILL.md — dropped inputs/outputs/preconditions frontmatter (commit: Trim backlog-author/SKILL.md {s1,s4,s9,s10} provisional-tail candidates)
- APPLIED s4 skills/backlog-author/SKILL.md — deleted ## Body Template dup section (commit: Trim backlog-author/SKILL.md {s1,s4,s9,s10} provisional-tail candidates)
- APPLIED s9 skills/backlog-author/SKILL.md — cut redundant compose contract restatements (commit: Trim backlog-author/SKILL.md {s1,s4,s9,s10} provisional-tail candidates)
- APPLIED s10 skills/backlog-author/SKILL.md — deleted parse/rule-restatement compose steps as pure span deletion (kept step 1 read + step 4 output-contract verbatim) (commit: Rework backlog-author s10 + clarify s5/s7 to extractive-only)
- APPLIED s3 skills/backlog-author/SKILL.md — deleted redundant ## Invocation, merged into ## Subcommand Dispatch (commit: Merge backlog-author {s3+s5} dispatch cluster; drop redundant Invocation)
- APPLIED s7 skills/backlog-author/SKILL.md — deleted redundant 5-question interview enumeration (commit: Trim backlog-author interview enumeration and body-template restatements)
- REFUTED s5 skills/backlog-author/SKILL.md — deleting mode bullets orphans the missing-subcommand AskUserQuestion fallback; extractive-only bars fixing the orphan (pinned by: missing-subcommand AskUserQuestion fallback branch)
- REFUTED s6 skills/backlog-author/SKILL.md — MOVE interview branch to nonexistent references/interview.md; not a span deletion (pinned by: non-extractive MOVE to nonexistent references/interview.md)
- REFUTED s8 skills/backlog-author/SKILL.md — shrink-to-one-sentence is a rewrite; span carries a unique recovery path (pinned by: sole recovery-path sentence not restated elsewhere)

## skills/backlog-author/references/body-template.md

- APPLIED s4 skills/backlog-author/references/body-template.md — dropped ## Integration citation clause (commit: Trim backlog-author interview enumeration and body-template restatements)
- APPLIED s5 skills/backlog-author/references/body-template.md — dropped final ## Edges restatement (commit: Trim backlog-author interview enumeration and body-template restatements)
- APPLIED s6 skills/backlog-author/references/body-template.md — bared ## Touch points heading and dropped restated sole-location sentence (commit: Trim backlog-author interview enumeration and body-template restatements)
- REFUTED s1 skills/backlog-author/references/body-template.md — fix-internal-contradiction is a rewrite; keeping the preamble preserves the citation anchor s4/s5/s6 rely on (pinned by: citation anchor consumed by s4/s5/s6)
- REFUTED s2 skills/backlog-author/references/body-template.md — merge-Why-into-disambiguation is a restructure, not a span deletion (pinned by: non-extractive restructure)
- REFUTED s3 skills/backlog-author/references/body-template.md — confined deletion would drop the Role mechanism-exclusion, not restated elsewhere (pinned by: sole Role mechanism-exclusion sentence)

## skills/discovery/SKILL.md

- APPLIED s2 skills/discovery/SKILL.md — deleted ## Invocation section (commit: Trim discovery SKILL.md {s2,s3} Invocation/Step 1 dupes (#359))
- APPLIED s3 skills/discovery/SKILL.md — deleted procedural If-topic-provided branch (commit: Trim discovery SKILL.md {s2,s3} Invocation/Step 1 dupes (#359))
- APPLIED s4 skills/discovery/SKILL.md — deleted Step 2 backward-compat resume sentence (commit: Trim discovery/SKILL.md {s4,s6} provisional-tail candidates)
- APPLIED s6 skills/discovery/SKILL.md — cut ADR-0009 WHY-clause from sibling-path prose (commit: Trim discovery/SKILL.md {s4,s6} provisional-tail candidates)
- APPLIED s8 skills/discovery/SKILL.md — deleted duplicated split-piece sentence, kept existing §5 pointer (commit: Trim #359 C5 discovery/decompose consolidate-vs-§5 cluster)
- REFUTED s5 skills/discovery/SKILL.md — LAZY_REF move of the R13 re-run block to a new file; bare deletion drops the rare-path recovery contract (pinned by: rare-path R13 re-run recovery contract)
- REFUTED s7b skills/discovery/SKILL.md — MOVE promote-sub-topic mechanics to a new ref file; out of scope and drops mech-pins (pinned by: out-of-scope MOVE dropping mech-pins)

## skills/discovery/references/decompose.md

- APPLIED s3a skills/discovery/references/decompose.md — deleted §2 packaging-vs-mutation restatement (commit: Trim decompose.md {s3a,s3b,s6a} provisional-tail candidates)
- APPLIED s3b skills/discovery/references/decompose.md — deleted §2 recap and halved example bullets (commit: Trim decompose.md {s3a,s3b,s6a} provisional-tail candidates)
- APPLIED s6a skills/discovery/references/decompose.md — deleted §5 intra-group-ordering fold dup and 5th research-untouched restatement (commit: Trim decompose.md {s3a,s3b,s6a} provisional-tail candidates)
- APPLIED s6c2 skills/discovery/references/decompose.md — cut R15 consolidate renumber/re-prompt bookkeeping (commit: Trim #359 C5 discovery/decompose consolidate-vs-§5 cluster)
- APPLIED s6c3 skills/discovery/references/decompose.md — cut R15 split-piece spelled-out reasoning (commit: Trim #359 C5 discovery/decompose consolidate-vs-§5 cluster)
- APPLIED s6d skills/discovery/references/decompose.md — dropped backlog-skill-owned generic routing mechanics, kept 3 ADR-0016 arms (commit: Trim #359 C5 discovery/decompose consolidate-vs-§5 cluster)

## skills/discovery/references/clarify.md

- APPLIED s3 skills/discovery/references/clarify.md — deleted duplicate consumer-rule glossary sentence (commit: Dedup consumer-rule glossary prose from discovery clarify/research)
- REFUTED s5 skills/discovery/references/clarify.md — §4 table→inline-list collapse is a non-extractive restructure; no meaning-preserving pure deletion keeps the dimension names, so the 4-row table is restored (pinned by: extractive-only review)
- APPLIED s7 skills/discovery/references/clarify.md — dropped output-1 worked example as pure deletion; output-3 template paraphrase reverted (four alignment-note bullets restored) per extractive-only review (commit: Rework backlog-author s10 + clarify s5/s7 to extractive-only)
- APPLIED s9 skills/discovery/references/clarify.md — dropped closing Fire-when restatement and bullet-structure spec (commit: Trim clarify.md + research.md non-cluster provisional-tail candidates)
- APPLIED s11 skills/discovery/references/clarify.md — deleted 3-row Constraints Thought/Reality table (commit: Trim clarify.md + research.md non-cluster provisional-tail candidates)
- REFUTED s8 skills/discovery/references/clarify.md — replace/merge is non-extractive and drops the sole mech-pin token ${CLAUDE_SKILL_DIR}/../research/references/fanout.md (pinned by: sole mech-pin token ${CLAUDE_SKILL_DIR}/../research/references/fanout.md)

## skills/discovery/references/research.md

- APPLIED s1 skills/discovery/references/research.md — deleted ToC and duplicated Read-only clause (commit: Trim clarify.md + research.md non-cluster provisional-tail candidates)
- APPLIED s3 skills/discovery/references/research.md — deleted duplicate consumer-rule glossary sentence (commit: Dedup consumer-rule glossary prose from discovery clarify/research)
- APPLIED s6 skills/discovery/references/research.md — dropped mandatory-core trio sentences (commit: Trim clarify.md + research.md non-cluster provisional-tail candidates)
- APPLIED s7 skills/discovery/references/research.md — dropped resolve-failure fallback deferring to fanout.md, verified fanout carries it (commit: Trim clarify.md + research.md non-cluster provisional-tail candidates)
- APPLIED s9 skills/discovery/references/research.md — compressed marker example to one bullet and deleted HTML comment (commit: Trim clarify.md + research.md non-cluster provisional-tail candidates)
- APPLIED s14 skills/discovery/references/research.md — deleted 3rd Signal-formats restatement (commit: Trim clarify.md + research.md non-cluster provisional-tail candidates)
- REFUTED s5 skills/discovery/references/research.md — cutting 'Size it' drops the sole mech-pin token agent_count; the no-drift-clause cut is a restructure (pinned by: sole mech-pin token agent_count)
