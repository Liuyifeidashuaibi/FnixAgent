/*
 * error-formatter.js
 * Error location parsing, line adjustment, and stack trace formatting
 */

/**
 * Parse error location from stack trace
 * Supports both Node VM and QuickJS sandboxes
 * @param {string} stack - The error stack trace
 * @returns {Object} Parsed location {line, column, file}
 */
const parseErrorLocation = (stack) => {
  if (!stack) return { line: 1, column: 1, file: '' };
  
  // Look for first stack frame that contains file info
  const lines = stack.split('\n');
  for (let i = 0; i < lines.length; i++) {
    // Match patterns like:
    // at script.js:10:5
    // at <anonymous>:15:20
    // at Object.<anonymous> (collection.bru:25:8)
    const match = lines[i].match(/at.*?:(\d+):(\d+)/);
    const parenMatch = lines[i].match(/\(([^)]+):(\d+):(\d+)\)/);
    
    if (match) {
      return {
        line: parseInt(match[1], 10),
        column: parseInt(match[2], 10),
        file: extractFileName(lines[i])
      };
    }
    
    if (parenMatch) {
      return {
        line: parseInt(parenMatch[2], 10),
        column: parseInt(parenMatch[3], 10),
        file: parenMatch[1]
      };
    }
  }
  
  return { line: 1, column: 1, file: '' };
};

/**
 * Extract file name from stack frame
 * @param {string} line - A stack trace line
 * @returns {string} File name
 */
const extractFileName = (line) => {
  // Try to extract .bru or .yml files
  const bruMatch = line.match(/(\S+\.bru)/);
  if (bruMatch) return bruMatch[1];
  
  const ymlMatch = line.match(/(\S+\.yml)/);
  if (ymlMatch) return ymlMatch[1];
  
  // Fallback to any file path pattern
  const fileMatch = line.match(/at.*?(\S+\.\w+)/);
  return fileMatch ? fileMatch[1] : '';
};

/**
 * Adjust line numbers to account for script composition
 * Handles collection + folder + request scripts merging
 * @param {number} originalLine - Original line number from error
 * @param {string} scriptContent - The full script content
 * @param {Object} errorLocation - Parsed error location
 * @returns {number} Adjusted line number
 */
const adjustLineNumber = (originalLine, scriptContent, errorLocation) => {
  // In real implementation would handle the script composition logic
  // For now, return original line as placeholder
  return originalLine;
};

/**
 * Format stack trace for display in UI
 * @param {string} stack - Raw stack trace
 * @returns {Array} Formatted stack frames
 */
const formatStackTrace = (stack) => {
  if (!stack) return [];
  
  return stack
    .split('\n')
    .filter(line => line.trim() && !line.includes('node:') && !line.includes('internal/'))
    .map((line, index) => ({
      id: index,
      text: line.trim(),
      // Extract file and line info for navigation
      file: extractFileName(line),
      line: parseLineFromStack(line)
    }));
};

/**
 * Parse line number from stack trace line
 * @param {string} line - Stack trace line
 * @returns {number} Line number or null
 */
const parseLineFromStack = (line) => {
  const match = line.match(/:(\d+):(\d+)/);
  if (match) {
    return parseInt(match[1], 10);
  }
  
  const parenMatch = line.match(/\(([^)]+):(\d+):(\d+)\)/);
  if (parenMatch) {
    return parseInt(parenMatch[2], 10);
  }
  
  return null;
};

module.exports = {
  parseErrorLocation,
  extractFileName,
  adjustLineNumber,
  formatStackTrace,
  parseLineFromStack
};