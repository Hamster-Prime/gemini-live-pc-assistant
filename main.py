"""Gemini Live PC Assistant - 主入口

将音频流、唤醒词检测、Gemini Live API 与 PC 控制整合为完整应用。
"""

from __future__ import annotations

import logging
import logging.handlers
import signal
import sys
import threading
from pathlib import Path

import keyboard

from audio_stream import AudioStreamManager
from config import AppConfig, ConfigManager
from gemini_session import GeminiLiveSession
from gui import FloatingStatusWindow, MainWindow, SettingsWindow
from tools import ToolRegistry
from tray import TrayManager
from wake_word import EnergyVadWakeDetector

LOGGER = logging.getLogger(__name__)


def _setup_logging() -> None:
    """配置日志：控制台 + 滚动文件。"""
    log_dir = Path(__file__).parent / "runtime" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "assistant.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(console)

    # File handler (10MB, keep 3 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(file_handler)


_setup_logging()


def _check_dependencies() -> None:
    """检查必要的依赖是否已安装。"""
    required = [
        ("pyaudio", "PyAudio"),
        ("pyautogui", "pyautogui"),
        ("pystray", "pystray"),
        ("PIL", "Pillow"),
        ("keyboard", "keyboard"),
        ("numpy", "numpy"),
        ("google.genai", "google-genai"),
    ]
    optional = [
        ("pyperclip", "pyperclip"),
        ("pycaw", "pycaw"),
        ("comtypes", "comtypes"),
        ("psutil", "psutil"),
    ]
    missing = []
    for module, package in required:
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        LOGGER.error("缺少必要依赖: %s，请运行: pip install %s", ", ".join(missing), " ".join(missing))
        sys.exit(1)
    for module, package in optional:
        try:
            __import__(module)
        except ImportError:
            LOGGER.warning("可选依赖 %s 未安装，部分功能不可用: pip install %s", package, package)


_check_dependencies()


