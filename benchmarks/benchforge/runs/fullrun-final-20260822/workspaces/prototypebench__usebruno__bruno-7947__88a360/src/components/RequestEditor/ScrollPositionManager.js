import { useEffect, useRef, useState } from 'react';

/**
 * ScrollPositionManager - Manages scroll position persistence for request panes
 * (Assertions, Headers, Body)
 */
class ScrollPositionManager {
  constructor() {
    this.scrollPositions = new Map();
  }

  /**
   * Save scroll position for a specific pane
   * @param {string} paneId - Identifier for the pane (e.g., 'assertions', 'headers', 'body')
   * @param {number} scrollTop - Scroll position
   */
  saveScrollPosition(paneId, scrollTop) {
    if (scrollTop !== undefined && scrollTop !== null) {
      this.scrollPositions.set(paneId, scrollTop);
      // Persist to localStorage for cross-session persistence
      try {
        localStorage.setItem(`bruno-scroll-${paneId}`, scrollTop.toString());
      } catch (e) {
        // Ignore localStorage errors
      }
    }
  }

  /**
   * Get saved scroll position for a pane
   * @param {string} paneId - Identifier for the pane
   * @returns {number} Saved scroll position or 0
   */
  getScrollPosition(paneId) {
    // Try to get from memory first
    const fromMemory = this.scrollPositions.get(paneId);
    if (fromMemory !== undefined) {
      return fromMemory;
    }
    
    // Fall back to localStorage
    try {
      const saved = localStorage.getItem(`bruno-scroll-${paneId}`);
      return saved ? parseInt(saved, 10) : 0;
    } catch (e) {
      return 0;
    }
  }

  /**
   * Clear scroll position for a pane
   * @param {string} paneId - Identifier for the pane
   */
  clearScrollPosition(paneId) {
    this.scrollPositions.delete(paneId);
    try {
      localStorage.removeItem(`bruno-scroll-${paneId}`);
    } catch (e) {
      // Ignore localStorage errors
    }
  }
}

// Export singleton instance
export const scrollPositionManager = new ScrollPositionManager();

/**
 * Hook to manage scroll position for a specific pane
 * @param {string} paneId - Identifier for the pane
 * @returns {Object} Object with ref, restoreScroll, and saveScroll functions
 */
export function useScrollPosition(paneId) {
  const ref = useRef(null);
  const [isRestored, setIsRestored] = useState(false);

  const restoreScroll = () => {
    if (ref.current && !isRestored) {
      const savedPosition = scrollPositionManager.getScrollPosition(paneId);
      if (savedPosition > 0) {
        ref.current.scrollTop = savedPosition;
      }
      setIsRestored(true);
    }
  };

  const saveScroll = () => {
    if (ref.current) {
      scrollPositionManager.saveScrollPosition(paneId, ref.current.scrollTop);
    }
  };

  useEffect(() => {
    // Restore scroll position on mount
    restoreScroll();
    
    // Set up scroll listener
    const element = ref.current;
    if (element) {
      const handleScroll = () => saveScroll();
      element.addEventListener('scroll', handleScroll);
      
      return () => {
        element.removeEventListener('scroll', handleScroll);
      };
    }
  }, [ref.current]);

  return {
    ref,
    restoreScroll,
    saveScroll
  };
}
