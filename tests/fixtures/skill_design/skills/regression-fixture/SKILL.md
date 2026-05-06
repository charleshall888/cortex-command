---
name: regression-fixture
description: Synthetic SKILL.md used by tests/test_skill_descriptions.py to prove the failure-detection path fires when a declared trigger phrase is absent from the description. This fixture intentionally mentions the phrase "fixture present phrase" but omits the phrase declared in regression_skill_trigger_phrases.yaml under must_contain.
---

# regression-fixture

This fixture is consumed only by tests. It is not a real skill and is not
enumerated by the canonical-skill helpers in `tests/conftest.py`.
