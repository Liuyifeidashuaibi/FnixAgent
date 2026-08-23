/*
 * Main entry point for Bruno Snapshot Example Index Refactor
 */

export { 
  createCollectionSnapshot, 
  restoreCollectionFromSnapshot,
  getExampleIndexInItem,
  updateExampleAtIndex 
} from './containers/Collection';

export { 
  createSnapshot, 
  restoreFromSnapshot,
  getExampleIndex 
} from './utils/snapshot';

// Default export for backward compatibility
export default {
  createCollectionSnapshot,
  restoreCollectionFromSnapshot,
  getExampleIndexInItem,
  updateExampleAtIndex,
  createSnapshot,
  restoreFromSnapshot,
  getExampleIndex
};