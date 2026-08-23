# Scroll Persistence Hooks

This directory contains hooks for persisting scroll positions across tab switches in Bruno.

## Available Hooks

### `usePersistedEditorScroll`

Persists and restores scroll position for editor components (e.g., request body, scripts, headers).

**Usage:**
```tsx
const { editorRef, isRestored } = usePersistedEditorScroll(tabUid, entityUid);

return (
  <div ref={editorRef} className="editor-container">
    {/* editor content */}
  </div>
);
```

### `usePersistedContainerScroll`

Persists and restores scroll position for generic container components (e.g., response pane, folder settings).

**Usage:**
```tsx
const { containerRef, isRestored } = usePersistedContainerScroll(tabUid, entityUid);

return (
  <div ref={containerRef} className="scrollable-container">
    {/* container content */}
  </div>
);
```

## Persistence Key Format

Keys follow the format: `persisted::<tabUid>::<type>-scroll-<entityUid>`

- `tabUid`: Unique identifier for the tab
- `type`: editor, container, response, folder-settings, collection-settings
- `entityUid`: Unique identifier for the specific entity

## State Management

- `clearPersistedScope(tabUid)`: Clears all persisted state for a specific tab
- `clearAllPersistedState()`: Clears all persisted state on app boot
- Keys are automatically cleaned up when tabs are closed

## Implementation Details

- Uses localStorage for persistence
- Handles errors gracefully with console warnings
- Uses requestAnimationFrame for smooth restoration
- Saves scroll position on scroll events and component unmount
- Includes type safety and proper React hook patterns