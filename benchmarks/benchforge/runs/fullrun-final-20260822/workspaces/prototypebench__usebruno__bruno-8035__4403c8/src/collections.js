/*
 * Collection Management System
 * Handles collection operations with environment path re-serialization
 * BRU-3448: Re-serialization addition for environment path when restoring non-mounted collections
 */

// Collection storage
const collections = new Map();

// Restore collection with environment path re-serialization
export function restoreCollection(collectionData) {
  if (!collectionData) return null;
  
  // Create collection object
  const collection = {
    id: collectionData.id || generateId(),
    name: collectionData.name || 'Untitled Collection',
    path: collectionData.path || '',
    isMounted: collectionData.isMounted !== undefined ? collectionData.isMounted : true,
    environment: null
  };
  
  // Handle environment restoration with re-serialization for non-mounted collections
  if (collectionData.environment) {
    // For non-mounted collections, ensure environment path is properly serialized
    if (!collection.isMounted) {
      collection.environment = reSerializeEnvironmentPath(collectionData.environment);
      console.log(`Re-serialized environment for non-mounted collection ${collection.name}`);
    } else {
      collection.environment = collectionData.environment;
      console.log(`Using original environment for mounted collection ${collection.name}`);
    }
  }
  
  // Store collection
  collections.set(collection.id, collection);
  
  return collection;
}

// Re-serialize environment path for non-mounted collections
function reSerializeEnvironmentPath(env) {
  if (!env) return null;
  
  // Create a new serialized version of the environment
  // This ensures proper path handling when collections are not mounted
  const serializedEnv = {
    ...env,
    // Add serialization metadata
    _serialized: true,
    _serializationTimestamp: new Date().toISOString(),
    // Ensure path is properly formatted
    path: env.path ? normalizePath(env.path) : ''
  };
  
  return serializedEnv;
}

// Normalize path for cross-platform compatibility
function normalizePath(path) {
  if (!path) return '';
  
  // Replace backslashes with forward slashes for consistency
  return path.replace(/\\/g, '/').replace(/\/g, '/');
}

// Generate unique ID
function generateId() {
  return Math.random().toString(36).substr(2, 9);
}

// Get collection by ID
export function getCollection(id) {
  return collections.get(id);
}

// Export collections store for testing
export { collections };