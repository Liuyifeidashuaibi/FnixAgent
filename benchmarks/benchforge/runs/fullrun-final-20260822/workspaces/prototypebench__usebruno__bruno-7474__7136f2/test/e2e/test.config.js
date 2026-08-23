module.exports = {
  // Test configuration for SSE cancellation tests
  timeout: 30000,
  retries: 2,
  
  // Environment variables
  env: {
    TEST_SERVER_URL: 'http://localhost:3001',
    BRUNO_APP_URL: 'http://localhost:3000'
  }
};