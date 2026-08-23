/*
 * Snapshot utility for Bruno
 * Stores collection state including example indices for restore functionality
 */

/**
 * Creates a snapshot of the current collection state
 * @param {Object} collection - The collection object
 * @returns {Object} Snapshot object with example indices
 */
export const createSnapshot = (collection) => {
  if (!collection || !collection.items) {
    return { version: '1.0', items: [] };
  }

  // Create deep copy of items and enhance with example indices
  const snapshotItems = collection.items.map(item => {
    const newItem = { ...item };
    
    // If this is a request item with examples, store example indices
    if (item.type === 'request' && item.examples && Array.isArray(item.examples)) {
      newItem.examples = item.examples.map((example, index) => ({
        ...example,
        // Store the original index for restore purposes
        __exampleIndex: index
      }));
    }
    
    return newItem;
  });

  return {
    version: '1.0',
    timestamp: new Date().toISOString(),
    items: snapshotItems
  };
};

/**
 * Restores collection from snapshot
 * @param {Object} snapshot - The snapshot object
 * @returns {Object} Restored collection
 */
export const restoreFromSnapshot = (snapshot) => {
  if (!snapshot || !snapshot.items) {
    return { items: [] };
  }

  // Restore items, preserving example indices
  const restoredItems = snapshot.items.map(item => {
    const restoredItem = { ...item };
    
    // Remove internal __exampleIndex property from restored item
    if (restoredItem.examples && Array.isArray(restoredItem.examples)) {
      restoredItem.examples = restoredItem.examples.map(example => {
        const { __exampleIndex, ...cleanExample } = example;
        return cleanExample;
      });
    }
    
    return restoredItem;
  });

  return {
    items: restoredItems
  };
};

/**
 * Gets example index from snapshot item
 * @param {Object} item - The snapshot item
 * @param {string} exampleId - The example ID to find
 * @returns {number|null} The example index or null if not found
 */
export const getExampleIndex = (item, exampleId) => {
  if (!item || !item.examples || !Array.isArray(item.examples)) {
    return null;
  }
  
  for (let i = 0; i < item.examples.length; i++) {
    if (item.examples[i].id === exampleId) {
      return i;
    }
  }
  
  return null;
};