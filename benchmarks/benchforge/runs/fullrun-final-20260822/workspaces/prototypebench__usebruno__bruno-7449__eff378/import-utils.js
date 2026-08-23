/*
 * import-utils.js
 * Utilities for importing Postman collections
 * Contains the fix for #2467: remove auto-commenting of untranslated pm commands
 */

/**
 * Process script content during import
 * Previously commented out untranslated pm.* calls, now leaves them as-is
 * @param {string} scriptContent - The original script content
 * @returns {string} Processed script content
 */
const processImportedScript = (scriptContent) => {
  if (!scriptContent) return scriptContent;
  
  // Split into lines for processing
  const lines = scriptContent.split('\n');
  
  // Process each line - remove the auto-commenting logic
  // Previously this would comment out lines like:
  // pm.test('status code is 200', function () {
  //   pm.response.to.have.status(200);
  // });
  // Now we leave them as-is so they throw clear runtime errors
  
  // Return original content unchanged
  return scriptContent;
};

/**
 * Check if a line contains an untranslated pm command
 * @param {string} line - A script line
 * @returns {boolean} True if line contains pm.* call that cannot be translated
 */
const hasUntranslatedPmCommand = (line) => {
  // Simple check for pm.* patterns
  const pmPattern = /\bpm\.[a-zA-Z0-9_]+\(/;
  return pmPattern.test(line);
};

/**
 * Get list of untranslated pm commands in script
 * @param {string} scriptContent - Script content
 * @returns {Array<string>} List of untranslated pm commands
 */
const getUntranslatedPmCommands = (scriptContent) => {
  if (!scriptContent) return [];
  
  const lines = scriptContent.split('\n');
  const commands = [];
  
  lines.forEach(line => {
    if (hasUntranslatedPmCommand(line)) {
      // Extract the pm command part
      const match = line.match(/\b(pm\.[a-zA-Z0-9_]+\([^)]*\))/);
      if (match) {
        commands.push(match[1]);
      }
    }
  });
  
  return commands;
};

module.exports = {
  processImportedScript,
  hasUntranslatedPmCommand,
  getUntranslatedPmCommands
};