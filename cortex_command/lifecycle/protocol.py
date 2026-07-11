"""Protocol handshake constant for the served lifecycle loop.

The served next/advance loop is a **two-sided** system: a wheel (these Python
verbs, installed as a distribution) serves JSON payloads, and a prose loop (the
cortex-core plugin's skill markdown) consumes them. When the installed wheel and
the plugin prose drift out of sync — a *distribution-lag* phenomenon, since both
sides move together in this repo — the loop must be able to detect it.

The mechanism is a single additive ``protocol`` integer stamped into every verb
payload. The integer is declared **once per layer**:

- **This constant** (``PROTOCOL_VERSION``) states what the *wheel* serves.
- A **plugin-side expectation file**
  (``skills/lifecycle/references/protocol-expectation.txt``, mirrored into the
  cortex-core plugin tree beside the loop prose that reads it) states the compat
  *range* the *prose* expects, versioned in the same commit as the prose.

Compat is **always range-based, never exact-equality**: the plugin declares a
``[min, max]`` inclusive range and any served ``PROTOCOL_VERSION`` inside it is
compatible. Both sides advance together in-repo (a parity test asserts this
constant lies within the plugin file's range at HEAD); only distribution
introduces skew, which the per-verb payload check catches at the consumer.

``PROTOCOL_VERSION`` is **append-only**: bump it (never reuse or decrement) when
a payload change is not backward-compatible for the prose, and move the plugin
expectation range in the same commit. A bump that would strand out-of-repo
consumers is a *protocol-floor* decision made deliberately by the operator.
"""

from __future__ import annotations

# The protocol integer this wheel serves. Append-only; range-compared against the
# plugin-side expectation file — never exact-equality. See module docstring.
PROTOCOL_VERSION = 1
