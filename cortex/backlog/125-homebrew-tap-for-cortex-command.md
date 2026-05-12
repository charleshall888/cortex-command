---
schema_version: "1"
uuid: 8ca55836-e562-400e-952b-1d91b23fe2f8
title: "Homebrew tap as thin wrapper around the curl installer"
status: wontfix
priority: low
type: feature
parent: 113
tags: [distribution, homebrew, overnight-layer-distribution]
areas: [install]
created: 2026-04-21
updated: 2026-04-24
lifecycle_slug: homebrew-tap-as-thin-wrapper-around-the-curl-installer
lifecycle_phase: complete
session_id: null
blocks: []
blocked-by: [118]
discovery_source: cortex/research/overnight-layer-distribution/research.md
complexity: complex
criticality: medium
---

# Homebrew tap as thin wrapper around the curl installer

## Context from discovery

Homebrew is a familiar discovery surface for macOS users but is sandbox-hostile for writing to `$HOME` (formula `post_install` re-runs on every `brew upgrade` and would clobber user customizations). DR-4 recommends a Homebrew tap that wraps the bootstrap installer from ticket 118 — the formula doesn't own `~/.claude/` deployment, it just runs the curl script once and prints `caveats` telling the user to run `cortex setup`. This gives brew users the familiar `brew install` entry without the sandbox-hostile `post_install` pitfall.

Low priority because the bootstrap installer already covers macOS via `curl | sh`; brew is discoverability, not a functional win.

## Scope

- Separate GitHub repo `charleshall888/homebrew-cortex-command` (or similar) — Homebrew requires the tap to be in a repo named `homebrew-<tapname>`
- Formula that runs `curl -fsSL https://cortex.sh/install | sh` in `install do system "..."` block
- `caveats` block directing users to run `cortex setup` after install
- Upgrade path: `brew upgrade` re-runs the curl script; `cortex upgrade` continues to be the in-CLI upgrade verb
- README pointing users at `cortex-command` as the source of truth

## Out of scope

- Formula that handles `~/.claude/` deployment directly (explicitly rejected — see DR-4 sharp edges)
- Linux package managers (apt/deb/rpm) — no prior art in this space; cortex-command user base doesn't justify
- Shipping cortex-command as a Python formula with `virtualenv_install_with_resources` — more complexity than a curl wrapper, no added value

## Research

See `research/overnight-layer-distribution/research.md` DR-4 trade-offs (Homebrew tap as thin wrapper), `_cli-packaging-report.md` Homebrew section (specifically the `post_install` runs on every `brew upgrade` problem), and the prior-art scan ("no surveyed project ships primarily via Homebrew").

## Closure (2026-04-24): wontfix

Closed after full lifecycle research + spec-phase architectural challenge. The wrapper-Formula approach the ticket proposes was found architecturally unsupported:

- **Pattern B (wrapper Formula) is unprecedented**: 0 of 11 surveyed real-world tools with both a `curl | sh` installer and a brew presence ship a Formula that wraps the curl script (rustup, uv, nvm, starship, deno, bun, fzf, gh, flyctl, cloudflared, railway). Expanded to a Python-CLI cohort (poetry, pipx, pdm, hatch, httpie, ansible) — independently 0/6. All surveyed tools build from source or download pre-built binaries independently in their formula.
- **Homebrew's `Empty installation` check** is a runtime invariant (`Library/Homebrew/keg.rb` `empty_installation?`) enforced regardless of tap-vs-core. A wrapper formula whose install block delegates to a curl script that places files outside the formula's prefix triggers the error. Documented mitigations (kiro-cli `--prefix` pattern, placeholder file, shim wrapper) are all hacks against brew's design.
- **Maintainer guidance** (Homebrew Discussion #4717, #5388) consistently redirects wrapper-formula proposals to either "build from source" or "ship in your own tap" — never "wrap the installer."
- **Cask alternative** with `auto_updates true` (gcloud-cli / miniforge precedent) makes `brew upgrade` a documented no-op, so it doesn't solve the upgrade-verb conflict either — it just names the mismatch.

**Full research artifact**: `lifecycle/archive/homebrew-tap-as-thin-wrapper-around-the-curl-installer/research.md`.

**Separable concerns that emerged during this ticket's design review**:

- **Option 2 (from-source Formula via `uv tool install --from git+url@tag`)** was prematurely dismissed in this ticket's original "Out of scope" line; the original rejection covers only `virtualenv_install_with_resources`, not all from-source paths. This is the survey's 9-of-11 consensus pattern. Not pursued here but documented for future work — if macOS-brew discoverability becomes a priority, this is the architecturally-honest path.
- **DR-4 discoverability surface**: the parent epic 113's DR-4 recommended a brew tap specifically for `brew search` discoverability. Closing this ticket leaves that rationale partially unaddressed. An epic-level decision record should be added (revise DR-4 or accept the loss); deferred.
- **CLI auto-update UX** surfaced as a separately feasible improvement: see ticket 145 (Lazy-apply cortex CLI auto-update via SessionStart probe + in-process apply-on-invoke). Addresses a different concern (upgrade UX, not discoverability); measured-feasible at <1 day implementation cost.
