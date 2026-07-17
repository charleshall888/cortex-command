---
schema_version: "1"
uuid: 2bdd3566-8d3d-4c51-9395-dc6b71a16934
title: validate.yml has been red since 2026-07-13 and main has no required status checks, so nothing gates merge
status: complete
priority: high
type: bug
created: 2026-07-16
updated: 2026-07-17
tags: ['ci', 'enforcement', 'tests']
areas: ['tests']
---
> **SHIPPED except the ruleset (2026-07-17).** What landed: (1) the red step is fixed — the six unresolved citations all pointed at gitignored/untracked local dirs (`lifecycle/sessions/`, a leftover `lifecycle/feat/` probe dir), and `_slug_resolves` now consults the git index (the same authority `git ls-files` enumerates from), so a green local run IS evidence CI is green; (2) every blocking step carries `if: !cancelled()`, so one red step can no longer hide the rest; (3) the two deferred candidates (config parity, dormancy pin) are blocking steps — ADR-0017 and docs/setup.md updated; (4) the ~28 order-dependent dashboard failures were root-caused and fixed: `dashboard/templates/` is a namespace package, so `as_file()` extracted templates to a TemporaryDirectory that a module reload (test_cli_dashboard's PID-path tests) orphaned for the next cyclic GC to delete — the loader now resolves through the regular `dashboard` package to a stable real path. The 2 remaining full-suite reds are the known pre-existing refine-writeback pins (stale prose contract superseded by #378's reroute), tracked separately. **Still open, deliberately: the branch ruleset.** Required status checks end direct pushes to `main` — an explicit operator decision this ticket can specify but not land. Spec for when ruled: add a `required_status_checks` rule for the `validate` job (plus a pull-request rule) to the existing `protect-main-history` ruleset or a sibling.

## Why

The repository's test enforcement does not exist in the form its documentation assumed. Two independent findings, both verified against GitHub during lifecycle 380:

First, `validate.yml` has failed on every push to `main` since 2026-07-13 — four consecutive runs, last green being the 2026-07-10 release. The failing step is the blocking lifecycle-reference-resolve test, whose assertion reports unresolved `lifecycle/<slug>` citations. GitHub Actions aborts a job at its first failing non-`continue-on-error` step, so every blocking step below it has been marked `skipped` for days. Four blocking test steps have not executed since 2026-07-13 and nobody noticed, because a red pipeline that nothing depends on is indistinguishable from a green one.

Second, `main` has no branch protection at all: the protection endpoint returns 404, and the sole ruleset carries only `deletion` and `non_fast_forward` — no required status checks, no pull-request rule. Four red runs have already landed on `main` as direct pushes. "CI gates merge" was never true of this repo, which is why lifecycle 380 corrected that claim out of two docs and an ADR rather than trying to make it true by adding workflow steps: merge gating lives in a branch ruleset, and no workflow file can supply it.

Compounding both: the reference-resolve test passes locally and fails in a fresh clone, because it enumerates via `git ls-files` and resolves via filesystem `is_dir()`, so gitignored and untracked directories that exist only on a developer's machine mask the failure. A green `just test` is not evidence CI is green.

## Role

After this lands, the pipeline's actual state is known and its claims match it. Either the blocking steps run and gate something, or the docs say plainly that enforcement is developer-run — with no third state where a red pipeline sits unnoticed behind steps that never execute. A developer can tell from a local run whether CI will agree, and a test added to the blocking allowlist is a test that actually runs.

## Integration

Touches the validate workflow's step ordering and failure semantics, the repository's branch ruleset, and the local-versus-CI divergence in the reference-resolve test's enumeration. It also settles a question lifecycle 380 deliberately deferred: whether the config parity test and the new dormancy pin belong in the blocking allowlist. Those two are currently developer-run only, which the docs now state accurately — a decision here supersedes that wording.

## Edges

- Fixing the red step and gating merges are separable; either alone is an improvement, and the ordering fix (so later steps run) is independent of both.
- **A second failure set is hiding behind the red step (measured 2026-07-17).** A clean-tree full-suite run has **30 failures**, only ~2 of which are the known-pre-existing ones (refine-writeback, mcp-DNS). The other ~28 are almost all `cortex_command/dashboard/tests/test_templates.py` (plus `test_feature_cards_pr_url.py`), and they are **test-order pollution, not real breakage**: they pass in isolation and fail only in a full-suite run. This ticket's own note that "later steps are `skipped` behind the first failure" is likely why they have gone unseen. Consequence for sequencing: **the ordering fix and required checks will surface them immediately** — fixing step order without fixing the pollution turns 28 order-dependent failures into a merge block. Whether that is in this ticket's scope or a sibling is a decision, but it cannot be discovered after the fact.
- Branch protection is a repo-admin action, not a code change — this ticket can specify it but cannot land it.
- Turning on required checks changes the operator's direct-push workflow to `main`; that is a real cost and an explicit decision, not a side effect.

## Touch points

- `.github/workflows/validate.yml` — the blocking allowlist and its step order; later steps are `skipped` behind the first failure.
- `tests/test_lifecycle_references_resolve.py` — enumerates via `git ls-files` but resolves via filesystem `is_dir()`; passes locally, fails in a fresh clone.
- The `main` branch ruleset — carries only `deletion` and `non_fast_forward`.
- `justfile` — the `test` recipe, which nothing in CI invokes.
- `tests/test_lifecycle_config_parity.py`, `tests/test_lifecycle_config_dormant_template.py` — the two deferred allowlist candidates from lifecycle 380.
