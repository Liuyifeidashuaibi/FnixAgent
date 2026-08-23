# MCP Context Forge - Observability Prototype

This prototype implements the observability session fix described in PR #3883.

## Key Features

- ✅ **Separate Session Pattern**: Observability write operations create and manage their own independent database sessions
- ✅ **Bug Fixed**: Observability data no longer rolled back with failed transactions
- ✅ **API Changes**: Write methods no longer accept `db` parameter
- ✅ **Context Managers**: `trace_span()`, `trace_tool_invocation()`, `trace_a2a_request()` updated to new API
- ✅ **Middleware Update**: `ObservabilityMiddleware` no longer creates `request.state.db`

## Files Included

- `mcpgateway/services/observability_service.py`: Core implementation with separate sessions
- `mcpgateway/middleware/observability_middleware.py`: Updated middleware without session management
- `mcpgateway/instrumentation/sqlalchemy.py`: Updated SQL instrumentation
- `mcpgateway/services/prompt_service.py`, `resource_service.py`, `tool_service.py`: Updated callers
- `AGENTS.md`: Documentation with observability transaction behavior
- `tests/unit/mcpgateway/services/test_observability_service.py`: Test coverage

## Usage

The observability service is designed to be used as follows:

```python
from mcpgateway.services.observability_service import service

# Start a trace (no db parameter needed)
trace_id = service.start_trace("http_request", method="GET", path="/api/v1/resource")

# Use context manager for spans
with service.trace_span(trace_id, "database.query") as span_id:
    # Your database operation here
    pass

# Record metrics
service.record_metric(trace_id, "response.time", 123.45)

# End the trace
service.end_trace(trace_id, status="ok")
```

## Testing

```bash
pytest tests/unit/mcpgateway/services/test_observability_service.py -v
```

## License

MIT License
