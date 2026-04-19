# /claude-api migrate to claude-opus-4-7 — Empirical Results

> Generated: 2026-04-18. Spike under epic #082 (opus-4-7 harness adaptation). Backlog ticket: #083.

## Context

Ran Anthropic's `/claude-api migrate this project to claude-opus-4-7` against the cortex-command working directory, captured the resulting diff, and documented it here for #085 (the downstream consumer that will do the real harness-wide migration).

- **Baseline SHA**: `373ca304` (commit: "Remove cortex-notify-remote hook and land epic-82 in-progress state")
- **Invocation**: `/claude-api migrate this project to claude-opus-4-7` — scope explicitly confirmed as "entire working directory" per spec-interview decision
- **Execution mode**: On `main` directly (deviation from plan; user override of the worktree-isolation approach). Pre-existing dirty state was committed first to establish a clean baseline.
- **Language detected**: Python (skill read `python/claude-api/README.md` + related docs)

## Transcript Summary

1. Skill scanned for non-Anthropic provider markers — none found (no OpenAI/LangChain imports).
2. Skill identified SDK call sites via `import anthropic` / `from anthropic` / `Anthropic(` patterns. **Two files matched**: `bin/count-tokens` and `bin/audit-doc`. Both use `client.messages.count_tokens()` for documentation-sizing decisions.
3. Skill read Opus 4.7 migration reference: sampling parameters (`temperature`, `top_p`, `top_k`) removed and return 400; `thinking: {type: "enabled", budget_tokens: N}` removed and returns 400; adaptive thinking is the only on-mode; `xhigh` effort new for coding/agentic work.
4. Applied changes: swapped three `claude-sonnet-4-6` string occurrences (one default in each file, plus an argparse `--model` default + help text) to `claude-opus-4-7`. **No other changes** — neither file passes sampling params, thinking config, or `budget_tokens`, so none of the Opus 4.7 breaking changes applied.

## Files Touched

Two files, three single-line edits, one semantic change each:

- `bin/audit-doc` — `DEFAULT_MODEL` constant: `claude-sonnet-4-6` → `claude-opus-4-7`
- `bin/count-tokens` — `count_tokens()` function default parameter: `claude-sonnet-4-6` → `claude-opus-4-7`
- `bin/count-tokens` — argparse `--model` flag default + help string: `claude-sonnet-4-6` → `claude-opus-4-7`

Not touched: any SKILL.md file, any reference doc under `claude/reference/`, `claude/Agents.md`, root `CLAUDE.md`, any hook under `hooks/` or `claude/hooks/`, `claude/settings.json`, `claude/pipeline/dispatch.py`, `claude/dashboard/*.py`, test fixture data in `claude/dashboard/tests/test_data.py` (historical event-log values were correctly left alone).

## Change Categories

- **Model ID swap** (3 occurrences across 2 files): `claude-sonnet-4-6` → `claude-opus-4-7`. Purely a default-value update; callers can still override via the existing `--model` flag / function parameter.

No other categories applied — no breaking-change remediations (no sampling params, no `thinking: enabled`, no `budget_tokens`, no assistant-message prefills), no new-capability adoptions (no `xhigh` effort, no adaptive-thinking adds, no task-budget adoption, no compaction enablement), no Managed Agents changes, no structured-output changes, no prompt-cache adjustments.

## Usable As-Is For #085

Directly: **marginally**. The migration surface for #085 (dispatch-skill audit for 4.7 at-risk prompt patterns) does not overlap with the files touched here — #085 targets SKILL.md files and reference docs, which `/claude-api migrate` explicitly skipped (consistent with DR-7's docs-based prediction).

