import React from 'react';
import CollectionErrorBoundary from './CollectionErrorBoundary';

// Example collection component that uses the error boundary
const CollectionWithErrorBoundary = ({ collectionId, children, onRetry, ...props }) => {
  return (
    <CollectionErrorBoundary 
      onRetry={onRetry}
      onError={(error, errorInfo) => {
        console.warn(`Error in collection ${collectionId}:`, error, errorInfo);
      }}
    >
      <div className="collection-content" {...props}>
        {children}
      </div>
    </CollectionErrorBoundary>
  );
};

export default CollectionWithErrorBoundary;