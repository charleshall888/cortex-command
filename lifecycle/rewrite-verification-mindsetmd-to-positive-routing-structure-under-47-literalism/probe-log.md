# Probe Log — rewrite verification-mindset.md to positive routing structure under 4.7 literalism

This log is the single source of truth for probe-battery evidence across the
lifecycle. Each section below is populated by a specific phase task; tasks
must append to the designated section and not reorder headings.

## Baseline

<!-- Populated by the baseline-capture task. Records the pre-rewrite commit
     SHA, rail file paths, and any additional environment notes needed so
     ring-fence byte-identity diffs resolve deterministically. -->

## Pre-R1 Rail Hash

The following hashes were recorded before any R1 probe trial ran. Any
pre-trial or post-trial drift aborts the probe-apparatus.sh invocation with a
non-zero exit code (see `probe-apparatus.sh` for exit-code semantics).

```
a19d649aaee912513a13b3f509a05a5181e0d9f9a6dd1d8dfa8c2ff2d16ba0f3  claude/reference/verification-mindset.md
72246609a6e8311e91c07abb40fbb9abbb19c69c848308728f3269026bd74e6e  claude/reference/context-file-authoring.md
```

Source file (verify with `sha256sum -c`):
`lifecycle/rewrite-verification-mindsetmd-to-positive-routing-structure-under-47-literalism/rail-hashes-pre-r1.txt`

## Run-1 Trial Log

<!-- Populated by T3/T4/T5. One entry per trial: wording, category, trial
     index, output path, apparatus exit code, and the one-line provenance
     emitted by probe-apparatus.sh on success. -->

## Trial Disagreements

<!-- Populated by the Run-1 summary task. Lists trials within a wording
     category whose classifications disagree, with pointers to the offending
     stream-json transcripts. -->

## Per-Wording Summary

<!-- Populated by the Run-1 summary task. One row per wording with
     canonical / hedge / control counts and the resulting classification. -->

## Decision

<!-- Populated by the decision task. Records whether the rewrite proceeds,
     which sections are promoted to positive routing, and the section-
     classification rationale. -->

## Section Classification

<!-- Populated by the decision task. Per-section classification table (keep
     / rewrite / cut) with the probe evidence that justifies each
     classification. -->

## Post-Rewrite Comparison

<!-- Populated by R5 tasks (T11/T12/T13). Mirrors the §Run-1 Trial Log
     structure but for the post-rewrite rail state; references
     `rail-hashes-pre-r5.txt`. -->

## User Override

<!-- Populated only if the user overrides the decision task's verdict.
     Records the override, rationale, and any follow-up tickets opened. -->
