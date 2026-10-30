import json
import logging
import sys

_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "service": self.service,
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
        }
        # Campos passados em extra=..., como trace_id e conversation_id
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS:
                line[key] = str(value)
        if record.exc_info:
            line["error"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False)


def configure_logging(service: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
