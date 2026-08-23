# Bruno Scroll Persistence

This package provides React hooks for persisting scroll positions across tab switches in the Bruno API client.

## Features

- ✅ Persist scroll positions for request panes (Headers, Body, Script)
- ✅ Persist scroll positions for response panes
- ✅ Persist scroll positions for folder settings
- ✅ Persist scroll positions for collection settings
- ✅ Automatic cleanup on tab close
- ✅ Global cleanup on app boot
- ✅ TypeScript support
- ✅ React hook pattern

## Installation

```bash
# Install as a dependency in your Bruno project
npm install bruno-scroll-persistence
```

## Usage

### Editor Scroll Persistence

```tsx
import { usePersistedEditorScroll } from 'bruno-scroll-persistence';

const MyEditor = ({ tabUid, entityUid }) => {
  const { editorRef, isRestored } = usePersistedEditorScroll(tabUid, entityUid);

  return (
    <div ref={editorRef} className="editor-container">
      {/* Your editor content */}
    </div>
  );
};
```

### Container Scroll Persistence

```tsx
import { usePersistedContainerScroll } from 'bruno-scroll-persistence';

const MyContainer = ({ tabUid, entityUid }) => {
  const { containerRef, isRestored } = usePersistedContainerScroll(tabUid, entityUid);

  return (
    <div ref={containerRef} className="scrollable-container">
      {/* Your container content */}
    </div>
  );
};
```

## Persistence Key Format

Keys follow the format: `persisted::<tabUid>::<type>-scroll-<entityUid>`

- `tabUid`: Unique identifier for the tab
- `type`: editor, container, response, folder-settings, collection-settings
- `entityUid`: Unique identifier for the specific entity

## State Management

- `clearPersistedScope(tabUid)`: Clears all persisted state for a specific tab
- `clearAllPersistedState()`: Clears all persisted state on app boot

## Contributing

Contributions are welcome! Please see the [contribution guidelines](CONTRIBUTING.md).

## License

MIT