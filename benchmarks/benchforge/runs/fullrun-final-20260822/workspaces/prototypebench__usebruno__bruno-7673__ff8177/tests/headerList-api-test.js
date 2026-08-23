/*
 * Test file demonstrating the headerList API usage
 * Following the exact examples from BRU-2893 specification
 */

// Example usage in Bruno script environment

// Read operations
console.log('Content-Type:', req.headerList.get('Content-Type')); // 'application/json'
console.log('Has Authorization:', req.headerList.has('Authorization')); // true
console.log('One Content-Type:', req.headerList.one('Content-Type')); // { key: 'Content-Type', value: 'application/json' }
console.log('All headers:', req.headerList.all()); // [{ key, value }, ...]
console.log('Header count:', req.headerList.count()); // 3

// Search operations
console.log('X- headers:', req.headerList.find(h => h.key.startsWith('X-')));
console.log('JSON headers:', req.headerList.filter(h => h.value.includes('json')));
console.log('Content-Type index:', req.headerList.indexOf('Content-Type'));

// Iteration operations
req.headerList.forEach((h, i) => {
  console.log(`Header ${i}: ${h.key} = ${h.value}`);
});

const keys = req.headerList.map(h => h.key);
console.log('All keys:', keys);

const headerMap = req.headerList.reduce((acc, h) => {
  acc[h.key] = h.value;
  return acc;
}, {});
console.log('Header map:', headerMap);

// Transform operations
console.log('To object:', req.headerList.toObject());
console.log('To string:', req.headerList.toString());

// Write operations (req only)
req.headerList.append({ key: 'X-Custom', value: 'val' });
req.headerList.append('X-Custom: val'); // string format
req.headerList.append('X-Custom', 'val'); // two-arg form
req.headerList.set({ key: 'Content-Type', value: 'text/plain' });
req.headerList.set('Content-Type', 'text/plain'); // two-arg form
req.headerList.delete('X-Custom');
req.headerList.delete(h => h.key.startsWith('X-'));
req.headerList.clear();
req.headerList.populate([{ key: 'A', value: '1' }, { key: 'B', value: '2' }]);
req.headerList.repopulate([{ key: 'A', value: '1' }]);
req.headerList.assimilate(otherList, true);

// Response headerList (read-only)
console.log('Response Content-Type:', res.headerList.get('content-type')); // 'application/json'
console.log('Has x-request-id:', res.headerList.has('x-request-id')); // true
console.log('All response headers:', res.headerList.all());
console.log('X- response headers:', res.headerList.filter(h => h.key.startsWith('x-')));
console.log('Response to object:', res.headerList.toObject());

// Verify read-only behavior
try {
  res.headerList.set('Content-Type', 'text/plain');
} catch (e) {
  console.log('Expected error for read-only:', e.message); // 'HeaderList is read-only'
}

// Case-insensitive testing
console.log('Case-insensitive get:', req.headerList.get('content-type')); // should work
console.log('Case-insensitive has:', req.headerList.has('CONTENT-TYPE')); // should work
