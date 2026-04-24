"""GUI 模块 - 主窗口、设置窗口与悬浮状态窗口。"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import ttk
from collections.abc import Callable

from config import AppConfig, ConfigManager

LOGGER = logging.getLogger(__name__)


_STATE_LABELS = {
    "connected": "已连接",
    "listening": "聆听中",
    "speaking": "播放中",
    "disconnected": "未连接",
    "idle": "待机",
}

_STATE_COLORS = {
    "connected": "#2E7D32",
    "listening": "#1565C0",
    "speaking": "#F9A825",
    "disconnected": "#757575",
    "idle": "#455A64",
}


class MainWindow:
    """完整主界面，显示状态、对话和常用操作。"""

    def __init__(
        self,
        *,
        config_getter: Callable[[], AppConfig],
        status_getter: Callable[[], str],
        on_toggle_listen: Callable[[], None],
        on_settings: Callable[[], None],
        on_exit: Callable[[], None],
        on_toggle_mute: Callable[[], None] | None = None,
    ) -> None:
        self._config_getter = config_getter
        self._status_getter = status_getter
        self._on_toggle_listen = on_toggle_listen
        self._on_settings = on_settings
        self._on_exit = on_exit
        self._on_toggle_mute = on_toggle_mute
        self._root: tk.Tk | None = None
        self._thread: threading.Thread | None = None
        self._state_label: ttk.Label | None = None
        self._status_var: tk.StringVar | None = None
        self._user_text: tk.Text | None = None
        self._assistant_text: tk.Text | None = None
        self._toggle_button: ttk.Button | None = None
        self._mute_button: ttk.Button | None = None
        self._alive = False

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
        if self._root is None or self._state_label is None:
            return
        self._root.after(0, lambda: self._apply_state(state))

    def set_status_text(self, text: str) -> None:
        if self._root is None or self._status_var is None:
            return
        self._root.after(0, lambda: self._status_var.set(text))

    def set_user_text(self, text: str) -> None:
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._append_text(self._user_text, f"[{timestamp}] {text}")

    def set_assistant_text(self, text: str) -> None:
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._append_text(self._assistant_text, f"[{timestamp}] {text}")
    
    def _clear_conversations(self) -> None:
        """清空对话历史"""
        if self._root is None:
            return
        
        def clear():
            try:
                # 清空用户和助手对话
                if self._user_text:
                    self._user_text.config(state=tk.NORMAL)
                    self._user_text.delete(1.0, tk.END)
                    self._user_text.config(state=tk.DISABLED)
                if self._assistant_text:
                    self._assistant_text.config(state=tk.NORMAL)
                    self._assistant_text.delete(1.0, tk.END)
                    self._assistant_text.config(state=tk.DISABLED)
            except tk.TclError:
                pass
        
        self._root.after(0, clear)

    def set_listening(self, listening: bool) -> None:
        if self._root is None or self._toggle_button is None:
            return
        label = "停止聆听" if listening else "开始聆听"
        self._root.after(0, lambda: self._toggle_button.configure(text=label))

    def set_muted(self, muted: bool) -> None:
        if self._root is None or self._mute_button is None:
            return
        label = "取消静音" if muted else "静音"
        self._root.after(0, lambda: self._mute_button.configure(text=label))

    def _clear_conversations(self) -> None:
        """清空对话历史显示。"""
        for widget in (self._user_text, self._assistant_text):
            if widget is not None:
                try:
                    widget.configure(state=tk.NORMAL)
                    widget.delete("1.0", tk.END)
                    widget.configure(state=tk.DISABLED)
                except tk.TclError:
                    pass

    def _run(self) -> None:
        self._root = tk.Tk()
        self._root.title("Gemini Live PC Assistant")
        self._root.geometry("720x520")
        self._root.minsize(620, 420)
        self._root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self._status_var = tk.StringVar(self._root, value="正在启动 ...")

        style = ttk.Style(self._root)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("State.TLabel", font=("Microsoft YaHei UI", 11, "bold"), padding=8)

        header = ttk.Frame(self._root, padding=(16, 14, 16, 8))
        header.pack(fill=tk.X)
        ttk.Label(header, text="Gemini Live PC Assistant", style="Title.TLabel").pack(side=tk.LEFT)
        self._state_label = ttk.Label(header, text="初始化", style="State.TLabel")
        self._state_label.pack(side=tk.RIGHT)

        status_frame = ttk.LabelFrame(self._root, text="状态", padding=12)
        status_frame.pack(fill=tk.X, padx=16, pady=(0, 10))
        ttk.Label(status_frame, textvariable=self._status_var, wraplength=650).pack(fill=tk.X)

        actions = ttk.Frame(self._root, padding=(16, 0, 16, 10))
        actions.pack(fill=tk.X)
        self._toggle_button = ttk.Button(actions, text="开始聆听", command=self._on_toggle_listen)
        self._toggle_button.pack(side=tk.LEFT)
        if self._on_toggle_mute:
            self._mute_button = ttk.Button(actions, text="静音", command=self._on_toggle_mute)
            self._mute_button.pack(side=tk.LEFT, padx=4)
        else:
            self._mute_button = None
        ttk.Button(actions, text="设置", command=self._on_settings).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="清空对话", command=self._clear_conversations).pack(side=tk.LEFT, padx=4)
        ttk.Button(actions, text="隐藏到托盘", command=self._hide_to_tray).pack(side=tk.LEFT)
        ttk.Button(actions, text="退出", command=self._on_exit).pack(side=tk.RIGHT)

        panes = ttk.PanedWindow(self._root, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))
        self._user_text = self._create_text_panel(panes, "用户")
        self._assistant_text = self._create_text_panel(panes, "助手")

        cfg = self._config_getter()
        self._status_var.set(f"热键: {cfg.hotkey}    模型: {cfg.model}")
        self._root.mainloop()
        self._alive = False

    def _create_text_panel(self, panes: ttk.PanedWindow, title: str) -> tk.Text:
        frame = ttk.LabelFrame(panes, text=title, padding=8)
        text = tk.Text(frame, height=12, wrap=tk.WORD, state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        panes.add(frame, weight=1)
        return text

    def _append_text(self, widget: tk.Text | None, text: str) -> None:
        if self._root is None or widget is None or not text:
            return
        self._root.after(0, lambda: self._apply_text(widget, text))

    @staticmethod
    def _apply_text(widget: tk.Text, text: str) -> None:
        try:
            widget.configure(state=tk.NORMAL)
            widget.insert(tk.END, text.strip() + "\n\n")
            widget.see(tk.END)
            widget.configure(state=tk.DISABLED)
        except tk.TclError:
            pass

    def _apply_state(self, state: str) -> None:
        if self._state_label is None:
            return
        self._state_label.configure(
            text=_STATE_LABELS.get(state, state),
            foreground=_STATE_COLORS.get(state, "#455A64"),
        )



    def _hide_to_tray(self) -> None:
        if self._root is not None:
            self._root.withdraw()

    def show(self) -> None:
        if self._root is None:
            self.start()
            return
        self._root.after(0, self._show_now)

    def _show_now(self) -> None:
        if self._root is not None:
            self._root.deiconify()
            self._root.lift()


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

        # 鼠标滚轮支持
        def _on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

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
            ("max_screenshots", "最大截图保留数量", False),
            ("status_window_opacity", "悬浮窗透明度 (0.1-1.0)", False),
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

            # Validate numeric fields before saving
            default = AppConfig()
            for key, value in updates.items():
                field_default = getattr(default, key, None)
                if isinstance(field_default, (int, float)) and not isinstance(field_default, bool):
                    try:
                        if isinstance(field_default, int):
                            num_value = int(value)
                        else:
                            num_value = float(value)
                    except (ValueError, TypeError):
                        if self._root:
                            self._root.title(f"字段 {key} 必须是数字")
                        return

                    # Range validation
                    range_limits = {
                        "vad_threshold": (0, 10000),
                        "vad_multiplier": (1.0, 10.0),
                        "vad_attack_ms": (10, 2000),
                        "vad_release_ms": (100, 5000),
                        "pre_roll_ms": (0, 2000),
                        "manual_listen_timeout": (1.0, 60.0),
                        "chunk_ms": (10, 200),
                        "reconnect_initial_delay": (0.5, 60.0),
                        "reconnect_max_delay": (1.0, 300.0),
                        "max_screenshots": (1, 200),
                        "status_window_opacity": (0.1, 1.0),
                    }
                    if key in range_limits:
                        min_val, max_val = range_limits[key]
                        if not (min_val <= num_value <= max_val):
                            if self._root:
                                self._root.title(f"字段 {key} 必须在 {min_val}~{max_val} 之间")
                            return

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

    def __init__(self, config_getter: Callable[[], AppConfig], config_manager: "ConfigManager | None" = None, on_double_click: Callable[[], None] | None = None) -> None:
        self._config_getter = config_getter
        self._config_manager = config_manager
        self._on_double_click = on_double_click
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
            "idle": "待机",
        }
        colors = {
            "connected": "#4CAF50",
            "listening": "#2196F3",
            "speaking": "#FFC107",
            "disconnected": "#9E9E9E",
            "idle": "#607D8B",
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
        self._root.configure(bg="#1E1E1E")

        cfg = self._config_getter()
        x = cfg.status_window_x
        y = cfg.status_window_y
        self._root.geometry(f"260x100+{x}+{y}")
        self._root.attributes("-alpha", max(0.1, min(1.0, cfg.status_window_opacity)))

        # 拖拽支持
        self._root.bind("<Button-1>", self._on_drag_start)
        self._root.bind("<B1-Motion>", self._on_drag_motion)
        self._root.bind("<ButtonRelease-1>", self._on_drag_end)
        # 双击事件支持
        if self._on_double_click:
            self._root.bind("<Double-Button-1>", self._on_double_click_handler)

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

    def _on_drag_end(self, event: tk.Event) -> None:
        """拖拽结束时保存窗口位置。"""
        if self._root is None:
            return
        try:
            x, y = self._root.winfo_x(), self._root.winfo_y()
            if self._config_manager is not None:
                self._config_manager.update(status_window_x=x, status_window_y=y)
            else:
                from config import ConfigManager
                ConfigManager().update(status_window_x=x, status_window_y=y)
        except Exception:
            pass
    
    def _on_double_click_handler(self, event: tk.Event) -> None:
        """双击事件处理"""
        try:
            if self._on_double_click:
                self._on_double_click()
        except Exception:
            LOGGER.exception("处理双击事件失败")

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
    
    def hide(self) -> None:
        if self._root is not None:
            try:
                self._root.after(0, lambda: self._root.withdraw())
            except Exception:
                pass
    
    def show(self) -> None:
        if self._root is not None:
            try:
                self._root.after(0, lambda: self._root.deiconify())
            except Exception:
                pass
    
    def toggle_visibility(self) -> None:
        if self._root is not None:
            try:
                if self._root.state() == "withdrawn":
                    self.show()
                else:
                    self.hide()
            except Exception:
                pass
