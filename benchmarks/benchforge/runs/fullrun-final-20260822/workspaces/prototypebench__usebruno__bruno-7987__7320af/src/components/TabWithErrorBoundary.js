import React from 'react';
import TabErrorBoundary from './TabErrorBoundary';

// Example tab component that uses the error boundary
const TabWithErrorBoundary = ({ tabId, children, onClose, ...props }) => {
  return (
    <TabErrorBoundary 
      onClose={onClose}
      onError={(error, errorInfo) => {
        console.warn(`Error in tab ${tabId}:`, error, errorInfo);
      }}
    >
      <div className="tab-content" {...props}>
        {children}
      </div>
    </TabErrorBoundary>
  );
};

export default TabWithErrorBoundary;