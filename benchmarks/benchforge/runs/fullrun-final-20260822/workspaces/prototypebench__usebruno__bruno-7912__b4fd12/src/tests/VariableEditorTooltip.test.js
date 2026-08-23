import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import VariableEditorTooltip from '../components/VariableEditorTooltip';

// Mock the onCopy and onPinToggle functions
const mockOnCopy = jest.fn();
const mockOnPinToggle = jest.fn();

describe('VariableEditorTooltip', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should render with initial value', () => {
    render(
      <VariableEditorTooltip 
        value="test-value" 
        initialValue="initial-value" 
        onCopy={mockOnCopy} 
        onPinToggle={mockOnPinToggle} 
      />
    );
    
    expect(screen.getByText('test-value')).toBeInTheDocument();
  });

  it('should copy current value when copy button is clicked', () => {
    render(
      <VariableEditorTooltip 
        value="current-value" 
        initialValue="initial-value" 
        onCopy={mockOnCopy} 
        onPinToggle={mockOnPinToggle} 
      />
    );
    
    const copyButton = screen.getByTitle('Copy value');
    fireEvent.click(copyButton);
    
    expect(mockOnCopy).toHaveBeenCalledWith('current-value');
  });

  it('should toggle pin state when pin button is clicked', () => {
    render(
      <VariableEditorTooltip 
        value="test-value" 
        initialValue="initial-value" 
        onCopy={mockOnCopy} 
        onPinToggle={mockOnPinToggle} 
      />
    );
    
    const pinButton = screen.getByTitle('Pin tooltip');
    fireEvent.click(pinButton);
    
    expect(mockOnPinToggle).toHaveBeenCalledWith(true);
    
    // Click again to unpin
    const unpinButton = screen.getByTitle('Unpin tooltip');
    fireEvent.click(unpinButton);
    
    expect(mockOnPinToggle).toHaveBeenCalledWith(false);
  });

  it('should not dismiss when hovering over tooltip content', async () => {
    render(
      <VariableEditorTooltip 
        value="test-value" 
        initialValue="initial-value" 
        onCopy={mockOnCopy} 
        onPinToggle={mockOnPinToggle} 
      />
    );
    
    // Simulate hover over tooltip
    const tooltip = screen.getByRole('tooltip');
    fireEvent.mouseEnter(tooltip);
    
    // Should remain visible
    expect(tooltip).toBeInTheDocument();
    
    fireEvent.mouseLeave(tooltip);
    
    // Should still be visible for unpinned tooltips (since we're testing hover behavior)
    expect(tooltip).toBeInTheDocument();
  });
});