import React, { useState, useRef, useEffect } from 'react';

interface MultipartFormItem {
  key: string;
  value: string;
  type: 'text' | 'file';
  file?: File;
}

interface MultipartFormProps {
  items: MultipartFormItem[];
  onChange: (items: MultipartFormItem[]) => void;
}

const MultipartForm: React.FC<MultipartFormProps> = ({ items, onChange }) => {
  const [multipartItems, setMultipartItems] = useState<MultipartFormItem[]>(items);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Handle empty row file selection - ensure we have at least one empty row
  useEffect(() => {
    if (multipartItems.length === 0) {
      setMultipartItems([{ key: '', value: '', type: 'text' }]);
    }
  }, [multipartItems.length]);

  const handleFileSelect = (index: number) => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>, index: number) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const newItems = [...multipartItems];
      newItems[index] = {
        ...newItems[index],
        type: 'file',
        file: files[0],
        value: files[0].name
      };
      setMultipartItems(newItems);
      onChange(newItems);
    }
  };

  const handleClearFile = (index: number) => {
    const newItems = [...multipartItems];
    newItems[index] = {
      ...newItems[index],
      type: 'text',
      file: undefined,
      value: ''
    };
    setMultipartItems(newItems);
    onChange(newItems);
  };

  const addRow = () => {
    setMultipartItems([...multipartItems, { key: '', value: '', type: 'text' }]);
  };

  const removeRow = (index: number) => {
    if (multipartItems.length > 1) {
      const newItems = multipartItems.filter((_, i) => i !== index);
      setMultipartItems(newItems);
      onChange(newItems);
    }
  };

  const updateItem = (index: number, field: 'key' | 'value', value: string) => {
    const newItems = [...multipartItems];
    newItems[index] = { ...newItems[index], [field]: value };
    setMultipartItems(newItems);
    onChange(newItems);
  };

  return (
    <div className="multipart-form">
      <div className="multipart-form-header">
        <span className="multipart-form-label">Key</span>
        <span className="multipart-form-label">Value</span>
      </div>
      {multipartItems.map((item, index) => (
        <div key={index} className="multipart-form-row">
          <input
            type="text"
            className="multipart-form-key"
            value={item.key}
            onChange={(e) => updateItem(index, 'key', e.target.value)}
            placeholder="Key"
          />
          <div className="multipart-form-value-container">
            {item.type === 'file' ? (
              <div className="multipart-file-display">
                <span className="multipart-file-name">{item.value}</span>
                <button 
                  type="button" 
                  className="multipart-clear-button"
                  onClick={() => handleClearFile(index)}
                  aria-label="Clear file"
                >
                  ×
                </button>
              </div>
            ) : (
              <input
                type="text"
                className="multipart-form-value"
                value={item.value}
                onChange={(e) => updateItem(index, 'value', e.target.value)}
                placeholder="Value or select file"
              />
            )}
            <button 
              type="button" 
              className="multipart-upload-button"
              onClick={() => handleFileSelect(index)}
              aria-label="Upload file"
            >
              Upload
            </button>
          </div>
          <button 
            type="button" 
            className="multipart-remove-button"
            onClick={() => removeRow(index)}
            aria-label="Remove row"
          >
            ×
          </button>
        </div>
      ))}
      <button 
        type="button" 
        className="multipart-add-button"
        onClick={addRow}
      >
        + Add Row
      </button>
      <input
        type="file"
        ref={fileInputRef}
        onChange={(e) => handleFileChange(e, multipartItems.length - 1)}
        className="hidden"
        aria-hidden="true"
      />
    </div>
  );
};

export default MultipartForm;