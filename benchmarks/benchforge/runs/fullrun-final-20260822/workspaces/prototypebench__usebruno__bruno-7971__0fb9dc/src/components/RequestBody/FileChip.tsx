import React from 'react';

interface FileChipProps {
  fileName: string;
  fileSize: number;
  onRemove?: () => void;
  isReadOnly?: boolean;
}

const FileChip: React.FC<FileChipProps> = ({
  fileName,
  fileSize,
  onRemove,
  isReadOnly = false
}) => {
  const formatFileSize = (size: number): string => {
    if (size === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(size) / Math.log(k));
    return parseFloat((size / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className="file-chip">
      <div className="file-chip-content">
        <span className="file-name">{fileName}</span>
        <span className="file-size">{formatFileSize(fileSize)}</span>
      </div>
      {!isReadOnly && onRemove && (
        <button 
          className="file-chip-remove-btn" 
          onClick={onRemove}
          aria-label={`Remove ${fileName}`}
        >
          ×
        </button>
      )}
    </div>
  );
};

export default FileChip;