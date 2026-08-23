import React, { useEffect } from 'react';
import { useScrollPosition } from './ScrollPositionManager';

/**
 * AssertionsPane - Request assertions editor with scroll position persistence
 */
const AssertionsPane = ({ assertions, onAssertionsChange }) => {
  const { ref, restoreScroll, saveScroll } = useScrollPosition('assertions');
  
  // Restore scroll position when assertions change (to handle tab switching)
  useEffect(() => {
    // Small timeout to ensure DOM is ready
    const timer = setTimeout(() => {
      restoreScroll();
    }, 10);
    return () => clearTimeout(timer);
  }, [assertions.length]);

  return (
    <div 
      ref={ref}
      className="bruno-assertions-pane"
      style={{
        height: '300px',
        overflowY: 'auto',
        border: '1px solid #ddd',
        borderRadius: '4px'
      }}
    >
      <div className="assertions-list">
        {assertions.map((assertion, index) => (
          <div key={index} className="assertion-item" style={{ padding: '8px 12px' }}>
            <input 
              type="text" 
              value={assertion.expression} 
              onChange={(e) => {
                const newAssertions = [...assertions];
                newAssertions[index].expression = e.target.value;
                onAssertionsChange(newAssertions);
              }}
              placeholder="Assertion Expression"
              style={{ width: '100%', marginBottom: '4px' }}
            />
            <select 
              value={assertion.type} 
              onChange={(e) => {
                const newAssertions = [...assertions];
                newAssertions[index].type = e.target.value;
                onAssertionsChange(newAssertions);
              }}
              style={{ width: '100%' }}
            >
              <option value="response-status">Response Status</option>
              <option value="response-body">Response Body</option>
              <option value="response-header">Response Header</option>
            </select>
          </div>
        ))}
      </div>
      {assertions.length === 0 && (
        <div className="no-assertions" style={{ padding: '16px', color: '#666' }}>
          No assertions configured
        </div>
      )}
    </div>
  );
};

export default AssertionsPane;
