---
name: invalid-marker
description: Synthetic fixture exercising the invalid-marker failure path.
---

# Invalid Marker

This fixture contains a malformed size-budget-exception marker (rationale below
the 30-character minimum) so the test's marker-validation path raises with the
literal string "invalid size-budget-exception marker".

<!-- size-budget-exception: too short -->

The file is otherwise small (well under the 500-line cap); the failure is
purely about marker validity, not cap breach.
