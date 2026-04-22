# Plan: Harden retry loop in overnight runner — skip retries on 4xx errors

## Background

The overnight runner dispatches Claude API calls in a loop. When any call fails, the runner
retries with exponential backoff (initial delay 2 s, multiplier 2×, max 4 retries). In
production incidents the retry loop has been observed re-submitting requests that received
`422 Unprocessable Entity` and `400 Bad Request` responses, wasting wall-clock time and
burning token quota on requests that are structurally invalid and will never succeed.

## Proposed Fix

Add a check in the retry predicate so that HTTP 4xx status codes short-circuit the retry
loop immediately. The check runs before the sleep/backoff calculation so no unnecessary wait
occurs.

```python
def should_retry(exc: Exception, attempt: int, max_attempts: int) -> bool:
    if attempt >= max_attempts:
        return False
    if isinstance(exc, APIStatusError) and exc.status_code // 100 == 4:
        return False   # <-- new: skip retries for all 4xx errors
    return True
```

The runner logs a structured message when the early-exit fires:

```
{"event": "retry_skipped", "reason": "4xx_status", "status_code": <N>, "attempt": <attempt>}
```

## Rationale

4xx errors indicate a client-side problem (malformed request, invalid auth token, payload too
large). Retrying them cannot produce a different outcome — the request is structurally invalid
and the server will reject it identically on every attempt.

## Implementation Notes

- `APIStatusError` is the Anthropic SDK exception class that carries `status_code`.
- `should_retry` is called from the single retry-loop callsite in `claude/overnight/runner.py`.
- No changes to the backoff calculation itself; only the early-exit predicate is added.
- Log line uses the existing structured-logging helper so it appears in `events.log`.
