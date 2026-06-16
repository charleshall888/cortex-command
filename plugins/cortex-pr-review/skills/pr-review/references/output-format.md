# PR Review Output Format

The single source of truth for what `/pr-review` emits: the finding schema, the canonical label/decoration/severity/verdict-effect table, the grounding-and-verdict vocabulary, terminal-first rendering (with a GitHub-markdown posting branch), the blocking-first sort, and the observability footer.

## Grounding & Verdict Vocabulary

This vocabulary is the single source of truth for grounding and verdict derivation. Every finding and the terminal verdict use these terms exactly.

- **Grounded finding**: the reviewer located the finding's quoted text on the added (`+`) side of the diff AND cites the concrete `file:line` where it appears.
- **Evidence-weak finding**: the reviewer could not locate the quoted text on the `+` side. The finding is still **surfaced** (shown to the user), flagged `evidence-weak` — it is NOT dropped.
- **Surfaced findings**: all findings shown to the user = grounded findings + evidence-weak findings. Counted in `findings_surfaced` (with an evidence-weak sub-count).
- **Dropped findings**: findings the reviewer removed entirely (e.g., exact duplicates). Counted in `findings_dropped` with a reason. In this design, an ungroundable finding is surfaced as evidence-weak, never silently dropped — so grounding failure is a *surface event*, not a *drop*.
- **Degradation signals** (any one fires): (1) reviewer agent errored, timed out, or returned unparseable output; (2) diff missing or empty; (3) grounding step could not complete; (4) PR metadata fetch failed; (5) the reviewer surfaced ≥1 finding but grounded NONE of them; (6) an evidence-weak finding carries `severity = blocking` (an unverifiable blocker the reviewer could neither confirm nor dismiss).
- **Verdict derivation** (deterministic, evaluated top-to-bottom; keys on *grounded* findings, never on a label string):
  1. If any **grounded** finding has `severity = blocking` → `REQUEST_CHANGES`.
  2. Else if any degradation signal fired → `REVIEW_INCONCLUSIVE`.
  3. Else (every surfaced finding is grounded, none is blocking, no degradation) → `APPROVE`.

The verdict set is `APPROVE | REQUEST_CHANGES | REVIEW_INCONCLUSIVE`. There is no `COMMENT` verdict — non-blocking nuance is carried by labels under an `APPROVE` verdict.

## Finding schema

Every finding the reviewer emits carries these fields. The verdict-helper consumes them by these exact names.

- `severity` — one of `blocking` | `non-blocking`. The single verdict-driving axis. A `blocking` finding is a defect that must be fixed before merge; everything else is `non-blocking`. The decoration on the wire is rendered *from* this field, so the label and the verdict cannot diverge.
- `grounding` — one of `grounded` | `evidence-weak`, per the vocabulary above. Every finding carries a grounding status. Evidence-weak findings are surfaced, never silently dropped.
- `file:line` — the concrete citation locating the finding on the `+` side of the diff (e.g. `sync.ts:142`). For a `grounded` finding this is where the quoted text appears and is **human-checkable in the terminal output** — a reader (or the footer) can spot-check it. For an `evidence-weak` finding it is the reviewer's best-guess location with the grounding flag signalling the quote could not be confirmed.
- `label` — one of the Conventional Comments labels in the canonical table below. The label is presentation; `severity` drives the verdict.
- `body` — the finding text, written per the Voice guide.

## Canonical label / decoration / severity / verdict-effect table

One table maps every label to its decoration, its `severity`, and its effect on the verdict. The decoration is rendered *from* `severity` — they cannot diverge. There is exactly one blocking label form: `issue (blocking):`.

| Label          | Decoration       | severity       | Verdict effect (when grounded)                       |
| -------------- | ---------------- | -------------- | ---------------------------------------------------- |
| `issue`        | `(blocking)`     | `blocking`     | A grounded `issue (blocking)` forces `REQUEST_CHANGES`. |
| `suggestion`   | `(non-blocking)` | `non-blocking` | None. Surfaced under `APPROVE`.                      |
| `nitpick`      | `(non-blocking)` | `non-blocking` | None. Surfaced under `APPROVE`.                      |
| `question`     | none             | `non-blocking` | None. Surfaced under `APPROVE`.                      |
| `praise`       | none             | `non-blocking` | None. Surfaced under `APPROVE`.                      |
| `cross-cutting`| none             | `non-blocking` | None. Surfaced under `APPROVE`.                      |

Decoration vocabulary (Conventional Comments): `(blocking)`, `(non-blocking)`, `(if-minor)`. `(blocking)` appears only on `issue` (driven by `severity = blocking`). `(non-blocking)` is the default decoration for `suggestion`/`nitpick` and MAY be omitted (a bare `suggestion:` reads as non-blocking). `(if-minor)` is available on a `suggestion` whose fix is optional cleanup the reviewer would accept being deferred. `question`, `praise`, and `cross-cutting` carry no decoration.

Notes:

