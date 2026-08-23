# Bruno Authentication Persistence Fix

## Issue Addressed
- **JIRA**: [BRU-1169](https://usebruno.atlassian.net/browse/BRU-1169)
- **GitHub**: Fixes https://github.com/usebruno/bruno/issues/5636

## Problem Description
When users switch between different authentication modes (e.g., from Bearer Token to Basic Auth), previously entered authentication data was being lost. This required users to re-enter credentials every time they changed auth modes, creating a poor user experience.

## Solution
Implemented authentication data persistence across mode switches using a dedicated storage mechanism that:
- Stores authentication data separately for each auth mode
- Preserves data when switching between modes
- Restores previously entered data when switching back to a mode
- Maintains backward compatibility with existing auth configuration

## Key Components

### `src/utils/authPersistence.js`
- Core utility for managing auth data storage
- `getAuthDataForMode()` - Retrieve stored data for a specific mode
- `storeAuthDataForMode()` - Store auth data for a specific mode
- `getCompleteAuthConfig()` - Get merged config with preserved data
- `updateAuthConfig()` - Update config while preserving cross-mode data

### `src/components/AuthenticationConfig.js`
- React component that handles auth mode selection
- Integrated with persistence utility to maintain data across mode changes
- Supports common auth modes: None, Bearer Token, Basic Auth, API Key

### `src/tests/authPersistence.test.js`
- Comprehensive test suite verifying the persistence behavior
- Tests data preservation across mode switches
- Validates edge cases and error handling

## How It Works
1. When user enters authentication data for a mode, it's stored in memory keyed by the mode
2. When user switches to a different mode, the previous mode's data is preserved
3. When user switches back to a previously used mode, the stored data is automatically restored
4. The UI component seamlessly integrates with this persistence layer

## Usage
The implementation is designed to be drop-in compatible with existing Bruno architecture. Simply import and use the provided utilities and components.

## Testing
Run tests with: `npm test` or `yarn test`

## License
MIT