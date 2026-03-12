from __future__ import annotations

import logging

from app.core.request_context import get_request_id

_LOGGING_CONFIGURED = False


class RequestIdLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        request_id = get_request_id() or "-"
        if not hasattr(record, "request_id"):
            record.request_id = request_id
        return True


def configure_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
        )

    request_id_filter = RequestIdLogFilter()
    root_logger.addFilter(request_id_filter)
    for handler in root_logger.handlers:
        handler.addFilter(request_id_filter)
    _LOGGING_CONFIGURED = True
