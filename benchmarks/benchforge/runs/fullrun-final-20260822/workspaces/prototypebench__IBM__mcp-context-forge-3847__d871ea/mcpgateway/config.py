'''Configuration module for MCP Context Forge gateway.

Contains application settings, including the new content security configuration.
'''

import os
from typing import Optional, List


# Base configuration class
class Settings:
    '''Application settings configuration.'''
    
    # General settings
    APP_NAME: str = os.getenv('APP_NAME', 'mcp-context-forge')
    DEBUG: bool = os.getenv('DEBUG', 'false').lower() == 'true'
    
    # Content security settings (new for US-1 and US-2)
    CONTENT_MAX_RESOURCE_SIZE: int = int(os.getenv('CONTENT_MAX_RESOURCE_SIZE', '102400'))
    CONTENT_MAX_PROMPT_SIZE: int = int(os.getenv('CONTENT_MAX_PROMPT_SIZE', '10240'))
    CONTENT_STRICT_MIME_VALIDATION: bool = os.getenv('CONTENT_STRICT_MIME_VALIDATION', 'false').lower() == 'true'
    CONTENT_ALLOWED_RESOURCE_MIMETYPES: str = os.getenv(
        'CONTENT_ALLOWED_RESOURCE_MIMETYPES',
        'text/plain,text/markdown,text/html,text/css,text/javascript,application/json,'
        'application/xml,application/yaml,application/x-yaml,application/ld+json,'
        'application/hal+json,application/vnd.api+json,application/vnd.oai.openapi+json,'
        'application/vnd.oai.openapi+yaml,image/png,image/jpeg,image/gif,image/svg+xml'
    )
    
    # Database settings
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///./app.db')
    
    # Logging settings
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    
    # Other service settings
    RESOURCE_SERVICE_URL: str = os.getenv('RESOURCE_SERVICE_URL', 'http://localhost:8000')
    PROMPT_SERVICE_URL: str = os.getenv('PROMPT_SERVICE_URL', 'http://localhost:8001')


# Global settings instance
settings = Settings()
