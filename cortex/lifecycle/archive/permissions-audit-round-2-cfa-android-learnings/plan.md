# Plan: Permissions audit round 2 — CFA Android learnings

## Overview

Deliver 10 requirements across 6 per-finding commits against `claude/settings.json`, closing five residual permission gaps identified by CFA Android learnings: curl exfiltration (R1), blanket interpreter allows (R2–R6), tee rc-file bypass (R7), destructive git checkout form (R8), and cloud metadata endpoint access (R9). JSON validity is a per-commit invariant (R10).

**Implementation approach**: Edit `claude/settings.json` directly (the single source of truth). Six commits in the order mandated by the spec's Technical Constraints. Before any commits, run all three Plan-Phase Verification Protocol tests (Q1, Q3, Q4) to resolve Open Decisions D1, D2, D3. Use the `/commit` skill for each commit.

**Key facts from current file state** (verified by reading `claude/settings.json`):
- `Bash(curl *)` — in `allow` at line 92
- `Bash(npm *)` — in `allow` at line 106
- `Bash(pip3 *)` — in `allow` at line 108
- `Bash(docker *)` — in `allow` at line 111
- `Bash(make *)` — in `allow` at line 112
- `Bash(tee *)` — in `allow` at line 114
- `Bash(brew *)` — in `allow` at line 124
- `Bash(git restore *)` — sole entry in `ask` at line 216
- No `Bash(git checkout -- *)` in `ask`
- No cloud metadata `WebFetch(domain:...)` denies in `deny`

No recovery log exists — this is a first attempt.

---

## Plan-Phase Verification Protocol

These three tests **must run before any commits land**. Their results determine the content of commits 3 and 4 (R8, R9) per Open Decisions D1 and D2.

---

### Task 0a — Q1: Verify git checkout -- glob does not match --theirs/--ours

**Files**: none (test only; no file changes)

**What**: In an interactive Claude Code session, verify that the glob pattern `Bash(git checkout -- *)` matches `git checkout -- <file>` (must prompt) and does NOT match `git checkout --theirs <file>` (must not prompt). This determines D1 (R8 fallback selection).

**Practical test procedure**: Add `Bash(git checkout -- *)` temporarily to `ask` in a test `settings.local.json` override (or run the test after Task 4 lands), then:
1. Create a throwaway tracked file: `touch /tmp/test-checkout.txt && git add /tmp/test-checkout.txt`
2. Attempt `git checkout -- /tmp/test-checkout.txt` — must trigger ask prompt.
3. Attempt `git checkout --theirs /tmp/test-checkout.txt` — must NOT trigger ask prompt.
4. Remove the temporary test entry before proceeding if tested in isolation.

**Expected outcome (D1 primary path)**: `Bash(git checkout -- *)` uses Claude Code's prefix-glob matching where `--` is literal prefix, `--theirs` has a different literal prefix, so the glob should NOT match `--theirs`. If this is confirmed, ship R8 as written (Task 4 primary form).

**Fallback (D1 alternate path)**: If the glob DOES match `--theirs`/`--ours`, Task 4 instead adds three entries: `Bash(git checkout --theirs *)` allow, `Bash(git checkout --ours *)` allow, `Bash(git checkout -- .)` ask. Document outcome in commit message.

**Depends on**: nothing (run first)

**Verification**: Record the observed prompt/no-prompt behavior for both invocations. Decision is binary — the executor notes which path is taken in the commit 4 message.

**Status**: [ ]

---

### Task 0b — Q4: Verify WebFetch(domain:<IP-literal>) matcher behavior

**Files**: none (test only; no file changes)

**What**: Temporarily add `WebFetch(domain:169.254.169.254)` to `permissions.deny` via `.claude/settings.local.json` (not the canonical file), then attempt a `WebFetch` to `https://169.254.169.254/` and observe whether the block fires. This determines D2 (R9 IP-literal fallback selection).

