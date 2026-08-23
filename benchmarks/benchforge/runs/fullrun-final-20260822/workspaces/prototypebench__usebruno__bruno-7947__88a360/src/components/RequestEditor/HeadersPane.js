import React, { useEffect, useRef } from 'react';
import { useScrollPosition } from './ScrollPositionManager';

/**
 * HeadersPane - Request headers editor with scroll position persistence
 */
const HeadersPane = ({ headers, onHeadersChange }) => {
  const { ref, restoreScroll, saveScroll } = useScrollPosition('headers');
  
  // Restore scroll position when headers change (to handle tab switching)
  useEffect(() => {
    // Small timeout to ensure DOM is ready
    const timer = setTimeout(() => {
      restoreScroll();
    }, 10);
    return () => clearTimeout(timer);
  }, [headers.length]);

  return (
    <div 
      ref={ref}
      className="bruno-headers-pane"
      style={{
        height: '300px',
        overflowY: 'auto',
        border: '1px solid #ddd',
        borderRadius: '4px'
      }}
    >
      <div className="headers-list">
        {headers.map((header, index) => (
          <div key={index} className="header-item" style={{ padding: '8px 12px' }}>
            <input 
              type="text" 
              value={header.key} 
              onChange={(e) => {
                const newHeaders = [...headers];
                newHeaders[index].key = e.target.value;
                onHeadersChange(newHeaders);
              }}
              placeholder="Header Key"
              style={{ width: '40%', marginRight: '8px' }}
            />
            <input 
              type="text" 
              value={header.value} 
              onChange={(e) => {
                const newHeaders = [...headers];
                newHeaders[index].value = e.target.value;
                onHeadersChange(newHeaders);
              }}
              placeholder="Header Value"
              style={{ width: '50%' }}
            />
          </div>
        ))}
      </div>
      {headers.length === 0 && (
        <div className="no-headers" style={{ padding: '16px', color: '#666' }}>
          No headers configured
        </div>
      )}
    </div>
  );
};

export default HeadersPane;
