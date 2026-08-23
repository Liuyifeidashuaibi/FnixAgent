const { ipcMain } = require('electron');
const { handleCollectionDragMove, handleCloseTabOnMove } = require('./handlers/collection-drag-handler');

/**
 * Register all IPC handlers for collection drag and drop functionality
 */
function registerIpcHandlers() {
  // Handle moving requests between collections with format conversion
  ipcMain.handle('collection:drag-move', handleCollectionDragMove);
  
  // Handle closing tabs when requests are moved
  ipcMain.handle('collection:close-tab-on-move', handleCloseTabOnMove);
  
  // Additional handlers could be registered here
}

module.exports = {
  registerIpcHandlers
};