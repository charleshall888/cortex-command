---
status: proposed
---

# Explicit path argument for the refine→research considerations hand-off

## Context

`/cortex-core:refine` hands clarify-critic alignment findings to `/cortex-core:research`. The original channel passed the findings *value* inline as `research-considerations="<multi-line bullets>"`. Because research parses its arguments from a model-read `$ARGUMENTS` string, a multi-line free-text value cannot safely contain `=` or `"`, so both skills carried character-stripping prose ("Strip or paraphrase away any embedded `=` or `"`" in refine; "Embedded `=` and `"` characters are not supported in the value" in research). That prose existed only because the channel was fragile.

This hand-off has now been designed three times — the original implementation, a deferral in #322 (which scoped itself to the resume-point offload), and the decision recorded here in #337. Re-litigation is itself a signal worth recording.

## Decision

Carry the considerations *text* over a file and pass only the file *path* in the argument:

- Refine writes the surviving Apply'd findings to `cortex/lifecycle/{slug}/research-considerations.md` (gitignored, overwriting — never appending) and emits `research-considerations-file=<path>` on the research dispatch.
- The write and the argument are **coupled** into one step: the argument is never emitted without a same-run fresh write, and it fires **only when at least one Apply'd alignment finding exists**. The no-findings path performs neither the write nor the argument.
- Research's orchestrator **body** reads the file and injects its literal **content** (never the path) into the three core-angle prompt placeholders. Reader contract: absent / missing / empty / whitespace-only ⇒ no injection, no halt.

Because only a benign path rides the argument, the escaping caveats are deleted; the channel can no longer misparse arbitrary text.

## Rejected alternatives

- **Implicit slug-derived file** — research always derives-and-reads the path in lifecycle mode (no argument to omit), so "no findings" must be materialized as a cleared/empty file. That mandatory clear-each-run discipline is the very kind of load-bearing prose this change removes — merely relocated — and it exposes the `resume=research` path (Clarify skipped → a leftover prior-run file is read as this run's signal). Rejected.
- **Full argument removal (zero-arg)** — to make the write structural without an argument would require a new `cortex-refine write-considerations` CLI verb (gratuitous ceremony, rejected by #322), engaging the parity/contract gates for no benefit over a coupled explicit path argument. Rejected.

## Consequences / Trade-off

A benign path argument is retained rather than a zero-argument interface, in exchange for an escaping-immune channel whose absence-semantics stays **structural** because the argument is coupled to the write (arg omitted = no read = no clear discipline needed). The producer disciplines that replace the escaping caveat — couple write+arg, overwrite-never-append, write-before-dispatch — are guarded by prose-contract tests rather than relied on by prose alone; this is an honest *trade* of an escaping caveat for test-guarded write semantics, not a free reduction.

The change is mechanically easy to reverse (swap the path key back for a value key), so its warrant rests primarily on the *surprising* leg (why keep an argument at all, and why coupling — not clearing — keeps absence structural) and the *real-trade-off* leg (path-arg vs. zero-arg vs. implicit-file), reinforced by the hand-off having been re-litigated three times — recording it stops a fourth round. This is recorded as a borderline ADR on the hard-to-reverse criterion; the recording value is the dominant justification.
