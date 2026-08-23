import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ClearCacheButton from './clear-cache-button';

describe('ClearCacheButton', () => {
  it('renders with correct text and title', () => {
    render(<ClearCacheButton onClear={jest.fn()} />);
    
    const button = screen.getByText('Clear Cache');
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute('title', 'Clear all cached data');
  });

  it('calls onClear handler when clicked', () => {
    const mockOnClear = jest.fn();
    render(<ClearCacheButton onClear={mockOnClear} />);
    
    const button = screen.getByText('Clear Cache');
    fireEvent.click(button);
    
    expect(mockOnClear).toHaveBeenCalledTimes(1);
  });
});
