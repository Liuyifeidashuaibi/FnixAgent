# Bruno Collection Empty State Fix

## Issue Description

Empty .bru collections in the sidebar did not show the "+ Add request" CTA because `bruno.json` (auto-created in every .bru collection) and other non-request items were counted toward `itemCount`, suppressing the empty state.

## Solution

This change aligns the collection-level empty check with how folders already behave: only requests and folders count toward "has content."

The fix implements:
- `isCollectionEmpty()` utility function that only considers requests (.bru files except bruno.json) and folders as meaningful content
- `getMeaningfulItemCount()` utility function that counts only requests and folders
- Updated CollectionSidebar component that uses the corrected empty state logic

## Files Modified

- `src/utils/collection-empty-check.js` - Core utility functions for empty state checking
- `src/utils/collection-empty-check.test.js` - Comprehensive tests for the fix
- `src/components/CollectionSidebar.js` - Component using the corrected logic

## How It Works

The empty state logic now ignores:
- `bruno.json` (collection configuration file)
- Other non-request files (environment.json, settings.yml, etc.)

And only considers as "content":
- Requests (.bru files that are not bruno.json)
- Folders (subdirectories)

This ensures the "+ Add request" CTA appears correctly when a collection truly has no requests or folders.