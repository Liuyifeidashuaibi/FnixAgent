/*
 * Tests for API key authentication detection with apiKeyHeaderName
 */

import { detectApiKeyAuth, interpolateVariable, getEffectiveAuthMode } from '../utils/auth-detection.js';

describe('API Key Auth Detection', () => {
  test('detects apikey auth when mode is explicitly set', () => {
    const authConfig = { mode: 'apikey', apiKeyHeaderName: 'X-API-Key' };
    const result = detectApiKeyAuth(authConfig, {}, {});
    expect(result).toBe('apikey');
  });

  test('detects apikey auth when apiKeyHeaderName is set and header exists', () => {
    const authConfig = { apiKeyHeaderName: 'X-API-Key' };
    const headers = { 'X-API-Key': 'test-key' };
    const result = detectApiKeyAuth(authConfig, headers, {});
    expect(result).toBe('apikey');
  });

  test('detects apikey auth when apiKeyHeaderName is set and query param exists', () => {
    const authConfig = { apiKeyHeaderName: 'api_key' };
    const queryParams = { 'api_key': 'test-value' };
    const result = detectApiKeyAuth(authConfig, {}, queryParams);
    expect(result).toBe('apikey');
  });

  test('handles variable interpolation in apiKeyHeaderName', () => {
    const authConfig = { 
      apiKeyHeaderName: 'X-{{authType}}-Key',
      variables: { authType: 'API' }
    };
    const headers = { 'X-API-Key': 'test-key' };
    const result = detectApiKeyAuth(authConfig, headers, {});
    expect(result).toBe('apikey');
  });

  test('getEffectiveAuthMode returns correct mode', () => {
    const authConfig = { apiKeyHeaderName: 'Authorization' };
    const headers = { 'Authorization': 'Bearer token' };
    const result = getEffectiveAuthMode(authConfig, headers, {});
    expect(result).toBe('apikey');
  });

  test('interpolateVariable handles missing variables gracefully', () => {
    const result = interpolateVariable('{{apiKey}} {{missing}}', { apiKey: 'test123' });
    expect(result).toBe('test123 {{missing}}');
  });
});