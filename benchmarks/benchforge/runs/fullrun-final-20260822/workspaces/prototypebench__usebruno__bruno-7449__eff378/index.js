/*
 * Main entry point for error context utilities
 */

// Export core utilities
export { buildErrorContext } from './source-context.js';
export { parseErrorLocation, formatStackTrace } from './error-formatter.js';
export { findScriptBlock, getScriptContent } from './collection.js';
export { processImportedScript } from './import-utils.js';

// Re-export CodeSnippet component
export { default as CodeSnippet } from './CodeSnippet.js';