/*
 * source-context.js
 * Utility to group and format error context for display
 */

/**
 * Groups error context information for display in ScriptError card
 * @param {Object} error - The error object
 * @param {Object} options - Configuration options
 * @returns {Object} Formatted error context
 */
const buildErrorContext = (error, options = {}) => {
  const { 
    scriptContent = '', 
    scriptPath = '', 
    scriptType = 'request', // 'collection', 'folder', 'request'
    lineNumber = 1,
    columnNumber = 1
  } = options;

  // Parse error location from stack trace
  const errorLocation = parseErrorLocation(error.stack);
  
  // Adjust line numbers to account for script composition
  const adjustedLineNumber = adjustLineNumber(
    lineNumber, 
    scriptContent, 
    errorLocation
  );

  // Resolve segment errors to correct source file
  const sourceFile = resolveSourceFile(scriptPath, scriptType);

  // Compute block-relative line numbers for CodeMirror editor
  const blockRelativeLine = computeBlockRelativeLine(
    scriptContent, 
    adjustedLineNumber
  );

  return {
    errorType: error.constructor.name,
    sourceFile,
    lineNumber: blockRelativeLine,
    columnNumber,
    codeSnippet: generateCodeSnippet(scriptContent, blockRelativeLine),
    stackTrace: formatStackTrace(error.stack)
  };
};

/**
 * Parse error location from stack trace
 * Supports both Node VM and QuickJS sandboxes
 */
const parseErrorLocation = (stack) => {
  if (!stack) return { line: 1, column: 1, file: '' };
  
  // Look for first stack frame that contains file info
  const lines = stack.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(/at.*?:(\d+):(\d+)/);
    if (match) {
      return {
        line: parseInt(match[1], 10),
        column: parseInt(match[2], 10),
        file: extractFileName(lines[i])
      };
    }
  }
  
  return { line: 1, column: 1, file: '' };
};

/**
 * Extract file name from stack frame
 */
const extractFileName = (line) => {
  const fileMatch = line.match(/at.*?(\S+\.bru|\S+\.yml)/);
  return fileMatch ? fileMatch[1] : '';
};

/**
 * Adjust line number to account for script composition
 */
const adjustLineNumber = (originalLine, scriptContent, errorLocation) => {
  // Simple adjustment - in real implementation would handle collection/folder/request script merging
  return originalLine;
};

/**
 * Resolve segment errors to correct source file
 */
const resolveSourceFile = (scriptPath, scriptType) => {
  switch (scriptType) {
    case 'collection':
      return scriptPath || 'collection.bru';
    case 'folder':
      return scriptPath || 'folder.bru';
    case 'request':
      return scriptPath || 'request.bru';
    default:
      return scriptPath || 'script.bru';
  }
};

/**
 * Compute block-relative line numbers for CodeMirror editor
 */
const computeBlockRelativeLine = (scriptContent, lineNumber) => {
  // In real implementation would find the start of the script block
  return lineNumber;
};

/**
 * Generate code snippet with surrounding lines and highlighting
 */
const generateCodeSnippet = (scriptContent, lineNumber, contextLines = 3) => {
  if (!scriptContent) return { lines: [], highlightedLine: 1 };
  
  const lines = scriptContent.split('\n');
  const startLine = Math.max(0, lineNumber - contextLines - 1);
  const endLine = Math.min(lines.length, lineNumber + contextLines);
  
  return {
    lines: lines.slice(startLine, endLine),
    highlightedLine: lineNumber - startLine
  };
};

/**
 * Format stack trace for display
 */
const formatStackTrace = (stack) => {
  if (!stack) return [];
  
  return stack
    .split('\n')
    .filter(line => line.trim() && !line.includes('node:') && !line.includes('internal/'))
    .map((line, index) => ({
      id: index,
      text: line.trim()
    }));
};

module.exports = {
  buildErrorContext,
  parseErrorLocation,
  extractFileName,
  adjustLineNumber,
  resolveSourceFile,
  computeBlockRelativeLine,
  generateCodeSnippet,
  formatStackTrace
};