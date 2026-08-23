import { RefObject } from 'react';

/**
 * Scroll position manager instance
 */
export declare const scrollPositionManager: {
  saveScrollPosition: (paneId: string, scrollTop: number) => void;
  getScrollPosition: (paneId: string) => number;
  clearScrollPosition: (paneId: string) => void;
};

/**
 * Hook to manage scroll position for a specific pane
 * @param paneId - Identifier for the pane
 * @returns Object with ref, restoreScroll, and saveScroll functions
 */
export declare function useScrollPosition(paneId: string): {
  ref: RefObject<HTMLElement | null>;
  restoreScroll: () => void;
  saveScroll: () => void;
};

/**
 * Export all components
 */
export { default as RequestEditor } from './RequestEditor';
export { default as HeadersPane } from './HeadersPane';
export { default as AssertionsPane } from './AssertionsPane';
export { default as BodyPane } from './BodyPane';
