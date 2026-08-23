import React from 'react';
import { canOpenInTerminal } from '../../utils/workspaceUtils';

const ManageWorkspaceMenu = ({ workspace, onOpenInTerminal }) => {
  // Only show "Open in Terminal" for non-default workspaces with valid paths
  const canOpenTerminal = canOpenInTerminal(workspace);
  
  return (
    <div className="manage-workspace-menu">
      {canOpenTerminal && (
        <div className="menu-item" onClick={() => onOpenInTerminal(workspace)}>
          Open in Terminal
        </div>
      )}
      <div className="menu-item" onClick={() => console.log('Rename workspace')}>
        Rename
      </div>
      <div className="menu-item" onClick={() => console.log('Remove workspace')}>
        Remove
      </div>
    </div>
  );
};

export default ManageWorkspaceMenu;