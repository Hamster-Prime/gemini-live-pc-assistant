"""系统托盘管理 - 使用 pystray 提供托盘图标和菜单。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PIL import Image, ImageDraw
import pystray

LOGGER = logging.getLogger(__name__)

_STATUS_LABELS = {
    "connected": "已连接 Gemini",
    "listening": "正在聆听 ...",
    "speaking": "正在播放 ...",
    "disconnected": "未连接",
}


def _create_icon_image(status: str = "disconnected") -> Image.Image:
    """创建一个简单的纯色托盘图标。"""
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    colors = {
        "connected": (76, 175, 80, 255),
        "listening": (33, 150, 243, 255),
        "speaking": (255, 193, 7, 255),
        "disconnected": (158, 158, 158, 255),
    }
    color = colors.get(status, colors["disconnected"])

    margin = 8
    draw.ellipse([margin, margin, size - margin, size - margin], fill=color)
    return image


class TrayManager:
    """管理 pystray 系统托盘。"""

    def __init__(
        self,
        on_settings: Callable[[], None],
        on_exit: Callable[[], None],
        status_getter: Callable[[], str],
        on_toggle_mute: Callable[[], None] | None = None,
        on_toggle_floating: Callable[[], None] | None = None,
        on_clear_conversation: Callable[[], None] | None = None,
        on_restart_session: Callable[[], None] | None = None,
    ) -> None:
        self._on_settings = on_settings
        self._on_exit = on_exit
        self._status_getter = status_getter
        self._on_toggle_mute = on_toggle_mute
        self._on_toggle_floating = on_toggle_floating
        self._on_clear_conversation = on_clear_conversation
        self._on_restart_session = on_restart_session
        self._icon: pystray.Icon | None = None
        self._current_status = "disconnected"

    def run(self) -> None:
        """阻塞运行托盘图标。"""
        def _status_text(icon: pystray.Icon, item: pystray.MenuItem) -> str:
            return f"状态: {_STATUS_LABELS.get(self._current_status, self._current_status)}"

        # 构建菜单
        menu_items = [
            pystray.MenuItem(_status_text, lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]
        
        # 添加快速操作（如果回调存在）
        if self._on_toggle_mute:
            menu_items.append(pystray.MenuItem("切换静音", self._on_toggle_mute_click))
        if self._on_toggle_floating:
            menu_items.append(pystray.MenuItem("显示/隐藏悬浮窗", self._on_toggle_floating_click))
        if self._on_clear_conversation:
            menu_items.append(pystray.MenuItem("清空对话历史", self._on_clear_conversation_click))
        if self._on_restart_session:
            menu_items.append(pystray.MenuItem("重启Gemini会话", self._on_restart_session_click))
        
        # 通用菜单项
        menu_items.extend([
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("设置", self._on_settings_click),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._on_exit_click),
        ])
        
        menu = pystray.Menu(*menu_items)

        self._icon = pystray.Icon(
            name="GeminiLiveAssistant",
            icon=_create_icon_image(),
            title="Gemini Live PC Assistant",
            menu=menu,
        )
        self._icon.run()

    def update_status(self, status: str) -> None:
        """更新托盘图标状态。"""
        self._current_status = status
        if self._icon is not None:
            self._icon.icon = _create_icon_image(status)
            label = _STATUS_LABELS.get(status, status)
            self._icon.title = f"Gemini Live - {label}"
            # pystray MenuItem 不支持动态文本，通过 icon title 传达状态

    def stop(self) -> None:
        """停止托盘图标主循环。"""
        if self._icon is not None:
            self._icon.stop()

    def _on_settings_click(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        try:
            self._on_settings()
        except Exception:
            LOGGER.exception("打开设置窗口失败")

    def _on_toggle_mute_click(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        try:
            if self._on_toggle_mute:
                self._on_toggle_mute()
        except Exception:
            LOGGER.exception("切换静音失败")
    
    def _on_toggle_floating_click(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        try:
            if self._on_toggle_floating:
                self._on_toggle_floating()
        except Exception:
            LOGGER.exception("切换悬浮窗显示失败")
    
    def _on_clear_conversation_click(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        try:
            if self._on_clear_conversation:
                self._on_clear_conversation()
        except Exception:
            LOGGER.exception("清空对话历史失败")
    
    def _on_restart_session_click(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        try:
            if self._on_restart_session:
                self._on_restart_session()
        except Exception:
            LOGGER.exception("重启Gemini会话失败")
    
    def _on_exit_click(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        try:
            self._on_exit()
        except Exception:
            LOGGER.exception("退出应用失败")
