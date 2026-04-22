#!/usr/bin/env bash
# PATH-injected `gh` stub for tests/test_runner_pr_gating.py.
#
# Dispatches on the first two positional arguments. Reads $GH_STUB_SCENARIO
# (default: empty) to pick a canned response for `gh pr view --head ...`.
# For `gh pr ready` (and `gh pr ready --undo`), picks behavior based on
# $GH_STUB_READY_MODE (default: ok).
#
# Scenarios for `gh pr view`:
#   open-ready-mismatch         -> {"url":"https://example.test/pr/1","isDraft":false,"state":"OPEN"}
#                                  (merged>0 intended=false matches, merged=0 intended=true MISMATCHES)
#   open-draft-mismatch         -> {"url":"https://example.test/pr/1","isDraft":true,"state":"OPEN"}
#                                  (merged=0 intended=true matches, merged>0 intended=false MISMATCHES)
#   merged                      -> {"url":"https://example.test/pr/1","isDraft":false,"state":"MERGED"}
#   closed                      -> {"url":"https://example.test/pr/1","isDraft":false,"state":"CLOSED"}
#   <empty / unset>             -> empty stdout, exit 1 (no PR found)
#
# Modes for `gh pr ready` / `gh pr ready --undo`:
#   ok (default) -> exit 0, empty stderr
#   transient    -> exit 1, stderr contains "HTTP 429 rate limit exceeded"
#   persistent   -> exit 1, stderr contains "HTTP 401 unauthorized"
#
# All other gh invocations exit 0 with empty output (harmless).

set -u

cmd="${1:-}"
sub="${2:-}"

case "$cmd" in
    pr)
        case "$sub" in
            view)
                scenario="${GH_STUB_SCENARIO:-}"
                case "$scenario" in
                    open-ready-mismatch)
                        printf '%s\n' '{"url":"https://example.test/pr/1","isDraft":false,"state":"OPEN"}'
                        exit 0
                        ;;
                    open-draft-mismatch)
                        printf '%s\n' '{"url":"https://example.test/pr/1","isDraft":true,"state":"OPEN"}'
                        exit 0
                        ;;
                    merged)
                        printf '%s\n' '{"url":"https://example.test/pr/1","isDraft":false,"state":"MERGED"}'
                        exit 0
                        ;;
                    closed)
                        printf '%s\n' '{"url":"https://example.test/pr/1","isDraft":false,"state":"CLOSED"}'
                        exit 0
                        ;;
                    *)
                        # No scenario -> pretend no PR exists
                        exit 1
                        ;;
                esac
                ;;
            ready)
                mode="${GH_STUB_READY_MODE:-ok}"
                case "$mode" in
                    ok)
                        exit 0
                        ;;
                    transient)
                        printf '%s\n' 'HTTP 429: rate limit exceeded' >&2
                        exit 1
                        ;;
                    persistent)
                        printf '%s\n' 'HTTP 401: unauthorized' >&2
                        exit 1
                        ;;
                    *)
                        exit 0
                        ;;
                esac
                ;;
            create)
                # Not expected to be invoked in dry-run mode (runner wraps it
                # in dry_run_echo); if it is, emit a fake URL so the success
                # branch is taken and no recovery path triggers.
                printf '%s\n' 'https://example.test/pr/created'
                exit 0
                ;;
            *)
                exit 0
                ;;
        esac
        ;;
    *)
        # Any other gh command: harmless no-op.
        exit 0
        ;;
esac
