import React, { useState, useEffect } from 'react';

interface HttpRequestEditorProps {
  onSend: () => void;
  onCancel: () => void;
  isSending: boolean;
}

const HttpRequestEditor: React.FC<HttpRequestEditorProps> = ({
  onSend,
  onCancel,
  isSending
}) => {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div className="request-editor">
      {/* URL bar with Send/Cancel buttons */}
      <div className="url-bar">
        <input 
          type="text" 
          className="url-input" 
          placeholder="Enter URL"
        />
        <div className="url-actions">
          {isSending ? (
            <button 
              className="cancel-button"
              onClick={onCancel}
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
              aria-label="Cancel request"
            >
              Cancel
            </button>
          ) : (
            <button 
              className="send-button"
              onClick={onSend}
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
              aria-label="Send request"
            >
              Send
            </button>
          )}
        </div>
      </div>
      
      {/* Other request components */}
      <div className="request-body">
        {/* Request body content */}
      </div>
    </div>
  );
};

export default HttpRequestEditor;