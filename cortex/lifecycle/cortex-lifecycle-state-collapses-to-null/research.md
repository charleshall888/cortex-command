# Research: cortex-lifecycle-state collapses to null on any malformed events.log line

**Clarified intent:** Eliminate the split-brain where `cortex-lifecycle-state` (`cortex_command/lifecycle/state_cli.py`'s `_reduce_events`, jq-1.8.1 reduce-to-null semantics) silently degrades the spec-phase tier/criticality gates to `simple` whenever any single `events.log` line fails JSON parse — `main()` writes the filtered `null` result and exits 0 with no diagnostic — while overnight model/effort sizing (via `common.py`'s tolerant skip-and-continue) still reads the correct value. The fix must make the readers agree on torn-line handling.

**Tier:** complex · **Criticality:** high

> **Headline result (read this first):** The ticket's suggested one-line fix (flip `return None` → `continue` in `state_cli`) is directionally correct but **incomplete on two counts the adversarial pass verified empirically**: (1) it does **not** fix the *dominant* trigger (an LLM-emitted malformed `lifecycle_start` line — skipping the only tier-bearing line still yields `{}` → still defaults to `simple`); and (2) it does **not** "make the two readers agree," because two further divergences remain — `errors="replace"` vs. not (a non-UTF-8 byte *crashes* `common.py` with `UnicodeDecodeError` in the overnight runner's gating path) and `.to`/`.tier` field-precedence. A *third* reducer (`refine.py`) already exists and already agrees with `common.py`. The real decision is a **scope choice** (minimal patch vs. observable-signal fix vs. shared-helper unification) — see `## Open Questions`.

## Codebase Analysis

**Fix site.** `cortex_command/lifecycle/state_cli.py:96-99` — `_reduce_events` collapses the entire reduce to `None` on the first malformed line:
```
94  try:
95      record = json.loads(line)
96  except json.JSONDecodeError:
97      # Replicates jq-1.8.1: any malformed line collapses the
98      # entire reduce to null.
99      return None
```
A single torn line discards the partially-accumulated `acc` (initialized `{}` at line 88). `main()` (lines 195-201) writes `json.dumps(result)` and **always `sys.exit(0)`** — `null` (no `--field`) or `{}` (with `--field`, via `_filter_field` lines 139-146, since `None` is not a dict). No stderr diagnostic. The **module docstring (lines 25-28) declares this reduce-to-null as intentional jq-1.8.1 parity**, and the docstring (lines 15, 59) claims it mirrors `common.read_tier`/`read_criticality` — currently false for torn lines.

**Tolerant sibling.** `common.py:_read_tier_inner` (595-614) and `_read_criticality_inner` (522-541) do `continue` on `json.JSONDecodeError` and return the last valid value (defaults: tier `simple`, criticality `medium`). These are `@lru_cache`'d on a `_stat_key` = `(exists, mtime_ns, size)` and expose `.__wrapped__` for spec-R1 introspection; `state_cli` has no caching.

**Two additional divergences beyond the torn-line branch** (these matter for "make the readers agree"):
- **Encoding:** `state_cli` reads with `errors="replace"` (line 90); `common.py` reads **without** it (lines 522, 595). A non-UTF-8 byte → silent mojibake in `state_cli`, **uncaught `UnicodeDecodeError`** in `common.py`.
- **Field precedence:** `state_cli` reads `.to` **or** `.tier`/`.criticality` on override rows (lines 116, 120); `common.py` reads `.to` only. Dead on real logs today (all writers emit `.to`) but a true reader disagreement.

**The divergence, concretely** (against the existing `torn-line.events.log` fixture: valid `lifecycle_start{tier:complex,criticality:high}` on line 1, torn line 2, valid `phase_transition` line 3):

| Reader | Line-2 behavior | Result | Effective tier |
|---|---|---|---|
| `state_cli._reduce_events` | `return None` (discards line-1 `complex`) | `null` → `--field tier` `{}`, exit 0 | absent → **`simple`** |
| `common._read_tier_inner` | `continue` (keeps line-1) | `"complex"` | **`complex`** (correct) |

