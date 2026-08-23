import React, { useState, useRef, ChangeEvent } from 'react';

interface MultipartFile {
  id: string;
  name: string;
  path: string;
  size: number;
  type: string;
}

interface MultipartFileSelectorProps {
  value: MultipartFile[];
  onChange: (files: MultipartFile[]) => void;
  disabled?: boolean;
}

const MultipartFileSelector: React.FC<MultipartFileSelectorProps> = ({
  value,
  onChange,
  disabled = false
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    
    const newFiles: MultipartFile[] = Array.from(e.target.files).map(file => ({
      id: Math.random().toString(36).substr(2, 9),
      name: file.name,
      path: file.webkitRelativePath || file.name,
      size: file.size,
      type: file.type || 'application/octet-stream'
    }));
    
    // Merge with existing files
    const mergedFiles = [...value, ...newFiles];
    onChange(mergedFiles);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (!e.dataTransfer.files || e.dataTransfer.files.length === 0) return;
    
    const newFiles: MultipartFile[] = Array.from(e.dataTransfer.files).map(file => ({
      id: Math.random().toString(36).substr(2, 9),
      name: file.name,
      path: file.webkitRelativePath || file.name,
      size: file.size,
      type: file.type || 'application/octet-stream'
    }));
    
    const mergedFiles = [...value, ...newFiles];
    onChange(mergedFiles);
  };

  const removeFile = (id: string) => {
    const filteredFiles = value.filter(file => file.id !== id);
    onChange(filteredFiles);
  };

  const clearAllFiles = () => {
    onChange([]);
  };

  return (
    <div className="multipart-file-selector">
      <div 
        className={`drop-area ${isDragging ? 'dragging' : ''} ${disabled ? 'disabled' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileChange}
          className="hidden-input"
          disabled={disabled}
        />
        <div className="drop-area-content">
          <p>Drag & drop files here or click to browse</p>
          <p className="small-text">Supports multiple files</p>
        </div>
      </div>
      
      {value.length > 0 && (
        <div className="file-chips">
          <div className="file-chip-header">
            <span className="file-count">{value.length} file{value.length !== 1 ? 's' : ''}</span>
            <button 
              className="clear-all-btn" 
              onClick={clearAllFiles}
              disabled={disabled}
            >
              Clear all
            </button>
          </div>
          <div className="chips-container">
            {value.map(file => (
              <div key={file.id} className="file-chip">
                <span className="file-name">{file.name}</span>
                <span className="file-size">{(file.size / 1024).toFixed(1)} KB</span>
                {!disabled && (
                  <button 
                    className="remove-btn" 
                    onClick={() => removeFile(file.id)}
                    aria-label={`Remove ${file.name}`}
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default MultipartFileSelector;