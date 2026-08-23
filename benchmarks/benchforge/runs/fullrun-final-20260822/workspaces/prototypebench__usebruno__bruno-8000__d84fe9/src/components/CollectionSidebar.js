import React from 'react';
import { isCollectionEmpty } from '../utils/collection-empty-check';

/**
 * Collection Sidebar Component
 * Displays collection items and the + Add request CTA when appropriate
 */
const CollectionSidebar = ({ collection, onAddRequest }) => {
  // Check if collection is empty (only showing CTA when truly empty)
  const isEmpty = isCollectionEmpty(collection.items);

  return (
    <div className="collection-sidebar">
      <div className="collection-header">
        <h3>{collection.name}</h3>
      </div>
      
      <div className="collection-items">
        {collection.items.map((item, index) => (
          <div key={index} className="collection-item">
            {item.type === 'folder' ? (
              <span>📁 {item.name}</span>
            ) : item.name && item.name.endsWith('.bru') && item.name !== 'bruno.json' ? (
              <span>📄 {item.name}</span>
            ) : (
              <span className="config-file">⚙️ {item.name}</span>
            )}
          </div>
        ))}
      </div>
      
      {/* Only show + Add request CTA when collection is truly empty */}
      {isEmpty && (
        <div className="empty-state-cta">
          <button 
            className="add-request-button" 
            onClick={onAddRequest}
          >
            + Add request
          </button>
        </div>
      )}
    </div>
  );
};

export default CollectionSidebar;