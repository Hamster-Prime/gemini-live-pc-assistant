from __future__ import annotations

import logging
from typing import Any

from google.genai import types

from config import AppConfig
from pc_control import PCController


LOGGER = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self, config: AppConfig) -> None:
        self._controller = PCController(config.screenshot_dir)
        self._declarations = self._build_declarations()

    def get_tools(self) -> list[types.Tool]:
        return [types.Tool(function_declarations=self._declarations)]

    def execute(self, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
        payload = args or {}
        LOGGER.info("执行工具调用：%s %s", name, payload)

        handlers = {
            "mouse_click": lambda: self._controller.mouse_click(
                x=payload["x"],
                y=payload["y"],
                button=payload.get("button", "left"),
            ),
            "double_click": lambda: self._controller.double_click(
                x=payload["x"],
                y=payload["y"],
            ),
            "right_click": lambda: self._controller.right_click(
                x=payload["x"],
                y=payload["y"],
            ),
            "mouse_move": lambda: self._controller.mouse_move(x=payload["x"], y=payload["y"]),
            "mouse_scroll": lambda: self._controller.mouse_scroll(
                clicks=payload["clicks"],
                x=payload.get("x"),
                y=payload.get("y"),
            ),
            "type_text": lambda: self._controller.type_text(text=payload["text"]),
            "press_key": lambda: self._controller.press_key(key=payload["key"]),
            "hotkey": lambda: self._controller.hotkey(*payload.get("keys", [])),
            "open_app": lambda: self._controller.open_app(name=payload["name"]),
            "close_app": lambda: self._controller.close_app(name=payload["name"]),
            "screenshot": self._controller.screenshot,
            "get_screen_info": self._controller.get_screen_info,
            "get_clipboard": self._controller.get_clipboard,
            "set_clipboard": lambda: self._controller.set_clipboard(text=payload["text"]),
            "get_mouse_position": self._controller.get_mouse_position,
            "list_audio_devices": self._controller.list_audio_devices,
            "window_minimize": lambda: self._controller.window_minimize(title=payload["title"]),
            "window_maximize": lambda: self._controller.window_maximize(title=payload["title"]),
            "window_restore": lambda: self._controller.window_restore(title=payload["title"]),
            "get_volume": self._controller.get_volume,
            "set_volume": lambda: self._controller.set_volume(level=payload["level"]),
            "drag": lambda: self._controller.drag(
                x1=payload["x1"], y1=payload["y1"],
                x2=payload["x2"], y2=payload["y2"],
                duration=payload.get("duration", 0.5),
            ),
            "wait_and_click": lambda: self._controller.wait_and_click(
                x=payload["x"], y=payload["y"],
                timeout=payload.get("timeout", 5.0),
            ),
            "get_active_window": self._controller.get_active_window,
            "list_windows": self._controller.list_windows,
            "get_pixel_color": lambda: self._controller.get_pixel_color(x=payload["x"], y=payload["y"]),
            "focus_window": lambda: self._controller.focus_window(title=payload["title"]),
            "open_url": lambda: self._controller.open_url(url=payload["url"]),
            "kill_process": lambda: self._controller.kill_process(name=payload["name"]),
            "list_processes": self._controller.list_processes,
            "get_system_info": self._controller.get_system_info,
            "run_command": lambda: self._controller.run_command(command=payload["command"], timeout=payload.get("timeout", 10)),
            "get_time": self._controller.get_time,
            "search_web": lambda: self._controller.search_web(query=payload["query"]),
            "select_all": self._controller.select_all,
            "undo": self._controller.undo,
            "redo": self._controller.redo,
            "copy_selection": self._controller.copy_selection,
            "paste_from_clipboard": self._controller.paste_from_clipboard,
            "save_file": self._controller.save_file,
            "close_tab": self._controller.close_tab,
            "new_tab": self._controller.new_tab,
            "switch_window": self._controller.switch_window,
            "lock_screen": self._controller.lock_screen,
            "read_file": lambda: self._controller.read_file(path=payload["path"]),
            "write_file": lambda: self._controller.write_file(path=payload["path"], content=payload["content"]),
            "list_directory": lambda: self._controller.list_directory(path=payload.get("path", ".")),
            "type_keys": lambda: self._controller.type_keys(keys=payload["keys"]),
        }

        if name not in handlers:
            raise ValueError(f"未知工具：{name}")

        try:
            return handlers[name]()
        except KeyError as exc:
            raise ValueError(f"工具 {name} 缺少必要参数: {exc}") from exc

    @staticmethod
    def _build_declarations() -> list[types.FunctionDeclaration]:
        return [
            types.FunctionDeclaration(
                name="mouse_click",
                description="在 Windows 屏幕指定坐标执行鼠标点击。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "屏幕横坐标"},
                        "y": {"type": "integer", "description": "屏幕纵坐标"},
                        "button": {
                            "type": "string",
                            "enum": ["left", "right", "middle"],
                            "description": "鼠标按键，默认 left",
                        },
                    },
                    "required": ["x", "y"],
                },
            ),
            types.FunctionDeclaration(
                name="double_click",
                description="在指定坐标执行鼠标双击。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "屏幕横坐标"},
                        "y": {"type": "integer", "description": "屏幕纵坐标"},
                    },
                    "required": ["x", "y"],
                },
            ),
            types.FunctionDeclaration(
                name="right_click",
                description="在指定坐标执行鼠标右键点击。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "屏幕横坐标"},
                        "y": {"type": "integer", "description": "屏幕纵坐标"},
                    },
                    "required": ["x", "y"],
                },
            ),
            types.FunctionDeclaration(
                name="mouse_move",
                description="把鼠标移动到指定坐标。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                    },
                    "required": ["x", "y"],
                },
            ),
            types.FunctionDeclaration(
                name="mouse_scroll",
                description="在当前位置或指定坐标执行鼠标滚轮滚动。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "clicks": {"type": "integer", "description": "正数向上滚动，负数向下滚动"},
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                    },
                    "required": ["clicks"],
                },
            ),
            types.FunctionDeclaration(
                name="type_text",
                description="把文本直接输入到当前聚焦窗口。支持中文等非 ASCII 字符（通过剪贴板粘贴）。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "需要键入的文本内容"}
                    },
                    "required": ["text"],
                },
            ),
            types.FunctionDeclaration(
                name="press_key",
                description="按下一次键盘按键，例如 enter、esc、tab。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                },
            ),
            types.FunctionDeclaration(
                name="hotkey",
                description="执行组合键，例如 ctrl+c、alt+tab。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "keys": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "按键顺序数组，例如 [\"ctrl\", \"c\"]",
                        }
                    },
                    "required": ["keys"],
                },
            ),
            types.FunctionDeclaration(
                name="open_app",
                description="打开一个应用程序、快捷方式或可执行文件。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ),
            types.FunctionDeclaration(
                name="close_app",
                description="关闭指定应用程序，优先按进程名结束。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ),
            types.FunctionDeclaration(
                name="screenshot",
                description="截取当前桌面截图并返回保存路径。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="get_screen_info",
                description="获取当前屏幕分辨率与鼠标位置。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="get_clipboard",
                description="获取系统剪贴板当前的文本内容。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="set_clipboard",
                description="将文本写入系统剪贴板。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "要写入剪贴板的文本"}
                    },
                    "required": ["text"],
                },
            ),
            types.FunctionDeclaration(
                name="get_mouse_position",
                description="获取当前鼠标的屏幕坐标位置。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="list_audio_devices",
                description="列出系统所有音频输入和输出设备。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="window_minimize",
                description="最小化指定标题的窗口。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "窗口标题"}
                    },
                    "required": ["title"],
                },
            ),
            types.FunctionDeclaration(
                name="window_maximize",
                description="最大化指定标题的窗口。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "窗口标题"}
                    },
                    "required": ["title"],
                },
            ),
            types.FunctionDeclaration(
                name="window_restore",
                description="恢复指定标题的窗口（从最小化/最大化恢复）。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "窗口标题"}
                    },
                    "required": ["title"],
                },
            ),
            types.FunctionDeclaration(
                name="get_volume",
                description="获取当前系统音量（0-100）。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="set_volume",
                description="设置系统音量（0-100）。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "level": {"type": "integer", "description": "音量级别 0-100"}
                    },
                    "required": ["level"],
                },
            ),
            types.FunctionDeclaration(
                name="drag",
                description="从一个坐标拖拽到另一个坐标。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "x1": {"type": "integer", "description": "起点横坐标"},
                        "y1": {"type": "integer", "description": "起点纵坐标"},
                        "x2": {"type": "integer", "description": "终点横坐标"},
                        "y2": {"type": "integer", "description": "终点纵坐标"},
                        "duration": {"type": "number", "description": "拖拽持续时间（秒），默认 0.5"},
                    },
                    "required": ["x1", "y1", "x2", "y2"],
                },
            ),
            types.FunctionDeclaration(
                name="wait_and_click",
                description="等待后点击指定坐标（用于等待页面加载）。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "屏幕横坐标"},
                        "y": {"type": "integer", "description": "屏幕纵坐标"},
                        "timeout": {"type": "number", "description": "等待超时（秒），默认 5"},
                    },
                    "required": ["x", "y"],
                },
            ),
            types.FunctionDeclaration(
                name="get_active_window",
                description="获取当前活动（前台）窗口的标题。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="list_windows",
                description="列出所有可见的窗口标题。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="get_pixel_color",
                description="获取指定屏幕坐标的像素颜色值。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "屏幕横坐标"},
                        "y": {"type": "integer", "description": "屏幕纵坐标"},
                    },
                    "required": ["x", "y"],
                },
            ),
            types.FunctionDeclaration(
                name="focus_window",
                description="将指定标题的窗口带到前台并激活。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "窗口标题（部分匹配）"}
                    },
                    "required": ["title"],
                },
            ),
            types.FunctionDeclaration(
                name="open_url",
                description="在默认浏览器中打开指定 URL。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "要打开的 URL"}
                    },
                    "required": ["url"],
                },
            ),
            types.FunctionDeclaration(
                name="kill_process",
                description="按进程名结束进程。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "进程名（如 notepad.exe）"}
                    },
                    "required": ["name"],
                },
            ),
            types.FunctionDeclaration(
                name="list_processes",
                description="列出当前运行中的进程。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="get_system_info",
                description="获取系统信息：操作系统、CPU、内存、磁盘使用情况。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="run_command",
                description="执行 shell 命令并返回输出。危险命令会被阻止。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "要执行的命令"},
                        "timeout": {"type": "integer", "description": "超时秒数，默认 10"},
                    },
                    "required": ["command"],
                },
            ),
            types.FunctionDeclaration(
                name="get_time",
                description="获取当前日期、时间和星期几。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="search_web",
                description="在默认浏览器中打开搜索引擎搜索指定关键词。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"}
                    },
                    "required": ["query"],
                },
            ),
            types.FunctionDeclaration(
                name="select_all",
                description="全选当前焦点中的所有内容 (Ctrl+A)。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="undo",
                description="撤销上一步操作 (Ctrl+Z)。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="redo",
                description="重做上一步操作 (Ctrl+Y)。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="copy_selection",
                description="复制当前选中内容 (Ctrl+C)。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="paste_from_clipboard",
                description="粘贴剪贴板内容到当前焦点 (Ctrl+V)。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="save_file",
                description="保存当前文件 (Ctrl+S)。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="close_tab",
                description="关闭当前标签页或文档 (Ctrl+W)。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="new_tab",
                description="打开新标签页 (Ctrl+T)。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="switch_window",
                description="切换到下一个窗口 (Alt+Tab)。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="lock_screen",
                description="锁定屏幕 (Win+L)。",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="read_file",
                description="读取文本文件内容（限 1MB 以内）。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"}
                    },
                    "required": ["path"],
                },
            ),
            types.FunctionDeclaration(
                name="write_file",
                description="写入内容到文本文件（会覆盖已有内容）。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "要写入的内容"},
                    },
                    "required": ["path", "content"],
                },
            ),
            types.FunctionDeclaration(
                name="list_directory",
                description="列出指定目录下的文件和子目录。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径，默认当前目录"}
                    },
                },
            ),
            types.FunctionDeclaration(
                name="type_keys",
                description="输入按键序列。支持特殊键如 {enter}、{tab}、{esc}、{backspace} 等。",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "keys": {"type": "string", "description": "按键序列，如 {tab}{tab}{enter} 或 hello{enter}"}
                    },
                    "required": ["keys"],
                },
            ),
        ]
