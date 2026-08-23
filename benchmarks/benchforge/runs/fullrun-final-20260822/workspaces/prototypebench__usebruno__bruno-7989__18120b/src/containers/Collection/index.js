/*
 * Collection container for Bruno
 * Integrates with snapshot system to preserve example indices
 */

import { createCollectionSnapshot, restoreCollectionFromSnapshot, getExampleIndexInItem, updateExampleAtIndex } from './utils';

// Export collection utilities for snapshot and example index handling
export {
  createCollectionSnapshot,
  restoreCollectionFromSnapshot,
  getExampleIndexInItem,
  updateExampleAtIndex
};

// Default export for the collection component
export default function Collection() {
  return null; // Placeholder for actual component implementation
}