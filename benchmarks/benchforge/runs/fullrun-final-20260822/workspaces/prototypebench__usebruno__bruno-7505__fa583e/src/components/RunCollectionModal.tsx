import React, { useState } from 'react';

interface RunCollectionModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const RunCollectionModal: React.FC<RunCollectionModalProps> = ({ isOpen, onClose }) => {
  const [isRunning, setIsRunning] = useState(false);
  
  if (!isOpen) return null;

  // Theme-based styling classes
  const themeClasses = {
    modal: 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50',
    modalContent: 'bg-surface w-full max-w-2xl rounded-lg shadow-xl max-h-[90vh] overflow-hidden',
    header: 'bg-surface-secondary border-b border-border px-6 py-4',
    title: 'text-xl font-bold',
    closeBtn: 'absolute right-4 top-4 text-text-secondary hover:text-text-primary',
    body: 'p-6 overflow-y-auto max-h-[calc(90vh-180px)]',
    section: 'bg-surface-secondary border border-border rounded-lg p-4 mb-4',
    heading: 'text-lg font-semibold mb-3',
    inputGroup: 'mb-3',
    label: 'block text-sm font-medium mb-1',
    input: 'w-full px-3 py-2 bg-surface-tertiary border border-border rounded focus:outline-none focus:ring-2 focus:ring-brand',
    select: 'w-full px-3 py-2 bg-surface-tertiary border border-border rounded focus:outline-none focus:ring-2 focus:ring-brand',
    button: 'px-4 py-2 bg-brand text-white rounded hover:bg-brand-dark transition-colors',
    runButton: 'px-6 py-3 bg-brand text-white rounded-lg font-medium hover:bg-brand-dark transition-colors',
    cancelButton: 'px-4 py-2 bg-surface-tertiary text-text-primary border border-border rounded hover:bg-surface-secondary transition-colors',
  };

  const handleRun = () => {
    setIsRunning(true);
    // Simulate API call
    setTimeout(() => {
      setIsRunning(false);
      onClose();
    }, 1500);
  };

  return (
    <div className={themeClasses.modal}>
      <div className={themeClasses.modalContent}>
        <div className={themeClasses.header}>
          <div className="flex justify-between items-center">
            <h2 className={themeClasses.title}>Run Collection</h2>
            <button 
              onClick={onClose} 
              className={themeClasses.closeBtn}
              aria-label="Close modal"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
        
        <div className={themeClasses.body}>
          {/* Two Separate Sections */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Configuration Section */}
            <div className={themeClasses.section}>
              <h3 className={themeClasses.heading}>Configuration</h3>
              
              <div className={themeClasses.inputGroup}>
                <label className={themeClasses.label}>Delay between requests (ms)</label>
                <input 
                  type="number" 
                  defaultValue="0" 
                  className={themeClasses.input}
                  placeholder="0"
                />
              </div>
              
              <div className={themeClasses.inputGroup}>
                <label className={themeClasses.label}>Include tags</label>
                <input 
                  type="text" 
                  className={themeClasses.input}
                  placeholder="e.g., auth, api"
                />
              </div>
              
              <div className={themeClasses.inputGroup}>
                <label className={themeClasses.label}>Exclude tags</label>
                <input 
                  type="text" 
                  className={themeClasses.input}
                  placeholder="e.g., skip, deprecated"
                />
              </div>
              
              <div className={themeClasses.inputGroup}>
                <label className={themeClasses.label}>Environment</label>
                <select className={themeClasses.select}>
                  <option>Default</option>
                  <option>Development</option>
                  <option>Production</option>
                  <option>Staging</option>
                </select>
              </div>
            </div>

            {/* Run Options Section */}
            <div className={themeClasses.section}>
              <h3 className={themeClasses.heading}>Run Options</h3>
              
              <div className="space-y-4">
                <div>
                  <h4 className="font-medium mb-2">Request Selection</h4>
                  <div className="space-y-2">
                    <div className="flex items-center">
                      <input type="radio" id="allRequests" name="requestSelection" defaultChecked className="mr-2" />
                      <label htmlFor="allRequests" className="text-sm">Run all requests</label>
                    </div>
                    <div className="flex items-center">
                      <input type="radio" id="selectedOnly" name="requestSelection" className="mr-2" />
                      <label htmlFor="selectedOnly" className="text-sm">Run selected requests only</label>
                    </div>
                    <div className="flex items-center">
                      <input type="radio" id="byTag" name="requestSelection" className="mr-2" />
                      <label htmlFor="byTag" className="text-sm">Run by tag</label>
                    </div>
                  </div>
                </div>
                
                <div>
                  <h4 className="font-medium mb-2">Advanced Options</h4>
                  <div className="space-y-2">
                    <div className="flex items-center">
                      <input type="checkbox" id="stopOnError" className="mr-2 rounded" />
                      <label htmlFor="stopOnError" className="text-sm">Stop on first error</label>
                    </div>
                    <div className="flex items-center">
                      <input type="checkbox" id="clearConsole" className="mr-2 rounded" />
                      <label htmlFor="clearConsole" className="text-sm">Clear console before run</label>
                    </div>
                    <div className="flex items-center">
                      <input type="checkbox" id="showDetails" className="mr-2 rounded" />
                      <label htmlFor="showDetails" className="text-sm">Show detailed results</label>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          {/* Action Buttons */}
          <div className="flex justify-end space-x-3 pt-4">
            <button 
              onClick={onClose} 
              className={themeClasses.cancelButton}
              disabled={isRunning}
            >
              Cancel
            </button>
            <button 
              onClick={handleRun}
              className={`${themeClasses.runButton} ${isRunning ? 'opacity-75 cursor-not-allowed' : ''}`}
              disabled={isRunning}
            >
              {isRunning ? 'Running...' : 'Run Collection'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RunCollectionModal;