import { ipcRenderer } from 'electron';

/**
 * Get process environment variables for a collection
 * Fixes runtime resolution by mapping scratch collections to workspace path
 */
const getProcessEnvVars = (collectionId) => {
  // This would normally look up the workspace path for the collection
  // and read .env files, but we need the mapping first
  
  // In the fixed version, this function can now find workspace .env values
  // because mountScratchCollection called renderer:set-collection-workspace
  
  return new Promise((resolve, reject) => {
    ipcRenderer.invoke('main:get-process-env-vars', collectionId)
      .then(vars => resolve(vars))
      .catch(err => reject(err));
  });
};

export { getProcessEnvVars };