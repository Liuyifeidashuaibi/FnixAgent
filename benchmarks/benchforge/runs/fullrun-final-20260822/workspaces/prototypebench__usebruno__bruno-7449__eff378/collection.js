/*
 * collection.js
 * Utilities for working with Bruno collection files (.bru and .yml)
 */

/**
 * Find the start and end line numbers of a script block in a .bru file
 * @param {string} content - The file content
 * @param {string} scriptType - 'preRequest', 'postResponse', 'tests'
 * @returns {Object} {startLine, endLine, content} or null if not found
 */
const findScriptBlock = (content, scriptType) => {
  if (!content) return null;
  
  const lines = content.split('\n');
  let startLine = -1;
  let endLine = -1;
  
  // Look for script block header like 'preRequest:' or 'tests:'
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    
    // Match script type header
    if (line.startsWith(scriptType + ':')) {
      startLine = i + 1; // 1-based line numbers
      
      // Find end of block (next non-indented line or end of file)
      for (let j = i + 1; j < lines.length; j++) {
        const nextLine = lines[j].trim();
        // End of block when we hit next top-level key or empty line
        if (nextLine === '' || nextLine.endsWith(':') || !nextLine.startsWith('  ')) {
          endLine = j;
          break;
        }
      }
      
      if (endLine === -1) {
        endLine = lines.length;
      }
      
      break;
    }
  }
  
  if (startLine === -1) return null;
  
  // Extract the script content
  const scriptContent = lines.slice(startLine, endLine).join('\n').trim();
  
  return {
    startLine,
    endLine,
    content: scriptContent
  };
};

/**
 * Find script block in YAML content
 * @param {string} content - YAML content
 * @param {string} scriptType - 'preRequest', 'postResponse', 'tests'
 * @returns {Object} {startLine, endLine, content} or null if not found
 */
const findScriptBlockYaml = (content, scriptType) => {
  if (!content) return null;
  
  const lines = content.split('\n');
  let startLine = -1;
  let endLine = -1;
  
  // Look for script type in YAML format
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    
    if (line.startsWith(scriptType + ':')) {
      startLine = i + 1;
      
      // Find end of block - look for next top-level key or end of file
      for (let j = i + 1; j < lines.length; j++) {
        const nextLine = lines[j].trim();
        if (nextLine === '' || (nextLine && !nextLine.startsWith('  ') && nextLine.endsWith(':'))) {
          endLine = j;
          break;
        }
      }
      
      if (endLine === -1) {
        endLine = lines.length;
      }
      
      break;
    }
  }
  
  if (startLine === -1) return null;
  
  // Extract script content (remove indentation)
  const scriptLines = lines.slice(startLine, endLine);
  const minIndent = Math.min(...scriptLines.map(l => l.length - l.trim().length));
  const cleanedLines = scriptLines.map(l => l.substring(minIndent));
  
  return {
    startLine,
    endLine,
    content: cleanedLines.join('\n').trim()
  };
};

/**
 * Get script content from a .bru file
 * @param {string} content - File content
 * @param {string} scriptType - 'preRequest', 'postResponse', 'tests'
 * @returns {string} Script content or empty string
 */
const getScriptContent = (content, scriptType) => {
  const block = findScriptBlock(content, scriptType);
  return block ? block.content : '';
};

/**
 * Get script content from a YAML file
 * @param {string} content - YAML content
 * @param {string} scriptType - 'preRequest', 'postResponse', 'tests'
 * @returns {string} Script content or empty string
 */
const getScriptContentYaml = (content, scriptType) => {
  const block = findScriptBlockYaml(content, scriptType);
  return block ? block.content : '';
};

module.exports = {
  findScriptBlock,
  findScriptBlockYaml,
  getScriptContent,
  getScriptContentYaml
};