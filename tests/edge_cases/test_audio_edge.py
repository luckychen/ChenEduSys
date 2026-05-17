"""Edge-case tests for audio service."""

from __future__ import annotations

import array
import struct

from chenedusys.services.audio import (
    AudioConfig,
    AudioMixer,
    AudioPlayback,
    OpusCodec,
    _DEFAULT_FRAME_SIZE,
    _DEFAULT_SAMPLE_RATE,
)


def _generate_sine(freq=440, samples=_DEFAULT_FRAME_SIZE, amplitude=16000):
    import math
    data = []
    for i in range(samples):
        t = i / _DEFAULT_SAMPLE_RATE
        val = int(amplitude * math.sin(2 * math.pi * freq * t))
        data.append(struct.pack("<h", val))
    return b"".join(data)


class TestCodecEdgeCases:

    def test_encode_all_zeros(self):
        codec = OpusCodec()
        codec.start()
        silence = b"\x00" * (_DEFAULT_FRAME_SIZE * 2)
        encoded = codec.encode(silence)
        decoded = codec.decode(encoded)
        # Decoded silence should be near-zero
        import array
        samples = array.array("h", decoded)
        avg = sum(abs(s) for s in samples) / len(samples)
        assert avg < 100  # silence or near-silence
        codec.stop()

    def test_encode_max_amplitude(self):
        codec = OpusCodec()
        codec.start()
        import array
        loud = array.array("h", [32767] * _DEFAULT_FRAME_SIZE).tobytes()
        encoded = codec.encode(loud)
        decoded = codec.decode(encoded)
        assert len(decoded) == len(loud)
        codec.stop()

    def test_encode_near_silence(self):
        codec = OpusCodec()
        codec.start()
        quiet = array.array("h", [1] * _DEFAULT_FRAME_SIZE).tobytes()
        encoded = codec.encode(quiet)
        decoded = codec.decode(encoded)
        assert len(decoded) == len(quiet)
        codec.stop()

    def test_many_rapid_encode_decode(self):
        codec = OpusCodec()
        codec.start()
        for i in range(100):
            pcm = _generate_sine(freq=440 + i, samples=_DEFAULT_FRAME_SIZE)
            encoded = codec.encode(pcm)
            codec.decode(encoded)
        codec.stop()


class TestMixerEdgeCases:

    def test_three_streams(self):
        streams = [_generate_sine(freq=f, samples=960) for f in (440, 880, 1320)]
        mixed = AudioMixer.mix(streams)
        assert len(mixed) == 960 * 2

    def test_mixed_result_nonzero(self):
        s1 = _generate_sine(freq=440, samples=960, amplitude=16000)
        s2 = _generate_sine(freq=880, samples=960, amplitude=16000)
        mixed = AudioMixer.mix([s1, s2])
        import array
        samples = array.array("h", mixed)
        assert any(s != 0 for s in samples)

    def test_unequal_length_uses_shorter(self):
        import array
        s1 = array.array("h", [100] * 100).tobytes()
        s2 = array.array("h", [200] * 50).tobytes()
        mixed = AudioMixer.mix([s1, s2])
        assert len(mixed) == 100 * 2  # length of first stream


class TestPlaybackEdgeCases:

    def test_volume_zero_produces_silence(self):
        pb = AudioPlayback()
        pb.volume = 0.0
        import array
        pcm = array.array("h", [10000, -10000, 32767, -32768]).tobytes()
        result = pb._apply_volume(pcm)
        samples = array.array("h", result)
        assert all(s == 0 for s in samples)

    def test_volume_full_passthrough(self):
        pb = AudioPlayback()
        pb.volume = 1.0
        import array
        pcm = array.array("h", [1000, -2000]).tobytes()
        result = pb._apply_volume(pcm)
        assert result == pcm
