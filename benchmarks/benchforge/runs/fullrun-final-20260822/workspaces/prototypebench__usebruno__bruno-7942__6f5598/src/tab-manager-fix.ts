/*
 * Fix for BRU-3311: Re-opening issue for preferences and global environments
 * 
 * This fix ensures that singleton tabs like Preferences and Global Environments
 * are properly managed and don't get duplicated when reopened.
 */

/**
 * Manages singleton tabs to prevent duplication
 * @param tabId The ID of the tab to check
 * @param tabs Current list of open tabs
 * @returns The existing tab if found, otherwise null
 */
export function findSingletonTab(tabId: string, tabs: Array<{ id: string; type: string }>): { id: string; type: string } | null {
  // Special tab types that should be singletons
  const singletonTypes = ['preferences', 'global-environments', 'collection-settings'];
  
  return tabs.find(tab => 
    tab.id === tabId || 
    (singletonTypes.includes(tab.type) && tab.type === tabId)
  ) || null;
}

/**
 * Creates or focuses a singleton tab
 * @param tabId The ID or type of the singleton tab
 * @param tabs Current list of open tabs
 * @param createTab Function to create a new tab if needed
 * @returns The tab ID that is now active
 */
export function ensureSingletonTab(
  tabId: string, 
  tabs: Array<{ id: string; type: string }>, 
  createTab: (type: string) => string
): string {
  // First try to find existing singleton tab by type
  const existingTab = findSingletonTab(tabId, tabs);
  
  if (existingTab) {
    // Focus existing tab instead of creating duplicate
    return existingTab.id;
  }
  
  // Create new tab if none exists
  return createTab(tabId);
}

/**
 * Tab type constants for singleton tabs
 */
export const TAB_TYPES = {
  PREFERENCES: 'preferences',
  GLOBAL_ENVIRONMENTS: 'global-environments',
  COLLECTION_SETTINGS: 'collection-settings'
} as const;

// Export type for tab types
export type TabType = typeof TAB_TYPES[keyof typeof TAB_TYPES];
