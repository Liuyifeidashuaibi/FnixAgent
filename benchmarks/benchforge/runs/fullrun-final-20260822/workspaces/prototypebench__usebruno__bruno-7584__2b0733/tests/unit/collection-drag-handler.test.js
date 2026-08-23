const { handleCollectionDragMove } = require('../src/main/ipc/handlers/collection-drag-handler');
const fs = require('fs').promises;
const path = require('path');

// Mock fs functions for testing
jest.mock('fs').promises;

describe('Collection Drag Handler', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('handleCollectionDragMove', () => {
    it('should handle same format move successfully', async () => {
      // Mock fs.rename
      fs.rename = jest.fn().mockResolvedValue();
      
      const result = await handleCollectionDragMove(null, {
        sourcePath: '/path/to/request.bru',
        targetCollectionPath: '/path/to/collection',
        targetFormat: 'bru'
      });
      
      expect(result.success).toBe(true);
      expect(fs.rename).toHaveBeenCalledWith(
        '/path/to/request.bru',
        '/path/to/collection/request.bru'
      );
    });

    it('should handle .bru to .yml conversion', async () => {
      // Mock fs.readFile and fs.writeFile
      fs.readFile = jest.fn().mockResolvedValue('{"name":"test"}');
      fs.writeFile = jest.fn().mockResolvedValue();
      fs.unlink = jest.fn().mockResolvedValue();
      
      // Mock js-yaml import
      jest.mock('js-yaml', () => ({
        load: jest.fn().mockReturnValue({ name: 'test' }),
        dump: jest.fn().mockReturnValue('name: test\n')
      }));
      
      const result = await handleCollectionDragMove(null, {
        sourcePath: '/path/to/request.bru',
        targetCollectionPath: '/path/to/collection',
        targetFormat: 'yml'
      });
      
      expect(result.success).toBe(true);
      expect(fs.writeFile).toHaveBeenCalledWith(
        '/path/to/collection/request.yml',
        'name: test\n',
        'utf8'
      );
    });

    it('should handle .yml to .bru conversion', async () => {
      // Mock fs.readFile and fs.writeFile
      fs.readFile = jest.fn().mockResolvedValue('name: test\n');
      fs.writeFile = jest.fn().mockResolvedValue();
      fs.unlink = jest.fn().mockResolvedValue();
      
      // Mock js-yaml import
      jest.mock('js-yaml', () => ({
        load: jest.fn().mockReturnValue({ name: 'test' }),
        dump: jest.fn().mockReturnValue('name: test\n')
      }));
      
      const result = await handleCollectionDragMove(null, {
        sourcePath: '/path/to/request.yml',
        targetCollectionPath: '/path/to/collection',
        targetFormat: 'bru'
      });
      
      expect(result.success).toBe(true);
      expect(fs.writeFile).toHaveBeenCalledWith(
        '/path/to/collection/request.bru',
        '{\n  "name": "test"\n}',
        'utf8'
      );
    });

    it('should return error for unsupported format', async () => {
      const result = await handleCollectionDragMove(null, {
        sourcePath: '/path/to/request.txt',
        targetCollectionPath: '/path/to/collection',
        targetFormat: 'bru'
      });
      
      expect(result.success).toBe(false);
      expect(result.error).toContain('Unsupported source format');
    });
  });
});