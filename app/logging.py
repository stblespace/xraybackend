import json
import logging
import sys
from typing import Any, Dict


class JsonLogFormatter(logging.Formatter):
    """
    Minimal JSON log formatter to keep logs structured and machine-friendly.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info

        for key, value in record.__dict__.items():
            if key.startswith("_") or key in payload:
                continue
            # Only include JSON-serializable extras; ignore anything else.
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = str(value)

        return json.dumps(payload, ensure_ascii=True)


def configure_logging(log_level: str) -> None:
    """
    Configure root and uvicorn loggers for structured output.
    """

    level = getattr(logging, log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())

    root_logger = logging.getLogger()
    for existing in list(root_logger.handlers):
        root_logger.removeHandler(existing)

    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "grpc"):
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.handlers = [handler]
