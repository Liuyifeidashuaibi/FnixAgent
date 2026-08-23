const { parsePostmanCollection } = require('../bruno-converters/postman-to-bruno');
const { isPostmanCollection } = require('../bruno-app/is-postman-collection');
const fs = require('fs');
const path = require('path');

// Load the wrapped v2.1 fixture
const wrappedCollectionData = JSON.parse(
  fs.readFileSync(path.join(__dirname, '../fixtures/wrapped-postman-v2.1.json'), 'utf8')
);

describe('E2E Test: Import Wrapped Postman Collection v2.1', () => {
  it('should detect wrapped Postman collection as valid', () => {
    expect(isPostmanCollection(wrappedCollectionData)).toBe(true);
  });

  it('should successfully parse wrapped Postman collection v2.1', () => {
    const result = parsePostmanCollection(wrappedCollectionData);
    
    // Verify basic structure
    expect(result).toBeDefined();
    expect(result.name).toBe('Wrapped Collection v2.1');
    expect(result.items.length).toBe(2);
    
    // Verify first item is GET request
    expect(result.items[0].type).toBe('request');
    expect(result.items[0].name).toBe('GET Users');
    expect(result.items[0].request.method).toBe('GET');
    
    // Verify second item is POST request
    expect(result.items[1].type).toBe('request');
    expect(result.items[1].name).toBe('POST User');
    expect(result.items[1].request.method).toBe('POST');
    expect(result.items[1].request.headers.length).toBe(1);
  });
});