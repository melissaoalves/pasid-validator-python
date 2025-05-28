import logging
import os
from datetime import datetime

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

current_time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
LOG_FILENAME = os.path.join(LOG_DIR, f"experiment_{current_time_str}.log")

log_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(threadName)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

file_handler = logging.FileHandler(LOG_FILENAME, mode='w')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.DEBUG)


console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)


logging.basicConfig(
    level=logging.DEBUG,
    handlers=[file_handler, console_handler]
)

def get_logger(name):
    """Retorna uma instância de logger com o nome fornecido."""
    return logging.getLogger(name)
