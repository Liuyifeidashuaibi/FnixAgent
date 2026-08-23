/*
 * Request builder service
 * Incorporates apiKeyHeaderName for deterministic API key auth detection
 */

import { detectApiKeyAuth, getEffectiveAuthMode, interpolateVariable } from '../utils/auth-detection.js';

/**
 * Builds request configuration with proper auth handling
 * @param {Object} requestConfig - Original request configuration
 * @returns {Object} Built request configuration
 */
export function buildRequest(requestConfig) {
  const { auth = {}, headers = {}, queryParams = {}, variables = {} } = requestConfig;
  
  // Get effective auth mode considering apiKeyHeaderName
  const effectiveAuthMode = getEffectiveAuthMode(auth, headers, queryParams);
  
  // Build headers with interpolated apiKeyHeaderName if needed
  let finalHeaders = { ...headers };
  
  // If apiKey auth is detected and apiKeyHeaderName is set, ensure it's in headers
  if (effectiveAuthMode === 'apikey' && auth.apiKeyHeaderName) {
    const interpolatedHeaderName = interpolateVariable(auth.apiKeyHeaderName, variables);
    
    // Only add if not already present
    if (finalHeaders[interpolatedHeaderName] === undefined) {
      // Add placeholder or default value
      finalHeaders[interpolatedHeaderName] = '{{apiKey}}';
    }
  }
  
  return {
    ...requestConfig,
    auth: {
      ...auth,
      mode: effectiveAuthMode
    },
    headers: finalHeaders
  };
}

/**
 * Validates auth configuration for API key mode
 * @param {Object} authConfig - Auth configuration
 * @returns {Object} Validation result
 */
export function validateApiKeyAuth(authConfig) {
  const errors = [];
  
  if (authConfig.mode === 'apikey') {
    // Check if apiKeyHeaderName is provided
    if (!authConfig.apiKeyHeaderName || !authConfig.apiKeyHeaderName.trim()) {
      errors.push('apiKeyHeaderName is required for apikey authentication mode');
    }
  }
  
  return {
    isValid: errors.length === 0,
    errors
  };
}