"""Logging + optional LangSmith tracing setup."""
from __future__ import annotations

import logging
import os

from pythonjsonlogger import json as jsonlogger

from core.config import get_settings


def setup_observability() -> None:
    """Configure structured logging and wire up LangSmith if enabled."""
    settings = get_settings()

    handler = logging.StreamHandler()
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "ts", "levelname": "level"},
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # LangSmith reads these env vars; setting them enables graph tracing.
    if settings.langsmith_tracing and settings.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        logging.getLogger(__name__).info("LangSmith tracing enabled")
