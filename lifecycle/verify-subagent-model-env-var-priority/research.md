# Research: verify-subagent-model-env-var-priority

## Epic Reference

Background: [research/subagent-model-routing/research.md](../../research/subagent-model-routing/research.md) — this spike resolves the disputed env var priority order that determines the implementation approach for epic 044.

## Research Questions

1. **Does the per-invocation `model` parameter on Agent() actually change the model?**
   → **Yes, confirmed empirically.** Spawning with `model: "opus"` produces an agent reporting `claude-opus-4-6[1m]`. Spawning with `model: "sonnet"` produces an agent reporting `claude-sonnet-4-6`. Tested in the current session.

2. **What is the priority order between `CLAUDE_CODE_SUBAGENT_MODEL` and per-invocation `model` param?**
   → **Env var wins.** The official Claude Code sub-agents documentation states the resolution order explicitly:
   1. `CLAUDE_CODE_SUBAGENT_MODEL` environment variable (if set) — **highest priority**
   2. Per-invocation `model` parameter
   3. Subagent definition's `model` frontmatter
   4. Main conversation's model — **lowest priority (inherit)**

   Source: [Claude Code sub-agents docs — "Choose a model"](https://code.claude.com/docs/en/sub-agents.md)

3. **What does this mean for the implementation approach?**
   → **Do NOT set `CLAUDE_CODE_SUBAGENT_MODEL`.** If set, it overrides ALL per-invocation model params, preventing skills from escalating to Opus for critical tasks. The correct approach is:
   - Leave `CLAUDE_CODE_SUBAGENT_MODEL` unset
   - Use per-invocation `model: "sonnet"` in skill Agent() calls for non-critical tasks
   - Use per-invocation `model: "opus"` (or omit to inherit) for critical implementation tasks
   - Add guidance to CLAUDE.md/Agents.md documenting this convention

## Empirical Test Results

| Test | Agent tool params | Env var | Agent reported model |
|------|-------------------|---------|---------------------|
| Control (Opus) | `model: "opus"` | not set | `claude-opus-4-6[1m]` (Opus) |
| Control (Sonnet) | `model: "sonnet"` | not set | `claude-sonnet-4-6` (Sonnet) |
| Env var override | not testable in-session | — | Documented: env var wins |

Note: The env var override test could not be performed empirically within this session because env vars set in bash subprocesses don't propagate to the parent Claude Code process. The priority order is confirmed via official documentation instead.

## Decision Impact

This resolves the disputed priority order in the epic research (DR-1):

- **Approach A (env var default) is NOT viable** for our use case — it blocks per-skill Opus escalation
- **Approach D (per-invocation params + CLAUDE.md guidance) is confirmed as the correct approach**
- The original DR-1 recommendation was correct; the critical review's challenge was well-founded but the documented behavior supports the original conclusion

## Open Questions

None — the spike's questions are fully resolved.
