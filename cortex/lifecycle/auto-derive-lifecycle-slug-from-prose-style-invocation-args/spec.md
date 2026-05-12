# Specification: auto-derive-lifecycle-slug-from-prose-style-invocation-args

## Problem Statement

`skills/lifecycle/SKILL.md` Step 1's parse rule assumes `$ARGUMENTS` first word is already a kebab-case slug. When a user invokes `/cortex-core:lifecycle` with a descriptive prose argument (e.g., `/cortex-core:lifecycle let's update CLAUDE.md to ...`), the SKILL has no prescribed branch — different agent instances behave differently (some ask via `AskUserQuestion` for confirmation, some pick silently, some try to use the literal first word as a slug). The same gap exists in `skills/refine/SKILL.md` Step 1's exit-3 (no backlog match) branch, which currently "treat[s] the input as the topic name" without slug derivation. This spec adds an explicit prose-handling branch to both surfaces: when input is prose (not a valid kebab-case slug), the SKILL prescribes that the agent derive a 3–6 word kebab-case slug from the prose, announce it, and proceed without confirmation. The user can correct via re-invocation if needed.

## Phases

- **Phase 1: Add prose-handling branch to both skill surfaces** — Update `skills/lifecycle/SKILL.md` Step 1 and `skills/refine/SKILL.md` Step 1 exit-3 branch with parallel prose-derivation prescriptions.

## Requirements

**Priority classification**: R1 and R2 are **Must-have** (the two skill files where the gap exists). R3 is **Must-have** (the no-confirmation rule that defines the desired behavior; without it, agents may still ask). No Should-have or Could-have requirements identified.

1. **R1 — Prose branch in `skills/lifecycle/SKILL.md` Step 1**: Modify the parse-rule prose in Step 1 of `skills/lifecycle/SKILL.md` to explicitly handle the case where `$ARGUMENTS` is non-empty AND its first word does not match the valid-slug pattern `^[a-z0-9]+(-[a-z0-9]+)*$`. The new prose instructs the agent to derive a 3–6 word kebab-case slug from the prose (semantic compression: a short summary, not a verbatim slugify), announce the chosen slug as it creates `cortex/lifecycle/{slug}/`, and use that slug as `{feature}` for the rest of Step 1 (resolver lookup) and Step 2. Soft positive-routing language; no MUST/NEVER/REQUIRED/CRITICAL. **Acceptance**: `grep -c 'kebab-case\|prose' skills/lifecycle/SKILL.md` returns a higher count than baseline; the new branch text appears within Step 1 (verified by `awk '/^## Step 1:/,/^## Step 2:/' skills/lifecycle/SKILL.md | grep -ci 'derive.*slug\|prose-style\|not a valid.*slug'` returning ≥`1`); `grep -ciE '^[^a-zA-Z]*\b(MUST|NEVER|REQUIRED|CRITICAL)\b' <new-prose-block>` returns `0`. **Phase**: Phase 1: Add prose-handling branch to both skill surfaces.

2. **R2 — Prose branch in `skills/refine/SKILL.md` Step 1 exit-3 path**: Modify the exit-3 routing prose in Step 1 of `skills/refine/SKILL.md` to mirror R1's prescription: when the resolver returns exit 3 and the input is prose (not a valid kebab-case slug), derive a 3–6 word kebab-case slug from the prose before switching to Context B (rather than passing prose through as the literal "topic name"). Soft positive-routing language; no MUST/NEVER/REQUIRED/CRITICAL. The refine prose should reference the lifecycle prose by inline pointer rather than duplicating the full rule — both surfaces stay in sync. **Acceptance**: `awk '/Exit 3.*no match/,/Exit 64/' skills/refine/SKILL.md | grep -ci 'derive.*slug\|prose'` returns ≥`1`; `grep -ciE '^[^a-zA-Z]*\b(MUST|NEVER|REQUIRED|CRITICAL)\b' <new-prose-block>` returns `0`. **Phase**: Phase 1: Add prose-handling branch to both skill surfaces.

3. **R3 — No-confirmation rule**: The new prose in both skills must explicitly prescribe that the agent **proceed without an `AskUserQuestion` prompt to confirm the slug**. (Without this prescription, the failure mode the ticket targets — gratuitous round-trip — remains possible.) Inline correction is via re-invocation; "rename in place" is out of scope per backlog #205. **Acceptance**: The new prose block in both files contains a phrase semantically equivalent to "do not ask the user to confirm" or "proceed without confirmation" (verified by reading); `awk '/^## Step 1:/,/^## Step 2:/' skills/lifecycle/SKILL.md | grep -ci 'do not ask\|without.*confirm\|do not.*confirm'` returns ≥`1` AND `awk '/Exit 3.*no match/,/Exit 64/' skills/refine/SKILL.md | grep -ci 'do not ask\|without.*confirm\|do not.*confirm'` returns ≥`1`. **Phase**: Phase 1: Add prose-handling branch to both skill surfaces.

## Non-Requirements

- Does NOT introduce a Python helper module or modify `cortex_command.common.slugify`. The model performs the semantic compression in-context, guided by SKILL.md prose. Adding a Python helper for what is fundamentally a prompt-engineering problem would be over-engineering.
- Does NOT rename existing lifecycle directories. Inline correction is via re-invocation with a corrected slug; in-place rename of a just-created lifecycle dir is out of scope per backlog #205 Out-of-scope #1.
- Does NOT modify slug derivation for backlog items (still handled by canonical `slugify()` per backlog #205 Out-of-scope #2).
- Does NOT edit `plugins/cortex-core/skills/{lifecycle,refine}/SKILL.md` (mirrors). The pre-commit dual-source hook regenerates mirrors from canonical sources.
- Does NOT add a parity test or hook enforcement for prose-derivation behavior. The behavior is prose-only guidance; adding test infrastructure for prose-only guidance is over-engineering.
- Does NOT change the `$ARGUMENTS` empty case (existing incomplete-lifecycle-dirs scan path is unchanged).
- Does NOT change exit-0 (unambiguous backlog match) or exit-2 (ambiguous match) paths in either skill.

## Edge Cases

- **Short prose (1–2 words)**: The agent uses the canonical `slugify()` directly when the input is already short enough to produce a reasonable slug. SKILL.md prose says "derive a 3–6 word kebab-case slug" which includes the trivial 1-word case where the slug is identical to slugify(input).
- **Single token with punctuation (e.g., `let's`)**: Apostrophe makes it invalid kebab-case → triggers derivation. The agent picks 1–2 words capturing intent. The model handles this in-context.
- **Prose with no nouns or clear topic**: The agent does its best; worst case is a slightly awkward slug. User can re-invoke with override. No SKILL.md fallback prescription needed — degenerate inputs accept degenerate outputs.
- **Derived slug collides with existing `cortex/lifecycle/{slug}/`**: Falls through to existing Step 2 phase-detection — treated as resume. The agent should announce that resume is happening, not silently append a counter to disambiguate. This matches the current Step 2 resume behavior; no new prescription needed.
- **`$ARGUMENTS` empty**: Unchanged — existing incomplete-lifecycle-dirs scan path applies.
- **First word IS a valid kebab-case slug but doesn't match any backlog item**: Unchanged — resolver returns exit 3, lifecycle proceeds with the slug as `{feature}` per existing exit-3 routing.

