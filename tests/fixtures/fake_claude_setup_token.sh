#!/usr/bin/env bash
# PATH-injected `claude` stub: clean shape for `setup-token`.
#
# Used by tests for `cortex auth bootstrap` to emulate `claude setup-token`
# emitting only the minted OAuth token line.
#
# Behavior:
#   `setup-token --help`  -> exit 0, no output (verb-probe path)
#   `setup-token` (mint)  -> exit 0, prints a canned token line on stdout
#   anything else         -> exit 0, no output
#
# The canned token satisfies the regex
#   ^sk-ant-oat[0-9]+-[A-Za-z0-9_-]{20,}$
# so the bootstrap regex extractor will accept it.

set -u

if [ "${1:-}" = "setup-token" ] && [ "${2:-}" = "--help" ]; then
    exit 0
fi

if [ "${1:-}" = "setup-token" ]; then
    printf '%s\n' 'sk-ant-oat01-FIXTURE-TOKEN-VALUE-FOR-TESTS-ONLY'
    exit 0
fi

exit 0
