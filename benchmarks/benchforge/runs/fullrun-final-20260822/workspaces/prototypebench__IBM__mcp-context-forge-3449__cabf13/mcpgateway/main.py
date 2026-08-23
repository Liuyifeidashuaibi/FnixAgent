from fastapi import Request, status
from fastapi.responses import ORJSONResponse
from .models import PluginViolation, PluginViolationError
from .plugins.framework.constants import PLUGIN_VIOLATION_CODE_MAPPING

async def plugin_violation_exception_handler(_request: Request, exc: PluginViolationError):
    # Determine HTTP status: explicit → mapping → default 200
    http_status = exc.violation.http_status_code if exc.violation and exc.violation.http_status_code else None
    if not http_status:
        http_status = PLUGIN_VIOLATION_CODE_MAPPING.get(exc.violation.code, 200)

    # Add custom headers if provided
    headers = exc.violation.http_headers if exc.violation and exc.violation.http_headers else None
    response = ORJSONResponse(status_code=http_status, content={...})
    if headers:
        response.headers.update(headers)
    return response