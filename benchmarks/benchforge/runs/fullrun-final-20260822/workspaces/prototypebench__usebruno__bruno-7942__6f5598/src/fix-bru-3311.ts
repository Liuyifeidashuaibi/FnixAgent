/*
 * BRU-3311 Fix: Prevent duplicate tabs for Preferences and Global Environments
 * 
 * This fix addresses the issue where opening Preferences or Global Environments
 * multiple times creates duplicate tabs instead of focusing the existing one.
 */

/**
 * Enhanced tab manager that prevents duplication of singleton tabs
 */
class SingletonTabManager {
  private static instance: SingletonTabManager;
  private singletonTabs: Map<string, string> = new Map(); // type -> tabId
  
  private constructor() {}
  
  public static getInstance(): SingletonTabManager {
    if (!SingletonTabManager.instance) {
      SingletonTabManager.instance = new SingletonTabManager();
    }
    return SingletonTabManager.instance;
  }
  
  /**
   * Get existing tab ID for a singleton tab type, or null if none exists
   */
  public getExistingTabId(tabType: string): string | null {
    return this.singletonTabs.get(tabType) || null;
  }
  
  /**
   * Register a tab as the active instance for its type
   */
  public registerTab(tabId: string, tabType: string): void {
    this.singletonTabs.set(tabType, tabId);
  }
  
  /**
   * Unregister a tab when it's closed
   */
  public unregisterTab(tabId: string, tabType: string): void {
    const currentId = this.singletonTabs.get(tabType);
    if (currentId === tabId) {
      this.singletonTabs.delete(tabType);
    }
  }
  
  /**
   * Ensure only one instance of a singleton tab exists
   */
  public ensureSingletonTab(tabType: string, createNewTab: () => string): string {
    const existingId = this.getExistingTabId(tabType);
    if (existingId) {
      return existingId;
    }
    
    const newId = createNewTab();
    this.registerTab(newId, tabType);
    return newId;
  }
}

// Export the singleton instance
export const singletonTabManager = SingletonTabManager.getInstance();

// Export constants for singleton tab types
export const SINGLETON_TAB_TYPES = {
  PREFERENCES: 'preferences',
  GLOBAL_ENVIRONMENTS: 'global-environments',
  COLLECTION_SETTINGS: 'collection-settings'
} as const;

export type SingletonTabType = typeof SINGLETON_TAB_TYPES[keyof typeof SINGLETON_TAB_TYPES];
