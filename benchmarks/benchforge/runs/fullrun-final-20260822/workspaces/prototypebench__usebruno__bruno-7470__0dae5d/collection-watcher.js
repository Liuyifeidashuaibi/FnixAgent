const fs = require('fs');
const chokidar = require('chokidar');

// Function to get collection format - this is where the "No collection configuration found" error occurs
function getCollectionFormat(collectionPath) {
  // This would normally read bruno.json or similar config file
  const configPath = `${collectionPath}/bruno.json`;
  if (!fs.existsSync(configPath)) {
    throw new Error('No collection configuration found');
  }
  // Read and parse config
  return JSON.parse(fs.readFileSync(configPath));
}

// Fixed chokidar event handlers with fs.existsSync guards
function setupCollectionWatcher(collectionPath) {
  const watcher = chokidar.watch(collectionPath, {
    awaitWriteFinish: {
      stabilityThreshold: 80,
      pollInterval: 10
    }
  });

  // Fixed change handler with exists check
  watcher.on('change', (filePath) => {
    // Guard: check if collection directory still exists before processing
    if (!fs.existsSync(collectionPath)) {
      console.log(`Collection directory no longer exists, skipping change event for ${filePath}`);
      return;
    }
    
    try {
      // Only process if collection config exists
      if (fs.existsSync(`${collectionPath}/bruno.json`)) {
        // Process the change
        console.log(`Processing change for ${filePath}`);
      }
    } catch (error) {
      console.error(`Error processing change for ${filePath}:`, error.message);
    }
  });

  // Fixed unlink handler with exists check
  watcher.on('unlink', (filePath) => {
    // Guard: check if collection directory still exists before processing
    if (!fs.existsSync(collectionPath)) {
      console.log(`Collection directory no longer exists, skipping unlink event for ${filePath}`);
      return;
    }
    
    try {
      // Only process if collection config exists
      if (fs.existsSync(`${collectionPath}/bruno.json`)) {
        // Process the unlink
        console.log(`Processing unlink for ${filePath}`);
      }
    } catch (error) {
      console.error(`Error processing unlink for ${filePath}:`, error.message);
    }
  });

  // Fixed unlinkDir handler with exists check
  watcher.on('unlinkDir', (dirPath) => {
    // Guard: check if collection directory still exists before processing
    if (!fs.existsSync(collectionPath)) {
      console.log(`Collection directory no longer exists, skipping unlinkDir event for ${dirPath}`);
      return;
    }
    
    try {
      // Only process if collection config exists
      if (fs.existsSync(`${collectionPath}/bruno.json`)) {
        // Process the unlinkDir
        console.log(`Processing unlinkDir for ${dirPath}`);
      }
    } catch (error) {
      console.error(`Error processing unlinkDir for ${dirPath}:`, error.message);
    }
  });

  return watcher;
}

module.exports = {
  getCollectionFormat,
  setupCollectionWatcher
};