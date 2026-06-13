# Implementation Notes

## R8 one-time hand-diff — exit-code route prose ↔ Python emitter (2026-06-13)

**Scope of the Task-3 trim**: only P5 (Step 2c.5 captured-SHA cross-reference) and P6 (Step 2a.5 substitution-site enumeration) were applied. **Neither is exit-code route-reaction prose** — so *no route-reaction prose was condensed* by this trim. The hand-diff below is therefore the widened one-time correctness check (the static gate pins exit-marker *presence*, not reaction *prose*), comparing the current `skills/critical-review/references/verification-gates.md` reactions against the exit constants in `cortex_command/critical_review/__init__.py`. Source of truth for the codes: the Python emitter; the markdown prose must not contradict it.

Per-code verdict: **all match**. The reaction lines are byte-identical to pre-trim (P5/P6 did not touch them).

### Exit 0 — clean pass
- **Python** (`critical_review/__init__.py:752-753`, and `:677-678` for synth): `if status == "ok": sys.stdout.write(f"OK {observed}\n"); return 0`.
- **Markdown** (Step 2c.5): "**Exit 0** — sentinel present … AND SHA matches. Pass — proceed to Phase 2 for this reviewer." (Step 2d.5): "**Exit 0** — synthesizer's `SYNTH_READ_OK:` sentinel present and SHA matches. Surface the synthesizer's prose output to the user normally, then proceed to Step 2e."
- **Verdict**: match — exit 0 = clean pass / proceed.

### Exit 2 — prepare-dispatch validation failure, stop dispatch
- **Python** (`_cmd_prepare_dispatch`, `:646`, `:657`, `:660`, `:671`): on `RuntimeError`/`ValueError`/`OSError` (path validation), `print(str(e), file=sys.stderr); return 2`. Non-zero exit, message on stderr.
- **Markdown** (Step 2a.5): "If `prepare-dispatch` exits non-zero, surface its stderr verbatim to the user and stop — do not dispatch any agent. Exit-2 messages name the offending path and the violated rule (symlink, prefix mismatch, non-file)."
- **Verdict**: match — exit 2 = surface stderr verbatim, stop, do not dispatch. (This is the reaction newly pinned by Phase 1's `test_exit2_stop_dispatch_reaction_present`.)

### Exit 3 — real drift/absence (lifecycle dir present), do-not-surface / exclude
- **Python** (`:801` artifact-stable, `:727` synth-stable): after `sys.stdout.write("EXCLUDED …")` / the `Critical-review pass invalidated:` diagnostic, `append_event(events_log, event)` (the `sentinel_absence` / `synthesizer_drift` event) then `return 3` — taken only when `_lifecycle_dir_exists(...)` is true.
- **Markdown** (Step 2c.5): "**Exit 3** — sentinel absent, SHA mismatch (drift), or `READ_FAILED` route, with a real `cortex/lifecycle/{feature}/` directory present. The subcommand has already appended the `sentinel_absence` event … atomically; the orchestrator MUST NOT append to `events.log` inline …". (Step 2d.5): "**Exit 3** — … **Do NOT surface the synthesizer's prose output.** … The subcommand has already appended the `synthesizer_drift` event …".
- **Verdict**: match — exit 3 = excluded / do-not-surface, event already persisted by the subcommand, orchestrator must not double-append.

### Exit 4 — telemetry skipped (phantom-dir guard), benign skip ≠ exit 3
- **Python** (`:52` `EXIT_TELEMETRY_SKIPPED = 4`; `:722` synth, `:796` artifact): `if not _lifecycle_dir_exists(...): print("telemetry skipped: lifecycle dir absent …", file=sys.stderr); return EXIT_TELEMETRY_SKIPPED`. Comment: "we return EXIT_TELEMETRY_SKIPPED (4), observably distinct from the real-invalidation exit (3), instead of fabricating either a clean or a recorded result."
- **Markdown** (Step 2c.5): "**Exit 4** — telemetry skipped: the target `cortex/lifecycle/{feature}/` directory does not exist, so the structural write-guard suppressed the `sentinel_absence` append … This is a benign skip, distinct from exit 3 … Treat the reviewer as a normal pass …". (Step 2d.5): "**Exit 4** — telemetry skipped … suppressed the `synthesizer_drift` append … Surface the synthesizer's prose output normally and proceed to Step 2e."
- **Verdict**: match — exit 4 = benign skip / no event persisted / treat as pass, explicitly distinct from exit 3. The two sections govern different downstream transitions (2c.5 → reviewer-tally/total-failure; 2d.5 → whether Step 2e proceeds), consistent with the refuter's reason for keeping both (P2/P3 skipped-with-reason).

**Conclusion**: no route-reaction prose was condensed by the applied trim (P5/P6 only); all four exit-code reactions remain consistent with the Python emitter. This is a one-time author check scoped to this change, not a re-runnable gate — a durable prose↔Python route-consistency test is a noted follow-up (spec Non-Requirements).
