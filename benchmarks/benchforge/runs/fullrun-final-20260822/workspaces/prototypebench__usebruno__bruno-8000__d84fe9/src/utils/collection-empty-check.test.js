import { isCollectionEmpty, getMeaningfulItemCount } from './collection-empty-check';

describe('collection-empty-check', () => {
  describe('isCollectionEmpty', () => {
    it('should return true for empty array', () => {
      expect(isCollectionEmpty([])).toBe(true);
    });

    it('should return true for collection with only bruno.json', () => {
      const items = [
        { name: 'bruno.json', type: 'file' }
      ];
      expect(isCollectionEmpty(items)).toBe(true);
    });

    it('should return true for collection with bruno.json and other config files', () => {
      const items = [
        { name: 'bruno.json', type: 'file' },
        { name: 'environment.json', type: 'file' },
        { name: 'settings.yml', type: 'file' }
      ];
      expect(isCollectionEmpty(items)).toBe(true);
    });

    it('should return false for collection with requests', () => {
      const items = [
        { name: 'bruno.json', type: 'file' },
        { name: 'get-users.bru', type: 'request' }
      ];
      expect(isCollectionEmpty(items)).toBe(false);
    });

    it('should return false for collection with folders', () => {
      const items = [
        { name: 'bruno.json', type: 'file' },
        { name: 'API Endpoints', type: 'folder' }
      ];
      expect(isCollectionEmpty(items)).toBe(false);
    });

    it('should return false for collection with .bru files that are not bruno.json', () => {
      const items = [
        { name: 'bruno.json', type: 'file' },
        { name: 'post-data.bru', type: 'file' }
      ];
      expect(isCollectionEmpty(items)).toBe(false);
    });
  });

  describe('getMeaningfulItemCount', () => {
    it('should return 0 for empty array', () => {
      expect(getMeaningfulItemCount([])).toBe(0);
    });

    it('should return 0 for collection with only bruno.json', () => {
      const items = [
        { name: 'bruno.json', type: 'file' }
      ];
      expect(getMeaningfulItemCount(items)).toBe(0);
    });

    it('should return 1 for collection with one request', () => {
      const items = [
        { name: 'bruno.json', type: 'file' },
        { name: 'get-users.bru', type: 'request' }
      ];
      expect(getMeaningfulItemCount(items)).toBe(1);
    });

    it('should return 2 for collection with one request and one folder', () => {
      const items = [
        { name: 'bruno.json', type: 'file' },
        { name: 'get-users.bru', type: 'request' },
        { name: 'API Endpoints', type: 'folder' }
      ];
      expect(getMeaningfulItemCount(items)).toBe(2);
    });
  });
});