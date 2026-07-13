# Requirements: training

> Last gathered: 2026-07-13

**Parent doc**: [requirements/project.md](project.md)

## Overview

Publicly shareable training materials teaching people to use Claude Code and agentic coding harnesses well — the mental models and skill ladder, not a feature tour. Serves three audience tiers (non-technical "beyond-ChatGPT" beginners, intermediate LLM users leveling up, expert engineers) and four delivery modes (send-a-link self-serve, 1:1, small-group workshop, department-scale presentation) by sharing one animation component library across hand-authored deliverables — the visuals are the reused asset; each deliverable owns its own words and arc. Lives in this repo as published *content* (a deliberate carve-out from the project's "no published modules" boundary), shipping from `docs/training/` on the existing GitHub Pages path beside the landing page.

The curriculum skeleton is a harness-agnostic skill ladder (chatbot user → autocomplete user → pair programmer → delegator → context engineer → systems builder) taught through five unlocks: *give it eyes; let go of the keyboard; write the ticket, not the wish; never say it twice; make it check itself*. Audiences differ in which rungs get dwell time, not in the story.

**V1** is a workshop-ready scene deck (small-group workshop and 1:1 use are the forcing functions). **Wave 2** (deferred, not dropped): the Cockpit branching simulator, the retention kit (delegation cheat sheet + 7-day challenge ladder), hands-on exercise scenes, and the self-serve guide page (fresh prose over the same components). **Permanently out**: LMS/completion tracking, certification, leaderboards, and produced video/screen recordings — concepts are conveyed by animated SVG scenes and a scripted mock-terminal component, never by recordings of real sessions. The cortex-command harness appears only as a closing horizon scene, never as curriculum.

## Functional Requirements

### Workshop scene deck

- **Description**: One self-contained hand-authored HTML deck of 12–18 scenes (v1) that follow the skill-ladder arc, built on the animation component library. Interactive checkpoints are presenter-led show-of-hands moments at the presenter's discretion — audience data-entry polls were cut by presenter decision 2026-07-13. Includes the "same ideas, different cockpits" dialect scene mapping concepts to Cursor/Codex equivalents, and a cortex-command horizon closer.
- **Inputs**: The component library; deck-owned prose (on-screen talking points + presenter talk track).
- **Outputs**: A presentable deck (workshop and keynote variants) that doubles as a 1:1 vocabulary map.
- **Acceptance criteria**:
  - A 60–90 minute small-group workshop can be run end-to-end from the deck alone.
  - Works offline on a workshop projector (no network fetches at present time).
  - Present-mode surfaces stay sparse: images, animations, talking points — the presenter carries the words.
- **Priority**: must

### Animation component library

- **Description**: Reusable vanilla JS+SVG components for the signature visuals — context vessel, agent loop, subagent fan-out, permission gates, plan-mode blueprint, mock terminal. This is the shared asset across all deliverables and where the build investment concentrates. Words are deliberately NOT abstracted: each deliverable hand-authors its own prose in its own register (presenter talk track vs. standalone narration are different genres, not different densities).
- **Inputs**: Component parameters and scripted beat sequences per use site.
- **Outputs**: Embeddable animations in any training page.
- **Acceptance criteria**:
  - The v1 deck is built from library components plus deck-owned words; no words live in the library.
  - A component fix propagates to every deliverable without touching any deliverable's prose.
- **Priority**: must

### Mock-terminal component

- **Description**: A reusable stylized terminal display that plays scripted, idealized session beats (prompt in, agent loop visibly working, results landing) — clean, deterministic, projector-legible. Replaces all session recordings and real-UI screenshots; becomes the seed of the wave-2 Cockpit engine.
- **Inputs**: Scripted beat sequences per scene.
- **Outputs**: In-scene terminal animations.
- **Acceptance criteria**: No recordings of real Claude sessions anywhere in the deck; demo-slot scenes document the live demo's setup and takeaway instead of embedding footage.
- **Priority**: must

### Deck variants

- **Description**: The v1 workshop deck is one hand-authored present-mode page (full-bleed, keyboard-driven, with workshop checkpoints). The department-scale keynote is the same page with scenes/stops marked skippable (query param or presenter discipline) — a restriction, not a second artifact and not a playlist engine. The wave-2 self-serve guide is a separate hand-authored scrollytelling page with freshly written narration, reusing the component library.
- **Inputs**: The workshop deck; skippable-section markers.
- **Outputs**: Workshop rendering, keynote rendering; later a standalone guide page.
- **Acceptance criteria**: No playlist/scene-schema machinery is built to support the keynote variant.
- **Priority**: must (workshop + keynote); deferred (self-serve guide, hands-on exercises)

## Non-Functional Requirements

- **Offline self-containment**: fonts, scripts, and assets bundled; no CDN or network dependency during presentation.
- **Present-mode sparseness bar**: if a scene needs paragraphs on screen to land in a live room, it fails review — move the words to the presenter talk track (or save them for the wave-2 guide page).
- **Volatility quarantine**: volatile facts (feature names, UI details, flags, model names, pricing) may appear only in blocks tagged with a greppable in-file marker (e.g. `<!-- volatile -->`). Concept scenes must pass: *would this scene still be true if the tool's UI changed completely?*
- **Maintenance sweep**: a quarterly pass greps the volatile markers and opens only those blocks; the durable spine is never bulk-edited on tool releases.
- **Tool stance**: agnostic spine, Claude Code demos — mental models are harness-agnostic by construction; every concrete demo is confidently Claude Code; the dialect scene absorbs Cursor/Codex parity; no parallel tool tracks. The presenter's own workflow (e.g. `/requirements`, `/discovery`) may appear as a worked example in small volatile-marked chips over generic stage labels — the harness is never taught as curriculum (amended 2026-07-13 per presenter direction).

## Architectural Constraints

- Ships from `docs/training/` on the existing GitHub Pages path (canonical site already publishes from `docs/`).
- Vanilla JS + SVG; no build step, no Node toolchain in the repo.
- Shared code lives in the component library (`docs/training/lib/`); each deliverable is a hand-authored page that owns its own words and arc. The code/content boundary is the component API — words are never stored separately from their presentation.
- Scenes-as-data machinery (scene schemas, word-track layers, playlist files) is deliberately NOT built in v1; extraction is gated by a rule-of-three trigger (see Open Questions).
- Training content is not lifecycle-gated source (`skills/`, `hooks/`, etc.); repo-wide conventions (commit skill, valid JSON, etc.) still apply.

## Dependencies

- **Internal**: GitHub Pages publishing from `docs/` on main; `cortex/requirements/glossary.md` (terms: *scene*, *cockpit*); parent project doc Conditional Loading row (training/workshop/presentation → this doc).
- **Source material**: the 2026-07-13 ideation rounds, persisted as `cortex/research/training-ideation-digest.md` (skill ladder + five unlocks, audience-tier architecture, wave-2 format designs, prior-art stealables with sources, standing craft rules) alongside `training-talk-messaging-brief.md` and `training-talk-deck-outline.md`.
- **External**: none — no new binaries, services, or env vars.

## Edge Cases

- **Mixed-tier big room**: don't pretend tier targeting — use the keynote variant at the shared T1–T2 altitude; goal shifts to motivation and shared vocabulary, not skill transfer.
- **Wording divergence between registers**: expected and accepted by design — each deliverable authors its own words; only visuals cross over. Never force prose reuse between the presenter and self-serve registers.
- **1:1 sessions**: the deck serves as a vocabulary map beside a real terminal; the expert-engineer 1:1 cell stays deliberately unauthored — its value is working in their codebase live.
- **Live demo requested anyway**: demo-slot scenes carry the setup and the takeaway ("show it recovering from a failing test; the point is the loop"), so a presenter can run a live demo outside the deck without the deck depending on its outcome.

## Open Questions

- **Scene-schema extraction**: v1 deliberately hand-authors each deliverable over the shared component library. Decision trigger (rule of three): if a third deliverable reveals structural duplication beyond what components absorb — the same scene sequencing, metadata, or tier logic copy-pasted across pages — extract scenes-as-data then, with the schema informed by real authored content.
- **Metaphor commitment**: the Workshop/contractor system (with the amnesiac-new-hire cold open) is recommended but not user-confirmed — decide at scene-authoring time.
- **Retention kit timing**: deferred to wave 2, but the learning-design finding (the leave-behind carries a third of a workshop's value) says revisit after the first real workshop.
