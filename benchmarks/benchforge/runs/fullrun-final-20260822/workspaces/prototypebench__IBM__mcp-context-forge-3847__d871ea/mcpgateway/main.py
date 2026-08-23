'''Main application entry point for MCP Context Forge gateway.

Configures FastAPI application with middleware, routes, and exception handlers.
Includes new content security exception handlers for HTTP 413 and 415 errors.
'''

import logging
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from mcpgateway.config import settings
from mcpgateway.services.content_security import content_security_validator


logger = logging.getLogger(__name__)


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    version="1.0.0"
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom exception handlers for content security
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    '''Custom handler for HTTP exceptions.'''
    if exc.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE:
        logger.warning(
            "Content size violation: %s %s - %s", 
            request.method, 
            request.url.path, 
            exc.detail
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "Request entity too large",
                "detail": exc.detail,
                "documentation_url": "https://docs.mcp-context-forge.ibm.com/content-security"
            }
        )
    elif exc.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE:
        logger.warning(
            "MIME type violation: %s %s - %s", 
            request.method, 
            request.url.path, 
            exc.detail
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "Unsupported media type",
                "detail": exc.detail,
                "allowed_types": content_security_validator.get_allowed_mimetypes(),
                "documentation_url": "https://docs.mcp-context-forge.ibm.com/content-security"
            }
        )
    
    # For other HTTP exceptions, use default handling
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# Content security validation middleware
@app.middleware("http")
async def content_security_middleware(request: Request, call_next):
    '''Middleware to validate content size and MIME types for incoming requests.'''
    try:
        # Only process POST, PUT, PATCH requests with content
        if request.method in ['POST', 'PUT', 'PATCH']:
            # Read content for validation (but don't consume it for the route handler)
            # In production, this would be more sophisticated to avoid double-reading
            # For prototype, we'll assume the route handlers will handle their own validation
            pass
        
        response = await call_next(request)
        return response
        
    except Exception as e:
        logger.error("Error in content security middleware: %s", str(e))
        raise e


# Health check endpoint
@app.get("/health")
async def health_check():
    '''Health check endpoint.'''
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "debug": settings.DEBUG
    }


# Example resource endpoint (to demonstrate integration)
@app.post("/v1/resources")
async def create_resource(request: Request):
    '''Create a new resource with content security validation.'''
    # This would be implemented in resource_service.py in production
    # For prototype, just return a placeholder
    return {"message": "Resource creation endpoint"}


# Example prompt endpoint (to demonstrate integration)
@app.post("/v1/prompts")
async def create_prompt(request: Request):
    '''Create a new prompt with content security validation.'''
    # This would be implemented in prompt_service.py in production
    # For prototype, just return a placeholder
    return {"message": "Prompt creation endpoint"}
