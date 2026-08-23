import { app, dialog, BrowserWindow } from 'electron';
import { join } from 'path';

// Function to show the Save Transient Modal
const showSaveTransientModal = (win: BrowserWindow) => {
  // In a real implementation, this would open the Save Transient Modal
  // For now, we'll just show a dialog as a placeholder
  dialog.showMessageBox(win, {
    type: 'question',
    title: 'Save Transient Requests?',
    message: 'You have unsaved transient requests. Would you like to save them before quitting?',
    buttons: ['Save', 'Don\'t Save', 'Cancel'],
    defaultId: 0,
    cancelId: 2
  }).then(result => {
    if (result.response === 0) {
      // User chose to save - redirect to save transient modal
      if (win && !win.isDestroyed()) {
        win.webContents.send('show-save-transient-modal');
      }
    } else if (result.response === 1) {
      // User chose not to save - proceed with quit
      app.quit();
    }
    // If user chose Cancel, do nothing - app will not quit
  });
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
};
