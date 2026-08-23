import React, { useState, useEffect } from 'react';

const AuthenticationConfig = ({ authConfig, onAuthChange }) => {
  const [authMode, setAuthMode] = useState(authConfig?.mode || 'none');
  const [authData, setAuthData] = useState({
    // Store all auth data separately to preserve it when switching modes
    bearerToken: authConfig?.bearerToken || '',
    username: authConfig?.username || '',
    password: authConfig?.password || '',
    apiKey: authConfig?.apiKey || '',
    // ... other auth fields
  });

  // Preserve auth data when mode changes
  useEffect(() => {
    if (authConfig) {
      // Restore previous auth data when mode changes
      setAuthData(prev => ({
        ...prev,
        bearerToken: authConfig.bearerToken || prev.bearerToken,
        username: authConfig.username || prev.username,
        password: authConfig.password || prev.password,
        apiKey: authConfig.apiKey || prev.apiKey,
      }));
    }
  }, [authConfig]);

  const handleModeChange = (mode) => {
    setAuthMode(mode);
    
    // Preserve current auth data before changing mode
    const updatedAuthConfig = {
      mode,
      ...authData
    };
    
    onAuthChange(updatedAuthConfig);
  };

  const handleAuthDataChange = (field, value) => {
    setAuthData(prev => ({ ...prev, [field]: value }));
    
    // Update the full auth config with current data
    const updatedAuthConfig = {
      mode: authMode,
      ...authData,
      [field]: value
    };
    
    onAuthChange(updatedAuthConfig);
  };

  return (
    <div className="authentication-config">
      <div className="auth-mode-selector">
        <label>Authentication Mode:</label>
        <select 
          value={authMode} 
          onChange={(e) => handleModeChange(e.target.value)}
        >
          <option value="none">None</option>
          <option value="bearer">Bearer Token</option>
          <option value="basic">Basic Auth</option>
          <option value="api-key">API Key</option>
        </select>
      </div>

      {authMode === 'bearer' && (
        <div className="auth-field">
          <label>Bearer Token:</label>
          <input
            type="text"
            value={authData.bearerToken}
            onChange={(e) => handleAuthDataChange('bearerToken', e.target.value)}
            placeholder="Enter token"
          />
        </div>
      )}

      {authMode === 'basic' && (
        <div className="auth-fields">
          <div className="auth-field">
            <label>Username:</label>
            <input
              type="text"
              value={authData.username}
              onChange={(e) => handleAuthDataChange('username', e.target.value)}
              placeholder="Username"
            />
          </div>
          <div className="auth-field">
            <label>Password:</label>
            <input
              type="password"
              value={authData.password}
              onChange={(e) => handleAuthDataChange('password', e.target.value)}
              placeholder="Password"
            />
          </div>
        </div>
      )}

      {authMode === 'api-key' && (
        <div className="auth-field">
          <label>API Key:</label>
          <input
            type="text"
            value={authData.apiKey}
            onChange={(e) => handleAuthDataChange('apiKey', e.target.value)}
            placeholder="API Key"
          />
        </div>
      )}
    </div>
  );
};

export default AuthenticationConfig;