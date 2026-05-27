import json
import sys
from pathlib import Path

from loguru import logger

from .client import AndroidWXCloudFuncHook
from .plugin import lower_gateway_and_match_v3_config, parse_gateway_http_response
from .types import RequestEvent, ResponseEvent

LOG_DIR_PATH = Path("logs")
LOG_DIR_PATH.mkdir(exist_ok=True)

logger.remove()
logger.add(sys.stdout, level="INFO")
logger.add(LOG_DIR_PATH.joinpath("example.log").as_posix(), level="INFO")


def on_request(_request: RequestEvent) -> None:
    """请求回调；通过修改 `_request.body` 可重写请求。"""
    return None


def on_response(_response: ResponseEvent) -> None:
    """响应回调；通过修改 `_response.body` 可重写响应。"""
    gateway_v3_full_config = lower_gateway_and_match_v3_config(_response)
    if gateway_v3_full_config:
        logger.success(
            "降级云网关成功 => 获取到网关 V3 配置信息:\n{}",
            json.dumps(gateway_v3_full_config, indent=2, ensure_ascii=False),
        )
        return None

    gateway_http_req_and_resp = parse_gateway_http_response(_response)
    if gateway_http_req_and_resp:
        req = gateway_http_req_and_resp["request"]
        resp = gateway_http_req_and_resp["response"]
        logger.info(
            "\n--------GateWay[Req:{}]--------\n{}\n--GateWay[Resp:{}]--\n{}\n--------GateWay[End:{}]--------",
            _response.id,
            json.dumps(req, indent=2, ensure_ascii=False),
            _response.id,
            json.dumps(resp, indent=2, ensure_ascii=False),
            _response.id,
        )


def run() -> None:
    with AndroidWXCloudFuncHook(device=None) as hook:
        processes = hook.get_wechat_processes()
        if not processes:
            print("没有找到微信进程，请先打开微信小程序。")
            return

        hook.start_hook(
            processes,
            on_request=on_request,
            on_response=on_response,
            auto_attach_new_processes=True,
            process_poll_interval=1.0,
        )
        logger.success("Hook 已启动，去触发一次小程序请求/点击右上角重新进入小程序；按 Ctrl+C 结束。")
        logger.warning("如果触发请求后 5 到 10 秒仍无日志，请检查小程序是否真的发起了请求。")
        sys.stdin.read()
