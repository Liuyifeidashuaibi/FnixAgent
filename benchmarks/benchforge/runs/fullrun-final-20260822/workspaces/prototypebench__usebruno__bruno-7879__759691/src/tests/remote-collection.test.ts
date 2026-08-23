import { remoteCollectionService } from '@/services/remote-collection';
import { RemoteCollectionConfig } from '@/types/remote-collection';

// Mock the service methods for testing
jest.mock('@/services/remote-collection', () => ({
  remoteCollectionService: {
    connectRemote: jest.fn(),
    disconnectRemote: jest.fn(),
    getRemoteConfig: jest.fn(),
    getStatus: jest.fn(),
    sync: jest.fn()
  }
}));

describe('RemoteCollectionService', () => {
  const collectionId = 'test-collection-id';
  
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('connectRemote', () => {
    it('should connect to a valid remote URL', async () => {
      const config: RemoteCollectionConfig = {
        url: 'https://github.com/user/repo.git'
      };
      
      await remoteCollectionService.connectRemote(collectionId, config);
      
      expect(remoteCollectionService.connectRemote).toHaveBeenCalledWith(collectionId, config);
    });

    it('should throw error for invalid URL protocol', async () => {
      const config: RemoteCollectionConfig = {
        url: 'ftp://invalid.com/repo.git'
      };
      
      await expect(
        remoteCollectionService.connectRemote(collectionId, config)
      ).rejects.toThrow('Invalid remote URL protocol');
    });
  });

  describe('disconnectRemote', () => {
    it('should disconnect from remote', () => {
      remoteCollectionService.disconnectRemote(collectionId);
      
      expect(remoteCollectionService.disconnectRemote).toHaveBeenCalledWith(collectionId);
    });
  });

  describe('getStatus', () => {
    it('should return status object', () => {
      const status = remoteCollectionService.getStatus(collectionId);
      
      expect(status).toBeDefined();
      expect(status.isConnected).toBe(false);
      expect(status.status).toBe('idle');
    });
  });

  describe('sync', () => {
    it('should sync collection when connected', async () => {
      // First connect
      const config: RemoteCollectionConfig = {
        url: 'https://github.com/user/repo.git'
      };
      await remoteCollectionService.connectRemote(collectionId, config);
      
      // Then sync
      await remoteCollectionService.sync(collectionId);
      
      expect(remoteCollectionService.sync).toHaveBeenCalledWith(collectionId);
    });

    it('should throw error when not connected', async () => {
      await expect(remoteCollectionService.sync(collectionId)).rejects.toThrow('Collection is not connected');
    });
  });
});
