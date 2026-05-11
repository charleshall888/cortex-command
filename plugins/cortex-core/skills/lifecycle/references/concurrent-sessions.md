# Concurrent Sessions

Multiple sessions can work on different features simultaneously. Each session is associated with one feature at a time via a `.session` file.

**Session-feature association**: When a session starts or resumes a feature, it writes its session ID to `lifecycle/{feature}/.session`:

```
echo $LIFECYCLE_SESSION_ID > lifecycle/{feature}/.session
```

`LIFECYCLE_SESSION_ID` is an environment variable set automatically by the SessionStart hook at the beginning of each session.

**`.session` files are ephemeral**: They are gitignored, cleaned up by the SessionEnd hook when the session exits, and overwritten when another session resumes the same feature. Do not commit them.

**Listing incomplete features**: If multiple incomplete `lifecycle/*/` directories exist and the user has not specified which to work on, list them and ask which to resume. Completed features (those with a `feature_complete` event in `events.log`, or `review.md` containing an APPROVED verdict) are ignored.
