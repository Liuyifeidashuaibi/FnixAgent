import React, { useState, useRef, useEffect } from 'react';

const VariableEditorTooltip = ({ value, initialValue, onCopy, onPinToggle }) => {
  const [isPinned, setIsPinned] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const tooltipRef = useRef(null);

  // Handle click outside to dismiss unpinned tooltips
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!isPinned && tooltipRef.current && !tooltipRef.current.contains(event.target)) {
        setIsPinned(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isPinned]);

  const handlePinClick = () => {
    const newPinnedState = !isPinned;
    setIsPinned(newPinnedState);
    if (onPinToggle) {
      onPinToggle(newPinnedState);
    }
  };

  const handleCopy = () => {
    // Copy the current value, not just initial value
    if (onCopy && value !== undefined) {
      onCopy(value);
    }
  };

  // Don't dismiss when hovering over the tooltip itself
  const handleMouseEnter = () => {
    setIsHovered(true);
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
  };

  return (
    <div 
      ref={tooltipRef}
      className={`variable-tooltip ${isPinned ? 'pinned' : ''} ${isHovered ? 'hovered' : ''}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className="tooltip-content">
        <span className="tooltip-value">{value}</span>
        <div className="tooltip-actions">
          <button 
            className="copy-button"
            onClick={handleCopy}
            title="Copy value"
          >
            📋
          </button>
          <button 
            className="pin-button"
            onClick={handlePinClick}
            title={isPinned ? 'Unpin tooltip' : 'Pin tooltip'}
          >
            {isPinned ? '📌' : '📍'}
          </button>
        </div>
      </div>
      {!isPinned && (
        <div className="tooltip-arrow"></div>
      )}
    </div>
  );
};

export default VariableEditorTooltip;