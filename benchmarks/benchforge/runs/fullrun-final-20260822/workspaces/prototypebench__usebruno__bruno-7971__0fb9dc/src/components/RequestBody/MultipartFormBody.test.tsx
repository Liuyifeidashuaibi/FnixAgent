import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import MultipartFormBody from './MultipartFormBody';

// Mock the FileChip and MultipartFileSelector components
jest.mock('./FileChip', () => {
  return jest.fn(({ fileName, fileSize, onRemove }) => (
    <div data-testid="file-chip">
      <span>{fileName}</span>
      <span>{fileSize} bytes</span>
      {onRemove && <button onClick={onRemove}>Remove</button>}
    </div>
  ));
});

jest.mock('./MultipartFileSelector', () => {
  return jest.fn(({ value, onChange }) => (
    <div data-testid="file-selector">
      <input 
        type="file" 
        multiple 
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) {
            const files = Array.from(e.target.files).map(file => ({
              id: Math.random().toString(36).substr(2, 9),
              name: file.name,
              path: file.name,
              size: file.size,
              type: file.type || 'application/octet-stream'
            }));
            onChange(files);
          }
        }} 
      />
      <div>Selected: {value.length} files</div>
    </div>
  ));
});

describe('MultipartFormBody', () => {
  const mockOnChange = jest.fn();
  
  beforeEach(() => {
    mockOnChange.mockClear();
  });

  it('renders form fields and file selector', () => {
    render(
      <MultipartFormBody 
        value={{ key1: 'value1' }} 
        files={[]} 
        onChange={mockOnChange} 
      />
    );
    
    expect(screen.getByText('Form Fields')).toBeInTheDocument();
    expect(screen.getByText('Files')).toBeInTheDocument();
    expect(screen.getByText('Selected: 0 files')).toBeInTheDocument();
  });

  it('handles adding new form fields', () => {
    render(
      <MultipartFormBody 
        value={{}} 
        files={[]} 
        onChange={mockOnChange} 
      />
    );
    
    const addBtn = screen.getByText('+ Add Field');
    fireEvent.click(addBtn);
    
    // Check that onChange was called with new field
    expect(mockOnChange).toHaveBeenCalledTimes(1);
  });

  it('handles file selection and displays chips', () => {
    const mockFiles = [
      { id: '1', name: 'test.txt', path: 'test.txt', size: 1024, type: 'text/plain' },
      { id: '2', name: 'image.png', path: 'image.png', size: 2048, type: 'image/png' }
    ];
    
    render(
      <MultipartFormBody 
        value={{}} 
        files={mockFiles} 
        onChange={mockOnChange} 
      />
    );
    
    expect(screen.getAllByTestId('file-chip')).toHaveLength(2);
    expect(screen.getByText('test.txt')).toBeInTheDocument();
    expect(screen.getByText('image.png')).toBeInTheDocument();
  });

  it('handles file removal', () => {
    const mockFiles = [
      { id: '1', name: 'test.txt', path: 'test.txt', size: 1024, type: 'text/plain' }
    ];
    
    render(
      <MultipartFormBody 
        value={{}} 
        files={mockFiles} 
        onChange={mockOnChange} 
      />
    );
    
    const removeBtn = screen.getByText('Remove');
    fireEvent.click(removeBtn);
    
    expect(mockOnChange).toHaveBeenCalledTimes(1);
  });
});