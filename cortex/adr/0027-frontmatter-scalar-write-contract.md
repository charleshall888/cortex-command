---
status: proposed
---

# Frontmatter scalar write contract

## Context

Tool-managed backlog/lifecycle frontmatter is emitted by hand-rolled, per-key line editors — deliberately, to preserve the ordered-block + inline-array + bare-`null` shape that PyYAML's block dumper cannot reproduce (see the `_yaml_safe_title_value` precedent in `create_item.py` and the `update_item.py` per-key `_set_frontmatter_value` editor). That writer boundary erases Python type: every value reaches the editor as `str`, and the `None` path arrives as the literal string `"null"`.

Readers, however, split into two populations: string-only custom parsers, and `yaml.safe_load`. A bare-numeric string scalar therefore type-leaks. `lifecycle_slug: 378` is written as the string `"378"` but read back by `yaml.safe_load` as the `int` `378`, which crashes the served resolve path (`lifecycle/resolve.py`, `Path / int` → `TypeError`) and reddens `tests/test_lifecycle_references_resolve.py`. This is the #374-residue defect that #378 fixed.

The naive fix — a `safe_dump`-style "quote anything that would mis-resolve under YAML 1.1" rule — is wrong here: dates (`updated`/`created`) and the `null` sentinel *also* mis-resolve under YAML 1.1, yet they MUST stay bare (the resolver relies on the bare `null` fallback, and churn-quoting every date is noise). Because the writer boundary has erased Python type, write-time intent can no longer be inferred from the value form; it must be carried by the **key**.

## Decision

Establish a single **key-scoped** YAML-safe scalar-quoting helper as the mandated write path for frontmatter scalar emission: `cortex_command/backlog/frontmatter_quote.py` (`quote_scalar`, gated by the `STRING_INTENDED_KEYS` allowlist). All hand-rolled frontmatter scalar writers route through it — currently `update_item.py::_set_frontmatter_value`, `lifecycle/create_index.py::_render`'s `feature:` emission, and `overnight/report.py`'s `lifecycle_slug:` emission.

The rule is deliberately **not** "quote anything that mis-resolves under YAML 1.1." It is:

- For a key on the **string-intended allowlist** (`lifecycle_slug`, `feature`, `parent`, `spec`, plus any scalar whose value is a bare slug/path/id-string), quote the value **when** its string form would otherwise mis-resolve under YAML 1.1 (bare int/float, the `true/false/yes/no/on/off` family and their case/short variants, sexagesimal `12:34`, `.inf`/`.nan`, hex/octal prefixes, empty string, or a leading YAML indicator / inline `#`) — **except the `None` sentinel**, the literal `null`/`~` that stays bare even on an allowlisted key so the resolver's null-fallback is preserved. Embedded `"`, `\`, newlines, and control chars are escaped as a single-scalar YAML double-quoted line edit, never a `safe_dump` block round-trip.
- Every other key (dates, `blocked-by`/`parent_backlog_id` ints, the `null` sentinel) is emitted **bare**, unchanged.

Ambiguity detection delegates to the actual reader (`yaml.safe_load`) rather than a hand-rolled YAML-1.1 regex, so the writer and reader agree by construction. Defensive reader-side coercion of a read `lifecycle_slug` to `str` (`resolve_item.py`, `lifecycle/resolve.py`) is retained as defense-in-depth for on-disk files that predate the writer fix — it is what keeps numeric backlog IDs a first-class input form (a numeric `lifecycle_slug` resolves correctly as the string `"378"` against dir `378`) rather than a value to reject.

## Trade-off / rejected alternatives

- **Blanket "quote anything ambiguous" (rejected).** A `safe_dump`-style rule quotes dates and the `null` sentinel, breaking the resolver's null-fallback and churn-quoting every `updated` write. The key allowlist is the only rule that reconciles "quote ambiguous slugs" with "leave dates/null/ints bare."
- **Reader-only coercion at every `yaml.safe_load` site (rejected as the primary fix).** Scattering defensive coercion across every reader is the "validate everywhere" anti-pattern; fixing the class at the single producer boundary ("parse, don't validate") is the durable form. Reader coercion is kept only as defense-in-depth for legacy on-disk files, not as the contract.
- **Migrate writers to `ruamel`/full YAML round-trip (rejected).** The per-key line editor is deliberate (it preserves shape PyYAML cannot); only scoped quoting is added.

## Consequences

- **Standing maintenance obligation.** The `STRING_INTENDED_KEYS` allowlist must be extended as new string-intended, numeric-looking fields are added; a field left off the list re-exposes the type-leak, and widening the set to "all keys" would quote the dates and `null` sentinel this contract exists to leave bare. The backstop is `tests/test_lifecycle_references_resolve.py`, now wired into the blocking CI path (`.github/workflows/validate.yml`) so a re-introduced malformed slug fails the critical path rather than regressing silently.
- **Generalizes an existing precedent.** This lifts the ad-hoc, title-only `_yaml_safe_title_value` into a reusable key-scoped form, replacing a one-off with a mandated write path.
