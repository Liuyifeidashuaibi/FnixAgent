/**
 * Authentication Persistence Utility
 * Fixes issue #5636: Preserve auth data when switching between auth modes
 * 
 * This utility ensures that when users switch between different authentication modes
 * (e.g., from Bearer Token to Basic Auth), the previously entered authentication data
 * is preserved and can be restored when switching back to that mode.
 */

// Store auth data by mode to preserve values across mode changes
const authDataStore = new Map();

/**
 * Get stored auth data for a specific mode
 * @param {string} mode - The auth mode (e.g., 'bearer', 'basic')
 * @returns {Object} The stored auth data for this mode
 */
export const getAuthDataForMode = (mode) => {
  return authDataStore.get(mode) || {};
};

/**
 * Store auth data for a specific mode
 * @param {string} mode - The auth mode
 * @param {Object} data - The auth data to store
 */
export const storeAuthDataForMode = (mode, data) => {
  if (!authDataStore.has(mode)) {
    authDataStore.set(mode, {});
  }
  
  // Merge new data with existing data to preserve fields not being updated
  const existingData = authDataStore.get(mode);
  authDataStore.set(mode, { ...existingData, ...data });
};

/**
 * Clear auth data for a specific mode
 * @param {string} mode - The auth mode
 */
export const clearAuthDataForMode = (mode) => {
  authDataStore.delete(mode);
};

/**
 * Get complete auth configuration with preserved data
 * @param {Object} currentConfig - Current auth configuration
 * @returns {Object} Complete auth configuration with preserved data
 */
export const getCompleteAuthConfig = (currentConfig) => {
  if (!currentConfig || !currentConfig.mode) {
    return currentConfig;
  }

  // Get stored data for current mode
  const storedData = getAuthDataForMode(currentConfig.mode);
  
  // Merge stored data with current config, prioritizing current config values
  // but preserving any stored values that aren't in current config
  return {
    ...storedData,
    ...currentConfig
  };
};

/**
 * Update auth configuration while preserving data across modes
 * @param {Object} newConfig - New auth configuration
 * @param {Object} previousConfig - Previous auth configuration (optional)
 * @returns {Object} Updated auth configuration
 */
export const updateAuthConfig = (newConfig, previousConfig) => {
  if (!newConfig || !newConfig.mode) {
    return newConfig;
  }

  // Store current data for the new mode
  storeAuthDataForMode(newConfig.mode, newConfig);

  // If we're switching from a different mode, preserve the previous mode's data
  if (previousConfig && previousConfig.mode && previousConfig.mode !== newConfig.mode) {
    // Store previous mode's data as well
    storeAuthDataForMode(previousConfig.mode, previousConfig);
  }

  return newConfig;
};

/**
 * Reset all auth data storage
 */
export const resetAuthStorage = () => {
  authDataStore.clear();
};