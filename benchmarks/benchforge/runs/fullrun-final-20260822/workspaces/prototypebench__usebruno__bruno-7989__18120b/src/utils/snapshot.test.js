/*
 * Tests for snapshot utility with example index support
 */

import { createSnapshot, restoreFromSnapshot, getExampleIndex } from './snapshot';

describe('snapshot utility', () => {
  describe('createSnapshot', () => {
    it('should store example indices in snapshot', () => {
      const collection = {
        items: [
          {
            type: 'request',
            id: 'req-1',
            examples: [
              { id: 'ex-1', name: 'Example 1' },
              { id: 'ex-2', name: 'Example 2' },
              { id: 'ex-3', name: 'Example 3' }
            ]
          }
        ]
      };

      const snapshot = createSnapshot(collection);
      
      expect(snapshot.items.length).toBe(1);
      expect(snapshot.items[0].examples.length).toBe(3);
      expect(snapshot.items[0].examples[0].__exampleIndex).toBe(0);
      expect(snapshot.items[0].examples[1].__exampleIndex).toBe(1);
      expect(snapshot.items[0].examples[2].__exampleIndex).toBe(2);
    });

    it('should handle collections without examples', () => {
      const collection = {
        items: [
          { type: 'folder', id: 'folder-1' },
          { type: 'request', id: 'req-1' }
        ]
      };

      const snapshot = createSnapshot(collection);
      
      expect(snapshot.items.length).toBe(2);
      expect(snapshot.items[0].type).toBe('folder');
      expect(snapshot.items[1].type).toBe('request');
    });
  });

  describe('restoreFromSnapshot', () => {
    it('should restore collection without __exampleIndex properties', () => {
      const snapshot = {
        items: [
          {
            type: 'request',
            id: 'req-1',
            examples: [
              { id: 'ex-1', name: 'Example 1', __exampleIndex: 0 },
              { id: 'ex-2', name: 'Example 2', __exampleIndex: 1 }
            ]
          }
        ]
      };

      const restored = restoreFromSnapshot(snapshot);
      
      expect(restored.items.length).toBe(1);
      expect(restored.items[0].examples.length).toBe(2);
      expect(restored.items[0].examples[0]).not.toHaveProperty('__exampleIndex');
      expect(restored.items[0].examples[1]).not.toHaveProperty('__exampleIndex');
    });
  });

  describe('getExampleIndex', () => {
    it('should return correct example index', () => {
      const item = {
        type: 'request',
        examples: [
          { id: 'ex-1', name: 'Example 1' },
          { id: 'ex-2', name: 'Example 2' },
          { id: 'ex-3', name: 'Example 3' }
        ]
      };

      expect(getExampleIndex(item, 'ex-1')).toBe(0);
      expect(getExampleIndex(item, 'ex-2')).toBe(1);
      expect(getExampleIndex(item, 'ex-3')).toBe(2);
      expect(getExampleIndex(item, 'ex-4')).toBeNull();
    });

    it('should handle items without examples', () => {
      const item = { type: 'folder', id: 'folder-1' };
      
      expect(getExampleIndex(item, 'ex-1')).toBeNull();
    });
  });
});