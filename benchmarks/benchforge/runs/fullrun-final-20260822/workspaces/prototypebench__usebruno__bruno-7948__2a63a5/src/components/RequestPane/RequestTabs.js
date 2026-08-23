import React, { useEffect, useState, useCallback } from 'react';

const RequestTabs = ({ 
  requests, 
  activeRequestId, 
  onTabSelect,
  onTabClose 
}) => {
  const [activeTab, setActiveTab] = useState(activeRequestId);

  // Sync active tab with active request ID when it changes
  useEffect(() => {
    if (activeRequestId && activeRequestId !== activeTab) {
      setActiveTab(activeRequestId);
    }
  }, [activeRequestId, activeTab]);

  // Handle tab selection
  const handleTabClick = useCallback((requestId) => {
    setActiveTab(requestId);
    onTabSelect(requestId);
  }, [onTabSelect]);

  // Handle tab close
  const handleTabClose = useCallback((requestId, e) => {
    e.stopPropagation();
    if (onTabClose) {
      onTabClose(requestId);
    }
  }, [onTabClose]);

  return (
    <div className="request-tabs">
      {requests.map((request) => (
        <div 
          key={request.id} 
          className={`tab-item ${activeTab === request.id ? 'active' : ''}`}
          onClick={() => handleTabClick(request.id)}
        >
          <span className="tab-name">{request.name}</span>
          <button 
            className="tab-close"
            onClick={(e) => handleTabClose(request.id, e)}
            aria-label={`Close ${request.name} tab`}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
};

export default RequestTabs;