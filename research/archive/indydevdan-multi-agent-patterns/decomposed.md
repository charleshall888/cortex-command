# Decomposition: indydevdan-multi-agent-patterns

## Outcome

No new backlog tickets. The discovery evaluated six multi-agent patterns from IndyDevDan's "One Agent Is NOT ENOUGH" video against cortex-command's existing capabilities:

| Pattern | Finding |
|---------|---------|
| Best-of-N | Already in use for exploration/design (3 variants); not worth extending to implementation |
| Trust progression | Already encoded implicitly via model selection matrix + overnight orchestrator |
| Stop-hook validation | **Already implemented** as `test_command` post-merge gate in `merge.py` — missed in initial research |
| Event-streaming observability | Not worth complexity; file-polling dashboard is sufficient |
| Agent Teams | Consciously deferred; revisit when interactive workflow demands inter-agent communication |
| Session-start context injection | cortex-command already exceeds IndyDevDan's approach |

## Action Taken

Documentation update only: expanded `docs/overnight.md` "Per-repo Overnight" section to document `lifecycle.config.md` setup and the `test-command` field for new repo onboarding. The existing validation mechanism was functional but poorly documented.

## Key Design Decisions

- **Stop-hook was the wrong pattern**: The Stop hook fires on every response completion (dozens per session). Post-merge (`merge.py:run_tests()`) is the correct checkpoint — runs once per feature at the boundary where validation matters.
- **No tickets needed**: All six evaluated patterns are either already implemented, already implicitly captured, or not worth the complexity. The only gap was documentation.
