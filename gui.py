"""GUI 模块 - 设置窗口与悬浮状态窗口。"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import ttk
from collections.abc import Callable

from config import AppConfig, ConfigManager

LOGGER = logging.getLogger(__name__)


# ======================================================================
# 设置窗口
# ======================================================================


class SettingsWindow:
    """基于 tkinter 的设置窗口，在独立线程中运行。"""

    def __init__(
        self,
        config: AppConfig,
        config_manager: ConfigManager,
        on_save: Callable[[AppConfig], None],
    ) -> None:
        self._config = config
        self._config_manager = config_manager
        self._on_save = on_save
        self._root: tk.Tk | None = None
        self._thread: threading.Thread | None = None
        self._entries: dict[str, tk.Entry] = {}
        self._alive = False

    def start(self) -> None:
        if self._alive:
            return
        self._alive = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def is_alive(self) -> bool:
        return self._alive

    def _run(self) -> None:
        self._root = tk.Tk()
        self._root.title("Gemini Live PC Assistant - 设置")
        self._root.geometry("480x620")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 主框架
        main_frame = ttk.Frame(self._root, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        ttk.Label(main_frame, text="设置", font=("", 14, "bold")).pack(pady=(0, 8))

        # 可滚动区域
        canvas = tk.Canvas(main_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 字段定义
        fields = [
            ("api_key", "Gemini API Key", True),
            ("model", "模型名称", False),
            ("hotkey", "热键 (如 ctrl+space)", False),
            ("wake_word", "唤醒词", False),
            ("vad_threshold", "VAD 能量阈值", False),
            ("vad_multiplier", "VAD 倍率", False),
            ("vad_attack_ms", "VAD 攻击时间 (ms)", False),
            ("vad_release_ms", "VAD 释放时间 (ms)", False),
            ("pre_roll_ms", "预缓冲时间 (ms)", False),
            ("manual_listen_timeout", "手动监听超时 (秒)", False),
            ("input_rate", "输入采样率 (Hz)", False),
            ("output_rate", "输出采样率 (Hz)", False),
            ("input_device_rate", "输入设备采样率 (Hz)", False),
            ("output_device_rate", "输出设备采样率 (Hz)", False),
            ("chunk_ms", "音频块时长 (ms)", False),
            ("input_device_index", "输入设备索引 (-1=默认)", False),
            ("output_device_index", "输出设备索引 (-1=默认)", False),
            ("reconnect_initial_delay", "重连初始延迟 (秒)", False),
            ("reconnect_max_delay", "重连最大延迟 (秒)", False),
            ("screenshot_dir", "截图保存目录", False),
        ]

        for key, label, is_password in fields:
            row = ttk.Frame(scroll_frame)
            row.pack(fill=tk.X, padx=4, pady=3)

            ttk.Label(row, text=label, width=28, anchor=tk.W).pack(side=tk.LEFT)

            entry = tk.Entry(row, width=30, show="*" if is_password else "")
            entry.pack(side=tk.RIGHT, fill=tk.X, expand=True)

            value = getattr(self._config, key, "")
            entry.insert(0, str(value))
            self._entries[key] = entry

        # 按钮区
        btn_frame = ttk.Frame(self._root, padding=8)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="保存", command=self._on_save_click).pack(
            side=tk.RIGHT, padx=4
        )
        ttk.Button(btn_frame, text="取消", command=self._on_close).pack(
            side=tk.RIGHT, padx=4
        )
        ttk.Button(btn_frame, text="重置为默认", command=self._on_reset).pack(
            side=tk.LEFT, padx=4
        )

        self._root.mainloop()

    def _on_save_click(self) -> None:
        try:
            updates: dict = {}
            for key, entry in self._entries.items():
                updates[key] = entry.get()

            new_config = self._config_manager.update(**updates)
            self._config = new_config
            self._on_save(new_config)

            if self._root:
                self._root.title("设置已保存!")
                self._root.after(1200, self._on_close)
        except Exception as exc:
            LOGGER.exception("保存设置失败")
            if self._root:
                self._root.title(f"保存失败: {exc}")

    def _on_reset(self) -> None:
        default = AppConfig()
        for key, entry in self._entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, str(getattr(default, key, "")))

    def _on_close(self) -> None:
        self._alive = False
        if self._root:
            self._root.destroy()
            self._root = None


# ======================================================================
# 悬浮状态窗口
# ======================================================================


class FloatingStatusWindow:
    """半透明悬浮窗，显示当前状态、用户和助手文本。"""

    def __init__(self, config_getter: Callable[[], AppConfig]) -> None:
        self._config_getter = config_getter
        self._root: tk.Tk | None = None
        self._thread: threading.Thread | None = None
        self._state_label: tk.Label | None = None
        self._user_label: tk.Label | None = None
        self._assistant_label: tk.Label | None = None
        self._alive = False
        self._drag_data = {"x": 0, "y": 0}

    def start(self) -> None:
        if self._alive:
            return
        self._alive = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._alive = False
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass

    def set_state(self, state: str) -> None:
        labels = {
            "connected": "已连接",
            "listening": "聆听中 ...",
            "speaking": "播放中 ...",
            "disconnected": "未连接",
        }
        colors = {
            "connected": "#4CAF50",
            "listening": "#2196F3",
            "speaking": "#FFC107",
            "disconnected": "#9E9E9E",
        }
        self._update_label(self._state_label, labels.get(state, state), colors.get(state, "#9E9E9E"))

    def set_status_text(self, text: str) -> None:
        self._update_label(self._state_label, text, "#2196F3")

    def set_user_text(self, text: str) -> None:
        display = text if len(text) <= 60 else text[:57] + "..."
        self._update_label(self._user_label, f"你: {display}", "#FFFFFF")

    def set_assistant_text(self, text: str) -> None:
        display = text if len(text) <= 60 else text[:57] + "..."
        self._update_label(self._assistant_label, f"助手: {display}", "#FFFFFF")

    def _run(self) -> None:
        self._root = tk.Tk()
        self._root.title("状态")
        self._root.overrideredirect(True)  # 无边框
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.85)
        self._root.configure(bg="#1E1E1E")

        cfg = self._config_getter()
        x = cfg.status_window_x
        y = cfg.status_window_y
        self._root.geometry(f"260x100+{x}+{y}")

        # 拖拽支持
        self._root.bind("<Button-1>", self._on_drag_start)
        self._root.bind("<B1-Motion>", self._on_drag_motion)

        # 状态标签
        self._state_label = tk.Label(
            self._root,
            text="初始化中 ...",
            font=("", 10, "bold"),
            fg="#9E9E9E",
            bg="#1E1E1E",
            anchor=tk.W,
        )
        self._state_label.pack(fill=tk.X, padx=8, pady=(6, 0))

        # 用户文本
        self._user_label = tk.Label(
            self._root,
            text="",
            font=("", 9),
            fg="#BBBBBB",
            bg="#1E1E1E",
            anchor=tk.W,
            wraplength=240,
        )
        self._user_label.pack(fill=tk.X, padx=8)

        # 助手文本
        self._assistant_label = tk.Label(
            self._root,
            text="",
            font=("", 9),
            fg="#BBBBBB",
            bg="#1E1E1E",
            anchor=tk.W,
            wraplength=240,
        )
        self._assistant_label.pack(fill=tk.X, padx=8)

        self._root.mainloop()

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag_motion(self, event: tk.Event) -> None:
        if self._root is None:
            return
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        x = self._root.winfo_x() + dx
        y = self._root.winfo_y() + dy
        self._root.geometry(f"+{x}+{y}")

    def _update_label(self, label: tk.Label | None, text: str, fg: str) -> None:
        if label is None or self._root is None:
            return
        try:
            self._root.after(0, lambda: self._apply_label(label, text, fg))
        except Exception:
            pass

    @staticmethod
    def _apply_label(label: tk.Label, text: str, fg: str) -> None:
        try:
            label.config(text=text, fg=fg)
        except tk.TclError:
            pass
