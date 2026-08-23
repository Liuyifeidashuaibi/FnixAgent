import React, { useState } from 'react';

interface GraphQLRequestEditorProps {
  onSend: () => void;
  onCancel: () => void;
  isSending: boolean;
}

const GraphQLRequestEditor: React.FC<GraphQLRequestEditorProps> = ({
  onSend,
  onCancel,
  isSending
}) => {
  return (
    <div className="graphql-request-editor">
      {/* URL bar with Send/Cancel buttons */}
      <div className="url-bar">
        <input 
          type="text" 
          className="url-input" 
          placeholder="Enter GraphQL endpoint"
        />
        <div className="url-actions">
          {isSending ? (
            <button 
              className="cancel-button"
              onClick={onCancel}
              aria-label="Cancel GraphQL request"
            >
              Cancel
            </button>
          ) : (
            <button 
              className="send-button"
              onClick={onSend}
              aria-label="Send GraphQL request"
            >
              Send
            </button>
          )}
        </div>
      </div>
      
      {/* GraphQL query editor */}
      <div className="query-editor">
        {/* Query content */}
      </div>
    </div>
  );
};

export default GraphQLRequestEditor;