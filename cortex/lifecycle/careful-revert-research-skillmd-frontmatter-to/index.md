---
feature: careful-revert-research-skillmd-frontmatter-to
backlog_item: 302
uuid: 0e8dcceb-26a5-432d-aec1-1137090e141a
status: active
artifacts:
  - research.md
  - spec.md
  - plan.md
updated: 2026-06-13
---
# careful-revert-research-skillmd-frontmatter-to

Backlog #302 — careful-revert `skills/research/SKILL.md`'s `description` from 502B to the ~378B #191 close-state by removing the +124B mechanism-narration regrowth, preserving the three test-enforced trigger phrases and the research.md-vs-conversation-output disambiguation tail; then lower the `research` and `total` rows in `tests/test_l1_surface_ratchet.py` and regenerate the cortex-core plugin mirror. complexity=complex, criticality=high. Split from #298, unblocked by #299 (complete). Entered via /cortex-core:refine.
