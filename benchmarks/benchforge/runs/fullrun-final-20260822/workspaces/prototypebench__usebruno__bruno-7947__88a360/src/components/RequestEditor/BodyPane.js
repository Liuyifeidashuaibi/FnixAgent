import React, { useEffect, useRef } from 'react';
import { useScrollPosition } from './ScrollPositionManager';

/**
 * BodyPane - Request body editor with scroll position persistence
 */
const BodyPane = ({ body, onBodyChange }) => {
  const { ref, restoreScroll, saveScroll } = useScrollPosition('body');
  
  // Restore scroll position when body changes (to handle tab switching)
  useEffect(() => {
    // Small timeout to ensure DOM is ready
    const timer = setTimeout(() => {
      restoreScroll();
    }, 10);
    return () => clearTimeout(timer);
  }, [body]);

  return (
    <div 
      ref={ref}
      className="bruno-body-pane"
      style={{
        height: '300px',
        overflowY: 'auto',
        border: '1px solid #ddd',
        borderRadius: '4px'
      }}
    >
      <textarea 
        value={body} 
        onChange={(e) => onBodyChange(e.target.value)}
        placeholder="Request body"
        style={{
          width: '100%', 
          height: '100%', 
          border: 'none', 
          resize: 'none',
          padding: '12px',
          fontFamily: 'monospace',
          fontSize: '14px'
        }}
      />
    </div>
  );
};

export default BodyPane;