What this run contributes to #085:
1. **DR-7 empirical confirmation** — `/claude-api migrate` is non-destructive to the prompt surface #085 cares about. It did not mutate SKILL.md, `claude/reference/*.md`, `Agents.md`, `CLAUDE.md`, hooks, or settings.json. #085 can proceed without worrying that migrate has already taken partial action on its surface.
2. **Research prediction refinement** — the research.md DR-7 prediction was directionally correct (migrate targets SDK call sites, not docs) but specifically wrong about the target file (`claude/pipeline/dispatch.py` does not import `anthropic` directly and was not touched; the actual targets were `bin/count-tokens` and `bin/audit-doc`). #085's planning should not assume `dispatch.py` is migrate's target; if #085's scope ever extends to SDK code, the targets are the `bin/` utilities.
3. **Zero breaking-change remediation needed for these call sites** — both use only `client.messages.count_tokens()` with a model ID. No param removal, no thinking-config change, no prefill rework. This is useful signal for #085's complexity estimation if it chooses to extend SDK-side coverage later.

## Tentative Mergeability

**Mergeable as-is, with one tradeoff to flag.** The 3-line diff is minimal, reversible, and introduces no API-incompatibility (callers can still pass `--model claude-sonnet-4-6` explicitly). However:

- **Access requirement shift**: `count_tokens` is billed-free regardless of model, but the API key must have access to the named model. Sonnet 4.6 is broadly available; Opus 4.7 access depends on the key's tier. If a user runs `audit-doc` or `count-tokens` with a tier that lacks Opus 4.7, the call will 404. Sonnet 4.6 was a safer universal default.
- **Tokenizer-equivalent semantics**: All Claude 4.x models share a tokenizer, so token counts are unchanged by this swap. Functionality is preserved.
- **Consistency with `claude/settings.json`**: the session model was already switched to `opus[1m]` in the baseline commit; swapping these SDK defaults to Opus 4.7 aligns the defaults with that choice.

Recommendation: merge as-is if the project's baseline API-key tier has Opus 4.7 access. Otherwise consider keeping the default at `claude-sonnet-4-6` for these diagnostic utilities and only pinning the session model via `settings.json`.

## End-of-run Checklist

The `/claude-api` skill did not emit a dedicated end-of-run checklist for this invocation — migration was a direct apply against the two matched files. For completeness, the skill's breaking-change reference (from the loaded `shared/model-migration.md` equivalent) was internally checked and determined non-applicable to these call sites:

- [x] Sampling parameters (`temperature`, `top_p`, `top_k`) — none used in either file; no removal needed.
- [x] `thinking: {type: "enabled", budget_tokens: N}` — not used; no swap to adaptive needed.
- [x] Assistant-message prefills — not used; no removal needed.
- [x] `output_format` → `output_config.format` deprecation — not used; no rewrite needed.
- [x] SDK streaming for 128K outputs — not used; `count_tokens` is non-streaming by design.
- [ ] Adoption of `xhigh` effort, adaptive thinking, task budgets, compaction — **not applicable** to `count_tokens`-only call sites; these are request-shape opportunities on `messages.create()`, which this project doesn't currently call.

## Diff

```diff
diff --git a/bin/audit-doc b/bin/audit-doc
index 6de9233..49a0de4 100755
--- a/bin/audit-doc
+++ b/bin/audit-doc
@@ -22,7 +22,7 @@ from pathlib import Path
 import anthropic


-DEFAULT_MODEL = "claude-sonnet-4-6"
+DEFAULT_MODEL = "claude-opus-4-7"


 def resolve_api_key() -> None:
diff --git a/bin/count-tokens b/bin/count-tokens
index c7a1680..bd6c402 100755
--- a/bin/count-tokens
+++ b/bin/count-tokens
@@ -69,7 +69,7 @@ def resolve_api_key() -> None:
     sys.exit(1)


-def count_tokens(text: str, model: str = "claude-sonnet-4-6") -> int:
+def count_tokens(text: str, model: str = "claude-opus-4-7") -> int:
     """
     Count tokens in text using the Anthropic count_tokens API.
     Counts include minimal message-envelope overhead (~5-15 tokens) from wrapping
@@ -112,8 +112,8 @@ Examples:

     parser.add_argument(
         '-m', '--model',
-        default='claude-sonnet-4-6',
-        help='Claude model to use for token counting (default: claude-sonnet-4-6)'
+        default='claude-opus-4-7',
+        help='Claude model to use for token counting (default: claude-opus-4-7)'
     )

     args = parser.parse_args()
```
