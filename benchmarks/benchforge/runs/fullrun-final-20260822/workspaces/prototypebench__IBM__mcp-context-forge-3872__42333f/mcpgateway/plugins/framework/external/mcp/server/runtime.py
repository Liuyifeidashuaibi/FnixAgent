import logging
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
from opentelemetry import trace
from opentelemetry.trace import Span
from opentelemetry.context import Context
from opentelemetry.propagators.textmap import CarrierT

# Import our observability helpers
from mcpgateway.observability import W3CTraceContextHelper

logger = logging.getLogger(__name__)


class FastMCPUpstreamRuntime:
    """Python FastMCP upstream runtime that joins distributed traces"""
    
    def __init__(self):
        self.tracer = trace.get_tracer(__name__)
    
    def extract_trace_context(self, carrier: CarrierT) -> Context:
        """Extract trace context from incoming request headers"""
        return W3CTraceContextHelper.extract_trace_context(carrier)
    
    def inject_trace_headers(self, carrier: CarrierT, span_context: Optional[Context] = None) -> None:
        """Inject trace headers into outgoing response headers"""
        W3CTraceContextHelper.inject_trace_headers(carrier, span_context)
    
    async def execute_with_trace(
        self, 
        operation_name: str, 
        operation_func: Callable[..., Awaitable[Any]], 
        carrier: CarrierT,
        **kwargs
    ) -> Any:
        """Execute an operation with proper trace context propagation"""
        # Extract incoming trace context
        context = self.extract_trace_context(carrier)
        
        # Create span for this operation
        with self.tracer.start_as_current_span(
            operation_name, 
            context=context,
            attributes={
                'mcp.upstream.runtime': 'fastmcp_python',
                'mcp.operation': operation_name
            }
        ) as span:
            try:
                # Execute the operation
                result = await operation_func(**kwargs)
                
                # Add success attributes
                span.set_attribute('mcp.status', 'success')
                
                return result
            except Exception as e:
                # Record error
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                span.record_exception(e)
                raise
    
    def create_upstream_span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
        """Create a span for upstream MCP server operations"""
        if attributes is None:
            attributes = {}
        
        attributes['mcp.upstream.runtime'] = 'fastmcp_python'
        
        return self.tracer.start_span(name, attributes=attributes)


# Global instance
fastmcp_runtime = FastMCPUpstreamRuntime()


# Helper function to wrap MCP server handlers with tracing
def traced_mcp_handler(handler_func: Callable) -> Callable:
    """Decorator to add tracing to MCP server handlers"""
    async def wrapper(*args, **kwargs):
        # Extract trace context from request (assuming first arg is request)
        request = args[0] if args else None
        
        # Get carrier from request headers
        carrier = {}
        if hasattr(request, 'headers'):
            for key, value in request.headers.items():
                if key.lower() in ['traceparent', 'tracestate']:
                    carrier[key] = value
        
        # Execute with trace context
        return await fastmcp_runtime.execute_with_trace(
            handler_func.__name__,
            handler_func,
            carrier,
            *args,
            **kwargs
        )
    
    return wrapper


# Example usage
async def example_mcp_tool_handler(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Example MCP tool handler with tracing"""
    # This would contain the actual tool logic
    return {
        'tool': tool_name,
        'result': 'success',
        'parameters': parameters
    }


# Traced version
traced_example_mcp_tool_handler = traced_mcp_handler(example_mcp_tool_handler)


# Function to prepare trace context for FastMCP upstream servers
def prepare_fastmcp_upstream_trace(carrier: CarrierT, span: Span):
    """Prepare trace context for FastMCP upstream servers"""
    # This is a compatibility wrapper for the main observability module
    from mcpgateway.observability import prepare_fastmcp_upstream_trace as main_prepare
    main_prepare(carrier, span)


# Function to inject W3C trace context into Rust plans (for compatibility)
def inject_w3c_trace_context_into_rust_plan(plan_headers: Dict[str, str], span: Span):
    """Inject W3C trace headers into Rust direct-execution plans"""
    # This is a compatibility wrapper for the main observability module
    from mcpgateway.observability import inject_w3c_trace_context_into_rust_plan as main_inject
    main_inject(plan_headers, span)


if __name__ == '__main__':
    # Example of how to use the runtime
    import asyncio
    
    async def test_runtime():
        # Simulate carrier with trace headers
        carrier = {'traceparent': '00-1234567890abcdef1234567890abcdef-1234567890abcdef-01'}
        
        # Execute with trace
        result = await fastmcp_runtime.execute_with_trace(
            'tool.execute',
            lambda: {'status': 'success'},
            carrier
        )
        
        print(f'Result: {result}')
    
    asyncio.run(test_runtime())
