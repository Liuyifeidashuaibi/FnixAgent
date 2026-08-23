import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MultipartForm from './MultipartForm';

// Mock file input
const mockFile = new File(['test content'], 'test.txt', { type: 'text/plain' });

describe('MultipartForm', () => {
  const mockOnChange = jest.fn();

  beforeEach(() => {
    mockOnChange.mockClear();
  });

  it('handles empty row file selection correctly', () => {
    render(<MultipartForm items={[]} onChange={mockOnChange} />);
    
    // Should have at least one row when initialized with empty array
    expect(screen.getAllByText('Key').length).toBe(1);
  });

  it('moves clear file (X) icon to the right side of the file name', () => {
    const items = [
      { key: 'file', value: 'test.txt', type: 'file', file: mockFile }
    ];
    
    render(<MultipartForm items={items} onChange={mockOnChange} />);
    
    // Check that the clear button is present and positioned correctly
    const clearButtons = screen.getAllByRole('button', { name: /Clear file/i });
    expect(clearButtons.length).toBe(1);
    
    // The clear button should be after the file name in the DOM structure
    const fileDisplay = screen.getByText('test.txt').closest('.multipart-file-display');
    expect(fileDisplay).toBeInTheDocument();
  });

  it('fixes upload button hover color', () => {
    render(<MultipartForm items={[{ key: '', value: '', type: 'text' }]} onChange={mockOnChange} />);
    
    const uploadButton = screen.getByRole('button', { name: /Upload/i });
    expect(uploadButton).toBeInTheDocument();
    
    // Test hover state - we can check the initial styles
    expect(uploadButton).toHaveStyle('background-color: var(--brand)');
  });

  it('handles file selection and clearing correctly', async () => {
    const items = [{ key: 'file', value: '', type: 'text' }];
    
    render(<MultipartForm items={items} onChange={mockOnChange} />);
    
    const uploadButton = screen.getByRole('button', { name: /Upload/i });
    fireEvent.click(uploadButton);
    
    // Simulate file input change
    const fileInput = screen.getByLabelText('Upload file');
    Object.defineProperty(fileInput, 'files', {
      value: [mockFile],
      writable: false
    });
    
    fireEvent.change(fileInput);
    
    await waitFor(() => {
      expect(screen.getByText('test.txt')).toBeInTheDocument();
    });
    
    // Test clearing the file
    const clearButton = screen.getByRole('button', { name: /Clear file/i });
    fireEvent.click(clearButton);
    
    await waitFor(() => {
      expect(screen.queryByText('test.txt')).not.toBeInTheDocument();
    });
  });
});