import { TestBed } from '@angular/core/testing';
import { TabManagerService } from './tab-manager.service';

describe('TabManagerService', () => {
  let service: TabManagerService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(TabManagerService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('getTabToActivateAfterClose', () => {
    it('should prioritize Workspace Overview tab when available', () => {
      // Given: tabs including workspace overview and collection tabs
      const tabs = [
        { id: 'overview-1', type: 'workspace-overview', name: 'Workspace Overview' },
        { id: 'collection-1', type: 'collection', name: 'My Collection', collectionId: 'col-1' },
        { id: 'request-1', type: 'request', name: 'GET Request', collectionId: 'col-1' }
      ];
      
      // When closing collection tabs
      const closedTabIds = ['collection-1', 'request-1'];
      
      // Then workspace overview should be selected
      const result = service['getTabToActivateAfterClose'](tabs, closedTabIds);
      
      expect(result).toBe('overview-1');
    });

    it('should fall back to last remaining tab when no workspace overview exists', () => {
      // Given: only collection tabs
      const tabs = [
        { id: 'collection-1', type: 'collection', name: 'My Collection', collectionId: 'col-1' },
        { id: 'request-1', type: 'request', name: 'GET Request', collectionId: 'col-1' },
        { id: 'request-2', type: 'request', name: 'POST Request', collectionId: 'col-1' }
      ];
      
      // When closing first two tabs
      const closedTabIds = ['collection-1', 'request-1'];
      
      // Then last remaining tab should be selected
      const result = service['getTabToActivateAfterClose'](tabs, closedTabIds);
      
      expect(result).toBe('request-2');
    });

    it('should return null when no tabs remain', () => {
      // Given: single tab
      const tabs = [
        { id: 'collection-1', type: 'collection', name: 'My Collection', collectionId: 'col-1' }
      ];
      
      // When closing that tab
      const closedTabIds = ['collection-1'];
      
      // Then no tab should be selected
      const result = service['getTabToActivateAfterClose'](tabs, closedTabIds);
      
      expect(result).toBeNull();
    });
  });

  describe('closeCollection', () => {
    it('should close all tabs associated with a collection and prioritize workspace overview', () => {
      // Given: tabs including workspace overview and collection tabs
      const tabs = [
        { id: 'overview-1', type: 'workspace-overview', name: 'Workspace Overview' },
        { id: 'collection-1', type: 'collection', name: 'My Collection', collectionId: 'col-1' },
        { id: 'request-1', type: 'request', name: 'GET Request', collectionId: 'col-1' }
      ];
      
      // Set initial tabs
      (service as any).tabsSubject.next(tabs);
      
      // When closing collection
      service.closeCollection('col-1');
      
      // Then workspace overview should be activated
      const activeTab = (service as any).activeTabSubject.value;
      expect(activeTab).toBe('overview-1');
    });
  });
});
