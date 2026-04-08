---
schema_version: "1"
uuid: e4f5a6b7-c8d9-0123-efab-234567890123
id: "021"
title: "Define evaluator rubric for software features (spike)"
type: spike
status: complete
priority: low
parent: "018"
blocked-by: []
tags: [overnight, evaluator, quality, spike]
created: 2026-04-03
updated: 2026-04-08
discovery_source: research/harness-design-long-running-apps/research.md
session_id: null
lifecycle_phase: specify
lifecycle_slug: define-evaluator-rubric-for-software-features-spike
complexity: complex
criticality: low
spec: lifecycle/define-evaluator-rubric-for-software-features-spike/spec.md
areas: [overnight-runner,lifecycle]
---

# Define evaluator rubric for software features (spike)

## Context from discovery

The harness design article's evaluator agent worked because the team defined a rubric — four weighted criteria — before building the mechanism. For software delivery, tests already provide strong objective evaluation signal. An evaluator agent would only add value for spec compliance cases that tests don't encode.

This spike should not begin until item 019 (tighter spec template and plan verification requirements) has been implemented and some overnight sessions have run. If 019 eliminates the spec compliance failures, the evaluator may not be needed. If failures persist, this spike defines the rubric grounded in those observed failures.

## What this spike should answer

1. Are there overnight failures in the current session history where a feature passed tests but violated spec intent? If so, what were the common characteristics?
2. For those failure patterns, can they be prevented by tighter plan.md verification requirements (019), or do they require an independent agent checking something tests cannot?
3. If an independent evaluator is warranted, what are the specific criteria — stated as observable, verifiable checks — that it would apply?

The output is a rubric definition, not an implementation. The evaluator agent implementation is a separate ticket that should only be created if this spike produces a concrete rubric.

## Do not start before 019

019 is the simpler alternative to this ticket. Many of the failures an evaluator would catch can be prevented upstream by requiring explicit acceptance criteria and runnable verification steps. Run 019 first and observe overnight behavior before investing in evaluator infrastructure.
