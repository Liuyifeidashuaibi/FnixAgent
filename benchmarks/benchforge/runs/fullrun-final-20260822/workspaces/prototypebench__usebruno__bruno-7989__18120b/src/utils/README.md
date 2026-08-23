# Utils

## Snapshot Utility

The snapshot utility provides functionality for creating and restoring collection snapshots with example index preservation.

### Features
- `createSnapshot()`: Creates a snapshot that stores example indices in `__exampleIndex` properties
- `restoreFromSnapshot()`: Restores collections while removing internal `__exampleIndex` properties
- `getExampleIndex()`: Retrieves the index of a specific example in a collection item

### Usage

```javascript
import { createSnapshot, restoreFromSnapshot } from './snapshot';

// Create snapshot with example indices
const snapshot = createSnapshot(collection);

// Restore collection from snapshot
const restoredCollection = restoreFromSnapshot(snapshot);
```

### Example Index Storage

When creating snapshots, example objects are enhanced with `__exampleIndex` properties that store their original array position. This enables accurate restoration and deterministic example selection by index rather than just by name.