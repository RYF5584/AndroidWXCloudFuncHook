from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeAlias

import frida
import frida_legacy_compat  # noqa: F401
frida_legacy_compat.patch_frida()
from loguru import logger

from .types import RequestEvent, ResponseEvent

HookTarget: TypeAlias = int | Any

WECHAT_PROCESS_PATTERN = re.compile(r"^com.tencent.mm:appbrand\d+$")
WECHAT_PROCESS_ALIASES = {"微信", "WeChat"}


def is_target_process_name(process_name: str) -> bool:
    return process_name in WECHAT_PROCESS_ALIASES or WECHAT_PROCESS_PATTERN.fullmatch(process_name) is not None


def pretty_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)

    text = value.strip()
    if not text:
        return ""

    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except Exception:
        return value


def escape_loguru_markup(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("<", "\\<")


def render_block(title: str, content: str) -> str:
    body = content if content else "(empty)"
    return f"{title}\n{escape_loguru_markup(body)}"


def field(value: Any) -> str:
    return escape_loguru_markup(value)


def parse_json_text(value: Any) -> Any | None:
    if not isinstance(value, str):
        return value if isinstance(value, (dict, list)) else None
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def dump_json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

RequestPatchLike: TypeAlias = RequestEvent | dict[str, Any] | None
ResponsePatchLike: TypeAlias = ResponseEvent | dict[str, Any] | None
RequestCallback: TypeAlias = Callable[[RequestEvent], RequestPatchLike]
ResponseCallback: TypeAlias = Callable[[ResponseEvent], ResponsePatchLike]


class AndroidWXCloudFuncHook:
    def __init__(
        self,
        device: Any | None = None,
    ):
        self.device = device if device is not None else frida.get_usb_device()
        self.package_dir = Path(__file__).resolve().parent
        self.script_path = self.package_dir / "js" / "native.js"
        self._sessions: dict[int, Any] = {}
        self._scripts: dict[int, Any] = {}
        self._process_names: dict[int, str] = {}
        self._request_cache: dict[int, dict[int, RequestEvent]] = {}
        self._request_callback: RequestCallback | None = None
        self._response_callback: ResponseCallback | None = None
        self._script_source = ""
        self._session_lock = threading.RLock()
        self._auto_attach_stop = threading.Event()
        self._auto_attach_thread: threading.Thread | None = None

    def _log_frida(self, level: str, message: str, *, colors: bool = True) -> None:
        target = logger.opt(colors=colors)
        getattr(target, level)(message)

    def _log_traffic(self, _level: str, _message: str, *, _colors: bool = True) -> None:
        return None

    def _force_hook_started_log(self, pid: int) -> None:
        self._log_frida("success", f"<green><bold>[HookReady]</bold></green> PID:{field(pid)}")

    def _process_name(self, pid: int) -> str:
        return self._process_names.get(pid, "")

    def _remember_request(self, pid: int, request: RequestEvent) -> None:
        if request.id > 0:
            self._request_cache.setdefault(pid, {})[request.id] = request

    def _pop_cached_request(self, pid: int, request_id: int) -> RequestEvent | None:
        cache = self._request_cache.get(pid)
        if not cache or request_id <= 0:
            return None
        return cache.pop(request_id, None)

    def _clear_request_cache(self, pid: int) -> None:
        self._request_cache.pop(pid, None)

    def _apply_request_patch_to_event(self, request: RequestEvent, patch: dict[str, Any]) -> None:
        if "api" in patch:
            request.api = str(patch["api"])
        if "body" in patch:
            request.body = str(patch["body"])

    def _apply_response_patch_to_event(self, response: ResponseEvent, patch: dict[str, Any]) -> None:
        if "body" in patch:
            response.body = str(patch["body"])

    def _enumerate_all_processes(self) -> list[Any]:
        return list(self.device.enumerate_processes())

    def _enumerate_target_processes(self) -> list[Any]:
        return [process for process in self._enumerate_all_processes() if is_target_process_name(process.name)]

    def get_frontmost_application(self) -> Any:
        front_app = self.device.get_frontmost_application()
        self._log_frida("info", "<blue><bold>STATUS</bold></blue> " + f"FrontApp:{field(front_app)}")
        return front_app

    def get_wechat_processes(self) -> list[Any]:
        front_app = self.get_frontmost_application()
        self._log_frida(
            "info",
            "<blue><bold>STATUS</bold></blue> " + f"CurrentFrontPid:{field(getattr(front_app, 'pid', ''))}",
        )

        processes = self._enumerate_all_processes()

        matched = [process for process in processes if is_target_process_name(process.name)]
        for process in matched:
            self._process_names[process.pid] = process.name
            self._log_frida(
                "success",
                "<green><bold>MATCHED</bold></green> " + f"PID:{field(process.pid)} | Name:{field(process.name)}" + "| 等待启动Hook中...",
            )
        return matched

    def start_hook(
        self,
        targets: Sequence[HookTarget] | HookTarget,
        on_request: RequestCallback | None = None,
        on_response: ResponseCallback | None = None,
        auto_attach_new_processes: bool = True,
        process_poll_interval: float = 1.0,
    ) -> list[Any]:
        self._request_callback = on_request
        self._response_callback = on_response
        self._script_source = self.script_path.read_text(encoding="utf-8")

        loaded_scripts: list[Any] = []
        for target in self._normalize_targets(targets):
            pid = self._resolve_pid(target)
            name = getattr(target, "name", None)
            script = self._attach_pid(pid, name)
            if script is not None:
                loaded_scripts.append(script)

        if auto_attach_new_processes:
            self._start_auto_attach_monitor(process_poll_interval)

        self._log_frida(
            "success",
            "<green><bold>HOOK READY</bold></green> "
            + f"Targets:{field(len(loaded_scripts))} | AutoAttach:{field(auto_attach_new_processes)}",
        )
        return loaded_scripts

    def sync_wechat_processes(self) -> None:
        if not self._script_source:
            return
        try:
            matched = self._enumerate_target_processes()
            alive = {process.pid: process.name for process in matched}
            for pid, name in alive.items():
                self._process_names[pid] = name
                self._attach_pid(pid, name)
            self._cleanup_stale_sessions(set(alive))
        except Exception as exc:
            self._log_frida(
                "error",
                "<red><bold>AUTO-ATTACH-ERROR</bold></red>\n" + render_block("detail:", pretty_text(str(exc))),
            )

    def stop_hook(self, targets: Sequence[HookTarget] | HookTarget | None = None) -> None:
        if targets is None:
            self._stop_auto_attach_monitor()
            target_pids = list(self._sessions.keys())
        else:
            target_pids = [self._resolve_pid(target) for target in self._normalize_targets(targets)]

        for pid in target_pids:
            self._detach_pid(pid, reason="manual-stop")

    def close(self) -> None:
        self.stop_hook()

    def _normalize_targets(self, targets: Sequence[HookTarget] | HookTarget) -> list[HookTarget]:
        if isinstance(targets, Sequence) and not isinstance(targets, (str, bytes, bytearray)):
            return list(targets)
        return [targets]

    def _resolve_pid(self, target: HookTarget) -> int:
        if isinstance(target, int):
            return target
        pid = getattr(target, "pid", None)
        if isinstance(pid, int):
            return pid
        raise TypeError(f"Unsupported hook target: {target!r}")

    def _attach_pid(self, pid: int, process_name: str | None = None) -> Any | None:
        with self._session_lock:
            if pid in self._sessions:
                return None
            if not self._script_source:
                raise RuntimeError("Script source not loaded.")

        session = None
        try:
            session = self.device.attach(pid)
            script = session.create_script(self._script_source)
            script.on("message", lambda message, data=None, current_pid=pid: self._on_message(current_pid, message, data))
            session.on("detached", lambda *args, current_pid=pid: self._on_session_detached(current_pid, *args))
            script.load()
            with self._session_lock:
                self._sessions[pid] = session
                self._scripts[pid] = script
                if process_name:
                    self._process_names[pid] = process_name
            self._log_frida(
                "info",
                "<blue><bold>ATTACH</bold></blue> " + f"PID:{field(pid)} | Name:{field(process_name or self._process_name(pid))}",
            )
            return script
        except Exception as exc:
            if session is not None:
                try:
                    session.detach()
                except Exception:
                    pass
            self._log_frida(
                "error",
                "<red><bold>ATTACH-ERROR</bold></red> "
                + f"PID:{field(pid)} | Name:{field(process_name or self._process_name(pid))}\n"
                + render_block("detail:", pretty_text(str(exc))),
            )
            return None

    def _detach_pid(self, pid: int, reason: str = "detach") -> None:
        with self._session_lock:
            script = self._scripts.pop(pid, None)
            session = self._sessions.pop(pid, None)
            process_name = self._process_names.get(pid, "")
            self._clear_request_cache(pid)
        if script is not None:
            try:
                script.unload()
            except Exception:
                pass
        if session is not None:
            try:
                session.detach()
            except Exception:
                pass
        self._log_frida(
            "info",
            "<blue><bold>DETACH</bold></blue> " + f"PID:{field(pid)} | Name:{field(process_name)} | Reason:{field(reason)}",
        )

    def _cleanup_stale_sessions(self, alive_pids: set[int]) -> None:
        with self._session_lock:
            stale_pids = [pid for pid in self._sessions if pid not in alive_pids]
        for pid in stale_pids:
            self._detach_pid(pid, reason="process-exit")

    def _on_session_detached(self, pid: int, *args: Any) -> None:
        reason = args[0] if args else "detached"
        with self._session_lock:
            had_session = pid in self._sessions or pid in self._scripts
            self._sessions.pop(pid, None)
            self._scripts.pop(pid, None)
            process_name = self._process_names.get(pid, "")
            self._clear_request_cache(pid)
        if had_session:
            self._log_frida(
                "warning",
                "<yellow><bold>DETACHED</bold></yellow> "
                + f"PID:{field(pid)} | Name:{field(process_name)} | Reason:{field(reason)}",
            )

    def _start_auto_attach_monitor(self, process_poll_interval: float) -> None:
        if self._auto_attach_thread is not None and self._auto_attach_thread.is_alive():
            return
        self._auto_attach_stop.clear()
        interval = max(0.5, float(process_poll_interval))
        self._auto_attach_thread = threading.Thread(
            target=self._auto_attach_loop,
            args=(interval,),
            daemon=True,
            name="wechat-auto-attach",
        )
        self._auto_attach_thread.start()
        self._log_frida(
            "info",
            "<blue><bold>STATUS</bold></blue> " + f"AutoAttachMonitor started, interval={field(interval)}s",
        )

    def _stop_auto_attach_monitor(self) -> None:
        thread = self._auto_attach_thread
        if thread is None:
            return
        self._auto_attach_stop.set()
        if thread.is_alive():
            thread.join(timeout=2.0)
        self._auto_attach_thread = None
        self._log_frida("info", "<blue><bold>STATUS</bold></blue> AutoAttachMonitor stopped")

    def _auto_attach_loop(self, interval: float) -> None:
        while not self._auto_attach_stop.wait(interval):
            self.sync_wechat_processes()

    def _build_request_event(self, payload: dict[str, Any]) -> RequestEvent:
        body = str(payload.get("body") or "")
        return RequestEvent(
            id=int(payload.get("id") or 0),
            api=str(payload.get("api") or ""),
            body=body,
            meta_body=str(payload.get("meta_body") or body),
        )

    def _build_response_event(self, pid: int, payload: dict[str, Any]) -> ResponseEvent:
        request_id = int(payload.get("id") or 0)
        body = str(payload.get("body") or "")
        return ResponseEvent(
            id=request_id,
            body=body,
            meta_body=str(payload.get("meta_body") or body),
            request=self._pop_cached_request(pid, request_id),
        )

    def _diff_patch(
        self,
        original: dict[str, Any],
        current: dict[str, Any],
        *,
        keys: tuple[str, ...],
    ) -> dict[str, Any] | None:
        patch = {key: current[key] for key in keys if current.get(key) != original.get(key)}
        return patch or None

    def _normalize_request_patch(
        self,
        result: RequestPatchLike,
        request: RequestEvent,
        original_patch: dict[str, Any],
    ) -> dict[str, Any] | None:
        candidate: object = result
        if candidate is None:
            return self._diff_patch(original_patch, request.to_patch(), keys=("api", "body"))
        if isinstance(candidate, RequestEvent):
            return self._diff_patch(original_patch, candidate.to_patch(), keys=("api", "body"))
        if isinstance(candidate, dict):
            self._apply_request_patch_to_event(request, candidate)
            return {
                key: value
                for key, value in {"api": request.api, "body": request.body}.items()
                if key in candidate
            } or None
        raise TypeError("on_request callback must return RequestEvent, dict or None")

    def _normalize_response_patch(
        self,
        result: ResponsePatchLike,
        response: ResponseEvent,
        original_patch: dict[str, Any],
    ) -> dict[str, Any] | None:
        candidate: object = result
        if candidate is None:
            return self._diff_patch(original_patch, response.to_patch(), keys=("body",))
        if isinstance(candidate, ResponseEvent):
            return self._diff_patch(original_patch, candidate.to_patch(), keys=("body",))
        if isinstance(candidate, dict):
            self._apply_response_patch_to_event(response, candidate)
            return {"body": response.body} if "body" in candidate else None
        raise TypeError("on_response callback must return ResponseEvent, dict or None")

    def _invoke_request_callback(self, pid: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        request = self._build_request_event(payload)
        if self._request_callback is None:
            self._remember_request(pid, request)
            return None
        original_patch = request.to_patch()
        try:
            result = self._request_callback(request)
            patch = self._normalize_request_patch(result, request, original_patch)
            self._remember_request(pid, result if isinstance(result, RequestEvent) else request)
            return patch
        except Exception as exc:
            self._log_frida("exception", f"CallbackError Type:{field('req')} | Message:{field(exc)}", colors=False)
            self._remember_request(pid, request)
            return None

    def _invoke_response_callback(self, pid: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        response = self._build_response_event(pid, payload)
        if self._response_callback is None:
            return None
        original_patch = response.to_patch()
        try:
            result = self._response_callback(response)
            return self._normalize_response_patch(result, response, original_patch)
        except Exception as exc:
            self._log_frida("exception", f"CallbackError Type:{field('resp')} | Message:{field(exc)}", colors=False)
            return None

    def _reply_patch(self, pid: int, reply_type: str, patch: dict[str, Any] | None) -> None:
        with self._session_lock:
            script = self._scripts.get(pid)
        if script is not None:
            script.post({"type": reply_type, "payload": patch or {}})

    def _log_structured_payload(self, payload: dict[str, Any], pid: int | None = None) -> None:
        flow = str(payload.get("flow") or "")
        ts = payload.get("ts", "")
        prefix = field(f"[{ts}] ") if ts else ""

        if flow == "req":
            self._log_traffic(
                "info",
                prefix
                + "<cyan><bold>REQ</bold></cyan> "
                + f"ID:{field(payload.get('id'))} | API:{field(payload.get('api'))}\n"
                + render_block("body:", pretty_text(payload.get("body")))
                + "\n"
                + render_block("meta_body:", pretty_text(payload.get("meta_body"))),
            )
            return

        if flow == "resp":
            self._log_traffic(
                "success" if payload.get("id") else "warning",
                prefix
                + ("<green><bold>RESP</bold></green> " if payload.get("id") else "<yellow><bold>RESP</bold></yellow> ")
                + f"ID:{field(payload.get('id'))}\n"
                + render_block("body:", pretty_text(payload.get("body")))
                + "\n"
                + render_block("meta_body:", pretty_text(payload.get("meta_body"))),
            )
            return

        if flow == "status":
            message = str(payload.get("message", ""))
            if message.startswith("Hooks installed:"):
                self._force_hook_started_log(pid or 0)
                return
            self._log_frida("info", prefix + "<blue><bold>STATUS</bold></blue> " + field(message))
            return

        if flow == "error":
            self._log_frida(
                "error",
                prefix
                + "<red><bold>HOOK-ERROR</bold></red> "
                + f"Stage:{field(payload.get('stage'))} | Message:{field(payload.get('message'))}\n"
                + render_block("detail:", pretty_text(payload.get("detail"))),
            )
            return

        self._log_traffic("info", prefix + pretty_text(payload), colors=False)

    def _on_message(self, pid: int, message: dict[str, Any], _data: Any | None = None) -> None:
        if message.get("type") == "error":
            self._log_frida(
                "error",
                "<red><bold>FRIDA-ERROR</bold></red> "
                + f"PID:{field(pid)} | Name:{field(self._process_name(pid))}\n"
                + escape_loguru_markup(pretty_text(message.get("stack") or message)),
            )
            return

        if message.get("type") != "send" or not message.get("payload"):
            self._log_frida("warning", pretty_text(message), colors=False)
            return

        payload = message["payload"]
        if isinstance(payload, dict):
            if payload.get("awaitPatch"):
                flow = str(payload.get("flow"))
                patch = self._invoke_request_callback(pid, payload) if flow == "req" else self._invoke_response_callback(pid, payload)
                self._reply_patch(pid, str(payload.get("replyType")), patch)
                return
            self._log_structured_payload(payload, pid)
            return

        self._log_frida("info", field(payload), colors=False)

    def __enter__(self) -> "AndroidWXCloudFuncHook":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
