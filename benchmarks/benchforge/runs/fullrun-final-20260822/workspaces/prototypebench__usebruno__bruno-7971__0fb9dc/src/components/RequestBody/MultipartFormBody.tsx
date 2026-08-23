import React, { useState, useEffect } from 'react';
import MultipartFileSelector from './MultipartFileSelector';
import FileChip from './FileChip';
import { normalizeFilePaths, detectContentType } from '../utils/multipartUtils';

interface MultipartFormBodyProps {
  value: Record<string, any>;
  files: Array<{ id: string; name: string; path: string; size: number; type: string }>;
  onChange: (value: Record<string, any>, files: Array<{ id: string; name: string; path: string; size: number; type: string }>) => void;
  disabled?: boolean;
  collectionPath?: string;
}

const MultipartFormBody: React.FC<MultipartFormBodyProps> = ({
  value,
  files,
  onChange,
  disabled = false,
  collectionPath
}) => {
  const [formData, setFormData] = useState<Record<string, any>>(value);
  const [multipartFiles, setMultipartFiles] = useState<Array<{ id: string; name: string; path: string; size: number; type: string }>>(files);

  // Sync external changes
  useEffect(() => {
    setFormData(value);
  }, [value]);

  useEffect(() => {
    setMultipartFiles(files);
  }, [files]);

  const handleFormChange = (key: string, value: string) => {
    const newFormData = { ...formData, [key]: value };
    setFormData(newFormData);
    onChange(newFormData, multipartFiles);
  };

  const handleFilesChange = (newFiles: Array<{ id: string; name: string; path: string; size: number; type: string }>) => {
    // Normalize paths and detect content types
    const normalizedFiles = normalizeFilePaths(newFiles, collectionPath).map(file => ({
      ...file,
      type: file.type || detectContentType(file.name)
    }));
    
    setMultipartFiles(normalizedFiles);
    onChange(formData, normalizedFiles);
  };

  const removeFile = (id: string) => {
    const filteredFiles = multipartFiles.filter(file => file.id !== id);
    setMultipartFiles(filteredFiles);
    onChange(formData, filteredFiles);
  };

  const addFormField = () => {
    const newKey = `field_${Date.now()}`;
    const newFormData = { ...formData, [newKey]: '' };
    setFormData(newFormData);
    onChange(newFormData, multipartFiles);
  };

  return (
    <div className="multipart-form-body">
      <div className="form-fields-section">
        <h3>Form Fields</h3>
        <div className="form-fields-list">
          {Object.entries(formData).map(([key, value]) => (
            <div key={key} className="form-field-row">
              <input
                type="text"
                value={key}
                onChange={(e) => {
                  const newFormData = { ...formData };
                  delete newFormData[key];
                  newFormData[e.target.value] = value;
                  setFormData(newFormData);
                  onChange(newFormData, multipartFiles);
                }}
                placeholder="Key"
                disabled={disabled}
              />
              <input
                type="text"
                value={String(value)}
                onChange={(e) => handleFormChange(key, e.target.value)}
                placeholder="Value"
                disabled={disabled}
              />
            </div>
          ))}
        </div>
        {!disabled && (
          <button className="add-field-btn" onClick={addFormField}>
            + Add Field
          </button>
        )}
      </div>

      <div className="files-section">
        <h3>Files</h3>
        <MultipartFileSelector 
          value={multipartFiles} 
          onChange={handleFilesChange} 
          disabled={disabled} 
        />
        
        {multipartFiles.length > 0 && (
          <div className="files-list">
            <h4>Selected Files ({multipartFiles.length})</h4>
            <div className="files-chips">
              {multipartFiles.map(file => (
                <FileChip 
                  key={file.id} 
                  fileName={file.name} 
                  fileSize={file.size} 
                  onRemove={() => removeFile(file.id)} 
                  isReadOnly={disabled} 
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default MultipartFormBody;