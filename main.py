"""Gemini Live PC Assistant - 主入口

将音频流、唤醒词检测、Gemini Live API 与 PC 控制整合为完整应用。
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable

import keyboard

from audio_stream import AudioStreamManager
from config import AppConfig, ConfigManager
from gemini_session import GeminiLiveSession
from gui import FloatingStatusWindow, MainWindow, SettingsWindow
from pc_control import PCController
from tools import ToolRegistry
from tray import TrayManager
from wake_word import EnergyVadWakeDetector

LOGGER = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


class AssistantApp:
    """主应用类，协调所有子系统。"""

    def __init__(self) -> None:
        self._config_manager = ConfigManager()
        self._config = self._config_manager.load()

        self._tool_registry = ToolRegistry(self._config)
        self._pc_controller = PCController(self._config.screenshot_dir)

        self._audio_stream: AudioStreamManager | None = None
        self._wake_detector: EnergyVadWakeDetector | None = None
        self._gemini_session: GeminiLiveSession | None = None

        self._tray: TrayManager | None = None
        self._main_window: MainWindow | None = None
        self._settings_window: SettingsWindow | None = None
        self._floating_status: FloatingStatusWindow | None = None

        self._listening = False
        self._manual_mode = False
        self._manual_timer: threading.Timer | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def run(self) -> None:
        """启动应用主循环。"""
        LOGGER.info("正在启动 Gemini Live PC Assistant ...")

        self._init_audio()
        self._init_wake_detector()
        self._init_gemini()
        self._register_hotkey()

        self._floating_status = FloatingStatusWindow(config_getter=self.get_config)
        self._floating_status.start()

        self._main_window = MainWindow(
            config_getter=self.get_config,
            status_getter=self._get_status_text,
            on_toggle_listen=self._on_hotkey_pressed,
            on_settings=self._open_settings,
            on_exit=self._exit,
        )
        self._main_window.start()

        self._tray = TrayManager(
            on_settings=self._show_main_window,
            on_exit=self._exit,
            status_getter=self._get_status_text,
        )

        try:
            self._tray.run()
        except KeyboardInterrupt:
            LOGGER.info("收到键盘中断，正在退出 ...")
        finally:
            self._cleanup()

    def _init_audio(self) -> None:
        cfg = self._config
        self._audio_stream = AudioStreamManager(
            input_rate=cfg.input_rate,
            output_rate=cfg.output_rate,
            input_device_rate=cfg.input_device_rate,
            output_device_rate=cfg.output_device_rate,
            chunk_ms=cfg.chunk_ms,
            input_device_index=cfg.input_device_index,
            output_device_index=cfg.output_device_index,
        )
        self._audio_stream.add_input_listener(self._on_mic_chunk)
        self._audio_stream.set_output_idle_callback(self._on_playback_idle)
        self._audio_stream.start()

    def _init_wake_detector(self) -> None:
        cfg = self._config
        self._wake_detector = EnergyVadWakeDetector(
            threshold=cfg.vad_threshold,
            multiplier=cfg.vad_multiplier,
            attack_ms=cfg.vad_attack_ms,
            release_ms=cfg.vad_release_ms,
            pre_roll_ms=cfg.pre_roll_ms,
            chunk_ms=cfg.chunk_ms,
        )

    def _init_gemini(self) -> None:
        self._gemini_session = GeminiLiveSession(
            config_getter=self.get_config,
            tool_registry_getter=self._get_tool_registry,
            on_connection_change=self._on_connection_change,
            on_status=self._on_status,
            on_user_transcript=self._on_user_transcript,
            on_assistant_transcript=self._on_assistant_transcript,
            on_audio_output=self._on_audio_output,
            on_turn_complete=self._on_turn_complete,
            on_interrupted=self._on_interrupted,
        )
        self._gemini_session.start()

    def _register_hotkey(self) -> None:
        hotkey = self._config.hotkey
        try:
            keyboard.add_hotkey(hotkey, self._on_hotkey_pressed, suppress=False)
            LOGGER.info("已注册热键：%s", hotkey)
        except Exception:
            LOGGER.exception("注册热键 %s 失败", hotkey)

    # ------------------------------------------------------------------
    # 配置访问（供回调使用）
    # ------------------------------------------------------------------

    def get_config(self) -> AppConfig:
        return self._config

    def _get_tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    # ------------------------------------------------------------------
    # 音频回调
    # ------------------------------------------------------------------

    def _on_mic_chunk(self, chunk: bytes) -> None:
        """麦克风数据到达：VAD 检测 → 唤醒词 → 发送到 Gemini。"""
        if self._wake_detector is None:
            return

        if self._manual_mode:
            if self._gemini_session and self._gemini_session.is_connected():
                self._gemini_session.send_audio(chunk)
            return

        decision = self._wake_detector.process(chunk)

        if decision.speech_started:
            LOGGER.debug("语音活动开始 (energy=%.1f)", decision.energy)

        if decision.speech_ended:
            LOGGER.debug("语音活动结束")

        # 发送 pre-roll 音频（语音开始前的缓冲数据）
        if decision.speech_started and decision.emit_chunks:
            if self._gemini_session and self._gemini_session.is_connected():
                for pre_chunk in decision.emit_chunks:
                    self._gemini_session.send_audio(pre_chunk)
            # pre-roll 已包含当前 chunk，跳过下面的重复发送
        elif decision.speech_active:
            # 将音频发送到 Gemini
            if self._gemini_session and self._gemini_session.is_connected():
                self._gemini_session.send_audio(chunk)

    def _on_playback_idle(self) -> None:
        """播放结束回调。"""
        if self._floating_status:
            self._floating_status.set_state("listening" if self._listening else "idle")

    # ------------------------------------------------------------------
    # 热键回调
    # ------------------------------------------------------------------

    def _on_hotkey_pressed(self) -> None:
        """热键按下：切换手动监听模式。"""
        if self._manual_mode:
            self._finish_manual_listen()
        else:
            self._start_manual_listen()

    def _start_manual_listen(self) -> None:
        with self._lock:
            if self._manual_mode:
                return
            self._manual_mode = True
            self._listening = True
        self._wake_detector.reset()

        if self._gemini_session and not self._gemini_session.is_connected():
            self._gemini_session.restart()

        if self._gemini_session:
            self._gemini_session.send_activity_start()

        if self._floating_status:
            self._floating_status.set_state("listening")
        if self._main_window:
            self._main_window.set_state("listening")
            self._main_window.set_listening(True)

        # 超时自动结束
        timeout = self._config.manual_listen_timeout
        self._manual_timer = threading.Timer(timeout, self._finish_manual_listen)
        self._manual_timer.daemon = True
        self._manual_timer.start()

        LOGGER.info("手动监听模式已开启 (超时 %.1fs)", timeout)

    def _finish_manual_listen(self) -> None:
        with self._lock:
            if not self._manual_mode:
                return
            self._manual_mode = False
            self._listening = False

            if self._manual_timer:
                self._manual_timer.cancel()
                self._manual_timer = None

        if self._gemini_session:
            self._gemini_session.send_activity_end()
            self._gemini_session.send_audio_stream_end()

        if self._floating_status:
            self._floating_status.set_state("idle")
        if self._main_window:
            self._main_window.set_state("idle")
            self._main_window.set_listening(False)

        LOGGER.info("手动监听模式已结束")

    # ------------------------------------------------------------------
    # Gemini 会话回调
    # ------------------------------------------------------------------

    def _on_connection_change(self, connected: bool) -> None:
        state = "connected" if connected else "disconnected"
        if self._floating_status:
            self._floating_status.set_state(state)
        if self._main_window:
            self._main_window.set_state(state)
        if self._tray:
            self._tray.update_status(state)

    def _on_status(self, message: str) -> None:
        LOGGER.info("Gemini 状态: %s", message)
        if self._floating_status:
            self._floating_status.set_status_text(message)
        if self._main_window:
            self._main_window.set_status_text(message)

    def _on_user_transcript(self, text: str) -> None:
        if text:
            LOGGER.info("用户: %s", text)
            if self._floating_status:
                self._floating_status.set_user_text(text)
            if self._main_window:
                self._main_window.set_user_text(text)

    def _on_assistant_transcript(self, text: str) -> None:
        if text:
            LOGGER.info("助手: %s", text)
            if self._floating_status:
                self._floating_status.set_assistant_text(text)
            if self._main_window:
                self._main_window.set_assistant_text(text)

    def _on_audio_output(self, audio_bytes: bytes, sample_rate: int) -> None:
        if self._audio_stream:
            self._audio_stream.play_output(audio_bytes, sample_rate=sample_rate)
        if self._floating_status:
            self._floating_status.set_state("speaking")
        if self._main_window:
            self._main_window.set_state("speaking")

    def _on_turn_complete(self) -> None:
        LOGGER.debug("助手回合结束")
        if self._floating_status:
            self._floating_status.set_state("listening" if self._listening else "idle")
        if self._main_window:
            self._main_window.set_state("listening" if self._listening else "idle")

    def _on_interrupted(self) -> None:
        LOGGER.debug("收到 Gemini 中断信号，清空播放缓冲")
        if self._audio_stream:
            self._audio_stream.clear_output()

    # ------------------------------------------------------------------
    # 设置窗口
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        if self._settings_window and self._settings_window.is_alive():
            return

        self._settings_window = SettingsWindow(
            config=self._config,
            config_manager=self._config_manager,
            on_save=self._on_settings_saved,
        )
        self._settings_window.start()

    def _show_main_window(self) -> None:
        if self._main_window:
            self._main_window.show()

    def _on_settings_saved(self, new_config: AppConfig) -> None:
        self._config = new_config
        self._tool_registry = ToolRegistry(new_config)

        # 重建唤醒检测器
        self._wake_detector = EnergyVadWakeDetector(
            threshold=new_config.vad_threshold,
            multiplier=new_config.vad_multiplier,
            attack_ms=new_config.vad_attack_ms,
            release_ms=new_config.vad_release_ms,
            pre_roll_ms=new_config.pre_roll_ms,
            chunk_ms=new_config.chunk_ms,
        )

        # 重启 Gemini 会话以应用新配置
        if self._gemini_session:
            self._gemini_session.restart()

        if self._floating_status:
            self._floating_status.set_status_text("设置已保存")
        if self._main_window:
            self._main_window.set_status_text("设置已保存")

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def _get_status_text(self) -> str:
        if self._gemini_session and self._gemini_session.is_connected():
            return "已连接"
        return "未连接"

    def _exit(self) -> None:
        """托盘菜单触发退出：停止托盘主循环，交由 finally 清理资源。"""
        LOGGER.info("收到退出请求，正在关闭托盘 ...")
        if self._tray:
            self._tray.stop()

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def _cleanup(self) -> None:
        LOGGER.info("正在清理资源 ...")
        if self._manual_timer:
            self._manual_timer.cancel()
        if self._gemini_session:
            self._gemini_session.stop()
        if self._audio_stream:
            self._audio_stream.stop()
        if self._floating_status:
            self._floating_status.stop()
        if self._main_window:
            self._main_window.stop()
        LOGGER.info("已退出")


def main() -> None:
    app = AssistantApp()
    app.run()


if __name__ == "__main__":
    main()
