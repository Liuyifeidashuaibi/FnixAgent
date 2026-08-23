import os
from typing import Optional


class Settings:
    # Master switch for automatic tool/resource/prompt sync
    AUTO_REFRESH_SERVERS: bool = os.getenv('AUTO_REFRESH_SERVERS', 'false').lower() == 'true'
    
    # Tool list refresh interval in seconds (default: 300, minimum: 60)
    GATEWAY_AUTO_REFRESH_INTERVAL: int = int(
        os.getenv('GATEWAY_AUTO_REFRESH_INTERVAL', '300')
    )
    
    # Minimum interval to prevent excessive polling
    GATEWAY_AUTO_REFRESH_MIN_INTERVAL: int = 60
    
    # Hot/cold classification (default: false, requires Redis for multi-worker)
    HOT_COLD_CLASSIFICATION_ENABLED: bool = os.getenv(
        'HOT_COLD_CLASSIFICATION_ENABLED', 'false'
    ).lower() == 'true'
    
    # Redis configuration
    REDIS_ENABLED: bool = os.getenv('REDIS_ENABLED', 'false').lower() == 'true'
    REDIS_URL: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Health check configuration
    HEALTH_CHECK_INTERVAL: int = int(os.getenv('HEALTH_CHECK_INTERVAL', '30'))
    
    # Session pool configuration
    MCP_SESSION_POOL_IDLE_EVICTION: int = int(
        os.getenv('MCP_SESSION_POOL_IDLE_EVICTION', '600')
    )


# Global settings instance
settings = Settings()

# Validate settings
if settings.GATEWAY_AUTO_REFRESH_INTERVAL < settings.GATEWAY_AUTO_REFRESH_MIN_INTERVAL:
    settings.GATEWAY_AUTO_REFRESH_INTERVAL = settings.GATEWAY_AUTO_REFRESH_MIN_INTERVAL
