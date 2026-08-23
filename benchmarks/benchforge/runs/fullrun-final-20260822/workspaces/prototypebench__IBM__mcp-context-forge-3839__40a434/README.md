# MCP Context Forge - Automatic Tool Discovery

This implementation provides automatic tool discovery for upstream MCP servers via usage-aware adaptive polling.

## Features

- ✅ **Automatic tool discovery**: Continuously synchronizes tool lists from registered servers without manual intervention
- ✅ **Hot/Cold server classification**: Polls frequently-used servers at 1× base interval and deprioritizes idle servers to 3×
- ✅ **Multi-worker coordination**: Leader election with Redis support for production deployments
- ✅ **Zero-cost at rest**: No persistent connections or asyncio tasks when idle
- ✅ **Self-healing**: Automatically recovers from upstream server restarts

## Configuration

Enable automatic tool discovery by setting these environment variables:

```env
AUTO_REFRESH_SERVERS=true            # Master switch
GATEWAY_AUTO_REFRESH_INTERVAL=300    # Tool list refresh interval (seconds)
HOT_COLD_CLASSIFICATION_ENABLED=true # Enable hot/cold classification
REDIS_ENABLED=true                   # Enable Redis for multi-worker coordination
```

## Architecture

The system builds on existing health check infrastructure:

- **Semaphore-based concurrency control** (adaptive limit)
- **Chunked processing** with 50ms pauses between batches
- **Per-gateway throttling** via `last_refresh_at` timestamps
- **Lock-based conflict prevention** (manual vs. auto-refresh)

## Design Rationale

### Why Polling Instead of Push Notifications?

- **Persistent notifications require live transport streams**, but the gateway uses ephemeral connections
- **Session pools are demand-driven**, not proactive - no sessions exist for idle servers
- **Connection cost scales poorly**: N servers requires N TCP sockets and 2N asyncio tasks per worker
- **Polling holds zero file descriptors at rest** and works across workers via leader election

The polling approach is more suitable for large-scale gateway deployments while maintaining compatibility with the MCP spec's push model for future enhancements.

## Usage

Run the application:

```bash
python main.py
```

The background polling loop will automatically start if `AUTO_REFRESH_SERVERS=true`.