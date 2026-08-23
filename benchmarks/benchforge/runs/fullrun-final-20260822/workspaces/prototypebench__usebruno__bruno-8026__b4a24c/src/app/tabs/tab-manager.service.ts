import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

export interface Tab {
  id: string;
  type: 'collection' | 'workspace-overview' | 'request' | 'environment' | 'settings';
  name: string;
  collectionId?: string;
}

@Injectable({
  providedIn: 'root'
})
export class TabManagerService {
  private tabsSubject = new BehaviorSubject<Tab[]>([]);
  public tabs$ = this.tabsSubject.asObservable();

  private activeTabSubject = new BehaviorSubject<string | null>(null);
  public activeTab$ = this.activeTabSubject.asObservable();

  constructor() {}

  /**
   * Get the tab that should be activated after closing tabs/collections
   * Prioritizes Workspace Overview tab, then falls back to last remaining tab
   */
  getTabToActivateAfterClose(currentTabs: Tab[], closedTabIds: string[]): string | null {
    // First, filter out the closed tabs
    const remainingTabs = currentTabs.filter(tab => !closedTabIds.includes(tab.id));
    
    // Priority 1: Workspace Overview tab
    const workspaceOverviewTab = remainingTabs.find(tab => tab.type === 'workspace-overview');
    if (workspaceOverviewTab) {
      return workspaceOverviewTab.id;
    }
    
    // Priority 2: Last remaining tab (if any)
    if (remainingTabs.length > 0) {
      return remainingTabs[remainingTabs.length - 1].id;
    }
    
    // No tabs remaining
    return null;
  }

  /**
   * Close tabs and update active tab according to priority rules
   */
  closeTabs(tabIds: string[]): void {
    const currentTabs = this.tabsSubject.value;
    const newTabs = currentTabs.filter(tab => !tabIds.includes(tab.id));
    
    this.tabsSubject.next(newTabs);
    
    // Determine which tab to activate
    const tabToActivate = this.getTabToActivateAfterClose(currentTabs, tabIds);
    if (tabToActivate) {
      this.activateTab(tabToActivate);
    }
  }

  /**
   * Close a collection and all its associated tabs
   */
  closeCollection(collectionId: string): void {
    const currentTabs = this.tabsSubject.value;
    const collectionTabIds = currentTabs
      .filter(tab => tab.collectionId === collectionId)
      .map(tab => tab.id);
    
    this.closeTabs(collectionTabIds);
  }

  activateTab(tabId: string): void {
    this.activeTabSubject.next(tabId);
  }

  addTab(tab: Tab): void {
    const currentTabs = this.tabsSubject.value;
    this.tabsSubject.next([...currentTabs, tab]);
  }

  getTabs(): Tab[] {
    return this.tabsSubject.value;
  }
}
