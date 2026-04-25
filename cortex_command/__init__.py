"""Cortex Command package root.

Invokes the install-in-flight guard (R28) so an entry-point CLI
invocation aborts when an overnight session is mid-run, preventing
``uv tool install --reinstall`` from clobbering the running package.
The guard has multiple carve-outs (pytest, runner children, dashboard,
explicit opt-out, cancel-bypass) so it does NOT fire on every package
import — see :mod:`cortex_command.install_guard` for the contract.
"""

from __future__ import annotations

from cortex_command.install_guard import check_in_flight_install

check_in_flight_install()
