from __future__ import annotations

import logging
import queue
import threading
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
    dst_positions = np.linspace(0, samples.size - 1, dst_size, dtype=np.float32)
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
        self._output_thread: threading.Thread | None = None
        self._output_queue: queue.Queue[tuple[int, bytes, int]] = queue.Queue()
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
        self._input_stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.input_device_rate,
            input=True,
            input_device_index=self.input_device_index,
            frames_per_buffer=self.input_frames,
        )
        self._output_stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.output_device_rate,
            output=True,
            output_device_index=self.output_device_index,
            frames_per_buffer=self.output_frames,
        )

        self._input_thread = threading.Thread(target=self._input_loop, daemon=True)
        self._output_thread = threading.Thread(target=self._output_loop, daemon=True)
        self._input_thread.start()
        self._output_thread.start()

    def stop(self) -> None:
        if not self._running.is_set():
            return

        self._running.clear()
        self.clear_output()

        if self._input_thread and self._input_thread.is_alive():
            self._input_thread.join(timeout=2)
        if self._output_thread and self._output_thread.is_alive():
            self._output_thread.join(timeout=2)

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
        self._output_queue.put((generation, audio_bytes, sample_rate))

    def clear_output(self) -> None:
        with self._playback_lock:
            self._playback_generation += 1

        try:
            while True:
                self._output_queue.get_nowait()
        except queue.Empty:
            pass

        if self._output_active:
            self._output_active = False
            self._notify_output_idle()

    def is_output_active(self) -> bool:
        return self._output_active

    def _input_loop(self) -> None:
        while self._running.is_set():
            try:
                assert self._input_stream is not None
                data = self._input_stream.read(self.input_frames, exception_on_overflow=False)
                if self.input_device_rate != self.input_rate:
                    data = resample_pcm16(data, self.input_device_rate, self.input_rate)

                for callback in list(self._listeners):
                    try:
                        callback(data)
                    except Exception:
                        LOGGER.exception("处理麦克风音频时发生异常")
            except OSError:
                LOGGER.exception("读取麦克风失败")

    def _output_loop(self) -> None:
        while self._running.is_set():
            try:
                generation, data, sample_rate = self._output_queue.get(timeout=0.1)
            except queue.Empty:
                if self._output_active:
                    self._output_active = False
                    self._notify_output_idle()
                continue

            self._output_active = True
            if sample_rate != self.output_device_rate:
                data = resample_pcm16(data, sample_rate, self.output_device_rate)

            for index in range(0, len(data), self.output_chunk_bytes):
                with self._playback_lock:
                    current_generation = self._playback_generation

                if generation != current_generation or not self._running.is_set():
                    break

                chunk = data[index : index + self.output_chunk_bytes]
                try:
                    assert self._output_stream is not None
                    self._output_stream.write(chunk)
                except OSError:
                    LOGGER.exception("播放扬声器音频失败")
                    break

    def _notify_output_idle(self) -> None:
        if self._output_idle_callback is None:
            return
        try:
            self._output_idle_callback()
        except Exception:
            LOGGER.exception("执行播放完成回调失败")

