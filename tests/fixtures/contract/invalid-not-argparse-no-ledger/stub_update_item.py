"""Stub module without argparse — exercises E104 when no ledger entry exists.

The contract lint should refuse to silently skip not_argparse binaries.
"""

import sys


def main() -> None:
    for token in sys.argv[1:]:
        print(token)
