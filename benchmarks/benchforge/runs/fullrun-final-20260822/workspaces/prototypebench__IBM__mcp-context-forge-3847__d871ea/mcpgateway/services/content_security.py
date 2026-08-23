'''Content security validation service for MCP Context Forge gateway.

Implements content size limits and MIME type restrictions for resources and prompts.
Supports flexible enforcement modes (strict reject or log-only) and provides
PII-safe logging with Prometheus metrics integration.
'''

import logging
import hashlib
import re
from typing import List, Optional, Set, Tuple, Dict, Any
from urllib.parse import urlparse

import prometheus_client

from mcpgateway.config import settings


logger = logging.getLogger(__name__)


# Prometheus metrics
count_size_violations = prometheus_client.Counter(
    'content_security_size_violations_total',
    'Total number of content size violations',
    ['entity_type']  # resource or prompt
)

count_mime_violations = prometheus_client.Counter(
    'content_security_mime_violations_total',
    'Total number of MIME type violations'
)


class ContentSecurityValidator:
    '''Content security validator for MCP Context Forge gateway.
    
    Validates content size and MIME types for resources and prompts.
    Supports both strict rejection mode and log-only mode.
    '''
    
    def __init__(self):
        self._allowed_mimetypes: Set[str] = set()
        self._initialize_allowed_mimetypes()
    
    def _initialize_allowed_mimetypes(self) -> None:
        '''Initialize the allowed MIME types from configuration.'''
        if hasattr(settings, 'CONTENT_ALLOWED_RESOURCE_MIMETYPES'):
            mimetypes_str = getattr(settings, 'CONTENT_ALLOWED_RESOURCE_MIMETYPES', '')
            if mimetypes_str:
                # Split by comma and strip whitespace
                self._allowed_mimetypes = {
                    mime.strip() for mime in mimetypes_str.split(',') if mime.strip()
                }
        
        # Default fallback if no config is set
        if not self._allowed_mimetypes:
            self._allowed_mimetypes = {
                'text/plain',
                'text/markdown',
                'text/html',
                'text/css',
                'text/javascript',
                'application/json',
                'application/xml',
                'application/yaml',
                'application/x-yaml',
                'application/ld+json',
                'application/hal+json',
                'application/vnd.api+json',
                'application/vnd.oai.openapi+json',
                'application/vnd.oai.openapi+yaml',
                'image/png',
                'image/jpeg',
                'image/gif',
                'image/svg+xml'
            }
    
    def validate_content_size(self, content: bytes, entity_type: str, 
                             max_size: Optional[int] = None) -> Tuple[bool, str]:
        '''Validate content size against maximum allowed size.
        
        Args:
            content: The content bytes to validate
            entity_type: Type of entity ('resource' or 'prompt')
            max_size: Maximum allowed size in bytes (defaults to config)
        
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        '''
        if max_size is None:
            if entity_type == 'resource':
                max_size = getattr(settings, 'CONTENT_MAX_RESOURCE_SIZE', 102400)
            elif entity_type == 'prompt':
                max_size = getattr(settings, 'CONTENT_MAX_PROMPT_SIZE', 10240)
            else:
                max_size = 102400  # default fallback
        
        content_size = len(content)
        
        if content_size > max_size:
            error_msg = f"{entity_type.capitalize()} content size {content_size} bytes exceeds maximum allowed {max_size} bytes"
            count_size_violations.labels(entity_type=entity_type).inc()
            return False, error_msg
        
        return True, ""
    
    def validate_mime_type(self, mime_type: str, content: bytes, 
                          entity_type: str = 'resource') -> Tuple[bool, str]:
        '''Validate MIME type against allowed list.
        
        Args:
            mime_type: The MIME type string to validate
            content: The content bytes (for additional validation if needed)
            entity_type: Type of entity ('resource' or 'prompt')
        
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        '''
        if not mime_type:
            return False, "MIME type is required but not provided"
        
        # Normalize MIME type (lowercase, remove parameters)
        normalized_mime = mime_type.split(';')[0].strip().lower()
        
        # Check base MIME type
        if normalized_mime in self._allowed_mimetypes:
            return True, ""
        
        # Check vendor MIME types and suffixes (+json, +xml)
        if '+' in normalized_mime:
            base_type = normalized_mime.split('+')[0].strip() + '+'
            # Check if base type with + suffix is allowed
            if any(allowed_mime.startswith(base_type) for allowed_mime in self._allowed_mimetypes):
                return True, ""
        
        # Check if there's a more general type that matches
        # e.g., application/* matches application/json
        mime_parts = normalized_mime.split('/')
        if len(mime_parts) == 2:
            type_part, subtype_part = mime_parts
            if type_part != '*' and subtype_part != '*':
                # Check for type/* pattern
                type_wildcard = f"{type_part}/*"
                if type_wildcard in self._allowed_mimetypes:
                    return True, ""
                
                # Check for */subtype pattern
                subtype_wildcard = f"*/{subtype_part}"
                if subtype_wildcard in self._allowed_mimetypes:
                    return True, ""
        
        error_msg = f"MIME type '{mime_type}' is not in the allowed list"
        count_mime_violations.inc()
        return False, error_msg
    
    def is_strict_mode_enabled(self) -> bool:
        '''Check if strict MIME validation mode is enabled.'''
        return getattr(settings, 'CONTENT_STRICT_MIME_VALIDATION', False)
    
    def get_allowed_mimetypes(self) -> List[str]:
        '''Get the list of allowed MIME types.'''
        return sorted(list(self._allowed_mimetypes))


# Global validator instance
content_security_validator = ContentSecurityValidator()


# Helper functions for PII-safe logging
def hash_email(email: str) -> str:
    '''Hash email address for PII-safe logging.'''
    if not email:
        return ""
    return hashlib.sha256(email.encode('utf-8')).hexdigest()[:16]

def mask_ip_address(ip: str) -> str:
    '''Mask IP address for PII-safe logging.'''
    if not ip:
        return ""
    parts = ip.split('.')
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.xxx.xxx"
    return "xxx.xxx.xxx.xxx"


# Utility function to extract MIME type from content (basic detection)
def detect_mime_type_from_content(content: bytes, filename: str = "") -> str:
    '''Basic MIME type detection from content and filename.'''
    if not content:
        return "application/octet-stream"
    
    # Check filename extension first
    if filename:
        ext = filename.lower().split('.')[-1] if '.' in filename else ""
        ext_to_mime = {
            'txt': 'text/plain',
            'md': 'text/markdown',
            'html': 'text/html',
            'htm': 'text/html',
            'css': 'text/css',
            'js': 'text/javascript',
            'json': 'application/json',
            'xml': 'application/xml',
            'yaml': 'application/yaml',
            'yml': 'application/yaml',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'svg': 'image/svg+xml',
        }
        if ext in ext_to_mime:
            return ext_to_mime[ext]
    
    # Basic content sniffing
    if len(content) >= 2:
        if content[:2] == b'\xff\xd8':  # JPEG magic bytes
            return 'image/jpeg'
        elif content[:4] == b'\x89PNG':  # PNG magic bytes
            return 'image/png'
        elif content[:3] == b'GIF':  # GIF magic bytes
            return 'image/gif'
    
    # Default fallback
    return 'application/octet-stream'
