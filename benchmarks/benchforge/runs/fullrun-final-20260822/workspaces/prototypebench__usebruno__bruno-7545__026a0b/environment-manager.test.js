const EnvironmentManager = require('./environment-manager');

describe('EnvironmentManager', () => {
  let manager;

  beforeEach(() => {
    manager = new EnvironmentManager();
    // Clear any existing config for clean test
    manager.workspaceConfig = { workspaces: {} };
  });

  test('should store global environment per workspace', () => {
    manager.setGlobalEnvironment('workspace-1', 'env-123');
    manager.setGlobalEnvironment('workspace-2', 'env-456');
    
    expect(manager.getGlobalEnvironment('workspace-1')).toBe('env-123');
    expect(manager.getGlobalEnvironment('workspace-2')).toBe('env-456');
  });

  test('should persist selections across instances', () => {
    // First instance
    const manager1 = new EnvironmentManager();
    manager1.workspaceConfig = { workspaces: { 'workspace-1': { globalEnvironment: 'env-123' } } };
    
    // Second instance
    const manager2 = new EnvironmentManager();
    manager2.workspaceConfig = { workspaces: { 'workspace-1': { globalEnvironment: 'env-123' } } };
    
    expect(manager2.getGlobalEnvironment('workspace-1')).toBe('env-123');
  });

  test('should clear environment when closing workspace', () => {
    manager.setGlobalEnvironment('workspace-1', 'env-123');
    expect(manager.getGlobalEnvironment('workspace-1')).toBe('env-123');
    
    manager.clearWorkspaceEnvironment('workspace-1');
    expect(manager.getGlobalEnvironment('workspace-1')).toBe('');
  });

  test('should migrate legacy environment selection', () => {
    manager.migrateLegacySelection('legacy-env');
    expect(manager.getGlobalEnvironment('default')).toBe('legacy-env');
  });
});