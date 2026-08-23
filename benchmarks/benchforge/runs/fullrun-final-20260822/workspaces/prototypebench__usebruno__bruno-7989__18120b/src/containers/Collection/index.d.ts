/*
 * Type declarations for Bruno Collection utilities
 */

export interface Example {
  id: string;
  name: string;
  // Add other example properties as needed
}

export interface CollectionItem {
  type: string;
  id: string;
  examples?: Example[];
  // Add other item properties as needed
}

export interface Collection {
  items: CollectionItem[];
}

export interface Snapshot {
  version: string;
  timestamp?: string;
  items: CollectionItem[];
}

/**
 * Creates a snapshot of the collection with example indices preserved
 */
export function createCollectionSnapshot(collection: Collection): Snapshot;

/**
 * Restores a collection from a snapshot
 */
export function restoreCollectionFromSnapshot(snapshot: Snapshot): Collection;

/**
 * Gets the index of an example in a collection item
 */
export function getExampleIndexInItem(item: CollectionItem, exampleId: string): number | null;

/**
 * Updates an example at its original index position
 */
export function updateExampleAtIndex(
  item: CollectionItem, 
  exampleId: string, 
  updates: Partial<Example>
): CollectionItem;

export default function Collection(): null;