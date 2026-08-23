import React from 'react';

interface GraphQLDocumentationExplorerProps {
  isOpen: boolean;
  onClose: () => void;
}

const GraphQLDocumentationExplorer: React.FC<GraphQLDocumentationExplorerProps> = ({
  isOpen,
  onClose
}) => {
  if (!isOpen) return null;

  return (
    <div className="graphql-doc-explorer">
      <div className="doc-header">
        <h3>GraphQL Documentation</h3>
        <button 
          className="close-button"
          onClick={onClose}
          aria-label="Close documentation"
        >
          ×
        </button>
      </div>
      <div className="doc-content">
        {/* Documentation content would go here */}
        <p>GraphQL schema documentation</p>
      </div>
    </div>
  );
};

export default GraphQLDocumentationExplorer;
