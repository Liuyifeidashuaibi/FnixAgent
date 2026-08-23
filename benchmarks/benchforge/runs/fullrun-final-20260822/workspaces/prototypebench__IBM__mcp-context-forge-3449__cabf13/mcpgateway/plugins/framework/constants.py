PLUGIN_VIOLATION_CODE_MAPPING = {
    "RATE_LIMIT": 429,              # Rate limiting
    "INVALID_URI": 400,             # Bad request
    "PROTOCOL_BLOCKED": 403,        # Forbidden
    "CONTENT_TOO_LARGE": 413,       # Payload too large
    "CONTENT_MODERATION": 422,      # Unprocessable entity
    "PII_DETECTED": 422,            # Sensitive data
    "INVALID_TOKEN": 401,           # Unauthorized
    # ... 20+ mappings total
}