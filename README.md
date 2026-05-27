# AndroidWXCloudFuncHook

[![Repository](https://img.shields.io/badge/Repository-GitHub-181717?logo=github)](https://github.com/RYF5584/AndroidWXCloudFuncHook)
[![PyPI Version](https://img.shields.io/pypi/v/android-wx-cloud-func-hook)](https://pypi.org/project/android-wx-cloud-func-hook/)

`android_wx_cloud_func_hook` 是一个面向微信 Android 小程序云请求分析的 Frida Hook 库，重点覆盖 `operateWXData`、`qbase_commapi`、`tcbapi_call_gateway` 等链路，并支持请求/响应回调改写。

## 通过 [frida-legacy-compat](https://github.com/RYF5584/frida-legacy-compat) 实现 Frida 17 新版 API 兼容。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=RYF5584/AndroidWXCloudFuncHook&type=Date)](https://star-history.com/#RYF5584/AndroidWXCloudFuncHook&Date)

## 一、微信云函数 / 云网关简介与当前研究结论

这里说的“微信云函数”并不只指单独的云函数能力，而是把以下几类能力统称为云函数体系：

- 云网关
- 云托管
- 云函数

很多小程序请求并不是普通 HTTP 请求，而是基于微信云网关 / 云函数 / 云托管完成。此类请求直接用常规抓包软件通常抓不到，因为底层往往通过微信自己的 `Mmtls` 链路发包。根据当前研究，常见云请求大致有以下几种：

1. 基于微信 `Mmtls` 协议，通过 `OperateWxData` 接口发包
   - 在 PC 小程序逆向中也能看到该函数
   - 该链路通过小程序进程与微信进程通信，最终走微信私有链路发包
2. 基于 `HTTP/2` 的鉴权模式
   - 常见于部分微信小程序
   - 一般流程如下：
     1. 通过 `OperateWxData` 的 `qbase_commit` 中的 `tcbapi_get_service_info` 获取加密参数与鉴权 Token
     2. 使用获取到的 key 和 token 对请求体进行加密并压缩
     3. 当前观察到压缩常见为 `snappy`，数据格式一般为 `ProtoBuf` 或 `JSON`
     4. 服务端收到后再用 key 解密，当前常见解密算法为 `AES-CBC`
3. 不鉴权的 `HTTP/2` 模式
   - 通常见于使用了微信云托管 / 云网关，但不在小程序内、而是独立网站的场景
   - key 和 token 仍通过微信链路获取，后续请求的编解码流程与上面的鉴权模式类似
4. 基于 HTTP 明文的请求
   - 常见于部分其他 App 的微信云网关接入
   - 这类请求往往需要带 `Socks` 的抓包软件才能看到
   - 请求头中通常会带上 `x-wx-auth-code` 和 `x-wx-call-id`
   - 这两个值由 URL 和 Body 共同计算，用于合法性校验
5. 2025 年 8 月以后，腾讯云网关 SDK 更新后，明文请求已经越来越少
   - 趋势逐渐转向 V3 加密版纯二进制实现
6. V3 算法通常通过 `tcbapi_get_service_info` 返回的 `key` / `kx` / `token` 完成请求编解码
   - 具体实现当前暂不开源

## 二、这个项目可以做什么

1. 提供可直接调用的 PyPI 库，对小程序 Native 层主要链路进行 Frida Hook，抓取大部分 API 的请求和响应
2. 通过修改 `operateWXData` 接口，实现对云网关 V3 的降级，让其改走 `Mmtls` 层面的云网关，方便抓包
3. 当 `operateWXData` 中的 `get_service_info` 触发特定异常时，可自动降级为第一种 `Mmtls` 模式，便于进一步定位和抓包
4. 相关辅助逻辑可直接参考 [plugin.py](./src/android_wx_cloud_func_hook/plugin.py)

## Features

- 自动枚举并附加微信主进程和 `appbrand` 相关进程
- 自动补挂新出现的 `com.tencent.mm:appbrandX` 进程
- 提供 `RequestEvent` / `ResponseEvent` 事件模型
- 支持在 Python 回调中重写请求体和响应体
- 将 `js/native.js` 作为包资源一起分发
- 内置 `example.run()`，安装后可直接导入运行示例

## Installation

从 PyPI 安装：

```bash
pip install android-wx-cloud-func-hook
```

如果你使用 `uv`：

```bash
uv add android-wx-cloud-func-hook
```

## Quick Start

### 安装后可以直接运行包内示例：

```python
from android_wx_cloud_func_hook import example

example.run()
```

### example代码的原理如下
```python
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

```

### 如果你想自定义回调，并重写请求和响应，可以直接使用核心类：

```python
from android_wx_cloud_func_hook import AndroidWXCloudFuncHook, RequestEvent, ResponseEvent


def on_request(request: RequestEvent) -> None:
    if "tcbapi_call_gateway" in request.body:
        print("matched request", request.id)
        request.body = "重写请求体"


def on_response(response: ResponseEvent) -> None:
    if response.request is not None:
        print("matched response", response.id, response.request.api)
        response.body = "重写响应体，可以实现重写降级后的网关 HTTP 响应以及 WxJS 中的其他 API 响应"


with AndroidWXCloudFuncHook() as hook:
    processes = hook.get_wechat_processes()
    if not processes:
        raise SystemExit("没有找到微信相关进程")

    hook.start_hook(
        processes,
        on_request=on_request,
        on_response=on_response,
        auto_attach_new_processes=True,
    )

    input("Hook 已启动，按回车退出...")
```

## Package API

### `AndroidWXCloudFuncHook`

- 负责枚举进程、附加 Frida、自动补挂新进程、接收消息并回传补丁

### `RequestEvent`

- `id`: 请求唯一 ID
- `api`: JSAPI 名称，可改写
- `body`: 当前请求体，可改写
- `meta_body`: 原始请求体快照，只读语义

### `ResponseEvent`

- `id`: 响应唯一 ID
- `body`: 当前响应体，可改写
- `meta_body`: 原始响应体快照，只读语义
- `request`: 匹配到的请求对象，没有命中时为 `None`

### `example.run()`

- 包内自带的最小可运行示例
- 适合快速验证设备、Frida 环境和微信小程序链路是否已命中


