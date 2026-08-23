# Response State Management Fix

## Description

This implementation addresses JIRA BRU-1086: "Clear assertion and test results when response is cleared".

When a response is cleared in the Redux store, the associated test results (`assertionResults`, `preRequestTestResults`, and `postRequestTestResults`) are now also cleared along with the response. This ensures consistency in the application state by preventing stale test results from being displayed alongside a cleared response.

## Changes Made

1. **Response Reducer** (`src/reducers/responseReducer.js`): Updated to handle `CLEAR_RESPONSE` action that clears not only the response but also all associated test results.
2. **Response Actions** (`src/actions/responseActions.js`): Added action creators for clearing response and setting test results.
3. **Response Constants** (`src/constants/responseConstants.js`): Defined constants for all response-related actions.
4. **Response Selectors** (`src/selectors/responseSelectors.js`): Created selectors to access response state and test results from components.
5. **Tests** (`src/reducers/responseReducer.test.js`): Added comprehensive tests to verify the clearing behavior.

## Why This Change

- Prevents confusing UI state where old test results remain visible after clearing a response
- Maintains consistency between response state and its related test results
- Ensures clean state management when users clear/reset requests

## Usage

To clear response and associated test results:

```javascript
import { clearResponse } from './actions/responseActions';

// Dispatch the action
dispatch(clearResponse());
```

The reducer will automatically clear:
- `response`
- `assertionResults`
- `preRequestTestResults`
- `postRequestTestResults`

## Testing

Run tests with:

```bash
npm test
# or
yarn test
```

The test suite verifies that `CLEAR_RESPONSE` action properly clears all response-related state.
