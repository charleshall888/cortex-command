"""Cortex auth subcommand package.

Houses the handlers for ``cortex auth bootstrap`` and ``cortex auth status``.
The bootstrap handler wraps ``claude setup-token`` to mint a subscription
OAuth token and atomically write it to ``~/.claude/personal-oauth-token``;
the status handler reports the resolved auth vector via
:func:`cortex_command.overnight.auth.ensure_sdk_auth`. Both handlers expose
a ``run(args) -> int`` entry point matching the rest of
:mod:`cortex_command.cli`.
"""
