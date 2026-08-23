// IPC Events Definitions

export const IPC_EVENTS = {
  SHOW_SAVE_TRANSIENT_MODAL: 'show-save-transient-modal',
  SAVE_TRANSIENT_REQUESTS: 'save-transient-requests',
  CANCEL_SAVE_TRANSIENT: 'cancel-save-transient',
  APP_QUIT_CONFIRMED: 'app-quit-confirmed',
  APP_QUIT_CANCELLED: 'app-quit-cancelled'
} as const;

export type IpcEvent = typeof IPC_EVENTS[keyof typeof IPC_EVENTS];
