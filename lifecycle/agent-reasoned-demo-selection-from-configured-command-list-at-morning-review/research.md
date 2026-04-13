# Research: Agent-reasoned demo selection from configured command list at morning review

## Codebase Analysis

### Files That Will Change

**Primary:**
1. `skills/lifecycle/assets/lifecycle.config.md` — template currently has `# demo-command:` as a single commented-out string field (line 4). Must be replaced (or supplemented) with a `demo-commands:` list schema (each entry: `label:` + `command:`).
2. `skills/morning-review/references/walkthrough.md` — Section 2a is the primary target. Guard 1 is keyed to `demo-command:` (single string); the demo offer block, print template, and edge-cases table all reference `demo-command` verbatim. All must be updated.
3. `skills/morning-review/SKILL.md` — Step 3 item 2 references `demo-command` and must be updated to reference the `demo-commands:` list.
4. `docs/overnight.md` — lines 52 and 65 document `demo-command`; must be updated.

**Project-root `lifecycle.config.md`**: does not have `demo-command:` set (the field is absent, not commented). No live value to migrate in this repo.

### Existing Patterns and Conventions

**Current `demo-command:` parsing (6-rule protocol in Section 2a Guard 1):**
- Read file; strip leading whitespace per line
- Lines beginning with `#` are comment lines — ignored
- Extract everything after the first `:` character; strip leading/trailing whitespace
- Reject values with byte < 0x20 except `\t` (control characters)
- Empty/missing values → treat as unset
- Do NOT strip inline `#` comments (shell commands may contain `#`)
- Parser form: `sed -n 's/^[[:space:]]*demo-command:[[:space:]]*//p'` — splits on first `:` only (NOT `awk -F:`, which breaks on values containing `://`)

**A YAML list is structurally incompatible with the existing sed-based parser.** New parsing rules for a multi-entry block list must be explicitly specified.

