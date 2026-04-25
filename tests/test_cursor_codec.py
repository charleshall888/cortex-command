"""Roundtrip + invariant tests for the opaque cursor codec (R10).

The codec backs the MCP ``overnight_logs`` tool's pagination contract. Per
spec acceptance criterion R10, ``decode(encode(o, s)) == {"offset": o,
"file_size_at_emit": s}`` for a representative set of values. We also
exercise the malformed-cursor rejection path so the MCP layer can rely on
``ValueError("invalid cursor")`` as the single failure mode.
"""

from __future__ import annotations

import base64
import json

import pytest

from cortex_command.overnight import cursor as cursor_codec


@pytest.mark.parametrize(
    "offset,file_size_at_emit",
    [
        (0, 0),
        (0, 1),
        (1, 1),
        (42, 100),
        (1024, 4096),
        # Realistic mid-day overnight file sizes.
        (1_048_576, 16_777_216),
        # 1 GiB-ish — still well within int64 range.
        (1_073_741_824, 2_147_483_648),
        # Boundary: large but under the 256 MiB MCP cap (cap lives in tools.py).
        (256 * 1024 * 1024 - 1, 256 * 1024 * 1024),
    ],
)
def test_encode_decode_roundtrip(offset: int, file_size_at_emit: int) -> None:
    """Roundtrip preserves both fields exactly across a representative range."""
    token = cursor_codec.encode(offset, file_size_at_emit)
    assert isinstance(token, str)
    decoded = cursor_codec.decode(token)
    assert decoded == {"offset": offset, "file_size_at_emit": file_size_at_emit}


def test_encoded_token_is_url_safe_base64() -> None:
    """The encoded token is URL-safe base64 of a JSON payload (server-internal,
    not part of the client contract per R23 — verified here so the codec
    invariant doesn't drift silently)."""
    token = cursor_codec.encode(123, 456)
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    payload = json.loads(raw)
    assert payload == {"offset": 123, "file_size_at_emit": 456}


def test_encoded_token_contains_no_path_separator() -> None:
    """URL-safe base64 must not produce '/' or '+', so cursors are safe to
    embed in URLs / shell args without escaping."""
    token = cursor_codec.encode(2**40, 2**40 + 1)
    assert "/" not in token
    assert "+" not in token


def test_decode_rejects_garbage_string() -> None:
    """Random non-base64 garbage raises ValueError('invalid cursor')."""
    with pytest.raises(ValueError, match="invalid cursor"):
        cursor_codec.decode("!!!not-base64!!!")


def test_decode_rejects_non_json_payload() -> None:
    """Valid base64 wrapping non-JSON bytes raises."""
    bogus = base64.urlsafe_b64encode(b"not-json").decode("ascii")
    with pytest.raises(ValueError, match="invalid cursor"):
        cursor_codec.decode(bogus)


def test_decode_rejects_missing_keys() -> None:
    """Valid JSON missing one of the required keys raises."""
    bogus = base64.urlsafe_b64encode(json.dumps({"offset": 1}).encode()).decode(
        "ascii"
    )
    with pytest.raises(ValueError, match="invalid cursor"):
        cursor_codec.decode(bogus)


def test_decode_rejects_non_integer_values() -> None:
    """Non-integer offset / file_size_at_emit raises."""
    bogus = base64.urlsafe_b64encode(
        json.dumps({"offset": "abc", "file_size_at_emit": 0}).encode()
    ).decode("ascii")
    with pytest.raises(ValueError, match="invalid cursor"):
        cursor_codec.decode(bogus)


def test_decode_rejects_negative_values() -> None:
    """Negative offsets / sizes are nonsensical and rejected."""
    bogus = base64.urlsafe_b64encode(
        json.dumps({"offset": -1, "file_size_at_emit": 0}).encode()
    ).decode("ascii")
    with pytest.raises(ValueError, match="invalid cursor"):
        cursor_codec.decode(bogus)


def test_decode_rejects_non_object_payload() -> None:
    """A JSON list (not object) at the top level is rejected."""
    bogus = base64.urlsafe_b64encode(json.dumps([1, 2]).encode()).decode("ascii")
    with pytest.raises(ValueError, match="invalid cursor"):
        cursor_codec.decode(bogus)
