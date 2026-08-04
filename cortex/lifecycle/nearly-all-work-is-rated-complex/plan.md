# Plan: nearly-all-work-is-rated-complex

## Overview

Two prose edits in `skills/refine/references/`: delete the critic's optional tier-calibration clause, and add a next-tier-down statement to `clarify.md` §5's Complexity item. The spec's phase-ordering constraint ("both land together or neither does") is satisfied by landing both in **one commit**, which also means the reference-size ratchet only ever observes the final combined state — so the two edits are order-independent as *edits* and can run in parallel, with ordering enforced at the commit boundary instead.

## Outline

### Phase 1: Land both prose edits (tasks: 1, 2)
**Goal**: Canonical prose reflects both spec phases — calibration removed from the critic, downward consideration created by §5 itself.
**Checkpoint**: Both acceptance greps pass against the canonical files; nothing committed yet.

### Phase 2: Re-measure, ratchet, verify, commit (tasks: 3)
**Goal**: Confirm the byte budget against the tree as it actually stands, lower the pin, prove the suite green, and land both edits atomically.
**Checkpoint**: One commit containing both canonical edits, the lowered pin, and the hook-regenerated mirrors; `uv run pytest tests/` green.

## Tasks

### Task 1: Delete the tier-calibration clause from the critic's Instructions
- **Files**: `skills/refine/references/clarify-critic.md`
- **What**: Narrows the critic's remit to the three confidence dimensions it is built for, so the one-sided reviewer stops opining on tier at all (spec R1, R2).
- **Depends on**: none
- **Context**: Line 44, the Instructions paragraph. Delete exactly the 89-byte trailing clause `, and optionally complexity/criticality calibration if that rating looks poorly supported`, leaving the sentence ending `...requirements alignment).` Occurrence enumeration is done: the only live occurrences repo-wide are this line and its generated mirror; every other hit is a historical `cortex/lifecycle/archive/**` or cancelled-lifecycle artifact and must not be edited. Touch nothing else — the `**Soft cap of 5 rubric dimensions.**` paragraph (line 80) enumerates no dimensions and must stay byte-identical (R2), and the `## Parent Epic Alignment` sub-rubric (lines 26–40) is a separate section, not part of the Instructions paragraph.
- **Complexity**: trivial
- **Verification**: `grep -c 'complexity/criticality calibration' skills/refine/references/clarify-critic.md` → `0`; `grep -c 'Soft cap of 5 rubric dimensions' skills/refine/references/clarify-critic.md` → `1`; `stat -f %z skills/refine/references/clarify-critic.md` → `4798` (was 4887, exactly 89 bytes freed). Pass = all three.
- **Status**: [x] done (46652bc0 2026-08-04T13:49:12-04:00)

