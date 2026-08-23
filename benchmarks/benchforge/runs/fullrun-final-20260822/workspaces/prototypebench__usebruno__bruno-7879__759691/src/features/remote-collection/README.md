# Remote Collection Support

This feature adds support for remote backed collections in Bruno workspaces.

## Overview

Remote collection support allows users to:
- Connect local collections to remote Git repositories
- Sync collections with remote changes
- Disconnect from remote repositories
- View connection status and sync history

## Architecture

The remote collection system consists of:

### Core Services
- `RemoteCollectionService`: Main service handling remote operations
- `RemoteCollectionContext`: React context for global access
- `useRemoteCollection`: Custom hook for component usage

### UI Components
- `RemoteCollectionManager`: Primary UI component for managing remotes
- Status indicators and connection forms

### Utilities & Types
- Type definitions for remote configurations and statuses
- Utility functions for URL validation and status formatting

## Usage

### Connecting a Collection
1. Open the collection settings
2. Click "Connect Remote"
3. Enter the remote repository URL (e.g., `https://github.com/user/repo.git`)
4. Optionally specify a branch
5. Click "Connect"

### Syncing
- Click "Sync Now" to pull changes from the remote repository
- Automatic sync occurs periodically when connected

### Disconnecting
- Click "Disconnect" to remove the remote connection

## Supported Protocols
- HTTPS: `https://github.com/user/repo.git`
- Git: `git@github.com:user/repo.git`
- SSH: `ssh://user@host/path/to/repo.git`

## Security Considerations
- Authentication tokens are stored securely in the application's secure storage
- SSH keys are handled through the system's SSH agent
- All remote operations are validated before execution

## Future Enhancements
- Pull request integration
- Conflict resolution UI
- Branch switching support
- Multi-remote support
- Webhook integration for automatic sync
