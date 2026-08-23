import { MultipartFile } from '../components/RequestBody/MultipartFileSelector';

/**
 * Converts multipart form data to Bruno's internal representation
 */
export const convertToBrunoMultipart = (
  formData: Record<string, any>,
  files: MultipartFile[],
  collectionPath?: string
): Record<string, any> => {
  // In Bruno, multipart data is stored with special structure
  const brunoData: Record<string, any> = {
    ...formData,
    __multipart__: true
  };
  
  // Add files with Bruno-specific metadata
  if (files.length > 0) {
    brunoData.__files__ = files.map(file => ({
      id: file.id,
      name: file.name,
      path: file.path,
      size: file.size,
      type: file.type,
      // Bruno-specific properties
      relativePath: collectionPath ? file.path.replace(new RegExp(`^${collectionPath}/`), '') : file.path,
      isLocal: true,
      lastModified: new Date().toISOString()
    }));
  }
  
  return brunoData;
};

/**
 * Extracts files from Bruno's internal multipart representation
 */
export const extractFilesFromBrunoMultipart = (
  brunoData: Record<string, any>
): MultipartFile[] => {
  if (!brunoData.__files__ || !Array.isArray(brunoData.__files__)) {
    return [];
  }
  
  return brunoData.__files__.map((file: any) => ({
    id: file.id,
    name: file.name,
    path: file.path,
    size: file.size,
    type: file.type
  }));
};

/**
 * Determines if a field should be converted to text when no files remain
 */
export const shouldConvertToText = (
  formData: Record<string, any>,
  files: MultipartFile[],
  fieldName: string = 'file'
): boolean => {
  // If no files and the field was previously a file field, convert back to text
  return files.length === 0 && 
         Object.keys(formData).some(key => key.toLowerCase().includes(fieldName.toLowerCase()));
};

/**
 * Gets the appropriate Bruno content type for multipart requests
 */
export const getBrunoMultipartContentType = (): string => {
  // Bruno uses standard multipart/form-data but may need boundary handling
  return 'multipart/form-data';
};

/**
 * Creates a Bruno-compatible FormData object
 */
export const createBrunoFormData = (
  formData: Record<string, any>,
  files: MultipartFile[],
  fileFieldName: string = 'file'
): FormData => {
  const brunoFormData = new FormData();
  
  // Add regular form fields
  Object.entries(formData).forEach(([key, value]) => {
    if (value !== null && value !== undefined) {
      brunoFormData.append(key, String(value));
    }
  });
  
  // Add files
  files.forEach(file => {
    // Create a Blob from the file path or use placeholder
    const blob = new Blob([''], { type: file.type });
    brunoFormData.append(fileFieldName, blob, file.name);
  });
  
  return brunoFormData;
};