const express = require('express');
const app = express();

// SSE endpoint that streams events
app.get('/api/sse/stream', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive'
  });

  const interval = setInterval(() => {
    res.write(`data: {"message": "SSE event at ${new Date().toISOString()}"}\n\n`);
  }, 1000);

  req.on('close', () => {
    clearInterval(interval);
    res.end();
  });
});

// Endpoint to get current connections count
app.get('/api/sse/connections', (req, res) => {
  // In real implementation, this would track active connections
  res.json({ connections: 0 });
});

// Endpoint to reset connection tracking
app.post('/api/sse/reset', (req, res) => {
  res.json({ success: true });
});

module.exports = app;