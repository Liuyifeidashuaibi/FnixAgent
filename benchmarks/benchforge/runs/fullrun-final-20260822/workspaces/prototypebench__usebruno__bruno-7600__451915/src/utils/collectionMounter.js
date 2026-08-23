import { ipcRenderer } from 'electron';

/**
 * Mount scratch collection and map it to its workspace path
 * This enables process.env variable resolution for scratch pad requests
 */
const mountScratchCollection = (collection, workspacePath) => {
  // Original collection mounting logic would go here...
  
  // Fix: Map scratch collections to their workspace via renderer IPC
  // This allows getProcessEnvVars() to find workspace .env values at runtime
  if (workspacePath && collection?.type === 'scratch') {
    ipcRenderer.send('renderer:set-collection-workspace', {
      collectionId: collection.id,
      workspacePath: workspacePath
    });
  }
  
  return collection;
};

export { mountScratchCollection };