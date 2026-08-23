import * as path from 'path';

/**
 * Gets the relative path of a file within a base path, with cross-platform containment checking.
 * Returns undefined if the file is not contained within the base path.
 * 
 * @param basePath - The base directory path
 * @param filePath - The file path to check
 * @param posixify - Whether to convert Windows paths to POSIX format (default: false)
 * @returns The relative path within the base path, or undefined if not contained
 */
export function getRelativePathWithinBasePath(
  basePath: string,
  filePath: string,
  posixify: boolean = false
): string | undefined {
  try {
    // Normalize both paths for cross-platform comparison
    const normalizedBasePath = path.normalize(basePath);
    const normalizedFilePath = path.normalize(filePath);
    
    // Get relative path
    const relativePath = path.relative(normalizedBasePath, normalizedFilePath);
    
    // Check containment: if the relative path starts with '..' or is empty/absolute,
    // then the file is not contained within the base path
    if (
      relativePath === '' || 
      relativePath.startsWith('..') || 
      path.isAbsolute(relativePath)
    ) {
      return undefined;
    }
    
    // If posixify is requested, convert backslashes to forward slashes
    if (posixify) {
      return relativePath.replace(/\\/g, '/');
    }
    
    return relativePath;
  } catch (error) {
    console.warn('Failed to get relative path within base path:', error);
    return undefined;
  }
}

/**
 * Alternative implementation that uses path.resolve for more robust containment checking
 */
export function getRelativePathWithinBasePathSafe(
  basePath: string,
  filePath: string,
  posixify: boolean = false
): string | undefined {
  try {
    // Resolve both paths to absolute paths
    const resolvedBasePath = path.resolve(basePath);
    const resolvedFilePath = path.resolve(filePath);
    
    // Check if filePath is within basePath by comparing paths
    const isContained = resolvedFilePath.startsWith(resolvedBasePath + path.sep) || 
                        resolvedFilePath === resolvedBasePath;
    
    if (!isContained) {
      return undefined;
    }
    
    // Get relative path
    const relativePath = path.relative(resolvedBasePath, resolvedFilePath);
    
    // If posixify is requested, convert backslashes to forward slashes
    if (posixify) {
      return relativePath.replace(/\\/g, '/');
    }
    
    return relativePath;
  } catch (error) {
    console.warn('Failed to get relative path within base path (safe version):', error);
    return undefined;
  }
}