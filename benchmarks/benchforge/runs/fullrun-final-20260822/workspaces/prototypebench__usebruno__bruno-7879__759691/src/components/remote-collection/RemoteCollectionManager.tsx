import React, { useState, useEffect } from 'react';
import { remoteCollectionService, RemoteCollectionConfig, RemoteCollectionStatus } from '@/services/remote-collection';

interface RemoteCollectionManagerProps {
  collectionId: string;
  onStatusChange?: (status: RemoteCollectionStatus) => void;
}

const RemoteCollectionManager: React.FC<RemoteCollectionManagerProps> = ({ 
  collectionId, 
  onStatusChange 
}) => {
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState<RemoteCollectionStatus>({
    isConnected: false,
    lastSynced: null,
    status: 'idle'
  });
  const [url, setUrl] = useState('');
  const [branch, setBranch] = useState('main');
  const [showConnectForm, setShowConnectForm] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  useEffect(() => {
    const updateStatus = () => {
      const currentStatus = remoteCollectionService.getStatus(collectionId);
      setStatus(currentStatus);
      setIsConnected(currentStatus.isConnected);
      if (onStatusChange) {
        onStatusChange(currentStatus);
      }
    };

    // Initial status check
    updateStatus();

    // Set up periodic status updates
    const interval = setInterval(updateStatus, 5000);
    return () => clearInterval(interval);
  }, [collectionId, onStatusChange]);

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    try {
      const config: RemoteCollectionConfig = {
        url: url.trim(),
        branch: branch.trim() || 'main'
      };
      await remoteCollectionService.connectRemote(collectionId, config);
      setShowConnectForm(false);
      setUrl('');
      setBranch('main');
    } catch (error) {
      console.error('Failed to connect remote:', error);
      // Handle error in UI
    }
  };

  const handleDisconnect = () => {
    remoteCollectionService.disconnectRemote(collectionId);
  };

  const handleSync = async () => {
    if (!isConnected) return;
    
    setIsSyncing(true);
    try {
      await remoteCollectionService.sync(collectionId);
    } catch (error) {
      console.error('Failed to sync:', error);
    } finally {
      setIsSyncing(false);
    }
  };

  const getStatusText = () => {
    if (status.status === 'connecting') return 'Connecting...';
    if (status.status === 'syncing') return 'Syncing...';
    if (status.status === 'error') return 'Error';
    if (isConnected) return 'Connected';
    return 'Not connected';
  };

  const getStatusColor = () => {
    if (status.status === 'error') return 'text-red-500';
    if (isConnected) return 'text-green-500';
    return 'text-gray-500';
  };

  return (
    <div className="remote-collection-manager p-4 border rounded-lg bg-white dark:bg-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Remote Collection</h3>
        {!isConnected && !showConnectForm && (
          <button 
            onClick={() => setShowConnectForm(true)}
            className="px-3 py-1 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors"
          >
            Connect Remote
          </button>
        )}
      </div>

      {showConnectForm && (
        <form onSubmit={handleConnect} className="mb-4 space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Remote URL
            </label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/user/repo.git"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Branch (optional)
            </label>
            <input
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="main"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
            />
          </div>
          <div className="flex space-x-2">
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors"
            >
              Connect
            </button>
            <button
              type="button"
              onClick={() => setShowConnectForm(false)}
              className="px-4 py-2 bg-gray-300 hover:bg-gray-400 text-gray-700 dark:bg-gray-600 dark:hover:bg-gray-500 dark:text-gray-200 rounded-md transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {isConnected && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className={`font-medium ${getStatusColor()}`}>
                {getStatusText()}
              </span>
              {status.lastSynced && (
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  Last synced: {status.lastSynced.toLocaleString()}
                </p>
              )}
            </div>
            <div className="flex space-x-2">
              <button
                onClick={handleSync}
                disabled={isSyncing || status.status === 'syncing'}
                className={`px-3 py-1 text-sm rounded-md transition-colors ${
                  isSyncing || status.status === 'syncing' 
                    ? 'bg-gray-300 dark:bg-gray-600 cursor-not-allowed' 
                    : 'bg-green-600 hover:bg-green-700 text-white'
                }`}
              >
                {isSyncing ? 'Syncing...' : 'Sync Now'}
              </button>
              <button
                onClick={handleDisconnect}
                className="px-3 py-1 text-sm bg-red-600 hover:bg-red-700 text-white rounded-md transition-colors"
              >
                Disconnect
              </button>
            </div>
          </div>
          
          <div className="text-sm text-gray-600 dark:text-gray-400">
            <p>Remote URL: {remoteCollectionService.getRemoteConfig(collectionId)?.url}</p>
            <p>Branch: {remoteCollectionService.getRemoteConfig(collectionId)?.branch || 'main'}</p>
          </div>
        </div>
      )}

      {status.status === 'error' && status.error && (
        <div className="mt-3 p-3 bg-red-50 text-red-700 rounded-md text-sm">
          Error: {status.error}
        </div>
      )}
    </div>
  );
};

export default RemoteCollectionManager;
