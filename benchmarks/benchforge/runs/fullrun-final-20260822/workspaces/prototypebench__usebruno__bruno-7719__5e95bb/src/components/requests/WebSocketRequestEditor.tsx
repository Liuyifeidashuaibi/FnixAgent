import React, { useState, useEffect } from 'react';
import { WebSocketMessage, WebSocketRequest, createWebSocketMessage, createWebSocketRequest } from '@/models/websocket-message';

interface WebSocketRequestEditorProps {
  request: WebSocketRequest;
  onChange: (request: WebSocketRequest) => void;
}

const WebSocketRequestEditor: React.FC<WebSocketRequestEditorProps> = ({
  request,
  onChange
}) => {
  const [expandedMessages, setExpandedMessages] = useState<Record<string, boolean>>({});
  const [editingNames, setEditingNames] = useState<Record<string, boolean>>({});
  
  // Initialize expanded state for all messages
  useEffect(() => {
    const initialExpanded: Record<string, boolean> = {};
    request.messages.forEach(msg => {
      initialExpanded[msg.id] = true; // Auto-expand new messages
    });
    setExpandedMessages(initialExpanded);
    
    // Set first message as editing by default
    if (request.messages.length > 0) {
      setEditingNames({ [request.messages[0].id]: true });
    }
  }, [request.messages.length]);

  const toggleMessageExpand = (messageId: string) => {
    setExpandedMessages(prev => ({
      ...prev,
      [messageId]: !prev[messageId]
    }));
  };

  const addMessage = () => {
    const newMessage = createWebSocketMessage();
    const updatedRequest = {
      ...request,
      messages: [...request.messages, newMessage]
    };
    
    // Expand the new message and set it as editing
    setExpandedMessages(prev => ({
      ...prev,
      [newMessage.id]: true
    }));
    
    setEditingNames(prev => ({
      ...prev,
      [newMessage.id]: true
    }));
    
    onChange(updatedRequest);
  };

  const deleteMessage = (messageId: string) => {
    const updatedMessages = request.messages.filter(msg => msg.id !== messageId);
    const updatedRequest = {
      ...request,
      messages: updatedMessages
    };
    
    // Remove from expanded and editing states
    setExpandedMessages(prev => {
      const newExpanded = { ...prev };
      delete newExpanded[messageId];
      return newExpanded;
    });
    
    setEditingNames(prev => {
      const newEditing = { ...prev };
      delete newEditing[messageId];
      return newEditing;
    });
    
    onChange(updatedRequest);
  };

  const updateMessage = (messageId: string, updates: Partial<WebSocketMessage>) => {
    const updatedMessages = request.messages.map(msg => 
      msg.id === messageId ? { ...msg, ...updates } : msg
    );
    
    const updatedRequest = {
      ...request,
      messages: updatedMessages
    };
    
    onChange(updatedRequest);
  };

  const renameMessage = (messageId: string, newName: string) => {
    updateMessage(messageId, { name: newName });
    setEditingNames(prev => ({
      ...prev,
      [messageId]: false
    }));
  };

  const sendMessage = (messageId: string) => {
    // In a real implementation, this would send the message to the WebSocket connection
    console.log(`Sending message ${messageId}`);
  };

  return (
    <div className="websocket-request-editor">
      <div className="websocket-header">
        <h3>WebSocket Messages</h3>
        <button 
          onClick={addMessage}
          className="btn btn-sm btn-primary"
        >
          + Add Message
        </button>
      </div>
      
      <div className="websocket-messages">
        {request.messages.length === 0 ? (
          <div className="empty-state">
            <p>No messages yet. Click "Add Message" to get started.</p>
          </div>
        ) : (
          request.messages.map((message) => (
            <div 
              key={message.id} 
              className={`websocket-message-accordion ${expandedMessages[message.id] ? 'expanded' : ''}`}
            >
              <div 
                className="message-header"
                onClick={() => toggleMessageExpand(message.id)}
              >
                <div className="message-name">
                  {editingNames[message.id] ? (
                    <input
                      type="text"
                      value={message.name}
                      onChange={(e) => renameMessage(message.id, e.target.value)}
                      onBlur={() => setEditingNames(prev => ({...prev, [message.id]: false}))}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          setEditingNames(prev => ({...prev, [message.id]: false}));
                        }
                      }}
                      autoFocus
                      className="message-name-input"
                    />
                  ) : (
                    <span 
                      className="message-name-display"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingNames(prev => ({...prev, [message.id]: true}));
                      }}
                    >
                      {message.name}
                    </span>
                  )}
                </div>
                
                <div className="message-actions">
                  <select
                    value={message.type}
                    onChange={(e) => updateMessage(message.id, { type: e.target.value as 'text' | 'binary' })}
                    className="message-type-select"
                  >
                    <option value="text">Text</option>
                    <option value="binary">Binary</option>
                  </select>
                  
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      sendMessage(message.id);
                    }}
                    className="btn btn-xs btn-success"
                    title="Send message"
                  >
                    Send
                  </button>
                  
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteMessage(message.id);
                    }}
                    className="btn btn-xs btn-danger"
                    title="Delete message"
                  >
                    ×
                  </button>
                </div>
              </div>
              
              {expandedMessages[message.id] && (
                <div className="message-content">
                  {message.type === 'text' ? (
                    <textarea
                      value={message.content}
                      onChange={(e) => updateMessage(message.id, { content: e.target.value })}
                      placeholder="Enter message content..."
                      className="message-content-textarea"
                    />
                  ) : (
                    <div className="message-content-binary">
                      <p>Binary content (base64 encoded)</p>
                      <input
                        type="text"
                        value={message.content}
                        onChange={(e) => updateMessage(message.id, { content: e.target.value })}
                        placeholder="Enter base64 encoded content..."
                        className="message-content-binary-input"
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default WebSocketRequestEditor;