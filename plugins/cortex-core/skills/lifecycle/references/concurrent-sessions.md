# Concurrent Sessions

Multiple sessions can work on different features simultaneously. Each session associates with one feature via the gitignored, SessionEnd-cleaned `cortex/lifecycle/{feature}/.session` file, written by SKILL.md Step 2's Register-session step from `$LIFECYCLE_SESSION_ID` (set by the SessionStart hook). Do not commit `.session` files.

**Listing incomplete features**: If multiple incomplete `cortex/lifecycle/*/` directories exist and the user has not specified which to work on, list them and ask which to resume. Completed features (those with a `feature_complete` event in `events.log`, or `review.md` containing an APPROVED verdict) are ignored.
