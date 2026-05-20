## Why

The discipline gap is visible at bin/cortex-check-prescriptive-prose:46 where
the FORBIDDEN_SECTIONS constant omits Why, allowing prescriptive prose in that
section to pass the pre-commit gate undetected.

This fixture should be rejected by LEX-1 due to the path:line citation above.

## Role

A regression guard demonstrating that path:line citations inside Why are flagged.

## Integration

Invoked via `bin/cortex-check-prescriptive-prose` in positional file-arg mode.

## Edges

No non-goals for this fixture; its only purpose is to trigger a LEX-1 failure.
