const { parsePostmanCollection } = require('../postman-to-bruno');
const { isPostmanCollection } = require('../bruno-app/is-postman-collection');

// Test standard Postman collection format
const standardPostmanCollection = {
  info: {
    name: 'Standard Collection',
    schema: 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json'
  },
  item: [
    {
      name: 'GET Request',
      request: {
        method: 'GET',
        url: {
          raw: 'https://api.example.com/data'
        }
      }
    }
  ]
};

// Test wrapped Postman collection format (v2.1)
const wrappedPostmanCollection = {
  collection: {
    info: {
      name: 'Wrapped Collection',
      schema: 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json'
    },
    item: [
      {
        name: 'POST Request',
        request: {
          method: 'POST',
          url: {
            raw: 'https://api.example.com/data'
          }
        }
      }
    ]
  }
};

describe('Postman to Bruno Converter', () => {
  describe('isPostmanCollection', () => {
    it('should return true for standard Postman collection', () => {
      expect(isPostmanCollection(standardPostmanCollection)).toBe(true);
    });

    it('should return true for wrapped Postman collection', () => {
      expect(isPostmanCollection(wrappedPostmanCollection)).toBe(true);
    });

    it('should return false for invalid data', () => {
      expect(isPostmanCollection({})).toBe(false);
      expect(isPostmanCollection(null)).toBe(false);
      expect(isPostmanCollection(undefined)).toBe(false);
    });
  });

  describe('parsePostmanCollection', () => {
    it('should parse standard Postman collection correctly', () => {
      const result = parsePostmanCollection(standardPostmanCollection);
      expect(result.name).toBe('Standard Collection');
      expect(result.items.length).toBe(1);
      expect(result.items[0].type).toBe('request');
      expect(result.items[0].name).toBe('GET Request');
    });

    it('should parse wrapped Postman collection correctly', () => {
      const result = parsePostmanCollection(wrappedPostmanCollection);
      expect(result.name).toBe('Wrapped Collection');
      expect(result.items.length).toBe(1);
      expect(result.items[0].type).toBe('request');
      expect(result.items[0].name).toBe('POST Request');
    });

    it('should handle missing info in wrapped format', () => {
      const invalidWrapped = { collection: {} };
      expect(() => parsePostmanCollection(invalidWrapped)).toThrow('Invalid Postman collection format');
    });
  });
});