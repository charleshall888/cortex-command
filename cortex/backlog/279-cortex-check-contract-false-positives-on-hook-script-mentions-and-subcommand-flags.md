---
schema_version: "1"
uuid: 69b4c348-5c4a-476d-a056-e3a2cfaf47e6
title: "cortex-check-contract false-positives on hook-script mentions and subcommand flags"
status: refined
priority: medium
type: bug
created: 2026-06-02
updated: 2026-06-02
complexity: complex
criticality: high
spec: cortex/lifecycle/cortex-check-contract-false-positives-on/spec.md
areas: ['hooks']
---
**Why:** `cortex-check-contract` exits 1 on 12 false-positive violations — none are real doc or code errors. Two distinct checker limitations cause all of them:

1. **Substring matching instead of invocation matching.** The 8 `cortex-worktree-create` E101 hits fire on mentions where the token is part of a hook-script filename (`claude/hooks/cortex-worktree-create.sh`, `plugins/cortex-core/hooks/cortex-worktree-create.sh`) or the argument of a `command -v` PATH probe. None are console-script invocations, so demanding the required `--feature` flag is wrong.
2. **No subcommand-flag modeling.** The 4 `cortex-discovery` E102 hits report `--topic`/`--complexity`/`--criticality` as unknown. They are valid flags of the `emit-research-sizing` and `read-research-sizing` subcommands; the checker validates flags only against the top-level parser and never descends into the matched subparser.

Net: the gate is permanently red on correct documentation, so it cannot serve as a whole-repo or CI gate (this is exactly why #277's Task 18 could not reach "contract green"), and it will block any future edit to the affected files at the pre-commit stage.

**Role:** Make `cortex-check-contract` precise enough to trust as a gate — flag only genuine console-script invocations that violate the real argparse surface, and resolve flags against subcommands.

**Integration:**
- Treat a token as an invocation only in command position — not when it is a substring of a `.sh` path or the argument to `command -v`/`which`.
- Model subcommands: when the matched command has subparsers and the line names one, validate flags against that subparser.

**Edges:** Do not regress genuine detection — a real `cortex-worktree-create --base-branch main` missing `--feature` must still flag, and a genuinely unknown flag on a known subcommand must still flag. Add fixtures for both the false-positive shapes (hook-filename mention, `command -v` probe, subcommand flags) and the true-positive shapes.

**Known false-positive lines (current tree):** `docs/agentic-layer.md:160,210`; `docs/internals/sdk.md:142,157`; `skills/lifecycle/references/implement.md:58,234`; `skills/lifecycle/references/parallel-execution.md:14,26`; `skills/discovery/references/clarify.md:77`; `skills/discovery/references/research.md:34`.

**Touch-points:** the `cortex-check-contract` implementation (the `bin/` console script or its `cortex_command` module) plus its test fixtures. Surfaced during #277 completion (Task 18 gate review).