### Task 2: Require a next-tier-down statement in `clarify.md` §5
- **Files**: `skills/refine/references/clarify.md`
- **What**: Makes the orchestrator that already owns the tier decision articulate the downward option explicitly, independent of any critic signal — this is what makes Task 1's deletion safe (spec R3, R4, R5).
- **Depends on**: none
- **Context**: §5 item 2 (`**Complexity**`, line 33). Append the spec's measured 73-byte example verbatim after the existing final sentence, so the item ends `...**When torn, take the lower tier** — the escalator re-checks after research. State whether the next tier down was considered, and why it was rejected.` Constraints on the wording: it must not mention the critic or condition on critic output (R3), must not instruct or prefer lowering, must add no quota/target/aim language, and must leave `**When torn, take the lower tier**` byte-identical (R4); no MUST/CRITICAL/REQUIRED token (R5). Item 3 (`**Criticality**`) is untouched — the criticality axis is split to #452. No `<!-- pause: -->` marker changes, so `kept-pauses-data.toml` needs no update.
- **Complexity**: trivial
- **Verification**: `awk '/^2\. \*\*Complexity\*\*/{f=1} /^3\. \*\*Criticality\*\*/{f=0} f' skills/refine/references/clarify.md | grep -c 'critic'` → `0`; same slice `| grep -c 'next tier down'` → `1`; (the slice must **exclude** the item-3 delimiter line — an inclusive `awk '/a/,/b/'` range pulls in item 3's literal `` `critical` `` and reports a false positive) `grep -c 'When torn, take the lower tier' skills/refine/references/clarify.md` → `1`; `grep -ciE 'quota|target (rate|distribution|share)|aim (for|at)' skills/refine/references/clarify.md` → `0`. Pass = all four.
- **Status**: [x] done (46652bc0 2026-08-04T13:49:12-04:00)

### Task 3: Re-measure the budget, lower the pin, verify, and commit both edits together
- **Files**: `skills/refine/references/size-pin.txt`, `skills/refine/references/clarify-critic.md`, `skills/refine/references/clarify.md`, `plugins/cortex-core/skills/refine/references/size-pin.txt`
- **What**: Confirms R6 against the tree as it actually stands (the spec's figures are authoring-time observations, not a reservation — this directory is under concurrent churn), locks in the lower floor, and lands both spec phases atomically so Phase 1 can never ship alone.
- **Depends on**: [1, 2]
- **Context**: The ratchet measures all regular files in the directory **excluding** `size-pin.txt` (`scripts/ratchet_refs.py:measure`). Pre-edit: 20583 against a pin of 20588. Expected post-edit: 20583 − 89 + 74 = **20568**. Re-derive it, don't assume: `python3 -c` over the directory, or read the ratchet's own failure text. **If the measured value exceeds the pin** — a sibling lifecycle committed to `specify.md`, `clarify-critic.md`, or `research-phase.md` and consumed the freed headroom — halt and report; R6 forbids adding a hand-raised `# raised:` exception. Then `just ratchet-refs` (down-only; it seeds and lowers, never raises). **Measured sequence** (the hook alone is not enough — `tests/test_mirror_dirs_deduplicate` reads the *working tree*, so an unmirrored canonical edit fails the suite before any commit): `just ratchet-refs` → `just build-plugin` (syncs the `.md` mirrors but **not** `size-pin.txt`) → `just ratchet-refs` again to bring the mirror pin down to the canonical value, at which point the dirs dedupe and the ratchet test passes. Commit via `/cortex-core:commit` per CLAUDE.md — never `git commit`. Expect the commit to also contain `plugins/cortex-core/skills/refine/references/*` mirror paths you did not name: the `.githooks/pre-commit` dual-source hook rebuilds them from your staged blobs and folds them in, including the mirror's own `size-pin.txt`. Never stage a mirror by hand. `just ratchet-refs` enumerates the mirror directory too and may lower `plugins/cortex-core/skills/refine/references/size-pin.txt` in the working tree — it is listed in **Files** for that reason only; it is tool-written, never hand-edited, and the hook overwrites it from the canonical blob at commit time.
- **Complexity**: simple
- **Verification**: `uv run pytest tests/test_reference_size_ratchet.py` passes; `grep -c '# raised:' skills/refine/references/size-pin.txt` → `0`; `git diff --cached -U0 -- skills/refine/references/ | grep -cE '^\+.*\b(MUST|CRITICAL|REQUIRED)\b'` → `0` (R5); `uv run pytest tests/ -q` reports no new failures against the pre-change baseline of 2473 passed; `git show --stat HEAD` lists both canonical files, `size-pin.txt`, and their mirrors in one commit.
- **Status**: [x] done (46652bc0 2026-08-04T13:49:12-04:00)

## Risks

- **The spec contradicts itself on whether §5 may reference the critic.** "Changes to Existing Behavior" says the §5 item "now requires a directional statement about whether critic findings moved the tier judgment"; R3 requires the opposite — an unconditional statement with `grep -c 'critic'` → `0` over that item, precisely so the downward consideration survives a critic that returned nothing or failed. This plan follows **R3**: it is the numbered, grep-verifiable requirement, it was written by the later critical-review fold (`158228e3`), and it is the reading that makes Phase 1's deletion safe. The stale bullet is prose residue; it is not being edited here.
- **`simple` has no next tier down.** The appended sentence is trivially satisfiable there ("n/a"), and per research an assessed `simple` routes out before a lifecycle exists — so the case is near-hypothetical. Accepted rather than spending ~14 of the 94 available bytes on a guard clause.
- **The byte budget is a live measurement, not a reservation.** Three commits touched this directory in the 36 hours before the spec was written. Task 3 re-derives it and halts on breach rather than raising the pin.
- **Prose-only enforcement.** No test can see whether an assessor actually states the downward consideration — the greps pin the instruction's presence, not its effect. This is the accepted trade for a change the spec justifies structurally, and it explicitly claims no tier rate (n=8, Wilson 0.53–0.98).

## Acceptance

`skills/refine/references/clarify-critic.md` no longer solicits tier or criticality calibration anywhere, and `clarify.md` §5's Complexity item requires the assessor to state whether the next tier down was considered and why it was rejected — unconditionally, with no reference to the critic. Both changes reach `main` in a single commit alongside a `size-pin.txt` lowered to the new directory size with no hand-raised exception, and `uv run pytest tests/` is green.
