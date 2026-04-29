"""Cortex Command package root.

The install-in-flight guard (R28) is now invoked only at the upgrade
dispatch path (:func:`cortex_command.cli._dispatch_upgrade`), not on
package import. This makes ``import cortex_command`` (and read-only
subcommands like ``cortex overnight status``) safe to execute while an
overnight session is mid-run. See :mod:`cortex_command.install_guard`
for the contract and remaining caller-side carve-outs.
"""

from __future__ import annotations
