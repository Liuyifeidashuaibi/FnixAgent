/*
 * Bruno Application Main Entry Point
 * Implements internal events for cache handling delegation to snapshots
 */

// Import required modules
import { setupSnapshotCacheHandler } from './snapshots.js';
import { initializeCacheSystem } from './cache.js';

// Initialize cache system
initializeCacheSystem();

// Setup internal event listeners for cache handling delegation
setupSnapshotCacheHandler();

// Export main application functions
export function clearCacheOnQuit() {
  // This will be handled by snapshot system via internal events
  console.log('Clear cache on quit event triggered');
}

export function restoreCollectionEnvironment(collection) {
  // Handle environment path re-serialization for non-mounted collections
  if (collection && collection.environment && !collection.isMounted) {
    // Re-serialize environment path
    const serializedEnv = serializeEnvironmentPath(collection.environment);
    console.log(`Re-serialized environment path for non-mounted collection: ${serializedEnv}`);
  }
}

function serializeEnvironmentPath(env) {
  // Simple serialization logic for environment path
  return JSON.stringify({
    path: env.path,
    name: env.name,
    variables: env.variables
  });
}