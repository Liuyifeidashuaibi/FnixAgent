/**
 * Remote collection configuration
 */

export const REMOTE_COLLECTION_CONFIG = {
  // Default branch to use when none is specified
  DEFAULT_BRANCH: 'main',
  
  // Maximum depth for shallow clones
  MAX_SHALLOW_DEPTH: 10,
  
  // Timeout for remote operations (in milliseconds)
  OPERATION_TIMEOUT: 30000,
  
  // Supported remote protocols
  SUPPORTED_PROTOCOLS: ['https:', 'git:', 'ssh:'] as const,
  
  // Default git options
  DEFAULT_GIT_OPTIONS: {
    shallow: true,
    depth: 1
  },
  
  // Status update interval (in milliseconds)
  STATUS_UPDATE_INTERVAL: 5000,
  
  // Sync retry configuration
  SYNC_RETRY_CONFIG: {
    maxRetries: 3,
    baseDelay: 1000
  }
} as const;

export type SupportedProtocol = typeof REMOTE_COLLECTION_CONFIG.SUPPORTED_PROTOCOLS[number];

// Export utility functions
export const isSupportedProtocol = (protocol: string): protocol is SupportedProtocol => {
  return REMOTE_COLLECTION_CONFIG.SUPPORTED_PROTOCOLS.includes(protocol as SupportedProtocol);
};
