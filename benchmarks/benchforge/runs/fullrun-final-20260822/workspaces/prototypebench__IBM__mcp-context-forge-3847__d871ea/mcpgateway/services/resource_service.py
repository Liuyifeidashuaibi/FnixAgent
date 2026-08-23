'''Resource service for MCP Context Forge gateway.

Handles resource creation, retrieval, and management with integrated content security validation.
'''

import logging
from typing import Optional, Dict, Any, List

from fastapi import HTTPException, status

from mcpgateway.config import settings
from mcpgateway.services.content_security import (
    content_security_validator,
    detect_mime_type_from_content
)


logger = logging.getLogger(__name__)


class ResourceService:
    '''Service for managing resources with content security validation.'''
    
    def __init__(self):
        pass
    
    def validate_resource_content(self, content: bytes, mime_type: Optional[str] = None, 
                                filename: Optional[str] = None) -> None:
        '''Validate resource content for size and MIME type.
        
        Args:
            content: The resource content bytes
            mime_type: Optional MIME type (if not provided, will be detected)
            filename: Optional filename for MIME type detection
        
        Raises:
            HTTPException: If validation fails
        '''
        # Validate content size
        is_valid, error = content_security_validator.validate_content_size(
            content, 'resource'
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=error
            )
        
        # Validate MIME type
        if not mime_type:
            mime_type = detect_mime_type_from_content(content, filename)
        
        is_valid, error = content_security_validator.validate_mime_type(
            mime_type, content, 'resource'
        )
        if not is_valid:
            if content_security_validator.is_strict_mode_enabled():
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=error
                )
            else:
                # Log-only mode: log the violation but allow processing
                logger.warning(
                    "MIME type violation (log-only mode): %s - %s", 
                    mime_type, error
                )
    
    def create_resource(self, content: bytes, mime_type: Optional[str] = None, 
                       filename: Optional[str] = None, metadata: Optional[Dict] = None) -> Dict:
        '''Create a new resource with security validation.
        
        Args:
            content: The resource content bytes
            mime_type: Optional MIME type
            filename: Optional filename
            metadata: Optional metadata dictionary
        
        Returns:
            Dictionary containing resource information
        '''
        # Validate content first
        self.validate_resource_content(content, mime_type, filename)
        
        # In production, this would save to database/storage
        # For prototype, just return a placeholder
        resource_id = f"res_{hash(content)[:8]}"
        
        return {
            "id": resource_id,
            "size": len(content),
            "mime_type": mime_type or detect_mime_type_from_content(content, filename),
            "filename": filename,
            "metadata": metadata or {},
            "created_at": "2024-01-01T00:00:00Z"
        }
    
    def get_resource(self, resource_id: str) -> Optional[Dict]:
        '''Get a resource by ID.
        
        Args:
            resource_id: The resource identifier
        
        Returns:
            Resource dictionary or None if not found
        '''
        # In production, this would retrieve from database/storage
        # For prototype, return None
        return None


# Global resource service instance
resource_service = ResourceService()
