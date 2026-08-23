const { getMultipartBoundary } = require('../utils/multipart-boundary');

/**
 * Process multipart request body
 * @param {Object} request - The request object
 * @returns {Object} Processed request with proper boundary
 */
function processMultipartRequestBody(request) {
  // Check if this is a multipart request
  const contentType = request.headers?.['Content-Type'] || request.headers?.['content-type'];
  
  if (contentType && contentType.toLowerCase().includes('multipart/')) {
    // Extract boundary from Content-Type if present
    const userBoundary = getMultipartBoundary(contentType, true);
    
    // Preserve user-defined boundary instead of generating new one
    // Update Content-Type header to use the preserved boundary
    if (userBoundary) {
      // Ensure Content-Type has boundary parameter
      if (!contentType.toLowerCase().includes('boundary=')) {
        // Add boundary parameter to existing Content-Type
        const mediaType = contentType.split(';')[0].trim();
        request.headers['Content-Type'] = `${mediaType}; boundary=${userBoundary}`;
      }
    }
    
    // Store the boundary for body processing
    request.multipartBoundary = userBoundary;
  }
  
  return request;
}

/**
 * Create multipart form data with preserved boundary
 * @param {Object} request - The request object
 * @param {string} boundary - Boundary string to use
 * @returns {string} Multipart body
 */
function createMultipartBody(request, boundary) {
  if (!request.body || typeof request.body !== 'string') {
    return '';
  }
  
  // For TEXT body mode with user-specified boundary, use the preserved boundary
  // Instead of generating a new one
  return request.body;
}

module.exports = {
  processMultipartRequestBody,
  createMultipartBody
};