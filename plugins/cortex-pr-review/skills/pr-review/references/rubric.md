# PR Review Rubric

Decision criteria the single full-context reviewer applies to each candidate finding: one verdict-driving severity, plus a hard grounding gate. This rubric decides whether a finding is `blocking` and whether it is `grounded`; it does NOT define the label set, the decorations, or the verdict derivation. Those live in `output-format.md` — see its canonical label/decoration/severity/verdict-effect table and `## Grounding & Verdict Vocabulary`, the single source of truth for both.

## Philosophy

- Findings are grounded by evidence or they are surfaced as `evidence-weak` — never silently dropped. A finding whose quoted text cannot be located on the `+` side of the diff is still shown to the user, flagged `evidence-weak`, so a reader can judge it. This aligns with the `/cortex-core:critical-review` verification philosophy: a claim that cannot cite a concrete `file:line` is suspect, but the user, not a silent gate, decides what it is worth.

## Severity — the single verdict-driving axis

Every finding carries exactly one severity. Severity is the only axis that drives the verdict (`blocking` findings, once grounded, force `REQUEST_CHANGES`; everything else is surfaced under `APPROVE`). There is no separate signal axis and no separate solidness axis — grounding (below) subsumes the old solidness judgment.

Buckets: `blocking | non-blocking`

- `blocking` — correctness, security, data loss, or a contract break. Merging as-is ships a defect that must be fixed first. A `blocking` finding takes the single blocking label form `issue (blocking):` (see the canonical table in `output-format.md`); there is no other blocking label.
- `non-blocking` — quality, maintainability, clarity, style, taste, an open question, praise, or a cross-cutting observation. Useful to surface, but does not block merge. Carried by the `suggestion` / `nitpick` / `question` / `praise` / `cross-cutting` labels, all non-blocking.

The decoration on the wire (`(blocking)` vs `(non-blocking)`) is rendered *from* this severity field, so the label and the verdict cannot diverge. The mapping is the canonical table in `output-format.md`.

## Grounding gate

Grounding is a hard gate applied to every finding, not a score. For each finding the reviewer confirms the finding's quoted text appears on the added (`+`) side of the diff and cites the concrete `file:line` where it appears.

- `grounded` — the quoted text was located on the `+` side and the finding cites the `file:line`. The citation makes the claim human-checkable in the terminal output.
- `evidence-weak` — the quoted text could not be located on the `+` side. The finding is still **surfaced**, flagged `evidence-weak`, never silently dropped. An `evidence-weak` finding that also carries `severity = blocking` is an unverifiable blocker and fires a degradation signal (see `output-format.md` `## Grounding & Verdict Vocabulary`, signal 6).

The grounding status and the `file:line` citation are finding-schema fields; their definitions and the verdict consequences live in `output-format.md`. This rubric only states the criterion the reviewer uses to assign the status.

## Drop-reason taxonomy

A finding is **surfaced** (grounded or evidence-weak) by default. Genuine drops are rare and each carries exactly one reason, reported in the footer's `findings_dropped` per-reason breakdown (see `output-format.md` `### Footer`).

- `duplicate` — the same finding was emitted more than once; the exact duplicate is removed and counted once. This is the canonical drop reason in this design.
- `linter-class` — a style, formatting, or linter-enforced issue filtered by design so the review does not duplicate tooling output.

An ungroundable finding is NOT a drop — it is surfaced as `evidence-weak`. There are no per-label caps and no `over-cap` drop reason.
