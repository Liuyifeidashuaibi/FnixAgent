import React, { useState, useEffect } from 'react';

const WorkspaceCreation = ({ onCreate, onCancel }) => {
  const [workspaceName, setWorkspaceName] = useState('');
  const [isAdvancedMode, setIsAdvancedMode] = useState(false);
  const [customPath, setCustomPath] = useState('');
  const [isValid, setIsValid] = useState(false);
  const [error, setError] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // Validate workspace name
  useEffect(() => {
    if (!workspaceName.trim()) {
      setIsValid(false);
      setError('Workspace name is required');
      return;
    }

    // Check for invalid characters
    if (/[^a-zA-Z0-9\-_\s]/.test(workspaceName)) {
      setIsValid(false);
      setError('Workspace name can only contain letters, numbers, spaces, hyphens, and underscores');
      return;
    }

    // Check for leading/trailing spaces
    if (workspaceName !== workspaceName.trim()) {
      setIsValid(false);
      setError('Workspace name cannot have leading or trailing spaces');
      return;
    }

    // Check for duplicate names (simulated)
    if (workspaceName.toLowerCase() === 'default') {
      setIsValid(false);
      setError('"Default" is a reserved workspace name');
      return;
    }

    setIsValid(true);
    setError('');
  }, [workspaceName]);

  const handleCreate = async () => {
    if (!isValid || isCreating) return;
    
    setIsCreating(true);
    try {
      // Simulate filesystem operation
      await new Promise(resolve => setTimeout(resolve, 500));
      
      const workspaceData = {
        name: workspaceName.trim(),
        path: isAdvancedMode ? customPath : null,
        createdAt: new Date().toISOString()
      };
      
      onCreate(workspaceData);
    } catch (err) {
      console.error('Failed to create workspace:', err);
      setError('Failed to create workspace. Please try again.');
    } finally {
      setIsCreating(false);
    }
  };

  const toggleAdvancedMode = () => {
    setIsAdvancedMode(!isAdvancedMode);
  };

  return (
    <div className="workspace-creation-container">
      <div className="workspace-creation-header">
        <h2>Create New Workspace</h2>
        <button 
          className="settings-cog"
          onClick={toggleAdvancedMode}
          aria-label={isAdvancedMode ? 'Hide advanced options' : 'Show advanced options'}
        >
          ⚙️
        </button>
      </div>
      
      <div className="workspace-creation-form">
        <div className="form-group">
          <label htmlFor="workspace-name">Workspace Name</label>
          <input
            id="workspace-name"
            type="text"
            value={workspaceName}
            onChange={(e) => setWorkspaceName(e.target.value)}
            placeholder="Enter workspace name"
            className={error ? 'error' : ''}
          />
          {error && <span className="error-message">{error}</span>}
        </div>
        
        {isAdvancedMode && (
          <div className="form-group advanced-options">
            <label htmlFor="custom-path">Custom Location</label>
            <input
              id="custom-path"
              type="text"
              value={customPath}
              onChange={(e) => setCustomPath(e.target.value)}
              placeholder="Enter custom path (optional)"
            />
            <p className="hint">Leave blank to use default location</p>
          </div>
        )}
        
        <div className="workspace-creation-actions">
          <button 
            type="button" 
            className="btn-cancel"
            onClick={onCancel}
            disabled={isCreating}
          >
            Cancel
          </button>
          <button 
            type="button" 
            className="btn-create"
            onClick={handleCreate}
            disabled={!isValid || isCreating}
          >
            {isCreating ? 'Creating...' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default WorkspaceCreation;