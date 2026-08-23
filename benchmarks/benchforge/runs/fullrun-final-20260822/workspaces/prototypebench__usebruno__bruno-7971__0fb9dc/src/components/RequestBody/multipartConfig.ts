/**
 * Configuration for multipart form behavior in Bruno
 */

export const MULTIPART_CONFIG = {
  // Maximum number of files that can be selected at once
  maxFiles: 100,
  
  // Maximum file size in bytes (10MB default)
  maxFileSize: 10 * 1024 * 1024,
  
  // Allowed file types for security
  allowedFileTypes: [
    'image/*',
    'text/*',
    'application/json',
    'application/xml',
    'application/pdf',
    'application/zip',
    'application/x-zip-compressed'
  ],
  
  // Default field name for file uploads
  defaultFileFieldName: 'file',
  
  // Whether to show file preview thumbnails
  showThumbnails: true,
  
  // Whether to auto-detect content type
  autoDetectContentType: true,
  
  // File path normalization options
  pathNormalization: {
    // Remove collection path prefix
    removeCollectionPrefix: true,
    // Convert Windows paths to Unix style
    normalizePathSeparators: true
  }
};

/**
 * Validates a file against Bruno's multipart constraints
 */
export const validateMultipartFile = (file: File): { valid: boolean; error?: string } => {
  if (file.size > MULTIPART_CONFIG.maxFileSize) {
    return {
      valid: false,
      error: `File size exceeds maximum limit of ${MULTIPART_CONFIG.maxFileSize / (1024 * 1024)}MB`
    };
  }
  
  return { valid: true };
};