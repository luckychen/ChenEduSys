"""Unit tests for audio service — codec, mixer, config."""

from __future__ import annotations

import struct

from chenedusys.services.audio import (
    AudioConfig,
    AudioMixer,
    AudioPlayback,
    AudioService,
    OpusCodec,
    _DEFAULT_CHANNELS,
    _DEFAULT_FRAME_MS,
    _DEFAULT_FRAME_SIZE,
    _DEFAULT_SAMPLE_RATE,
)


class TestAudioConfig:

    def test_defaults(self):
        cfg = AudioConfig()
        assert cfg.sample_rate == 48000
        assert cfg.channels == 1
        assert cfg.frame_ms == 20
        assert cfg.bitrate == 32000
        assert cfg.frame_size == 960  # 48000 * 20 / 1000

    def test_custom_values(self):
        cfg = AudioConfig(sample_rate=44100, channels=2, frame_ms=40, bitrate=64000)
        assert cfg.sample_rate == 44100
        assert cfg.channels == 2
        assert cfg.frame_ms == 40
        assert cfg.frame_size == 44100 * 40 // 1000

    def test_frame_size_calculation(self):
        cfg = AudioConfig(sample_rate=16000, frame_ms=60)
        assert cfg.frame_size == 960  # 16000 * 60 / 1000


class TestOpusCodec:

    def test_encode_decode_round_trip(self):
        codec = OpusCodec()
        codec.start()

        # Generate a sine wave as test PCM data (1 frame = 960 samples * 2 bytes)
        pcm = _generate_sine(freq=440, samples=_DEFAULT_FRAME_SIZE)
        encoded = codec.encode(pcm)
        assert isinstance(encoded, bytes)
        assert len(encoded) < len(pcm)  # Opus compresses

        decoded = codec.decode(encoded)
        assert isinstance(decoded, bytes)
        assert len(decoded) == len(pcm)

        codec.stop()

    def test_encode_silence(self):
        codec = OpusCodec()
        codec.start()

        silence = b"\x00" * (_DEFAULT_FRAME_SIZE * 2)
        encoded = codec.encode(silence)
        decoded = codec.decode(encoded)
        assert len(decoded) == len(silence)

        codec.stop()

    def test_encode_without_start_raises(self):
        import pytest
        codec = OpusCodec()
        with pytest.raises(RuntimeError, match="not started"):
            codec.encode(b"\x00" * 100)

    def test_decode_without_start_raises(self):
        import pytest
        codec = OpusCodec()
        with pytest.raises(RuntimeError, match="not started"):
            codec.decode(b"\x00" * 100)

    def test_multiple_frames(self):
        codec = OpusCodec()
        codec.start()

        for _ in range(10):
            pcm = _generate_sine(freq=880, samples=_DEFAULT_FRAME_SIZE)
            encoded = codec.encode(pcm)
            decoded = codec.decode(encoded)
            assert len(decoded) == len(pcm)

        codec.stop()

    def test_stop_clears_state(self):
        codec = OpusCodec()
        codec.start()
        codec.stop()
        import pytest
        with pytest.raises(RuntimeError):
            codec.encode(b"\x00" * 100)

    def test_custom_bitrate(self):
        cfg = AudioConfig(bitrate=64000)
        codec = OpusCodec(cfg)
        codec.start()

        pcm = _generate_sine(samples=cfg.frame_size)
        encoded = codec.encode(pcm)
        assert isinstance(encoded, bytes)

        codec.stop()


class TestAudioMixer:

    def test_single_stream_passthrough(self):
        data = _generate_sine(samples=960)
        result = AudioMixer.mix([data])
        assert result == data

    def test_two_streams(self):
        s1 = _generate_sine(freq=440, samples=960)
        s2 = _generate_sine(freq=880, samples=960)
        mixed = AudioMixer.mix([s1, s2])
        assert len(mixed) == len(s1)

    def test_empty_list(self):
        assert AudioMixer.mix([]) == b""

    def test_clipping(self):
        # Two max-amplitude signals should clip
        import array
        samples = array.array("h", [32767] * 100)
        data = samples.tobytes()
        mixed = AudioMixer.mix([data, data])
        result = array.array("h", mixed)
        for s in result:
            assert -32768 <= s <= 32767

    def test_mixed_length(self):
        s1 = _generate_sine(samples=960)
        s2 = _generate_sine(samples=960)
        mixed = AudioMixer.mix([s1, s2])
        assert len(mixed) == 960 * 2  # 960 samples * 2 bytes


class TestAudioPlayback:

    def test_volume_clamping(self):
        pb = AudioPlayback()
        pb.volume = 1.5
        assert pb.volume == 1.0
        pb.volume = -0.5
        assert pb.volume == 0.0
        pb.volume = 0.5
        assert pb.volume == 0.5

    def test_apply_volume(self):
        pb = AudioPlayback()
        pb.volume = 0.5
        import array
        pcm = array.array("h", [1000, -1000, 32767, -32768]).tobytes()
        result = pb._apply_volume(pcm)
        samples = array.array("h", result)
        assert samples[0] == 500
        assert samples[1] == -500


class TestAudioService:

    def test_initial_state(self):
        svc = AudioService()
        assert not svc.running
        assert not svc.muted
        assert svc.volume == 1.0

    def test_set_volume(self):
        svc = AudioService()
        svc.set_volume(0.7)
        assert svc.volume == 0.7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_sine(freq: int = 440, samples: int = _DEFAULT_FRAME_SIZE, amplitude: int = 16000) -> bytes:
    """Generate a sine wave as 16-bit PCM bytes."""
    import math
    data = []
    for i in range(samples):
        t = i / _DEFAULT_SAMPLE_RATE
        val = int(amplitude * math.sin(2 * math.pi * freq * t))
        data.append(struct.pack("<h", val))
    return b"".join(data)
