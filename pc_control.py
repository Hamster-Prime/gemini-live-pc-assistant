from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import pyautogui


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


COMMON_APPS = {
    "记事本": "notepad.exe",
    "notepad": "notepad.exe",
    "计算器": "calc.exe",
    "calc": "calc.exe",
    "画图": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "资源管理器": "explorer.exe",
    "explorer": "explorer.exe",
    "命令提示符": "cmd.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "浏览器": "msedge.exe",
    "edge": "msedge.exe",
}


class PCController:
    def __init__(self, screenshot_dir: str = "runtime/screenshots") -> None:
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def mouse_click(self, x: int, y: int, button: str = "left") -> dict[str, Any]:
        self._validate_button(button)
        width, height = pyautogui.size()
        x = max(0, min(int(x), width - 1))
        y = max(0, min(int(y), height - 1))
        pyautogui.click(x=x, y=y, button=button)
        return {"ok": True, "action": "mouse_click", "x": x, "y": y, "button": button}

    def mouse_move(self, x: int, y: int) -> dict[str, Any]:
        width, height = pyautogui.size()
        x = max(0, min(int(x), width - 1))
        y = max(0, min(int(y), height - 1))
        pyautogui.moveTo(x, y, duration=0.08)
        return {"ok": True, "action": "mouse_move", "x": x, "y": y}

    def mouse_scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> dict[str, Any]:
        if x is not None and y is not None:
            pyautogui.moveTo(int(x), int(y), duration=0.08)
        pyautogui.scroll(int(clicks))
        return {"ok": True, "action": "mouse_scroll", "clicks": int(clicks), "x": x, "y": y}

    def type_text(self, text: str) -> dict[str, Any]:
        pyautogui.write(text, interval=0.02)
        return {"ok": True, "action": "type_text", "text": text}

    def press_key(self, key: str) -> dict[str, Any]:
        pyautogui.press(key)
        return {"ok": True, "action": "press_key", "key": key}

    def hotkey(self, *keys: str) -> dict[str, Any]:
        normalized = [key for key in keys if key]
        if not normalized:
            raise ValueError("组合键不能为空")
        pyautogui.hotkey(*normalized)
        return {"ok": True, "action": "hotkey", "keys": normalized}

    def open_app(self, name: str) -> dict[str, Any]:
        target = self._normalize_app_name(name)
        if hasattr(os, "startfile") and Path(target).exists():
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["cmd", "/c", "start", "", target])
        return {"ok": True, "action": "open_app", "name": name, "target": target}

    def close_app(self, name: str) -> dict[str, Any]:
        target = self._normalize_app_name(name)
        image_name = Path(target).name if Path(target).suffix else target
        if not image_name.lower().endswith(".exe"):
            image_name = f"{image_name}.exe"

        result = subprocess.run(
            ["taskkill", "/IM", image_name, "/F"],
            capture_output=True,
            text=True,
            shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "关闭应用失败")

        return {"ok": True, "action": "close_app", "name": name, "target": image_name}

    def screenshot(self) -> dict[str, Any]:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.screenshot_dir / f"screenshot_{now}.png"
        image = pyautogui.screenshot()
        image.save(path)
        width, height = image.size
        return {
            "ok": True,
            "action": "screenshot",
            "path": str(path),
            "width": width,
            "height": height,
        }

    def get_screen_info(self) -> dict[str, Any]:
        width, height = pyautogui.size()
        x, y = pyautogui.position()
        return {
            "ok": True,
            "action": "get_screen_info",
            "width": width,
            "height": height,
            "mouse_x": x,
            "mouse_y": y,
        }

    @staticmethod
    def _validate_button(button: str) -> None:
        if button not in {"left", "right", "middle"}:
            raise ValueError("button 只能是 left、right 或 middle")

    @staticmethod
    def _normalize_app_name(name: str) -> str:
        key = name.strip().lower()
        return COMMON_APPS.get(key, name.strip())

