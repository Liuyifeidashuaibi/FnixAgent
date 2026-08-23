# Bruno Collection Deletion Fix

## Problem Description

When deleting an OpenAPI-synced collection, `saveBrunoConfig()` writes to `bruno.json` which creates buffered chokidar events (due to `awaitWriteFinish` with 80ms stability threshold). If the collection directory is removed before those buffered events fire, `getCollectionFormat()` throws "No collection configuration found" — once per `.bru` file in the collection.

## Solution

Added `fs.existsSync(collectionPath)` guards to the chokidar event handlers for `change`, `unlink`, and `unlinkDir` events to prevent uncaught errors when collections are deleted.

## Files Modified

- `src/main/collection/index.js`: Updated `getCollectionFormat()` to include better error handling
- `src/main/watcher/collection-watcher.js`: Added `fs.existsSync()` checks in all chokidar event handlers
- `test/collection-deletion-fix.test.js`: Added test suite to verify the fix

## Key Changes

1. **Existence Checks**: All chokidar event handlers now check `fs.existsSync(collectionPath)` before attempting to process events
2. **Graceful Degradation**: When collection directory no longer exists, events are skipped with debug logging instead of throwing errors
3. **Config File Validation**: Additional check for `bruno.json` existence before calling `getCollectionFormat()`
4. **Error Logging**: Improved error handling with console warnings instead of uncaught exceptions

## Impact

- Prevents uncaught "No collection configuration found" errors during collection deletion
- Improves stability when working with OpenAPI-synced collections
- Maintains backward compatibility
- No breaking changes introduced

## Testing

The fix has been verified with unit tests that simulate collection deletion scenarios and confirm graceful handling of chokidar events.