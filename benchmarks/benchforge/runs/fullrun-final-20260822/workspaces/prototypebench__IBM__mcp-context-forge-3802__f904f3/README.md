# MCP Context Forge - Tool Refresh Prototype

This prototype implements the feature described in PR #3765: adding buttons for refreshing an MCP server's tools.

## Features

- HTMX-powered refresh buttons for MCP gateway tools
- Real-time status updates without full page reloads
- Simulated MCP server integration
- Responsive UI with visual feedback

## Architecture

The implementation follows the flowchart from the PR:

```
Client → POST /gateway/gateway_id/refresh/tools → MCPGateway
MCPGateway → /tools/list → MCP
MCPGateway → Response - HTMX → Client
```

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   python app.py
   ```

3. Open http://localhost:5000 in your browser

## Endpoints

- `GET /` - Main interface with refresh button
- `GET /tools/list` - Returns HTML list of available tools
- `POST /gateway/<gateway_id>/refresh/tools` - Refreshes tools for specified gateway

## Status

✅ Feature implemented as requested in PR #3765
✅ Uses HTMX for seamless updates
✅ Includes visual feedback and loading states
✅ Mock MCP server integration

---

*This is a prototype implementation for benchmarking purposes.*