**Section 2a guard chain (established by #071):**
- Guard 1: `demo-command` absent/empty/malformed → skip
- Guard 2: `$SSH_CONNECTION` set → skip (remote session)
- Guard 3: `git rev-parse --verify {integration_branch}` exits non-zero → skip

Guards 2 and 3 are unchanged by this feature. Guard 1 is the only guard affected.

**Security boundary (hard constraint from #071 R10 / NR2):**
- The agent MUST NOT execute the demo command — it only prints it for the user
- This applies equally to any command selected from a list

**Placeholder conventions:** `{placeholder}` braces in skill text are LITERAL — agents substitute at runtime. `{demo-command}` in the print template must be replaced with the selected entry's label and command but the brace convention is preserved.

**Worktree creation:** must use `git -c core.hooksPath=/dev/null worktree add` (neutralizes `post-checkout` hooks through tracked hooks directories). This is a load-bearing implementation detail from #071 retro Problem 5.

### Integration Points and Consumers of `lifecycle.config.md`

| Consumer | Fields Read | Impact |
|---|---|---|
| `skills/morning-review/references/walkthrough.md` Section 2a | `demo-command` (Guard 1) | **Must change** — primary target |
| Overnight runner (`claude/overnight/*.py`) | Does NOT read `lifecycle.config.md` | No impact |
| Lifecycle skill phases | `type`, `test-command`, skip fields | No impact |
| `docs/overnight.md` | Documents `demo-command` | Documentation update needed |

### No Tests

No test files cover morning-review behavior or `demo-command` parsing. The behavior is skill-text only — mechanically untestable. This is consistent with the backlog's characterization ("the untestable part is the selection logic").

---

## Web Research

### Prior Art

**Diff-to-structured-output pattern (commit message generators):**
- Feed `git diff --cached` to an LLM with chain-of-thought → structured output. Key papers/implementations: Samuel Liedtke's CoT commit message generator; Harper Reed's `prepare-commit-msg` hook. Standard pipeline: diff in → reasoning → structured JSON out.

**Closest config schema prior art — Warp Terminal YAML Workflows:**
- Schema: `name` (required) + `command` (required) + optional `description`, `tags`, `arguments`. This is the canonical "human-readable label + shell command" YAML pattern for developer tools.

**Dynamic constrained selection from a user list:**
- Dynamic Pydantic enum pattern: build `enum.Enum("CategoryEnum", {c: c for c in categories})` at call time from the config list. Forces the model to output only configured values — no hallucinated options.
- `Literal["option_a", "option_b"]` types work reliably across Anthropic models. `BeforeValidator` + fuzzy fallback for graceful degradation.
- Chain-of-thought before final selection consistently improves accuracy (~12–13% improvement on classification tasks).

### Key Anti-Patterns

- Prompt-only list instruction without schema enforcement → models hallucinate unlisted values
- Feeding raw unified diff without filtering → wastes tokens, confuses model with line-number noise
- `awk -F:` for config parsing → breaks on values containing `://`

---

## Requirements & Constraints

### From `requirements/project.md`

- **File-based state**: All state uses plain files — no database. Config schema and selection output must fit this constraint.
- **Context efficiency**: Verbose tool output is filtered before entering context. Diffing the integration branch must not produce unbounded output in context.
- **Complexity earns its place**: The simpler solution is correct. Agent-reasoned selection is "explicitly accepted as the filter" — implementation scope should not inflate around this.
- **Security**: The agent MUST NOT execute any demo command (existing hard boundary from #071 R10).
- **Morning is strategic review**: Demo offer is acceptable only if it never blocks the walkthrough and auto-advances regardless of user response.

### From `requirements/pipeline.md`

- **Integration branch persistence**: `overnight/{session_id}` branches persist post-session for PR creation — this is what enables the morning-review diff. The constraint is permanent.
- **Integration branch is not guaranteed to exist**: Guard 3 exists because branches can be pruned. Any diff operation must be atomic with the branch-existence check, or protected by an existence guard immediately before the diff.
- **Runner does not read `lifecycle.config.md`**: Adding `demo-commands:` does not require changes to `runner.sh`, `parser.py`, or `batch_runner.py`.

### Critical Pre-existing Non-Requirements from #071 Spec

The #071 spec (lifecycle `agent-driven-demoability-assessment-and-validation-setup-at-morning-review`) contains two Non-Requirements that directly conflict with the #072 proposal:

> **NR1**: No "smart demoability assessment" layer. The agent does not read the diff, does not read per-feature spec.md, and does not classify which features are "demoable." Section 2a is triggered solely by `demo-command` being configured + branch existing + non-remote session. The original ticket's framing of "the agent reasons about whether features warrant validation" is **explicitly discarded as untestable false-precision**.

> **NR7**: No conditional offer based on diff content (e.g., "skip if only docs changed"). The offer fires whenever `demo-command` is set and guards pass. A user with a docs-only session pays a one-keystroke decline cost; this is cheaper than the spec-ambiguity of "what counts as docs-only."

**These were deliberate descope decisions from a full research-and-review cycle.** Backlog #072 proposes to build exactly what NR1 and NR7 rejected. The Spec phase must engage with this directly — either documenting why the reasoning no longer applies, or identifying what changed since #071 shipped.

---

## Tradeoffs & Alternatives

### Alternative A: Label + command list, pure agent reasoning (recommended)

`lifecycle.config.md` gains a `demo-commands:` list; each entry has `label:` and `command:`. In Section 2a, after guards pass, the agent diffs the overnight integration branch, reads the list, and selects the most relevant entry (or none).

**Pros**: Minimal authoring friction; no path/tag taxonomy to maintain; agent already has full diff context in scope from Section 2a; testable contract (one offer or none, from the configured list, auto-advancing) is preserved regardless of which entry is chosen.

**Cons**: Selection quality is untestable. For sessions with many demo modes (>5), inconsistent selection is possible.

### Alternative B: Entries with `areas:` or `paths:` hints

Each `demo-commands:` entry adds an optional `areas:` or `paths:` field. Section 2a applies mechanical pre-filtering before agent reasoning.

**Rejected**: explicitly violates "no `demo-paths:` to maintain" design constraint stated in backlog #072. Adds parsing complexity for partial determinism that still relies on agent judgment as a tiebreaker.

### Alternative C: Rules-based matching only

Selection is purely mechanical via file-pattern globs — no agent reasoning.

**Rejected**: discards semantic signal the agent already possesses (feature intent from specs, not just file paths). High maintenance burden. Inconsistent with "agent judgment accepted for bounded outputs."

### Alternative D: Separate config-driven preprocessor

Extract selection into a standalone script called before the walkthrough; Section 2a reads its output.

**Rejected**: over-engineers a simple problem (complexity: simple), adds a new artifact lifecycle, fragments context that is already co-located in Section 2a.

### Backward Compatibility

Additive migration path: Guard 1 checks for `demo-commands:` first; if present and non-empty, uses list-based agent selection. If absent, falls back to `demo-command:` (existing behavior unchanged). Projects that haven't added `demo-commands:` continue to work. **The spec must make the fallback ordering explicit** — specifically: when agent selects "none relevant" from `demo-commands:`, does the `demo-command:` fallback fire, or does Section 2a skip silently? Both behaviors have problems (see Open Questions).

---

## Adversarial Review

### Failure Modes

1. **All-failed sessions produce an empty diff**: If the overnight session has zero completed features, the integration branch exists (Guard 3 passes) but contains no merged feature work. The diff against main is empty or only contains scaffolding commits. The agent has no meaningful signal and cannot select a command. The proposed approach has no "skip if no completed features" guard — and could offer a demo for a session where nothing demoable was produced.

2. **Wrong diff base**: The correct diff base is the merge-base of `main` and the integration branch: `git diff $(git merge-base main {integration_branch})..{integration_branch}`. Using `git diff main..{integration_branch}` includes commits on main that landed after the integration branch was created, producing a misleading diff if main has advanced (e.g., after a prior overnight PR was merged).

3. **Unbounded diff output in context**: A large overnight session produces thousands of lines of diff. The morning-review agent is already running with substantial context. A raw `git diff` risks overwhelming context limits or degrading analysis quality. Mitigation: use `git diff --stat` (file paths + line counts only) or reference the morning report's already-validated "Key files changed" sections — both avoid the unbounded diff problem and eliminate the merge-base race condition.

4. **YAML list parsing is not specified**: The existing 6-rule parser handles a single-value line. A `demo-commands:` block list requires multi-line lookahead, indentation sensitivity, and YAML block-scalar handling — none of which the current sed-based approach supports. The spec must pin the parsing rules precisely, including how colons in command values are handled.

5. **"Nothing relevant" case is unspecified**: When the agent reasons that no command is relevant, Section 2a presumably skips silently. But the backward-compatibility ordering creates a question: does `demo-command:` then fire as a fallback? If yes, the single-command behavior always fires as a catch-all, eliminating the "smart selection" value proposition. If no, users who configured both fields lose the single-command offer. The spec must decide.

6. **Reversal of NR1/NR7**: The feature is proposing to build exactly what #071's spec named as Non-Requirements and explained why they were rejected. The reasoning behind NR1 ("untestable false-precision") and NR7 ("one-keystroke decline cost is cheaper than spec-ambiguity of what counts as relevant") must be directly engaged with — not silently ignored.

### Security Concerns

7. **Injection surface grows from 1 to N**: With `demo-commands:`, a malicious PR could add a plausible-sounding entry with a harmful command and stage commits touching the "right" files to trigger selection. The existing single-command model requires the attacker to replace the only entry; the list model only requires adding one entry. The security prohibition in walkthrough.md (R10-equivalent) must be explicitly broadened to cover the "N commands, agent picks one" case.

### Assumptions That May Not Hold

8. **"Agent judgment is fine for bounded outputs"**: The user's memory note was recorded for a different feature. For demo-command selection, the output is either "offer this command" or "offer nothing" — and the boundary between those outputs is undefined. There is no defined threshold for the agent's certainty, unlike closed-enum status selection where any valid output is acceptable.

---

## Open Questions

1. **NR1/NR7 reversal justification** — Why does the reasoning that led to NR1 ("untestable false-precision") and NR7 ("one-keystroke decline cheaper than spec-ambiguity") no longer apply? What changed since #071 shipped? *Deferred: must be resolved in Spec by asking the user.*

2. **Fallback ordering when agent selects "none"** — When `demo-commands:` is configured and the agent selects no relevant entry, should `demo-command:` (the single-string fallback) fire? Or should Section 2a skip silently? Each behavior is problematic for a subset of users. *Deferred: must be resolved in Spec by asking the user.*

3. **Diff scope and granularity** — Should Section 2a use `git diff --stat`, a file-list-only approach, the morning report's existing "Key files changed" data, or a full unified diff? Full diff risks overwhelming context; file list only may be insufficient for label-to-change matching. *Deferred: resolved in Spec.*

4. **YAML list parsing format** — Inline array (`demo-commands: [{label: "...", command: "..."}]`) vs. block scalar (multi-line YAML list)? How are colons in command values handled? Are control-char rejection rules from R3 applied per-entry? *Deferred: resolved in Spec.*

5. **Guard: skip when no completed features** — Should a new guard fire before the diff when `overnight-state.json` shows zero completed features (nothing demoable produced)? *Deferred: resolved in Spec.*
