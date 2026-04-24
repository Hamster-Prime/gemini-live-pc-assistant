from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)


CONFIG_FILE = Path(__file__).with_name("assistant_config.json")


@dataclass(slots=True)
class AppConfig:
    api_key: str = ""
    model: str = "gemini-3.1-flash-live-preview"
    hotkey: str = "ctrl+space"
    wake_word: str = "小助手"
    vad_threshold: float = 180.0
    vad_multiplier: float = 2.2
    vad_attack_ms: int = 150
    vad_release_ms: int = 900
    pre_roll_ms: int = 300
    manual_listen_timeout: float = 8.0
    input_rate: int = 16000
    output_rate: int = 24000
    input_device_rate: int = 16000
    output_device_rate: int = 24000
    chunk_ms: int = 30
    input_device_index: int = -1
    output_device_index: int = -1
    reconnect_initial_delay: float = 2.0
    reconnect_max_delay: float = 12.0
    status_window_x: int = 30
    status_window_y: int = 30
    screenshot_dir: str = "runtime/screenshots"
    max_screenshots: int = 50
    status_window_opacity: float = 0.85
    silent_mode: bool = False
    auto_start: bool = False
    main_window_x: int = -1  # 主窗口X坐标，-1表示默认
    main_window_y: int = -1  # 主窗口Y坐标，-1表示默认
    main_window_width: int = 720  # 主窗口宽度
    main_window_height: int = 520  # 主窗口高度
    http_proxy: str = ""  # HTTP代理地址，如 http://127.0.0.1:7890
    https_proxy: str = ""  # HTTPS代理地址，如 http://127.0.0.1:7890

    def resolved_api_key(self) -> str:
        return self.api_key.strip() or os.getenv("GEMINI_API_KEY", "").strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConfigManager:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CONFIG_FILE
        self._lock = threading.RLock()

    def load(self) -> AppConfig:
        with self._lock:
            if not self.path.exists():
                config = AppConfig(api_key=os.getenv("GEMINI_API_KEY", "").strip())
                self.save(config)
                return config

            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                LOGGER.warning("配置文件 %s 读取失败，使用默认值: %s", self.path, exc)
                data = {}

            config = AppConfig()
            for key, value in data.items():
                if hasattr(config, key):
                    setattr(config, key, self._coerce_value(getattr(config, key), value))

            if not config.api_key:
                config.api_key = os.getenv("GEMINI_API_KEY", "").strip()

            return config

    def save(self, config: AppConfig) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)

    def update(self, **kwargs: Any) -> AppConfig:
        with self._lock:
            config = self.load()
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, self._coerce_value(getattr(config, key), value))
            self.save(config)
            return config

    @staticmethod
    def _coerce_value(current: Any, value: Any) -> Any:
        try:
            if isinstance(current, bool):
                if isinstance(value, str):
                    return value.strip().lower() in {"1", "true", "yes", "on"}
                return bool(value)

            if isinstance(current, int) and not isinstance(current, bool):
                return int(value)

            if isinstance(current, float):
                return float(value)

            return value
        except (ValueError, TypeError):
            LOGGER.warning("配置值转换失败: %r -> %r，使用默认值", value, current)
            return current

