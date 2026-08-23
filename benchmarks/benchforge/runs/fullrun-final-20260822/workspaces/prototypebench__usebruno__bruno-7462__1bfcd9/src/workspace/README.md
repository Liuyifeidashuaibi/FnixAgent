# Workspace Creation Feature

This module provides the functionality for creating new workspaces in Bruno.

## Components

### `WorkspaceCreation`
Main workspace creation component with basic flow:
- Workspace name input
- Settings cog for advanced options
- Confirm/Cancel buttons
- Real-time validation

### `AdvancedWorkspaceModal`
Modal dialog for advanced workspace creation:
- Custom path selection
- Default location option
- Enhanced validation

## Utilities

### `workspaceValidation`
Validation utilities for workspace creation:
- `validateWorkspaceName()` - Validates name format and length
- `checkDuplicateWorkspaceName()` - Checks for existing workspaces with same name
- `validateCustomPath()` - Validates custom filesystem paths
- `validateWorkspace()` - Combines all validations

### `workspaceService`
Filesystem service for workspace management:
- `createWorkspace()` - Creates workspace directory and configuration
- `getWorkspaces()` - Retrieves list of existing workspaces

## Usage

```javascript
import { WorkspaceCreation } from './workspace';

const App = () => {
  const handleCreate = (workspaceData) => {
    console.log('Creating workspace:', workspaceData);
    // Handle workspace creation logic
  };

  return (
    <WorkspaceCreation 
      onCreate={handleCreate} 
      onCancel={() => console.log('Cancelled')} 
    />
  );
};
```

## Validation Rules

- Workspace names must be 2-50 characters long
- Only letters, numbers, spaces, hyphens, and underscores allowed
- No leading or trailing spaces
- Reserved names: `default`, `temp`, `workspace`, `bruno`
- Cannot duplicate existing workspace names
- Custom paths are validated for safety

## Filesystem Operations

The workspace service simulates filesystem operations. In production, it would use Electron's `fs` module to:
- Create workspace directories
- Write `bruno.json` configuration files
- Create initial collections structure
- Handle cross-platform path resolution