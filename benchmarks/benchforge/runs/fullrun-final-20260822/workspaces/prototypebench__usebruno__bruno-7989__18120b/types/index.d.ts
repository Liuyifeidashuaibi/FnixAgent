/*
 * Type declarations for Bruno Snapshot Example Index Refactor
 */

import { 
  createCollectionSnapshot, 
  restoreCollectionFromSnapshot,
  getExampleIndexInItem,
  updateExampleAtIndex 
} from './src/containers/Collection';

import { 
  createSnapshot, 
  restoreFromSnapshot,
  getExampleIndex 
} from './src/utils/snapshot';

export { 
  createCollectionSnapshot, 
  restoreCollectionFromSnapshot,
  getExampleIndexInItem,
  updateExampleAtIndex 
};

export { 
  createSnapshot, 
  restoreFromSnapshot,
  getExampleIndex 
};

export default {
  createCollectionSnapshot,
  restoreCollectionFromSnapshot,
  getExampleIndexInItem,
  updateExampleAtIndex,
  createSnapshot,
  restoreFromSnapshot,
  getExampleIndex
};