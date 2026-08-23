import { Injectable } from '@angular/core';
import { TabManagerService } from '../tabs/tab-manager.service';

@Injectable({
  providedIn: 'root'
})
export class CollectionService {
  constructor(private tabManagerService: TabManagerService) {}

  /**
   * Close a collection and ensure Workspace Overview tab is prioritized
   * This implements the BRU-3247 requirement to prioritize Workspace Overview
   */
  closeCollection(collectionId: string): void {
    // Use the tab manager's built-in logic which prioritizes Workspace Overview
    this.tabManagerService.closeCollection(collectionId);
  }

  /**
   * Close multiple collections
   */
  closeCollections(collectionIds: string[]): void {
    collectionIds.forEach(collectionId => {
      this.closeCollection(collectionId);
    });
  }
}
