/*
 * Bruno Application Entry Point
 * Integrates all core modules for cache handling and collection management
 */

// Import core modules
import { clearCacheOnQuit, restoreCollectionEnvironment } from './main.js';
import { onSnapshotEvent, emitSnapshotEvent } from './snapshots.js';
import { initializeCacheSystem } from './cache.js';
import { restoreCollection } from './collections.js';

// Initialize the application
function initializeBrunoApp() {
  console.log('Initializing Bruno application...');
  
  // Initialize cache system
  initializeCacheSystem();
  
  // Setup snapshot event handlers
  setupEventHandlers();
  
  console.log('Bruno application initialized successfully');
}

// Setup internal event handlers
function setupEventHandlers() {
  // Handle clear cache requests
  onSnapshotEvent('clear-cache-request', (data) => {
    console.log('Clear cache request received:', data);
  });
  
  // Handle app quit events
  onSnapshotEvent('app-quit', () => {
    console.log('App quit event received');
    clearCacheOnQuit();
  });
  
  // Handle collection restoration events
  onSnapshotEvent('restore-collection', (data) => {
    console.log('Restore collection event received:', data);
    if (data.collection) {
      restoreCollectionEnvironment(data.collection);
    }
  });
}

// Export initialization function
export { initializeBrunoApp, restoreCollection, emitSnapshotEvent };