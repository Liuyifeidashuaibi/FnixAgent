import logging
import asyncio
from typing import Dict, Any, Optional
from opentelemetry import trace
from opentelemetry.trace import Span
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Import our observability module
from mcpgateway.observability import (
    trace_rpc_request,
    trace_mcp_request,
    trace_server_scoped_mcp_route,
    trace_internal_mcp_hop,
    trace_mcp_client_call,
    trace_mcp_client_initialize,
    trace_mcp_client_request,
    trace_mcp_client_response,
    trace_plugin_hook_invoke,
    trace_plugin_execute,
    record_plugin_stop_chain,
    W3CTraceContextHelper
)

# Initialize FastAPI app
app = FastAPI(title="MCP Gateway", version="1.0.0")

# Logger
logger = logging.getLogger(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware to add OpenTelemetry tracing to HTTP requests"""
    
    async def dispatch(self, request: Request, call_next):
        # Extract trace context from incoming request headers
        carrier = {}
        for key, value in request.headers.items():
            if key.lower() in ['traceparent', 'tracestate']:
                carrier[key] = value
        
        # Create root span based on request path
        if request.url.path == '/rpc':
            span = trace_rpc_request({
                'http.method': request.method,
                'http.path': request.url.path,
                'http.host': request.url.hostname or '',
                'http.scheme': request.url.scheme
            })
        elif request.url.path == '/mcp':
            span = trace_mcp_request({
                'http.method': request.method,
                'http.path': request.url.path,
                'http.host': request.url.hostname or '',
                'http.scheme': request.url.scheme
            })
        else:
            # Server-scoped MCP routes
            span = trace_server_scoped_mcp_route(request.url.path, {
                'http.method': request.method,
                'http.path': request.url.path,
                'http.host': request.url.hostname or '',
                'http.scheme': request.url.scheme
            })
        
        try:
            # Process the request
            response = await call_next(request)
            
            # Add response attributes to span
            span.set_attribute('http.status_code', response.status_code)
            
            return response
        except Exception as e:
            # Record exception in span
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            span.record_exception(e)
            raise
        finally:
            span.end()


# Add middleware to app
app.add_middleware(TracingMiddleware)


@app.post('/rpc')
async def rpc_endpoint(request: Request):
    """RPC endpoint with full tracing"""
    # This would contain the actual RPC logic
    # For now, just demonstrate the tracing structure
    
    # Simulate tool.invoke span
    with trace_span('tool.invoke', 'tool.execution') as tool_span:
        tool_span.set_attribute('tool.name', 'example_tool')
        
        # Simulate pre-invoke plugin hooks
        with trace_span('plugin.hook.invoke', 'plugin.hook') as pre_hook_span:
            pre_hook_span.set_attribute('hook.phase', 'pre_invoke')
            
            # Simulate plugin execution
            with trace_span('plugin.execute', 'plugin.execution') as plugin_span:
                plugin_span.set_attribute('plugin.name', 'pre_invoke_validator')
                
                # Simulate MCP client call
                with trace_span('mcp.client.call', 'mcp.client') as client_span:
                    client_span.set_attribute('mcp.method', 'tool')
                    
                    # MCP client lifecycle
                    init_span = trace_mcp_client_initialize()
                    init_span.set_attribute('mcp.server', 'http://upstream.example.com')
                    init_span.end()
                    
                    request_span = trace_mcp_client_request()
                    request_span.set_attribute('mcp.endpoint', 'http://upstream.example.com/tool')
                    request_span.end()
                    
                    response_span = trace_mcp_client_response()
                    response_span.set_attribute('http.status_code', 200)
                    response_span.set_attribute('mcp.response.size', 1024)
                    response_span.end()
        
        # Simulate post-invoke plugin hooks
        with trace_span('plugin.hook.invoke', 'plugin.hook') as post_hook_span:
            post_hook_span.set_attribute('hook.phase', 'post_invoke')
            
            # Simulate plugin execution
            with trace_span('plugin.execute', 'plugin.execution') as plugin_span:
                plugin_span.set_attribute('plugin.name', 'response_enhancer')
    
    return {'status': 'success', 'message': 'RPC processed with full tracing'}


@app.post('/mcp')
async def mcp_endpoint(request: Request):
    """MCP endpoint with tracing"""
    # Similar structure to /rpc but for MCP protocol
    return {'status': 'success', 'message': 'MCP processed with tracing'}


@app.get('/health')
async def health_check():
    """Health check endpoint"""
    return {'status': 'healthy'}


# Example function to demonstrate internal MCP transport hops
async def execute_internal_mcp_hop():
    """Example of internal MCP transport hop tracing"""
    with trace_span('MCP Internal Hop', 'mcp.internal') as hop_span:
        hop_span.set_attribute('hop.type', 'internal')
        hop_span.set_attribute('hop.destination', 'local_service')
        
        # Simulate some work
        await asyncio.sleep(0.01)
        
        return {'result': 'hop_completed'}


# Example function to demonstrate plugin stop-chain behavior
def demonstrate_plugin_stop_chain():
    """Demonstrate recording which plugin stopped processing"""
    span = trace_plugin_hook_invoke({'hook.chain': 'pre_invoke'})
    
    # Record that a specific plugin stopped the chain
    record_plugin_stop_chain(span, 'rate_limit_checker', 'exceeded_quota')
    
    span.end()


if __name__ == '__main__':
    # This would be run by Uvicorn in production
    pass
