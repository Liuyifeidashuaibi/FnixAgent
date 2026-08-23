const fs = require('fs');
const path = require('path');
const chokidar = require('chokidar');

// Import collection utilities
const { getCollectionFormat } = require('../collection');

/**
 * Sets up a chokidar watcher for a collection with proper error handling
 * to prevent "No collection configuration found" errors when collections are deleted
 */
function setupCollectionWatcher(collectionPath) {
  // Create watcher with awaitWriteFinish for stability
  const watcher = chokidar.watch(collectionPath, {
    awaitWriteFinish: {
      stabilityThreshold: 80,
      pollInterval: 10
    },
    ignored: /(^|[\\/])\../, // Ignore dotfiles
    persistent: true
  });

  // Handle 'change' events with existence check
  watcher.on('change', (filePath) => {
    // Guard: Check if collection directory still exists before processing
    if (!fs.existsSync(collectionPath)) {
      console.debug(`[CollectionWatcher] Collection directory no longer exists, skipping change event for ${filePath}`);
      return;
    }
    
    try {
      // Only attempt to get collection format if config exists
      const configPath = path.join(collectionPath, 'bruno.json');
      if (fs.existsSync(configPath)) {
        const collectionConfig = getCollectionFormat(collectionPath);
        // Process the change with valid collection config
        console.debug(`[CollectionWatcher] Processing change for ${filePath}`);
      } else {
        console.debug(`[CollectionWatcher] Skipping change for ${filePath} - no bruno.json found`);
      }
    } catch (error) {
      // Log but don't throw - collection may be in process of deletion
      console.warn(`[CollectionWatcher] Error processing change for ${filePath}:`, error.message);
    }
  });

  // Handle 'unlink' events with existence check
  watcher.on('unlink', (filePath) => {
    // Guard: Check if collection directory still exists before processing
    if (!fs.existsSync(collectionPath)) {
      console.debug(`[CollectionWatcher] Collection directory no longer exists, skipping unlink event for ${filePath}`);
      return;
    }
    
    try {
      // Only attempt to get collection format if config exists
      const configPath = path.join(collectionPath, 'bruno.json');
      if (fs.existsSync(configPath)) {
        const collectionConfig = getCollectionFormat(collectionPath);
        // Process the unlink with valid collection config
        console.debug(`[CollectionWatcher] Processing unlink for ${filePath}`);
      } else {
        console.debug(`[CollectionWatcher] Skipping unlink for ${filePath} - no bruno.json found`);
      }
    } catch (error) {
      // Log but don't throw - collection may be in process of deletion
      console.warn(`[CollectionWatcher] Error processing unlink for ${filePath}:`, error.message);
    }
  });

  // Handle 'unlinkDir' events with existence check
  watcher.on('unlinkDir', (dirPath) => {
    // Guard: Check if collection directory still exists before processing
    if (!fs.existsSync(collectionPath)) {
      console.debug(`[CollectionWatcher] Collection directory no longer exists, skipping unlinkDir event for ${dirPath}`);
      return;
    }
    
    try {
      // Only attempt to get collection format if config exists
      const configPath = path.join(collectionPath, 'bruno.json');
      if (fs.existsSync(configPath)) {
        const collectionConfig = getCollectionFormat(collectionPath);
        // Process the unlinkDir with valid collection config
        console.debug(`[CollectionWatcher] Processing unlinkDir for ${dirPath}`);
      } else {
        console.debug(`[CollectionWatcher] Skipping unlinkDir for ${dirPath} - no bruno.json found`);
      }
    } catch (error) {
      // Log but don't throw - collection may be in process of deletion
      console.warn(`[CollectionWatcher] Error processing unlinkDir for ${dirPath}:`, error.message);
    }
  });

  // Handle 'add' events (for completeness)
  watcher.on('add', (filePath) => {
    if (!fs.existsSync(collectionPath)) {
      console.debug(`[CollectionWatcher] Collection directory no longer exists, skipping add event for ${filePath}`);
      return;
    }
    console.debug(`[CollectionWatcher] Processing add for ${filePath}`);
  });

  return watcher;
}

module.exports = {
  setupCollectionWatcher
};