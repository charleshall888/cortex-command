"""Regression: the `cortex-backlog` plugin token must not shadow the backlog
`cortex-*` console scripts after it joins ``PLUGIN_NAMES``.

``PLUGIN_NAMES`` membership excludes a token from BOTH the reference-candidate
scan (E002/W003) and the wiring scan. Adding ``cortex-backlog`` as a plugin name
must exclude only the bare ``cortex-backlog`` token — not the longer
``cortex-backlog-ready`` / ``cortex-*-backlog-*`` console-script tokens, which
``TOKEN_RE`` captures as distinct word-boundaried tokens. This test exercises the
real scanner functions (``collect_reference_candidates``, ``collect_wiring_signals``)
and ``TOKEN_RE`` rather than asserting a hand-rolled stub.
"""

from __future__ import annotations

from cortex_command.parity_check import (
    PLUGIN_NAMES,
    TOKEN_RE,
    collect_reference_candidates,
    collect_wiring_signals,
)

# The backlog engine's console scripts that must stay visible to the scanner.
BACKLOG_SCRIPTS = (
    "cortex-backlog-ready",
    "cortex-create-backlog-item",
    "cortex-resolve-backlog-item",
    "cortex-update-item",
    "cortex-generate-backlog-index",
)

# Path-qualified mentions are always candidates and always wiring signals; the
# bare plugin token sits in inline code alongside them.
SAMPLE = (
    "The backlog skill runs `bin/cortex-backlog-ready`, "
    "`bin/cortex-create-backlog-item`, `bin/cortex-resolve-backlog-item`, "
    "`bin/cortex-update-item`, and `bin/cortex-generate-backlog-index`. "
    "Install the `cortex-backlog` plugin to get the interactive surface."
)


def test_cortex_backlog_is_a_plugin_name() -> None:
    assert "cortex-backlog" in PLUGIN_NAMES


def test_token_re_does_not_shadow_longer_backlog_tokens() -> None:
    # TOKEN_RE is greedy/word-boundaried: it captures the full script token,
    # never truncating it to the bare `cortex-backlog` plugin prefix.
    for script in BACKLOG_SCRIPTS:
        assert TOKEN_RE.findall(script) == [script]
    assert TOKEN_RE.findall("cortex-backlog") == ["cortex-backlog"]


def test_backlog_scripts_stay_candidates() -> None:
    candidates = collect_reference_candidates(SAMPLE)
    for script in BACKLOG_SCRIPTS:
        assert script in candidates, f"{script} dropped from candidates"
    # The bare plugin token is excluded by PLUGIN_NAMES membership.
    assert "cortex-backlog" not in candidates


def test_backlog_scripts_stay_wired() -> None:
    wired = collect_wiring_signals(SAMPLE)
    for script in BACKLOG_SCRIPTS:
        assert script in wired, f"{script} dropped from wiring signals"
    # The bare plugin token is excluded by PLUGIN_NAMES membership.
    assert "cortex-backlog" not in wired
