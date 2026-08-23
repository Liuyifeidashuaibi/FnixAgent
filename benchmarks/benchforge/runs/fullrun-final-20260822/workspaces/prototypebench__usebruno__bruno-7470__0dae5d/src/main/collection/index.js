const fs = require('fs');
const path = require('path');

// Function to get collection format - this is where the "No collection configuration found" error occurs
function getCollectionFormat(collectionPath) {
  const configPath = path.join(collectionPath, 'bruno.json');
  
  // Check if collection directory exists first
  if (!fs.existsSync(collectionPath)) {
    throw new Error(`Collection directory does not exist: ${collectionPath}`);
  }
  
  // Check if config file exists
  if (!fs.existsSync(configPath)) {
    throw new Error('No collection configuration found');
  }
  
  try {
    const configContent = fs.readFileSync(configPath, 'utf8');
    return JSON.parse(configContent);
  } catch (error) {
    throw new Error(`Failed to parse collection configuration: ${error.message}`);
  }
}

// Function to save Bruno config
function saveBrunoConfig(collectionPath, config) {
  const configPath = path.join(collectionPath, 'bruno.json');
  
  // Ensure collection directory exists before writing
  if (!fs.existsSync(collectionPath)) {
    throw new Error(`Cannot save config: collection directory does not exist: ${collectionPath}`);
  }
  
  fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8');
}

module.exports = {
  getCollectionFormat,
  saveBrunoConfig
};