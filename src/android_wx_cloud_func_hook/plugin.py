from __future__ import annotations

import json
from typing import Any

from loguru import logger

from .types import RequestEvent, ResponseEvent


def lower_gateway_and_match_v3_config(response: ResponseEvent) -> dict[str, Any] | None:
    """提取网关 V3 配置并将响应体置空，以便触发 JS 侧降级。"""
    request = response.request
    if response.api != "operateWXData" or request is None or "tcbapi_get_service_info" not in request.body:
        return None

    try:
        response_dict = json.loads(response.body)
        response_data = json.loads(response_dict["data"])
        cloud_v3_response_config = json.loads(response_data["data"])

        request_dict = json.loads(request.body)
        cloud_v3_request_config = json.loads(request_dict["data"]["data"]["qbase_req"])

        logger.info(cloud_v3_response_config)
        logger.info(cloud_v3_request_config)

        full_config = {**cloud_v3_response_config, **cloud_v3_request_config}
        response.body = ""
        return full_config
    except Exception:
        return None


def parse_gateway_http_request(request: RequestEvent | None) -> dict[str, Any] | None:
    """解析 `tcbapi_call_gateway` 对应的 qbase 请求体。"""
    if request is None or request.api != "operateWXData":
        return None

    try:
        body_dict = json.loads(request.body)
        qbase_api_name = body_dict["data"]["data"].get("qbase_api_name")
        if qbase_api_name != "tcbapi_call_gateway":
            return None
        qbase_request = body_dict["data"]["data"]["qbase_req"]
        return json.loads(qbase_request)
    except Exception:
        return None


def parse_gateway_http_response(response: ResponseEvent) -> dict[str, dict[str, Any]] | None:
    """解析网关 HTTP 请求和响应，便于调试打印。"""
    parsed_request = parse_gateway_http_request(response.request)
    if parsed_request is None:
        return None

    try:
        response_dict = json.loads(response.body)
        response_data = json.loads(response_dict["data"])
        return {
            "request": parsed_request,
            "response": response_data,
        }
    except Exception:
        return None
