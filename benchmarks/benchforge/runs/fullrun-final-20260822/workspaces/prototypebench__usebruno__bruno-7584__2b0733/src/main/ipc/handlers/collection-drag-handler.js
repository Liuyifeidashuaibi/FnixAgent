const { app } = require('electron');
const fs = require('fs').promises;
const path = require('path');

/**
 * IPC handler for moving requests between collections with format conversion
 * @param {import('electron').IpcMainInvokeEvent} event
 * @param {Object} payload
 * @param {string} payload.sourcePath - Path to source request file
 * @param {string} payload.targetCollectionPath - Path to target collection directory
 * @param {string} payload.targetFormat - Target format ('bru' or 'yml')
 * @returns {Promise<{success: boolean, error?: string}>}
 */
async function handleCollectionDragMove(event, payload) {
  try {
    const { sourcePath, targetCollectionPath, targetFormat } = payload;
    
    // Validate paths
    if (!sourcePath || !targetCollectionPath || !targetFormat) {
      return { success: false, error: 'Missing required parameters' };
    }
    
    // Check if source and target formats are different
    const sourceExt = path.extname(sourcePath).toLowerCase().substring(1);
    if (sourceExt === targetFormat.toLowerCase()) {
      // Same format, just move the file
      const targetPath = path.join(targetCollectionPath, path.basename(sourcePath));
      await fs.rename(sourcePath, targetPath);
      return { success: true };
    }
    
    // Different formats - need conversion
    const sourceContent = await fs.readFile(sourcePath, 'utf8');
    
    // Parse source content based on format
    let parsedData;
    if (sourceExt === 'bru') {
      try {
        parsedData = JSON.parse(sourceContent);
      } catch (e) {
        return { success: false, error: `Invalid JSON in .bru file: ${e.message}` };
      }
    } else if (sourceExt === 'yml' || sourceExt === 'yaml') {
      try {
        const yaml = await import('js-yaml');
        parsedData = yaml.load(sourceContent);
      } catch (e) {
        return { success: false, error: `Invalid YAML in .yml file: ${e.message}` };
      }
    } else {
      return { success: false, error: `Unsupported source format: .${sourceExt}` };
    }
    
    // Serialize to target format
    let targetContent;
    const targetFilename = path.basename(sourcePath, `.${sourceExt}`).concat('.', targetFormat);
    const targetPath = path.join(targetCollectionPath, targetFilename);
    
    if (targetFormat.toLowerCase() === 'bru') {
      targetContent = JSON.stringify(parsedData, null, 2);
    } else if (targetFormat.toLowerCase() === 'yml') {
      try {
        const yaml = await import('js-yaml');
        targetContent = yaml.dump(parsedData, { indent: 2, skipInvalid: true });
      } catch (e) {
        return { success: false, error: `Failed to serialize to YAML: ${e.message}` };
      }
    } else {
      return { success: false, error: `Unsupported target format: ${targetFormat}` };
    }
    
    // Write the converted file
    await fs.writeFile(targetPath, targetContent, 'utf8');
    
    // Remove the original file
    await fs.unlink(sourcePath);
    
    return { success: true };
  } catch (error) {
    console.error('Error in collection drag move handler:', error);
    return { success: false, error: error.message || 'Unknown error occurred' };
  }
}

/**
 * IPC handler for closing tabs when requests are moved
 * @param {import('electron').IpcMainInvokeEvent} event
 * @param {Object} payload
 * @param {string} payload.requestId - ID of the request being moved
 * @returns {Promise<void>}
 */
async function handleCloseTabOnMove(event, payload) {
  try {
    const { requestId } = payload;
    
    if (!requestId) {
      throw new Error('Missing requestId');
    }
    
    // In a real implementation, this would communicate with the renderer process
    // to close the tab with the given requestId
    console.log(`Closing tab for request: ${requestId}`);
    
    // This would typically emit to renderer processes
    // mainWindow.webContents.send('close-tab', { requestId });
    
    return { success: true };
  } catch (error) {
    console.error('Error closing tab on move:', error);
    return { success: false, error: error.message };
  }
}

module.exports = {
  handleCollectionDragMove,
  handleCloseTabOnMove
};