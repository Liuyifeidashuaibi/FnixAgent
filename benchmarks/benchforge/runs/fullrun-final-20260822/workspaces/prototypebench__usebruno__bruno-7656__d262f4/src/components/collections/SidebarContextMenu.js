import React from 'react';
import { handlePasteItem, shouldShowPasteMenu, getPasteMenuLabel } from '../../utils/collections/pasteHandler';

const SidebarContextMenu = ({ 
  focusedItem, 
  onPaste, 
  onClose 
}) => {
  // Check if paste menu should be visible for this item
  const showPasteMenu = shouldShowPasteMenu(focusedItem);
  
  const handlePasteClick = () => {
    if (focusedItem && onPaste) {
      handlePasteItem(focusedItem, onPaste);
      onClose?.();
    }
  };

  return (
    <div className="sidebar-context-menu" onClick={(e) => e.stopPropagation()}>
      {/* Other menu items would go here */}
      
      {/* Paste menu item - visible on both folders and requests */}
      {showPasteMenu && (
        <div 
          className="context-menu-item paste-item"
          onClick={handlePasteClick}
          role="menuitem"
          tabIndex="0"
          onKeyPress={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handlePasteClick();
            }
          }}
        >
          <span className="menu-icon">📋</span>
          <span className="menu-label">{getPasteMenuLabel(focusedItem)}</span>
        </div>
      )}
      
      {/* Other context menu items */}
      <div className="context-menu-item">
        <span className="menu-icon">📁</span>
        <span className="menu-label">New Folder</span>
      </div>
      <div className="context-menu-item">
        <span className="menu-icon">📄</span>
        <span className="menu-label">New Request</span>
      </div>
      <div className="context-menu-item">
        <span className="menu-icon">✏️</span>
        <span className="menu-label">Rename</span>
      </div>
      <div className="context-menu-item">
        <span className="menu-icon">🗑️</span>
        <span className="menu-label">Delete</span>
      </div>
    </div>
  );
};

export default SidebarContextMenu;