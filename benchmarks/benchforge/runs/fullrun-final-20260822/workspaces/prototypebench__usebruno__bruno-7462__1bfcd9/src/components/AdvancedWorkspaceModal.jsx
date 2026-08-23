import React, { useState, useEffect } from 'react';

const AdvancedWorkspaceModal = ({ isOpen, onClose, onConfirm }) => {
  const [workspaceName, setWorkspaceName] = useState('');
  const [customPath, setCustomPath] = useState('');
  const [useDefaultLocation, setUseDefaultLocation] = useState(true);
  const [isValid, setIsValid] = useState(false);
  const [error, setError] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    if (!workspaceName.trim()) {
      setIsValid(false);
      setError('Workspace name is required');
      return;
    }

    // Basic validation
    if (workspaceName.length < 2 || workspaceName.length > 50) {
      setIsValid(false);
      setError('Workspace name must be between 2 and 50 characters');
      return;
    }

    if (/[^a-zA-Z0-9\-_\s]/.test(workspaceName)) {
      setIsValid(false);
      setError('Workspace name can only contain letters, numbers, spaces, hyphens, and underscores');
      return;
    }

    if (workspaceName !== workspaceName.trim()) {
      setIsValid(false);
      setError('Workspace name cannot have leading or trailing spaces');
      return;
    }

    setIsValid(true);
    setError('');
  }, [workspaceName]);

  const handleConfirm = async () => {
    if (!isValid || isCreating) return;
    
    setIsCreating(true);
    try {
      // Simulate filesystem operation
      await new Promise(resolve => setTimeout(resolve, 300));
      
      const workspaceData = {
        name: workspaceName.trim(),
        path: useDefaultLocation ? null : customPath,
        useDefaultLocation,
        createdAt: new Date().toISOString()
      };
      
      onConfirm(workspaceData);
    } catch (err) {
      console.error('Failed to create workspace:', err);
      setError('Failed to create workspace. Please try again.');
    } finally {
      setIsCreating(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay">
      <div className="advanced-workspace-modal">
        <div className="modal-header">
          <h3>Advanced Workspace Creation</h3>
          <button className="close-button" onClick={onClose} aria-label="Close modal">×</button>
        </div>
        
        <div className="modal-content">
          <div className="form-group">
            <label htmlFor="advanced-workspace-name">Workspace Name *</label>
            <input
              id="advanced-workspace-name"
              type="text"
              value={workspaceName}
              onChange={(e) => setWorkspaceName(e.target.value)}
              placeholder="Enter workspace name"
              className={error ? 'error' : ''}
            />
            {error && <span className="error-message">{error}</span>}
          </div>
          
          <div className="form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={useDefaultLocation}
                onChange={(e) => setUseDefaultLocation(e.target.checked)}
              />
              Use default location
            </label>
          </div>
          
          {!useDefaultLocation && (
            <div className="form-group">
              <label htmlFor="advanced-custom-path">Custom Path *</label>
              <input
                id="advanced-custom-path"
                type="text"
                value={customPath}
                onChange={(e) => setCustomPath(e.target.value)}
                placeholder="Enter full path to workspace directory"
              />
              <p className="hint">The directory will be created if it doesn't exist</p>
            </div>
          )}
          
          <div className="modal-footer">
            <button 
              type="button" 
              className="btn-secondary"
              onClick={onClose}
              disabled={isCreating}
            >
              Cancel
            </button>
            <button 
              type="button" 
              className="btn-primary"
              onClick={handleConfirm}
              disabled={!isValid || isCreating}
            >
              {isCreating ? 'Creating...' : 'Create Workspace'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdvancedWorkspaceModal;