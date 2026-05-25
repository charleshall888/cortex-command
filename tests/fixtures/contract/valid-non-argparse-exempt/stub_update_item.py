"""Stub module that does NOT use argparse.

Demonstrates the non-argparse-module exemption category. The AST extractor
should classify this module as extraction_status="not_argparse" and any
invocation against it must be suppressed via the bin/.contract-lint-exceptions.md
ledger entry.
"""

import sys


def main() -> None:
    args = sys.argv[1:]
    for token in args:
        if "=" not in token:
            print(f"error: expected key=value, got {token!r}", file=sys.stderr)
            sys.exit(1)
