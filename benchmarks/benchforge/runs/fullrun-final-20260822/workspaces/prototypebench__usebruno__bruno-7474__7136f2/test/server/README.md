# Bruno Test Server - SSE Endpoints

## Available Endpoints

- `GET /api/sse/stream`: SSE endpoint that streams events every second
- `GET /api/sse/connections`: Returns current number of active connections
- `POST /api/sse/reset`: Resets connection tracking

## Usage

Start the test server with:

```bash
node test/server/index.js
```

The server will run on http://localhost:3001