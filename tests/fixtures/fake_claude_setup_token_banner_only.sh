#!/usr/bin/env bash
# PATH-injected `claude` stub: banner-only shape for `setup-token`.
#
# Used by tests for `cortex auth bootstrap` to emulate a degenerate
# `claude setup-token` invocation that emits ONLY the upgrade banner and
# no token line at all. The bootstrap regex must reject every line of
# output and the bootstrap command must error rather than write a token
# file containing banner content.
#
# Behavior:
#   `setup-token --help`  -> exit 0, no output (verb-probe path)
#   `setup-token` (mint)  -> exit 0, prints only the two-line banner on
#                            stdout (no token line)
#   anything else         -> exit 0, no output

set -u

if [ "${1:-}" = "setup-token" ] && [ "${2:-}" = "--help" ]; then
    exit 0
fi

if [ "${1:-}" = "setup-token" ]; then
    printf '%s\n' "WARNING: Claude Code v9.99.0 is now available — run 'npm i -g @anthropic/claude' to upgrade."
    printf '%s\n' 'Release notes: https://example.com/notes/v9.99.0-sk-ant-oat01-release.html'
    exit 0
fi

exit 0
