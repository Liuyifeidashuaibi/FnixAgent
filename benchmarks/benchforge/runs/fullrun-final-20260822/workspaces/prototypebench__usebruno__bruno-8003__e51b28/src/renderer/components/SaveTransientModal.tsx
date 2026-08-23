import React, { useState, useEffect } from 'react';

interface SaveTransientModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const SaveTransientModal: React.FC<SaveTransientModalProps> = ({ isOpen, onClose }) => {
  const [isSaving, setIsSaving] = useState(false);

  if (!isOpen) return null;

  const handleSave = () => {
    setIsSaving(true);
    // Simulate save operation
    setTimeout(() => {
      setIsSaving(false);
      onClose();
    }, 1000);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <h2>Save Transient Requests</h2>
        <p>Would you like to save your transient requests before quitting?</p>
        
        <div className="modal-actions">
          <button onClick={handleSave} disabled={isSaving}>
            {isSaving ? 'Saving...' : 'Save'}
          </button>
          <button onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
};

export default SaveTransientModal;
