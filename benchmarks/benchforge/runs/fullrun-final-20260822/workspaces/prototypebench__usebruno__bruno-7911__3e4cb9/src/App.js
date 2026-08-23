import React, { useState, useEffect } from 'react';
import AuthenticationConfig from './components/AuthenticationConfig';
import { getCompleteAuthConfig, updateAuthConfig } from './utils/authPersistence';

const App = () => {
  // Simulate request auth configuration state
  const [authConfig, setAuthConfig] = useState({
    mode: 'none',
    bearerToken: '',
    username: '',
    password: '',
    apiKey: ''
  });

  // Store previous config to handle mode switching
  const [previousAuthConfig, setPreviousAuthConfig] = useState(null);

  // Initialize with complete config including preserved data
  useEffect(() => {
    const completeConfig = getCompleteAuthConfig(authConfig);
    if (completeConfig) {
      setAuthConfig(completeConfig);
    }
  }, []);

  const handleAuthChange = (newConfig) => {
    // Store previous config before updating
    setPreviousAuthConfig(authConfig);
    
    // Update config with persistence logic
    const updatedConfig = updateAuthConfig(newConfig, authConfig);
    setAuthConfig(updatedConfig);
  };

  return (
    <div className="app">
      <h1>Bruno Authentication Fix</h1>
      <p>Fix for issue #5636: Preserve auth data when switching between auth modes</p>
      
      <div className="request-editor">
        <h2>Request Authentication Configuration</h2>
        <AuthenticationConfig 
          authConfig={authConfig} 
          onAuthChange={handleAuthChange} 
        />
      </div>
      
      <div className="debug-info">
        <h3>Current Auth Config:</h3>
        <pre>{JSON.stringify(authConfig, null, 2)}</pre>
      </div>
    </div>
  );
};

export default App;