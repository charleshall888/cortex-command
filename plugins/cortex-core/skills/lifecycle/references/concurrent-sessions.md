# Concurrent Sessions

Multiple sessions can work on different features simultaneously. Each session associates with one feature via the gitignored, SessionEnd-cleaned `cortex/lifecycle/{feature}/.session` file, written at SKILL.md Step 2's Register-session step from `$LIFECYCLE_SESSION_ID` (set by the SessionStart hook). Do not commit `.session` files.

<!-- pause: resume-feature-pick question -->
**Listing incomplete features**: if multiple incomplete `cortex/lifecycle/*/` directories exist and the user hasn't specified which to work on, list them and ask which to resume. Completed features (`feature_complete` in `events.log`, or an APPROVED verdict in `review.md`) are ignored.
