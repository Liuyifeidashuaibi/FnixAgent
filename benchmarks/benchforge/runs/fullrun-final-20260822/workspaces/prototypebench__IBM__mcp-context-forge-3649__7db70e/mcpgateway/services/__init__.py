# mcpgateway.services package initialization

from .tool_service import get_tools_for_server
from .resource_service import get_resources_for_server
from .prompt_service import get_prompts_for_server
from .server_service import get_servers

__all__ = [
    'get_tools_for_server',
    'get_resources_for_server',
    'get_prompts_for_server',
    'get_servers'
]
