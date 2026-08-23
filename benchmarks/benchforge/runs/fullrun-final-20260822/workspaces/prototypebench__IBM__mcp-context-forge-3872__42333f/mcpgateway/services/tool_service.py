import logging
import asyncio
from typing import Dict, Any, Optional, List, Union
from opentelemetry import trace
from opentelemetry.trace import Span

# Import observability helpers
from mcpgateway.observability import (
    trace_mcp_client_call,
    trace_mcp_client_initialize,
    trace_mcp_client_request,
    trace_mcp_client_response,
    trace_plugin_hook_invoke,
    trace_plugin_execute,
    record_plugin_stop_chain,
    W3CTraceContextHelper
)

logger = logging.getLogger(__name__)


class ToolService:
    """Service for handling MCP tool execution with full tracing"""
    
    def __init__(self):
        self.tracer = trace.get_tracer(__name__)
    
    async def invoke_tool(
        self, 
        tool_name: str, 
        parameters: Dict[str, Any],
        pre_hooks: Optional[List[Callable]] = None,
        post_hooks: Optional[List[Callable]] = None
    ) -> Dict[str, Any]:
        """Invoke an MCP tool with full tracing"""
        # Start root span for tool invocation
        with self.tracer.start_as_current_span(
            'tool.invoke',
            attributes={
                'tool.name': tool_name,
                'tool.parameters.count': len(parameters) if parameters else 0
            }
        ) as tool_span:
            
            # Execute pre-invoke hooks with tracing
            if pre_hooks:
                with self.tracer.start_as_current_span(
                    'plugin.hook.invoke',
                    attributes={'hook.phase': 'pre_invoke'}
                ) as pre_hook_span:
                    
                    for i, hook in enumerate(pre_hooks):
                        try:
                            with self.tracer.start_as_current_span(
                                'plugin.execute',
                                attributes={
                                    'plugin.name': hook.__name__,
                                    'plugin.index': i
                                }
                            ) as plugin_span:
                                
                                # Execute hook
                                result = await hook(tool_name, parameters)
                                
                                # Check if hook stopped the chain
                                if result and isinstance(result, dict) and result.get('stop_chain'):
                                    record_plugin_stop_chain(
                                        plugin_span, 
                                        hook.__name__, 
                                        result.get('reason', 'unknown')
                                    )
                                    return {'status': 'stopped', 'by': hook.__name__}
                                
                        except Exception as e:
                            logger.error(f'Pre-hook {hook.__name__} failed: {e}')
                            raise
            
            # Execute MCP client call with full lifecycle tracing
            with self.tracer.start_as_current_span(
                'mcp.client.call',
                attributes={'mcp.tool': tool_name}
            ) as client_call_span:
                
                # MCP client initialize
                init_span = trace_mcp_client_initialize({
                    'mcp.tool': tool_name,
                    'mcp.client.type': 'streamablehttp'
                })
                init_span.end()
                
                # MCP client request
                request_span = trace_mcp_client_request({
                    'mcp.tool': tool_name,
                    'mcp.endpoint': f'http://upstream.example.com/tool/{tool_name}'
                })
                
                # Simulate HTTP request (in real code this would be actual HTTP call)
                await asyncio.sleep(0.01)
                
                # Record request completion
                request_span.set_attribute('http.status_code', 200)
                request_span.set_attribute('http.duration_ms', 10.5)
                request_span.end()
                
                # MCP client response
                response_span = trace_mcp_client_response({
                    'mcp.tool': tool_name,
                    'http.status_code': 200
                })
                
                # Simulate response processing
                await asyncio.sleep(0.005)
                
                # Record response attributes
                response_span.set_attribute('mcp.response.size', 512)
                response_span.set_attribute('mcp.response.format', 'json')
                response_span.end()
            
            # Execute post-invoke hooks with tracing
            if post_hooks:
                with self.tracer.start_as_current_span(
                    'plugin.hook.invoke',
                    attributes={'hook.phase': 'post_invoke'}
                ) as post_hook_span:
                    
                    for i, hook in enumerate(post_hooks):
                        try:
                            with self.tracer.start_as_current_span(
                                'plugin.execute',
                                attributes={
                                    'plugin.name': hook.__name__,
                                    'plugin.index': i
                                }
                            ) as plugin_span:
                                
                                # Execute hook
                                await hook(tool_name, parameters)
                                
                        except Exception as e:
                            logger.error(f'Post-hook {hook.__name__} failed: {e}')
                            raise
            
            # Return success result
            return {
                'status': 'success',
                'tool': tool_name,
                'result': 'tool_executed_successfully'
            }
    
    async def prepare_rust_mcp_tool_execution(
        self, 
        tool_name: str, 
        parameters: Dict[str, Any],
        plan_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Prepare Rust MCP tool execution with W3C trace context injection"""
        if plan_headers is None:
            plan_headers = {}
        
        # Create span for Rust execution preparation
        with self.tracer.start_as_current_span(
            'rust.mcp.tool.prepare',
            attributes={'tool.name': tool_name}
        ) as rust_span:
            
            # Inject W3C trace context into plan headers for Rust compatibility
            from mcpgateway.observability import inject_w3c_trace_context_into_rust_plan
            inject_w3c_trace_context_into_rust_plan(plan_headers, rust_span)
            
            # Record that trace context was injected
            rust_span.set_attribute('trace.context.injected', True)
            rust_span.set_attribute('trace.headers.count', len(plan_headers))
            
            return {
                'plan_headers': plan_headers,
                'tool': tool_name,
                'trace_injected': True
            }


# Global instance
tool_service = ToolService()


# Example hook functions for demonstration
async def validate_parameters_hook(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Example pre-invoke validation hook"""
    if not parameters:
        return {'stop_chain': True, 'reason': 'missing_parameters'}
    return {'continue': True}


async def rate_limit_hook(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Example rate limiting hook"""
    # Simulate rate limit check
    import random
    if random.random() < 0.1:  # 10% chance of rate limit
        return {'stop_chain': True, 'reason': 'rate_limit_exceeded'}
    return {'continue': True}


if __name__ == '__main__':
    # Example usage
    import asyncio
    
    async def test_tool_service():
        service = ToolService()
        
        # Test basic tool invocation
        result = await service.invoke_tool(
            'example_tool', 
            {'param1': 'value1'},
            pre_hooks=[validate_parameters_hook, rate_limit_hook]
        )
        
        print(f'Tool result: {result}')
    
    asyncio.run(test_tool_service())
