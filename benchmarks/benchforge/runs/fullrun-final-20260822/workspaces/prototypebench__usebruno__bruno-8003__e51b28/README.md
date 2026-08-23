# Bruno Save Transient Modal on Quit

## Description

This implementation redirects to the Save Transient Modal when the app quit is triggered, as required by JIRA ticket BRU-3391.

## Files Created

- `src/main/quit-handler.ts`: Main process handler for quit events
- `src/main/quit-handler-enhanced.ts`: Enhanced version with IPC event handling
- `src/main/ipc-events.ts`: IPC event definitions for type safety
- `src/renderer/components/SaveTransientModal.tsx`: React component for the save modal
- `src/renderer/components/SaveTransientModal.css`: CSS styling for the modal
- `src/renderer/quit-handler.ts`: Renderer process handler for IPC events

## How It Works

1. When the app receives a quit signal (via `before-quit-forced` or `will-quit` events), the main process prevents default behavior
2. The main process sends an IPC event to the renderer process to show the Save Transient Modal
3. The renderer process displays the modal to the user
4. User can choose to save transient requests, cancel, or don't save
5. Based on user choice, appropriate IPC events are sent back to the main process to either save and quit, or continue running

## Usage

The quit handler should be initialized in the main Electron process with the main window reference:

```ts
import { setupQuitHandler } from './main/quit-handler-enhanced';
// ...
setupQuitHandler(mainWindow);
```

The Save Transient Modal component should be integrated into the main renderer application and listen for the appropriate IPC events.
