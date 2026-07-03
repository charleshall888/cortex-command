# Verify outcomes — cortex/requirements/remote-access.md (fragment, Task 2d)

Whole-file, recall-first verification of the 5 `master_candidates.json` rows with
`file == "cortex/requirements/remote-access.md"`, `status == "unverified"`, no
`overlaps_ticket`, no `reproposal_of` (ids: `file-compress`, s2, s4, s5, s6 —
confirmed against the ledger; `file-compress` is MERGE_DEDUP over the tail-section
aggregate, s2/s4/s5/s6 are COMPRESS). Keep-guidance is taken only from each
candidate's ledger `claim` field, per spec Req 2. This is a transient Phase-1
input; Task 3 folds it into the assembled `verify-outcomes.md`. No requirements
file is edited by this fragment.

**s2 ↔ s6 ↔ file-compress cluster (spec Req 5b)**: whole-file reading confirms
two facts are each triplicated across this doc, not just duplicated:
- **tmux tool-agnostic framing** — Overview L9 ("current implementation uses
  tmux… subject to change"), Dependencies L49 ("tmux (current implementation,
  **subject to change**)"), and Open Questions L58-60 ("tool currently providing
  session persistence (tmux skill) is under review… must be preserved regardless
  of which tool provides it") all state the same fact. Open Questions is the
  Overview-adjacent duplicate named by s2's claim; the Dependencies echo is a
  third instance surfaced by this verification pass, inside `file-compress`'s span.
- **macOS/Ghostty constraint** — NFR L41 ("macOS is the primary and only
  supported platform… Ghostty dependency"), Architectural Constraints L45
  ("depends on a macOS terminal that supports persistent container processes
  (currently Ghostty)"), and Dependencies L49 ("Ghostty terminal (macOS)") all
  state the same fact. NFR is s6's span; Architectural Constraints and the
  Ghostty half of Dependencies are inside `file-compress`'s span.

All three candidates individually survive verification (below), but per spec
Req 5(b) Phase 2 must apply them as **one coordinated edit** with one canonical
home per fact — not three independent trims that could each leave a different
"last" copy standing, or that could jointly delete every copy of a fact.

Named must-keep confirmed intact and untouched by all 5 candidates' spans: the
**Failure transparency** NFR bullet (L39) is independently load-bearing —
`docs/overnight-operations.md:615` cites it by file reference ("per
`cortex/requirements/remote-access.md`, notification and session-management
failures are silent by design"). s6's claim already keeps this bullet; verified
correct and flagged here as a hard constraint on Phase 2, not just a nice-to-have.

**Citer scan (spec Req 7 scope, `cortex_command/**` + `docs/**`)**: the only live
citer of this file anywhere in that scope is `docs/overnight-operations.md:615`,
and it is a **file-level reference with no line number** (no `remote-access.md:N`,
no L-prefix form, no range form found by grep across `cortex_command/`, `docs/`,
`tests/`, `skills/`, `hooks/`, `claude/`). It cites the Failure-transparency fact,
which survives unmodified, so no post-trim recompute is needed for this file
regardless of which of the 5 candidates are applied in Phase 2.

| file | id | heading | anchor_token | verdict | signal | reason | applied_in_commit |
|---|---|---|---|---|---|---|---|
| cortex/requirements/remote-access.md | s2 | ## Overview | "subject to change" | survives | c (preserved-elsewhere) | The Overview's tool-agnostic framing ("The current implementation uses tmux for session persistence, but the requirement is defined at the capability level: the specific tool providing persistence is subject to change") is preserved-elsewhere: near-verbatim at Open Questions L58-60 ("The tool currently providing session persistence (tmux skill) is under review. The requirements above describe the capability that must be preserved regardless of which tool provides it.") and echoed a third time at Dependencies L49 ("tmux (current implementation, subject to change)"). Confirmed by direct read of current file (no drift from the claim). Part of the s2↔s6↔file-compress cluster (Req 5b) — Phase 2 must pick one canonical home (Overview is the natural one, per the claim's own framing) and point the other two at it, not delete all three or leave duplicates. | pending |
| cortex/requirements/remote-access.md | s4 | ### Session Persistence | "developer initiates session move or reconnection" | survives | b (informative-only) + c (preserved-elsewhere) | Inputs ("Active Claude Code session; developer initiates session move or reconnection") and Outputs ("New terminal window with session running inside a persistent container; original session continues unaffected") are template-filler scene-setting with no independent `shall/must` content — quoted spans, signal b. The two AC bullets this candidate proposes cutting — "detached from its client window without interrupting the active conversation" and "reattached from a different terminal window or device" — restate Description L15 ("must persist independently of the client connection, surviving network interruptions, terminal closures, and device switches"), signal c, preserved at L15. Confirmed no code/test/hook in this repo implements or checks tmux session-persistence behavior (grepped `tests/`, `cortex_command/`, `hooks/`, `skills/`); `docs/setup.md:7` confirms tmux/terminal session mechanics are machine-config-repo territory, not this repo's, so there is no structural-substitution (signal a) available or needed. The three untouched AC bullets (session identity preserved, enumerable, name/ID-addressable) carry the only non-derivable capability contract and are correctly kept per the claim. | pending |
| cortex/requirements/remote-access.md | s5 | ### Remote Session Reattachment | "roaming between networks" | survives | b (informative-only) + c (preserved-elsewhere) | Inputs/Outputs are template filler, same pattern as s4 (signal b, quoted). The AC bullet "mosh connection survives IP address changes and roaming between networks" states mosh's well-known generic design property (mosh was built specifically for this), not a project-specific decision — confirmed no test/hook/doc in the repo encodes IP-roaming behavior (grepped `tests/`, `cortex_command/`, `hooks/`, `skills/`, `docs/` for "mosh"/"IP address"/"roaming" — only generic tool-name mentions found, e.g. `docs/internals/sdk.md:240`, `skills/morning-review/references/walkthrough.md:127,658`, none describing IP-roaming semantics); it is derivable from the tool choice already recorded in Dependencies L50 and Description L28 (signal b). The genuinely project-specific decisions this candidate keeps — Tailscale+mosh stack choice, no-port-forwarding constraint, should-have priority — are independently confirmed load-bearing: `docs/internals/sdk.md:240` cites "Tailscale + mosh + tmux handles remote access" for `RemoteTrigger`, but does not restate the no-port-forwarding nuance anywhere, so that AC line (L34) must survive untouched, consistent with the claim. | pending |
| cortex/requirements/remote-access.md | s6 | ## Non-Functional Requirements | "Failure transparency" | survives | b (informative-only) + c (preserved-elsewhere) | The Failure-transparency bullet (L39) is confirmed independently load-bearing — `docs/overnight-operations.md:615` cites it by file reference — and the claim correctly keeps it untouched; verified as a hard constraint, not just a claim to trust. "Timeout: Session reattachment depends on network latency" (L40) is a vacuous, non-actionable restatement with no `shall/must` content — no timeout value, config, or check exists anywhere in `cortex_command/` or `hooks/` (grepped) — signal b, quoted. The Platform/Ghostty bullet (L41, "macOS is the primary and only supported platform for session persistence (Ghostty dependency). Linux/Windows are not supported.") is confirmed triplicated in substance at Architectural Constraints L45 and Dependencies L49 — signal c. Part of the s2↔s6↔file-compress cluster (Req 5b); Phase 2 must consolidate to one canonical Platform/Ghostty statement (NFR is the natural home, since it also carries the "Linux/Windows are not supported" negative-scope statement the other two copies lack) rather than trimming independently. | pending |
| cortex/requirements/remote-access.md | file-compress | ## Architectural Constraints / ## Dependencies / ## Edge Cases / ## Open Questions (aggregate) | "persistent container processes" · "Local notifications" · "Ghostty not installed" · "tmux skill" | survives | b (informative-only) + c (preserved-elsewhere) | Verified sub-span by sub-span (whole-file, recall-first): (1) Architectural Constraints' sole bullet ("depends on a macOS terminal that supports persistent container processes (currently Ghostty)") is preserved-elsewhere at NFR L41 and Dependencies L49 — signal c; same macOS/Ghostty triplication also touched by s6 (Req 5b cluster). (2) Dependencies' "Local notifications: `terminal-notifier` (macOS), Ghostty (for click-to-activate)" line is preserved-elsewhere in substance at `observability.md:116` ("Notifications (macOS): `terminal-notifier` (installed via `brew install terminal-notifier`); Ghostty terminal") — signal c; confirmed vestigial via `git show 373ca304 --stat`, which independently confirms that commit's subject/body ("Remove cortex-notify-remote hook… strip references from… observability/remote-access requirements") removed the companion remote-notification hook this "Local notifications" line used to pair with, leaving it an orphaned duplicate of observability.md's copy. Dependencies' other two bullets ("Session persistence: tmux…" and "Remote connection: Tailscale…") are each independently preserved-elsewhere too (Overview L9 and s5 Description L28 respectively, signal c) but are **not** claimed for deletion by this candidate — the claim's "roughly half" framing and MERGE_DEDUP category mean Phase 2 condenses/points, it does not blank the whole Dependencies section; flagging this so Phase 2 doesn't over-delete. (3) Edge Cases' two bullets ("Ghostty not installed → fails at window creation, error suggests installation"; "Tailscale/mosh not installed → fails at client") are mechanically derivable "dependency missing → that leg fails" statements — no test/hook implements or checks these specific error messages (grepped `tests/`, `hooks/`, `cortex_command/`), and the kept NFR Failure-transparency bullet already establishes failures are silent-by-design, which is in tension with the aspirational "error message suggests installation" clause — signal b, quoted. (4) Open Questions' tmux-under-review bullet is preserved-elsewhere at Overview L9 (near-verbatim) — signal c; third leg of the tool-agnostic-framing triplication (Overview / Dependencies "subject to change" / Open Questions), same s2↔s6↔file-compress cluster requiring one coordinated Phase-2 edit. | pending |

## Notes for Phase 2 (citer refresh, spec Req 7)

- Only one live citer of this file exists in the `cortex_command/**` + `docs/**`
  scope: `docs/overnight-operations.md:615`, a **file-level reference with no
  line number** ("per `cortex/requirements/remote-access.md`"). No recompute is
  needed post-trim as long as the Failure-transparency fact it cites (kept
  untouched by s6) survives at some canonical location — which it does under
  every candidate's verdict above.
- No L-prefix or range-form citers found for this file anywhere in the repo.

## Verification self-check

- Row count: 5 (`grep -c '^| cortex/requirements/remote-access.md ' verify-outcomes-remote-access.md` = 5).
- All 5 rows are `survives`; every signal cell is non-empty and typed (b/c, no
  bare "looks safe" reasons — each cites a quoted span, a specific surviving
  location, or a specific grep/`git show` confirmation).
- No candidate refuted in this fragment.
- Self-sealing check: every signal is backed by an artifact independently
  re-checkable by a third party (a specific file+line quoted or grepped, or a
  `git show <hash> --stat` commit-message excerpt) rather than by this agent's
  own unaided judgment. The one soft spot: the s2/s6/file-compress "preserved
  elsewhere" calls describe content as semantically equivalent, not always
  byte-identical, across the three triplicated copies — flagged explicitly in
  the cluster note above so Phase 2 treats consolidation as a coordinated
  single edit (per spec Req 5b) rather than three independent trims that could
  each assume a different copy is "the" canonical one.
