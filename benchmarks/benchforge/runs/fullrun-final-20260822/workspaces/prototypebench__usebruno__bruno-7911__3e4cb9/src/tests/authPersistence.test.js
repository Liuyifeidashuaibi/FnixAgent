import {
  getAuthDataForMode,
  storeAuthDataForMode,
  getCompleteAuthConfig,
  updateAuthConfig
} from '../utils/authPersistence';

describe('Authentication Persistence', () => {
  beforeEach(() => {
    // Clear storage before each test
    jest.resetModules();
  });

  test('should preserve auth data when switching between modes', () => {
    // Store initial bearer token
    storeAuthDataForMode('bearer', { bearerToken: 'abc123' });
    
    // Store basic auth credentials
    storeAuthDataForMode('basic', { username: 'user', password: 'pass' });
    
    // Get data for each mode
    expect(getAuthDataForMode('bearer')).toEqual({ bearerToken: 'abc123' });
    expect(getAuthDataForMode('basic')).toEqual({ username: 'user', password: 'pass' });
  });

  test('should merge stored data with current config', () => {
    // Store some data
    storeAuthDataForMode('bearer', { bearerToken: 'abc123', customHeader: 'value' });
    
    // Current config has partial data
    const currentConfig = { mode: 'bearer', bearerToken: 'def456' };
    
    // Get complete config - should have merged values
    const completeConfig = getCompleteAuthConfig(currentConfig);
    
    expect(completeConfig).toEqual({
      mode: 'bearer',
      bearerToken: 'def456',
      customHeader: 'value'
    });
  });

  test('should preserve data across mode switches', () => {
    // Initial config
    const initialConfig = { mode: 'bearer', bearerToken: 'token1' };
    
    // Update to basic auth
    const basicConfig = { mode: 'basic', username: 'testuser', password: 'testpass' };
    
    // Store both configs
    updateAuthConfig(initialConfig);
    updateAuthConfig(basicConfig);
    
    // Verify both are stored
    expect(getAuthDataForMode('bearer')).toEqual({ bearerToken: 'token1' });
    expect(getAuthDataForMode('basic')).toEqual({ username: 'testuser', password: 'testpass' });
  });

  test('should handle empty configs gracefully', () => {
    expect(getCompleteAuthConfig(null)).toBeNull();
    expect(getCompleteAuthConfig({})).toEqual({});
    expect(getCompleteAuthConfig({ mode: 'none' })).toEqual({ mode: 'none' });
  });
});