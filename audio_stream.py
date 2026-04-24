from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import numpy as np
import pyaudio


LOGGER = logging.getLogger(__name__)


def resample_pcm16(audio_bytes: bytes, src_rate: int, dst_rate: int) -> bytes:
    if not audio_bytes or src_rate == dst_rate:
        return audio_bytes

    samples = np.frombuffer(audio_bytes, dtype=np.int16)
    if samples.size == 0:
        return audio_bytes

    src_positions = np.arange(samples.size, dtype=np.float32)
    dst_size = max(1, int(samples.size * dst_rate / src_rate))
    dst_positions = np.arange(dst_size, dtype=np.float32) * (src_rate / dst_rate)
    dst_positions = np.minimum(dst_positions, samples.size - 1)
    resampled = np.interp(dst_positions, src_positions, samples).astype(np.int16)
    return resampled.tobytes()


class AudioStreamManager:
    def __init__(
        self,
        *,
        input_rate: int,
        output_rate: int,
        input_device_rate: int,
        output_device_rate: int,
        chunk_ms: int,
        input_device_index: int = -1,
        output_device_index: int = -1,
    ) -> None:
        self.input_rate = input_rate
        self.output_rate = output_rate
        self.input_device_rate = input_device_rate
        self.output_device_rate = output_device_rate
        self.chunk_ms = chunk_ms
        self.input_device_index = None if input_device_index < 0 else input_device_index
        self.output_device_index = None if output_device_index < 0 else output_device_index

        self.input_frames = max(160, int(self.input_device_rate * self.chunk_ms / 1000))
        self.output_frames = max(240, int(self.output_device_rate * self.chunk_ms / 1000))
        self.output_chunk_bytes = self.output_frames * 2

        self._audio = pyaudio.PyAudio()
        self._input_stream: pyaudio.Stream | None = None
        self._output_stream: pyaudio.Stream | None = None

        self._running = threading.Event()
        self._listeners: list[Callable[[bytes], None]] = []
        self._output_idle_callback: Callable[[], None] | None = None

        self._input_thread: threading.Thread | None = None
        self._output_buffer = bytearray()
        self._output_prebuffer_bytes = self.output_chunk_bytes * 2
        self._output_max_bytes = self.output_chunk_bytes * 2000  # ~60s at 24kHz
        self._output_buffer_lock = threading.Lock()
        self._output_primed = False
        self._last_output_data_time = 0.0
        self._playback_generation = 0
        self._playback_lock = threading.Lock()
        self._output_active = False

    def add_input_listener(self, callback: Callable[[bytes], None]) -> None:
        self._listeners.append(callback)

    def set_output_idle_callback(self, callback: Callable[[], None]) -> None:
        self._output_idle_callback = callback

    def start(self) -> None:
        if self._running.is_set():
            return

        self._running.set()
        try:
            self._input_stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.input_device_rate,
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=self.input_frames,
            )
        except Exception:
            LOGGER.exception("初始化输入音频流失败")
            self._running.clear()
            raise
        try:
            self._output_stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.output_device_rate,
                output=True,
                output_device_index=self.output_device_index,
                frames_per_buffer=self.output_frames,
                stream_callback=self._output_callback,
            )
        except Exception:
            LOGGER.exception("初始化输出音频流失败")
            if self._input_stream is not None:
                self._input_stream.stop_stream()
                self._input_stream.close()
                self._input_stream = None
            self._audio.terminate()
            self._running.clear()
            raise

        self._input_thread = threading.Thread(target=self._input_loop, daemon=True)
        self._input_thread.start()

    def stop(self) -> None:
        if not self._running.is_set():
            return

        self._running.clear()
        self.clear_output()

        if self._input_thread and self._input_thread.is_alive():
            self._input_thread.join(timeout=2)

        if self._input_stream is not None:
            self._input_stream.stop_stream()
            self._input_stream.close()
            self._input_stream = None

        if self._output_stream is not None:
            self._output_stream.stop_stream()
            self._output_stream.close()
            self._output_stream = None

        self._audio.terminate()

    def play_output(self, audio_bytes: bytes, sample_rate: int = 24000) -> None:
        if not audio_bytes:
            return
        with self._playback_lock:
            generation = self._playback_generation

        if sample_rate != self.output_device_rate:
            audio_bytes = resample_pcm16(audio_bytes, sample_rate, self.output_device_rate)

        with self._output_buffer_lock:
            with self._playback_lock:
                if generation != self._playback_generation:
                    return
            # Drop incoming data if buffer is full to prevent unbounded growth
            if len(self._output_buffer) < self._output_max_bytes:
                self._output_buffer.extend(audio_bytes)
                self._last_output_data_time = time.monotonic()
                self._output_active = True

    def clear_output(self) -> None:
        with self._playback_lock:
            self._playback_generation += 1

        with self._output_buffer_lock:
            self._output_buffer.clear()
            self._output_primed = False
            was_active = self._output_active
            self._output_active = False

        if was_active:
            self._notify_output_idle()

    def is_output_active(self) -> bool:
        with self._output_buffer_lock:
            return self._output_active

    def _input_loop(self) -> None:
        consecutive_errors = 0
        while self._running.is_set():
            try:
                if self._input_stream is None:
                    break
                data = self._input_stream.read(self.input_frames, exception_on_overflow=False)
                consecutive_errors = 0
                if self.input_device_rate != self.input_rate:
                    data = resample_pcm16(data, self.input_device_rate, self.input_rate)

                for callback in list(self._listeners):
                    try:
                        callback(data)
                    except Exception:
                        LOGGER.exception("处理麦克风音频时发生异常")
            except OSError:
                consecutive_errors += 1
                LOGGER.exception("读取麦克风失败 (连续 %d 次)", consecutive_errors)
                if consecutive_errors >= 5:
                    LOGGER.error("麦克风连续失败 %d 次，停止输入循环", consecutive_errors)
                    break
                time.sleep(min(0.1 * consecutive_errors, 1.0))

    def _output_callback(
        self,
        in_data: bytes | None,
        frame_count: int,
        time_info: dict,
        status_flags: int,
    ) -> tuple[bytes, int]:
        requested_bytes = frame_count * 2
        silence = b"\x00" * requested_bytes

        if not self._running.is_set():
            return silence, pyaudio.paComplete

        notify_idle = False
        with self._output_buffer_lock:
            buffered = len(self._output_buffer)
            if not self._output_primed:
                if buffered < self._output_prebuffer_bytes:
                    return silence, pyaudio.paContinue
                self._output_primed = True

            if buffered >= requested_bytes:
                data = bytes(self._output_buffer[:requested_bytes])
                del self._output_buffer[:requested_bytes]
                return data, pyaudio.paContinue

            if buffered:
                data = bytes(self._output_buffer) + (b"\x00" * (requested_bytes - buffered))
                self._output_buffer.clear()
                # Don't reset _output_primed here - we're still playing
            else:
                data = silence

            if time.monotonic() - self._last_output_data_time > 0.2:
                self._output_primed = False
                if self._output_active:
                    self._output_active = False
                    notify_idle = True

        if notify_idle:
            self._notify_output_idle()
        return data, pyaudio.paContinue

    def _notify_output_idle(self) -> None:
        if self._output_idle_callback is None:
            return
        try:
            self._output_idle_callback()
        except Exception:
            LOGGER.exception("执行播放完成回调失败")