**Practical test procedure**:
1. Add `"WebFetch(domain:169.254.169.254)"` to the `deny` array in `/Users/charlie.hall/Workspaces/cortex-command/.claude/settings.local.json` (creating the file if absent, or appending to the existing deny array).
2. In an interactive Claude Code session, attempt `WebFetch https://169.254.169.254/`.
3. Observe: does Claude Code block it with a permission denial, or does it attempt the fetch?
4. Remove the temporary entry before proceeding.

**Expected outcome (D2 primary path)**: IP-literal enforces → ship all 5 R9 entries (Task 2 primary form).

**Fallback (D2 alternate path)**: IP-literal silently fails → ship only 3 hostname entries (`metadata.google.internal`, `api.metadata.cloud.ibm.com`, `instance-data.ec2.internal`); drop `169.254.169.254` and `169.254.170.2` from the commit; document in commit message: "IP-literal matching unsupported by Claude Code; shipping hostname coverage only; full coverage depends on PreToolUse hook or sandbox enforcement (both out of scope per Non-Requirements)."

**Depends on**: nothing (run first)

**Verification**: Record observed block/pass behavior. Decision is binary — executor notes which path is taken in the commit 2 message.

**Status**: [ ]

---

### Task 0c — Q3: Verify compound-command bypass behavior for ask-tier rules

**Files**: none (test only; no file changes)

**What**: After R1 lands (or using a temporary settings.local.json override that adds `Bash(curl *)` to ask), attempt `true && curl http://example.com/` and observe whether the ask prompt fires for the curl invocation. This determines D3 (outcome-recording only — the spec does not change regardless).

**Practical test procedure**:
1. Either test after Task 1 (R1 curl→ask) commits, or temporarily add `Bash(curl *)` to ask in settings.local.json.
2. In an interactive Claude Code session, run `true && curl http://example.com/`.
3. Observe: does the ask prompt appear for curl?

