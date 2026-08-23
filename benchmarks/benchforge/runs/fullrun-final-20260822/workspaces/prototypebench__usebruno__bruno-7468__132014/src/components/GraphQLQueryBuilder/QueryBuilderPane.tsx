import React, { useState, useCallback } from 'react';

interface QueryBuilderPaneProps {
  schema?: any;
  query?: string;
  onQueryChange?: (query: string) => void;
}

interface QueryNode {
  type: string;
  name: string;
  fields: QueryNode[];
  args?: { name: string; value: string }[];
  isSelected?: boolean;
}

const QueryBuilderPane: React.FC<QueryBuilderPaneProps> = ({
  schema,
  query,
  onQueryChange
}) => {
  const [nodes, setNodes] = useState<QueryNode[]>([
    {
      type: 'Query',
      name: 'users',
      fields: [
        { type: 'ID!', name: 'id', fields: [] },
        { type: 'String', name: 'name', fields: [] },
        { type: 'String', name: 'email', fields: [] }
      ],
      args: [
        { name: 'first', value: '10' },
        { name: 'after', value: '' }
      ]
    }
  ]);
  
  const [selectedNode, setSelectedNode] = useState<number | null>(0);

  const addField = useCallback((nodeIndex: number, fieldType: string, fieldName: string) => {
    setNodes(prev => {
      const newNodes = [...prev];
      if (newNodes[nodeIndex] && newNodes[nodeIndex].fields) {
        newNodes[nodeIndex].fields.push({
          type: fieldType,
          name: fieldName,
          fields: []
        });
      }
      return newNodes;
    });
  }, []);

  const removeField = useCallback((nodeIndex: number, fieldIndex: number) => {
    setNodes(prev => {
      const newNodes = [...prev];
      if (newNodes[nodeIndex] && newNodes[nodeIndex].fields) {
        newNodes[nodeIndex].fields.splice(fieldIndex, 1);
      }
      return newNodes;
    });
  }, []);

  const updateArgValue = useCallback((nodeIndex: number, argIndex: number, value: string) => {
    setNodes(prev => {
      const newNodes = [...prev];
      if (newNodes[nodeIndex] && newNodes[nodeIndex].args) {
        newNodes[nodeIndex].args[argIndex].value = value;
      }
      return newNodes;
    });
  }, []);

  const generateQuery = useCallback(() => {
    // Simple query generation for demo
    const queryParts = [];
    
    nodes.forEach((node, nodeIndex) => {
      let args = '';
      if (node.args && node.args.length > 0) {
        const argStrings = node.args
          .filter(arg => arg.value)
          .map(arg => `${arg.name}: "${arg.value}"`);
        if (argStrings.length > 0) {
          args = `(${argStrings.join(', ')})`;
        }
      }
      
      let fields = '';
      if (node.fields && node.fields.length > 0) {
        fields = ` {
          ${node.fields.map(f => f.name).join('\n          ')}
        }`;
      }
      
      queryParts.push(`${node.name}${args}${fields}`);
    });
    
    return `query {
      ${queryParts.join('\n      ')}
    }`;
  }, [nodes]);

  const handlePrettify = () => {
    const generatedQuery = generateQuery();
    if (onQueryChange) {
      onQueryChange(generatedQuery);
    }
  };

  return (
    <div className="query-builder-pane">
      <div className="pane-header">
        <h4>Query Builder</h4>
        <button onClick={handlePrettify} className="prettify-button">
          Prettify
        </button>
      </div>
      
      <div className="query-nodes">
        {nodes.map((node, nodeIndex) => (
          <div key={nodeIndex} className="query-node">
            <div className="node-header">
              <span className="node-type">{node.type}</span>
              <span className="node-name">{node.name}</span>
              <button 
                className="add-field-button"
                onClick={() => addField(nodeIndex, 'String', 'newField')}
              >
                + Add Field
              </button>
            </div>
            
            {node.args && node.args.length > 0 && (
              <div className="node-args">
                <h5>Arguments:</h5>
                {node.args.map((arg, argIndex) => (
                  <div key={argIndex} className="arg-item">
                    <span className="arg-name">{arg.name}:</span>
                    <input
                      type="text"
                      value={arg.value}
                      onChange={(e) => updateArgValue(nodeIndex, argIndex, e.target.value)}
                      placeholder={`Enter ${arg.name}`}
                    />
                  </div>
                ))}
              </div>
            )}
            
            {node.fields && node.fields.length > 0 && (
              <div className="node-fields">
                <h5>Fields:</h5>
                {node.fields.map((field, fieldIndex) => (
                  <div key={fieldIndex} className="field-item">
                    <span className="field-name">{field.name}</span>
                    <span className="field-type">{field.type}</span>
                    <button 
                      className="remove-field-button"
                      onClick={() => removeField(nodeIndex, fieldIndex)}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default QueryBuilderPane;