# Research: auto-derive-lifecycle-slug-from-prose-style-invocation-args

## Scope anchor

Make the slug-derivation prose in `skills/lifecycle/SKILL.md` Step 1 explicit about handling prose-style invocation arguments. When `$ARGUMENTS` is non-empty but its first word is not a valid kebab-case slug (i.e., the user typed a prose description), the skill should derive a 3–6 word kebab-case slug from the prose, announce it, and proceed without asking for confirmation. The user can override via re-invocation with their preferred slug (renaming an existing lifecycle directory is explicitly out of scope per the ticket). Apply the same fix to `skills/refine/SKILL.md` Step 1 Context-B branch where prose input is currently passed through unchanged as the "topic name."

## Current behavior in the source

`skills/lifecycle/SKILL.md:45` defines the parse rule as:

> Feature/phase from invocation: $ARGUMENTS. Parse: first word = feature name, second word (if present) = explicit phase override.

Line 47 adds:

> Determine the feature name from the invocation. Use lowercase-kebab-case for directory naming. When linked to a backlog item, use the canonical `slugify()` from `cortex_command.common`.

This implicitly assumes the first word IS already kebab-case. There is no explicit "if input is prose, derive slug" branch. The current friction is emergent: the agent sees `let's`, recognizes it isn't a slug, but has no prescription for what to do — different agents may ask via `AskUserQuestion`, default-pick silently, or pick and announce. The variability is what the ticket targets.

`skills/refine/SKILL.md:39` has the parallel gap on the resolver exit-3 path:

> Exit 3 — no match. Switch to Context B (ad-hoc topic) per `../lifecycle/references/clarify.md` §1 and treat the input as the topic name.

"Treat the input as the topic name" — when the input is multi-word prose, the topic name then carries punctuation/spaces and is unsuitable as a directory slug. No explicit derivation step.

## Existing slug-derivation primitives

`cortex_command/common.py` defines `slugify(title)`. Empirical test against the prior lifecycle's invocation prose:

```
input:  "let's update our processes/skills and/or claude.md to make it clear this is a long term project ..."
output: "lets-update-our-processes-skills-and-or-claudemd-to-make-it-clear-this-is-a-long-term-project"
```

`slugify()` produces a 90+ character slug from sentence-length prose — verbatim word retention is unsuitable for a directory name. The canonical helper is fit for **titles** (which are already concise), not for **prose descriptions**.

This is the design constraint the ticket implicitly identifies: prose → slug needs *semantic distillation*, not character-level normalization. That is precisely the kind of decision the model is well-suited to make in-context, and the SKILL.md prose can simply prescribe the constraint and let the model do the distillation.

## Detection rule (prose vs. slug)

A valid kebab-case slug, by repo convention:

- Lowercase letters, digits, hyphens only
- No leading/trailing hyphens
- Length 3–60 characters (longer is allowed but unusual; the ticket asks for 3–6 *words*, which typically lands in the 15–50 character range)
- No spaces, no underscores, no punctuation other than hyphens

Anything else (contains spaces, punctuation like `'` `/` `.` `,`, uppercase letters, or is unparseably long) is prose and triggers derivation.

This regex captures the valid-slug shape: `^[a-z0-9]+(-[a-z0-9]+)*$`.

## Derivation approach (delegated to the model in prose)

Three viable approaches considered:

1. **Algorithmic stopword strip + first-N-words**: pure-Python, predictable, but stopword lists drift and the result is often awkward (e.g., "update-our-processes-skills" misses the actual intent "long-term-solutions"). Brittle.
2. **Algorithmic + LLM polish**: two-step where Python emits a candidate and the model refines. Adds an extra round-trip with no clear benefit over option 3.
3. **Pure model-side distillation guided by prose criteria**: SKILL.md tells the agent to pick a 3–6 word kebab-case slug that summarizes the prose's intent, and proceed. The model does what it does well (semantic compression) with clear constraints.

Approach 3 fits the project's "prescribe What and Why, not How" design principle (CLAUDE.md). It also has no failure modes that approach 1 or 2 don't have, because the model still produces a slug under all three.

## Edge cases & handling

- **Short prose (1–2 words)**: use the canonical `slugify()` directly — those cases land within reasonable slug length.
- **Single word with apostrophe (`let's`)**: treat as prose (apostrophe makes it invalid slug); model derives.
- **Prose with no clear noun phrase**: model picks the best 3–6 words it can. Worst case is a slightly awkward slug; user can re-invoke with override.
- **Derived slug collides with existing `cortex/lifecycle/{slug}/`**: the existing phase-detection branch will treat the invocation as a resume of the prior lifecycle. If that's not what the user intended, they can rename their prose to disambiguate and re-invoke. The skill should not silently append a counter — that creates ghost lifecycles.
- **`$ARGUMENTS` empty**: existing fallback path unchanged (scan for incomplete lifecycle dirs).
- **`$ARGUMENTS` is a valid slug but doesn't match a backlog item**: existing exit-3 path unchanged (no match, proceed with the slug as feature name).

The collision case is the only one with a substantive design call: do we (a) treat collision as a resume signal, or (b) force the user to disambiguate? Reading existing Step 2 behavior — phase detection already routes to the existing lifecycle when the directory exists — treating collision as resume is consistent with current behavior. So (a) wins by alignment, no SKILL.md change needed for the collision case.

## /cortex-core:refine in scope

Backlog #205's Problem statement explicitly names refine: "`/cortex-core:lifecycle` (and by extension the clarify phase inside `/cortex-core:refine`)". The same prose-handling gap exists in refine's Step 1 Context-B branch (line 39: "treat the input as the topic name" — silently passes prose through).

The fix in refine clarify §1 mirrors the lifecycle fix: when the resolver returns exit 3 and the input is prose, derive a slug for `cortex/lifecycle/{lifecycle-slug}/` directory creation, announce it, and use that slug throughout refine's downstream phases.

## Insertion-point summary

| File | Insertion point | Style |
|---|---|---|
| `skills/lifecycle/SKILL.md` | Step 1 (~line 45), augment the "Parse" rule with a prose-handling branch and slug-derivation prescription | Existing prose-instruction style; add ~6–12 lines between current line 45 and line 47 |
| `skills/refine/SKILL.md` | Step 1 Exit 3 branch (~line 39), augment with prose-handling branch | Mirror the lifecycle prescription so the two surfaces stay consistent |

Both files are the canonical sources under `skills/`. The plugin mirrors at `plugins/cortex-core/skills/lifecycle/SKILL.md` and `plugins/cortex-core/skills/refine/SKILL.md` regenerate via the pre-commit dual-source hook (per CLAUDE.md: "Auto-generated mirrors at `plugins/cortex-core/{skills,hooks,bin}/` regenerate via pre-commit hook; edit canonical sources only").

## Open Questions

None. The clarify-critic findings closed every gap (mechanism, terminology, refine scope, edge cases, alignment framing). Implementation can proceed to spec.
