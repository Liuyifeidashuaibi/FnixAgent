# Request Tabs Fix - BRU-3327

## Issue Description
JIRA BRU-3327: Request tabs are not being selected when navigating between requests.

## Root Cause
The tab selection state was not properly synchronized with the active request ID state, causing tabs to remain in their previous state when navigating between different requests.

## Solution
Implemented proper synchronization between the active request ID and tab selection state using React's useEffect hook to ensure the active tab always matches the currently active request.

## Key Changes
- Added useEffect hook to sync activeTab state with activeRequestId prop
- Used useCallback for tab event handlers to prevent unnecessary re-renders
- Enhanced tab close functionality with proper event propagation handling
- Added comprehensive test coverage to verify tab selection behavior

## Files Modified
- `src/components/RequestPane/RequestTabs.js` - Main component with synchronization logic
- `src/components/RequestPane/RequestTabs.test.js` - Test suite for verification
- `src/components/RequestPane/RequestPane.js` - Parent component integration
- `src/components/RequestPane/index.js` - Export configuration

## Verification
- Tabs now automatically select the correct request when navigating between requests
- Tab selection remains consistent across different navigation methods (click, keyboard, programmatic)
- Tests pass confirming proper synchronization behavior