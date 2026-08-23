import React from 'react';

const RequestTabPanel = ({ request, onSend }) => {
  return (
    <div className="request-tab-panel">
      {/* Simplified panel without duplicate cancel logic */}
      {/* Cancel logic is now handled centrally in sendRequest */}
      <button onClick={() => onSend(request)}>
        Send Request
      </button>
      <div className="request-content">
        {/* Request content rendering */}
      </div>
    </div>
  );
};

export default RequestTabPanel;