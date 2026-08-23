import logging
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


class ToolResult:
    """Mock ToolResult class for demonstration"""
    def __init__(self, is_error: bool = False, isError: bool = False, content: list = None):
        self.is_error = is_error
        self.isError = isError
        self.content = content or []


class Tool:
    """Mock Tool class for demonstration"""
    def __init__(self, name: str = "<unknown>"):
        self.name = name


def _extract_and_validate_structured_content(
    tool_result: ToolResult,
    tool: Tool,
    output_schema: Optional[Dict[str, Any]] = None,
    logger: logging.Logger = logger
) -> bool:
    """
    Extract and validate structured content from tool result.
    
    CRITICAL: Skip validation for error responses per MCP spec
    Error responses with isError=true do not require structured content
    Reference: https://modelcontextprotocol.io/specification/2025-11-25/server/tools#error-handling
    
    Args:
        tool_result: The tool result to extract and validate
        tool: The tool that produced the result
        output_schema: Optional schema to validate against
        logger: Logger instance
    
    Returns:
        bool: True if validation passed or was skipped, False otherwise
    """
    # CRITICAL: Skip validation for error responses per MCP spec
    # Error responses with isError=true do not require structured content
    # Reference: https://modelcontextprotocol.io/specification/2025-11-25/server/tools#error-handling
    is_error = getattr(tool_result, "is_error", False) or getattr(tool_result, "isError", False)
    if is_error:
        logger.debug(f"Skipping output schema validation for error response from tool {getattr(tool, 'name', '<unknown>')}")
        return True
    
    # Original validation logic would go here
    # For the purpose of this fix, we're just implementing the early return
    # In a real implementation, the rest of the validation would follow
    
    # Placeholder for actual validation logic
    if output_schema is not None:
        # Simulate validation logic
        pass
    
    return True
