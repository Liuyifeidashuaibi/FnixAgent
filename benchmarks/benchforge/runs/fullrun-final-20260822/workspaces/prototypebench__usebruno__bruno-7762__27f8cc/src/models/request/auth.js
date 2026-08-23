/*
 * Auth configuration model
 * Adds apiKeyHeaderName field to support deterministic API key auth detection
 */

export class AuthConfig {
  constructor({
    mode = 'none',
    basic = {},
    bearer = {},
    apiKey = {},
    // New field for BRU-3156: track the header name for API key auth
    apiKeyHeaderName = '',
    ...rest
  } = {}) {
    this.mode = mode;
    this.basic = basic;
    this.bearer = bearer;
    this.apiKey = apiKey;
    // Track the header name used for API key authentication
    this.apiKeyHeaderName = apiKeyHeaderName;
    Object.assign(this, rest);
  }

  // Method to determine if auth mode is apikey based on header presence
  isApiKeyAuth() {
    if (this.mode === 'apikey') {
      return true;
    }
    
    // Check if apiKeyHeaderName is set and non-empty
    if (this.apiKeyHeaderName && this.apiKeyHeaderName.trim()) {
      return true;
    }
    
    return false;
  }

  // Method to get interpolated apiKeyHeaderName with variable expansion
  getInterpolatedApiKeyHeaderName(variables = {}) {
    if (!this.apiKeyHeaderName) {
      return '';
    }
    
    // Simple variable interpolation: replace {{var}} with variables[var]
    let result = this.apiKeyHeaderName;
    const regex = /\{\{([^}]+)\}\}/g;
    
    return result.replace(regex, (match, varName) => {
      const trimmedVarName = varName.trim();
      return variables[trimmedVarName] !== undefined ? variables[trimmedVarName] : match;
    });
  }
}

// Export default auth config structure
export const AUTH_MODES = {
  NONE: 'none',
  BASIC: 'basic',
  BEARER: 'bearer',
  APIKEY: 'apikey'
};