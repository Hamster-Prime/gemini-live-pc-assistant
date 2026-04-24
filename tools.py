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
                description="把文本直接输入到当前聚焦窗口。",
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
        ]

