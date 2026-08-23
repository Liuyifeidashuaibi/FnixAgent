import * as React from 'react';
import { getRelativePathWithinBasePath } from '../utils/pathUtils';

interface MultipartFormParam {
  name: string;
  value: string;
  type: 'text' | 'file';
  filePath?: string;
}

interface MultipartFormParamsProps {
  basePath: string;
  params: MultipartFormParam[];
  onChange: (params: MultipartFormParam[]) => void;
}

const MultipartFormParams: React.FC<MultipartFormParamsProps> = ({
  basePath,
  params,
  onChange
}) => {
  const handleFileChange = (index: number, e: React.ChangeEvent<HTMLInputElement>) => {
    const fileInput = e.target;
    if (fileInput.files && fileInput.files.length > 0) {
      const selectedFilePath = fileInput.files[0].path || '';
      
      // Use centralized utility instead of ad-hoc startsWith logic
      const relativePath = getRelativePathWithinBasePath(basePath, selectedFilePath);
      
      const updatedParams = [...params];
      updatedParams[index] = {
        ...updatedParams[index],
        filePath: relativePath || '',
        value: relativePath || ''
      };
      
      onChange(updatedParams);
    }
  };

  return (
    <div className="multipart-form-params">
      <h3>Multipart Form Parameters</h3>
      {params.map((param, index) => (
        <div key={index} className="param-item">
          <label>{param.name}:</label>
          {param.type === 'file' ? (
            <input
              type="file"
              onChange={(e) => handleFileChange(index, e)}
              className="file-input"
            />
          ) : (
            <input
              type="text"
              value={param.value}
              onChange={(e) => {
                const updatedParams = [...params];
                updatedParams[index] = {
                  ...updatedParams[index],
                  value: e.target.value
                };
                onChange(updatedParams);
              }}
              className="text-input"
            />
          )}
        </div>
      ))}
    </div>
  );
};

export default MultipartFormParams;