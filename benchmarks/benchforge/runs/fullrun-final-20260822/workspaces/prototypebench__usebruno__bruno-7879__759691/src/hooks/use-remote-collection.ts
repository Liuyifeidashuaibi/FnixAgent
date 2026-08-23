import { useState, useEffect, useCallback } from 'react';
import { 
  remoteCollectionService, 
  RemoteCollectionConfig, 
  RemoteCollectionStatus 
} from '@/services/remote-collection';
import { RemoteSyncResult } from '@/types/remote-collection';

interface UseRemoteCollectionOptions {
  collectionId: string;
}

interface UseRemoteCollectionReturn {
  isConnected: boolean;
  status: RemoteCollectionStatus;
  connect: (config: RemoteCollectionConfig) => Promise<void>;
  disconnect: () => void;
  sync: () => Promise<RemoteSyncResult>;
  isLoading: boolean;
}

export const useRemoteCollection = ({ 
  collectionId 
}: UseRemoteCollectionOptions): UseRemoteCollectionReturn => {
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState<RemoteCollectionStatus>({
    isConnected: false,
    lastSynced: null,
    status: 'idle'
  });
  const [isLoading, setIsLoading] = useState(false);

  // Update status when component mounts and on interval
  useEffect(() => {
    const updateStatus = () => {
      const currentStatus = remoteCollectionService.getStatus(collectionId);
      setStatus(currentStatus);
      setIsConnected(currentStatus.isConnected);
    };

    updateStatus();
    
    const interval = setInterval(updateStatus, 5000);
    return () => clearInterval(interval);
  }, [collectionId]);

  const connect = useCallback(async (config: RemoteCollectionConfig) => {
    setIsLoading(true);
    try {
      await remoteCollectionService.connectRemote(collectionId, config);
    } finally {
      setIsLoading(false);
    }
  }, [collectionId]);

  const disconnect = useCallback(() => {
    remoteCollectionService.disconnectRemote(collectionId);
  }, [collectionId]);

  const sync = useCallback(async (): Promise<RemoteSyncResult> => {
    setIsLoading(true);
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
    } finally {
      setIsLoading(false);
    }
  }, [collectionId]);

  return {
    isConnected,
    status,
    connect,
    disconnect,
    sync,
    isLoading
  };
};
