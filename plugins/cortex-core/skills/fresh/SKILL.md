---
name: fresh
description: Capture the current session state as a resume prompt you can paste into a fresh context window. Use when user says "/cortex-core:fresh", "fresh context", "context is full", "start fresh", or wants to continue work in a new window. Reads the conversation, identifies ephemeral context not captured in files, and outputs a ready-to-paste prompt.
disable-model-invocation: true
---

# Fresh

Read the current conversation and generate a resume prompt the user can paste into a new window to continue without re-reading the conversation.

## Steps

0. **Run /cortex-core:retro if this is a human-initiated session.** Check whether this is an automated session:

   ```bash
   [ "${CLAUDE_AUTOMATED_SESSION:-0}" = "1" ]
   ```

   - If the variable is **not set** (exit code 1 — human session): run `/cortex-core:retro` now, before proceeding, while full session context is still available.
   - If the variable **is set to 1** (automated session): skip the retro and continue directly to step 1.

1. **Read the conversation.** Identify:
   - What was the main topic or work (the "current context")
   - Decisions or conclusions reached — especially the *why*, not just the *what*
   - In-progress reasoning or exploration not yet committed to a file
   - User preferences or constraints stated during the session
   - Unresolved questions or blockers
   - Files created or modified during the session (if any)
   - If a lifecycle feature was being worked on **in this conversation**: feature name, current phase, last completed task, resume command (e.g. `/cortex-core:lifecycle feature-name`)
   - If a pipeline was being run **in this conversation**: phase, feature statuses, resume command (`/pipeline resume`)

   Only include lifecycle/pipeline context if it was part of the conversation. Do not scan for active lifecycles or pipelines on disk.

2. **Generate an adaptive resume prompt.**
   - **Short or simple session** (brief Q&A, quick exploration, no files changed): 2-5 sentences of prose, no headers
   - **Rich session** (active lifecycle/pipeline, files written, multi-step decisions, unresolved blockers): light structure with headers — **Context**, **Files** (if any were written), **Next Steps**
   - Focus on what a fresh agent *cannot* recover from files alone. Skip recapping what the SessionStart hook or lifecycle artifacts already surface automatically.
   - Include resume commands where relevant (e.g. `/cortex-core:lifecycle feature-name`, `/pipeline resume`)

3. **Output the prompt** directly in the conversation, clearly delimited so the user can copy it:

   ````
   ---
   [resume prompt here]
   ---
   ````
