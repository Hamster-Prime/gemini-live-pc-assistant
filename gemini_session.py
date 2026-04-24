from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import threading
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import types

from config import AppConfig
from tools import ToolRegistry


LOGGER = logging.getLogger(__name__)


class GeminiLiveSession:
    def __init__(
        self,
        *,
        config_getter: Callable[[], AppConfig],
        tool_registry_getter: Callable[[], ToolRegistry],
        on_connection_change: Callable[[bool], None],
        on_status: Callable[[str], None],
        on_user_transcript: Callable[[str], None],
        on_assistant_transcript: Callable[[str], None],
        on_audio_output: Callable[[bytes, int], None],
        on_turn_complete: Callable[[], None],
    ) -> None:
        self._config_getter = config_getter
        self._tool_registry_getter = tool_registry_getter
        self._on_connection_change = on_connection_change
        self._on_status = on_status
        self._on_user_transcript = on_user_transcript
        self._on_assistant_transcript = on_assistant_transcript
        self._on_audio_output = on_audio_output
        self._on_turn_complete = on_turn_complete

        self._stop_event = threading.Event()
        self._connected = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: Any = None
        self._sender_queue: asyncio.Queue[dict[str, Any]] | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._connected.clear()
        if self._loop is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(self._close_current_session(), self._loop)
                future.result(timeout=3)
            except Exception:
                LOGGER.debug("关闭 Gemini Live 会话时触发异常", exc_info=True)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def restart(self) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._close_current_session(), self._loop)

    def is_connected(self) -> bool:
        return self._connected.is_set()

    def send_audio(self, chunk: bytes) -> bool:
        return self._enqueue({"kind": "audio", "data": chunk})

    def send_activity_start(self) -> bool:
        return self._enqueue({"kind": "activity_start"}, allow_when_disconnected=False)

    def send_activity_end(self) -> bool:
        return self._enqueue({"kind": "activity_end"}, allow_when_disconnected=False)

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        delay = self._config_getter().reconnect_initial_delay

        while not self._stop_event.is_set():
            config = self._config_getter()
            api_key = config.resolved_api_key()
            if not api_key:
                self._notify_status("尚未配置 Gemini API Key，请先在设置中填写。")
                await asyncio.sleep(1.0)
                continue

            try:
                await self._connect_once(config, api_key)
                delay = config.reconnect_initial_delay
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.exception("Gemini Live 会话异常")
                self._connected.clear()
                self._session = None
                self._notify_connection(False)
                self._notify_status(f"Gemini 连接断开，{delay:.0f} 秒后重连：{exc}")
                await asyncio.sleep(delay)
                delay = min(delay * 2, config.reconnect_max_delay)

    async def _connect_once(self, config: AppConfig, api_key: str) -> None:
        self._notify_status("正在连接 Gemini Live API...")
        client = genai.Client(api_key=api_key)
        live_config = self._build_live_config(config)

        async with client.aio.live.connect(model=config.model, config=live_config) as session:
            self._session = session
            self._sender_queue = asyncio.Queue(maxsize=512)
            self._connected.set()
            self._notify_connection(True)
            self._notify_status("Gemini Live 已连接")

            sender_task = asyncio.create_task(self._sender_loop(session))
            receiver_task = asyncio.create_task(self._receiver_loop(session))
            done, pending = await asyncio.wait(
                {sender_task, receiver_task},
                return_when=asyncio.FIRST_EXCEPTION,
            )

            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

            for task in done:
                exception = task.exception()
                if exception is not None:
                    raise exception

        self._connected.clear()
        self._session = None
        self._notify_connection(False)

    async def _sender_loop(self, session: Any) -> None:
        assert self._sender_queue is not None
        while not self._stop_event.is_set():
            message = await self._sender_queue.get()
            kind = message["kind"]

            if kind == "audio":
                config = self._config_getter()
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=message["data"],
                        mime_type=f"audio/pcm;rate={config.input_rate}",
                    )
                )
            elif kind == "activity_start":
                await session.send_realtime_input(activity_start=types.ActivityStart())
            elif kind == "activity_end":
                await session.send_realtime_input(activity_end=types.ActivityEnd())
            elif kind == "function_response":
                await session.send_tool_response(function_responses=message["responses"])

    async def _receiver_loop(self, session: Any) -> None:
        async for response in session.receive():
            await self._handle_response(session, response)

    async def _handle_response(self, session: Any, response: Any) -> None:
        server_content = getattr(response, "server_content", None)
        if server_content is not None:
            input_transcription = getattr(server_content, "input_transcription", None)
            if input_transcription and getattr(input_transcription, "text", None):
                self._on_user_transcript(str(input_transcription.text).strip())

            output_transcription = getattr(server_content, "output_transcription", None)
            if output_transcription and getattr(output_transcription, "text", None):
                self._on_assistant_transcript(str(output_transcription.text).strip())

            model_turn = getattr(server_content, "model_turn", None)
            if model_turn is not None:
                for part in getattr(model_turn, "parts", []) or []:
                    audio_bytes, sample_rate = self._extract_audio_from_part(part)
                    if audio_bytes:
                        self._on_audio_output(audio_bytes, sample_rate)

                    text = getattr(part, "text", None)
                    if text:
                        self._on_assistant_transcript(str(text).strip())

            fallback_data = getattr(response, "data", None)
            if fallback_data:
                self._on_audio_output(self._ensure_bytes(fallback_data), self._config_getter().output_rate)

            if getattr(server_content, "turn_complete", False) or getattr(server_content, "interrupted", False):
                self._on_turn_complete()

        tool_call = getattr(response, "tool_call", None)
        if tool_call is not None:
            await self._handle_tool_call(session, tool_call)

        go_away = getattr(response, "go_away", None)
        if go_away is not None:
            time_left = getattr(go_away, "time_left", None)
            if time_left is not None:
                self._notify_status(f"服务端提示会话即将结束，剩余 {time_left} 秒。")

    async def _handle_tool_call(self, session: Any, tool_call: Any) -> None:
        function_calls = getattr(tool_call, "function_calls", None) or []
        if not function_calls:
            return

        tool_registry = self._tool_registry_getter()
        responses: list[types.FunctionResponse] = []

        for function_call in function_calls:
            args = self._normalize_function_args(getattr(function_call, "args", None))
            try:
                result = await asyncio.to_thread(tool_registry.execute, function_call.name, args)
            except Exception as exc:
                LOGGER.exception("执行工具 %s 失败", function_call.name)
                result = {"ok": False, "error": str(exc)}

            responses.append(
                types.FunctionResponse(
                    id=function_call.id,
                    name=function_call.name,
                    response=result,
                )
            )

        await session.send_tool_response(function_responses=responses)

    def _enqueue(self, message: dict[str, Any], allow_when_disconnected: bool = True) -> bool:
        if self._loop is None or self._sender_queue is None:
            return False
        if not allow_when_disconnected and not self.is_connected():
            return False
        if message["kind"] == "audio" and not self.is_connected():
            return False

        def _put() -> None:
            assert self._sender_queue is not None
            if message["kind"] == "audio" and self._sender_queue.qsize() > 200:
                return
            self._sender_queue.put_nowait(message)

        self._loop.call_soon_threadsafe(_put)
        return True

    async def _close_current_session(self) -> None:
        session = self._session
        if session is None:
            return
        try:
            await session.close()
        except Exception:
            LOGGER.debug("关闭 Live 会话时异常", exc_info=True)

    @staticmethod
    def _build_live_config(config: AppConfig) -> dict[str, Any]:
        system_text = (
            "你是一个 Windows 电脑语音助手。用户会通过中文语音让你操控电脑。"
            "请优先使用工具执行鼠标、键盘与应用控制。"
            "在执行危险操作前先用中文简短确认。"
            f"当前助手唤醒词偏好为：{config.wake_word}。"
        )
        return {
            "response_modalities": ["AUDIO"],
            "system_instruction": types.Content(parts=[types.Part(text=system_text)]),
            "tools": ToolRegistry(config).get_tools(),
            "input_audio_transcription": {},
            "output_audio_transcription": {},
            "realtime_input_config": {
                "automatic_activity_detection": {
                    "disabled": True,
                }
            },
        }

    @staticmethod
    def _extract_audio_from_part(part: Any) -> tuple[bytes, int]:
        inline_data = getattr(part, "inline_data", None)
        if inline_data is None:
            return b"", 24000

        mime_type = getattr(inline_data, "mime_type", "") or ""
        data = getattr(inline_data, "data", b"")
        if "audio/pcm" not in mime_type:
            return b"", 24000

        rate = 24000
        match = re.search(r"rate=(\d+)", mime_type)
        if match:
            rate = int(match.group(1))

        return GeminiLiveSession._ensure_bytes(data), rate

    @staticmethod
    def _ensure_bytes(data: Any) -> bytes:
        if isinstance(data, bytes):
            return data
        if isinstance(data, bytearray):
            return bytes(data)
        if isinstance(data, str):
            try:
                return base64.b64decode(data)
            except Exception:
                return data.encode("utf-8")
        return bytes(data)

    @staticmethod
    def _normalize_function_args(args: Any) -> dict[str, Any]:
        if args is None:
            return {}
        if isinstance(args, dict):
            return args
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return dict(args)

    def _notify_status(self, message: str) -> None:
        self._on_status(message)

    def _notify_connection(self, connected: bool) -> None:
        self._on_connection_change(connected)

