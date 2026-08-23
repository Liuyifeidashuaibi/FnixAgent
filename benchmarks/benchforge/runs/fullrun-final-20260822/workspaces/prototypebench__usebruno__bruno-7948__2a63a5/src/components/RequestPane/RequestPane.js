import React, { useEffect, useState } from 'react';

const RequestPane = ({ requests, activeRequestId, onActiveRequestChange }) => {
  const [activeTab, setActiveTab] = useState(activeRequestId);

  // Ensure tab selection stays in sync with active request
  useEffect(() => {
    setActiveTab(activeRequestId);
  }, [activeRequestId]);

  const handleTabSelect = (requestId) => {
    setActiveTab(requestId);
    onActiveRequestChange(requestId);
  };

  return (
    <div className="request-pane">
      <div className="request-tabs-container">
        {/* Request tabs would be rendered here */}
      </div>
      <div className="request-content">
        {/* Active request content would be rendered here */}
      </div>
    </div>
  );
};

export default RequestPane;