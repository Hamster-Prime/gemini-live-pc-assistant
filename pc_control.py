from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pyautogui
import pyperclip


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
    "文件管理器": "explorer.exe",
    "命令提示符": "cmd.exe",
    "cmd": "cmd.exe",
    "终端": "wt.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "浏览器": "msedge.exe",
    "edge": "msedge.exe",
    "chrome": "chrome.exe",
    "谷歌浏览器": "chrome.exe",
    "word": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE",
    "ppt": "POWERPNT.EXE",
    "vscode": "code.exe",
    "代码": "code.exe",
    "设置": "ms-settings:",
    "settings": "ms-settings:",
    "控制面板": "control.exe",
    "任务管理器": "taskmgr.exe",
    "微信": "WeChat.exe",
    "qq": "QQ.exe",
    "钉钉": "DingTalk.exe",
    "飞书": "Lark.exe",
    "网易云音乐": "cloudmusic.exe",
    "spotify": "Spotify.exe",
}


class PCController:
    def __init__(self, screenshot_dir: str = "runtime/screenshots", max_screenshots: int = 50) -> None:
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.max_screenshots = max_screenshots
        self._cleanup_old_screenshots()

    def mouse_click(self, x: int, y: int, button: str = "left") -> dict[str, Any]:
        try:
            self._validate_button(button)
            width, height = pyautogui.size()
            x = max(0, min(int(x), width - 1))
            y = max(0, min(int(y), height - 1))
            pyautogui.click(x=x, y=y, button=button)
            return {"ok": True, "action": "mouse_click", "x": x, "y": y, "button": button}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "mouse_click", "x": x, "y": y}

    def mouse_move(self, x: int, y: int) -> dict[str, Any]:
        try:
            width, height = pyautogui.size()
            x = max(0, min(int(x), width - 1))
            y = max(0, min(int(y), height - 1))
            pyautogui.moveTo(x, y, duration=0.08)
            return {"ok": True, "action": "mouse_move", "x": x, "y": y}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "mouse_move", "x": x, "y": y}

    def mouse_scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> dict[str, Any]:
        try:
            clicks = max(-50, min(50, int(clicks)))
            if x is not None and y is not None:
                pyautogui.moveTo(int(x), int(y), duration=0.08)
            pyautogui.scroll(clicks)
            return {"ok": True, "action": "mouse_scroll", "clicks": clicks, "x": x, "y": y}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "mouse_scroll", "clicks": clicks, "x": x, "y": y}

    def type_text(self, text: str) -> dict[str, Any]:
        """输入文本，支持中文等非 ASCII 字符（通过剪贴板）。"""
        if any(ord(c) > 127 for c in text):
            try:
                old_clipboard = pyperclip.paste()
            except Exception:
                old_clipboard = None
            try:
                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.1)
            finally:
                if old_clipboard is not None:
                    try:
                        pyperclip.copy(old_clipboard)
                    except Exception:
                        pass
        else:
            pyautogui.write(text, interval=0.02)
        return {"ok": True, "action": "type_text", "text": text}

    def press_key(self, key: str) -> dict[str, Any]:
        try:
            pyautogui.press(key)
            return {"ok": True, "action": "press_key", "key": key}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "press_key", "key": key}

    def hotkey(self, *keys: str) -> dict[str, Any]:
        normalized = [key for key in keys if key]
        if not normalized:
            return {"ok": False, "error": "组合键不能为空", "action": "hotkey"}
        try:
            pyautogui.hotkey(*normalized)
            return {"ok": True, "action": "hotkey", "keys": normalized}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "hotkey", "keys": normalized}

    def open_app(self, name: str) -> dict[str, Any]:
        target = self._normalize_app_name(name)
        try:
            if hasattr(os, "startfile") and Path(target).exists():
                os.startfile(target)  # type: ignore[attr-defined]
            else:
                # Use list form to avoid shell injection
                subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)
            return {"ok": True, "action": "open_app", "name": name, "target": target}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "open_app", "name": name}

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
            return {"ok": False, "error": result.stderr.strip() or result.stdout.strip() or "关闭应用失败", "action": "close_app", "name": name}
        return {"ok": True, "action": "close_app", "name": name, "target": image_name}

    def screenshot(self) -> dict[str, Any]:
        try:
            now = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = self.screenshot_dir / f"screenshot_{now}.png"
            image = pyautogui.screenshot()
            image.save(path)
            width, height = image.size
            self._cleanup_old_screenshots()
            return {
                "ok": True,
                "action": "screenshot",
                "path": str(path),
                "width": width,
                "height": height,
            }
        except Exception as exc:
            return {"ok": False, "error": f"截图失败: {exc}"}

    def get_pixel_color(self, x: int, y: int) -> dict[str, Any]:
        """获取指定坐标的像素颜色。"""
        try:
            width, height = pyautogui.size()
            x = max(0, min(int(x), width - 1))
            y = max(0, min(int(y), height - 1))
            r, g, b = pyautogui.pixel(x, y)
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            return {
                "ok": True,
                "action": "get_pixel_color",
                "x": x, "y": y,
                "r": r, "g": g, "b": b,
                "hex": hex_color,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "get_pixel_color", "x": x, "y": y}

    def get_screen_info(self) -> dict[str, Any]:
        try:
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
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "get_screen_info"}

    @staticmethod
    def _validate_button(button: str) -> None:
        if button not in {"left", "right", "middle"}:
            raise ValueError("button 只能是 left、right 或 middle")

    def get_clipboard(self) -> dict[str, Any]:
        """获取剪贴板内容。"""
        try:
            text = pyperclip.paste()
            return {"ok": True, "action": "get_clipboard", "text": text}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def set_clipboard(self, text: str) -> dict[str, Any]:
        """设置剪贴板内容。"""
        try:
            pyperclip.copy(text)
            return {"ok": True, "action": "set_clipboard", "text": text}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_mouse_position(self) -> dict[str, Any]:
        """获取当前鼠标位置。"""
        try:
            x, y = pyautogui.position()
            return {"ok": True, "action": "get_mouse_position", "x": x, "y": y}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def double_click(self, x: int, y: int) -> dict[str, Any]:
        """双击指定坐标。"""
        try:
            width, height = pyautogui.size()
            x = max(0, min(int(x), width - 1))
            y = max(0, min(int(y), height - 1))
            pyautogui.doubleClick(x=x, y=y)
            return {"ok": True, "action": "double_click", "x": x, "y": y}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "double_click", "x": x, "y": y}

    def right_click(self, x: int, y: int) -> dict[str, Any]:
        """右键点击指定坐标。"""
        try:
            width, height = pyautogui.size()
            x = max(0, min(int(x), width - 1))
            y = max(0, min(int(y), height - 1))
            pyautogui.rightClick(x=x, y=y)
            return {"ok": True, "action": "right_click", "x": x, "y": y}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "right_click", "x": x, "y": y}

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> dict[str, Any]:
        """从 (x1,y1) 拖拽到 (x2,y2)。"""
        try:
            width, height = pyautogui.size()
            x1 = max(0, min(int(x1), width - 1))
            y1 = max(0, min(int(y1), height - 1))
            x2 = max(0, min(int(x2), width - 1))
            y2 = max(0, min(int(y2), height - 1))
            pyautogui.moveTo(x1, y1)
            pyautogui.dragTo(x2, y2, duration=duration, button="left")
            return {"ok": True, "action": "drag", "x1": x1, "y1": y1, "x2": x2, "y2": y2}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "drag", "x1": x1, "y1": y1, "x2": x2, "y2": y2}

    def wait_and_click(self, x: int, y: int, timeout: float = 5.0) -> dict[str, Any]:
        """等待指定时间后点击坐标。"""
        try:
            width, height = pyautogui.size()
            x = max(0, min(int(x), width - 1))
            y = max(0, min(int(y), height - 1))
            time.sleep(max(0.0, float(timeout)))
            pyautogui.click(x=x, y=y)
            return {"ok": True, "action": "wait_and_click", "x": x, "y": y, "waited": timeout}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "wait_and_click", "x": x, "y": y}

    def get_active_window(self) -> dict[str, Any]:
        """获取当前活动窗口信息。"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            return {"ok": True, "action": "get_active_window", "title": title, "hwnd": hwnd}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def list_windows(self) -> dict[str, Any]:
        """列出所有可见窗口。"""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            windows = []
            def _enum_callback(hwnd, _lparam):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        windows.append({"hwnd": hwnd, "title": buf.value})
                return True
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)
            return {"ok": True, "action": "list_windows", "windows": windows}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @staticmethod
    def _find_window_by_title(title: str) -> int:
        """通过标题查找窗口，支持部分匹配。返回 hwnd 或 0。"""
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        # 先精确匹配
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            return hwnd
        # 部分匹配
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        found = [0]
        def _enum(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if title.lower() in buf.value.lower():
                        found[0] = hwnd
                        return False
            return True
        WNDENUMPROC(_enum)(0)
        return found[0]

    def focus_window(self, title: str) -> dict[str, Any]:
        """将指定标题的窗口带到前台（支持部分匹配）。"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._find_window_by_title(title)
            if not hwnd:
                return {"ok": False, "error": f"未找到窗口: {title}"}
            user32.SetForegroundWindow(hwnd)
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            return {"ok": True, "action": "focus_window", "title": title}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "focus_window", "title": title}

    def open_url(self, url: str) -> dict[str, Any]:
        """在默认浏览器中打开 URL。"""
        try:
            import webbrowser
            webbrowser.open(url)
            return {"ok": True, "action": "open_url", "url": url}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def kill_process(self, name: str) -> dict[str, Any]:
        """按进程名结束进程（比 close_app 更精确）。"""
        try:
            result = subprocess.run(
                ["taskkill", "/IM", name, "/F"],
                capture_output=True,
                text=True,
                shell=False,
            )
            if result.returncode != 0:
                return {"ok": False, "error": result.stderr.strip() or result.stdout.strip() or "结束进程失败"}
            return {"ok": True, "action": "kill_process", "name": name}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "kill_process", "name": name}

    def list_processes(self) -> dict[str, Any]:
        """列出所有运行中的进程。"""
        try:
            import psutil
            processes = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    info = proc.info
                    processes.append({
                        "name": info["name"] or "",
                        "pid": str(info["pid"]),
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return {"ok": True, "action": "list_processes", "processes": processes[:50]}
        except ImportError:
            return {"ok": False, "error": "需要安装 psutil: pip install psutil"}

    def get_system_info(self) -> dict[str, Any]:
        """获取系统基本信息。"""
        import platform
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return {
                "ok": True,
                "action": "get_system_info",
                "os": platform.system(),
                "os_version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "cpu_percent": cpu_percent,
                "memory_total_gb": round(mem.total / (1024**3), 1),
                "memory_used_gb": round(mem.used / (1024**3), 1),
                "memory_percent": mem.percent,
                "disk_total_gb": round(disk.total / (1024**3), 1),
                "disk_used_gb": round(disk.used / (1024**3), 1),
                "disk_percent": round(disk.percent, 1),
            }
        except ImportError:
            return {
                "ok": True,
                "action": "get_system_info",
                "os": platform.system(),
                "os_version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "note": "安装 psutil 可获取 CPU/内存/磁盘信息",
            }

    def get_battery_status(self) -> dict[str, Any]:
        """获取电池状态（电量、是否充电、剩余时间）。"""
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery is None:
                return {"ok": True, "action": "get_battery_status", "note": "未检测到电池（可能是台式机）"}
            return {
                "ok": True,
                "action": "get_battery_status",
                "percent": battery.percent,
                "is_charging": battery.power_plugged,
                "secs_left": battery.secs_left if battery.secs_left != psutil.POWER_TIME_UNLIMITED else None,
            }
        except ImportError:
            return {"ok": False, "error": "需要安装 psutil: pip install psutil"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def run_command(self, command: str, timeout: int = 10) -> dict[str, Any]:
        """执行 shell 命令并返回输出。"""
        timeout = max(1, min(60, int(timeout)))
        dangerous = [
            "format ", "del /s", "rmdir /s", "rd /s",
            "shutdown", "reboot", "reg delete", "reg add",
            "bcdedit", "diskpart", "cipher /w", "sfc /",
            "net user", "net localgroup", "netsh firewall",
        ]
        cmd_lower = command.lower().strip()
        for d in dangerous:
            if d in cmd_lower:
                return {"ok": False, "error": f"危险命令被阻止: {d.strip()}"}
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, shell=True,
                timeout=timeout, encoding="utf-8", errors="replace",
            )
            output = result.stdout.strip()
            if result.returncode != 0 and result.stderr:
                output = (output + "\n" + result.stderr.strip()).strip()
            if len(output) > 2000:
                output = output[:2000] + "...\n[输出已截断]"
            return {
                "ok": result.returncode == 0,
                "action": "run_command",
                "command": command,
                "returncode": result.returncode,
                "output": output,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"命令执行超时 ({timeout}s)"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_time(self) -> dict[str, Any]:
        """获取当前日期和时间。"""
        from datetime import datetime
        now = datetime.now()
        return {
            "ok": True,
            "action": "get_time",
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
        }

    def search_web(self, query: str) -> dict[str, Any]:
        """在默认浏览器中搜索。"""
        try:
            import webbrowser
            import urllib.parse
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            webbrowser.open(url)
            return {"ok": True, "action": "search_web", "query": query, "url": url}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _safe_hotkey(self, *keys: str) -> dict[str, Any]:
        """安全执行组合键，捕获异常。"""
        action = "+".join(keys)
        try:
            pyautogui.hotkey(*keys)
            return {"ok": True, "action": action}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": action}

    def select_all(self) -> dict[str, Any]:
        """全选 (Ctrl+A)。"""
        return self._safe_hotkey("ctrl", "a")

    def undo(self) -> dict[str, Any]:
        """撤销 (Ctrl+Z)。"""
        return self._safe_hotkey("ctrl", "z")

    def redo(self) -> dict[str, Any]:
        """重做 (Ctrl+Y)。"""
        return self._safe_hotkey("ctrl", "y")

    def copy_selection(self) -> dict[str, Any]:
        """复制选中内容 (Ctrl+C)。"""
        return self._safe_hotkey("ctrl", "c")

    def paste_from_clipboard(self) -> dict[str, Any]:
        """粘贴剪贴板内容 (Ctrl+V)。"""
        return self._safe_hotkey("ctrl", "v")

    def save_file(self) -> dict[str, Any]:
        """保存文件 (Ctrl+S)。"""
        return self._safe_hotkey("ctrl", "s")

    def close_tab(self) -> dict[str, Any]:
        """关闭当前标签页 (Ctrl+W)。"""
        return self._safe_hotkey("ctrl", "w")

    def new_tab(self) -> dict[str, Any]:
        """打开新标签页 (Ctrl+T)。"""
        return self._safe_hotkey("ctrl", "t")

    def switch_window(self) -> dict[str, Any]:
        """切换窗口 (Alt+Tab)。"""
        return self._safe_hotkey("alt", "tab")

    def lock_screen(self) -> dict[str, Any]:
        """锁定屏幕 (Win+L)。"""
        return self._safe_hotkey("win", "l")

    def read_file(self, path: str) -> dict[str, Any]:
        """读取文本文件内容。"""
        try:
            p = Path(path).resolve()
            # 阻止读取敏感系统路径
            blocked = ["windows/system32", "windows/syswow64", "windows/system", "/etc/shadow", "/etc/passwd"]
            path_lower = str(p).lower()
            for b in blocked:
                if b in path_lower:
                    return {"ok": False, "error": "不允许读取系统文件"}
            if not p.exists():
                return {"ok": False, "error": f"文件不存在: {path}"}
            if p.stat().st_size > 1024 * 1024:  # 1MB limit
                return {"ok": False, "error": "文件过大（超过 1MB）"}
            content = p.read_text(encoding="utf-8", errors="replace")
            return {"ok": True, "action": "read_file", "path": str(p), "content": content}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        """写入文本文件（原子写入）。"""
        try:
            p = Path(path).resolve()
            # 阻止写入敏感系统路径
            blocked = ["windows/system32", "windows/syswow64", "windows/system", "/etc/"]
            path_lower = str(p).lower()
            for b in blocked:
                if b in path_lower:
                    return {"ok": False, "error": "不允许写入系统目录"}
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(p)
            return {"ok": True, "action": "write_file", "path": str(p), "size": len(content)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def list_directory(self, path: str = ".") -> dict[str, Any]:
        """列出目录内容。"""
        try:
            p = Path(path).resolve()
            if not p.exists():
                return {"ok": False, "error": f"目录不存在: {path}"}
            if not p.is_dir():
                return {"ok": False, "error": f"不是目录: {path}"}
            items = []
            for item in p.iterdir():
                try:
                    items.append({
                        "name": item.name,
                        "type": "dir" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    })
                except (PermissionError, OSError):
                    continue
                if len(items) >= 100:
                    break
            return {"ok": True, "action": "list_directory", "path": str(p), "items": items}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def type_keys(self, keys: str) -> dict[str, Any]:
        """输入按键序列，支持 {enter}、{tab}、{esc} 等特殊键。"""
        import re
        special_keys = {
            "{enter}": "enter", "{tab}": "tab", "{esc}": "esc",
            "{space}": "space", "{backspace}": "backspace",
            "{delete}": "delete", "{up}": "up", "{down}": "down",
            "{left}": "left", "{right}": "right",
            "{home}": "home", "{end}": "end",
            "{pageup}": "pageup", "{pagedown}": "pagedown",
            "{f1}": "f1", "{f2}": "f2", "{f3}": "f3", "{f4}": "f4",
            "{f5}": "f5", "{f6}": "f6", "{f7}": "f7", "{f8}": "f8",
            "{f9}": "f9", "{f10}": "f10", "{f11}": "f11", "{f12}": "f12",
        }
        parts = re.split(r"(\{[^}]+\})", keys)
        for part in parts:
            if not part:
                continue
            if part in special_keys:
                pyautogui.press(special_keys[part])
            elif any(ord(c) > 127 for c in part):
                try:
                    old_clipboard = pyperclip.paste()
                except Exception:
                    old_clipboard = None
                try:
                    pyperclip.copy(part)
                    time.sleep(0.05)
                    pyautogui.hotkey("ctrl", "v")
                    time.sleep(0.1)
                finally:
                    if old_clipboard is not None:
                        try:
                            pyperclip.copy(old_clipboard)
                        except Exception:
                            pass
            else:
                pyautogui.write(part, interval=0.02)
        return {"ok": True, "action": "type_keys", "keys": keys}

    @staticmethod
    def _normalize_app_name(name: str) -> str:
        key = name.strip().lower()
        return COMMON_APPS.get(key, name.strip())

    def _cleanup_old_screenshots(self) -> None:
        """保留最新的 max_screenshots 张截图，删除旧的。"""
        try:
            files = sorted(self.screenshot_dir.glob("screenshot_*.png"), key=lambda f: f.stat().st_mtime)
            if len(files) > self.max_screenshots:
                for f in files[: len(files) - self.max_screenshots]:
                    f.unlink(missing_ok=True)
        except Exception:
            pass

    def list_audio_devices(self) -> dict[str, Any]:
        """列出所有音频输入/输出设备。"""
        import pyaudio
        pa = pyaudio.PyAudio()
        devices = []
        try:
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                devices.append({
                    "index": i,
                    "name": info.get("name", ""),
                    "max_input_channels": info.get("maxInputChannels", 0),
                    "max_output_channels": info.get("maxOutputChannels", 0),
                    "default_sample_rate": info.get("defaultSampleRate", 0),
                })
        finally:
            pa.terminate()
        return {"ok": True, "action": "list_audio_devices", "devices": devices}

    def window_minimize(self, title: str) -> dict[str, Any]:
        """最小化指定标题的窗口。"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._find_window_by_title(title)
            if not hwnd:
                return {"ok": False, "error": f"未找到窗口: {title}"}
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            return {"ok": True, "action": "window_minimize", "title": title}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "window_minimize", "title": title}

    def window_maximize(self, title: str) -> dict[str, Any]:
        """最大化指定标题的窗口。"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._find_window_by_title(title)
            if not hwnd:
                return {"ok": False, "error": f"未找到窗口: {title}"}
            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            return {"ok": True, "action": "window_maximize", "title": title}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "window_maximize", "title": title}

    def window_restore(self, title: str) -> dict[str, Any]:
        """恢复指定标题的窗口。"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._find_window_by_title(title)
            if not hwnd:
                return {"ok": False, "error": f"未找到窗口: {title}"}
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            return {"ok": True, "action": "window_restore", "title": title}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "action": "window_restore", "title": title}

    def get_volume(self) -> dict[str, Any]:
        """获取系统音量（0-100）。"""
        try:
            from ctypes import POINTER, cast
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            vol = volume.GetMasterVolumeLevelScalar()
            return {"ok": True, "action": "get_volume", "volume": round(vol * 100)}
        except ImportError:
            return {"ok": False, "error": "需要安装 pycaw: pip install pycaw"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def set_volume(self, level: int) -> dict[str, Any]:
        """设置系统音量（0-100）。"""
        level = max(0, min(100, int(level)))
        try:
            from ctypes import POINTER, cast
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(level / 100.0, None)
            return {"ok": True, "action": "set_volume", "volume": level}
        except ImportError:
            return {"ok": False, "error": "需要安装 pycaw: pip install pycaw"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

