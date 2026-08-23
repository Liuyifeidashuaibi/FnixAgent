import os
from typing import Optional, Union

# SSL Context Cache Configuration
SSL_CONTEXT_CACHE_MAX_SIZE: int = int(os.getenv("SSL_CONTEXT_CACHE_MAX_SIZE", "100"))
SSL_CONTEXT_CACHE_TTL: Optional[Union[int, float]] = None

# Parse TTL from environment variable if set
ssl_context_cache_ttl_env = os.getenv("SSL_CONTEXT_CACHE_TTL")
if ssl_context_cache_ttl_env:
    try:
        SSL_CONTEXT_CACHE_TTL = float(ssl_context_cache_ttl_env)
    except ValueError:
        SSL_CONTEXT_CACHE_TTL = None

# Other configuration constants
# ... other config ...
