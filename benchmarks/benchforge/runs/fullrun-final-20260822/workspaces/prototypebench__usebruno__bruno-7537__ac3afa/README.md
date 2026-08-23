# Bruno Error Context Enhancement

## Overview

This enhancement improves error handling in Bruno by utilizing in-memory script content for error context, which provides more accurate debugging information when users have unsaved (draft) changes.

## Key Features

- **In-Memory Script Context**: Error formatter now uses the current editor content instead of relying solely on saved file content
- **Source Context Utility**: New `getSourceContextFromContent` function extracts relevant code lines around error locations
- **Draft Script Support**: Special handling for pre-request, post-response, and test scripts in draft state
- **Comprehensive Testing**: Unit tests and Playwright e2e tests validate the functionality

## Files Added

- `src/utils/source-context.js` - Core utility for extracting context from script content
- `src/utils/error-formatter.js` - Enhanced error formatter with draft support
- `src/utils/__tests__/error-formatter.test.js` - Unit tests for error formatting
- `tests/e2e/error-handling-draft.test.js` - Playwright end-to-end tests for draft error handling

## Usage

The enhanced error formatter is used automatically when:
- Scripts are in draft (unsaved) state
- Errors occur during script execution
- The system needs to display contextual code information for debugging

## Testing

Run tests with:

```bash
# Unit tests
npm test

# Playwright e2e tests
npx playwright test tests/e2e/error-handling-draft.test.js
```

## Contributing

Please follow the [Bruno contribution guidelines](https://github.com/usebruno/bruno/blob/main/contributing.md) when making changes to this functionality.