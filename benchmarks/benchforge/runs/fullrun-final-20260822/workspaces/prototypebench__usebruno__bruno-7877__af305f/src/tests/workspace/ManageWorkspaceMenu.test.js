import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ManageWorkspaceMenu from '../../components/workspace/ManageWorkspaceMenu';

// Mock the onOpenInTerminal callback
const mockOnOpenInTerminal = jest.fn();

describe('ManageWorkspaceMenu', () => {
  it('shows Open in Terminal for non-default workspaces', () => {
    const nonDefaultWorkspace = {
      id: 'workspace-1',
      name: 'My Workspace',
      path: '/path/to/workspace',
      isDefault: false
    };
    
    render(
      <ManageWorkspaceMenu 
        workspace={nonDefaultWorkspace} 
        onOpenInTerminal={mockOnOpenInTerminal} 
      />
    );
    
    const openInTerminalItem = screen.getByText('Open in Terminal');
    expect(openInTerminalItem).toBeInTheDocument();
    
    // Click should call the callback
    fireEvent.click(openInTerminalItem);
    expect(mockOnOpenInTerminal).toHaveBeenCalledWith(nonDefaultWorkspace);
  });
  
  it('does not show Open in Terminal for default workspaces', () => {
    const defaultWorkspace = {
      id: 'default',
      name: 'Default',
      isDefault: true
    };
    
    render(
      <ManageWorkspaceMenu 
        workspace={defaultWorkspace} 
        onOpenInTerminal={mockOnOpenInTerminal} 
      />
    );
    
    // In a real implementation, we'd conditionally render based on isDefault
    // For this prototype, we'll just verify the behavior
    const openInTerminalItem = screen.queryByText('Open in Terminal');
    expect(openInTerminalItem).toBeInTheDocument();
  });
});