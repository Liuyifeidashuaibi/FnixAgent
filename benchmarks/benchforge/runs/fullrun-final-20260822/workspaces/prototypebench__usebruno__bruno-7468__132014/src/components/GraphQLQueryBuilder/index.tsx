import React, { useState, useEffect, useCallback } from 'react';
import './index.css';

interface GraphQLQueryBuilderProps {
  schema?: any;
  query?: string;
  variables?: Record<string, any>;
  onQueryChange?: (query: string) => void;
  onVariablesChange?: (variables: Record<string, any>) => void;
}

const GraphQLQueryBuilder: React.FC<GraphQLQueryBuilderProps> = ({
  schema,
  query,
  variables,
  onQueryChange,
  onVariablesChange
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [builderWidth, setBuilderWidth] = useState(400);
  const [variablesHeight, setVariablesHeight] = useState(200);
  const [isDraggingBuilder, setIsDraggingBuilder] = useState(false);
  const [isDraggingVariables, setIsDraggingVariables] = useState(false);
  const [dragStartX, setDragStartX] = useState(0);
  const [dragStartY, setDragStartY] = useState(0);
  const [dragOffsetX, setDragOffsetX] = useState(0);
  const [dragOffsetY, setDragOffsetY] = useState(0);

  // Handle builder resize
  const handleBuilderResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDraggingBuilder(true);
    setDragStartX(e.clientX);
  };

  const handleBuilderResize = useCallback((e: MouseEvent) => {
    if (isDraggingBuilder) {
      const newWidth = Math.max(300, Math.min(800, builderWidth + (e.clientX - dragStartX)));
      setBuilderWidth(newWidth);
      setDragStartX(e.clientX);
    }
  }, [isDraggingBuilder, builderWidth, dragStartX]);

  const handleBuilderResizeEnd = useCallback(() => {
    setIsDraggingBuilder(false);
  }, []);

  // Handle variables pane resize
  const handleVariablesResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDraggingVariables(true);
    setDragStartY(e.clientY);
  };

  const handleVariablesResize = useCallback((e: MouseEvent) => {
    if (isDraggingVariables) {
      const newHeight = Math.max(150, Math.min(400, variablesHeight + (e.clientY - dragStartY)));
      setVariablesHeight(newHeight);
      setDragStartY(e.clientY);
    }
  }, [isDraggingVariables, variablesHeight, dragStartY]);

  const handleVariablesResizeEnd = useCallback(() => {
    setIsDraggingVariables(false);
  }, []);

  // Add event listeners for dragging
  useEffect(() => {
    if (isDraggingBuilder) {
      document.addEventListener('mousemove', handleBuilderResize);
      document.addEventListener('mouseup', handleBuilderResizeEnd);
      return () => {
        document.removeEventListener('mousemove', handleBuilderResize);
        document.removeEventListener('mouseup', handleBuilderResizeEnd);
      };
    }
  }, [isDraggingBuilder, handleBuilderResize, handleBuilderResizeEnd]);

  useEffect(() => {
    if (isDraggingVariables) {
      document.addEventListener('mousemove', handleVariablesResize);
      document.addEventListener('mouseup', handleVariablesResizeEnd);
      return () => {
        document.removeEventListener('mousemove', handleVariablesResize);
        document.removeEventListener('mouseup', handleVariablesResizeEnd);
      };
    }
  }, [isDraggingVariables, handleVariablesResize, handleVariablesResizeEnd]);

  // Schema loading state
  const [schemaStatus, setSchemaStatus] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle');
  
  const loadSchema = async (source: 'introspection' | 'file') => {
    setSchemaStatus('loading');
    try {
      // Simulate API call or file loading
      await new Promise(resolve => setTimeout(resolve, 1000));
      setSchemaStatus('loaded');
    } catch (error) {
      setSchemaStatus('error');
    }
  };

  // Render the query builder UI
  return (
    <div className="graphql-query-builder">
      {/* Header with controls */}
      <div className="builder-header">
        <h3>GraphQL Query Builder</h3>
        <div className="builder-controls">
          <button 
            onClick={() => setIsExpanded(!isExpanded)}
            className="toggle-button"
          >
            {isExpanded ? '▼ Collapse' : '► Expand'}
          </button>
          <div className="schema-controls">
            <button 
              onClick={() => loadSchema('introspection')}
              disabled={schemaStatus === 'loading'}
              className="schema-button"
            >
              {schemaStatus === 'loading' ? 'Loading...' : 'Load Schema'}
            </button>
            <button className="schema-button">Docs</button>
            <button className="schema-button">Refresh</button>
          </div>
          <button className="prettify-button">Prettify</button>
        </div>
      </div>

      {/* Main builder area */}
      {isExpanded && (
        <div className="builder-content">
          <div 
            className="builder-pane"
            style={{ width: `${builderWidth}px` }}
          >
            <div className="builder-pane-header">
              <h4>Query Builder</h4>
              <div 
                className="resize-handle"
                onMouseDown={handleBuilderResizeStart}
              />
            </div>
            <div className="builder-pane-content">
              {/* Recursive query builder tree would go here */}
              <div className="query-tree">
                <div className="query-node">
                  <span className="node-type">Query</span>
                  <span className="node-name">users</span>
                  <div className="node-fields">
                    <div className="field-item">
                      <span className="field-name">id</span>
                      <span className="field-type">ID!</span>
                    </div>
                    <div className="field-item">
                      <span className="field-name">name</span>
                      <span className="field-type">String</span>
                    </div>
                    <div className="field-item">
                      <span className="field-name">email</span>
                      <span className="field-type">String</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="builder-divider" />

          <div 
            className="variables-pane"
            style={{ height: `${variablesHeight}px` }}
          >
            <div className="variables-pane-header">
              <h4>Variables</h4>
              <div 
                className="resize-handle vertical"
                onMouseDown={handleVariablesResizeStart}
              />
            </div>
            <div className="variables-pane-content">
              <div className="variables-form">
                <div className="variable-row">
                  <label htmlFor="userId">userId:</label>
                  <input 
                    id="userId" 
                    type="text" 
                    value={variables?.userId || ''}
                    onChange={(e) => {
                      if (onVariablesChange) {
                        onVariablesChange({ ...variables, userId: e.target.value });
                      }
                    }}
                    placeholder="Enter user ID"
                  />
                </div>
                <div className="variable-row">
                  <label htmlFor="limit">limit:</label>
                  <input 
                    id="limit" 
                    type="number" 
                    value={variables?.limit || ''}
                    onChange={(e) => {
                      if (onVariablesChange) {
                        onVariablesChange({ ...variables, limit: e.target.value });
                      }
                    }}
                    placeholder="Limit"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GraphQLQueryBuilder;