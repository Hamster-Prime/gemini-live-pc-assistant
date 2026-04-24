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
    ) -> None:
        self._on_settings = on_settings
        self._on_exit = on_exit
        self._status_getter = status_getter
        self._icon: pystray.Icon | None = None
        self._current_status = "disconnected"
        self._status_item: pystray.MenuItem | None = None

    def run(self) -> None:
        """阻塞运行托盘图标。"""
        self._status_item = pystray.MenuItem(
            f"状态: {_STATUS_LABELS.get(self._current_status, self._current_status)}",
            lambda: None,
            enabled=False,
        )

        menu = pystray.Menu(
            self._status_item,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("设置", self._on_settings_click),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._on_exit_click),
        )

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

    def _on_settings_click(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        try:
            self._on_settings()
        except Exception:
            LOGGER.exception("打开设置窗口失败")

    def _on_exit_click(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        try:
            self._on_exit()
        except Exception:
            LOGGER.exception("退出应用失败")
