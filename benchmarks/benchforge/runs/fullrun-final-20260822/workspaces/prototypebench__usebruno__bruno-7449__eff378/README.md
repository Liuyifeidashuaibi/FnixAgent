# Bruno Script Error Enhancement

This module provides enhanced ScriptError display capabilities for the Bruno API client.

## Features

### 1. Enhanced ScriptError Display
- **Error type and source file** - Shows error class name and relative path to source file
- **Code snippet with line highlighting** - Displays surrounding lines with error line highlighted
- **Formatted stack trace** - Clean, readable stack trace formatting
- **Collapsible sections** - Expand/collapse error details and stack trace

### 2. Import Behavior Change
- **Removed auto-commenting** of untranslated `pm.*` commands during Postman import
- Untranslated commands are now left as-is, throwing clear runtime errors instead of being silently commented out

## Usage

```javascript
import { buildErrorContext } from './source-context.js';
import CodeSnippet from './CodeSnippet.js';

// Build error context for display
const errorContext = buildErrorContext(error, {
  scriptContent: 'console.log("test");',
  scriptPath: 'request.bru',
  scriptType: 'request',
  lineNumber: 1
});

// Display code snippet
<CodeSnippet 
  lines={errorContext.codeSnippet.lines}
  highlightedLine={errorContext.codeSnippet.highlightedLine}
/>;
```

## Files

- `source-context.js` - Main error context builder
- `error-formatter.js` - Error location parsing and stack trace formatting
- `collection.js` - Utilities for working with .bru and .yml files
- `CodeSnippet.js` - Reusable code display component
- `import-utils.js` - Import processing utilities
- `index.js` - Main module exports
