"""Custom middleware for the uptime monitor."""
import uuid

import structlog

logger = structlog.get_logger(__name__)


class RequestIDMiddleware:
    """Adds a unique request ID to each request and response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response
