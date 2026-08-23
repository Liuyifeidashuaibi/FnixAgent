import { Collection } from '@/types/collection';

/**
 * Remote collection configuration
 */
export interface RemoteCollectionConfig {
  /** Remote repository URL */
  url: string;
  
  /** Branch to track */
  branch?: string;
  
  /** Authentication configuration */
  auth?: {
    username?: string;
    password?: string;
    token?: string;
    sshKeyPath?: string;
  };
  
  /** Additional git options */
  options?: {
    shallow?: boolean;
    depth?: number;
  };
}

/**
 * Remote collection status
 */
export interface RemoteCollectionStatus {
  /** Whether the collection is connected to a remote */
  isConnected: boolean;
  
  /** Last sync timestamp */
  lastSynced: Date | null;
  
  /** Current operation status */
  status: 'idle' | 'connecting' | 'syncing' | 'error' | 'pulling' | 'pushing';
  
  /** Error message if status is 'error' */
  error?: string;
  
  /** Progress information */
  progress?: {
    current: number;
    total: number;
    percentage: number;
  };
}

/**
 * Extended collection with remote support
 */
export interface RemoteCollection extends Collection {
  /** Remote configuration */
  remoteConfig?: RemoteCollectionConfig;
  
  /** Remote status */
  remoteStatus?: RemoteCollectionStatus;
  
  /** Whether this is a ghost collection (exists only remotely) */
  isGhostCollection?: boolean;
}

/**
 * Remote collection sync result
 */
export interface RemoteSyncResult {
  success: boolean;
  message: string;
  changes?: {
    added: number;
    modified: number;
    deleted: number;
  };
  timestamp: Date;
}
