from pydantic import BaseModel, Optional

class PluginViolation(BaseModel):
    # ... existing fields ...
    http_status_code: Optional[int] = None  # NEW: Explicit HTTP status
    http_headers: Optional[dict[str, str]] = None  # NEW: Custom headers (e.g., Retry-After)