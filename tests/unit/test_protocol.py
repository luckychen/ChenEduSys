"""Unit tests for P2P binary protocol."""

from __future__ import annotations

import pytest

from chenedusys.transport.protocol import (
    CONTROL,
    AUDIO,
    CONTENT,
    PAINT,
    HEADER_SIZE,
    MAX_PAYLOAD_SIZE,
    ProtocolError,
    FrameReader,
    decode,
    encode,
    frame_size,
)


class TestEncode:

    def test_encode_dict_payload(self):
        payload = {"type": "hello", "peer_id": "abc123"}
        frame = encode(CONTROL, payload)
        assert isinstance(frame, bytes)
        assert len(frame) > HEADER_SIZE

    def test_encode_bytes_payload(self):
        payload = b"\x00\x01\x02\x03"
        frame = encode(AUDIO, payload)
        assert isinstance(frame, bytes)

    def test_encode_header_format(self):
        payload = {"test": True}
        frame = encode(CONTROL, payload)
        import struct
        length, channel = struct.unpack("!IB", frame[:HEADER_SIZE])
        assert channel == CONTROL
        assert length == len(frame) - HEADER_SIZE

    def test_encode_invalid_channel(self):
        import pytest
        with pytest.raises(ProtocolError, match="Invalid channel"):
            encode(0xFF, {"test": True})

    def test_encode_invalid_payload_type(self):
        import pytest
        with pytest.raises(ProtocolError, match="Payload must be dict or bytes"):
            encode(CONTROL, "not_valid")

    def test_encode_zero_length_payload(self):
        frame = encode(CONTROL, b"")
        assert len(frame) == HEADER_SIZE


class TestDecode:

    def test_round_trip_dict(self):
        original = {"type": "stroke", "points": [{"x": 1.0, "y": 2.0}]}
        frame = encode(PAINT, original)
        channel, payload = decode(frame)
        assert channel == PAINT
        assert payload == original

    def test_round_trip_bytes(self):
        original = b"\xde\xad\xbe\xef" * 100
        frame = encode(AUDIO, original)
        channel, payload = decode(frame)
        assert channel == AUDIO
        assert payload == original

    def test_decode_incomplete_header(self):
        import pytest
        with pytest.raises(ProtocolError, match="Incomplete header"):
            decode(b"\x00\x01\x02")

    def test_decode_incomplete_payload(self):
        import pytest
        frame = encode(CONTROL, {"test": True})
        with pytest.raises(ProtocolError, match="Incomplete payload"):
            decode(frame[:HEADER_SIZE + 2])

    def test_decode_invalid_channel_in_frame(self):
        import struct
        import msgpack
        body = msgpack.packb({"test": True}, use_bin_type=True)
        header = struct.pack("!IB", len(body), 0xFF)
        with pytest.raises(ProtocolError, match="Invalid channel"):
            decode(header + body)


class TestFrameSize:

    def test_complete_frame(self):
        frame = encode(CONTROL, {"a": 1})
        assert frame_size(frame) == len(frame)

    def test_incomplete_header(self):
        assert frame_size(b"\x00\x01") is None

    def test_incomplete_payload(self):
        frame = encode(CONTROL, {"a": 1})
        assert frame_size(frame[:HEADER_SIZE + 1]) == len(frame)


class TestFrameReader:

    def test_single_frame(self):
        reader = FrameReader()
        frame = encode(CONTROL, {"type": "hello"})
        reader.feed(frame)
        results = list(reader)
        assert len(results) == 1
        ch, payload = results[0]
        assert ch == CONTROL
        assert payload["type"] == "hello"

    def test_multiple_frames(self):
        reader = FrameReader()
        f1 = encode(CONTROL, {"msg": 1})
        f2 = encode(PAINT, {"msg": 2})
        f3 = encode(AUDIO, b"\x00\x01\x02")
        reader.feed(f1 + f2 + f3)
        results = list(reader)
        assert len(results) == 3
        assert results[0][1]["msg"] == 1
        assert results[1][1]["msg"] == 2
        assert results[2][1] == b"\x00\x01\x02"

    def test_partial_then_rest(self):
        reader = FrameReader()
        frame = encode(CONTROL, {"type": "hello"})
        mid = len(frame) // 2
        reader.feed(frame[:mid])
        # Partial frame — iterator yields nothing
        results = []
        for item in reader:
            results.append(item)
        assert results == []
        reader.feed(frame[mid:])
        results = list(reader)
        assert len(results) == 1

    def test_buffered_property(self):
        reader = FrameReader()
        reader.feed(b"\x00\x01\x02")
        assert reader.buffered == 3

    def test_empty_feed(self):
        reader = FrameReader()
        reader.feed(b"")
        assert list(reader) == []

    def test_incremental_feed(self):
        reader = FrameReader()
        frame = encode(CONTROL, {"big": "data" * 100})
        for i in range(0, len(frame), 7):
            reader.feed(frame[i:i+7])
        results = list(reader)
        assert len(results) == 1
        assert results[0][1]["big"] == "data" * 100


class TestAllChannels:

    def test_control_channel(self):
        frame = encode(CONTROL, {"type": "ping"})
        ch, payload = decode(frame)
        assert ch == CONTROL
        assert payload["type"] == "ping"

    def test_audio_channel(self):
        frame = encode(AUDIO, b"\x00" * 960)
        ch, _ = decode(frame)
        assert ch == AUDIO

    def test_content_channel(self):
        frame = encode(CONTENT, {"page": 1})
        ch, payload = decode(frame)
        assert ch == CONTENT
        assert payload["page"] == 1

    def test_paint_channel(self):
        frame = encode(PAINT, {"stroke_id": "abc"})
        ch, payload = decode(frame)
        assert ch == PAINT
        assert payload["stroke_id"] == "abc"
