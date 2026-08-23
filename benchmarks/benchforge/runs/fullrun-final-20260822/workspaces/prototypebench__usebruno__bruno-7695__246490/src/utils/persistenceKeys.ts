/**
 * Utility functions for generating consistent persistence keys
 */

/**
 * Generate a persistence key for editor scroll position
 * Format: persisted::<tabUid>::editor-scroll-<entityUid>
 */
export const getEditorScrollKey = (tabUid: string, entityUid: string): string => {
  return `persisted::${tabUid}::editor-scroll-${entityUid}`;
};

/**
 * Generate a persistence key for container scroll position
 * Format: persisted::<tabUid>::container-scroll-<entityUid>
 */
export const getContainerScrollKey = (tabUid: string, entityUid: string): string => {
  return `persisted::${tabUid}::container-scroll-${entityUid}`;
};

/**
 * Generate a persistence key for response pane scroll position
 * Format: persisted::<tabUid>::response-scroll-<entityUid>
 */
export const getResponseScrollKey = (tabUid: string, entityUid: string): string => {
  return `persisted::${tabUid}::response-scroll-${entityUid}`;
};

/**
 * Generate a persistence key for folder settings scroll position
 * Format: persisted::<tabUid>::folder-settings-scroll-<entityUid>
 */
export const getFolderSettingsScrollKey = (tabUid: string, entityUid: string): string => {
  return `persisted::${tabUid}::folder-settings-scroll-${entityUid}`;
};

/**
 * Generate a persistence key for collection settings scroll position
 * Format: persisted::<tabUid>::collection-settings-scroll-<entityUid>
 */
export const getCollectionSettingsScrollKey = (tabUid: string, entityUid: string): string => {
  return `persisted::${tabUid}::collection-settings-scroll-${entityUid}`;
};