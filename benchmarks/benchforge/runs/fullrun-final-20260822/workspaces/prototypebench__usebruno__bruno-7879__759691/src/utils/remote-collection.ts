import { Collection } from '@/types/collection';

/**
 * Utility functions for remote collection operations
 */

/**
 * Check if a collection has remote backing
 */
export const hasRemoteBacking = (collection: Collection): boolean => {
  return !!collection.remoteConfig;
};

/**
 * Get remote URL from collection
 */
export const getRemoteUrl = (collection: Collection): string | undefined => {
  return collection.remoteConfig?.url;
};

/**
 * Get remote branch from collection
 */
export const getRemoteBranch = (collection: Collection): string | undefined => {
  return collection.remoteConfig?.branch || 'main';
};

/**
 * Validate remote URL format
 */
export const isValidRemoteUrl = (url: string): boolean => {
  try {
    const parsed = new URL(url);
    return ['https:', 'git:', 'ssh:'].includes(parsed.protocol);
  } catch {
    return false;
  }
};

/**
 * Generate git clone command for a remote collection
 */
export const generateCloneCommand = (collection: Collection): string => {
  const url = getRemoteUrl(collection);
  const branch = getRemoteBranch(collection);
  
  if (!url) return '';
  
  return `git clone ${url} ${collection.name || 'collection'}${branch ? ` -b ${branch}` : ''}`;
};

/**
 * Format remote status for display
 */
export const formatRemoteStatus = (status: {
  isConnected: boolean;
  lastSynced: Date | null;
  status: 'idle' | 'connecting' | 'syncing' | 'error';
  error?: string;
}): string => {
  if (status.status === 'error') return 'Error';
  if (status.status === 'connecting') return 'Connecting...';
  if (status.status === 'syncing') return 'Syncing...';
  if (status.isConnected) return 'Connected';
  return 'Not connected';
};
