/**
 * Packaging shell does not ship its own React tree.
 * Product UI lives in apps/workbench; this entry is unused at runtime
 * (tauri.conf frontendDist → ../workbench/dist).
 */
console.info('[fnix] desktop-tauri packaging shell — UI is @fnixagent/workbench');
