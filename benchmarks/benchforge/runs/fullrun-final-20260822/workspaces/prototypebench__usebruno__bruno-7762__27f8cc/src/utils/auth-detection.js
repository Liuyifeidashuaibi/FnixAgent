/*
 * Authentication detection utility
 * Handles deterministic API key auth detection using apiKeyHeaderName
 */

/**
 * Detects if the request uses API key authentication
 * @param {Object} authConfig - The auth configuration object
 * @param {Object} headers - Request headers object
 * @param {Object} queryParams - Query parameters object
 * @returns {string} 'apikey' if API key auth is detected, otherwise null
 */
export function detectApiKeyAuth(authConfig, headers = {}, queryParams = {}) {
  // Check if auth mode is explicitly set to apikey
  if (authConfig.mode === 'apikey') {
    return 'apikey';
  }

  // Check if apiKeyHeaderName is set and the corresponding header exists
  if (authConfig.apiKeyHeaderName && authConfig.apiKeyHeaderName.trim()) {
    const headerName = interpolateVariable(authConfig.apiKeyHeaderName, authConfig.variables || {});
    
    // Check header placement
    if (headers[headerName] !== undefined) {
      return 'apikey';
    }
    
    // Check query param placement
    if (queryParams[headerName] !== undefined) {
      return 'apikey';
    }
  }

  return null;
}

/**
 * Interpolates variables in a string (e.g., {{apiKey}} -> value)
 * @param {string} str - String with variable placeholders
 * @param {Object} variables - Variables object
 * @returns {string} Interpolated string
 */
export function interpolateVariable(str, variables = {}) {
  if (!str || typeof str !== 'string') {
    return str;
  }
  
  return str.replace(/\{\{([^}]+)\}\}/g, (match, varName) => {
    const trimmedVarName = varName.trim();
    return variables[trimmedVarName] !== undefined ? variables[trimmedVarName] : match;
  });
}

/**
 * Gets the effective auth mode considering apiKeyHeaderName
 * @param {Object} authConfig - Auth configuration
 * @param {Object} headers - Request headers
 * @param {Object} queryParams - Query parameters
 * @returns {string} Detected auth mode
 */
export function getEffectiveAuthMode(authConfig, headers = {}, queryParams = {}) {
  // First check for explicit apikey mode
  if (authConfig.mode === 'apikey') {
    return 'apikey';
  }
  
  // Then check for apiKeyHeaderName based detection
  const apiKeyAuth = detectApiKeyAuth(authConfig, headers, queryParams);
  if (apiKeyAuth) {
    return apiKeyAuth;
  }
  
  // Fall back to original mode
  return authConfig.mode || 'none';
}