import { clipboard } from 'electron';

/**
 * Handle paste operation for collection items
 * @param {Object} focusedItem - The currently focused item (folder or request)
 * @param {Function} onPaste - Callback function to handle the actual paste operation
 */
export const handlePasteItem = async (focusedItem, onPaste) => {
  try {
    // Read from clipboard
    const clipboardContent = clipboard.readText();
    
    // Check if clipboard contains JSON data (copied collection item)
    let parsedData;
    try {
      parsedData = JSON.parse(clipboardContent);
    } catch (e) {
      // If not valid JSON, treat as plain text/request
      parsedData = {
        type: 'request',
        name: 'Pasted Request',
        content: clipboardContent
      };
    }
    
    // Determine paste location based on focused item type and clipboard content
    if (focusedItem && focusedItem.type === 'folder') {
      // If focused on a folder, paste inside the folder
      onPaste(parsedData, { target: 'inside', folderId: focusedItem.id });
    } else {
      // Otherwise, paste as sibling (next to the focused item)
      onPaste(parsedData, { target: 'sibling', parentId: focusedItem?.parentId || null });
    }
  } catch (error) {
    console.error('Error handling paste:', error);
    // Fallback: try to get clipboard data using alternative method
    if (clipboard.availableFormats && clipboard.availableFormats().includes('text/plain')) {
      const text = clipboard.readText();
      if (text) {
        onPaste({ type: 'request', name: 'Pasted Request', content: text }, { target: 'sibling' });
      }
    }
  }
};

/**
 * Check if paste menu should be visible for a given item
 * Returns true for both folders and requests
 * @param {Object} item - The collection item
 * @returns {boolean}
 */
export const shouldShowPasteMenu = (item) => {
  // Show paste menu on both folders and requests
  return item && (item.type === 'folder' || item.type === 'request');
};

/**
 * Get paste menu label based on context
 * @param {Object} focusedItem - The focused item
 * @returns {string}
 */
export const getPasteMenuLabel = (focusedItem) => {
  if (focusedItem && focusedItem.type === 'folder') {
    return 'Paste Inside';
  }
  return 'Paste';
};