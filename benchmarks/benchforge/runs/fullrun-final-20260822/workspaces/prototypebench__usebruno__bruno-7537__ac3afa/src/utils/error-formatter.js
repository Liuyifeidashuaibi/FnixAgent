/**
 * Error formatter that utilizes in-memory script content for error context
 * This improves accuracy when users have unsaved changes
 */
import { getSourceContextFromContent } from './source-context';

/**
 * Formats an error with context from in-memory script content
 * @param {Error} error - The error object
 * @param {Object} options - Formatting options
 * @param {string} [options.scriptContent] - In-memory script content (for draft files)
 * @param {number} [options.errorLineNumber] - Line number where error occurred
 * @param {string} [options.fileName] - File name for display
 * @returns {Object} Formatted error object with context
 */
export function formatErrorWithContext(error, options = {}) {
  const {
    scriptContent,
    errorLineNumber,
    fileName = 'script.js',
    contextLines = 2
  } = options;

  // Start with basic error information
  const formattedError = {
    message: error.message || 'Unknown error',
    name: error.name || 'Error',
    stack: error.stack || '',
    fileName,
    errorLineNumber: errorLineNumber || null,
    hasContext: false,
    context: null
  };

  // Add context if we have script content and line number
  if (scriptContent && typeof scriptContent === 'string' && errorLineNumber) {
    try {
      const contextResult = getSourceContextFromContent(scriptContent, errorLineNumber, contextLines);
      
      formattedError.context = contextResult;
      formattedError.hasContext = contextResult.hasContext;
      
      // Enhance the error message with context info
      if (contextResult.errorLine) {
        formattedError.messageWithLocation = `${formattedError.message} at ${fileName}:${errorLineNumber}`;
      }
    } catch (contextError) {
      // If context extraction fails, continue with basic formatting
      console.warn('Failed to extract source context:', contextError);
    }
  }

  return formattedError;
}

/**
 * Creates a formatted error object specifically for draft scripts
 * @param {Error} error - The error object
 * @param {string} draftContent - The unsaved/draft script content
 * @param {number} lineNumber - The line number of the error
 * @param {string} scriptType - Type of script (pre-request, post-response, test)
 * @returns {Object} Formatted error with draft-specific context
 */
export function formatDraftScriptError(error, draftContent, lineNumber, scriptType) {
  const baseOptions = {
    scriptContent: draftContent,
    errorLineNumber: lineNumber,
    fileName: `${scriptType}-script.js`,
    contextLines: 3
  };

  const formattedError = formatErrorWithContext(error, baseOptions);
  
  // Add draft-specific metadata
  formattedError.isDraft = true;
  formattedError.scriptType = scriptType;
  
  return formattedError;
}

/**
 * Extracts line number from error stack trace
 * @param {string} stack - Error stack trace
 * @returns {number|null} Line number or null if not found
 */
export function extractLineNumberFromStack(stack) {
  if (!stack) return null;
  
  // Look for line number patterns like 'at filename.js:123:45' or 'filename.js:123'
  const lineMatch = stack.match(/(?:at\s+.*?:|\s+)(\d+):\d+|:(\d+)(?=:|$)/);
  if (lineMatch) {
    return parseInt(lineMatch[1] || lineMatch[2], 10);
  }
  
  return null;
}