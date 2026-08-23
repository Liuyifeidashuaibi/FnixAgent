import React, { createContext, useContext, useState, useEffect } from 'react';
import { 
  remoteCollectionService, 
  RemoteCollectionConfig, 
  RemoteCollectionStatus 
} from '@/services/remote-collection';
import { RemoteSyncResult } from '@/types/remote-collection';

interface RemoteCollectionContextType {
  connectRemote: (collectionId: string, config: RemoteCollectionConfig) => Promise<void>;
  disconnectRemote: (collectionId: string) => void;
  syncRemote: (collectionId: string) => Promise<RemoteSyncResult>;
  getRemoteStatus: (collectionId: string) => RemoteCollectionStatus;
  getRemoteConfig: (collectionId: string) => RemoteCollectionConfig | undefined;
}

const RemoteCollectionContext = createContext<RemoteCollectionContextType | undefined>(undefined);

export const RemoteCollectionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isInitialized, setIsInitialized] = useState(false);

  // Initialize the service
  useEffect(() => {
    // Service is already initialized as singleton
    setIsInitialized(true);
  }, []);

  const connectRemote = async (collectionId: string, config: RemoteCollectionConfig) => {
    await remoteCollectionService.connectRemote(collectionId, config);
  };

  const disconnectRemote = (collectionId: string) => {
    remoteCollectionService.disconnectRemote(collectionId);
  };

  const syncRemote = async (collectionId: string): Promise<RemoteSyncResult> => {
    try {
      await remoteCollectionService.sync(collectionId);
      return {
        success: true,
        message: 'Sync completed successfully',
        timestamp: new Date()
      };
    } catch (error) {
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Unknown error',
        timestamp: new Date()
      };
    }
  };

  const getRemoteStatus = (collectionId: string): RemoteCollectionStatus => {
    return remoteCollectionService.getStatus(collectionId);
  };

  const getRemoteConfig = (collectionId: string): RemoteCollectionConfig | undefined => {
    return remoteCollectionService.getRemoteConfig(collectionId);
  };

  const value: RemoteCollectionContextType = {
    connectRemote,
    disconnectRemote,
    syncRemote,
    getRemoteStatus,
    getRemoteConfig
  };

  return (
    <RemoteCollectionContext.Provider value={value}>
      {children}
    </RemoteCollectionContext.Provider>
  );
};

export const useRemoteCollectionContext = (): RemoteCollectionContextType => {
  const context = useContext(RemoteCollectionContext);
  if (!context) {
    throw new Error('useRemoteCollectionContext must be used within a RemoteCollectionProvider');
  }
  return context;
};
