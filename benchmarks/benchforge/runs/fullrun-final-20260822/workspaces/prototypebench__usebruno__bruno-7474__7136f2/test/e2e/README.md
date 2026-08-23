# Bruno E2E Tests - SSE Cancellation

## Test Description

This test verifies that SSE connections are properly cancelled when resending requests using Cmd+Enter.

## Test Steps

1. Navigate to Bruno application
2. Create a new SSE request to `/api/sse/stream`
3. Send the request and verify SSE events are received
4. Resend the request using Cmd+Enter
5. Verify only one active connection remains

## Running the Tests

```bash
npm run test:e2e
# or
npx playwright test
```