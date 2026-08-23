// Environment Manager for per-workspace global environment selection

class EnvironmentManager {
  constructor() {
    this.workspaceConfig = this.loadWorkspaceConfig();
  }

  // Load workspace configuration from file
  loadWorkspaceConfig() {
    try {
      const fs = require('fs');
      const configPath = 'workspace-config.json';
      if (fs.existsSync(configPath)) {
        return JSON.parse(fs.readFileSync(configPath, 'utf8'));
      }
    } catch (error) {
      console.error('Error loading workspace config:', error);
    }
    return { workspaces: {} };
  }

  // Save workspace configuration to file
  saveWorkspaceConfig() {
    try {
      const fs = require('fs');
      const configPath = 'workspace-config.json';
      fs.writeFileSync(configPath, JSON.stringify(this.workspaceConfig, null, 2));
    } catch (error) {
      console.error('Error saving workspace config:', error);
    }
  }

  // Get global environment for a specific workspace
  getGlobalEnvironment(workspaceId) {
    if (!this.workspaceConfig.workspaces[workspaceId]) {
      this.workspaceConfig.workspaces[workspaceId] = { globalEnvironment: '' };
      this.saveWorkspaceConfig();
    }
    return this.workspaceConfig.workspaces[workspaceId].globalEnvironment;
  }

  // Set global environment for a specific workspace
  setGlobalEnvironment(workspaceId, environmentId) {
    if (!this.workspaceConfig.workspaces[workspaceId]) {
      this.workspaceConfig.workspaces[workspaceId] = { globalEnvironment: '' };
    }
    this.workspaceConfig.workspaces[workspaceId].globalEnvironment = environmentId;
    this.saveWorkspaceConfig();
  }

  // Clear global environment selection for a workspace (when closing)
  clearWorkspaceEnvironment(workspaceId) {
    if (this.workspaceConfig.workspaces[workspaceId]) {
      this.workspaceConfig.workspaces[workspaceId].globalEnvironment = '';
      this.saveWorkspaceConfig();
    }
  }

  // Migrate legacy global environment selection to per-workspace
  migrateLegacySelection(legacyEnvironmentId) {
    // In a real implementation, this would migrate from old config format
    // For now, we'll set it as default workspace
    const defaultWorkspaceId = 'default';
    this.setGlobalEnvironment(defaultWorkspaceId, legacyEnvironmentId);
  }
}

module.exports = EnvironmentManager;