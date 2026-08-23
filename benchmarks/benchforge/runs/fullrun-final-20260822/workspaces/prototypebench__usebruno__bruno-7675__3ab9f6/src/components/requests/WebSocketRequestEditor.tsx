import React, { useState } from 'react';

interface WebSocketRequestEditorProps {
  onSend: () => void;
  onCancel: () => void;
  isSending: boolean;
}

const WebSocketRequestEditor: React.FC<WebSocketRequestEditorProps> = ({
  onSend,
  onCancel,
  isSending
}) => {
  return (
    <div className="websocket-request-editor">
      {/* URL bar with Send/Cancel buttons */}
      <div className="url-bar">
        <input 
          type="text" 
          className="url-input" 
          placeholder="Enter WebSocket URL"
        />
        <div className="url-actions">
          {isSending ? (
            <button 
              className="cancel-button"
              onClick={onCancel}
              aria-label="Cancel WebSocket connection"
            >
              Cancel
            </button>
          ) : (
            <button 
              className="send-button"
              onClick={onSend}
              aria-label="Connect to WebSocket"
            >
              Send
            </button>
          )}
        </div>
      </div>
      
      {/* WebSocket message editor */}
      <div className="message-editor">
        {/* Message content */}
      </div>
    </div>
  );
};

export default WebSocketRequestEditor;