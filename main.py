# @Author: Ruan
import json
import frida
import sys
import os
from loguru import logger
import _types
import subprocess

subprocess.getoutput("adb forward tcp:27042 tcp:27042")
subprocess.getoutput("adb forward tcp:27043 tcp:27043")
logger_red = logger.bind()
logger_red.remove()  # 移除默认的日志配置
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | - <level>{message}</level>",
    level="DEBUG"
)
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


def handle_response(response: _types.Response):
    try:
        data = json.loads(response.data)
    except:
        pass


def on_message(message: dict, *args, **kwargs):
    """
        HOOK结果回调函数,需要自定义解析,请修改该函数
    """
    if message.get("type") != "send" or not message.get("payload"):
        logger.error(message)
        return
    try:
        payload = _types.JsSendRequest.parse_obj(message.get("payload"))
        if payload.type == _types.Request:
            logger_red.info(payload)
        elif payload.type == _types.Response:
            logger.info(payload)
        else:
            logger.info(payload)
    except:
        logger.error(message.get("payload"))


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
