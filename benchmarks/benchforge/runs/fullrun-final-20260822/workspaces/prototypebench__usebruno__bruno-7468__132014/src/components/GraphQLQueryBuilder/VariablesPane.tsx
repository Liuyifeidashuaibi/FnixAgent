import React, { useState, useEffect } from 'react';

interface VariablesPaneProps {
  variables?: Record<string, any>;
  onVariablesChange?: (variables: Record<string, any>) => void;
}

const VariablesPane: React.FC<VariablesPaneProps> = ({
  variables,
  onVariablesChange
}) => {
  const [localVariables, setLocalVariables] = useState<Record<string, any>>(variables || {});
  
  // Sync with external changes
  useEffect(() => {
    if (variables) {
      setLocalVariables(variables);
    }
  }, [variables]);

  const handleVariableChange = (key: string, value: string | number | boolean | null) => {
    const newVariables = { ...localVariables, [key]: value };
    setLocalVariables(newVariables);
    
    if (onVariablesChange) {
      onVariablesChange(newVariables);
    }
  };

  const addVariable = () => {
    const newKey = `newVar${Object.keys(localVariables).length + 1}`;
    const newVariables = { ...localVariables, [newKey]: '' };
    setLocalVariables(newVariables);
    
    if (onVariablesChange) {
      onVariablesChange(newVariables);
    }
  };

  const removeVariable = (key: string) => {
    const newVariables = { ...localVariables };
    delete newVariables[key];
    setLocalVariables(newVariables);
    
    if (onVariablesChange) {
      onVariablesChange(newVariables);
    }
  };

  return (
    <div className="variables-pane">
      <div className="pane-header">
        <h4>Variables</h4>
        <button onClick={addVariable} className="add-variable-button">
          + Add Variable
        </button>
      </div>
      
      <div className="variables-list">
        {Object.entries(localVariables).length === 0 ? (
          <div className="no-variables">
            No variables defined. Click "Add Variable" to get started.
          </div>
        ) : (
          Object.entries(localVariables).map(([key, value]) => (
            <div key={key} className="variable-item">
              <div className="variable-key">
                <label htmlFor={`var-${key}`}>{key}:</label>
              </div>
              <div className="variable-value">
                <input
                  id={`var-${key}`}
                  type="text"
                  value={value !== null && value !== undefined ? String(value) : ''}
                  onChange={(e) => handleVariableChange(key, e.target.value)}
                  placeholder={`Enter ${key}`}
                />
              </div>
              <button 
                className="remove-variable-button"
                onClick={() => removeVariable(key)}
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default VariablesPane;