- A `suggestion` is **never** blocking and carries no blocking decoration. A defect that must be fixed is an `issue (blocking)`; there is exactly one blocking label form.
- There are no per-label caps and no alphabetical tie-break. The reviewer surfaces every finding worth surfacing; sort order is defined below.

### Canonical form

`<label>[ (decoration)]: <finding text>`

Examples:

- `issue (blocking): The retry loop in \`sync.ts:142\` never resets \`attempts\` after a successful call, so the next transient failure immediately trips the max-retry abort.`
- `suggestion: Extract the three duplicated timeout constants in \`client.ts\` into a single \`DEFAULT_TIMEOUTS\` record so the next tuning pass has one place to edit.`
- `nitpick (non-blocking): \`src/config.ts\` is missing a trailing newline; \`git diff\` flags it and the rest of the tree is consistent.`
- `question: Is the \`forceRefresh\` flag on \`loadConfig()\` intended to bypass the in-memory cache as well as the disk cache, or only the disk layer?`
- `praise: The new \`withDeadline\` helper in \`timeouts.ts\` collapses three ad-hoc timeout patterns into one composable wrapper, and the tests cover the cancel-vs-timeout race explicitly.`
- `cross-cutting: Three new call sites (\`api/users.ts\`, \`api/orgs.ts\`, \`api/teams.ts\`) each re-implement the same pagination guard. The pattern is worth extracting before a fourth caller arrives.`

## Sort order

Findings are sorted **blocking-first**, then by `file:line`:

1. Grounded `blocking` findings first (these drive the verdict and the reader needs them up top).
2. Then everything else, ordered by `file:line` (file path, then line number ascending).

This is the only ordering rule. There is no per-label cap and no alphabetical tie-break.

## Terminal-first output

Plain text is the default and only rendering until an explicit posting request. The terminal output contains:

1. The findings, sorted blocking-first then by `file:line`, each on the canonical `<label>[ (decoration)]: <finding>` form.
2. The verdict (`APPROVE` | `REQUEST_CHANGES` | `REVIEW_INCONCLUSIVE`), derived deterministically per the vocabulary above.
3. The footer (below).

Default terminal output contains **no** `<summary>` blocks, no HTML, and no markdown tables — those belong only to the posting branch.

### Footer

The footer reports observability fields so a reader can see what ran and what happened to every finding. The evidence-weak count is the headline observability fix — these findings vanish silently today.

- `model` — the model that actually ran, captured at dispatch. Do not pin or hardcode a model id; report whatever session-default / highest-available model executed the review.
- `findings_surfaced` — total surfaced, split into a grounded count and an evidence-weak sub-count.
- `findings_dropped` — findings genuinely removed (e.g., exact duplicates), with a per-reason breakdown. (Ungroundable findings are NOT dropped — they are surfaced as evidence-weak.)

Footer shape (illustrative; the model field reports whatever ran):

```
---
model: <model-that-ran>
findings_surfaced: 4 (grounded: 3, evidence-weak: 1)
findings_dropped: 1 (duplicate: 1)
verdict: REQUEST_CHANGES
```

## Posting mode (GitHub markdown)

Posting to GitHub is **not** the default. No-autopost is the default-and-only behavior unless the user explicitly requests posting via a flag/request; that request is the presentation gate that switches rendering from terminal plain-text to GitHub markdown.

Only in posting mode does the renderer emit GitHub-flavored markdown: a collapsible `<details>` block may wrap the non-blocking findings, and a markdown table may summarize the findings. The same finding schema, canonical labels, sort order, and footer fields apply; only the surface syntax differs.

<details>
<summary>Example: non-blocking findings collapsed in posting mode</summary>

- `suggestion: Extract the three duplicated timeout constants in \`client.ts\` into a single \`DEFAULT_TIMEOUTS\` record.`
- `nitpick (non-blocking): \`src/config.ts\` is missing a trailing newline.`

</details>

## Voice guide

Findings are read by busy reviewers and authors. Write like an engineer talking to another engineer, not like a language model producing prose.

- **No em-dashes.** Do not use `—` (U+2014) or `–` (U+2013) as a sentence-internal pause. Use a period, a comma, a colon, or parentheses. Hyphens inside compound words (`non-blocking`) are fine; em-dashes as rhetorical connectors are not.
- **No AI-tell vocabulary.** The following terms are forbidden in finding text: `delve`, `delves`, `delving`, `leverage`, `leverages`, `leveraging`, `robust`, `robustly`, `seamless`, `seamlessly`, `navigate` (as metaphor), `navigating` (as metaphor), `realm`, `tapestry`, `landscape` (as metaphor), `intricate`, `intricacies`, `furthermore`, `moreover`, `notably`, `crucially`, `it is worth noting`, `it is important to note`, `in the realm of`, `a testament to`, `underscore`, `underscores`, `underscoring`.
- **No validation openers.** Do not begin a comment with `Great question`, `Good catch`, `You're absolutely right`, `Excellent point`, or any variant. Open with the finding.
- **No closing fluff.** Do not end a comment with `Hope this helps`, `Let me know if you have questions`, `Happy to discuss`, or similar. Stop when the finding stops.
