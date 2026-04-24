from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass(slots=True)
class VadDecision:
    energy: float
    threshold: float
    raw_active: bool
    speech_started: bool = False
    speech_ended: bool = False
    speech_active: bool = False
    emit_chunks: list[bytes] = field(default_factory=list)


class EnergyVadWakeDetector:
    def __init__(
        self,
        *,
        threshold: float,
        multiplier: float,
        attack_ms: int,
        release_ms: int,
        pre_roll_ms: int,
        chunk_ms: int,
        volume_callback: callable = None,
    ) -> None:
        self.base_threshold = float(threshold)
        self.multiplier = float(multiplier)
        self.attack_frames = max(1, math.ceil(attack_ms / chunk_ms))
        self.release_frames = max(1, math.ceil(release_ms / chunk_ms))
        self.pre_roll_frames = max(1, math.ceil(pre_roll_ms / chunk_ms))
        self.volume_callback = volume_callback  # 音量回调，参数是归一化的音量值0-100
        self._max_energy = 1000  # 最大能量参考值，用于归一化音量

        self._noise_floor = max(1.0, self.base_threshold / 2)
        self._pre_roll: deque[bytes] = deque(maxlen=self.pre_roll_frames)
        self._active_count = 0
        self._silent_count = 0
        self._in_speech = False

    def reset(self) -> None:
        self._pre_roll.clear()
        self._active_count = 0
        self._silent_count = 0
        self._in_speech = False

    def process(self, chunk: bytes) -> VadDecision:
        energy = self._calculate_energy(chunk)
        # 回调音量值，归一化到0-100
        if self.volume_callback:
            normalized_volume = min(100, int(energy / self._max_energy * 100))
            self.volume_callback(normalized_volume)
        threshold = max(self.base_threshold, self._noise_floor * self.multiplier)
        raw_active = energy >= threshold
        self._pre_roll.append(chunk)

        if not self._in_speech and not raw_active:
            # 快速攻击（噪声升高时快速跟随），慢速释放（噪声降低时缓慢跟随）
            if energy > self._noise_floor:
                self._noise_floor = (self._noise_floor * 0.85) + (energy * 0.15)
            else:
                self._noise_floor = (self._noise_floor * 0.98) + (energy * 0.02)

        speech_started = False
        speech_ended = False
        emit_chunks: list[bytes] = []

        if raw_active:
            self._active_count += 1
            self._silent_count = 0
        else:
            if self._in_speech:
                self._silent_count += 1
            else:
                self._active_count = 0

        if not self._in_speech and self._active_count >= self.attack_frames:
            self._in_speech = True
            self._silent_count = 0
            speech_started = True
            emit_chunks = list(self._pre_roll)
            self._pre_roll.clear()
        elif self._in_speech:
            emit_chunks = [chunk]
            if not raw_active and self._silent_count >= self.release_frames:
                speech_ended = True
                self._in_speech = False
                self._active_count = 0
                self._silent_count = 0

        return VadDecision(
            energy=energy,
            threshold=threshold,
            raw_active=raw_active,
            speech_started=speech_started,
            speech_ended=speech_ended,
            speech_active=self._in_speech,
            emit_chunks=emit_chunks,
        )

    @staticmethod
    def _calculate_energy(chunk: bytes) -> float:
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(samples))))


EnergyWakeWordDetector = EnergyVadWakeDetector

