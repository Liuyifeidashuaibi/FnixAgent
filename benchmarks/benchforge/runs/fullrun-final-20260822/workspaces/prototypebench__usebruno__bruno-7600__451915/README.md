# Bruno Process Env Variable Resolution Fixes

## Fixes Implemented

### 1. EnvironmentVariablesTable - Global Environment Editor Fix
- When `collection` prop is null (global environment editor), the component now reads `processEnvVariables` directly from the active workspace in Redux state
- This ensures tooltip/preview correctly shows resolved values from workspace .env files

### 2. mountScratchCollection - Runtime Resolution Fix
- Added call to `ipcRenderer.send('renderer:set-collection-workspace')` to map scratch collections to their workspace path
- This enables `getProcessEnvVars()` to find workspace .env values at runtime for scratch pad requests

## Root Cause Addressed
- Missing data connection: `EnvironmentVariablesTable` with `collection={null}` had no access to workspace process.env values
- Missing mapping: Scratch collections were never mapped to their workspace, preventing `.env` resolution at runtime

## Files Modified
- `src/components/EnvironmentVariablesTable.js` - Enhanced to handle null collection case
- `src/utils/collectionMounter.js` - Added workspace mapping for scratch collections
- `src/utils/environmentUtils.js` - Updated process env variable retrieval logic

Fixes #7572
[JIRA BRU-2978](https://usebruno.atlassian.net/browse/BRU-2978)