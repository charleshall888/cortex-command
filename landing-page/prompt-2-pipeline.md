# Prompt 2 — Pipeline activation, day/night, second toast, ink cursor behaviors

Run this in the same Claude Design project as Prompt 1, after v1 of the foundation passes the fallback-trigger checklist. Save the project before sending.

---

The spec-document concept from v1 is the substrate — this prompt assumes v1 passed the acceptance check (visible section-lock state changes; sidebar indicators paired to specific spec sections). Do not run this prompt if v1 did not pass.

Now make the lower half of the page (pipeline activation through dawn) genuinely choreographed.

PIPELINE BEHAVIOR. Sticky viewport, ~3 viewport heights max. Scroll-scrub the camera and work-trains, not every animated element — particles and ambient motion run on their own clocks.

PIPELINE STRUCTURE MIRRORS THE SPEC ABOVE. The fishing spec has 4 research branches (Stardew, Sea of Thieves, Dredge, real-world nightline technique) — so Discovery fans out to exactly 4 rails, labeled with those references. Refine spawns one rail per implementation task from the Plan section: tackle data model, cast/set screen, overnight resolver, dawn reveal animation, catch encyclopedia — exactly 5 rails. The pipeline is not generic stagecraft; it visibly executes the spec the viewer just read.

60-SECOND SEQUENCE.
- 0-6s: Spec is locked. Pipeline rails draw in left-to-right with a draftsman's stroke (1.2s).
- 6-18s: Discovery fans out to the 4 named research branches. Trains travel each rail; reconverge to a labeled "backlog: 5 refine tickets" node.
- 18-30s: Refine spawns 5 parallel rails (one per Plan task). Each runs Clarify→Research→Spec in miniature.
- 30-42s: Day → night transition. Page desaturates over 2-3s (CSS filter saturate 1→0.4, brightness 1→0.85). Deep blue overnight rail ignites. Starfield fades in behind at 0.15 opacity. Patient, not dramatic.
- 42-55s: Parallel worktrees run; each emits a small PR badge that travels to the morning-review converge point.
- 55-60s: Dawn. Page re-saturates over 2s. Gold morning-review rail converges.

ACHIEVEMENT TOASTS (now two, in this order):
- "ACHIEVEMENT — Spec Earned" fires at the end of v1's spec-locking sequence (already in v1, confirm placement).
- "ACHIEVEMENT — First Light" fires at dawn. Subtitle: "Overnight run completed before you woke up." Slide in from bottom-right, 400ms ease-out, dwell 4s, fade out.

STILL-FRAME POSTER REQUIREMENT. The pipeline's sticky scroll-scrub MUST degrade gracefully. A viewer who fast-scrolls past must land on a comprehensible static poster frame at the section's natural resting state — discovery fan-out frozen at 50% (showing all 4 research rails clearly), day/night caught at dusk, swimlane labels readable. This poster frame is what I'll screenshot for the README hero. Test by scrolling fast and confirming the rendered frame is readable.

INK CURSOR BEHAVIORS (now activated). The cursor from v1 follows the active rail subtly during pipeline activation — eased follow with ~120ms lag, no walk cycle, no bobbing. At fan-out points, brief 180ms pause at the junction, then continues. In the spec section above, the cursor occasionally underlines a phrase as it locks (specifically: underline "felt morning" in Clarify, "sleep-while-you-fish" in Research, "the soul of the feature" in Plan). One self-correction moment: in Research, briefly write "Animal Crossing" then strike through and replace with "Sea of Thieves" — visual evidence the spec was authored, not generated.

INTERACTIVITY (minimal — restraint is the point):
- Hover any pipeline node → small popover with the node's name and the artifact path it produces (e.g., "Refine: tackle data model · produces lifecycle/{slug}/spec.md"). Tooltips, not full panels.
- No criticality toggle. No complexity slider in the pipeline section.

PLAYGROUND SECTION (after the main pipeline, collapsed by default). One element: a complexity slider (simple → complex → critical). When dragged, run a 1.5s ghost-train down the new pipeline shape so the viewer SEES which gates fire in sequence. Closed by default; revealed by a small "explore the lifecycle gates →" link.

KONAMI EASTER EGG (best-effort feature). Implement ↑↑↓↓←→←→BA → toggles "redlined spec mode": the fishing spec gains pencil annotations in a different voice (lowercase, dry, occasionally self-deprecating). Sample annotations:
- next to autonomous overnight runner: "i killed three of these before the morning report was useful. you'll probably kill two."
- next to the overnight resolver line: "the soul of the feature. mock it badly and the loop collapses. ask me how i know."
- next to "/clarify": "this gate exists because i kept skipping it and paying for it at review."
- next to install commands: "it was 7 last month. it'll probably be 2 next month."

If the keyboard-sequence handler can't be cleanly emitted on first attempt, do NOT iterate — instead provide redlined mode as a separate URL fragment (?mode=redlined) accessible via a small footer link. Do not block on this feature.

POLISH PASS in this same session: typography (optical sizing, ligatures, old-style figures), engineering-paper grid texture only at certain scroll positions, AI-tell audit (no lorem, no stock photos, no "powered by AI" badges, no sparkle/glow), WCAG AA contrast.

Show me the full v2 of the page.
