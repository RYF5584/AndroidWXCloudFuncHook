# @Author: Ruan
import json
import frida
import sys
import os
from logger import (
    logger,
    request_loger,
    response_logger,
    other_logger
)
import _types
import subprocess

USB = True
if not USB:
    HOST = '127.0.0.1'
    PORT = 27042
    DEVICE_ADDR = input('请输入ADB设备Host:').strip()
    FRIDA_SERVER_ADDRESS = f'{HOST}:{PORT}'

    subprocess.getoutput(f"adb connect {DEVICE_ADDR}")
    subprocess.getoutput(f"adb forward tcp:{PORT} tcp:{PORT}")

    device = frida.get_device_manager().add_remote_device(
        FRIDA_SERVER_ADDRESS,
    )
else:
    device = frida.get_usb_device()
front_app = device.get_frontmost_application()
app_name = front_app.pid
logger.info(f'当前前台应用:{front_app}')
BASE_DIR = os.path.dirname(__file__)


def attach_start(pid: int):
    global script
    session = device.attach(pid)
    with open(os.path.join(BASE_DIR, 'js', 'native.js'), encoding='utf-8') as file:
        script = session.create_script(file.read())
    script.on('message', on_message)
    script.load()





def on_message(message: dict, *args, **kwargs):
    """
        HOOK结果回调函数,需要自定义解析,请修改该函数
    """
    if message.get("type") != "send" or not message.get("payload"):
        other_logger.error(message)
        return
    try:
        payload = _types.JsSendRequest.model_validate(message.get("payload"))
        if payload.type == _types.JsSendType.Request:
            request_loger.info(f'请求 ==> 请求Api:{payload.data.api_name} | 参数:{payload.data.data}')
            if payload.data.api_name == 'operateWXData':
                print(f'-------微信云操作接口-------\n')
                print(json.dumps(
                    json.loads(payload.data.data),
                    indent=4
                ))
                # 这里打印格式化后的接口参数,具体实现可以自己修改逻辑
                # Demo打印QBaseReq
                req_dict = json.loads(payload.data.data)
                req_data = req_dict.get("data", {})
                if req_data.get('api_name') == 'qbase_commapi':
                    common_api_data = req_data.get("data")
                    qbase_api_name = common_api_data.get('api_name')
                    qbase_req = common_api_data.get('qbase_req')
                    qbase_req_dict = json.loads(qbase_req)
                    method = qbase_req_dict["method"].upper()
                    headers_list = qbase_req_dict['headers']
                    headers_dict = {item["k"]: item["v"] for item in headers_list}
                    path = headers_dict.get('X-WX-HTTP-PATH')
                    print(f'----GateWayReq----\n')
                    print(method, path)
                    print(json.dumps(headers_dict, indent=4))
                    if method == 'POST':
                        data = qbase_req_dict['data']
                        print('\n\n')
                        print(data)
                    print(f'----GateWayEnd----\n')
                print(f'-----------End-----------\n')
        elif payload.type == _types.JsSendType.Response:
            response_logger.warning(f'响应 ==> {payload.data}')
        else:
            other_logger.info(payload.data)
    except:
        other_logger.error(message.get("payload"))


processes = device.enumerate_processes()
target_processes = [
    process for process in processes if
    any(keyword in process.name for keyword in ['微信', 'tencent.mm'])
]
for process in target_processes:
    try:
        logger.info(f"Attaching to PID: {process.pid}, Name: {process.name}")
        attach_start(process.pid)
    except Exception as e:
        logger.error(f"Error attaching to PID {process.pid}: {e}")

logger.info('py-Hook Start...')
sys.stdin.read()
