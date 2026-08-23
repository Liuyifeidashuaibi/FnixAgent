/*
 * Collection utilities for Bruno
 * Handles example index preservation during snapshot operations
 */

import { createSnapshot, restoreFromSnapshot, getExampleIndex } from '../../utils/snapshot';

/**
 * Creates a collection snapshot that preserves example indices
 * @param {Object} collection - The collection to snapshot
 * @returns {Object} Snapshot object
 */
export const createCollectionSnapshot = (collection) => {
  return createSnapshot(collection);
};

/**
 * Restores collection from snapshot, maintaining example index information
 * @param {Object} snapshot - The snapshot to restore from
 * @returns {Object} Restored collection
 */
export const restoreCollectionFromSnapshot = (snapshot) => {
  return restoreFromSnapshot(snapshot);
};

/**
 * Gets the example index for a given example ID in a collection item
 * @param {Object} item - The collection item
 * @param {string} exampleId - The example ID
 * @returns {number|null} The example index
 */
export const getExampleIndexInItem = (item, exampleId) => {
  return getExampleIndex(item, exampleId);
};

/**
 * Updates an example in a collection item while preserving its index position
 * @param {Object} item - The collection item
 * @param {string} exampleId - The example ID to update
 * @param {Object} updates - The updates to apply
 * @returns {Object} Updated item
 */
export const updateExampleAtIndex = (item, exampleId, updates) => {
  if (!item || !item.examples || !Array.isArray(item.examples)) {
    return item;
  }

  const exampleIndex = getExampleIndex(item, exampleId);
  if (exampleIndex === null) {
    return item;
  }

  const updatedExamples = [...item.examples];
  updatedExamples[exampleIndex] = { ...updatedExamples[exampleIndex], ...updates };
  
  return {
    ...item,
    examples: updatedExamples
  };
};