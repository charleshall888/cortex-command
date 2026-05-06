---
name: consumer-fixture
description: Synthetic consumer SKILL.md used by tests/test_skill_handoff.py to prove the failure-detection path fires when a declared cross-skill handoff field name is absent from the consumer's prose. This fixture intentionally omits the field-name token declared in the sibling handoff_rename/skill_handoff_schema.yaml fixture.
---

# consumer-fixture

This fixture is consumed only by tests. It is not a real skill and is not
enumerated by the canonical-skill helpers in `tests/conftest.py`. The
field-name token declared in the sibling fixture YAML is deliberately
omitted from this file's body to exercise the missing-field-name detection
path in tests/test_skill_handoff.py.
