/**
 * Extracts context lines from in-memory script content around a given line number
 * @param {string} content - The full script content
 * @param {number} lineNumber - The line number where the error occurred (1-based)
 * @param {number} contextLines - Number of context lines to include before and after (default: 2)
 * @returns {Object} Object containing context lines and metadata
 */
export function getSourceContextFromContent(content, lineNumber, contextLines = 2) {
  if (!content || typeof content !== 'string') {
    return {
      contextLines: [],
      errorLine: null,
      hasContext: false
    };
  }

  const lines = content.split('\n');
  
  // Adjust for 1-based line numbers
  const errorIndex = lineNumber - 1;
  
  // Ensure the error line exists
  if (errorIndex < 0 || errorIndex >= lines.length) {
    return {
      contextLines: [],
      errorLine: null,
      hasContext: false
    };
  }

  // Calculate start and end indices for context
  const startIndex = Math.max(0, errorIndex - contextLines);
  const endIndex = Math.min(lines.length, errorIndex + contextLines + 1);

  // Extract context lines with line numbers
  const contextLinesArray = [];
  for (let i = startIndex; i < endIndex; i++) {
    contextLinesArray.push({
      lineNumber: i + 1,
      content: lines[i],
      isErrorLine: i === errorIndex
    });
  }

  return {
    contextLines: contextLinesArray,
    errorLine: {
      lineNumber: lineNumber,
      content: lines[errorIndex]
    },
    hasContext: contextLinesArray.length > 0
  };
}

/**
 * Gets source context from content with additional formatting options
 * @param {string} content - The full script content
 * @param {number} lineNumber - The line number where the error occurred
 * @param {Object} options - Additional options
 * @returns {Object} Formatted context object
 */
export function getSourceContextFromContentFormatted(content, lineNumber, options = {}) {
  const { contextLines = 2, includeLineNumbers = true, maxLineLength = 100 } = options;
  
  const result = getSourceContextFromContent(content, lineNumber, contextLines);
  
  if (!result.hasContext) {
    return result;
  }

  // Format the context lines for display
  const formattedContext = result.contextLines.map(lineObj => ({
    ...lineObj,
    formattedContent: lineObj.content.length > maxLineLength 
      ? lineObj.content.substring(0, maxLineLength) + '...' 
      : lineObj.content
  }));

  return {
    ...result,
    contextLines: formattedContext,
    formatted: true
  };
}