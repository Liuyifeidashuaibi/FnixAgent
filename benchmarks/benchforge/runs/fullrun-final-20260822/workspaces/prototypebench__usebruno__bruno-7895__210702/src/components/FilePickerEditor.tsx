import * as React from 'react';
import { getRelativePathWithinBasePath } from '../utils/pathUtils';

interface FilePickerEditorProps {
  basePath: string;
  filePath: string;
  onChange: (relativePath: string | undefined) => void;
}

const FilePickerEditor: React.FC<FilePickerEditorProps> = ({
  basePath,
  filePath,
  onChange
}) => {
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileInput = e.target;
    if (fileInput.files && fileInput.files.length > 0) {
      const selectedFilePath = fileInput.files[0].path || '';
      
      // Use centralized utility instead of ad-hoc startsWith logic
      const relativePath = getRelativePathWithinBasePath(basePath, selectedFilePath);
      
      onChange(relativePath);
    }
  };

  return (
    <div className="file-picker-editor">
      <input
        type="file"
        onChange={handleFileChange}
        className="file-input"
      />
      <div className="current-path">
        {filePath ? `Current path: ${filePath}` : 'No file selected'}
      </div>
    </div>
  );
};

export default FilePickerEditor;