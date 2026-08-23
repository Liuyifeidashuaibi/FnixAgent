/**
 * Utility to extract boundary from Content-Type header for multipart requests
 * @param {string} contentType - The Content-Type header value
 * @returns {string|null} The boundary string if found, null otherwise
 */
function getBoundaryFromContentType(contentType) {
  if (!contentType || typeof contentType !== 'string') {
    return null;
  }
  
  // Look for boundary parameter in Content-Type header
  // Format: multipart/mixed; boundary=abc123 or multipart/mixed; boundary="abc123"
  const boundaryMatch = contentType.match(/boundary=(?:"([^"]+)"|([^;\s]+))/i);
  
  if (boundaryMatch) {
    // Return the first non-null group (either quoted or unquoted)
    return boundaryMatch[1] || boundaryMatch[2];
  }
  
  return null;
}

/**
 * Generate a random boundary string
 * @returns {string} Random boundary string
 */
function generateRandomBoundary() {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let boundary = '----BrunoBoundary_';
  for (let i = 0; i < 16; i++) {
    boundary += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return boundary;
}

/**
 * Get appropriate boundary for multipart request
 * @param {string} contentType - The Content-Type header value
 * @param {boolean} preserveUserBoundary - Whether to preserve user-defined boundary
 * @returns {string} Boundary string to use
 */
function getMultipartBoundary(contentType, preserveUserBoundary = true) {
  if (preserveUserBoundary && contentType) {
    const userBoundary = getBoundaryFromContentType(contentType);
    if (userBoundary) {
      return userBoundary;
    }
  }
  
  return generateRandomBoundary();
}

module.exports = {
  getBoundaryFromContentType,
  generateRandomBoundary,
  getMultipartBoundary
};