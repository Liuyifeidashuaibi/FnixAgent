import { app, dialog, BrowserWindow, ipcMain } from 'electron';
import { IPC_EVENTS } from './ipc-events';

// Function to show the Save Transient Modal
const showSaveTransientModal = (win: BrowserWindow) => {
  // Send event to renderer to show the modal
  if (win && !win.isDestroyed()) {
    win.webContents.send(IPC_EVENTS.SHOW_SAVE_TRANSIENT_MODAL);
  }
};

// Handle app quit events
export const setupQuitHandler = (mainWindow: BrowserWindow) => {
  // Listen for before-quit-forced event (e.g., Ctrl+C, kill command)
  app.on('before-quit-forced', (event) => {
    event.preventDefault();
    showSaveTransientModal(mainWindow);
  });

  // Listen for will-quit event (normal quit)
  app.on('will-quit', (event) => {
    event.preventDefault();
    showSaveTransientModal(mainWindow);
  });

  // Handle save confirmation from renderer
  ipcMain.on(IPC_EVENTS.SAVE_TRANSIENT_REQUESTS, (event) => {
    // Perform save logic here
    console.log('Saving transient requests...');
    
    // After saving, quit the app
    app.quit();
  });

  // Handle cancel from renderer
  ipcMain.on(IPC_EVENTS.CANCEL_SAVE_TRANSIENT, (event) => {
    console.log('Save cancelled, app will remain open');
    // App remains open
  });
};
