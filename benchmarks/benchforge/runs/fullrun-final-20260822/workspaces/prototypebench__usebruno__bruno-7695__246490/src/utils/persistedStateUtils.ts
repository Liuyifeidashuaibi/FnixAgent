/**
 * Utility functions for managing persisted scroll state
 */

/**
 * Clear all persisted scroll state for a specific tab scope
 * @param tabUid The unique identifier for the tab
 */
export const clearPersistedScope = (tabUid: string) => {
  try {
    // Get all keys that match the tab scope pattern
    const keysToDelete: string[] = [];
    
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(`persisted::${tabUid}::`)) {
        keysToDelete.push(key);
      }
    }
    
    // Delete all matching keys
    keysToDelete.forEach(key => {
      localStorage.removeItem(key);
    });
    
    console.debug(`Cleared ${keysToDelete.length} persisted scroll states for tab: ${tabUid}`);
  } catch (e) {
    console.warn(`Failed to clear persisted scope for tab ${tabUid}:`, e);
  }
};

/**
 * Clear all persisted scroll state across the entire application
 */
export const clearAllPersistedState = () => {
  try {
    // Get all keys that match the persisted pattern
    const keysToDelete: string[] = [];
    
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith('persisted::')) {
        keysToDelete.push(key);
      }
    }
    
    // Delete all matching keys
    keysToDelete.forEach(key => {
      localStorage.removeItem(key);
    });
    
    console.debug(`Cleared ${keysToDelete.length} persisted scroll states globally`);
  } catch (e) {
    console.warn('Failed to clear all persisted state:', e);
  }
};

/**
 * Get all persisted scroll state keys for debugging
 */
export const getPersistedStateKeys = (): string[] => {
  const keys: string[] = [];
  
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith('persisted::')) {
        keys.push(key);
      }
    }
  } catch (e) {
    console.warn('Failed to get persisted state keys:', e);
  }
  
  return keys;
};