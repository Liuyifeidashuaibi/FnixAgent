# BRU-3311 Fix: Preferences and Global Environments Tab Re-opening Issue

## Problem Description
When users attempt to open Preferences or Global Environments multiple times, Bruno creates duplicate tabs instead of focusing the existing one. This leads to cluttered UI and inconsistent state.

## Solution
Implemented a singleton tab management system that ensures only one instance of special tabs (Preferences, Global Environments, Collection Settings) exists at any time.

## Key Changes

### 1. Singleton Tab Manager Class
- Created `SingletonTabManager` class to track and manage singleton tabs
- Uses a Map to store tab type → tab ID mappings
- Provides methods to register, unregister, and ensure singleton tabs

### 2. Tab Type Constants
- Defined constants for singleton tab types: `PREFERENCES`, `GLOBAL_ENVIRONMENTS`, `COLLECTION_SETTINGS`

### 3. Integration Points
The fix should be integrated in:
- Tab creation logic (to check for existing singleton tabs before creating new ones)
- Menu item handlers (Preferences, Global Environments menu items)
- Keyboard shortcut handlers (Ctrl+, for preferences)
- Sidebar navigation handlers

## Usage Example

```typescript
import { singletonTabManager, SINGLETON_TAB_TYPES } from './fix-bru-3311';

// When opening Preferences
const preferencesTabId = singletonTabManager.ensureSingletonTab(
  SINGLETON_TAB_TYPES.PREFERENCES,
  () => createPreferencesTab()
);

// Focus the existing tab or create new one
focusTab(preferencesTabId);
```

## Testing
- Verify that opening Preferences multiple times focuses the existing tab
- Verify that opening Global Environments multiple times focuses the existing tab
- Verify that closing a singleton tab removes it from the manager
- Verify that reopening after closing creates a new tab

## Related Issues
- JIRA: [BRU-3311](https://usebruno.atlassian.net/browse/BRU-3311)
