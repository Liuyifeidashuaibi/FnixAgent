import { app } from 'electron';

// Service to handle opening terminals for workspaces
const terminalService = {
  openInTerminal: (workspace) => {
    if (!workspace || !workspace.path) {
      console.warn('Cannot open terminal: workspace has no path');
      return;
    }
    
    // Check if this is a non-default workspace
    if (workspace.isDefault) {
      console.warn('Cannot open terminal for default workspace');
      return;
    }
    
    try {
      // Electron API to open terminal in workspace directory
      app.openExternal(`file://${workspace.path}`);
      
      // In a real implementation, this would use platform-specific terminal commands
      // For example: 'cmd.exe /c start cmd.exe /k cd /d "' + workspace.path + '"'
      console.log(`Opening terminal in workspace: ${workspace.path}`);
    } catch (error) {
      console.error('Failed to open terminal:', error);
    }
  }
};

export default terminalService;