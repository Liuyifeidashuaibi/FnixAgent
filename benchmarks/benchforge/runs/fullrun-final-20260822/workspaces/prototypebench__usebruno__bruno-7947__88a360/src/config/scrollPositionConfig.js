/**
 * Scroll Position Configuration
 * 
 * Configuration options for scroll position persistence behavior
 */

const scrollPositionConfig = {
  // Enable/disable scroll position persistence
  enabled: true,
  
  // Persistence strategy
  // 'localStorage' - persist across browser sessions
  // 'sessionStorage' - persist only for current session
  // 'memory' - in-memory only (default)
  persistenceStrategy: 'localStorage',
  
  // Debounce delay for scroll events (ms)
  scrollDebounceDelay: 100,
  
  // Maximum number of scroll positions to store in memory
  maxMemoryCacheSize: 100,
  
  // Keys to exclude from scroll position tracking
  excludedKeys: ['preview'],
  
  // Auto-restore behavior
  autoRestoreOnTabChange: true,
  autoRestoreOnMount: true,
  
  // Debug mode
  debug: false
};

export default scrollPositionConfig;
