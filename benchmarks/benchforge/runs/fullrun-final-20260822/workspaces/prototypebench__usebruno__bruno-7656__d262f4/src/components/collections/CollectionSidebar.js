import React, { useState, useEffect } from 'react';

const CollectionSidebar = ({ onPasteItem }) => {
  const [focusedItem, setFocusedItem] = useState(null);
  
  // Handle paste operation
  const handlePasteItem = async () => {
    try {
      // Read clipboard content
      const clipboardText = await navigator.clipboard.readText();
      
      // Try to parse as JSON to determine item type
      let clipboardData;
      try {
        clipboardData = JSON.parse(clipboardText);
      } catch (e) {
        // If not valid JSON, treat as plain text/request
        clipboardData = { type: 'request', content: clipboardText };
      }
      
      // Determine paste behavior based on focused item and clipboard content
      if (focusedItem && focusedItem.type === 'folder' && clipboardData.type === 'request') {
        // Paste inside the folder
        onPasteItem(clipboardData, { target: 'inside', folderId: focusedItem.id });
      } else {
        // Paste as sibling
        onPasteItem(clipboardData, { target: 'sibling', parentId: focusedItem?.parentId || null });
      }
    } catch (error) {
      console.error('Failed to read clipboard:', error);
      // Fallback: try to get clipboard data from system clipboard
      if (navigator.clipboard && navigator.clipboard.read) {
        try {
          const items = await navigator.clipboard.read();
          for (let item of items) {
            if (item.types.includes('text/plain')) {
              const blob = await item.getType('text/plain');
              const text = await blob.text();
              // Process the text content
              onPasteItem({ type: 'request', content: text }, { target: 'sibling' });
              return;
            }
          }
        } catch (readError) {
          console.error('Failed to read clipboard items:', readError);
        }
      }
    }
  };

  // Render paste menu item that appears on both folders and requests
  const renderPasteMenuItem = () => (
    <div 
      className="paste-menu-item" 
      onClick={handlePasteItem}
      role="menuitem"
      tabIndex="0"
      onKeyPress={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handlePasteItem();
        }
      }}
    >
      Paste
    </div>
  );

  return (
    <div className="collection-sidebar">
      <div className="sidebar-content">
        {/* Collection items would be rendered here */}
        <div className="sidebar-items">
          {/* Items would be mapped here */}
        </div>
      </div>
      <div className="context-menu">
        {/* Paste menu item should appear on both folders and requests */}
        {renderPasteMenuItem()}
      </div>
    </div>
  );
};

export default CollectionSidebar;