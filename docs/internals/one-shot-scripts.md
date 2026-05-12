[← Back to Agentic Layer](../agentic-layer.md)

# One-Shot Scripts Registry

**Internal reference — not a user-facing skill.**

Some remediations only need to run once, against a finite known-bad set
of historical artifacts. These scripts live in the lifecycle directory
of the feature that produced them, not in `bin/`, because (a) they are
not part of the long-running surface, (b) re-running them is unsafe or
useless after the initial pass, and (c) keeping them next to the spec
and plan that justified them makes the audit trail self-contained.

The tradeoff: a script outside `bin/` is undiscoverable by anyone who
doesn't already know the lifecycle directory exists. This registry
mitigates that risk — it is the single discovery surface for one-shot
remediation scripts. Add a row here whenever you ship a one-shot under
`cortex/lifecycle/<feature>/scripts/`.

---

## Registry

| Script | Lifecycle | Purpose | Status |
|---|---|---|---|
| [`remediate-historical-drift.py`](../../cortex/lifecycle/requirements-skill-v2/scripts/remediate-historical-drift.py) | `requirements-skill-v2` (R8) | Enumerate the historical `cortex/lifecycle/{,archive/}*/review.md` files where the reviewer flagged `requirements_drift: detected` but omitted the `## Suggested Requirements Update` section that R7 now enforces going forward. Supports `--dry-run` to list candidates without dispatch. Operator runs the script inside an interactive Claude Code session and dispatches a reviewer sub-agent per file. | active (run via Task 12 of `requirements-skill-v2`) |

---

## Conventions

When adding a one-shot script:

1. Place the script at `cortex/lifecycle/<feature>/scripts/<name>.py`.
2. Make it executable (`chmod +x`) with a `#!/usr/bin/env python3` shebang.
3. Default to a behavior an operator can read without side effects;
   require an explicit live flag (or invoke from an interactive session
   where the operator drives dispatch) before mutating files.
4. Add a `--dry-run` mode that lists exactly what the live run would
   touch — this is the semantic verifier the operator uses to confirm
   the candidate set before running anything destructive.
5. Append a row to the registry above with a one-line purpose
   description and a link to the script.
6. After the script has been run and its remediation merged, leave it
   in place as documentation of what was done; update the Status column
   to `archived (ran on YYYY-MM-DD)`.
