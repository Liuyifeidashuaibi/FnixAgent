const express = require('express');
const sseEndpoints = require('./sseEndpoints');

const app = express();
const PORT = 3001;

// Use SSE endpoints
app.use('/api', sseEndpoints);

app.listen(PORT, () => {
  console.log(`Test server running on http://localhost:${PORT}`);
});

module.exports = app;