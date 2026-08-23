import React from 'react';
import ManageWorkspaceMenu from './ManageWorkspaceMenu';
import terminalService from '../../services/terminalService';

const WorkspaceManager = ({ currentWorkspace }) => {
  const handleOpenInTerminal = (workspace) => {
    if (workspace) {
      terminalService.openInTerminal(workspace);
    }
  };

  return (
    <div className="workspace-manager">
      <h2>Manage Workspace</h2>
      <ManageWorkspaceMenu 
        workspace={currentWorkspace} 
        onOpenInTerminal={handleOpenInTerminal} 
      />
    </div>
  );
};

export default WorkspaceManager;