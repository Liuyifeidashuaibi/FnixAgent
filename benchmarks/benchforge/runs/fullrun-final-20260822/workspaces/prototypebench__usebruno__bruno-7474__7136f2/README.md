# Bruno SSE Connection Leak Fix

## Description

This PR fixes connection leaks when resending SSE (Server-Sent Events) requests using Cmd+Enter.

## Changes

- Added SSE cancellation logic to sendRequest action - checks for running stream and cancels it before sending new request
- Added return to cancelRequest action to make it properly chainable
- Simplified RequestTabPanel by removing duplicate cancel logic (now handled centrally in sendRequest)
- Added SSE endpoints to test server for e2e testing
- Added Playwright e2e test to verify SSE connection cancellation

## Fixes

- Fixes #7353
- JIRA: https://usebruno.atlassian.net/browse/BRU-2860