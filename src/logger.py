import logging
import sys
from datetime import datetime, timezone
import json


class StructuredFormatter(logging.Formatter):
    """
    Lightweight structured logging formatter.
    Outputs JSON formatted strings containing log level, timestamp, message,
    and any extra parameters passed to logging.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        standard_attrs = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                log_data[key] = value
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configures the root logger to output structured JSON logs to standard output
    and light text logs to a local file.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(stdout_handler)
    try:
        file_handler = logging.FileHandler("app.log", encoding="utf-8")
        file_formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not set up file logging to app.log: {e}")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
