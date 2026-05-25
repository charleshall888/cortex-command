"""Module entry point so ``python3 -m cortex_command.critical_review`` works.

The ``critical_review`` namespace is a package (housing the
``resolve_feature_cli`` and ``write_residue_cli`` submodules). When invoked
via ``python -m`` Python looks for ``__main__`` rather than executing the
package's ``__init__.py``, so this shim forwards to the ``main()`` function
defined alongside the package-level helpers.
"""

from __future__ import annotations

import sys

from cortex_command.critical_review import main

if __name__ == "__main__":
    sys.exit(main())