**Existing tests.** `tests/test_cortex_lifecycle_state_parity.py` is a golden-replay test that **pins the buggy behavior** — the `torn-line` fixture's `.stdout` = `null`, `.exitcode` = `0`, with an `error-formatter-shape`/`key-reorder` tolerance (line 75). It does **not** test `common.py`. `tests/test_bin_lifecycle_state_parity.py` *does* compare the bin script against `common.py` readers as source-of-truth — but its fixtures contain **no torn line** (so the divergence is currently untested) and it parses via `bin_out.get("tier", "simple")`, which would `AttributeError` on a `null` stdout.

**Conventions:** compact JSON (`separators=(",",":")` + trailing `\n`); exit 0 success / 2 usage-error with `cortex-lifecycle-state:` stderr prefix; canonical sources under `cortex_command/`, `skills/`, `bin/` with auto-regenerated mirrors under `plugins/cortex-core/`. Editing `common.py`/`skills/`/`bin/cortex-*` is lifecycle-gated and trips the dual-source drift pre-commit hook.

## Web Research

- **The current behavior is a textbook anti-pattern under every reading.** Silent `null` + exit 0 is the canonical silent-failure footgun; jq itself has an open issue titled "Null output and exit code 0 on broken json" ([jqlang/jq #2236](https://github.com/jqlang/jq/issues/2236)). jq aborts the whole stream on the first parse error by default ([#884](https://github.com/jqlang/jq/issues/884)).
- **jq already offers both postures:** tolerant `fromjson?` / `try fromjson catch empty` (silent skip); `--seq` (skip **but warns**); dropping `?` (loud stderr per bad line); `--exit-status` (0 value / 1 null-or-false / **4 no valid result ever**). The current behavior is the *worst of both* — neither a clean skip nor a loud failure.
- **Postel's-law critique (RFC 9413, "Maintaining Robust Protocols", 2023):** silent tolerance creates a "pathological feedback cycle"; endorses "virtuous intolerance" (fatal errors so faults get attention). **Crucial caveat, directly on point:** "when you control all the modules, prefer strictness / fail-fast" — here both readers and the log producer are in-repo and co-owned.
- **Key nuance for this decision:** tolerant-skip is correct for a torn **final** line, but **silently skipping a mid-file torn line still changes a gate-feeding derived value**. The strongest pattern in the literature **combines skip-and-continue WITH an observable signal** (a warning like `--seq`, or an exit code) — not a fully silent skip like bare `fromjson?`.
- **Append-only torn writes are real but low-frequency** (etcd WAL bug #6191 from torn writes is production precedent). WAL readers' rule is "when in doubt, stop" precisely because skipping silently changes derived state.
- **Three-state distinction** (present / empty-valid / missing-or-corrupt) is a well-established pattern (sentinel objects; jq's 0/1/4 exit trichotomy; Go's `sql.ErrNoRows`) — collapsing them is the bug.

## Requirements & Constraints

- **In-repo precedent points BOTH ways** (a genuine, surfaced contradiction):
  - *Toward tolerance:* `project.md` "Graceful partial failure" (degrade-and-continue) and the "Historical compatibility shim pattern" (read-side filters tolerate old/odd log shapes). `common.py` itself has four JSONL readers that all `continue`; `state_cli` is the lone outlier.
  - *Toward fail-loud:* `pipeline.md:42` is the one place the project explicitly chose fail-loud over silent-degrade — "Unparseable ordering metadata fails the feature loudly (`parse_error`) rather than degrading silently" — with a "silent mis-dispatch" rationale **structurally parallel** to this bug.
- **The aggravating, topic-specific fact:** `pipeline.md:63-67` gating matrix — a silently-degraded `complex`/`critical` feature is routed past the **required Post-Merge Review**. This is the concrete downstream harm and the thing that distinguishes this from a generic log-read.
- **No hard parity rule binds the readers** beyond `state_cli`'s own (currently-false) docstring self-claim of mirroring. **No events-registry obligation** is triggered (the three events read — `lifecycle_start`, `complexity_override`, `criticality_override` — are already registered; an output-contract change mints no new event name) and **no `cortex-check-parity` gate** is triggered (it polices wiring, not output semantics).
- **Two competing parity tests pin `state_cli` in opposite directions** (jq-original vs. `common.py`); aligning to tolerant-skip makes them consistent, failing-loud would require carve-outs in both.
- **Scope creep to avoid:** re-architecting the bash→Python parity discipline broadly; adding atomic-append/locking or a schema validator to `events.log` writers (would violate ADR-0001 / the no-locks forward-only constraint); touching unrelated dual-implementation divergences.

## Tradeoffs & Alternatives

- **Approach A — Tolerant skip-and-continue (ticket's suggestion):** flip `return None` → `continue`. *Complexity:* lowest (one branch). *Maintainability/Alignment:* highest — it IS the 4-to-1 existing pattern. *Cons (per adversarial pass):* see Open Questions — it silently relabels rather than fixes the dominant torn-`lifecycle_start` case, and does not reconcile the encoding/field-precedence divergences.
- **Approach B — Fail loudly (non-zero exit / stderr):** *Critically flawed as the sole fix.* The overnight runner gates review via `common.py` **directly** (no subprocess, no exit code), so a `state_cli` non-zero exit is unobserved there; and a loud failure in the agent-read paths has no torn-line repair affordance — it would abort the run or fall back to the same default. Fail-loud-via-exit-code is dead-on-arrival for `state_cli`. (A stderr **warning** — distinct from a non-zero exit — is a different, cheap proposition; see Open Questions.)
- **Approach C — Third 'corrupted' stdout state:** over-engineering. No consumer can act on it (all 8 are LLM-prose that default on absent key; none reads a sentinel). A `{"_corrupted":true}` on stdout would be a dead signal and would force new prose into every consumer. If corruption observability is wanted, the durable form is a separate telemetry event, not a tri-state on the hot read contract.
- **Shared-helper option:** extract one tolerant `reduce_lifecycle_state(events_path) -> {tier?, criticality?}` that **all three** reducers (`state_cli`, `common.py`'s `read_tier`/`read_criticality`, and `refine.py`'s `_reduce_current_state`) call — structurally impossible to diverge again. Cost: perturbs `common.py`'s `lru_cache`/`__wrapped__` introspection contract pinned by `test_bin_lifecycle_state_parity.py` and spec-R1 tests. Larger and more invasive than Approach A, but it is the policy-indicated durable target (this is the *second* split-brain in this reader pair after #285; the adversarial pass found it is actually the *third* copy).
- **Recommended (research's lean, for Spec to ratify):** tolerant skip as the base discipline (it serves the goal — the gate keeps firing — where fail-loud does not), **plus an observable stderr warning on any skipped line** (breaks zero consumers since none reads stderr; addresses the dominant-trigger silence and honors the `pipeline.md:42` fail-loud precedent cheaply), staged toward the shared-helper unification so the three readers cannot drift a fourth time.

## Consumer-Contract Audit

**8 runtime consumers, all LLM-prose skill instructions.** None uses jq, checks the exit code, reads stderr, or branches on a `null`/`corrupted` sentinel. All apply: read the field, default tier→`simple` / criticality→`medium` on absent key.

| # | Consumer (canonical) | Line(s) | Field |
|---|---|---|---|
| 1 | `skills/lifecycle/references/specify.md` §3b | 169-170 | tier + criticality |
| 2 | `skills/lifecycle/references/orchestrator-review.md` applicability | 7 | whole object |
| 3 | `skills/refine/SKILL.md` §3b tier detection | 172 | tier |
| 4 | `skills/lifecycle/SKILL.md` resume reporting | 100, 102 | criticality, tier |
| 5 | `skills/lifecycle/references/plan.md` §1a + §3b | 21, 271-272 | criticality, then tier+criticality |
| 6 | `skills/lifecycle/references/implement.md` §4 | 303 | criticality |
| 7 | `skills/dev/SKILL.md` resumed lifecycle | 126 | criticality |
| 8 | `skills/morning-review/references/walkthrough.md` step 3 | 236-241 | whole object |

(Mirrors under `plugins/cortex-core/` and `plugins/cortex-overnight/` are byte-identical regenerated copies, not separate consumers.)

**Q4 verdict — VERIFIED, not refuted:** **No consumer relies on reduce-to-null as a corruption signal.** The reduce-to-null is an accidental jq-1.8.1 artifact funneled into every consumer's generic "absent key → default" path — so today a corrupt log silently reads as `simple`/`medium` and the gates silently skip.

**Breakage per approach:** A = zero breakage (recovered/last-valid flows through the existing read-the-field path). B and C = all 8 consumers would need new "if non-zero exit / if `corrupted` → halt/escalate" prose, and would otherwise fall through to the default anyway (re-introducing the silent skip).

## Write-Path & Corruption Semantics

**The OQ4 premise ("atomic writer precludes torn lines") is FALSE for the events `state_cli` reads.** There are three write disciplines, and the state-relevant events use the weakest:
- **Atomic flock + tempfile + `os.replace`** (`lifecycle_event.py:69-139`) — strongest, but writes only `interactive_worktree_entered`-class events, **none state_cli-consumed**.
- **tempfile + fsync + `os.replace`** (`discovery.py`, `critical_review/__init__.py`) — atomic+durable, again **no state_cli-consumed events**.
- **Plain `open(path, "a")` append** (NON-atomic, no fsync) — `refine.py:230` (`criticality_override`), `refine.py:277` (`lifecycle_start`), `complexity_escalator.py:200` (`complexity_override`) — **these are the state events**. And the dominant interactive producer of `lifecycle_start`/`criticality_override` is **LLM-issued shell append** (`skills/lifecycle/SKILL.md:150-153`), with no atomicity guarantee.

**Realistic torn-line triggers, ranked:** (1) **LLM-emitted malformed JSON / missing newline** — the dominant, normal-operation trigger; (2) crash/interrupt mid plain-append (no fsync); (3) external edit / manual truncation / partial git artifact; (4) concurrent-writer interleave (rare; per-feature logs are effectively single-writer).

**OQ3 verdict — third state NOT warranted:** a third stdout state is a dead signal (no consumer acts on it). The actionable fix is to *remove* the null-collapse and match `common.py`'s tolerant-skip; if observability is wanted, a stderr warning (which the `clean.py:166-169` enumerator already does — skip-with-stderr-warn) is the cheap, consumer-safe form.

**OQ4 verdict — torn lines ARE realistic**, dominated by LLM-malformed-JSON, so tolerant-skip is the right base discipline; `state_cli` is the outlier that should be brought into line with `common.py` and `clean.py`.

## Adversarial Review

The adversarial pass verified each claim against the code and synthetic logs. Three findings materially change the deliverable:

1. **Approach A does NOT fix the dominant-trigger case (empirically verified).** Staging a torn `lifecycle_start` as the only tier-bearing line: current `state_cli --field tier` → `{}` → `simple`; proposed-fix accumulator → `{}` → still `simple`. Tolerant-skip changes nothing when the torn line *is* the start event — it only helps when a valid start co-exists with a separate later torn line (the existing fixture's shape, but **not** the dominant LLM-malformed-start failure). **A real fix needs an observable signal on any skipped line**, not a silent skip.
2. **"Make the readers agree" needs three axes reconciled, not one.** Beyond torn-line: **non-UTF-8** — `state_cli` (`errors="replace"`) returns `{}`/exit 0 while **`common.py` raises `UnicodeDecodeError`**, and the overnight runner calls `read_tier`/`read_criticality` directly (`outcome_router.py:1024-1025,1240`; `runner.py:2717`) → a **latent runner-crash** on a non-UTF-8 byte; and **field-precedence** (`.to`/`.tier` vs `.to`). A parity test built only on the torn-line fixture passes while the readers still disagree/crash on these.
3. **There is a THIRD reducer, and two of three already agree.** `refine.py:_reduce_current_state` (113-160) already uses tolerant-skip + `.to`-only and matches `common.py`; its own comment documents the deliberate divergence from `state_cli`. So `state_cli` is the lone outlier among three hand-rolled reducers. Per `project.md:21` Solution Horizon ("patch applies in multiple known places you can name → propose the durable version"), **the shared-helper extraction is policy-indicated as the primary fix, not an optional follow-up.**

Further adversarial points: the existing agreement harness (`test_bin_lifecycle_state_parity.py:88-100`) is the thing to *extend* (not reinvent) but must first be hardened against `null`/`None` stdout and non-UTF-8 input or it `AttributeError`s/crashes; flipping the `torn-line` golden is not a one-fixture edit — the fixture README (50-115) calls tolerant-skip "a parity failure," so the jq-parity framing (a fossil now that the bash+jq oracle is gone) must be retired and re-founded on the `common.py`-agreement contract; the "no operator in overnight" argument conflates consumers — the **morning-review** path (`walkthrough.md:236`) decides Post-Merge-Review necessity in front of a human reading the morning report, so a stderr warning would surface usefully there.

## Open Questions

> **RESOLVED at the Research Exit Gate (user decision, 2026-06-10): scope (c) "Durable".** The fix unifies the three reducers behind one shared tolerant helper, adds an observable stderr warning on any skipped line, reconciles the non-UTF-8 encoding contract (closing the latent overnight-runner `UnicodeDecodeError` crash) and field-precedence, and extends `test_bin_lifecycle_state_parity.py` with a multi-reader agreement matrix. This resolves OQ1→(c), OQ2→in-scope, OQ3→tolerant base + stderr signal, OQ4→retire jq-parity framing and extend the existing agreement test. The items below are retained for Spec as the rationale of record.

1. **[SCOPE — the central decision] How far does the fix go?** *(Resolved: (c) Durable.)* Three coherent scopes:
   - **(a) Minimal** — flip `return None` → `continue` in `state_cli`, flip the `torn-line` fixture + README, add a torn-line agreement assertion. *Caveat established by research:* this does **not** fix the dominant LLM-malformed-`lifecycle_start` trigger (still silently degrades to `simple`) and does **not** make the readers agree on non-UTF-8 or field-precedence.
   - **(b) Correct** — (a) **plus** an observable **stderr warning** on any skipped/malformed line (breaks zero consumers; addresses the dominant-trigger *silence* and honors the `pipeline.md:42` fail-loud precedent cheaply). The value gained is observability, not a different gate outcome (the degraded line still defaults).
   - **(c) Durable** — (b) **plus** extract one shared tolerant reducer used by all three call sites (`state_cli`, `common.py`, `refine.py`), reconcile the **non-UTF-8 encoding contract** (the latent runner-crash bug — pick `errors=` uniformly) and **field-precedence**, and add a multi-reader agreement-test matrix (torn-mid-file, torn-`lifecycle_start`-only, non-UTF-8, `.tier`/`.criticality`-keyed override). This is the Solution-Horizon-indicated version given three named call sites + a latent crash.
   *Research lean: (c), staged on top of (b)* — but the user owns the scope/value tradeoff at Spec's §4 complexity/value gate.
2. **Is the latent non-UTF-8 `UnicodeDecodeError` crash in `common.py` (which the overnight runner hits directly) in-scope for this ticket, or a separately-tracked bug?** It is a real defect the adversarial pass found, not in the original ticket. (Bears directly on scope (c).)
3. **Contradiction to resolve:** in-repo precedent supports both tolerance (`project.md` Graceful-partial-failure / Historical-compat-shim; `common.py` 4-to-1) and fail-loud (`pipeline.md:42`). Research's resolution is "tolerant base + observable stderr signal" (scope b/c), but the user should confirm this reading rather than pure-silent-skip (a) or hard-fail (rejected).
4. **Test re-founding:** confirm it is acceptable to retire the jq-1.8.1-parity justification for the `torn-line` fixture (the bash+jq oracle no longer exists) and re-found the golden on the `common.py`-agreement contract — and to extend `test_bin_lifecycle_state_parity.py` (hardened first) rather than add a parallel test.
