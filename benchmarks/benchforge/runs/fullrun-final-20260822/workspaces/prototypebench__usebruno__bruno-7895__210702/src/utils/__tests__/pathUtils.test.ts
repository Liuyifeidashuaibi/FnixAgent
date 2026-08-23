import { getRelativePathWithinBasePath, getRelativePathWithinBasePathSafe } from '../pathUtils';

describe('getRelativePathWithinBasePath', () => {
  // Test cases for cross-platform path handling
  
  it('should return relative path when file is within base path (Unix)', () => {
    const basePath = '/home/user/project';
    const filePath = '/home/user/project/src/index.js';
    
    expect(getRelativePathWithinBasePath(basePath, filePath)).toBe('src/index.js');
  });

  it('should return relative path when file is within base path (Windows)', () => {
    const basePath = 'C:\\Users\\user\\project';
    const filePath = 'C:\\Users\\user\\project\\src\\index.js';
    
    expect(getRelativePathWithinBasePath(basePath, filePath)).toBe('src\\index.js');
  });

  it('should return undefined when file is outside base path (Unix)', () => {
    const basePath = '/home/user/project';
    const filePath = '/home/user/other-project/file.txt';
    
    expect(getRelativePathWithinBasePath(basePath, filePath)).toBeUndefined();
  });

  it('should return undefined when file is outside base path (Windows)', () => {
    const basePath = 'C:\\Users\\user\\project';
    const filePath = 'C:\\Users\\other-user\\project\\file.txt';
    
    expect(getRelativePathWithinBasePath(basePath, filePath)).toBeUndefined();
  });

  it('should handle mixed separators correctly', () => {
    const basePath = 'C:/Users/user/project';
    const filePath = 'C:\\Users\\user\\project\\src\\index.js';
    
    expect(getRelativePathWithinBasePath(basePath, filePath)).toBe('src\\index.js');
  });

  it('should handle posixify option', () => {
    const basePath = 'C:\\Users\\user\\project';
    const filePath = 'C:\\Users\\user\\project\\src\\index.js';
    
    expect(getRelativePathWithinBasePath(basePath, filePath, true)).toBe('src/index.js');
  });

  it('should handle sibling directories correctly (no false positives)', () => {
    const basePath = '/home/user/project';
    const filePath = '/home/user/other-project/file.txt';
    
    // This should not match with startsWith logic but should be properly handled
    expect(getRelativePathWithinBasePath(basePath, filePath)).toBeUndefined();
  });

  it('should handle case-insensitive on Windows correctly', () => {
    const basePath = 'C:\\Users\\User\\Project';
    const filePath = 'c:\\users\\user\\project\\src\\index.js';
    
    // In real Windows environment, this would be handled by path.normalize
    // For testing purposes, we assume normalize handles case-insensitivity
    expect(getRelativePathWithinBasePath(basePath, filePath)).toBe('src\\index.js');
  });
});

describe('getRelativePathWithinBasePathSafe', () => {
  it('should return relative path when file is within base path', () => {
    const basePath = '/home/user/project';
    const filePath = '/home/user/project/src/index.js';
    
    expect(getRelativePathWithinBasePathSafe(basePath, filePath)).toBe('src/index.js');
  });

  it('should return undefined when file is outside base path', () => {
    const basePath = '/home/user/project';
    const filePath = '/home/user/other-project/file.txt';
    
    expect(getRelativePathWithinBasePathSafe(basePath, filePath)).toBeUndefined();
  });
});