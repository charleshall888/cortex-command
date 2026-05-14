#!/usr/bin/env bash
# PATH-injected `claude` stub: banner-trailing shape for `setup-token`.
#
# Used by tests for `cortex auth bootstrap` to emulate `claude setup-token`
# emitting the token line followed by a multi-line upgrade banner. The
# banner deliberately includes a `sk-ant-oat01-`-shaped substring inside a
# URL to verify the bootstrap regex's `^...$` line anchors reject substring
# matches and only accept whole-line token matches.
#
# Behavior:
#   `setup-token --help`  -> exit 0, no output (verb-probe path)
#   `setup-token` (mint)  -> exit 0, prints token line, blank line, then a
#                            two-line banner on stdout
#   anything else         -> exit 0, no output

set -u

if [ "${1:-}" = "setup-token" ] && [ "${2:-}" = "--help" ]; then
    exit 0
fi

if [ "${1:-}" = "setup-token" ]; then
    printf '%s\n' 'sk-ant-oat01-FIXTURE-TOKEN-VALUE-FOR-TESTS-ONLY'
    printf '\n'
    printf '%s\n' "WARNING: Claude Code v9.99.0 is now available — run 'npm i -g @anthropic/claude' to upgrade."
    printf '%s\n' 'Release notes: https://example.com/notes/v9.99.0-sk-ant-oat01-release.html'
    exit 0
fi

exit 0
