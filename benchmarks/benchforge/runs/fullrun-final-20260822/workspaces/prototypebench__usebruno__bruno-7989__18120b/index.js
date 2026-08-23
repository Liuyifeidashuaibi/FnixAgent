/*
 * Bruno Snapshot Example Index Refactor
 * Main entry point for the example index snapshot functionality
 */

export { 
  createCollectionSnapshot, 
  restoreCollectionFromSnapshot,
  getExampleIndexInItem,
  updateExampleAtIndex 
} from './src/containers/Collection';

export { 
  createSnapshot, 
  restoreFromSnapshot,
  getExampleIndex 
} from './src/utils/snapshot';

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