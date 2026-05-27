from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RequestEvent:
    """请求事件；可通过修改 `body` / `api` 回写请求。"""

    id: int = field(metadata={"doc": "请求唯一 ID，可与响应 ID 对应"})
    api: str = field(metadata={"doc": "JSAPI 名称，可被回调改写"})
    body: str = field(metadata={"doc": "当前请求体，可被回调改写"})
    meta_body: str = field(metadata={"doc": "原始请求体快照，只读，用于修改前后对照"})

    def to_patch(self) -> dict[str, Any]:
        return {"api": self.api, "body": self.body}


@dataclass(slots=True)
class ResponseEvent:
    """响应事件；可通过修改 `body` 回写响应。"""

    id: int = field(metadata={"doc": "响应唯一 ID，可与请求 ID 对应"})
    body: str = field(metadata={"doc": "当前响应体，可被回调改写"})
    meta_body: str = field(metadata={"doc": "原始响应体快照，只读，用于修改前后对照"})
    request: RequestEvent | None

    @property
    def api(self) -> str:
        """返回该响应对应请求的 API 名称。"""
        return self.request.api if self.request else "unknown"

    def to_patch(self) -> dict[str, Any]:
        return {"body": self.body}


__all__ = ["RequestEvent", "ResponseEvent"]
