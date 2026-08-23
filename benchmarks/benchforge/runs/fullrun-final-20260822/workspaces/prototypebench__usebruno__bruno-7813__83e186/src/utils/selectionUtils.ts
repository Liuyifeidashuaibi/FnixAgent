/**
 * Utility functions for handling selections in Bruno
 */

/**
 * Creates a new Set from an array of items
 */
export const createSelectionSet = <T>(items: T[]): Set<T> => {
  return new Set(items);
};

/**
 * Toggles an item in a selection set
 */
export const toggleSelection = <T>(set: Set<T>, item: T): Set<T> => {
  const newSet = new Set(set);
  if (newSet.has(item)) {
    newSet.delete(item);
  } else {
    newSet.add(item);
  }
  return newSet;
};

/**
 * Selects all items in a set
 */
export const selectAll = <T>(items: T[]): Set<T> => {
  return new Set(items);
};

/**
 * Deselects all items
 */
export const deselectAll = <T>(): Set<T> => {
  return new Set();
};

/**
 * Checks if all items are selected
 */
export const areAllSelected = <T>(items: T[], selected: Set<T>): boolean => {
  if (items.length === 0) return true;
  return items.every(item => selected.has(item));
};

/**
 * Gets the count of selected items
 */
export const getSelectedCount = <T>(selected: Set<T>): number => {
  return selected.size;
};