## Changes to Existing Behavior

- **MODIFIED**: `skills/lifecycle/SKILL.md` Step 1 parse rule. The implicit "first word = feature name" rule gains an explicit branch for prose inputs.
- **MODIFIED**: `skills/refine/SKILL.md` Step 1 exit-3 path. The "treat the input as the topic name" rule gains an explicit slug-derivation step before switching to Context B.
- **ADDED**: The agent now derives a slug from prose deterministically (in-context, guided by SKILL.md prose) instead of varying its handling per invocation.

## Technical Constraints

- **Dual-source enforcement**: Canonical sources are `skills/lifecycle/SKILL.md` and `skills/refine/SKILL.md`. Mirrors at `plugins/cortex-core/skills/{lifecycle,refine}/SKILL.md` regenerate via the pre-commit dual-source hook (per CLAUDE.md "Auto-generated mirrors at `plugins/cortex-core/{skills,hooks,bin}/` regenerate via pre-commit hook; edit canonical sources only"). Editing the mirrors directly would be rejected at pre-commit.
- **Soft positive-routing**: CLAUDE.md MUST-escalation policy applies. The new prose in both SKILL.md files must use soft positive-routing language. No F-row evidence artifact exists for this lifecycle (the trigger is general DX friction, not a specific failure incident).
- **SKILL.md size budget**: SKILL.md files are capped at 500 lines per `tests/test_skill_size_budget.py` (per `cortex/requirements/project.md` Architectural Constraints). `skills/lifecycle/SKILL.md` is currently 173 lines (checked); `skills/refine/SKILL.md` is 213 lines (checked). Both have ample headroom for ~6–12 lines of added prose each.
- **No new MUST in mirrored content**: Same MUST-escalation constraint applies to both canonical and (auto-regenerated) mirrored copies.
- **Semantic compression by the model, not by Python**: The derivation strategy is prescribed in prose; the agent (Opus 4.7 or later) does the semantic distillation. SKILL.md does NOT call out to a Python helper for this — the chosen approach treats prose-to-slug as a prompt-engineering problem, consistent with the project's "prescribe What and Why, not How" principle.

## Open Decisions

None. All design questions resolved during clarify-critic Apply round (mechanism, terminology, refine scope, edge cases, alignment framing).
