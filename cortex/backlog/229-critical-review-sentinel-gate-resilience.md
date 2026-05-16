---
schema_version: "1"
uuid: 41db000d-76db-4179-bb73-b0db3fde5076
title: "Critical-review sentinel gate: relax first-line strictness to accept lead-in exposition"
status: ready
priority: medium
type: bug
tags: [critical-review, skills, verification-gate]
created: 2026-05-16
updated: 2026-05-16
complexity: simple
criticality: high
---

## Problem

The `/cortex-core:critical-review` skill's Step 2c.5 verification gate strictly checks whether each reviewer's `READ_OK: <path> <sha>` sentinel is the **literal first line** of output. The gate's stated purpose is to detect reviewers that didn't actually read the artifact (hallucination signal) or that read a stale version (SHA drift signal).

In practice, reviewer agents reliably prepend short exposition before emitting the sentinel — phrases like `"I have enough context. Let me write the findings."` or `"Now I'll produce the adversarial review."` — despite emphatic prompt instructions to emit `READ_OK` as the literal first line. This is consistent across Sonnet and Opus and across the four parallel reviewers dispatched per pass.

### Observed impact

Two critical-review passes during external project lifecycle 109 (`Workspaces/wild-light` repo, feature `spriteframes-auto-import-tool`) exhibited the failure mode:

- **Spec pre-approval pass**: 3 of 4 reviewers excluded by sentinel absence.
- **Plan pre-approval pass**: 4 of 4 reviewers excluded.

In every excluded case, the reviewer had verifiably read the artifact: their findings quoted the spec/plan verbatim, grounded claims in actual repo files via grep, and emitted `READ_OK: <correct-sha>` correctly — just not as the literal first line. The seven `sentinel_absence` events are preserved in that lifecycle's `events.log` as a real repro corpus.

The protocol's documented response to all-reviewers-excluded is *"Re-run after resolving concurrent write source"* — but re-running just produces the same exclusion (agents keep preambling), so the gate degrades the skill from "parallel adversarial review" to one of:

1. Synthesize on the single passing reviewer's findings (degraded coverage)
2. Orchestrator quietly bypasses the protocol and applies excluded findings via direct judgment (protocol bypass)

In lifecycle 109 the orchestrator chose option (2) both times.

### Why the gate exists

The SHA-match check is the part that catches real drift. The first-line-strict positional check is the part that's over-firing — it was added on the theory that hallucinated reviewers would also omit the sentinel, but the actual failure mode (reviewers reading correctly but emitting preamble) is not hallucination.

## Fix

Relax the gate's positional rule to accept the sentinel anywhere within an initial window. **Keep the SHA-match check strict** — that one catches actual drift. Three concrete approaches; implementer picks one and verifies against the lifecycle 109 events.log corpus:

1. **First-N-lines window** (recommended, lowest risk): change `cortex-critical-review record-exclusion`'s upstream parser in `skills/critical-review/SKILL.md` and `references/verification-gates.md` to search the first 20 lines of reviewer output for `^READ_OK: ` (or `^READ_FAILED: `) via `re.search` with `re.MULTILINE`. Match → pass; no match → exclude.

2. **Pre-content sentinel window**: search for the sentinel only in the prose block BEFORE the first `## ` markdown heading. Still requires reviewers to emit the sentinel before substantive analysis, but allows arbitrary preamble.

3. **Prompt-side belt-and-suspenders**: tighten `references/reviewer-prompt.md` to use a structured sentinel format (e.g., `<sentinel>READ_OK: ...</sentinel>` on its own line) that the parser unambiguously locates. Higher risk — may not help if agents ignore the structured-format instruction the same way they ignore "first line."

## Acceptance

- Re-running the gate against a saved reviewer output that emits `READ_OK` on line 3+ no longer triggers `sentinel_absence` exclusion when the SHA matches.
- A reviewer output that genuinely lacks `READ_OK` anywhere (true hallucination) still gets excluded under `sentinel_absent`.
- A reviewer output with `READ_OK` present but the wrong SHA still gets excluded under `sha_mismatch`.
- The `cortex-critical-review record-exclusion` subcommand's exit codes and event-log payload schema are unchanged (downstream consumers of the events.log don't break).
- Verification corpus: the seven `sentinel_absence` events at `Workspaces/wild-light/cortex/lifecycle/spriteframes-auto-import-tool-generate-tres-from-spritesheets/events.log` (saved reviewer outputs reachable from the agent IDs in that conversation's transcripts) all flip to "pass" under the new rule when their SHAs match the captured `expected_sha`.

## Out of Scope

- Redesigning the verification protocol end-to-end.
- Adding new sentinel types (e.g., `READ_PARTIAL`).
- Changing the synthesizer-side `SYNTH_READ_OK` gate — that one fires reliably because Opus follows the literal-first-line instruction.
- Softening the load-bearing voice anchors at `SKILL.md:97` (`Do not soften or editorialize`) or `synthesizer-prompt.md:50` (`Do not be balanced. Do not reassure.`) — preserve those per backlog #082 / #085.

## Notes

Surfaced during a downstream project lifecycle; not via a cortex-command-internal investigation. The repro corpus lives in another repo, but the bug is entirely in this repo's `skills/critical-review/` files.
