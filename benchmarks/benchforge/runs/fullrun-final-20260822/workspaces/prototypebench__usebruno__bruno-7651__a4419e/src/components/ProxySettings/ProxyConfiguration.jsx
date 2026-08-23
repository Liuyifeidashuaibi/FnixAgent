import React, { useState, useEffect } from 'react';

const ProxyConfiguration = ({ proxyConfig, onChange }) => {
  const [proxyMode, setProxyMode] = useState(proxyConfig?.mode || 'none');
  const [httpProxy, setHttpProxy] = useState(proxyConfig?.http || '');
  const [httpsProxy, setHttpsProxy] = useState(proxyConfig?.https || '');
  const [pacConfig, setPacConfig] = useState({
    pacMode: proxyConfig?.pacMode || 'url',
    pacUrl: proxyConfig?.pacUrl || '',
    pacFile: proxyConfig?.pacFile || null,
    pacFileName: proxyConfig?.pacFileName || ''
  });

  useEffect(() => {
    if (proxyConfig) {
      setProxyMode(proxyConfig.mode || 'none');
      setHttpProxy(proxyConfig.http || '');
      setHttpsProxy(proxyConfig.https || '');
      
      setPacConfig({
        pacMode: proxyConfig.pacMode || 'url',
        pacUrl: proxyConfig.pacUrl || '',
        pacFile: proxyConfig.pacFile || null,
        pacFileName: proxyConfig.pacFileName || ''
      });
    }
  }, [proxyConfig]);

  const handleProxyModeChange = (mode) => {
    setProxyMode(mode);
    
    // Reset other config when changing mode
    if (mode === 'none') {
      onChange({
        mode: 'none'
      });
    } else if (mode === 'manual') {
      onChange({
        mode: 'manual',
        http: httpProxy,
        https: httpsProxy
      });
    } else if (mode === 'pac') {
      onChange({
        mode: 'pac',
        ...pacConfig
      });
    }
  };

  const handleHttpProxyChange = (e) => {
    const value = e.target.value;
    setHttpProxy(value);
    if (proxyMode === 'manual') {
      onChange({
        mode: 'manual',
        http: value,
        https: httpsProxy
      });
    }
  };

  const handleHttpsProxyChange = (e) => {
    const value = e.target.value;
    setHttpsProxy(value);
    if (proxyMode === 'manual') {
      onChange({
        mode: 'manual',
        http: httpProxy,
        https: value
      });
    }
  };

  const handlePacConfigChange = (config) => {
    setPacConfig(config);
    if (proxyMode === 'pac') {
      onChange({
        mode: 'pac',
        ...config
      });
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Proxy Mode
        </label>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <label className="flex items-center p-3 border rounded-md cursor-pointer hover:bg-gray-50">
            <input
              type="radio"
              name="proxyMode"
              value="none"
              checked={proxyMode === 'none'}
              onChange={() => handleProxyModeChange('none')}
              className="mr-2 h-4 w-4 text-blue-600"
            />
            <span className="font-medium">No Proxy</span>
          </label>
          
          <label className="flex items-center p-3 border rounded-md cursor-pointer hover:bg-gray-50">
            <input
              type="radio"
              name="proxyMode"
              value="manual"
              checked={proxyMode === 'manual'}
              onChange={() => handleProxyModeChange('manual')}
              className="mr-2 h-4 w-4 text-blue-600"
            />
            <span className="font-medium">Manual</span>
          </label>
          
          <label className="flex items-center p-3 border rounded-md cursor-pointer hover:bg-gray-50">
            <input
              type="radio"
              name="proxyMode"
              value="pac"
              checked={proxyMode === 'pac'}
              onChange={() => handleProxyModeChange('pac')}
              className="mr-2 h-4 w-4 text-blue-600"
            />
            <span className="font-medium">PAC File</span>
          </label>
        </div>
      </div>

      {proxyMode === 'manual' && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              HTTP Proxy
            </label>
            <input
              type="text"
              value={httpProxy}
              onChange={handleHttpProxyChange}
              placeholder="http://proxy.example.com:8080"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              HTTPS Proxy
            </label>
            <input
              type="text"
              value={httpsProxy}
              onChange={handleHttpsProxyChange}
              placeholder="https://proxy.example.com:8080"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
      )}

      {proxyMode === 'pac' && (
        <div className="border-t pt-4">
          <h3 className="text-lg font-medium text-gray-900 mb-4">PAC Proxy Configuration</h3>
          {/* Import the PacProxySettings component */}
          <div className="bg-gray-50 p-4 rounded-md">
            <p className="text-sm text-gray-600 mb-3">
              Configure how Bruno should use Proxy Auto-Configuration (PAC) files to determine proxy settings.
            </p>
            {/* This would be imported in a real app */}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  PAC Mode
                </label>
                <div className="flex space-x-4">
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="pacMode"
                      value="url"
                      checked={pacConfig.pacMode === 'url'}
                      onChange={() => handlePacConfigChange({...pacConfig, pacMode: 'url'})}
                      className="mr-2 h-4 w-4 text-blue-600"
                    />
                    <span>URL</span>
                  </label>
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="pacMode"
                      value="file"
                      checked={pacConfig.pacMode === 'file'}
                      onChange={() => handlePacConfigChange({...pacConfig, pacMode: 'file'})}
                      className="mr-2 h-4 w-4 text-blue-600"
                    />
                    <span>File Upload</span>
                  </label>
                </div>
              </div>

              {pacConfig.pacMode === 'url' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    PAC File URL
                  </label>
                  <input
                    type="url"
                    value={pacConfig.pacUrl}
                    onChange={(e) => handlePacConfigChange({...pacConfig, pacUrl: e.target.value})}
                    placeholder="https://example.com/proxy.pac"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              )}

              {pacConfig.pacMode === 'file' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    PAC File
                  </label>
                  <div className="flex items-center space-x-3">
                    <button
                      type="button"
                      onClick={() => document.getElementById('pacFileInput').click()}
                      className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                    >
                      Browse...
                    </button>
                    {pacConfig.pacFileName && (
                      <div className="flex items-center space-x-2">
                        <span className="text-sm text-gray-700">{pacConfig.pacFileName}</span>
                        <button
                          type="button"
                          onClick={() => handlePacConfigChange({...pacConfig, pacFile: null, pacFileName: ''})}
                          className="text-red-600 hover:text-red-800"
                        >
                          ×
                        </button>
                      </div>
                    )}
                  </div>
                  <input
                    type="file"
                    id="pacFileInput"
                    onChange={(e) => {
                      const file = e.target.files[0];
                      if (file) {
                        const reader = new FileReader();
                        reader.onload = (e) => {
                          handlePacConfigChange({
                            ...pacConfig,
                            pacMode: 'file',
                            pacFile: e.target.result,
                            pacFileName: file.name
                          });
                        };
                        reader.readAsText(file);
                      }
                    }}
                    accept=".pac,text/plain"
                    className="hidden"
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="pt-4 border-t">
        <p className="text-sm text-gray-600">
          PAC (Proxy Auto-Configuration) files allow Bruno to automatically determine the appropriate proxy server for each URL based on JavaScript functions.
        </p>
      </div>
    </div>
  );
};

export default ProxyConfiguration;