class AssistantApp:
    """主应用类，协调所有子系统。"""

    VERSION = "1.2.0"

    def __init__(self) -> None:
        self._config_manager = ConfigManager()
        self._config = self._config_manager.load()

        self._tool_registry = ToolRegistry(self._config)

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
        self._muted = False
        self._lock = threading.Lock()
        self._hold_to_talk = False
        self._hotkey_release_callback = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def run(self) -> None:
        """启动应用主循环。"""
        LOGGER.info("正在启动 Gemini Live PC Assistant v%s ...", self.VERSION)

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self._init_audio()
        self._init_wake_detector()
        self._init_gemini()
        self._register_hotkey()

        self._floating_status = FloatingStatusWindow(
            config_getter=self.get_config,
            config_manager=self._config_manager,
            on_double_click=self._show_main_window,
        )
        self._floating_status.start()

        self._main_window = MainWindow(
            config_getter=self.get_config,
            status_getter=self._get_status_text,
            on_toggle_listen=self._on_hotkey_pressed,
            on_settings=self._open_settings,
            on_exit=self._exit,
            on_toggle_mute=self.toggle_mute,
        )
        self._main_window.start()

        self._tray = TrayManager(
            on_settings=self._show_main_window,
            on_exit=self._exit,
            status_getter=self._get_status_text,
            on_toggle_mute=self.toggle_mute,
            on_toggle_floating=self.toggle_floating_window,
            on_clear_conversation=self.clear_conversation,
            on_restart_session=self.restart_gemini_session,
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
            # 注册热键按下和松开事件，支持按住说话
            def on_hotkey_press(e):
                with self._lock:
                    if not self._manual_mode:
                        self._hold_to_talk = True
                        self._on_hotkey_pressed() # 开始聆听
            
            def on_hotkey_release(e):
                with self._lock:
                    if self._hold_to_talk and self._manual_mode:
                        self._hold_to_talk = False
                        self._finish_manual_listen() # 松开结束
            
            keyboard.add_hotkey(hotkey, callback=on_hotkey_press, suppress=False, trigger_on_release=False)
            self._hotkey_release_callback = on_hotkey_release
            keyboard.on_release_key(hotkey.split('+')[-1], callback=on_hotkey_release, suppress=False)
            LOGGER.info("已注册热键：%s (支持按住说话)", hotkey)
        except Exception:
            LOGGER.exception("注册热键 %s 失败", hotkey)

        # Register mute hotkey (Ctrl+M)
        try:
            keyboard.add_hotkey("ctrl+m", self.toggle_mute, suppress=False)
            LOGGER.info("已注册静音热键：ctrl+m")
        except Exception:
            LOGGER.exception("注册静音热键失败")
            
        # Register open main window hotkey (Ctrl+O)
        try:
            keyboard.add_hotkey("ctrl+o", self._show_main_window, suppress=False)
            LOGGER.info("已注册打开主窗口热键：ctrl+o")
        except Exception:
            LOGGER.exception("注册打开主窗口热键失败")

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

        if self._muted:
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
            # 非手动模式下，语音结束自动发送结束标记，触发Gemini回复
            if not self._manual_mode and self._gemini_session and self._gemini_session.is_connected():
                self._gemini_session.send_activity_end()
                self._gemini_session.send_audio_stream_end()
                with self._lock:
                    self._listening = False
                # 更新UI状态
                if self._floating_status:
                    self._floating_status.set_state("idle")
                if self._main_window:
                    self._main_window.set_state("idle")
                    self._main_window.set_listening(False)

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
        if self._wake_detector:
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

    def toggle_mute(self) -> None:
        """切换麦克风静音状态。"""
        self._muted = not self._muted
        state = "已静音" if self._muted else "已取消静音"
        LOGGER.info(state)
        if self._floating_status:
            self._floating_status.set_status_text(state)
        if self._main_window:
            self._main_window.set_status_text(state)
            self._main_window.set_muted(self._muted)

    def is_muted(self) -> bool:
        return self._muted
    
    def toggle_floating_window(self) -> None:
        """切换悬浮窗显示/隐藏"""
        if self._floating_status:
            self._floating_status.toggle_visibility()
            LOGGER.info("已切换悬浮窗显示状态")
    
    def clear_conversation(self) -> None:
        """清空主窗口对话历史"""
        if self._main_window:
            self._main_window._clear_conversations()
            LOGGER.info("已清空对话历史")
            if self._floating_status:
                self._floating_status.set_status_text("对话历史已清空")
            if self._main_window:
                self._main_window.set_status_text("对话历史已清空")
    
    def restart_gemini_session(self) -> None:
        """重启Gemini会话"""
        if self._gemini_session:
            self._gemini_session.restart()
            LOGGER.info("已重启Gemini会话")
            if self._floating_status:
                self._floating_status.set_status_text("正在重启Gemini会话...")
            if self._main_window:
                self._main_window.set_status_text("正在重启Gemini会话...")

    def _on_settings_saved(self, new_config: AppConfig) -> None:
        old_config = self._config
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

        # 音频设备配置变更时重启音频流
        audio_changed = (
            old_config.input_device_index != new_config.input_device_index
            or old_config.output_device_index != new_config.output_device_index
            or old_config.input_device_rate != new_config.input_device_rate
            or old_config.output_device_rate != new_config.output_device_rate
            or old_config.chunk_ms != new_config.chunk_ms
        )
        if audio_changed and self._audio_stream:
            LOGGER.info("音频设备配置已变更，重启音频流")
            self._audio_stream.stop()
            self._init_audio()

        # 热键变更时重新注册
        if old_config.hotkey != new_config.hotkey:
            try:
                keyboard.remove_hotkey(old_config.hotkey)
                # 移除旧的松开事件回调
                if self._hotkey_release_callback:
                    keyboard.unhook(self._hotkey_release_callback)
                    self._hotkey_release_callback = None
            except Exception:
                pass
            try:
                # 重新注册新热键（支持按住说话）
                def on_hotkey_press(e):
                    with self._lock:
                        if not self._manual_mode:
                            self._hold_to_talk = True
                            self._on_hotkey_pressed() # 开始聆听
                
                def on_hotkey_release(e):
                    with self._lock:
                        if self._hold_to_talk and self._manual_mode:
                            self._hold_to_talk = False
                            self._finish_manual_listen() # 松开结束
                
                keyboard.add_hotkey(new_config.hotkey, callback=on_hotkey_press, suppress=False, trigger_on_release=False)
                self._hotkey_release_callback = on_hotkey_release
                keyboard.on_release_key(new_config.hotkey.split('+')[-1], callback=on_hotkey_release, suppress=False)
                LOGGER.info("热键已更新：%s (支持按住说话)", new_config.hotkey)
            except Exception:
                LOGGER.exception("注册新热键 %s 失败", new_config.hotkey)

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

    def _signal_handler(self, signum: int, frame: object) -> None:
        """信号处理：优雅退出。"""
        LOGGER.info("收到信号 %d，正在退出 ...", signum)
        self._exit()

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def _cleanup(self) -> None:
        LOGGER.info("正在清理资源 ...")
        if self._manual_timer:
            self._manual_timer.cancel()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
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
