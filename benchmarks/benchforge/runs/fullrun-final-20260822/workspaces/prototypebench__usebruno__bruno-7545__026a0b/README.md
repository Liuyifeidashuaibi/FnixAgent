# Per-Workspace Global Environment Selection

This implementation provides per-workspace global environment selection persistence for Bruno.

## Features

- ✅ Store global environment selection separately for each workspace
- ✅ Persist selections across application restarts
- ✅ Maintain separate selections when switching between workspaces
- ✅ Clear environment selection when closing a workspace
- ✅ Migrate legacy global environment selections to per-workspace format

## Usage

```javascript
const EnvironmentManager = require('./environment-manager');
const manager = new EnvironmentManager();

// Set global environment for workspace 'my-project'
manager.setGlobalEnvironment('my-project', 'production-env');

// Get global environment for workspace 'my-project'
const env = manager.getGlobalEnvironment('my-project');

// Clear environment when closing workspace
manager.clearWorkspaceEnvironment('my-project');
```

## Configuration

The configuration is stored in `workspace-config.json` with the following structure:

```json
{
  "workspaces": {
    "workspace-id-1": {
      "globalEnvironment": "env-id-1"
    },
    "workspace-id-2": {
      "globalEnvironment": "env-id-2"
    }
  }
}
```

## Migration

Legacy global environment selections are automatically migrated to the per-workspace format using the `migrateLegacySelection()` method.