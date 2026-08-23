import React, { useState } from 'react';
import { MultipartFormBody } from './index';

// Example of how this would be integrated into Bruno's request editor
const BrunoRequestEditor = () => {
  const [formData, setFormData] = useState<Record<string, any>>({
    'username': 'john_doe',
    'email': 'john@example.com'
  });
  
  const [files, setFiles] = useState<Array<{ id: string; name: string; path: string; size: number; type: string }>>([]);
  
  const handleMultipartChange = (
    newFormData: Record<string, any>, 
    newFiles: Array<{ id: string; name: string; path: string; size: number; type: string }>
  ) => {
    setFormData(newFormData);
    setFiles(newFiles);
    
    // In Bruno, this would trigger a save/update of the request
    console.log('Multipart data updated:', { formData: newFormData, files: newFiles });
  };
  
  return (
    <div className="bruno-request-editor">
      <h2>API Request Editor</h2>
      <div className="request-body-section">
        <h3>Request Body</h3>
        <div className="body-type-selector">
          <button className="active">multipart/form-data</button>
          <button>application/json</button>
          <button>text/plain</button>
        </div>
        
        {/* This is where the multipart form body component would be used */}
        <MultipartFormBody 
          value={formData} 
          files={files} 
          onChange={handleMultipartChange} 
          collectionPath="/path/to/collection"
        />
      </div>
    </div>
  );
};

export default BrunoRequestEditor;