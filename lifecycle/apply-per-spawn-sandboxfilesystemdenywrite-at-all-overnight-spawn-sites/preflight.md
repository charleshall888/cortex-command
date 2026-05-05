# Pre-flight verification

> **SKELETON / PLACEHOLDER — NOT YET A PASSING ARTIFACT.**
>
> This file is a schema skeleton authored by the implementation agent. The
> actual blocking pre-flight test (spec Req 12) requires a **human** to run
> the empirical end-to-end test in a clean (non-sandboxed) terminal:
>
> 1. Construct a denying settings tempfile (e.g., `denyWrite` covering some
>    target path that the prompt instructs Claude to write).
> 2. Invoke:
>    ```
>    claude -p "$PROMPT" --settings <denying-tempfile> \
>        --dangerously-skip-permissions --max-turns 3
>    ```
>    where `$PROMPT` instructs Claude to attempt a denied write via Bash
>    (e.g., `echo test > /etc/forbidden`).
> 3. Verify: child exits non-zero AND stderr contains "Operation not
>    permitted" AND the target file was not modified.
> 4. Populate the YAML block below with real values, including
>    `commit_hash` set to whatever the cortex-command HEAD is at the time
>    of the run (`git rev-parse HEAD`) and `claude_version` set to the
>    exact output of `claude --version`.
>
> Until a human performs the run and replaces the placeholders below,
> `pass` is set to `false` so the `bin/cortex-check-parity` gate
> (spec Req 17) naturally fails when sandbox-source files are staged.

```yaml
pass: false
timestamp: "<PENDING_HUMAN_RUN>"
commit_hash: "<PENDING_HUMAN_RUN>"
claude_version: "<PENDING_HUMAN_RUN>"
test_command: "<PENDING_HUMAN_RUN>"
exit_code: 0
stderr_contains_eperm: false
stderr_excerpt: |
  <PENDING_HUMAN_RUN>
target_path: "<PENDING_HUMAN_RUN>"
target_unmodified: false
```