**Outcome recording**: If compound commands DO trigger ask → R1 provides meaningful closure beyond naive-path. If compound commands BYPASS ask → R1 is a naive-path mitigation only (as already acknowledged in R1's Residual Risk). Spec is NOT re-opened regardless. Record outcome in Q3 verification note; mention in commit 1 message if bypass is confirmed.

**Depends on**: nothing (can run in parallel with Q1/Q4, or after Task 1 using live settings)

**Verification**: Record observed prompt/no-prompt behavior for the compound invocation.

**Status**: [ ]

---

## Commit Sequence

---

### Task 1 — R1: Move Bash(curl *) to ask tier

**Files**: `/Users/charlie.hall/Workspaces/cortex-command/claude/settings.json`

**What**:
1. Remove `"Bash(curl *)"` from the `permissions.allow` array (currently at line 92).
2. Add `"Bash(curl *)"` to the `permissions.ask` array (which currently contains only `"Bash(git restore *)"` — add after it).

**Depends on**: Tasks 0a, 0b, 0c can run concurrently; this commit does not depend on their outcomes (R1 ships regardless of Q3 result).

**Context**: R1 is the highest-severity change. Moving curl to ask closes the naive-path curl-to-api.github.com channel that bypasses the `gh gist create` deny. Session-scoped: first `curl` invocation per session triggers a single ask prompt; subsequent invocations reuse the approval. Known friction: `ui-judge`, `ui-a11y`, `ui-check` use `curl http://localhost:PORT` for dev-server probes — first invocation per session will prompt.

**Verification**:
- `python3 -m json.tool claude/settings.json > /dev/null` exits 0
- `jq '.permissions.allow | map(select(. == "Bash(curl *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.ask | map(select(. == "Bash(curl *)")) | length' claude/settings.json` returns `1`
- `jq '.permissions.deny | map(select(. == "Bash(curl *)")) | length' claude/settings.json` returns `0`

**Commit subject**: `Move Bash(curl *) to ask tier for exfiltration control`

**Status**: [ ]

---

### Task 2 — R9: Add cloud metadata endpoint denies

**Files**: `/Users/charlie.hall/Workspaces/cortex-command/claude/settings.json`

**What**: Add entries to `permissions.deny`. The exact set depends on Q4 (Task 0b) outcome:
- **Primary path (IP-literal enforces)**: Add all 5 entries:
  - `"WebFetch(domain:169.254.169.254)"`
  - `"WebFetch(domain:169.254.170.2)"`
  - `"WebFetch(domain:metadata.google.internal)"`
  - `"WebFetch(domain:api.metadata.cloud.ibm.com)"`
  - `"WebFetch(domain:instance-data.ec2.internal)"`
- **Fallback path (IP-literal fails)**: Add only 3 hostname entries:
  - `"WebFetch(domain:metadata.google.internal)"`
  - `"WebFetch(domain:api.metadata.cloud.ibm.com)"`
  - `"WebFetch(domain:instance-data.ec2.internal)"`

Add the new deny entries after the existing `"WebFetch(domain:0.0.0.0)"` deny entry.

**Depends on**: Task 0b (Q4 result determines primary vs fallback set); Task 1 must be committed first (commit ordering per spec).

**Context**: R9 covers WebFetch only. Bash-layer metadata access is a Non-Requirement. Deny additions propagate via the sync hook's union merge, so existing installs gain this protection on next SessionStart. No in-repo callers for any of these endpoints.

**Verification** (primary path — adjust if fallback):
- `python3 -m json.tool claude/settings.json > /dev/null` exits 0
- `jq '.permissions.deny | map(select(. == "WebFetch(domain:169.254.169.254)")) | length' claude/settings.json` returns `1`
- `jq '.permissions.deny | map(select(. == "WebFetch(domain:169.254.170.2)")) | length' claude/settings.json` returns `1`
- `jq '.permissions.deny | map(select(. == "WebFetch(domain:metadata.google.internal)")) | length' claude/settings.json` returns `1`
- `jq '.permissions.deny | map(select(. == "WebFetch(domain:api.metadata.cloud.ibm.com)")) | length' claude/settings.json` returns `1`
- `jq '.permissions.deny | map(select(. == "WebFetch(domain:instance-data.ec2.internal)")) | length' claude/settings.json` returns `1`
- Also re-verify Task 1 acceptance criteria remain passing (cumulative invariant)

**Commit subject**: `Add cloud metadata endpoint denies to WebFetch`

**Status**: [ ]

---

### Task 3 — R7: Move Bash(tee *) to ask tier

**Files**: `/Users/charlie.hall/Workspaces/cortex-command/claude/settings.json`

**What**:
1. Remove `"Bash(tee *)"` from `permissions.allow` (currently at line 114).
2. Add `"Bash(tee *)"` to `permissions.ask` after the existing ask entries.

**Depends on**: Task 2 must be committed first (commit ordering per spec).

**Context**: R7 raises the naive-path effort of bypassing `Edit(~/.zshrc)` deny via `tee -a ~/.zshrc`. Zero runtime callers in the repo (grep-verified). Session-scoped ask: first `tee` invocation prompts once per session. Architecturally-correct fix (sandbox.filesystem.denyWrite) is out of scope.

**Verification**:
- `python3 -m json.tool claude/settings.json > /dev/null` exits 0
- `jq '.permissions.allow | map(select(. == "Bash(tee *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.ask | map(select(. == "Bash(tee *)")) | length' claude/settings.json` returns `1`
- `jq '.permissions.deny | map(select(. == "Bash(tee *)")) | length' claude/settings.json` returns `0`
- Re-verify Tasks 1 and 2 acceptance criteria remain passing (cumulative invariant)

**Commit subject**: `Move Bash(tee *) to ask tier for rc-file bypass`

**Status**: [ ]

---

### Task 4 — R8: Add Bash(git checkout -- *) to ask tier

**Files**: `/Users/charlie.hall/Workspaces/cortex-command/claude/settings.json`

**What**: The exact change depends on Q1 (Task 0a) outcome:
- **Primary path (glob does NOT match --theirs/--ours)**: Add `"Bash(git checkout -- *)"` to `permissions.ask`.
- **Fallback path (glob DOES match --theirs/--ours)**: Instead add to `permissions.allow`: `"Bash(git checkout --theirs *)"` and `"Bash(git checkout --ours *)"`, and add to `permissions.ask`: `"Bash(git checkout -- .)"`.

The existing `"Bash(git checkout *)"` allow entry remains in place in either case — it continues to cover branch switching, `-b`, and other non-destructive forms.

**Depends on**: Task 0a (Q1 result determines primary vs fallback); Task 3 must be committed first (commit ordering per spec).

**Context**: R8 is symmetric with the 054-R2 treatment of `Bash(git restore *)` (already in ask). Destructive discard-changes form (`git checkout -- <file>`) is the risk. Pipeline callers (`bin/git-sync-rebase.sh`, `claude/pipeline/conflict.py`) use `git checkout --theirs` via subprocess directly, not Claude's Bash tool — they are unaffected by this permission change regardless of D1 outcome.

**Verification** (primary path — adjust if fallback):
- `python3 -m json.tool claude/settings.json > /dev/null` exits 0
- `jq '.permissions.ask | map(select(. == "Bash(git checkout -- *)")) | length' claude/settings.json` returns `1`
- `jq '.permissions.deny | map(select(. == "Bash(git checkout -- *)")) | length' claude/settings.json` returns `0`
- Re-verify Tasks 1, 2, 3 acceptance criteria remain passing (cumulative invariant)

**Commit subject**: `Add Bash(git checkout -- *) to ask tier`

**Status**: [ ]

---

### Task 5 — R2+R3+R4: Remove docker/make/pip3 from allow

**Files**: `/Users/charlie.hall/Workspaces/cortex-command/claude/settings.json`

**What**: Remove three entries from `permissions.allow`:
1. Remove `"Bash(docker *)"` (currently at line 111)
2. Remove `"Bash(make *)"` (currently at line 112)
3. Remove `"Bash(pip3 *)"` (currently at line 108)

Do NOT add any of these to ask or deny — pure removal per the 057 pattern. They fall through to the default prompt on invocation.

**Depends on**: Task 4 must be committed first (commit ordering per spec).

**Context**: All three have zero runtime callers in the repo (grep-verified in research). Docker is incompatible with the sandbox per Anthropic docs. Make's `-n` dry-run is not safe. pip3 install runs setup.py (arbitrary code). `uv run`/`uv sync` remain in allow as the canonical Python tooling. Pure removals do NOT propagate to existing installs' `settings.local.json` — existing users must run `just setup-force` or manually clean.

**Verification**:
- `python3 -m json.tool claude/settings.json > /dev/null` exits 0
- `jq '.permissions.allow | map(select(. == "Bash(docker *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.ask | map(select(. == "Bash(docker *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.deny | map(select(. == "Bash(docker *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.allow | map(select(. == "Bash(make *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.ask | map(select(. == "Bash(make *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.deny | map(select(. == "Bash(make *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.allow | map(select(. == "Bash(pip3 *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.ask | map(select(. == "Bash(pip3 *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.deny | map(select(. == "Bash(pip3 *)")) | length' claude/settings.json` returns `0`
- Re-verify Tasks 1, 2, 3, 4 acceptance criteria remain passing (cumulative invariant)

**Commit subject**: `Remove blanket docker/make/pip3 allows (no repo callers)`

**Status**: [ ]

---

### Task 6 — R5+R6: Move npm/brew to ask tier

**Files**: `/Users/charlie.hall/Workspaces/cortex-command/claude/settings.json`

**What**:
1. Remove `"Bash(npm *)"` from `permissions.allow` (currently at line 106).
2. Remove `"Bash(brew *)"` from `permissions.allow` (currently at line 124).
3. Add `"Bash(npm *)"` to `permissions.ask`.
4. Add `"Bash(brew *)"` to `permissions.ask`.

**Depends on**: Task 5 must be committed first (commit ordering per spec).

**Context**: npm has legitimate callers (ui-setup, ui-judge, ui-a11y, ui-lint) but wholesale ask is chosen over scoped subcommand allows because `npm run <script>` executes arbitrary code from package.json (supply-chain risk, GHSA-c292-qxq4-4p2v). Session-scoped ask: each skill's first npm invocation prompts once per session. brew has zero runtime callers; Trail of Bits 2024 audit found brew allows arbitrary code execution by design. Both moves propagate via the sync hook's union merge (ask entries added; pre-existing allow entries in `settings.local.json` are overridden by the ask taking matcher precedence at runtime).

**Verification**:
- `python3 -m json.tool claude/settings.json > /dev/null` exits 0
- `jq '.permissions.allow | map(select(. == "Bash(npm *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.ask | map(select(. == "Bash(npm *)")) | length' claude/settings.json` returns `1`
- `jq '.permissions.deny | map(select(. == "Bash(npm *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.allow | map(select(. == "Bash(brew *)")) | length' claude/settings.json` returns `0`
- `jq '.permissions.ask | map(select(. == "Bash(brew *)")) | length' claude/settings.json` returns `1`
- `jq '.permissions.deny | map(select(. == "Bash(brew *)")) | length' claude/settings.json` returns `0`
- Re-verify Tasks 1–5 acceptance criteria remain passing (cumulative invariant)

**Commit subject**: `Move Bash(npm *) and Bash(brew *) to ask tier`

**Status**: [ ]

---

### Task 7 — Post-commit smoke check (R10 terminal + AC#4 qualitative)

**Files**: none (verification only; no file changes)

**What**: After all 6 commits land, run the terminal qualitative smoke check required by the spec's Technical Constraints:
1. `python3 -m json.tool claude/settings.json > /dev/null` exits 0 (R10 terminal acceptance).
2. In a fresh interactive Claude Code session, invoke one representative command per ask-tier change:
   - `curl http://localhost:9999/test` — verify ask prompt appears (R1)
   - Any `tee /tmp/test-file.txt` invocation — verify ask prompt appears (R7)
   - `npm --version` — verify ask prompt appears (R5)
   - `brew --version` — verify ask prompt appears (R6)
3. `gh pr list` — verify it still works (sanity check that nothing sandbox-adjacent was accidentally perturbed).
4. If any step produces a hard failure (not a prompt), halt and identify the responsible commit for revert/amend before PR merges.

**Depends on**: Task 6 must be committed first (all commits landed).

**Verification**: All commands in step 2 produce a permission ask prompt (not a silent allow or hard error). `gh pr list` returns output without error. `python3 -m json.tool` exits 0.

**Status**: [ ]

---

## Verification Strategy

**Per-commit invariant (R10)**: Every task that commits runs `python3 -m json.tool claude/settings.json > /dev/null` as the first verification step. If this fails, the commit is halted and the JSON error is fixed before proceeding.

**Cumulative acceptance invariant**: Each commit's verification section includes re-running all previously-passing acceptance criteria (the jq checks from all prior tasks). This ensures no commit silently regresses an earlier fix.

**Decision-gating**: Tasks 0a (Q1), 0b (Q4), and 0c (Q3) run before any commits. Their outcomes gate the content of Tasks 4 and 2 respectively. The executor records the outcome of each in the corresponding commit message (D1 path taken for commit 4, D2 path taken for commit 2, Q3 result for commit 1's residual risk note).

**Terminal verification**: Task 7 (smoke check) provides the qualitative AC#4 gate. A hard failure at smoke check triggers a halt-and-investigate before PR merge.

**Overnight impact**: Zero. The overnight runner uses `--dangerously-skip-permissions`, which bypasses the permission matcher entirely. This spec makes no changes to `sandbox.*` keys. No overnight regression is possible from these changes.

**Propagation**: deny additions and ask additions propagate to existing installs via the `cortex-sync-permissions.py` union merge on next SessionStart. Allow removals (R2/R3/R4) do NOT propagate — this is accepted per the 056 non-requirement. Existing users who want the R2/R3/R4 removals can run `just setup-force`.
