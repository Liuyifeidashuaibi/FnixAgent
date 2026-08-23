import { MultipartFile } from '../components/RequestBody/MultipartFileSelector';

/**
 * Creates FormData object with multiple files for multipart requests
 */
export const createMultipartFormData = (
  formData: Record<string, any>,
  files: MultipartFile[],
  fileFieldName: string = 'file'
): FormData => {
  const multipartData = new FormData();
  
  // Add regular form fields
  Object.entries(formData).forEach(([key, value]) => {
    if (value !== null && value !== undefined) {
      multipartData.append(key, String(value));
    }
  });
  
  // Add files
  files.forEach(file => {
    // For multipart, we need to create a File object or use Blob
    // In Bruno's context, this would be handled by the actual file system integration
    multipartData.append(fileFieldName, new Blob([''], { type: file.type }), file.name);
  });
  
  return multipartData;
};

/**
 * Gets appropriate content type for multipart form with files
 */
export const getMultipartContentType = (files: MultipartFile[]): string => {
  if (files.length === 0) {
    return 'multipart/form-data';
  }
  
  // Bruno might use boundary detection, but for now return standard multipart
  return 'multipart/form-data';
};

/**
 * Normalizes file paths relative to collection directory
 */
export const normalizeFilePaths = (files: MultipartFile[], collectionPath?: string): MultipartFile[] => {
  return files.map(file => {
    // In Bruno, this would resolve relative paths to collection root
    const normalizedPath = collectionPath 
      ? file.path.replace(new RegExp(`^${collectionPath}/`), '')
      : file.path;
    
    return {
      ...file,
      path: normalizedPath
    };
  });
};

/**
 * Auto-detects content type for file based on extension
 */
export const detectContentType = (fileName: string): string => {
  const extension = fileName.split('.').pop()?.toLowerCase() || '';
  
  const mimeTypes: Record<string, string> = {
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'pdf': 'application/pdf',
    'txt': 'text/plain',
    'json': 'application/json',
    'xml': 'application/xml',
    'csv': 'text/csv',
    'zip': 'application/zip',
    'js': 'application/javascript',
    'css': 'text/css'
  };
  
  return mimeTypes[extension] || 'application/octet-stream';
};