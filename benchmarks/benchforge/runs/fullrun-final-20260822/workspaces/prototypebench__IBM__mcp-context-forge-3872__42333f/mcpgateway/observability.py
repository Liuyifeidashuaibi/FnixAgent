import logging
import time
from typing import Optional, Dict, Any, Callable, Awaitable
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.trace import Span, Tracer
from opentelemetry.trace.propagation import TraceContextTextMapPropagator
from opentelemetry.context import Context, set_value, get_value
from opentelemetry.propagators.textmap import CarrierT

# Initialize tracer
tracer = trace.get_tracer(__name__)

# Logger
logger = logging.getLogger(__name__)


class W3CTraceContextHelper:
    """Helper class for W3C trace context propagation"""
    
    @staticmethod
    def inject_trace_headers(carrier: CarrierT, span_context: Optional[Context] = None) -> None:
        """Inject traceparent and tracestate headers into carrier"""
        propagator = TraceContextTextMapPropagator()
        propagator.inject(carrier, context=span_context)
    
    @staticmethod
    def extract_trace_context(carrier: CarrierT) -> Context:
        """Extract trace context from carrier"""
        propagator = TraceContextTextMapPropagator()
        return propagator.extract(carrier)


def create_root_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Create a root span for gateway transport paths"""
    if attributes is None:
        attributes = {}
    
    # Add common attributes
    attributes['mcp.gateway.component'] = 'root'
    
    return tracer.start_span(name, attributes=attributes)


def create_mcp_client_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Create MCP client lifecycle spans"""
    if attributes is None:
        attributes = {}
    
    attributes['mcp.gateway.component'] = 'mcp_client'
    
    return tracer.start_span(name, attributes=attributes)


def create_plugin_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Create plugin framework spans"""
    if attributes is None:
        attributes = {}
    
    attributes['mcp.gateway.component'] = 'plugin'
    
    return tracer.start_span(name, attributes=attributes)


@contextmanager
def trace_span(name: str, span_type: str = 'generic', attributes: Optional[Dict[str, Any]] = None):
    """Context manager for automatic span creation and cleanup"""
    if attributes is None:
        attributes = {}
    
    # Add span type classification
    attributes['span.type'] = span_type
    
    span = tracer.start_span(name, attributes=attributes)
    try:
        yield span
    except Exception as e:
        span.set_status(trace.Status(trace.StatusCode.ERROR))
        span.record_exception(e)
        raise
    finally:
        span.end()


# Gateway transport path spans
def trace_rpc_request(attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Trace POST /rpc requests"""
    return create_root_span('POST /rpc', attributes)

def trace_mcp_request(attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Trace /mcp requests"""
    return create_root_span('POST /mcp', attributes)

def trace_server_scoped_mcp_route(route: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Trace server-scoped MCP routes"""
    if attributes is None:
        attributes = {}
    attributes['mcp.route'] = route
    return create_root_span(f'MCP Route: {route}', attributes)

def trace_internal_mcp_hop(attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Trace internal MCP transport hops"""
    return create_root_span('MCP Internal Hop', attributes)


# MCP client lifecycle spans
def trace_mcp_client_call(attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Trace mcp.client.call"""
    return create_mcp_client_span('mcp.client.call', attributes)

def trace_mcp_client_initialize(attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Trace mcp.client.initialize"""
    return create_mcp_client_span('mcp.client.initialize', attributes)

def trace_mcp_client_request(attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Trace mcp.client.request"""
    return create_mcp_client_span('mcp.client.request', attributes)

def trace_mcp_client_response(attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Trace mcp.client.response"""
    return create_mcp_client_span('mcp.client.response', attributes)


# Plugin framework spans
def trace_plugin_hook_invoke(attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Trace plugin.hook.invoke"""
    return create_plugin_span('plugin.hook.invoke', attributes)

def trace_plugin_execute(plugin_name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
    """Trace plugin.execute"""
    if attributes is None:
        attributes = {}
    attributes['plugin.name'] = plugin_name
    return create_plugin_span('plugin.execute', attributes)


# Helper function to record plugin stop-chain behavior
def record_plugin_stop_chain(span: Span, stopped_by: str, reason: str = ''):
    """Record which plugin stopped processing in trace attributes"""
    span.set_attribute('plugin.stopped_by', stopped_by)
    if reason:
        span.set_attribute('plugin.stop_reason', reason)


# FastMCP upstream runtime support helper
def prepare_fastmcp_upstream_trace(carrier: CarrierT, span: Span):
    """Prepare trace context for FastMCP upstream servers"""
    W3CTraceContextHelper.inject_trace_headers(carrier, span.get_span_context())


# Rust compatibility helper
def inject_w3c_trace_context_into_rust_plan(plan_headers: Dict[str, str], span: Span):
    """Inject W3C trace headers into Rust direct-execution plans"""
    carrier = {}
    W3CTraceContextHelper.inject_trace_headers(carrier, span.get_span_context())
    
    # Copy trace headers to plan headers
    for key, value in carrier.items():
        if key.lower() in ['traceparent', 'tracestate']:
            plan_headers[key] = value


# Example usage function for demonstration
def example_usage():
    """Example of how to use the tracing functions"""
    # Example 1: RPC request
    with trace_span('POST /rpc', 'gateway.transport') as rpc_span:
        rpc_span.set_attribute('http.method', 'POST')
        rpc_span.set_attribute('http.path', '/rpc')
        
        # Example 2: Tool invoke
        with trace_span('tool.invoke', 'tool.execution') as tool_span:
            tool_span.set_attribute('tool.name', 'example_tool')
            
            # Example 3: Plugin hooks
            with trace_span('plugin.hook.invoke', 'plugin.hook') as hook_span:
                hook_span.set_attribute('hook.name', 'pre_invoke')
                
                # Example 4: MCP client call
                with trace_span('mcp.client.call', 'mcp.client') as client_span:
                    client_span.set_attribute('mcp.method', 'tool')
                    
                    # Simulate MCP client lifecycle
                    init_span = trace_mcp_client_initialize()
                    init_span.end()
                    
                    request_span = trace_mcp_client_request()
                    request_span.set_attribute('mcp.endpoint', 'http://upstream.example.com')
                    request_span.end()
                    
                    response_span = trace_mcp_client_response()
                    response_span.set_attribute('http.status_code', 200)
                    response_span.end()

if __name__ == '__main__':
    example_usage()
