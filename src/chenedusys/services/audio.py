"""Audio service — capture, encode, stream, decode, and playback."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable

import opuslib

logger = logging.getLogger(__name__)

_DEFAULT_SAMPLE_RATE = 48000
_DEFAULT_CHANNELS = 1
_DEFAULT_FRAME_MS = 20
_DEFAULT_BITRATE = 32000
_DEFAULT_FRAME_SIZE = _DEFAULT_SAMPLE_RATE * _DEFAULT_FRAME_MS // 1000  # 960 samples


class AudioConfig:
    __slots__ = ("sample_rate", "channels", "frame_ms", "bitrate", "frame_size")

    def __init__(
        self,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        channels: int = _DEFAULT_CHANNELS,
        frame_ms: int = _DEFAULT_FRAME_MS,
        bitrate: int = _DEFAULT_BITRATE,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_ms = frame_ms
        self.bitrate = bitrate
        self.frame_size = sample_rate * frame_ms // 1000


class OpusCodec:
    """Encode and decode audio frames using Opus."""

    def __init__(self, config: AudioConfig | None = None) -> None:
        self._config = config or AudioConfig()
        self._encoder: opuslib.Encoder | None = None
        self._decoder: opuslib.Decoder | None = None

    def start(self) -> None:
        self._encoder = opuslib.Encoder(
            self._config.sample_rate,
            self._config.channels,
            "voip",
        )
        self._encoder.bitrate = self._config.bitrate
        self._decoder = opuslib.Decoder(
            self._config.sample_rate,
            self._config.channels,
        )

    def stop(self) -> None:
        self._encoder = None
        self._decoder = None

    def encode(self, pcm_data: bytes) -> bytes:
        if self._encoder is None:
            raise RuntimeError("Codec not started")
        return self._encoder.encode(pcm_data, self._config.frame_size)

    def decode(self, opus_data: bytes) -> bytes:
        if self._decoder is None:
            raise RuntimeError("Codec not started")
        return self._decoder.decode(opus_data, self._config.frame_size)


class AudioCapture:
    """Captures audio from the microphone in a background thread."""

    def __init__(
        self,
        config: AudioConfig | None = None,
        on_frame: Callable[[bytes], None] | None = None,
    ) -> None:
        self._config = config or AudioConfig()
        self._on_frame = on_frame
        self._running = False
        self._muted = False
        self._thread: threading.Thread | None = None
        self._pa = None
        self._stream = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool) -> None:
        self._muted = value

    def start(self) -> None:
        import pyaudio

        self._pa = pyaudio.PyAudio()
        self._running = True
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._config.channels,
            rate=self._config.sample_rate,
            input=True,
            frames_per_buffer=self._config.frame_size,
        )
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("Audio capture started (%dHz, %dms frames)", self._config.sample_rate, self._config.frame_ms)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._pa:
            self._pa.terminate()
        self._pa = None
        self._stream = None
        logger.info("Audio capture stopped")

    def _capture_loop(self) -> None:
        while self._running:
            try:
                pcm = self._stream.read(self._config.frame_size, exception_on_overflow=False)
                if self._on_frame and not self._muted:
                    self._on_frame(pcm)
            except OSError as exc:
                if self._running:
                    logger.warning("Audio capture error: %s", exc)
                break


class AudioPlayback:
    """Plays decoded PCM audio to speakers."""

    def __init__(self, config: AudioConfig | None = None) -> None:
        self._config = config or AudioConfig()
        self._pa = None
        self._stream = None
        self._volume = 1.0

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, value))

    def start(self) -> None:
        import pyaudio

        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._config.channels,
            rate=self._config.sample_rate,
            output=True,
            frames_per_buffer=self._config.frame_size,
        )
        logger.info("Audio playback started")

    def stop(self) -> None:
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._pa:
            self._pa.terminate()
        self._pa = None
        self._stream = None
        logger.info("Audio playback stopped")

    def play(self, pcm_data: bytes) -> None:
        if self._stream is None:
            return
        if self._volume < 1.0:
            pcm_data = self._apply_volume(pcm_data)
        try:
            self._stream.write(pcm_data)
        except OSError:
            pass

    def _apply_volume(self, pcm_data: bytes) -> bytes:
        import array
        samples = array.array("h", pcm_data)
        for i in range(len(samples)):
            samples[i] = int(samples[i] * self._volume)
        return samples.tobytes()


class AudioMixer:
    """Mixes multiple PCM audio streams (for teacher receiving from multiple students)."""

    @staticmethod
    def mix(pcm_streams: list[bytes], frame_size: int = _DEFAULT_FRAME_SIZE) -> bytes:
        """Mix multiple PCM frames into one by summing and clipping."""
        import array

        if not pcm_streams:
            return b""
        if len(pcm_streams) == 1:
            return pcm_streams[0]

        mixed = array.array("h", pcm_streams[0])
        for stream in pcm_streams[1:]:
            samples = array.array("h", stream)
            for i in range(min(len(mixed), len(samples))):
                val = mixed[i] + samples[i]
                mixed[i] = max(-32768, min(32767, val))
        return mixed.tobytes()


class AudioService:
    """High-level audio service that ties capture, codec, and playback together.

    Integration point: connect to P2P transport to send/receive AUDIO channel frames.
    """

    def __init__(self, config: AudioConfig | None = None) -> None:
        self._config = config or AudioConfig()
        self._codec = OpusCodec(self._config)
        self._capture: AudioCapture | None = None
        self._playback = AudioPlayback(self._config)
        self._mixer = AudioMixer()
        self._on_encoded_frame: Callable[[bytes], None] | None = None
        self._incoming_buffers: dict[str, list[bytes]] = {}
        self._running = False

    @property
    def muted(self) -> bool:
        return self._capture.muted if self._capture else False

    @property
    def volume(self) -> float:
        return self._playback.volume

    @property
    def running(self) -> bool:
        return self._running

    def on_encoded_frame(self, handler: Callable[[bytes], None]) -> None:
        """Set the callback for encoded frames ready to send over the network."""
        self._on_encoded_frame = handler

    def start(self) -> None:
        """Start audio capture and playback."""
        self._codec.start()
        self._capture = AudioCapture(
            config=self._config,
            on_frame=self._handle_captured_frame,
        )
        self._capture.start()
        self._playback.start()
        self._running = True
        logger.info("Audio service started")

    def stop(self) -> None:
        """Stop audio capture and playback."""
        self._running = False
        if self._capture:
            self._capture.stop()
        self._playback.stop()
        self._codec.stop()
        self._incoming_buffers.clear()
        logger.info("Audio service stopped")

    def set_mute(self, muted: bool) -> None:
        if self._capture:
            self._capture.muted = muted

    def set_volume(self, volume: float) -> None:
        self._playback.volume = volume

    def handle_incoming_frame(self, peer_id: str, opus_data: bytes) -> None:
        """Called when an encoded audio frame arrives from a peer."""
        try:
            pcm = self._codec.decode(opus_data)
            self._playback.play(pcm)
        except Exception as exc:
            logger.warning("Decode/playback error: %s", exc)

    def _handle_captured_frame(self, pcm_data: bytes) -> None:
        """Encode captured PCM and forward to network callback."""
        try:
            encoded = self._codec.encode(pcm_data)
            if self._on_encoded_frame:
                self._on_encoded_frame(encoded)
        except Exception as exc:
            logger.warning("Encode error: %s", exc)
