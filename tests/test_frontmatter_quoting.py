"""Tests for the key-scoped YAML-safe frontmatter scalar quoter (378 req-1).

Covers the ``cortex_command.backlog.frontmatter_quote.quote_scalar`` contract
and its routing through the three hand-rolled frontmatter writers:

  - ``update_item._set_frontmatter_value`` (all scalars)
  - ``lifecycle.create_index._render`` (``feature:`` emission)
  - ``overnight.report.create_followup_backlog_items`` (``lifecycle_slug:``)

Acceptance (spec req-1):
  (a) allowlisted keys with numeric-looking / YAML-ambiguous values are quoted,
      while ``updated`` (a date), a numeric ``blocked-by``, and a ``null``/None
      field stay bare;
  (b) the writers stay per-key line editors — no ``safe_dump`` (asserted by the
      spec's grep, not here);
  (c) a value carrying ``"``/``\\``/``:`` round-trips through ``yaml.safe_load``
      to the exact original string.
"""

from __future__ import annotations

import yaml

from cortex_command.backlog.frontmatter_quote import (
    STRING_INTENDED_KEYS,
    quote_scalar,
)


# ---------------------------------------------------------------------------
# (a) Allowlisted keys: quote YAML-ambiguous values
# ---------------------------------------------------------------------------


class TestAllowlistedKeysQuoted:
    def test_lifecycle_slug_numeric_is_quoted(self):
        assert quote_scalar("lifecycle_slug", "378") == '"378"'

    def test_feature_bool_word_is_quoted(self):
        assert quote_scalar("feature", "yes") == '"yes"'

    def test_parent_sexagesimal_is_quoted(self):
        assert quote_scalar("parent", "12:34") == '"12:34"'

    def test_spec_empty_string_is_quoted(self):
        # Empty string mis-resolves to null under YAML — must be quoted, and is
        # distinct from the None sentinel (which stays bare).
        assert quote_scalar("spec", "") == '""'

    def test_short_bool_variants_are_quoted(self):
        # PyYAML reads bare ``y``/``n`` as strings, but the spec still requires
        # the short YAML 1.1 bool variants quoted on allowlisted keys.
        assert quote_scalar("feature", "y") == '"y"'
        assert quote_scalar("feature", "n") == '"n"'
        assert quote_scalar("feature", "ON") == '"ON"'

    def test_all_quoted_values_round_trip_to_string(self):
        for value in ("378", "yes", "12:34", "", "y", ".inf", "0x1F"):
            rendered = quote_scalar("lifecycle_slug", value)
            loaded = yaml.safe_load(f"lifecycle_slug: {rendered}\n")["lifecycle_slug"]
            assert loaded == value, (value, rendered, loaded)


# ---------------------------------------------------------------------------
# (a) Allowlisted keys: leave already-safe values bare (no churn)
# ---------------------------------------------------------------------------


class TestAllowlistedKeysBareWhenSafe:
    def test_normal_kebab_slug_is_bare(self):
        assert quote_scalar("feature", "critical-review-gate") == "critical-review-gate"

    def test_path_value_is_bare(self):
        assert (
            quote_scalar("spec", "cortex/lifecycle/378/spec.md")
            == "cortex/lifecycle/378/spec.md"
        )

    def test_none_sentinel_stays_bare_on_allowlisted_key(self):
        # The literal ``null``/``~`` that update_item emits for a None field must
        # stay bare even on an allowlisted key (preserves the null-fallback).
        assert quote_scalar("lifecycle_slug", "null") == "null"
        assert quote_scalar("parent", "~") == "~"


# ---------------------------------------------------------------------------
# (a) Non-allowlisted keys: always bare, even when they would mis-resolve
# ---------------------------------------------------------------------------


class TestNonAllowlistedKeysBare:
    def test_updated_date_is_bare(self):
        # A date mis-resolves to datetime.date under yaml.safe_load, but
        # ``updated`` is not string-intended, so it must NOT be churn-quoted.
        assert quote_scalar("updated", "2026-07-13") == "2026-07-13"

    def test_created_date_is_bare(self):
        assert quote_scalar("created", "2026-07-13") == "2026-07-13"

    def test_numeric_blocked_by_is_bare(self):
        assert quote_scalar("blocked-by", "374") == "374"

    def test_parent_backlog_id_int_is_bare(self):
        assert quote_scalar("parent_backlog_id", "374") == "374"

    def test_none_on_non_allowlisted_key_is_bare(self):
        assert quote_scalar("updated", "null") == "null"


# ---------------------------------------------------------------------------
# (c) Metacharacter round-trip through yaml.safe_load
# ---------------------------------------------------------------------------


class TestMetacharRoundTrip:
    def test_quote_backslash_colon_round_trips(self):
        original = 'a"b\\c: d#e'  # contains " \ : (with space) and #
        rendered = quote_scalar("spec", original)
        assert rendered.startswith('"') and rendered.endswith('"')
        loaded = yaml.safe_load(f"spec: {rendered}\n")["spec"]
        assert loaded == original

    def test_control_chars_round_trip(self):
        original = "tab\tnewline\nnull\x00end"
        rendered = quote_scalar("parent", original)
        loaded = yaml.safe_load(f"parent: {rendered}\n")["parent"]
        assert loaded == original


# ---------------------------------------------------------------------------
# Routing: the three writers go through the helper
# ---------------------------------------------------------------------------


class TestWriterRouting:
    def test_allowlist_contains_the_four_spec_keys(self):
        assert {"lifecycle_slug", "feature", "parent", "spec"} <= STRING_INTENDED_KEYS

    def test_set_frontmatter_value_quotes_slug_and_leaves_date_bare(self):
        from cortex_command.backlog.update_item import _set_frontmatter_value

        text = "---\nlifecycle_slug: old\nupdated: 2026-01-01\n---\nbody\n"
        out = _set_frontmatter_value(text, "lifecycle_slug", "378")
        out = _set_frontmatter_value(out, "updated", "2026-07-13")
        assert 'lifecycle_slug: "378"\n' in out
        assert "updated: 2026-07-13\n" in out
        # The written slug reads back as the string "378", not int.
        fm = yaml.safe_load(out.split("---\n")[1])
        assert fm["lifecycle_slug"] == "378"
        assert isinstance(fm["lifecycle_slug"], str)

    def test_set_frontmatter_value_none_sentinel_bare(self):
        from cortex_command.backlog.update_item import _set_frontmatter_value

        text = "---\nlifecycle_slug: old\n---\n"
        out = _set_frontmatter_value(text, "lifecycle_slug", "null")
        assert "lifecycle_slug: null\n" in out

    def test_create_index_render_quotes_numeric_feature(self):
        from cortex_command.lifecycle.create_index import _render

        out = _render(
            feature="378",
            uuid=None,
            backlog_id=374,
            tags=[],
            created="2026-07-13",
            updated="2026-07-13",
            stem=None,
            title=None,
            shape_a=False,
        )
        assert 'feature: "378"\n' in out
        # parent_backlog_id is an intended int and stays bare.
        assert "parent_backlog_id: 374\n" in out
        fm = yaml.safe_load(out.split("---\n")[1])
        assert fm["feature"] == "378"
        assert isinstance(fm["feature"], str)
