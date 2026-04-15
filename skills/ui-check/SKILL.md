---
name: ui-check
description: Run the full UI design enforcement pipeline — Layer 0 (DESIGN.md + shadcn presence, warns only) → Layer 1 (/ui-lint, blocks on failures) → Layer 2 (/ui-a11y if a dev server is reachable, skips if not). Writes ui-check-results/summary.json after every run. Use when user says "/ui-check", "run UI checks", "check frontend quality", "run the full UI check pipeline", or wants to verify design enforcement before committing.
disable-model-invocation: true
inputs:
  - "--only: enum (optional) — lint|a11y|judge; run a single layer in isolation"
outputs:
  - "ui-check-results/summary.json — layered pass/fail summary"
preconditions:
  - "Run from project root"
  - "ui-check-results/ directory will be created if absent"
---

# /ui-check

Orchestrate Layer 0 → Layer 1 → Layer 2 in order. Stop on the first layer failure. Write `ui-check-results/summary.json` after every run (including partial runs).

## Setup

```bash
mkdir -p ui-check-results
```

Read `.ui-config.json` at the project root if it exists. Extract `devServerUrl` if present — this overrides port scanning in Layer 2.

## --only mode

If `--only <layer>` was passed, run that layer only and skip all others:

- `--only lint` → Layer 1 only (skip Layers 0 and 2)
- `--only a11y` → Layer 2 only (skip Layers 0 and 1; server detection still applies)
- `--only judge` → invoke `/ui-judge` directly; record `judge` status in summary; exit 0

After the targeted layer finishes, jump directly to Output.

## Layer 0: Prevention check

Check file presence only. Never exit non-zero from this layer.

1. Check for `DESIGN.md` at repo root or `frontend/DESIGN.md` → set `design_md: "present"` or `"missing"`.
2. Check for `components.json` at repo root → set `shadcn: "present"` or `"missing"`.

If `design_md` is `"missing"`, print: `Warning: DESIGN.md not found — run /ui-brief to generate it`
If `shadcn` is `"missing"`, print: `Warning: shadcn not initialized — run /ui-setup`

Continue to Layer 1 regardless.

## Layer 1: Lint gate

1. Invoke `/ui-lint` (it runs ESLint + Stylelint in fix-then-report mode and writes `ui-check-results/lint.json`).
2. Read `ui-check-results/lint.json`. Extract `passed`, `autofixed_count`, `failure_count`.
3. If `failure_count > 0`: write summary, print the one-liner, exit non-zero. **Skip Layer 2.**
4. If `failure_count === 0`: record counts and continue.

Read `lint.json` once. Do not loop or re-run lint.

## Layer 2: A11y (conditional)

**Detect dev server:**

If `.ui-config.json` provided a `devServerUrl`, use it. Otherwise probe ports in order:

```bash
curl -s --max-time 2 -o /dev/null -w "%{http_code}" http://localhost:PORT
```

Ports to try: `3000`, `3001`, `5173`, `4173`. First port returning a 2xx or 3xx response is the server URL.

If no server is found: set `a11y.status = "skipped"`, `a11y.reason = "no server found"`. Skip to Output.

**If server found:**

Invoke `/ui-a11y`. Read `ui-check-results/a11y.json`. Set `a11y.status = "passed"` or `"failed"` from results. If `"failed"`, exit non-zero after Output.

## Output

Write `ui-check-results/summary.json`:

```json
{
  "design_md": "present|missing",
  "shadcn": "present|missing",
  "lint": { "passed": true, "autofixed_count": 2, "failure_count": 0 },
  "a11y": { "status": "skipped", "reason": "no server found" },
  "judge": { "status": "not_run" }
}
```

Print a single stdout line:

```
DESIGN.md: present | shadcn: present | Lint: ✓ (2 autofixed) | A11y: skipped (no server) | Judge: not run
```

Token formats: passed → `✓` or `✓ (N autofixed)`; failed → `✗ (N failures)`; skipped → `skipped (<reason>)`.

**Exit code**: 0 if all run layers passed or were skipped. 1 if any run layer had failures.
