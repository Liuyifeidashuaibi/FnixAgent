import React, { useState, useRef, useEffect } from 'react';

const PacProxySettings = ({ proxyConfig, onChange }) => {
  const [pacMode, setPacMode] = useState(proxyConfig?.pacMode || 'url');
  const [pacUrl, setPacUrl] = useState(proxyConfig?.pacUrl || '');
  const [pacFile, setPacFile] = useState(null);
  const [pacFileName, setPacFileName] = useState(proxyConfig?.pacFileName || '');
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (proxyConfig) {
      setPacMode(proxyConfig.pacMode || 'url');
      setPacUrl(proxyConfig.pacUrl || '');
      setPacFileName(proxyConfig.pacFileName || '');
      if (proxyConfig.pacFile) {
        setPacFile(proxyConfig.pacFile);
      }
    }
  }, [proxyConfig]);

  const handlePacModeChange = (mode) => {
    setPacMode(mode);
    if (mode === 'url') {
      onChange({
        ...proxyConfig,
        pacMode: 'url',
        pacUrl,
        pacFile: null,
        pacFileName: ''
      });
    } else {
      onChange({
        ...proxyConfig,
        pacMode: 'file',
        pacUrl: '',
        pacFile: null,
        pacFileName: ''
      });
    }
  };

  const handlePacUrlChange = (e) => {
    const url = e.target.value;
    setPacUrl(url);
    if (pacMode === 'url') {
      onChange({
        ...proxyConfig,
        pacMode: 'url',
        pacUrl: url,
        pacFile: null,
        pacFileName: ''
      });
    }
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target.result;
        setPacFile(content);
        setPacFileName(file.name);
        
        if (pacMode === 'file') {
          onChange({
            ...proxyConfig,
            pacMode: 'file',
            pacUrl: '',
            pacFile: content,
            pacFileName: file.name
          });
        }
      };
      reader.readAsText(file);
    }
  };

  const triggerFileInput = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const removeFile = () => {
    setPacFile(null);
    setPacFileName('');
    if (pacMode === 'file') {
      onChange({
        ...proxyConfig,
        pacMode: 'file',
        pacUrl: '',
        pacFile: null,
        pacFileName: ''
      });
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          PAC Proxy Mode
        </label>
        <div className="flex space-x-4">
          <label className="flex items-center">
            <input
              type="radio"
              name="pacMode"
              value="url"
              checked={pacMode === 'url'}
              onChange={() => handlePacModeChange('url')}
              className="mr-2 h-4 w-4 text-blue-600"
            />
            <span>URL</span>
          </label>
          <label className="flex items-center">
            <input
              type="radio"
              name="pacMode"
              value="file"
              checked={pacMode === 'file'}
              onChange={() => handlePacModeChange('file')}
              className="mr-2 h-4 w-4 text-blue-600"
            />
            <span>File Upload</span>
          </label>
        </div>
      </div>

      {pacMode === 'url' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            PAC File URL
          </label>
          <input
            type="url"
            value={pacUrl}
            onChange={handlePacUrlChange}
            placeholder="https://example.com/proxy.pac"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="mt-1 text-sm text-gray-500">
            Enter the URL to your PAC file. The file will be fetched when the request is made.
          </p>
        </div>
      )}

      {pacMode === 'file' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            PAC File
          </label>
          <div className="flex items-center space-x-3">
            <button
              type="button"
              onClick={triggerFileInput}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
            >
              Browse...
            </button>
            {pacFileName && (
              <div className="flex items-center space-x-2">
                <span className="text-sm text-gray-700">{pacFileName}</span>
                <button
                  type="button"
                  onClick={removeFile}
                  className="text-red-600 hover:text-red-800"
                >
                  ×
                </button>
              </div>
            )}
          </div>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            accept=".pac,text/plain"
            className="hidden"
          />
          <p className="mt-1 text-sm text-gray-500">
            Upload a PAC file (.pac extension). The file will be read and used for proxy routing.
          </p>
        </div>
      )}
    </div>
  );
};

export default PacProxySettings;