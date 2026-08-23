/**
 * Check if a collection is truly empty (only showing + Add request CTA when appropriate)
 * 
 * Empty state should only consider requests and folders as "content"
 * bruno.json and other non-request files should be ignored for empty state determination
 * 
 * @param {Array} items - Array of items in the collection
 * @returns {boolean} - true if collection is empty (no requests or folders)
 */
export const isCollectionEmpty = (items) => {
  if (!Array.isArray(items) || items.length === 0) {
    return true;
  }

  // Count only requests and folders as meaningful content
  // Requests: .bru files that are request definitions (not bruno.json or other config files)
  // Folders: directories
  const hasRequestsOrFolders = items.some(item => {
    // Check if it's a folder/directory
    if (item.type === 'folder' || item.isDirectory === true) {
      return true;
    }
    
    // Check if it's a request file (.bru extension, but not bruno.json)
    if (item.type === 'request' || 
        (item.name && item.name.endsWith('.bru') && item.name !== 'bruno.json')) {
      return true;
    }
    
    return false;
  });

  return !hasRequestsOrFolders;
};

/**
 * Get count of meaningful items (requests and folders only)
 * @param {Array} items - Array of items in the collection
 * @returns {number} - Count of requests and folders
 */
export const getMeaningfulItemCount = (items) => {
  if (!Array.isArray(items)) {
    return 0;
  }

  return items.filter(item => {
    // Folders
    if (item.type === 'folder' || item.isDirectory === true) {
      return true;
    }
    
    // Requests (.bru files except bruno.json)
    if (item.name && item.name.endsWith('.bru') && item.name !== 'bruno.json') {
      return true;
    }
    
    return false;
  }).length;
};