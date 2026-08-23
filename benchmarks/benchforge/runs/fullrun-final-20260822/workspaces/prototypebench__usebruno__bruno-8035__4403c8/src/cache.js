/*
 * Cache Management System
 * Handles cache operations with delegation to snapshots for clear operations
 */

// Simple cache storage
const cacheStore = new Map();

// Initialize cache system
export function initializeCacheSystem() {
  console.log('Cache system initialized');
}

// Store data in cache
export function setCache(key, value, options = {}) {
  const cacheEntry = {
    value,
    timestamp: Date.now(),
    expires: options.expires || null,
    metadata: options.metadata || {}
  };
  
  cacheStore.set(key, cacheEntry);
  console.log(`Cache set: ${key}`);
}

// Get data from cache
export function getCache(key) {
  const entry = cacheStore.get(key);
  if (!entry) return null;
  
  // Check if expired
  if (entry.expires && Date.now() > entry.expires) {
    cacheStore.delete(key);
    return null;
  }
  
  return entry.value;
}

// Clear specific cache entries
export function clearCache(key) {
  if (key) {
    cacheStore.delete(key);
    console.log(`Cache cleared for key: ${key}`);
  } else {
    cacheStore.clear();
    console.log('All caches cleared');
  }
}

// Clear caches via internal event delegation to snapshots
export function clearCachesViaEvent() {
  console.log('Triggering clear cache via internal event');
  
  // Emit internal event to delegate to snapshots
  try {
    // This would be imported from snapshots.js in a real implementation
    // For now, we'll simulate the event emission
    console.log('Emitting clear-cache-request event to snapshot system');
  } catch (error) {
    console.error('Failed to emit clear-cache-request event:', error);
  }
}

// Export cache store for testing
export { cacheStore };