# PR Review Output Format

Wire format for comments emitted by the pr-review synthesizer. Every surviving finding from the rubric gate is rendered as a Conventional Comments entry using exactly one of the six labels below. The rubric decides whether a finding survives and which label it takes; this file specifies how that label is written on the wire.

## Scope

- This file covers the six Conventional Comments labels, their decorators, and voice rules.
- This file does NOT cover fenced suggestion blocks, GitHub review-comment anchoring fields, or fuzzy line-anchoring rules. Those belong to ticket 005.

## Labels

Each label is written as a prefix on the first line of the comment body, followed by a space and the finding text. Decorators, when present, are placed in parentheses immediately before the colon.

Canonical form: `<label>[ (decorator)]: <finding text>`

### issue:

- Format: `issue (blocking): <finding>` by default. The `(blocking)` decorator is required; `issue:` without a decorator is malformed.
- Decorator rule: always `(blocking)`. An `issue:` is a rubric `must-fix` and blocks merge by construction.
- Example:
  - `issue (blocking): The retry loop in \`sync.ts:142\` never resets \`attempts\` after a successful call, so the next transient failure immediately trips the max-retry abort.`

### suggestion:

- Format: `suggestion: <finding>` by default; `suggestion (blocking): <finding>` when the underlying gate severity is `must-fix` and the reviewer is proposing a specific fix shape rather than just flagging the defect.
- Decorator rule: `(non-blocking)` is the default and MAY be omitted (bare `suggestion:` is read as non-blocking). `(blocking)` is permitted only when the rubric severity is `must-fix`; otherwise do not mark a suggestion as blocking.
- Example (default, non-blocking):
  - `suggestion: Extract the three duplicated timeout constants in \`client.ts\` into a single \`DEFAULT_TIMEOUTS\` record so the next tuning pass has one place to edit.`
- Example (blocking variant):
  - `suggestion (blocking): Wrap the \`fs.writeFile\` call in \`persist.ts:88\` in a try/catch; an EIO here currently crashes the worker and drops the in-flight batch.`

### nitpick:

- Format: `nitpick (non-blocking): <finding>`. Spec-canonical label is `nitpick:`, never `nit:`.
- Decorator rule: always `(non-blocking)`. A nitpick is a rubric `nit` and never blocks merge.
- Example:
  - `nitpick (non-blocking): The parameter ordering in \`formatRange(end, start)\` reads backwards from every other range helper in this file; consider \`formatRange(start, end)\` for symmetry.`

### question:

- Format: `question: <finding>`. No decorator.
- Decorator rule: `question:` carries no `(blocking)` or `(non-blocking)` marker. Questions are never blocking and are never paired with a prescriptive fix; if you have a fix in mind, route it to `issue:` or `suggestion:` instead.
- Example:
  - `question: Is the \`forceRefresh\` flag on \`loadConfig()\` intended to bypass the in-memory cache as well as the disk cache, or only the disk layer? The call sites in \`boot.ts\` and \`reload.ts\` seem to assume different answers.`

### praise:

- Format: `praise: <finding>`. No decorator.
- Decorator rule: `praise:` carries no decorator. Praise is earned by strong evidence and real impact, not by tone; it is never blocking.
- Example:
  - `praise: The new \`withDeadline\` helper in \`timeouts.ts\` collapses three ad-hoc timeout patterns into one composable wrapper, and the tests cover the cancel-vs-timeout race explicitly.`

### cross-cutting:

- Format: `cross-cutting: <finding>`. No decorator.
- Decorator rule: `cross-cutting:` carries no decorator. It may reference multiple files or the PR as a whole and bypasses the usual locality expectation; blocking status, when relevant, is inherited from any embedded `issue:` framing rather than from the label itself.
- Example:
  - `cross-cutting: Three new call sites (\`api/users.ts\`, \`api/orgs.ts\`, \`api/teams.ts\`) each re-implement the same pagination guard. The pattern is worth extracting before a fourth caller arrives.`

## Voice guide

Findings are read by busy reviewers and authors. Write like an engineer talking to another engineer, not like a language model producing prose.

- **No em-dashes.** Do not use `—` (U+2014) or `–` (U+2013) as a sentence-internal pause. Use a period, a comma, a colon, or parentheses. Hyphens inside compound words (`must-fix`, `non-blocking`) are fine; em-dashes as rhetorical connectors are not.
- **No AI-tell vocabulary.** The following terms are forbidden in finding text: `delve`, `delves`, `delving`, `leverage`, `leverages`, `leveraging`, `robust`, `robustly`, `seamless`, `seamlessly`, `navigate` (as metaphor), `navigating` (as metaphor), `realm`, `tapestry`, `landscape` (as metaphor), `intricate`, `intricacies`, `furthermore`, `moreover`, `notably`, `crucially`, `it is worth noting`, `it is important to note`, `in the realm of`, `a testament to`, `underscore`, `underscores`, `underscoring`.
- **No validation openers.** Do not begin a comment with `Great question`, `Good catch`, `You're absolutely right`, `Excellent point`, or any variant. Open with the finding.
- **No closing fluff.** Do not end a comment with `Hope this helps`, `Let me know if you have questions`, `Happy to discuss`, or similar. Stop when the finding stops.

## Anti-patterns

### Dropping style findings as `linter-class` instead of emitting `nitpick:`

If a rubric gate produced a `nitpick:` finding with `solidness = solid` and `signal = high`, emit it. Do not invent a secondary "linter-class" bucket that silently discards style findings the rubric already promoted.

- Don't emit: `nitpick: Missing trailing newline.` — drop as `linter-class`.
- Instead: either (a) the rubric gate did not produce a nitpick (because `signal` was not `high`) and there is nothing to emit, or (b) the rubric gate did produce one and the full Conventional Comment is written, e.g. `nitpick (non-blocking): \`src/config.ts\` is missing a trailing newline; most editors and \`git diff\` flag it, and the rest of the tree is consistent.`

The rubric is the only place findings are filtered. The output-format layer renders what survives; it does not re-gate.
