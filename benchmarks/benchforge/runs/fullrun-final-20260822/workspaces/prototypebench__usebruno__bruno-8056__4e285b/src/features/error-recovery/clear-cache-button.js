import React from 'react';

const ClearCacheButton = ({ onClear }) => {
  return (
    <button 
      className="btn btn-sm btn-outline-danger" 
      onClick={onClear}
      title="Clear all cached data"
    >
      Clear Cache
    </button>
  );
};

export default ClearCacheButton;
