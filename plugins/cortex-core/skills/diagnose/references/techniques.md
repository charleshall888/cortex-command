# Supporting Techniques

Three techniques referenced from the 4-phase debugging protocol. Read on demand when the body points here.

## Backward Root-Cause Tracing

Bugs often manifest far from their source. Your instinct is to fix where the error appears — that treats a symptom.

**Core principle**: Trace backward through the execution path until you find the original trigger, then fix at the source.

**The tracing process:**

1. Observe the symptom (e.g., "commit fails with GPG error")
2. Find the immediate cause (e.g., `git commit` exits non-zero; GNUPGHOME not set)
3. Ask: what called this? What provided the environment? (e.g., the commit skill ran, but the SessionStart hook that sets up GNUPGHOME didn't complete)
4. Keep tracing up: what caused the hook to not complete? (e.g., the extra socket path wasn't found because TMPDIR changed)
5. Fix at the source (the socket path logic in the hook) — not at the symptom (suppressing the GPG error in the commit skill)

**Adding diagnostic instrumentation** when you can't trace manually:

```bash
# In a hook script: trace execution
set -x  # prints every command as it runs

# At a key decision point: log the state
echo "DEBUG: GNUPGHOME=$GNUPGHOME, socket exists=$(test -S $GNUPGHOME/S.gpg-agent && echo yes || echo no)" >&2

# For skill invocation: add an explicit trace to the description trigger
# (temporarily add the invocation phrase you're testing to verify it triggers)
```

**Never fix just where the error appears.** Trace back to find the original trigger.

---

## Defense-in-Depth Validation

When you fix a bug caused by bad state, adding validation at one place feels sufficient — but that check can be bypassed by different code paths or edge cases.

**Core principle**: Validate at every layer data passes through. Make the bug structurally impossible.

**The four layers:**

1. **Entry point**: reject invalid input at the boundary

   ```bash
   # In a hook script: verify required env vars are set before using them
   if [ -z "$GNUPGHOME" ]; then
     echo "ERROR: GNUPGHOME not set" >&2; exit 1
   fi
   ```

2. **Business logic**: ensure data makes sense for this operation

   ```bash
   # In a lifecycle script: verify events.log is valid before appending
   if ! python3 -c "import json; [json.loads(l) for l in open('events.log')]" 2>/dev/null; then
     echo "ERROR: events.log is malformed" >&2; exit 1
   fi
   ```

3. **Environment guards**: prevent dangerous operations in specific contexts

   ```bash
   # Before destructive operations: verify you're not in the wrong directory
   if [ "$(pwd)" != "$EXPECTED_ROOT" ]; then
     echo "ERROR: wrong working directory" >&2; exit 1
   fi
   ```

4. **Debug instrumentation**: capture context for forensics

   ```bash
   # Log state at each boundary for post-mortem if something still goes wrong
   echo "DEBUG: entering hook, session=$LIFECYCLE_SESSION_ID, feature=$1" >&2
   ```

Don't stop at one validation point. Add checks at every layer.

---

## Condition-Based Waiting

Arbitrary sleeps guess at timing. This creates races where scripts pass on fast machines but fail under load or when the system is busy.

**Core principle**: wait for the actual condition you care about, not a guess about how long it takes.

**Shell-native pattern:**

```bash
wait_for() {
  local description="$1"
  local condition="$2"      # a bash test expression
  local timeout="${3:-30}"  # seconds
  local elapsed=0
  while ! eval "$condition" 2>/dev/null; do
    if [ "$elapsed" -ge "$timeout" ]; then
      echo "Timeout after ${timeout}s waiting for: $description" >&2
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
}

# Usage examples:
wait_for "events.log to appear"       '[ -s cortex/lifecycle/my-feature/events.log ]'
wait_for "task-done flag"             '[ -f /tmp/task-done.flag ]'       30
wait_for "GPG agent socket"           '[ -S "$GNUPGHOME/S.gpg-agent" ]'  10
wait_for "overnight runner to finish" 'grep -q feature_complete cortex/lifecycle/my-feature/events.log' 120
```

**Don't use when:**

- Testing actual timing behavior (a debounce or rate-limit mechanism)
- If using an arbitrary sleep, document WHY with a comment

**Common mistakes:**

- No timeout: loop forever if condition never met — always include a timeout with a clear error
- Stale state: evaluate the condition fresh inside the loop, not a cached value
