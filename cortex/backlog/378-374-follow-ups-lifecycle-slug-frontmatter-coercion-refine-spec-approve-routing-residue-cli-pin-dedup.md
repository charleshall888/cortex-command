---
schema_version: "1"
uuid: 73f3083d-7468-4080-9850-87e851e40739
title: '374 follow-ups: lifecycle_slug frontmatter coercion, refine spec-approve routing residue, CLI_PIN dedup'
status: complete
priority: medium
type: bug
created: 2026-07-12
updated: 2026-07-13
tags: ['cli-served-lifecycle-state-machine']
areas: ['backlog', 'lifecycle']
lifecycle_phase: complete
lifecycle_slug: "378"
complexity: complex
criticality: high
spec: cortex/lifecycle/378/spec.md
---
## Why

Three residues surfaced while completing #374 (the served next/advance lifecycle loop) and its two-cycle review. None blocked #374 — each is pre-existing or fell outside a task's file scope — but each is a real papercut worth clearing before it accretes. Grouped as one ticket because they are all small, 374-adjacent, and cheap to land together.

## Items

**1. Numeric `lifecycle_slug` in backlog frontmatter (the bug).** Tool-managed frontmatter can write `lifecycle_slug: 374` as an unquoted YAML integer. `tests/test_lifecycle_references_resolve.py::test_every_lifecycle_reference_resolves` fails on it, and it is a *latent crash*, not just a red test: `cortex_command/backlog/generate_index.py:164` does `fm.get("lifecycle_slug", "").strip()`, which raises `AttributeError` on an int; `cortex_command/backlog/resolve_item.py:136` returns it raw. Decide the contract — quote-on-write (locate the writer, which is not obvious from a grep) vs coerce-to-str at the consumers — then backfill existing files. `lifecycle_phase` is also observed stale (`research` on a completed feature); worth checking the same writer. Needs a short diagnosis of the write path.

**2. `skills/refine/references/specify.md` still calls `cortex-lifecycle-spec-approve` directly** — an absorbed verb. #374 Task 19 routed the lifecycle loop through `cortex-lifecycle-advance`, but `specify.md` (refine tree) was outside that task's file list, so this one direct B1-verb invocation survives. Route it through `cortex-lifecycle-advance spec-approve` for consistency. Skills-gated; regenerate the dual-source mirror.

**3. Duplicate `CLI_PIN` (chore).** #374 Task 11 inlined a second pin (`v2.34.6`) in `plugins/cortex-core/install_core.py` alongside `plugins/cortex-overnight/cli_pin.py` (documented in ADR-0026). The two must be bumped together at release — a footgun with no guard. Consolidate to one shared pin source, or add a parity check that fails when they diverge.

## Edges — considered and decided (do not re-open without a new lens)

- **`--audit` reports 12 stale-deprecation rows** in the events registry → already the scope of **#377** (events hygiene). Not duplicated here.
- **Wrapper auto-reads `protocol-expectation.txt`** to drop the loop's `--expect-min`/`--expect-max` handshake step → **REJECTED**. Marginal recurring-token ROI; breaks the tested verbatim-clone wrapper invariant (all `bin/cortex-lifecycle-*` wrappers are byte-identical modulo module name); and fails *open* in the `uv tool` console-script install mode, where there is no sibling `skills/` to read — precisely the distribution mode where skew matters most. The explicit handshake keeps skew detection visible and the model an active participant; keep it.

## Touch-points

- `cortex_command/backlog/generate_index.py:164`, `cortex_command/backlog/resolve_item.py:136`, `tests/test_lifecycle_references_resolve.py`
- `skills/refine/references/specify.md` (+ `plugins/cortex-core/` mirror)
- `plugins/cortex-core/install_core.py`, `plugins/cortex-overnight/cli_pin.py`, `cortex/adr/0026-cortex-core-background-install.md`