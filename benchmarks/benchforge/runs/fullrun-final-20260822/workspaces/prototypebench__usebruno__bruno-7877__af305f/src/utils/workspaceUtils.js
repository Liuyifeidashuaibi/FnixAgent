// Utility functions for workspace management

export const isDefaultWorkspace = (workspace) => {
  // Default workspace is typically the one with no path or special identifier
  return !workspace || 
         !workspace.path || 
         workspace.isDefault === true || 
         workspace.name === 'Default' || 
         workspace.id === 'default';
};

export const canOpenInTerminal = (workspace) => {
  // Only non-default workspaces with valid paths can open in terminal
  return workspace && 
         workspace.path && 
         !isDefaultWorkspace(workspace);
};