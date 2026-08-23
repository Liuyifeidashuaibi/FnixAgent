import { ipcRenderer } from 'electron';
import { showToast } from '@/utils/toast';

/**
 * Handle drag and drop of requests between collections
 */
class CollectionDragHandler {
  /**
   * Initialize drag and drop handlers
   */
  static init() {
    // Listen for drag events on collection items
    document.addEventListener('dragstart', this.handleDragStart.bind(this));
    document.addEventListener('dragover', this.handleDragOver.bind(this));
    document.addEventListener('drop', this.handleDrop.bind(this));
  }

  /**
   * Handle drag start event
   * @param {DragEvent} event
   */
  static handleDragStart(event) {
    const requestElement = event.target.closest('[data-request-id]');
    if (requestElement) {
      const requestId = requestElement.dataset.requestId;
      const requestPath = requestElement.dataset.requestPath;
      
      event.dataTransfer.setData('text/plain', JSON.stringify({
        type: 'request',
        requestId,
        requestPath
      }));
      
      // Add visual feedback
      requestElement.classList.add('dragging');
    }
  }

  /**
   * Handle drag over event
   * @param {DragEvent} event
   */
  static handleDragOver(event) {
    event.preventDefault();
    
    // Check if we're hovering over a collection drop zone
    const collectionDropZone = event.target.closest('[data-collection-id]');
    if (collectionDropZone && collectionDropZone.dataset.collectionId) {
      event.dataTransfer.dropEffect = 'move';
      collectionDropZone.classList.add('drop-target');
    }
  }

  /**
   * Handle drop event
   * @param {DragEvent} event
   */
  static async handleDrop(event) {
    event.preventDefault();
    
    // Remove drop target class
    const dropZones = document.querySelectorAll('[data-collection-id].drop-target');
    dropZones.forEach(zone => zone.classList.remove('drop-target'));
    
    const collectionDropZone = event.target.closest('[data-collection-id]');
    if (!collectionDropZone || !collectionDropZone.dataset.collectionId) {
      return;
    }
    
    try {
      const data = event.dataTransfer.getData('text/plain');
      if (!data) return;
      
      const payload = JSON.parse(data);
      if (payload.type !== 'request') return;
      
      const { requestId, requestPath } = payload;
      const targetCollectionId = collectionDropZone.dataset.collectionId;
      const targetCollectionPath = collectionDropZone.dataset.collectionPath;
      const targetFormat = collectionDropZone.dataset.collectionFormat || 'bru';
      
      // Close the tab for the moved request
      await ipcRenderer.invoke('collection:close-tab-on-move', {
        requestId
      });
      
      // Move the request with format conversion if needed
      const result = await ipcRenderer.invoke('collection:drag-move', {
        sourcePath: requestPath,
        targetCollectionPath,
        targetFormat
      });
      
      if (!result.success) {
        // Show error toast
        showToast(`Failed to move request: ${result.error}`, 'error');
        return;
      }
      
      // Show success toast
      showToast('Request moved successfully', 'success');
      
      // Refresh the UI
      this.refreshCollectionView();
      
    } catch (error) {
      console.error('Error handling drop:', error);
      showToast(`Error moving request: ${error.message}`, 'error');
    }
  }

  /**
   * Refresh the collection view after a move
   */
  static refreshCollectionView() {
    // In a real implementation, this would trigger a re-render
    // or dispatch an event to update the collection state
    window.dispatchEvent(new CustomEvent('collection-updated'));
  }
}

// Export as default
export default CollectionDragHandler;