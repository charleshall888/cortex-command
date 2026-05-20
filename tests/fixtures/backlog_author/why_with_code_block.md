## Why

The scanner misses violations because the current regex does not handle
multi-line fenced code blocks inside the Why section. For example:

```python
FORBIDDEN_SECTIONS = {"Role", "Integration", "Edges"}
PERMITTED_SECTIONS = {"Touch points"}
```

This fixture should be rejected by LEX-1 (fenced code block with ≥2 non-empty lines).

## Role

A regression guard demonstrating that fenced code blocks inside Why are flagged.

## Integration

Invoked via `bin/cortex-check-prescriptive-prose` in positional file-arg mode.

## Edges

No non-goals for this fixture; its only purpose is to trigger a LEX-1 failure.
