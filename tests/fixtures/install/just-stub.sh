#!/bin/sh
# Trivial `just` stub — symlinked into per-test $tmpdir/bin when a test needs
# just to be on PATH (so the just-precondition check in install.sh passes).
# Tests for the just-absence path (R3) deliberately do NOT install this.
exit 0
