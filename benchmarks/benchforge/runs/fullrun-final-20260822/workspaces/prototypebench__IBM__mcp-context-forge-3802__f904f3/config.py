# MCP Gateway Configuration

# MCP Server endpoint
MCP_SERVER_URL = "http://localhost:8000"

# Gateway configuration
def get_gateway_config(gateway_id):
    return {
        "gateway_id": gateway_id,
        "mcp_server_url": MCP_SERVER_URL,
        "tools_cache_ttl": 300,  # 5 minutes
        "timeout": 10  # seconds
    }

# Default gateway
DEFAULT_GATEWAY_ID = "gateway-123"