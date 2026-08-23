const parsePostmanCollection = (data) => {
  // Handle wrapped format: { "collection": { ... } }
  // Unwrap the envelope if present
  let parsedCollection;
  if (data && data.collection && data.collection.info) {
    // Wrapped format: { "collection": { ... } }
    parsedCollection = data.collection;
  } else if (data && data.info) {
    // Standard format: { "info": { ... }, ... }
    parsedCollection = data;
  } else {
    throw new Error('Invalid Postman collection format: missing info object');
  }

  // Convert the parsedCollection to Bruno format
  // This is a simplified version - actual implementation would be more complex
  const brunoCollection = {
    name: parsedCollection.info?.name || 'Untitled Collection',
    items: []
  };

  // Process items (requests, folders, etc.)
  if (parsedCollection.item) {
    brunoCollection.items = parsedCollection.item.map(item => {
      if (item.item) {
        // Folder
        return {
          type: 'folder',
          name: item.name,
          items: item.item.map(subItem => ({
            type: 'request',
            name: subItem.name || 'Untitled Request',
            request: {
              method: subItem.request?.method || 'GET',
              url: subItem.request?.url?.raw || '',
              headers: subItem.request?.header || [],
              body: subItem.request?.body || null
            }
          }))
        };
      } else {
        // Request
        return {
          type: 'request',
          name: item.name || 'Untitled Request',
          request: {
            method: item.request?.method || 'GET',
            url: item.request?.url?.raw || '',
            headers: item.request?.header || [],
            body: item.request?.body || null
          }
        };
      }
    });
  }

  return brunoCollection;
};

module.exports = { parsePostmanCollection };