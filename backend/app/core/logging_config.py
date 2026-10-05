"""Structured JSON logging. Every execution-related log line carries
request_id / job_id / server_id / tool / task / status so operators can grep
and correlate across a distributed run. Secrets are redacted defensively."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

SECRET_PATTERNS = [
    re.compile(r"(?i)(password\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(secret[_-]?key\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(aws_secret_access_key\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(token\s*[:=]\s*)(\S+)"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+PRIVATE KEY-----"),
]


def redact(text: str) -> str:
    out = text
    for pattern in SECRET_PATTERNS:
        out = pattern.sub(lambda m: (m.group(1) + "[REDACTED]") if m.groups() else "[REDACTED-KEY]", out)
    return out


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for key in ("request_id", "job_id", "server_id", "tool", "task", "status", "user_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class LogContext:
    """Attach structured context fields to every log call inside the `with` block."""

    def __init__(self, logger: logging.Logger, **fields):
        self.logger = logger
        self.fields = fields
        self._old_factory = None

    def __enter__(self):
        old_factory = logging.getLogRecordFactory()
        fields = self.fields
        self._old_factory = old_factory

        def factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for k, v in fields.items():
                setattr(record, k, v)
            return record

        logging.setLogRecordFactory(factory)
        return self.logger

    def __exit__(self, *exc):
        logging.setLogRecordFactory(self._old_factory)
