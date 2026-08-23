# Bruno - Open in Terminal Feature

## Description

This implementation adds the "Open in Terminal" functionality to the Manage Workspace menu for non-default workspaces, addressing [BRU-3193](https://usebruno.atlassian.net/browse/BRU-3193) and fixing [issue #6770](https://github.com/usebruno/bruno/issues/6770).

## Features

- ✅ "Open in Terminal" menu item appears only for non-default workspaces
- ✅ Validates workspace path before attempting to open terminal
- ✅ Platform-agnostic terminal opening logic
- ✅ Proper error handling for invalid workspaces
- ✅ Unit tests for the new functionality

## Implementation Details

### Components
- `src/components/workspace/ManageWorkspaceMenu.js` - The menu component with conditional rendering
- `src/components/workspace/WorkspaceManager.js` - Integration component

### Services
- `src/services/terminalService.js` - Handles the terminal opening logic

### Utilities
- `src/utils/workspaceUtils.js` - Contains helper functions for workspace validation

### Tests
- `src/tests/workspace/ManageWorkspaceMenu.test.js` - Unit tests for the menu component

## Usage

The "Open in Terminal" option will automatically appear in the Manage Workspace menu when:
- The selected workspace is not the default workspace
- The workspace has a valid file system path
- The workspace is properly configured in Bruno's workspace management system

## Notes

This is a prototype implementation that follows Bruno's existing architecture patterns. In a production environment, additional platform-specific terminal integration would be required (e.g., using Electron's shell module or native OS commands).