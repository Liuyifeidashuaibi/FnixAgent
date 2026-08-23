# Bruno Prototype - Whitespace Validation Fix

This prototype implements the fixes for Jira issue BRU-2465:

## Changes Implemented

### 1. Whitespace-only Input Validation
- Added validation to prevent creation of collections and workspaces with names that are empty or contain only whitespace characters
- Both `CollectionCreateModal` and `WorkspaceCreateModal` now validate input using shared utility functions

### 2. Formik State Management Fix
- Fixed stale Formik values by ensuring proper state updates in onChange handlers
- Added explicit `setFieldValue` and `setFieldTouched` calls to maintain consistent form state

## Files Modified/Added

- `src/components/CollectionCreateModal.jsx` - Collection creation modal with validation
- `src/components/WorkspaceCreateModal.jsx` - Workspace creation modal with validation
- `src/utils/validation.js` - Shared validation utilities
- `src/utils/validation.test.js` - Validation test cases
- `src/components/index.js` - Component exports
- `package.json` - Project configuration

## Validation Logic

The validation checks for:
- Null or undefined values
- Empty strings (`''`)
- Whitespace-only strings (`'   '`, `'\t\n\r'`, etc.)
- Excessively long names (> 100 characters)

All whitespace-only inputs are trimmed before submission to ensure clean data storage.