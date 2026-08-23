import json
import logging
from typing import Any, Dict, List, Optional, Union

from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    Content,
    ContentItem,
    TextContentItem,
    ToolResult,
)

logger = logging.getLogger(__name__)

class OutputLengthGuardPlugin:
    def __init__(self, max_output_length: int = 100):
        self.max_output_length = max_output_length

    def _truncate_content(self, content: Union[str, List[ContentItem]]) -> Union[str, List[ContentItem]]:
        if isinstance(content, str):
            return content[:self.max_output_length]
        elif isinstance(content, list):
            # Process each content item
            truncated_items = []
            remaining_length = self.max_output_length
            
            for item in content:
                if remaining_length <= 0:
                    break
                    
                if isinstance(item, TextContentItem) and hasattr(item, 'text'):
                    # Truncate text content
                    truncated_text = item.text[:remaining_length]
                    truncated_items.append(TextContentItem(text=truncated_text))
                    remaining_length -= len(truncated_text)
                else:
                    # For other content types, try to get text representation
                    item_str = str(item)
                    truncated_item_str = item_str[:remaining_length]
                    truncated_items.append(TextContentItem(text=truncated_item_str))
                    remaining_length -= len(truncated_item_str)
                    
            return truncated_items
        return content

    def process_tool_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        # Check if structuredContent exists and is not None
        # Before (buggy): if "structuredContent" in result:
        # After (fixed): if "structuredContent" in result and result["structuredContent"] is not None:
        if "structuredContent" in result and result["structuredContent"] is not None:
            struct_key = "structuredContent"
        elif "content" in result:
            struct_key = "content"
        else:
            # No content to process
            return result

        # Process the content based on the identified key
        if struct_key in result:
            original_content = result[struct_key]
            if isinstance(original_content, (str, list)):
                truncated_content = self._truncate_content(original_content)
                result[struct_key] = truncated_content
            
        return result

    def execute(self, request: CallToolRequest) -> CallToolResult:
        # This would normally call the tool and then process the result
        # For the purpose of this plugin, we'll assume the tool is called elsewhere
        # and we're just processing the result
        pass

# Example usage and registration
if __name__ == "__main__":
    # Plugin registration code would go here
    pass
