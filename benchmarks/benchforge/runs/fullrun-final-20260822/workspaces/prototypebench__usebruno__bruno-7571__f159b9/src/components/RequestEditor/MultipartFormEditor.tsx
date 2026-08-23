import React, { useState, useEffect } from 'react';

interface MultipartFormField {
  key: string;
  value: string;
  type: 'text' | 'file';
  file?: File;
}

interface MultipartFormEditorProps {
  fields: MultipartFormField[];
  onFieldsChange: (fields: MultipartFormField[]) => void;
}

const MultipartFormEditor: React.FC<MultipartFormEditorProps> = ({
  fields,
  onFieldsChange
}) => {
  const [localFields, setLocalFields] = useState<MultipartFormField[]>(fields);

  // Sync with parent when fields prop changes
  useEffect(() => {
    setLocalFields(fields);
  }, [fields]);

  const handleKeyChange = (index: number, key: string) => {
    const newFields = [...localFields];
    newFields[index].key = key;
    setLocalFields(newFields);
    onFieldsChange(newFields);
  };

  const handleValueChange = (index: number, value: string) => {
    const newFields = [...localFields];
    newFields[index].value = value;
    // Keep type as 'text' when entering text
    if (newFields[index].type === 'file' && value && !newFields[index].file) {
      newFields[index].type = 'text';
    }
    setLocalFields(newFields);
    onFieldsChange(newFields);
  };

  const handleFileTypeChange = (index: number) => {
    const newFields = [...localFields];
    newFields[index].type = 'file';
    newFields[index].value = '';
    newFields[index].file = undefined;
    setLocalFields(newFields);
    onFieldsChange(newFields);
  };

  const handleFileSelect = (index: number, file: File | null) => {
    const newFields = [...localFields];
    if (file) {
      newFields[index].file = file;
      newFields[index].value = file.name;
      newFields[index].type = 'file';
    } else {
      newFields[index].file = undefined;
      newFields[index].value = '';
      // Reset to text type if no file selected
      newFields[index].type = 'text';
    }
    setLocalFields(newFields);
    onFieldsChange(newFields);
  };

  const addField = () => {
    const newFields = [
      ...localFields,
      { key: '', value: '', type: 'text' }
    ];
    setLocalFields(newFields);
    onFieldsChange(newFields);
  };

  const removeField = (index: number) => {
    const newFields = localFields.filter((_, i) => i !== index);
    setLocalFields(newFields);
    onFieldsChange(newFields);
  };

  return (
    <div className="multipart-form-editor">
      <div className="form-header">
        <h3>Multipart Form Data</h3>
        <button onClick={addField} className="add-field-btn">
          + Add Field
        </button>
      </div>
      
      {localFields.map((field, index) => (
        <div key={index} className="form-field-row">
          <input
            type="text"
            placeholder="Key"
            value={field.key}
            onChange={(e) => handleKeyChange(index, e.target.value)}
            className="key-input"
          />
          
          <div className="value-container">
            {field.type === 'file' ? (
              <div className="file-input-container">
                <input
                  type="text"
                  placeholder="No file selected"
                  value={field.file ? field.file.name : field.value}
                  readOnly
                  className="file-name-input"
                />
                {/* File upload button is now always visible for file-type fields */}
                <button
                  onClick={() => {
                    const input = document.createElement('input');
                    input.type = 'file';
                    input.onchange = (e) => {
                      const files = (e.target as HTMLInputElement).files;
                      if (files && files.length > 0) {
                        handleFileSelect(index, files[0]);
                      }
                    };
                    input.click();
                  }}
                  className="file-upload-btn"
                  title="Select file"
                >
                  📎
                </button>
              </div>
            ) : (
              <input
                type="text"
                placeholder="Value"
                value={field.value}
                onChange={(e) => handleValueChange(index, e.target.value)}
                className="value-input"
              />
            )}
          </div>
          
          <div className="field-actions">
            <button 
              onClick={() => handleFileTypeChange(index)}
              className={`type-toggle-btn ${field.type === 'file' ? 'active' : ''}`}
              title={field.type === 'file' ? 'Switch to text' : 'Switch to file'}
            >
              {field.type === 'file' ? '🔤' : '📎'}
            </button>
            <button 
              onClick={() => removeField(index)}
              className="remove-btn"
              title="Remove field"
            >
              ×
            </button>
          </div>
        </div>
      ))}
      
      <style jsx>{`
        .multipart-form-editor {
          margin: 16px 0;
        }
        
        .form-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }
        
        .form-field-row {
          display: flex;
          gap: 8px;
          margin-bottom: 8px;
          align-items: center;
        }
        
        .key-input, .value-input {
          flex: 1;
          padding: 8px 12px;
          border: 1px solid #ddd;
          border-radius: 4px;
          font-size: 14px;
        }
        
        .file-input-container {
          display: flex;
          gap: 8px;
          flex: 1;
        }
        
        .file-name-input {
          flex: 1;
          padding: 8px 12px;
          border: 1px solid #ddd;
          border-radius: 4px;
          font-size: 14px;
          background-color: #f9f9f9;
        }
        
        .file-upload-btn {
          padding: 8px 12px;
          background-color: #007bff;
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 14px;
        }
        
        .file-upload-btn:hover {
          background-color: #0056b3;
        }
        
        .field-actions {
          display: flex;
          gap: 4px;
        }
        
        .type-toggle-btn {
          width: 32px;
          height: 32px;
          padding: 0;
          border: 1px solid #ddd;
          border-radius: 4px;
          background-color: white;
          cursor: pointer;
          font-size: 16px;
        }
        
        .type-toggle-btn.active {
          background-color: #007bff;
          color: white;
          border-color: #007bff;
        }
        
        .remove-btn {
          width: 32px;
          height: 32px;
          padding: 0;
          border: 1px solid #ddd;
          border-radius: 4px;
          background-color: white;
          cursor: pointer;
          font-size: 16px;
        }
        
        .remove-btn:hover {
          background-color: #dc3545;
          color: white;
          border-color: #dc3545;
        }
        
        .add-field-btn {
          padding: 6px 12px;
          background-color: #28a745;
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
        }
        
        .add-field-btn:hover {
          background-color: #218838;
        }
      `}</style>
    </div>
  );
};

export default MultipartFormEditor;
