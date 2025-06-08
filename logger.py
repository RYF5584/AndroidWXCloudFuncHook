from pathlib import Path
from loguru import logger
import sys

BASE_DIR = Path('logs')
BASE_DIR.mkdir(exist_ok=True)

logger.remove(0)

logger.add(
    sys.stdout,
    colorize=True,
    format='<green>{time}</green> <yellow>{file}</yellow>:<yellow>{line}</yellow> <level>{level}</level> <cyan>{message}</cyan>',
    level='INFO',
)


logger.add(
    BASE_DIR / 'All.log',
)
logger.add(
    BASE_DIR / 'Request.log',
    filter=lambda record: record["extra"].get("name") == "Request"
)
logger.add(
    BASE_DIR / 'Response.log',
    filter=lambda record: record["extra"].get("name") == "Response"
)

logger.add(
    BASE_DIR / 'Other.log',
    filter=lambda record: record["extra"].get("name") == "Other"
)


request_loger = logger.bind(name="Request")
response_logger = logger.bind(name="Response")
other_logger = logger.bind(name="Other")
