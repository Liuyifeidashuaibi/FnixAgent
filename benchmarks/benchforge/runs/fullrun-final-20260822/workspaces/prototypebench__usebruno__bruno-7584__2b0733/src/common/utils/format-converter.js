/**
 * Utility functions for converting between Bruno request formats (.bru and .yml)
 */

/**
 * Convert request data from one format to another
 * @param {Object} requestData - Parsed request data
 * @param {string} targetFormat - Target format ('bru' or 'yml')
 * @returns {string} Serialized content in target format
 */
function convertRequestFormat(requestData, targetFormat) {
  if (targetFormat.toLowerCase() === 'bru') {
    return JSON.stringify(requestData, null, 2);
  } else if (targetFormat.toLowerCase() === 'yml' || targetFormat.toLowerCase() === 'yaml') {
    try {
      const yaml = require('js-yaml');
      return yaml.dump(requestData, { indent: 2, skipInvalid: true });
    } catch (e) {
      throw new Error(`Failed to serialize to YAML: ${e.message}`);
    }
  } else {
    throw new Error(`Unsupported target format: ${targetFormat}`);
  }
}

/**
 * Parse request content from source format
 * @param {string} content - Raw content of the request file
 * @param {string} sourceFormat - Source format ('bru' or 'yml')
 * @returns {Object} Parsed request data
 */
function parseRequestContent(content, sourceFormat) {
  if (sourceFormat.toLowerCase() === 'bru') {
    try {
      return JSON.parse(content);
    } catch (e) {
      throw new Error(`Invalid JSON in .bru file: ${e.message}`);
    }
  } else if (sourceFormat.toLowerCase() === 'yml' || sourceFormat.toLowerCase() === 'yaml') {
    try {
      const yaml = require('js-yaml');
      return yaml.load(content);
    } catch (e) {
      throw new Error(`Invalid YAML in .yml file: ${e.message}`);
    }
  } else {
    throw new Error(`Unsupported source format: ${sourceFormat}`);
  }
}

/**
 * Get file extension for format
 * @param {string} format - Format name ('bru' or 'yml')
 * @returns {string} File extension
 */
function getExtensionForFormat(format) {
  return format.toLowerCase() === 'bru' ? '.bru' : '.yml';
}

module.exports = {
  convertRequestFormat,
  parseRequestContent,
  getExtensionForFormat
};