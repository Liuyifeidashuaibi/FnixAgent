const { getBoundaryFromContentType, getMultipartBoundary } = require('../utils/multipart-boundary');

describe('Multipart Boundary Handling', () => {
  describe('getBoundaryFromContentType', () => {
    test('should extract boundary from quoted parameter', () => {
      const contentType = 'multipart/mixed; boundary="abc123"';
      expect(getBoundaryFromContentType(contentType)).toBe('abc123');
    });

    test('should extract boundary from unquoted parameter', () => {
      const contentType = 'multipart/mixed; boundary=abc123';
      expect(getBoundaryFromContentType(contentType)).toBe('abc123');
    });

    test('should handle mixed case content-type', () => {
      const contentType = 'MULTIPART/MIXED; BOUNDARY="test123"';
      expect(getBoundaryFromContentType(contentType)).toBe('test123');
    });

    test('should return null for no boundary', () => {
      const contentType = 'application/json';
      expect(getBoundaryFromContentType(contentType)).toBeNull();
    });
  });

  describe('getMultipartBoundary', () => {
    test('should preserve user-defined boundary', () => {
      const contentType = 'multipart/mixed; boundary="user-defined-boundary"';
      const boundary = getMultipartBoundary(contentType, true);
      expect(boundary).toBe('user-defined-boundary');
    });

    test('should generate random boundary when no user boundary', () => {
      const contentType = 'multipart/mixed';
      const boundary = getMultipartBoundary(contentType, true);
      expect(boundary).toMatch(/^----BrunoBoundary_/);
    });

    test('should generate random boundary when preserveUserBoundary is false', () => {
      const contentType = 'multipart/mixed; boundary="user-defined"';
      const boundary = getMultipartBoundary(contentType, false);
      expect(boundary).toMatch(/^----BrunoBoundary_/);
    });
  });
});