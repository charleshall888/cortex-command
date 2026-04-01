---
name: ui-a11y
description: Run axe-core via Playwright against the project's running dev server, targeting WCAG 2.1 AA. Produces ui-check-results/a11y.json (compact violation JSON). Layer 2 of the design enforcement stack — runtime a11y verification that catches rendered issues static JSX analysis cannot (color contrast on real renders, ARIA in context, dynamic state). Use when user says "/ui-a11y", "check accessibility", "run a11y check", "WCAG audit", or when /ui-check invokes Layer 2.
disable-model-invocation: true
inputs:
  - "url: string (optional) — path to append to the base server URL (e.g. /dashboard); defaults to root"
outputs:
  - "ui-check-results/a11y.json — compact violation summary sorted by impact"
preconditions:
  - "Run from project root"
  - "A dev server must be running before invocation — this skill does not start it"
  - "uv must be installed"
  - "Playwright browser binaries must be installed — run: uv run --with playwright python -m playwright install chromium"
  - "ui-check-results/ will be created if absent"
---

# /ui-a11y

Run a browser-rendered WCAG 2.1 AA audit. Write compact results to `ui-check-results/a11y.json`. Exit non-zero if any violations are found.

## Step 1: Parse arguments and read config

Extract `--url {{url}}` flag (default: `""`). Read `.ui-config.json` at the project root if it exists; extract `devServerUrl` if present.

## Step 2: Discover dev server

If `devServerUrl` was read from `.ui-config.json`, use it as the base URL. Otherwise probe ports in order:

```bash
curl -s --max-time 2 -o /dev/null -w "%{http_code}" http://localhost:PORT
```

Ports: `3000`, `3001`, `5173`, `4173`. First port returning a 2xx or 3xx code is the base URL.

If no server is found, print:

```
Dev server not found. Tried ports 3000, 3001, 5173, 4173. Start with npm run dev before running /ui-a11y.
```

Exit non-zero.

## Step 3: Check prerequisites

Check `uv` is installed:

```bash
uv --version 2>/dev/null
```

If it fails, print: `uv not found. Install from https://docs.astral.sh/uv/` — exit non-zero.

## Step 4: Run axe audit

Create `ui-check-results/`:

```bash
mkdir -p ui-check-results
```

Write a Python runner to `$TMPDIR/a11y-runner.py`. The runner must use a PEP 723 inline script header and the `axe-playwright-python` library:

```python
#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["playwright", "axe-playwright-python"]
# ///

import json
import os
import sys
from playwright.sync_api import sync_playwright
from axe_playwright_python.sync_playwright import Axe

BASE_URL = os.environ["A11Y_BASE_URL"]
URL_PATH = os.environ.get("A11Y_URL_PATH", "")
OUT = os.environ["A11Y_RAW_OUT"]

with sync_playwright() as p:
    try:
        browser = p.chromium.launch(headless=True)
    except Exception:
        print("Playwright browser not found. Install with: uv run --with playwright python -m playwright install chromium")
        sys.exit(1)
    page = browser.new_page()
    page.goto(BASE_URL + URL_PATH)
    results = Axe().run(page, options={
        "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21aa"]},
        "resultTypes": ["violations"],
    })
    browser.close()

with open(OUT, "w") as f:
    json.dump(results.response, f)
```

Pass `BASE_URL`, `URL_PATH`, and output path via environment variables before executing:

```bash
A11Y_BASE_URL="<base url>" A11Y_URL_PATH="<url path>" A11Y_RAW_OUT="$TMPDIR/a11y-raw.json" uv run --script $TMPDIR/a11y-runner.py
```

If the runner exits non-zero, print the error and exit non-zero.

## Step 5: Build output

Parse `$TMPDIR/a11y-raw.json` (written by the Python runner as `json.dumps(results.response)`). For each entry in `violations`:

- `id` — rule id
- `impact` — severity string
- `count` — `nodes.length`
- `help` — rule description
- `helpUrl` — Deque link
- `selectors` — array of `nodes[N].target[0]` values (CSS selectors for affected elements)

Sort violations by impact order: `critical` → `serious` → `moderate` → `minor`.

Compute:
- `violation_count` = total violations array length
- `passed` = `violation_count === 0`
- `url` = full URL used for the audit (base + path)

## Step 6: Write output and exit

Write `ui-check-results/a11y.json`:

```json
{
  "passed": false,
  "url": "http://localhost:3000",
  "violation_count": 3,
  "violations": [
    {
      "id": "color-contrast",
      "impact": "serious",
      "count": 2,
      "help": "Elements must have sufficient color contrast",
      "helpUrl": "https://dequeuniversity.com/rules/axe/4.4/color-contrast",
      "selectors": [".btn-secondary", ".card-caption"]
    }
  ]
}
```

**Stdout** (one line):

```
A11y: 3 violations (2 serious, 1 moderate) — see ui-check-results/a11y.json
A11y: 0 violations — see ui-check-results/a11y.json
```

List only impacts with a non-zero count. Do not print full violation details to stdout.

**Exit codes**:
- `0` — `violation_count === 0`
- non-zero — use `violation_count` as exit value when violations found

## Behavioral constraint: one pass

Run the audit once. Do not loop or re-invoke based on the contents of `a11y.json`.
